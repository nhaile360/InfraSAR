#!/usr/bin/env python3
"""Verify and crop individual catalogued Frequency A HH observations."""

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
from tempfile import TemporaryDirectory
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import pipeline as roseires
from catalog_nisar import CATALOG
from crop_roseires import ARCHIVE, load_token


OUTPUT = roseires.HERE / "outputs" / "timeline"
BAND = "//science/LSAR/GCOV/grids/frequencyA/HHHH"
SCENE_ID = re.compile(r"NISAR_L2_PR_GCOV_[A-Z0-9_]+")
HDF5_SIGNATURE = b"\x89HDF\r\n\x1a\n"


def gdal(tool, binary, env, *args):
    program = str(binary / tool) if binary else shutil.which(tool)
    if not program:
        raise ValueError(f"Install GDAL with the HDF5 driver or supply --gdal-bin ({tool}).")
    result = subprocess.run([program, *map(str, args)], env=env, capture_output=True, text=True, check=False)
    if result.returncode:
        message = result.stderr.strip().splitlines()[-1:] or ["no diagnostic"]
        raise ValueError(f"{tool} returned {result.returncode}: {message[0]}")
    return result.stdout


def remote_access(url, token):
    """Probe only the HDF5 signature and keep the bearer on the original request."""
    request = Request(url, headers={"Range": "bytes=0-7"})
    request.add_unredirected_header("Authorization", "Bearer " + token)
    try:
        with urlopen(request, timeout=12) as response:
            if urlsplit(response.url).hostname == "urs.earthdata.nasa.gov":
                return False, "ASF access redirected to Earthdata Login."
            readable = response.status == 206 and response.read(8) == HDF5_SIGNATURE
            if readable:
                return True, "ASF returned the HDF5 signature over HTTP 206."
            return False, f"ASF returned HTTP {response.status} without the expected HDF5 byte range."
    except HTTPError as error:
        if urlsplit(error.url).hostname == "urs.earthdata.nasa.gov":
            return False, f"ASF access redirected to Earthdata Login (HTTP {error.code})."
        return False, f"ASF data request returned HTTP {error.code}."
    except (URLError, OSError) as error:
        reason = getattr(error, "reason", error)
        if isinstance(reason, socket.gaierror):
            return False, "DNS lookup failed while connecting to NASA/ASF."
        return False, f"NASA/ASF connection failed ({type(reason).__name__})."


def dataset_info(dataset, row, args, env):
    try:
        return json.loads(gdal("gdalinfo", args.gdal_bin, env, "-json", dataset))
    except ValueError as error:
        if args.source_dir is not None:
            raise
        readable, report = remote_access(row["source_url"], env["GDAL_HTTP_BEARER"])
        if readable:
            # Some hosts serve ranges but reject the initial HEAD request.
            env["CPL_VSIL_CURL_USE_HEAD"] = "NO"
            try:
                return json.loads(gdal("gdalinfo", args.gdal_bin, env, "-json", dataset))
            except ValueError as retry:
                raise ValueError(f"{report} GDAL could not open the HH subdataset even with HEAD disabled. {retry}") from retry
        raise ValueError(f"{report} {error}") from error


def native_window(info, grid):
    """Map study-cell centers to their containing native cells, at unchanged 20 m spacing."""
    transform = info["geoTransform"]
    wkt = info["coordinateSystem"]["wkt"]
    band, = info["bands"]
    if (transform[1:3] != [20, 0] or transform[4:] != [0, -20] or band["type"] != "Float32"
            or not re.search(r'(?:ID|AUTHORITY)\["EPSG",\s*"?32636"?\]\s*\]\s*$', wkt)):
        raise ValueError("Expected native north-up Float32 Frequency A HH on the 20 m UTM 36N grid.")
    target_x, target_y = grid["west"] + 10, grid["north"] - 10
    x = math.floor((target_x - transform[0]) / 20)
    y = math.floor((transform[3] - target_y) / 20)
    width, height = grid["width"], grid["height"]
    if min(x, y) < 0 or x + width > info["size"][0] or y + height > info["size"][1]:
        raise ValueError("The native raster extent does not contain the full study grid.")
    offset = [transform[0] + x * 20 - grid["west"], transform[3] - y * 20 - grid["north"]]
    return (x, y, width, height), offset


def source_file(row, directory):
    identity = row["id"]
    if not SCENE_ID.fullmatch(identity):
        raise ValueError("Unexpected NISAR scene identifier.")
    name = identity + ".h5"
    expected = f"{ARCHIVE}/{identity}/{name}"
    if row["source_url"] != expected:
        raise ValueError("The granule link does not match the expected NASA ASF archive URL.")
    if directory is None:
        return f"/vsicurl/{expected}", False
    source = directory / name
    if source.stat().st_size != row["source_size_bytes"]:
        raise ValueError(f"Source size differs from CMR: {name}")
    checksum = row["source_checksum"]
    with source.open("rb") as handle:
        digest = hashlib.file_digest(handle, checksum["Algorithm"].lower())
    if digest.hexdigest().lower() != checksum["Value"].lower():
        raise ValueError(f"Source checksum differs from CMR: {name}")
    return str(source.resolve()), True


def extract(row, grid, inlet_mask, args, env):
    source, verified_source = source_file(row, args.source_dir)
    if '"' in source:
        raise ValueError("Use a source directory without quotes.")
    dataset = f'HDF5:"{source}":{BAND}'
    info = dataset_info(dataset, row, args, env)
    window, offset = native_window(info, grid)
    west, south, east, north = roseires.bounds(grid)
    name = f"roseires_{row['datetime'][:10]}_HHHH.tif"
    target = args.output_dir / name
    with TemporaryDirectory(dir=args.output_dir) as directory:
        crop = Path(directory) / name
        # Select original native samples. Assign the reference-grid cell edges after selection.
        gdal("gdal_translate", args.gdal_bin, env, "-q", "-of", "GTiff", "-srcwin", *window,
             "-a_ullr", west, north, east, south, "-co", "COMPRESS=DEFLATE", "-co", "TILED=YES", dataset, crop)
        raw, actual, _ = roseires.raster(crop)
        roseires.require_grid(actual, grid, crop)
        if raw.dtype != roseires.np.dtype("float32"):
            raise ValueError("The extracted samples are no longer Float32.")
        declared = info["bands"][0].get("noDataValue")
        fill = float(declared) if declared is not None else None
        valid = roseires.np.isfinite(raw) & (raw > 0)
        if fill is not None and math.isfinite(fill):
            valid &= raw != fill
        inlet_valid = int(valid[inlet_mask].sum())
        if inlet_valid == 0:
            raise ValueError("The acquisition has no valid HH samples inside the fixed inlet outline.")
        digest = roseires.digest(crop)
        crop.replace(target)
    return {"id": row["id"], "datetime": row["datetime"], "maturity": row["maturity"],
            "version": row["version"], "release": row["release"], "mode": row["mode"], "grid": grid,
            "cmr_concept_id": row["concept_id"], "source_url": row["source_url"], "band": BAND,
            "source_checksum_catalog": row["source_checksum"], "source_checksum_verified": verified_source,
            "source_nodata": declared if fill is None or math.isfinite(fill) else str(declared),
            "source_window": window, "native_center_offset_m": offset,
            "valid_cells": int(valid.sum()), "inlet_valid_cells": inlet_valid,
            "raster": name, "sha256": digest}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dates", nargs="+", help="UTC dates from the catalog, e.g. 2026-08-17")
    parser.add_argument("--catalog", type=Path, default=CATALOG)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT)
    parser.add_argument("--source-dir", type=Path, help="Directory with original downloaded HDF5 files")
    parser.add_argument("--env-file", type=Path, help="File containing EARTHDATA_TOKEN for remote access")
    parser.add_argument("--gdal-bin", type=Path)
    args = parser.parse_args()
    catalog = roseires.load(args.catalog)
    rows = {row["datetime"][:10]: row for row in catalog["granules"]
            if row["status"] == "awaiting native HH verification"}
    unknown = set(args.dates) - rows.keys()
    if unknown or len(set(args.dates)) != len(args.dates):
        parser.error("Give distinct catalog-eligible non-pilot dates. Unknown: " + ", ".join(sorted(unknown)))
    env = dict(os.environ, GDAL_HTTP_NETRC="NO", CPL_CURL_VERBOSE="NO", CPL_DEBUG="OFF",
               GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR", GDAL_HTTP_TIMEOUT="45",
               GDAL_HTTP_MAX_RETRY="2", CPL_VSIL_CURL_AUTHORIZATION_HEADER_ALLOWED_IF_REDIRECT="NO")
    if args.source_dir is None:
        env_file = args.env_file or next((p for p in (roseires.ROOT / ".env", roseires.ROOT.parent / ".env")
                                          if p.is_file()), roseires.ROOT / ".env")
        env.update(GDAL_HTTP_AUTH="BEARER", GDAL_HTTP_BEARER=load_token(env_file))
    _, grid, _ = roseires.raster(roseires.radar_paths("pilot")[0])
    mask, mask_grid, _ = roseires.raster(roseires.HERE / "outputs/pilot/inlet_patch_mask.tif")
    roseires.require_grid(mask_grid, grid, "inlet mask")
    if mask.sum() != 108:
        raise ValueError("Expected the fixed 108-cell inlet mask.")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    manifest = args.output_dir / "manifest.json"
    prior = {r["datetime"][:10]: r for r in roseires.load(manifest)} if manifest.is_file() else {}
    for date in args.dates:
        row = extract(rows[date], grid, mask == 1, args, env)
        prior[date] = row
        roseires.dump(manifest, [prior[d] for d in sorted(prior)])
        print(f"{date}: {row['valid_cells']} valid HH cells, {row['inlet_valid_cells']}/108 at the inlet")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, KeyError) as error:
        sys.exit(str(error))
