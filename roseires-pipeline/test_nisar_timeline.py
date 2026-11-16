import unittest

from catalog_nisar import CATALOG
from extract_nisar import native_window, source_file
from pipeline import load


class NisarTimelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = load(CATALOG)
        cls.candidates = [row for row in cls.catalog["granules"]
                          if row["status"] == "awaiting native HH verification"]

    def test_catalog_candidate_metadata(self):
        self.assertEqual(len(self.catalog["granules"]), 38)
        self.assertEqual(self.catalog["queries"]["VALIDATED"]["hits"], 0)
        self.assertEqual(len(self.candidates), 8)
        self.assertIn("2026-08-17", {item["datetime"][:10] for item in self.candidates})
        for row in self.candidates:
            self.assertEqual((row["track"], row["frame"], row["frequency_a_mhz"]), (57, 7, 20))
            self.assertIn("HH", row["frequency_a_polarizations"])
            self.assertIsNone(row["optical_date"])
            source, verified = source_file(row, None)
            self.assertTrue(source.startswith("/vsicurl/https://nisar.asf.earthdatacloud.nasa.gov/"))
            self.assertFalse(verified)

    def test_native_window_keeps_posting_and_chooses_nearest(self):
        info = {"size": [100, 200], "geoTransform": [640000, 20, 0, 1310000, 0, -20],
                "coordinateSystem": {"wkt": 'PROJCRS["WGS 84 / UTM zone 36N",ID["EPSG",32636]]'},
                "bands": [{"type": "Float32"}]}
        grid = {"west": 640025, "north": 1309951, "width": 10, "height": 20}
        self.assertEqual(native_window(info, grid), ((1, 2, 10, 20), [-5, 9]))
        with self.assertRaisesRegex(ValueError, "full study grid"):
            native_window(info, {**grid, "width": 101})
        with self.assertRaisesRegex(ValueError, "20 m UTM 36N"):
            native_window({**info, "geoTransform": [640000, 40, 0, 1310000, 0, -40]}, grid)

    def test_archive_url_is_restricted(self):
        row = self.candidates[0]
        with self.assertRaisesRegex(ValueError, "NASA ASF archive"):
            source_file({**row, "source_url": "https://example.com/" + row["id"] + ".h5"}, None)


if __name__ == "__main__":
    unittest.main()
