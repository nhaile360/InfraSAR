import json
from pathlib import Path
import unittest

import numpy as np

from analyze_power import analyze, linear_fit, monthly_totals


HERE = Path(__file__).resolve().parent
SOURCE = HERE / "nasa-power-roseires.json"


class PowerTrendTest(unittest.TestCase):
    def test_preserves_monthly_source_and_weights_leap_day(self):
        source = json.loads(SOURCE.read_text())
        rows = monthly_totals(source)
        self.assertEqual(len(rows), 528)
        february = next(row for row in rows if row["month"] == "1988-02")
        self.assertEqual(february, {"month": "1988-02", "source_mm_day": 0.32,
                                    "days": 29, "total_mm": 9.28})

    def test_refuses_missing_month(self):
        source = json.loads(SOURCE.read_text())
        source["properties"]["parameter"]["PRECTOTCORR"]["198802"] = -999
        with self.assertRaisesRegex(ValueError, "198802"):
            monthly_totals(source)

    def test_refuses_a_gap_in_annual_estimates(self):
        with self.assertRaisesRegex(ValueError, "consecutive"):
            linear_fit(np.array([1981, 1982, 1984, 1985, 1986, 1987]), np.arange(6), lags=1)

    def test_verified_snapshot_and_primary_estimate(self):
        result = analyze(SOURCE)
        exported = json.loads((HERE / "power-analysis.json").read_text())
        for key in ("source", "monthly", "annual"):
            self.assertEqual(result[key], exported[key])
        fit = result["windows"][0]
        for key in ("slope_mm_per_year", "p_two_sided"):
            self.assertAlmostEqual(fit[key], exported["windows"][0][key], places=10)
        self.assertEqual((fit["start"], fit["end"], fit["n_years"]), (1981, 2024, 44))
        self.assertAlmostEqual(fit["slope_mm_per_year"], 1.52484848, places=7)
        self.assertAlmostEqual(fit["p_two_sided"], 0.79524202, places=7)
        self.assertLess(fit["ci95_mm_per_year"][0], 0)
        self.assertGreater(fit["ci95_mm_per_year"][1], 0)


if __name__ == "__main__":
    unittest.main()
