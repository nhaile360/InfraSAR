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


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--pilot", type=Path, help="Scored pilot comparator.html")
    cli.add_argument("--observations", type=Path, action="append", default=[], help="Other scored comparator.html files")
    cli.add_argument("--august-scl", type=Path, help="Original aligned 36PXT classification")
    cli.add_argument("--october-scl", type=Path, help="Original aligned 36PXT classification")
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

    patch = None
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
    payload = {"grid": grid, "bundles": [pilot, *(processed_bundle(path, grid) for path in args.observations)],
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
