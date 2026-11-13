import importlib.util
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "gee" / "landsat_night_pixel_diagnostic_2025.py"
SPEC = importlib.util.spec_from_file_location("landsat_night_pixel_diagnostic", SCRIPT)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


def grid(value):
    return [[value for _ in range(9)] for _ in range(9)]


def masks(value=True):
    return {band: grid(value) for band in module.REQUIRED_BANDS}


class PixelDiagnosticTests(unittest.TestCase):
    def test_deterministic_selection_chooses_two_satellites(self):
        selected = module.select_pairs()
        self.assertEqual(len(selected), 2)
        self.assertEqual({row["collection"].split("/")[1] for row in selected}, {"LC08", "LC09"})
        self.assertEqual([int(row["candidate_row_number"]) for row in selected], [4, 4])
        with open(module.ROOT / "data/derived/worldbank/landsat_night_pixel_diagnostic_2025_restricted.json", encoding="utf-8") as stream:
            report = __import__("json").load(stream)
        self.assertEqual(len(report["selected_pairs_restricted"]), 2)
        self.assertTrue(all(pair["result"] == "interpretation_unresolved" for pair in report["selected_pairs_restricted"]))
        self.assertEqual(report["live_requests"], 0)

    def test_fully_masked_window_does_not_replace_values_with_zero(self):
        result = module.inspect_window({band: grid(0) for band in module.REQUIRED_BANDS}, masks(False))
        self.assertEqual((result["total_cells"], result["valid_cells"], result["masked_cells"]), (81, 0, 81))
        self.assertIsNone(result["stored_b10"])

    def test_missing_required_band_is_rejected(self):
        arrays = {band: grid(1) for band in module.REQUIRED_BANDS if band != "QA_RADSAT"}
        with self.assertRaisesRegex(module.DiagnosticError, "QA_RADSAT"):
            module.inspect_window(arrays, masks())

    def test_qa_pixel_flags_are_counted_independently(self):
        values = [0, 1, 2, 4, 8, 16, 32]
        summary = module.qa_summary(values)
        self.assertEqual(summary, {"fill": 1, "dilated_cloud": 1, "cirrus": 1, "cloud": 1, "cloud_shadow": 1, "snow": 1})

    def test_request_failure_is_not_misclassified_as_empty_data(self):
        self.assertEqual(module.classify_request("HTTP failure", 0), "request_error")
        self.assertEqual(module.classify_request("", 0), "no_valid_data")
        self.assertEqual(module.classify_request("", 12), "reviewable_data")

    def test_valid_stored_values_have_summary(self):
        arrays = {band: grid(0) for band in module.REQUIRED_BANDS}
        arrays["B10"] = [[float(y * 9 + x) for x in range(9)] for y in range(9)]
        result = module.inspect_window(arrays, masks())
        self.assertEqual(result["stored_b10"], {"count": 81, "min": 0.0, "max": 80.0, "mean": 40.0})


if __name__ == "__main__":
    unittest.main()
