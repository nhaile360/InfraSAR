#!/usr/bin/env python3
"""Reproduce the Roseires reservoir surface-area results from the derived MODIS CSV."""

import argparse
import csv
from datetime import date
import hashlib
import io
import json
from math import erfc, isfinite, sqrt
from pathlib import Path

import numpy as np

from analyze_power import NORMAL, hac_covariance


HERE = Path(__file__).resolve().parent
CSV_PATH = HERE / "roseires_modis_monthly_surface_area.csv"
BREAK_YEAR = 2013
MODEL_MONTHS = (1, 2, 3, 4, 5, 10, 11, 12)
HAC_LAGS = 12


def month_number(month):
    parsed = date.fromisoformat(month + "-01")
    return parsed.year * 12 + parsed.month - 1


def read_months(source):
    rows = {}
    for row in csv.DictReader(io.StringIO(source.decode("utf-8-sig"))):
        month, status = row["month_utc"], row["status"]
        index = month_number(month)
        if (row["lake_id"], row["grand_id"]) != ("111", "4483") or index in rows:
            raise ValueError(f"Expected one Roseires record for {month}.")
        if status not in ("published", "fill_value", "no_granule"):
            raise ValueError(f"Unrecognized MODIS status for {month}: {status}")
        area = float(row["lake_area_km2"]) if status == "published" else None
        if area is not None and (not isfinite(area) or area < 0):
            raise ValueError(f"Invalid published reservoir area for {month}.")
        rows[index] = {"month": month, "area_km2": area, "status": status}
    if not rows:
        raise ValueError("The MODIS CSV contains no months.")
    return [
        rows.get(index, {"month": date(index // 12, index % 12 + 1, 1).isoformat()[:7],
                         "area_km2": None, "status": "no_granule"})
        for index in range(min(rows), max(rows) + 1)
    ]


def coefficient(design, area, positions, column):
    fitted, _, rank, _ = np.linalg.lstsq(design, area, rcond=None)
    if rank != design.shape[1] or len(area) <= rank or positions[-1] - positions[0] < HAC_LAGS:
        raise ValueError("The MODIS record has insufficient observations for this seasonal model.")
    residuals = area - design @ fitted
    covariance = hac_covariance(design, residuals, HAC_LAGS, positions)
    se = float(np.sqrt(max(0, covariance[column, column])))
    if se <= np.finfo(float).eps:
        raise ValueError("The MODIS record has insufficient variation to estimate uncertainty.")
    value = float(fitted[column])
    half_width = NORMAL.inv_cdf(0.975) * se
    return {
        "estimate": round(value, 8),
        "ci95": [round(value - half_width, 8), round(value + half_width, 8)],
        "p_two_sided": round(erfc(abs(value / se) / sqrt(2)), 12),
        "observations": len(area),
    }


def analyze(csv_path=CSV_PATH):
    source = csv_path.read_bytes()
    monthly = read_months(source)
    model_rows = [row for row in monthly if row["area_km2"] is not None
                  and int(row["month"][5:]) in MODEL_MONTHS]
    calendar = np.array([month_number(row["month"]) for row in model_rows], dtype=int)
    years = calendar // 12 - BREAK_YEAR
    post = years >= 0
    if not post.any() or post.all():
        raise ValueError("The MODIS fit needs published observations on both sides of 2013.")
    area = np.array([row["area_km2"] for row in model_rows])
    seasons = [calendar % 12 + 1 == month for month in MODEL_MONTHS[1:]]
    interrupted = np.column_stack((np.ones(len(area)), years, post, years * post, *seasons))
    post_design = np.column_stack((np.ones(post.sum()), years[post], *(column[post] for column in seasons)))
    return {
        "source": {"product": "NASA Terra MODIS MOD28C3.061", "lake_id": 111, "grand_id": 4483,
                   "sha256": hashlib.sha256(source).hexdigest()},
        "break_month": f"{BREAK_YEAR}-01",
        "model_months": list(MODEL_MONTHS),
        "hac_lags_months": HAC_LAGS,
        "coverage": {status: sum(row["status"] == status for row in monthly)
                     for status in ("published", "fill_value", "no_granule")},
        "monthly": monthly,
        "shift_km2": coefficient(interrupted, area, calendar, 2),
        "post_slope_km2_per_year": coefficient(post_design, area[post], calendar[post], 1),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", type=Path, default=CSV_PATH)
    args = parser.parse_args()
    print(json.dumps(analyze(args.csv), indent=2, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
