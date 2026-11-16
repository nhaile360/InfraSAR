#!/usr/bin/env python3
"""Verify the locked scientific inputs and recompute the published Roseires claims."""

import base64
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sys
import zlib

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / folder) for folder in ("roseires-visuals", "roseires-trends", "roseires-pipeline")]
from build_infrasar import processed_bundle
import pipeline as roseires
from analyze_power import analyze as rainfall
from analyze_modis import analyze as area

MANIFEST = ROOT / "docs/scientific-inputs.sha256"
PILOT = roseires.HERE / "outputs/pilot"


def verify(condition, message):
    if not condition:
        raise ValueError(message)


def check_hashes():
    entries = MANIFEST.read_text().splitlines()
    for line in entries:
        expected, name = line.split("  ", 1)
        actual = hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        verify(actual == expected, f"Scientific input changed: {name}")
    return len(entries)


def height_at(rows, time):
    for left, right in zip(rows, rows[1:]):
        start = datetime.fromisoformat(left["datetime"])
        stop = datetime.fromisoformat(right["datetime"])
        if start <= time <= stop:
            return left["meters"] + (right["meters"] - left["meters"]) * ((time - start) / (stop - start))
    raise ValueError(f"No bracketing DAHITI observations for {time}")


def main():
    np = roseires.np
    count = check_hashes()
    mask, grid, _ = roseires.raster(PILOT / "inlet_patch_mask.tif")
    inlet = mask == 1
    verify(int(inlet.sum()) == 108, "Inlet mask must contain 108 cells.")
    hh, fixed, local, lock = roseires.verified_predictions("pilot", PILOT, grid)
    median = float(np.median((hh[1] - hh[0])[inlet]))
    verify(round(median, 2) == -4.32, "Unexpected pilot HH change.")
    bundle = processed_bundle(PILOT / "comparator.html", grid)
    provenance = roseires.load(PILOT / "optical_provenance.json")
    verify(bundle["optical_sources"] == provenance["sources"], "Optical source identifiers differ.")
    scl = []
    for phase, code in (("before", 5), ("after", 6)):
        packed = bundle["arrays"][f"scl_{phase}"]
        values = np.frombuffer(zlib.decompress(base64.b64decode(packed["payload"])), dtype="u1").reshape(inlet.shape)
        verify(bool(np.all(values[inlet] == code)), f"Unexpected {phase} inlet optical classes.")
        scl.append(values)
    optical = roseires.change(*(roseires.scl_state(values) for values in scl))
    metrics = {"fixed": roseires.scores(fixed, optical), "local": roseires.scores(local, optical)}
    verify(metrics == bundle["metrics"] == roseires.load(PILOT / "scores.json")["metrics"], "Scores differ from the frozen pilot.")
    timeline = list(roseires.timeline_planes(roseires.HERE / "outputs/timeline/manifest.json", grid, inlet))
    verify(len(timeline) == 8 and all(r["valid_cells"] == 317106 and r["inlet_valid_cells"] == 108
                                      for r, _ in timeline), "Unexpected timeline coverage.")
    heights = roseires.load(ROOT / "roseires-visuals/src/dahiti-216.json")
    before, after = [height_at(heights, datetime.fromisoformat(r["datetime"])) for r in lock["radar"]]
    verify(round(after - before, 2) == 1.15, "Unexpected DAHITI rise.")
    rain = rainfall(ROOT / "roseires-trends/nasa-power-roseires.json")
    frozen = roseires.load(ROOT / "roseires-trends/power-analysis.json")
    verify(rain["annual"] == frozen["annual"] and rain["monthly"] == frozen["monthly"], "Rainfall totals differ.")
    for fresh, saved in zip(rain["windows"], frozen["windows"], strict=True):
        for key in ("slope_mm_per_year", "ci95_mm_per_year", "p_two_sided"):
            verify(np.allclose(fresh[key], saved[key], rtol=0, atol=1e-8), f"Rainfall fit differs: {key}")
    reservoir = area()
    verify(reservoir["coverage"] == {"published": 235, "fill_value": 77, "no_granule": 5}
           and round(reservoir["shift_km2"]["estimate"], 2) == 164.07
           and round(reservoir["post_slope_km2_per_year"]["estimate"], 2) == -1.26, "MODIS coverage or fit differs.")
    print(json.dumps({"verified_files": count, "inlet_cells": int(inlet.sum()), "inlet_median_db": median,
                      "height_difference_m": after - before, "whole_crop_scores": metrics,
                      "nisar_acquisitions": len(timeline) + len(hh), "rainfall": rain["windows"][0],
                      "modis": {"coverage": reservoir["coverage"], "shift": reservoir["shift_km2"],
                                "post_slope": reservoir["post_slope_km2_per_year"]}}, indent=2))


if __name__ == "__main__":
    main()
