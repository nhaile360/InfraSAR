#!/usr/bin/env python3
"""Build independent Roseires shoreline maps and compare them on the NISAR grid."""

import argparse
import base64
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen
import zlib

try:
    import numpy as np
    import tifffile
except ModuleNotFoundError as exc:
    raise SystemExit(
        "Missing Python dependencies. From the project folder, run "
        "'conda env create -f roseires-pipeline/environment.yml', then launch the "
        "pipeline with 'conda run -n roseires-pipeline python'."
    ) from exc

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT))
from crop_roseires import ARCHIVE, SCENES, load_token
from catalog_nisar import CATALOG

HOLDOUT = {
    "2026-08-17": "NISAR_L2_PR_GCOV_028_057_A_007_2005_DHDH_A_20260817T031901_20260817T031935_P05023_N_F_J_001",
    "2026-10-04": "NISAR_L2_PR_GCOV_032_057_A_007_2005_DHDH_A_20261004T031900_20261004T031935_P05023_N_F_J_001",
}
PAIRS = {"pilot": SCENES, "holdout": HOLDOUT}
OPTICAL_PILOT = {"2026-08-29": "2026-08-26", "2026-10-16": "2026-10-15"}
TILES = ("36PXT", "36PXU")
STAC = "https://earth-search.aws.element84.com/v1/search"
AOI = [34.35, 11.71, 34.48, 11.79]
WATER_CONTROL = (651500, 1297900, 653200, 1300500)
LAND_CONTROL = (647600, 1301800, 648200, 1302800)
POLICY = {
    "fixed_cutoff_db": -17.0,
    "local_uncertainty_db": 0.75,
    "water_control_utm": list(WATER_CONTROL),
    "land_control_utm": list(LAND_CONTROL),
    "local_rule": "3×3 median; midpoint of open-water P90 and land P10 per date; abstain if the controls overlap",
}

LAND, WATER, GAIN, LOSS = 1, 2, 3, 4
GAP, CLOUD, SHADOW, AMBIGUOUS, NODATA, CONFLICT = 5, 6, 7, 8, 9, 10
OUTSIDE_TILE, TILE_CONFLICT = 255, 254
LABELS = {
    1: "Persistent land", 2: "Persistent water", 3: "Land to water",
    4: "Water to land", 5: "Outside tile coverage", 6: "Cloud",
    7: "Cloud shadow", 8: "Ambiguous", 9: "No observation",
    10: "Tile overlap disagreement",
}
AGREEMENT = {
    1: "Both stable", 2: "Matching gain", 3: "Matching loss",
    4: "Optical change missed", 5: "Radar false alarm against optical",
    6: "Opposite direction", 7: "Unverified radar change",
    8: "Optical evidence unavailable", 9: "Radar abstained",
}


def dump(path, value):
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(value, indent=2) + "\n")
    temp.replace(path)


def load(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def raster(path):
    with tifffile.TiffFile(path) as f:
        page = f.pages[0]
        tags = page.tags
        scale = tags[33550].value
        tie = tags[33922].value
        keys = tags[34735].value
        epsg = next((keys[i + 3] for i in range(4, len(keys), 4)
                     if keys[i:i + 3] == (3072, 0, 1)), None)
        data = page.asarray(maxworkers=1)
        if epsg != 32636 or scale[:2] != (20, 20) or tie[:3] != (0, 0, 0) or data.ndim != 2:
            raise ValueError(f"Expected a single 20 m UTM 36N band: {path}")
        grid = {"width": page.imagewidth, "height": page.imagelength,
                "west": tie[3], "north": tie[4], "epsg": epsg, "pixel_m": 20}
        return data, grid, {k: tags[k].value for k in (33550, 33922, 34735, 34737) if k in tags}


def require_grid(actual, expected, filename):
    if (actual["width"], actual["height"]) != (expected["width"], expected["height"]) or any(
        abs(actual[k] - expected[k]) > 1e-6 for k in ("west", "north")
    ):
        raise ValueError(f"Raster is not on the shared NISAR grid: {filename}")


def geotiff(path, data, tags):
    types = {33550: "d", 33922: "d", 34735: "H", 34737: "s"}
    extratags = [(k, types[k], len(v), v, False) for k, v in tags.items()]
    tifffile.imwrite(path, data.astype(np.uint8), compression="deflate",
                    metadata=None, extratags=extratags)


def bounds(grid):
    return [grid["west"], grid["north"] - grid["height"] * 20,
            grid["west"] + grid["width"] * 20, grid["north"]]


def gdalwarp(source, output, grid, binary, optical, env=None):
    executable = binary / "gdalwarp" if binary else shutil.which("gdalwarp")
    if not executable or not Path(executable).is_file():
        raise ValueError("Install GDAL or pass --gdal-bin with the directory containing gdalwarp.")
    with TemporaryDirectory(dir=output.parent) as scratch:
        tmp = Path(scratch) / output.name
        options = (["-ot", "Byte", "-srcnodata", "None", "-dstnodata", "255", "-co", "COMPRESS=NONE"]
                   if optical else ["-dstnodata", "nan", "-co", "COMPRESS=DEFLATE", "-co", "TILED=YES"])
        subprocess.run([
            str(executable), "-q", "-of", "GTiff", "-t_srs", "EPSG:32636",
            "-te", *map(str, bounds(grid)), "-ts", str(grid["width"]), str(grid["height"]),
            "-r", "near", *options, str(source), str(tmp),
        ], check=True, env=env)
        _, actual, _ = raster(tmp)
        require_grid(actual, grid, output)
        tmp.replace(output)


def radar_info(when, scene):
    stamp = re.search(r"_(\d{8}T\d{6})_", scene)[1]
    acquired = datetime.strptime(stamp, "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
    return {"date": when, "id": scene, "datetime": acquired.isoformat(),
            "url": f"{ARCHIVE}/{scene}/{scene}.h5", "band": "Frequency A HHHH",
            "resampling": "nearest neighbor"}


def midpoint(when):
    return datetime.fromisoformat(when + "T12:00:00+00:00")


def search_tiles(when, days):
    center = date.fromisoformat(when)
    start, end = center - timedelta(days=days), center + timedelta(days=days)
    query = {"collections": "sentinel-2-l2a", "bbox": ",".join(map(str, AOI)), "limit": 100,
             "datetime": f"{start}T00:00:00Z/{end}T23:59:59Z"}
    url = f"{STAC}?{urlencode(query)}"
    visited = set()
    items = []
    while url:
        if url in visited:
            raise ValueError(f"The Sentinel-2 catalog repeated a page while searching around {when}.")
        visited.add(url)
        request = Request(url, headers={"Accept": "application/geo+json"})
        with urlopen(request, timeout=25) as response:
            result = json.load(response)
        items.extend(result["features"])
        next_href = next((link["href"] for link in result.get("links", []) if link.get("rel") == "next"), None)
        url = urljoin(url, next_href) if next_href else None
    return items


def choose_tiles(items, when, pilot, target=None):
    by_tile = {tile: [] for tile in TILES}
    for item in items:
        match = re.fullmatch(r"(S2[ABC])_(36PX[TU])_(\d{8})_\d+_L2A", item["id"])
        if not match or "scl" not in item["assets"]:
            continue
        platform, tile, _ = match.groups()
        if pilot and tile == "36PXT" and item["id"] != f"S2C_36PXT_{when.replace('-', '')}_0_L2A":
            continue
        prop = item["properties"]
        timestamp = datetime.fromisoformat(prop["datetime"].replace("Z", "+00:00"))
        by_tile[tile].append((item, platform, timestamp, prop.get("s2:datatake_id"),
                              prop.get("sat:relative_orbit")))
    candidates = []
    for a in by_tile["36PXT"]:
        for b in by_tile["36PXU"]:
            if a[1] != b[1] or a[2].date() != b[2].date() or abs((a[2] - b[2]).total_seconds()) > 180:
                continue
            if (a[3] and b[3] and a[3] != b[3]) or (a[4] is not None and b[4] is not None and a[4] != b[4]):
                continue
            candidates.append((abs((a[2] - (target or midpoint(when))).total_seconds()), a[0]["id"], a, b))
    if not candidates:
        raise ValueError(f"No co-acquired 36PXT/36PXU Sentinel-2 pair found near {when}. Supply both dated source tiles via --optical-manifest.")
    _, _, a, b = min(candidates, key=lambda item: item[:2])
    return {tile: {"id": record[0]["id"], "datetime": record[2].isoformat(),
                   "tile": tile, "scl": record[0]["assets"]["scl"]["href"]}
            for tile, record in zip(TILES, (a, b))}


def optical_sources(pair, manifest):
    if manifest:
        provided = load(manifest)
        result = {}
        for when in PAIRS[pair]:
            rows = provided[when]
            result[when] = {}
            for tile in TILES:
                row = dict(rows[tile])
                match = re.fullmatch(r"(S2[ABC])_(36PX[TU])_(\d{8})_\d+_L2A", row["id"])
                if not match or match[2] != tile:
                    raise ValueError(f"Scene ID does not match {tile}: {row['id']}")
                time = datetime.fromisoformat(row["datetime"].replace("Z", "+00:00"))
                if time.tzinfo is None:
                    raise ValueError(f"Provide a timezone-aware acquisition timestamp: {row['id']}")
                time = time.astimezone(timezone.utc)
                if time.strftime("%Y%m%d") != match[3]:
                    raise ValueError(f"Provide a UTC timestamp matching the scene date: {row['id']}")
                if pair == "pilot" and time.date().isoformat() != OPTICAL_PILOT[when]:
                    raise ValueError(f"Use {OPTICAL_PILOT[when]} Sentinel-2 data for the pilot around {when}.")
                if pair == "holdout" and abs((time.date() - date.fromisoformat(when)).days) > 3:
                    raise ValueError(f"The optical reference for {when} must be within three calendar days.")
                if not row["scl"].startswith("https://"):
                    row["scl"] = str((manifest.parent / row["scl"]).resolve())
                result[when][tile] = dict(row, tile=tile, datetime=time.isoformat())
            first, second = (result[when][tile] for tile in TILES)
            t0, t1 = (datetime.fromisoformat(row["datetime"].replace("Z", "+00:00")) for row in (first, second))
            if first["id"][:3] != second["id"][:3] or t0.date() != t1.date() or abs((t1-t0).total_seconds()) > 180:
                raise ValueError("Both tiles must have the same platform and near-identical acquisition times.")
        return result
    return {when: choose_tiles(search_tiles(OPTICAL_PILOT[when], 0), OPTICAL_PILOT[when], True)
            if pair == "pilot" else choose_tiles(search_tiles(when, 3), when, False,
                datetime.fromisoformat(radar_info(when, scene)["datetime"]))
            for when, scene in PAIRS[pair].items()}


def usable_scl(data):
    return np.isin(data, (4, 5, 6))


def mosaic(pxt, pxu):
    result = pxt.copy()
    ok_a, ok_b = usable_scl(pxt), usable_scl(pxu)
    # Prefer a usable classification; retain both raw tiles for inspection.
    use_u = (pxt == OUTSIDE_TILE) | (ok_b & ~ok_a) | ((pxt == 0) & (pxu != OUTSIDE_TILE))
    result[use_u] = pxu[use_u]
    result[ok_a & ok_b & ((pxt == 6) != (pxu == 6))] = TILE_CONFLICT
    return result


def scl_state(data):
    state = np.full(data.shape, AMBIGUOUS, dtype=np.uint8)
    state[np.isin(data, (4, 5))] = LAND
    state[data == 6] = WATER
    state[np.isin(data, (8, 9, 10))] = CLOUD
    state[data == 3] = SHADOW
    state[data == 0] = NODATA
    state[data == OUTSIDE_TILE] = GAP
    state[data == TILE_CONFLICT] = CONFLICT
    return state


def change(a, b):
    values = np.full(a.shape, AMBIGUOUS, dtype=np.uint8)
    values[(a == LAND) & (b == LAND)] = LAND
    values[(a == WATER) & (b == WATER)] = WATER
    values[(a == LAND) & (b == WATER)] = GAIN
    values[(a == WATER) & (b == LAND)] = LOSS
    # Both per-date states are preserved for inspection when both are invalid.
    for code in (SHADOW, CLOUD, CONFLICT, NODATA, GAP):
        values[(a == code) | (b == code)] = code
    return values


def median_grid(values):
    padded = np.pad(values, 1, mode="edge")
    neighborhoods = np.lib.stride_tricks.sliding_window_view(padded, (3, 3))
    flat = neighborhoods.reshape(*values.shape, 9)
    filled = np.where(np.isfinite(flat), flat, np.inf)
    n = np.isfinite(flat).sum(axis=-1)
    ordered = np.sort(filled, axis=-1)
    median = np.take_along_axis(ordered, ((n - 1).clip(min=0)//2)[..., None], axis=-1)[..., 0]
    median[(n < 5) | ~np.isfinite(values)] = np.nan
    return median


def db(data):
    output = np.full(data.shape, np.nan, np.float32)
    valid = np.isfinite(data) & (data > 0)
    output[valid] = 10 * np.log10(data[valid])
    return output


def radar_states(plane, threshold, margin=0):
    state = np.full(plane.shape, AMBIGUOUS, dtype=np.uint8)
    state[~np.isfinite(plane)] = NODATA
    if threshold is not None:
        state[np.isfinite(plane) & (plane <= threshold - margin)] = WATER
        state[np.isfinite(plane) & (plane > threshold + margin)] = LAND
    return state


def control_values(plane, grid, box, p):
    x = grid["west"] + (np.arange(grid["width"]) + .5)*20
    y = grid["north"] - (np.arange(grid["height"]) + .5)*20
    west, south, east, north = box
    values = plane[np.ix_((y >= south) & (y <= north), (x >= west) & (x <= east))]
    valid = values[np.isfinite(values)]
    return float(np.percentile(valid, p)) if valid.size >= 25 else None


def calibrate(plane, grid):
    water = control_values(plane, grid, WATER_CONTROL, 90)
    land = control_values(plane, grid, LAND_CONTROL, 10)
    margin = POLICY["local_uncertainty_db"]
    threshold = (water + land) / 2 if water is not None and land is not None and land - water > 2*margin else None
    return {"water_p90_db": water, "land_p10_db": land, "threshold_db": threshold}


def agreement(radar, optical):
    out = np.full(radar.shape, 1, dtype=np.uint8)
    rc, oc = np.isin(radar, (GAIN, LOSS)), np.isin(optical, (GAIN, LOSS))
    valid = optical < GAP
    out[(radar == GAIN) & (optical == GAIN)] = 2
    out[(radar == LOSS) & (optical == LOSS)] = 3
    out[oc & ~rc] = 4
    out[valid & rc & ~oc] = 5
    out[valid & rc & oc & (radar != optical)] = 6
    out[~valid & rc] = 7
    out[~valid & ~rc] = 8
    out[valid & (radar >= GAP) & ~oc] = 9
    return out


def scores(radar, optical):
    valid = optical < GAP
    result = {"usable_optical_pixels": int(valid.sum()),
              "usable_optical_fraction": float(valid.mean()),
              "radar_abstentions_on_usable_optical": int((valid & (radar >= GAP)).sum()),
              "unverified_radar_change_pixels": int((~valid & np.isin(radar, (GAIN, LOSS))).sum()),
              "optical_states": {LABELS[k]: int((optical == k).sum()) for k in LABELS}}
    for label, k in (("gain", GAIN), ("loss", LOSS)):
        hits = int((valid & (radar == k) & (optical == k)).sum())
        misses = int((valid & (radar != k) & (optical == k)).sum())
        false_alarms = int((valid & (radar == k) & (optical != k)).sum())
        result[label] = {"hits": hits, "misses": misses, "false_alarms": false_alarms,
                         "precision": hits / (hits + false_alarms) if hits + false_alarms else None,
                         "recall": hits / (hits + misses) if hits + misses else None}
    return result


def radar_paths(pair):
    return [ROOT / "roseires-crops" / f"roseires_{when}_HHHH.tif" for when in PAIRS[pair]]


def extract(out, grid, sources, binary):
    mosaics = []
    pxt_states = []
    for when, tiles in sources.items():
        rasters = []
        for tile, scene in tiles.items():
            target = out / f"{when}_{tile}_SCL.tif"
            sidecar = target.with_suffix(".json")
            source = scene["scl"]
            identity = dict(scene, grid=grid, resampling="nearest neighbor",
                            local_source_sha256=None if source.startswith("https://") else digest(Path(source)))
            if not target.is_file() or not sidecar.is_file() or load(sidecar) != identity:
                print(f"Extracting {tile}: {scene['id']}", flush=True)
                if source.startswith("https://"):
                    source = "/vsicurl/" + source
                gdalwarp(source, target, grid, binary, optical=True)
                dump(sidecar, identity)
            plane, found, _ = raster(target)
            require_grid(found, grid, target)
            rasters.append(plane.astype(np.uint8))
        pxt_states.append(scl_state(rasters[0]))
        mosaics.append(mosaic(*rasters))
    layers = [scl_state(plane) for plane in mosaics]
    values = change(*layers)
    single_tile = change(*pxt_states)
    coverage = {
        name: {"usable_both_dates": float((value < GAP).mean()),
               "outside_tile_on_either_date": float((value == GAP).mean())}
        for name, value in (("36PXT_only", single_tile), ("36PXT_and_36PXU", values))
    }
    dump(out / "optical_provenance.json", {"grid": grid, "bounds_utm": bounds(grid), "sources": sources,
         "resampling": "nearest neighbor", "mosaic": "usable class wins; usable land/water disagreement remains unknown",
         "coverage": coverage,
         "raw_scl": {"255": "outside source coverage", "254": "tile disagreement", "0": "source no data",
                     "7": "low-probability cloud or unclassified"}})
    return mosaics, layers, values


def fetch_radar(pair, grid, binary):
    missing = [(when, scene, path) for (when, scene), path in zip(PAIRS[pair].items(), radar_paths(pair))
               if not path.is_file()]
    if not missing:
        print("Radar pair already available.")
        return
    env = dict(os.environ, GDAL_HTTP_AUTH="BEARER", GDAL_HTTP_BEARER=load_token(),
               GDAL_HTTP_NETRC="NO", CPL_CURL_VERBOSE="NO", CPL_DEBUG="OFF",
               GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_TIMEOUT="45")
    for when, scene, path in missing:
        url = radar_info(when, scene)["url"]
        source = f'HDF5:"/vsicurl/{url}"://science/LSAR/GCOV/grids/frequencyA/HHHH'
        print(f"Cropping radar {when}", flush=True)
        gdalwarp(source, path, grid, binary, optical=False, env=env)


def predict(pair, out, grid, tags):
    paths = radar_paths(pair)
    raw = []
    for path in paths:
        data, actual, _ = raster(path)
        require_grid(actual, grid, path)
        raw.append(db(data))
    fixed = change(*(radar_states(plane, POLICY["fixed_cutoff_db"]) for plane in raw))
    planes = [median_grid(plane) for plane in raw]
    calibrations = [calibrate(plane, grid) for plane in planes]
    adaptive = change(*(radar_states(plane, cal["threshold_db"], POLICY["local_uncertainty_db"])
                        for plane, cal in zip(planes, calibrations)))
    for name, result in (("fixed", fixed), ("local", adaptive)):
        geotiff(out / f"radar_change_{name}.tif", result, tags)
    lock = {"policy": POLICY, "grid": grid, "bounds_utm": bounds(grid), "calibrations": calibrations,
            "radar": [dict(radar_info(when, scene), sha256=digest(path))
                      for (when, scene), path in zip(PAIRS[pair].items(), paths)],
            "predictions": {name: digest(out / f"radar_change_{name}.tif") for name in ("fixed", "local")}}
    dump(out / "radar_predictions.json", lock)
    return raw, fixed, adaptive, lock


def verified_predictions(pair, out, grid):
    lock = load(out / "radar_predictions.json")
    require_grid(lock["grid"], grid, "radar prediction record")
    raw = []
    for path, scene in zip(radar_paths(pair), lock["radar"]):
        if digest(path) != scene["sha256"]:
            raise ValueError("Radar source has changed. Regenerate the radar-only predictions.")
        values, actual, _ = raster(path)
        require_grid(actual, grid, path)
        raw.append(db(values))
    changes = []
    for name in ("fixed", "local"):
        path = out / f"radar_change_{name}.tif"
        if digest(path) != lock["predictions"][name]:
            raise ValueError(f"Frozen {name} prediction changed.")
        values, actual, _ = raster(path)
        require_grid(actual, grid, path)
        changes.append(values)
    return raw, *changes, lock


def timeline_planes(manifest, grid, patch):
    """Load aligned, checksum-verified timeline crops as dB planes."""
    if not manifest.is_file():
        return
    catalog = {row["id"]: row for row in load(CATALOG)["granules"]
               if row["status"] == "awaiting native HH verification"}
    seen = set()
    for record in load(manifest):
        source = catalog[record["id"]]
        for field in ("datetime", "maturity", "version", "release", "mode", "source_url"):
            if record[field] != source[field]:
                raise ValueError(f"Observation metadata differs from CMR: {record['id']}")
        if (record["cmr_concept_id"] != source["concept_id"]
                or record["source_checksum_catalog"] != source["source_checksum"]):
            raise ValueError(f"Observation source differs from CMR: {record['id']}")
        if record["datetime"] in seen:
            raise ValueError(f"Duplicate radar acquisition: {record['datetime']}")
        seen.add(record["datetime"])
        filename = f"roseires_{record['datetime'][:10]}_HHHH.tif"
        path = manifest.parent / filename
        if record["raster"] != filename or digest(path) != record["sha256"]:
            raise ValueError(f"Radar crop does not match its manifest: {path}")
        require_grid(record["grid"], grid, manifest)
        raw, actual, _ = raster(path)
        require_grid(actual, grid, path)
        if raw.dtype != np.dtype("float32") or record["inlet_valid_cells"] < 1:
            raise ValueError(f"Radar crop has an unsupported numeric type or no inlet observations: {path}")
        # Compute dB before rounding to Float32 for the browser.
        raw_db = db(raw.astype(np.float64))
        if record["source_nodata"] is not None:
            raw_db[raw == float(record["source_nodata"])] = np.nan
        valid = np.isfinite(raw_db)
        if int(valid.sum()) != record["valid_cells"] or (patch is not None
                and int(valid[patch].sum()) != record["inlet_valid_cells"]):
            raise ValueError(f"Radar crop coverage differs from manifest: {path}")
        yield record, raw_db


def encode(array):
    a = np.ascontiguousarray(array, dtype="<f4" if array.dtype.kind == "f" else "uint8")
    return {"type": "float32" if a.dtype.kind == "f" else "uint8",
            "payload": base64.b64encode(zlib.compress(a.tobytes(), 6)).decode("ascii")}


def report(pair, home, out, grid, tags, optical, predictions):
    mosaics, states, optical_change = optical
    raw, fixed, local, lock = predictions
    if pair == "holdout":
        pilot = load(home / "pilot" / "radar_predictions.json")
        if pilot["policy"] != lock["policy"]:
            raise ValueError("Holdout prediction uses a different policy than the pilot.")
    metrics = {key: scores(prediction, optical_change) for key, prediction in (("fixed", fixed), ("local", local))}
    dump(out / "scores.json", {"pair": pair, "metrics": metrics})
    comparisons = [agreement(rule, optical_change) for rule in (fixed, local)]
    arrays = {"hh_before": raw[0], "hh_after": raw[1], "scl_before": mosaics[0],
              "scl_after": mosaics[1], "opt_before": states[0], "opt_after": states[1],
              "optical": optical_change, "fixed": fixed, "local": local,
              "agreement_fixed": comparisons[0], "agreement_local": comparisons[1]}
    # Keep each overlapping tile's native codes available to the pixel inspector.
    for i, when in enumerate(PAIRS[pair]):
        for tile in TILES:
            arrays[f"tile_{i}_{tile}"] = raster(out / f"{when}_{tile}_SCL.tif")[0]
    for name in ("optical", "agreement_fixed", "agreement_local"):
        geotiff(out / f"{name}.tif", arrays[name], tags)
    provenance = load(out / "optical_provenance.json")
    bundle = {"pair": pair, "grid": grid, "labels": LABELS, "agreement": AGREEMENT,
              "radar": lock, "optical_sources": provenance["sources"], "tile_coverage": provenance["coverage"],
              "metrics": metrics, "arrays": {name: encode(a) for name, a in arrays.items()}}
    template = (HERE / "comparator.html").read_text()
    (out / "comparator.html").write_text(template.replace("__ROSEIRES_DATA__", json.dumps(bundle).replace("<", "\\u003c")))
    print(json.dumps(metrics, indent=2))
    print(f"Open {out / 'comparator.html'}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("extract", "fetch-radar", "predict", "score", "all"))
    parser.add_argument("--pair", choices=PAIRS, default="pilot")
    parser.add_argument("--optical-manifest", type=Path)
    parser.add_argument("--gdal-bin", type=Path)
    parser.add_argument("--output", type=Path, default=HERE / "outputs")
    args = parser.parse_args()
    _, grid, tags = raster(radar_paths("pilot")[0])
    out = args.output / args.pair
    out.mkdir(parents=True, exist_ok=True)
    if args.stage == "fetch-radar":
        fetch_radar(args.pair, grid, args.gdal_bin)
    if args.stage in ("predict", "all"):
        predictions = predict(args.pair, out, grid, tags)
        print(f"Radar-only predictions frozen: {out / 'radar_predictions.json'}")
    if args.stage in ("extract", "all"):
        sources = optical_sources(args.pair, args.optical_manifest)
        optical = extract(out, grid, sources, args.gdal_bin)
        geotiff(out / "optical.tif", optical[2], tags)
        print("Optical usable on both dates:", f"{(optical[2] < GAP).mean():.1%}")
    if args.stage == "score":
        predictions = verified_predictions(args.pair, out, grid)
        provenance = load(out / "optical_provenance.json")
        optical = extract(out, grid, provenance["sources"], args.gdal_bin)
    if args.stage in ("score", "all"):
        report(args.pair, args.output, out, grid, tags, optical, predictions)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        sys.exit(f"Roseires pipeline: {exc}")
