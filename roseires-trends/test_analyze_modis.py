import unittest

from analyze_modis import analyze, read_months


class ModisAnalysisTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = analyze()

    def test_missing_months_remain_gaps(self):
        self.assertEqual(self.result["coverage"], {"published": 235, "fill_value": 77, "no_granule": 5})
        months = {row["month"]: row for row in self.result["monthly"]}
        self.assertIsNone(months["2000-06"]["area_km2"])
        self.assertIsNone(months["2022-01"]["area_km2"])
        self.assertEqual(months["2022-01"]["status"], "no_granule")
        self.assertGreater(months["2000-03"]["area_km2"], 0)

    def test_calendar_fills_absent_row_with_gap(self):
        data = b"month_utc,lake_id,grand_id,status,lake_area_km2\n"
        data += b"2000-01,111,4483,published,0\n2000-03,111,4483,published,300\n"
        rows = read_months(data)
        self.assertEqual(rows[0]["area_km2"], 0)
        self.assertEqual(rows[1], {"month": "2000-02", "area_km2": None, "status": "no_granule"})

    def test_reported_fits(self):
        shift = self.result["shift_km2"]
        slope = self.result["post_slope_km2_per_year"]
        self.assertAlmostEqual(shift["estimate"], 164.069059, places=5)
        self.assertAlmostEqual(shift["ci95"][0], 107.548711, places=5)
        self.assertAlmostEqual(shift["ci95"][1], 220.589407, places=5)
        self.assertAlmostEqual(slope["estimate"], -1.262599, places=5)
        self.assertAlmostEqual(slope["ci95"][0], -3.340755, places=5)
        self.assertAlmostEqual(slope["ci95"][1], 0.815558, places=5)
        self.assertGreater(slope["p_two_sided"], .05)
