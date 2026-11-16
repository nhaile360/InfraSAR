#!/usr/bin/env python3
"""Summarize paired HH changes over the fixed Roseires inlet cells."""

import argparse
from datetime import datetime
import json

import pipeline as roseires


def summarize():
    pilot = roseires.HERE / "outputs" / "pilot"
    mask, grid, _ = roseires.raster(pilot / "inlet_patch_mask.tif")
    mask = mask == 1
    if mask.sum() != 108:
        raise ValueError("Expected the original 108-cell pilot inlet mask.")
    planes, _, _, lock = roseires.verified_predictions("pilot", pilot, grid)
    baseline = [({**record, "mode": "DHDH"}, plane) for record, plane in zip(lock["radar"], planes)]
    manifest = roseires.HERE / "outputs" / "timeline" / "manifest.json"
    series = sorted([*baseline, *roseires.timeline_planes(manifest, grid, mask)],
                    key=lambda item: datetime.fromisoformat(item[0]["datetime"]))
    previous = {}
    results = []
    for record, plane in series:
        date, mode = record["datetime"][:10], record["mode"]
        inlet = plane[mask]
        result = {
            "date": date, "mode": mode, "cells": int(roseires.np.isfinite(inlet).sum()),
            "median_hh_db": round(float(roseires.np.nanmedian(inlet)), 3),
        }
        if mode in previous:
            prior_date, prior_inlet = previous[mode]
            delta = inlet - prior_inlet
            q25, median, q75 = roseires.np.nanquantile(delta, [.25, .5, .75])
            result["change_from"] = prior_date
            result["paired_cells"] = int(roseires.np.isfinite(delta).sum())
            result["paired_change_db"] = [round(float(value), 3) for value in (q25, median, q75)]
        results.append(result)
        previous[mode] = (date, inlet)
    delta = (planes[1] - planes[0])[mask]
    return {"observations": results, "pilot_median_cellwise_change_db": round(float(roseires.np.nanmedian(delta)), 3)}


def main():
    argparse.ArgumentParser(description=__doc__).parse_args()
    print(json.dumps(summarize(), indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
