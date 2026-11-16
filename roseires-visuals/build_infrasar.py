#!/usr/bin/env python3
"""Build the portable InfraSAR explorer from the frozen radar and processed optical layers."""

import argparse
import json
from pathlib import Path
import re
import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "roseires-pipeline"))
sys.path.insert(0, str(HERE.parent / "roseires-trends"))
import pipeline as roseires
from analyze_modis import CSV_PATH as MODIS_CSV, analyze as analyze_modis
from catalog_nisar import CATALOG


def processed_bundle(path, grid):
    text = path.read_text()
    match = re.search(r'<script\s+type="application/json"\s+id="data">([\s\S]*?)</script>', text)
    if not match:
        raise ValueError(f"No Roseires pipeline data in {path}")
    bundle = json.loads(match[1])
    roseires.require_grid(bundle["grid"], grid, path)
    return bundle


def aligned_byte_raster(path, grid):
    np = roseires.np
    data, original, _ = roseires.raster(path)
    offsets = [(original["west"] - grid["west"]) / 20, (grid["north"] - original["north"]) / 20]
    col, row = (round(value) for value in offsets)
    if (any(abs(value - round(value)) > 1e-5 for value in offsets)
            or min(row, col) < 0 or row + data.shape[0] > grid["height"] or col + data.shape[1] > grid["width"]):
        raise ValueError(f"{path} is outside or misaligned with the Roseires grid")
    aligned = np.full((grid["height"], grid["width"]), roseires.OUTSIDE_TILE, dtype=np.uint8)
    aligned[row:row + data.shape[0], col:col + data.shape[1]] = data
    return aligned


def radar_observations(manifest, grid, patch):
    if not manifest.is_file():
        return []
    catalog = {row["id"]: row for row in roseires.load(CATALOG)["granules"]
               if row["status"] == "awaiting native HH verification"}
    records = []
    seen = set()
    for record in roseires.load(manifest):
        source = catalog[record["id"]]
        for field in ("datetime", "maturity", "version", "release", "mode"):
            if record[field] != source[field]:
                raise ValueError(f"Observation metadata differs from CMR: {record['id']}")
        if record["datetime"] in seen:
            raise ValueError(f"Duplicate radar acquisition: {record['datetime']}")
        seen.add(record["datetime"])
        filename = f"roseires_{record['datetime'][:10]}_HHHH.tif"
        path = manifest.parent / filename
        if record["raster"] != filename or roseires.digest(path) != record["sha256"]:
            raise ValueError(f"Radar crop does not match its manifest: {path}")
        roseires.require_grid(record["grid"], grid, manifest)
        raw, actual, _ = roseires.raster(path)
        roseires.require_grid(actual, grid, path)
        if raw.dtype != roseires.np.dtype("float32") or record["inlet_valid_cells"] < 1:
            raise ValueError(f"Radar crop has an unsupported numeric type or no inlet observations: {path}")
        raw_db = roseires.db(raw)
        if record["source_nodata"] is not None:
            raw_db[raw == float(record["source_nodata"])] = roseires.np.nan
        valid = roseires.np.isfinite(raw_db)
        if int(valid.sum()) != record["valid_cells"] or (patch is not None
                and int(valid[patch].sum()) != record["inlet_valid_cells"]):
            raise ValueError(f"Radar crop coverage differs from manifest: {path}")
        records.append({**record, "hh_db": roseires.encode(raw_db)})
    return records


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--pilot", type=Path, help="Scored pilot comparator.html")
    cli.add_argument("--observations", type=Path, action="append", default=[], help="Other scored comparator.html files")
    cli.add_argument("--august-scl", type=Path, help="Original aligned 36PXT classification")
    cli.add_argument("--october-scl", type=Path, help="Original aligned 36PXT classification")
    cli.add_argument("--radar-manifest", type=Path, default=roseires.HERE / "outputs/timeline/manifest.json")
    cli.add_argument("--radar-json-dir", type=Path, help="Export individual verified observations for local browser import")
    cli.add_argument("--patch", type=Path, help="Original aligned outlined patch mask")
    cli.add_argument("--trend", type=Path,
                     default=HERE.parent / "roseires-trends" / "power-analysis.json",
                     help="Verified precipitation analysis from analyze_power.py")
    cli.add_argument("--modis-csv", type=Path, default=MODIS_CSV,
                     help="Derived MODIS monthly surface-area CSV")
    cli.add_argument("--output", type=Path, default=HERE / "roseires-shoreline-comparator.html")
    args = cli.parse_args()

    np = roseires.np
    _, grid, _ = roseires.raster(roseires.radar_paths("pilot")[0])
    raw, fixed, local, lock = roseires.verified_predictions("pilot", roseires.HERE / "outputs" / "pilot", grid)
    pilot = {"pair": "pilot", "grid": grid, "radar": lock, "optical_sources": {}, "tile_coverage": {},
             "arrays": {name: roseires.encode(array) for name, array in
                        (("hh_before", raw[0]), ("hh_after", raw[1]), ("fixed", fixed), ("local", local))}}
    if args.pilot:
        pilot = processed_bundle(args.pilot, grid)
        if pilot["pair"] != "pilot":
            raise ValueError("--pilot needs the scored August 29 / October 16 pilot")
    elif args.august_scl and args.october_scl:
        rows = [aligned_byte_raster(path, grid) for path in (args.august_scl, args.october_scl)]
        states = [roseires.scl_state(row) for row in rows]
        for phase, row, state in zip(("before", "after"), rows, states):
            pilot["arrays"][f"scl_{phase}"] = roseires.encode(row)
            pilot["arrays"][f"opt_{phase}"] = roseires.encode(state)
        for radar_date, optical_date in roseires.OPTICAL_PILOT.items():
            scene_id = f"S2C_36PXT_{optical_date.replace('-', '')}_0_L2A"
            pilot["optical_sources"][radar_date] = {"36PXT": {"id": scene_id, "date": optical_date, "tile": "36PXT"}}

    patch = mask = None
    if args.patch:
        mask = aligned_byte_raster(args.patch, grid) == 1
        deltas = (raw[1] - raw[0])[mask]
        if mask.sum() != 108 or not np.all(np.isfinite(deltas)) or abs(np.median(deltas) + 4.32) > .04:
            raise ValueError("The mask does not reproduce the verified 108-cell inlet study")
        patch = roseires.encode(mask)

    src = HERE / "src"
    reservoir = json.loads((src / "roseires-reservoir.json").read_text())
    if reservoir["epsg"] != grid["epsg"]:
        raise ValueError("Reservoir geometry must use the study grid projection")
    observations = radar_observations(args.radar_manifest, grid, mask)
    if args.radar_json_dir:
        args.radar_json_dir.mkdir(parents=True, exist_ok=True)
        for record in observations:
            roseires.dump(args.radar_json_dir / (record["id"] + ".json"), record)
    payload = {"grid": grid, "bundles": [pilot, *(processed_bundle(path, grid) for path in args.observations)],
               "radar_observations": observations,
               "patch": patch, "heights": json.loads((src / "dahiti-216.json").read_text()),
               "reservoir": reservoir, "trend": json.loads(args.trend.read_text()),
               "modis": analyze_modis(args.modis_csv)}
    replacements = {"/* INFRASAR_STYLE */": (src / "atlas.css").read_text(),
                    "/* INFRASAR_SCRIPT */": "\n".join(
                        (src / name).read_text() for name in ("data.js", "tiff.js", "atlas.js", "trend.js")
                    ),
                    "__INFRASAR_DATA__": json.dumps(payload, separators=(",", ":")).replace("<", "\\u003c")}
    html = (src / "index.html").read_text()
    for marker, content in replacements.items():
        html = html.replace(marker, content)
    args.output.write_text(html)
    print(f"Built {args.output.resolve()}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError) as error:
        sys.exit(str(error))
