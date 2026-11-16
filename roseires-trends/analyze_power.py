#!/usr/bin/env python3
"""Analyze the verified POWER monthly point response for the Roseires grid cell."""

import argparse
from calendar import monthrange
import hashlib
from itertools import combinations
import json
from math import erfc, sqrt
from pathlib import Path
from statistics import NormalDist

import numpy as np


HERE = Path(__file__).resolve().parent
PARAMETER = "PRECTOTCORR"
START, END = 1981, 2024
REQUEST = (
    "https://power.larc.nasa.gov/api/temporal/monthly/point?parameters=PRECTOTCORR"
    "&community=AG&longitude=34.4673&latitude=11.7285&start=1981&end=2024&format=JSON"
)
PERIODS = ((START, END), (START, 2002), (2003, END))
NORMAL = NormalDist()


def monthly_totals(source):
    header = source["header"]
    longitude, latitude, _ = source["geometry"]["coordinates"]
    if (
        source["type"] != "Feature"
        or source["geometry"]["type"] != "Point"
        or abs(longitude - 34.4673) > 0.001
        or abs(latitude - 11.7285) > 0.001
        or header["sources"] != ["MERRA2"]
        or (header["start"], header["end"]) != ("19810101", "20241231")
        or source["parameters"][PARAMETER]["units"] != "mm/day"
    ):
        raise ValueError("Expected the 1981–2024 NASA POWER MERRA-2 Roseires point response.")

    values = source["properties"]["parameter"][PARAMETER]
    days_and_values = []
    for year in range(START, END + 1):
        for month in range(1, 13):
            key = f"{year}{month:02d}"
            value = values.get(key, header["fill_value"])
            if not np.isfinite(value) or value == header["fill_value"] or value < 0:
                raise ValueError(f"Missing or invalid monthly value for {key}. Annual totals require all 12 months.")
            days = monthrange(year, month)[1]
            days_and_values.append({
                "month": f"{year}-{month:02d}",
                "source_mm_day": value,
                "days": days,
                "total_mm": round(value * days, 2),
            })
    return days_and_values


def linear_fit(years, totals, lags, *, details=False):
    """OLS with Bartlett Newey–West covariance and a two-sided normal approximation."""
    n = len(years)
    if not 0 <= lags < n - 2 or not np.all(np.diff(years) == 1):
        raise ValueError("HAC requires consecutive annual totals and enough observations for the lag.")
    x = np.column_stack((np.ones(n), years - years[0]))
    coefficients = np.linalg.lstsq(x, totals, rcond=None)[0]
    residuals = totals - x @ coefficients
    covariance = hac_covariance(x, residuals, lags)
    se = float(np.sqrt(max(0, covariance[1, 1])))
    intercept, slope = map(float, coefficients)
    if se <= np.finfo(float).eps:
        raise ValueError("The record has insufficient residual variation to estimate uncertainty.")
    half_width = NORMAL.inv_cdf(0.975) * se
    fit = {
        "start": int(years[0]),
        "end": int(years[-1]),
        "n_years": n,
        "slope_mm_per_year": slope,
        "fitted_start_mm": intercept,
        "fitted_end_mm": intercept + (n - 1) * slope,
        "se_mm_per_year": se,
        "ci95_mm_per_year": [slope - half_width, slope + half_width],
        "p_two_sided": erfc(abs(slope / se) / sqrt(2)),
        "hac_lags_years": lags,
    }
    if details:
        rss = residuals @ residuals
        i, j = np.triu_indices(n, k=1)
        fit.update({
            "fit_covariance": [float(covariance[0, 0]), float(covariance[0, 1]), float(covariance[1, 1])],
            "residual_sd_mm": float(np.sqrt(rss / (n - 2))),
            "residual_acf1": float(residuals[1:] @ residuals[:-1] / rss),
            "theil_sen_mm_per_year": float(np.median((totals[j] - totals[i]) / (years[j] - years[i]))),
        })
    return fit, residuals


def hac_covariance(design, residuals, lags, positions=None):
    """Bartlett Newey–West covariance on the supplied time grid."""
    n, parameters = design.shape
    scores = design * residuals[:, None]
    if positions is not None:
        # Missing observations contribute no score. The lag still counts calendar periods.
        offsets = positions - positions[0]
        calendar_scores = np.zeros((offsets[-1] + 1, parameters))
        calendar_scores[offsets] = scores
        scores = calendar_scores
    covariance_sum = scores.T @ scores
    for lag in range(1, lags + 1):
        cross_product = scores[lag:].T @ scores[:-lag]
        covariance_sum += (1 - lag / (lags + 1)) * (cross_product + cross_product.T)
    bread = np.linalg.inv(design.T @ design)
    return bread @ covariance_sum @ bread * n / (n - parameters)


def screen_level_shifts(years, totals, line_residuals):
    """Compare exploratory step-plus-trend fits, allowing at least eight years per segment."""
    segment_min = 8
    baseline_rss = float(line_residuals @ line_residuals)
    x = np.column_stack((np.ones(len(years)), years - years[0]))
    candidates = range(segment_min, len(years) - segment_min + 1)
    screens = []
    for n_breaks in (1, 2):
        best = None
        for indices in combinations(candidates, n_breaks):
            if any(b - a < segment_min for a, b in zip(indices, indices[1:])):
                continue
            design = np.column_stack((x, *(years >= years[i] for i in indices)))
            residuals = totals - design @ np.linalg.lstsq(design, totals, rcond=None)[0]
            rss = float(residuals @ residuals)
            if best is None or rss < best[0]:
                best = rss, indices
        if best is not None:
            rss, indices = best
            # Each searched breakpoint adds one level coefficient and one breakpoint parameter.
            delta = len(years) * np.log(rss / baseline_rss) + 2 * n_breaks * np.log(len(years))
            screens.append({"first_years_after_shift": [int(years[i]) for i in indices],
                            "bic_minus_linear": float(delta)})
    return screens


def analyze(source_path):
    source_bytes = source_path.read_bytes()
    source = json.loads(source_bytes)
    monthly = monthly_totals(source)
    years = np.arange(START, END + 1)
    calendar_months = np.array([row["total_mm"] for row in monthly]).reshape(-1, 12)
    totals = calendar_months.sum(axis=1).round(2)
    primary, residuals = linear_fit(years, totals, lags=3)
    windows = [{"label": "Full record", **primary}]
    for start, end in PERIODS[1:]:
        keep = (years >= start) & (years <= end)
        fit, _ = linear_fit(years[keep], totals[keep], lags=3)
        windows.append({"label": "Exploratory half-record", **fit})

    return {
        "variable": "Corrected precipitation",
        "region": "Grid cell near Roseires, Sudan",
        "source": {
            "product": "NASA POWER / MERRA-2",
            "parameter": PARAMETER,
            "api_version": source["header"]["api"]["version"],
            "time_standard": source["header"]["time_standard"],
            "fill_value": source["header"]["fill_value"],
            "requested_point": {"latitude": 11.7285, "longitude": 34.4673},
            "response_coordinates": source["geometry"]["coordinates"],
            "native_grid_degrees": {"latitude": 0.5, "longitude": 0.625},
            "retrieved_on": "2026-11-15",
            "request": REQUEST,
            "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
        },
        "coverage": {"complete_months": len(monthly), "missing_months": 0,
                     "filled_by_infrasar": 0, "annual_api_summaries_excluded": len(years)},
        "method": {
            "aggregation": "Monthly mean mm/day multiplied by calendar days, then summed over 12 months.",
            "model": "OLS linear slope of complete annual precipitation totals with an intercept.",
            "inference": "Newey–West HAC, Bartlett weights, n/(n−2) correction, two-sided normal approximation.",
            "interval_level": 0.95,
            "primary_hac_lag_years": 3,
            "sensitivity_hac_lag_years": [1, 5],
        },
        "diagnostics": {
            "mean_monthly_total_mm": calendar_months.mean(axis=0).round(2).tolist(),
            "june_september_fraction": float(calendar_months[:, 5:9].sum() / calendar_months.sum()),
            "annual_residual_acf_1_to_6": [float(residuals[lag:] @ residuals[:-lag] / (residuals @ residuals))
                                          for lag in range(1, 7)],
            "level_shift_screen": screen_level_shifts(years, totals, residuals),
            "hac_sensitivity": [linear_fit(years, totals, lag)[0] for lag in (1, 5)],
        },
        "monthly": monthly,
        "annual": [{"year": int(year), "total_mm": float(total)} for year, total in zip(years, totals)],
        "windows": windows,
    }



def explorer_windows(investigation):
    """Precompute the same fit for every supported interval and round for portable HTML."""
    years = np.array([row["year"] for row in investigation["annual"]])
    totals = np.array([row["total_mm"] for row in investigation["annual"]])
    min_years = 10
    fits = {}
    for start in range(len(years) - min_years + 1):
        for stop in range(start + min_years, len(years) + 1):
            fit, _ = linear_fit(years[start:stop], totals[start:stop], lags=3, details=True)
            key = f"{fit['start']}-{fit['end']}"
            fits[key] = {k: (round(v, 7) if isinstance(v, float) else
                             [round(item, 7) for item in v] if isinstance(v, list) else v)
                         for k, v in fit.items()}
    return {"min_years": min_years, "windows": fits}


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--source", type=Path, default=HERE / "nasa-power-roseires.json")
    cli.add_argument("--output", type=Path, default=HERE / "power-analysis.json")
    args = cli.parse_args()
    result = analyze(args.source)
    args.output.write_text(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2) + "\n")
    fit = result["windows"][0]
    low, high = fit["ci95_mm_per_year"]
    print(f"{fit['start']}–{fit['end']}, n={fit['n_years']}, "
          f"slope {fit['slope_mm_per_year']:+.2f} mm/year, "
          f"95% CI [{low:.2f}, {high:.2f}], p={fit['p_two_sided']:.3f}")


if __name__ == "__main__":
    main()
