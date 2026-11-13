import importlib.util
import math
import sys
import types
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
        self.assertEqual({row["collection"] for row in selected}, set(module.COLLECTIONS.values()))
        self.assertTrue(all("_L1" in row["footprint_product_id"] and row["footprint_product_id"].endswith("_02_T2") for row in selected))
        with open(module.ROOT / "data/derived/worldbank/landsat_night_pixel_diagnostic_2025_restricted.json", encoding="utf-8") as stream:
            report = __import__("json").load(stream)
        self.assertEqual(len(report["selected_pairs_restricted"]), 2)
        self.assertTrue(all(pair["result"] == "interpretation_unresolved" for pair in report["selected_pairs_restricted"]))
        self.assertEqual(report["live_requests"], 0)

    def test_fully_masked_window_does_not_replace_values_with_zero(self):
        result = module.inspect_window({band: grid(0) for band in module.REQUIRED_BANDS}, masks(False))
        self.assertEqual((result["total_cells"], result["valid_cells"], result["masked_cells"]), (81, 0, 81))
        self.assertIsNone(result["stored_b10"])

    def test_mixed_validity_uses_band_masks_not_values_or_qa_flags(self):
        arrays = {band: grid(0) for band in module.REQUIRED_BANDS}
        arrays["B10"] = grid(0)
        band_masks = masks()
        band_masks["B10"] = grid(False)
        band_masks["B10"][0][0] = True
        band_masks["QA_PIXEL"][0][1] = False
        result = module.inspect_window(arrays, band_masks)
        self.assertEqual((result["valid_cells"], result["masked_cells"]), (1, 80))
        self.assertEqual(result["stored_b10"], {"count": 1, "min": 0, "max": 0, "mean": 0.0})
        self.assertEqual(result["qa_pixel"], {name: 0 for name in module.QA_PIXEL_BITS})

    def test_zero_qa_is_counted_as_clear_when_its_mask_is_valid(self):
        arrays = {band: grid(0) for band in module.REQUIRED_BANDS}
        result = module.inspect_window(arrays, masks())
        self.assertEqual(result["valid_cells"], 81)
        self.assertEqual(result["qa_pixel"], {name: 0 for name in module.QA_PIXEL_BITS})

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

    def test_live_mode_fails_closed_before_any_pixel_request(self):
        calls = []
        fake_ee = types.SimpleNamespace(Initialize=lambda **kwargs: (_ for _ in ()).throw(RuntimeError("403 https://private.invalid/token=secret")), Image=lambda *_: calls.append("asset"))
        previous = sys.modules.get("ee")
        sys.modules["ee"] = fake_ee
        try:
            with self.assertRaisesRegex(module.DiagnosticError, "initialization failed") as caught:
                module.main(["--live"])
            self.assertEqual(calls, [])
            self.assertNotIn("private.invalid", str(caught.exception))
            self.assertNotIn("secret", str(caught.exception))
        finally:
            if previous is None:
                del sys.modules["ee"]
            else:
                sys.modules["ee"] = previous

    def asset_info(self):
        transform = [30, 0, 500000, 0, -30, 4000000]
        return {"bands": [{"id": band, "data_type": {"precision": "int"}, "crs": "EPSG:32639", "crs_transform": transform} for band in module.REQUIRED_BANDS], "properties": {}}

    def test_asset_validation_rejects_missing_band(self):
        info = self.asset_info()
        info["bands"] = info["bands"][:-1]
        with self.assertRaisesRegex(module.DiagnosticError, "missing required asset bands"):
            module.validate_asset_info(info)

    def test_asset_validation_rejects_invalid_or_inconsistent_projection(self):
        info = self.asset_info()
        info["bands"][0]["crs_transform"] = [0, 0, 0, 0, 0, 0]
        with self.assertRaisesRegex(module.DiagnosticError, "affine transform is invalid"):
            module.validate_asset_info(info)
        info = self.asset_info()
        info["bands"][1]["crs"] = "EPSG:4326"
        with self.assertRaisesRegex(module.DiagnosticError, "do not share"):
            module.validate_asset_info(info)

    def test_missing_conversion_coefficients_remain_missing(self):
        spec = module.validate_asset_info(self.asset_info())
        self.assertTrue(all(value is None for value in spec["coefficients"].values()))

    def test_error_scrubber_suppresses_html_body(self):
        cleaned = module.clean_error(RuntimeError('HTTPError 403 https://private.invalid "Ok" <!DOCTYPE html> Authorization: Bearer secret'))
        self.assertEqual(cleaned, "HTTP 403; response body suppressed")
        self.assertNotIn("secret", cleaned)

    def test_affine_centered_pixel_grid_is_nine_by_nine(self):
        import pyproj

        longitude, latitude = pyproj.Transformer.from_crs("EPSG:32639", "EPSG:4326", always_xy=True).transform(500015, 3999985)
        transform = [30, 0, 500000, 0, -30, 4000000]
        grid_transform = module.pixel_grid(longitude, latitude, transform, "EPSG:32639")
        self.assertEqual(grid_transform, [30, 0, 499880, 0, -30, 4000120])
        self.assertTrue(all(math.isfinite(value) for value in grid_transform))

    def test_radsat_reports_dropped_not_b10_saturation(self):
        arrays = {band: grid(0) for band in module.REQUIRED_BANDS}
        arrays["QA_RADSAT"][0][0] = 1 << 9
        result = module.inspect_window(arrays, masks())
        self.assertEqual(result["qa_radsat_dropped_cells"], 1)
        self.assertIsNone(result["qa_radsat_b10_saturated_cells"])

    def test_valid_stored_values_have_summary(self):
        arrays = {band: grid(0) for band in module.REQUIRED_BANDS}
        arrays["B10"] = [[float(y * 9 + x) for x in range(9)] for y in range(9)]
        result = module.inspect_window(arrays, masks())
        self.assertEqual(result["stored_b10"], {"count": 81, "min": 0.0, "max": 80.0, "mean": 40.0})

    def test_live_pixel_response_uses_predecoded_structured_array(self):
        import numpy as np
        import pyproj

        longitude, latitude = pyproj.Transformer.from_crs("EPSG:32639", "EPSG:4326", always_xy=True).transform(500015, 3999985)
        selected = [{"asset_id": "asset", "longitude": longitude, "latitude": latitude, "footprint_product_id": "PRODUCT_L1_02_T2"}]
        transform = [30, 0, 500000, 0, -30, 4000000]
        spec = {"transform": transform, "projection": "EPSG:32639", "coefficients": {}}
        pixel_dtype = [(band, "i4") for band in module.REQUIRED_BANDS + tuple("mask_" + band for band in module.REQUIRED_BANDS)]
        pixels = np.zeros((9, 9), dtype=pixel_dtype)

        class FakeImage:
            def getInfo(self):
                return {"properties": {"LANDSAT_PRODUCT_ID": "PRODUCT_L1_02_T2"}}

            def select(self, *_):
                return self

            def addBands(self, *_):
                return self

            def mask(self):
                return self

            def rename(self, *_):
                return self

        fake_ee = types.SimpleNamespace(
            Image=lambda *_: FakeImage(),
            data=types.SimpleNamespace(computePixels=lambda *_: pixels),
        )
        original_validate = module.validate_asset_info
        module.validate_asset_info = lambda _: spec
        try:
            result = module.live_pair_diagnostics(selected, fake_ee, np)
        finally:
            module.validate_asset_info = original_validate
        self.assertEqual(result[0]["total_cells"], 81)

    def test_live_pixel_response_rejects_non_structured_data_offline(self):
        import pyproj

        longitude, latitude = pyproj.Transformer.from_crs("EPSG:32639", "EPSG:4326", always_xy=True).transform(500015, 3999985)
        selected = [{"asset_id": "asset", "longitude": longitude, "latitude": latitude, "footprint_product_id": "PRODUCT_L1_02_T2"}]
        transform = [30, 0, 500000, 0, -30, 4000000]
        spec = {"transform": transform, "projection": "EPSG:32639", "coefficients": {}}

        class FakeImage:
            def getInfo(self):
                return {"properties": {"LANDSAT_PRODUCT_ID": "PRODUCT_L1_02_T2"}}

            def select(self, *_):
                return self

            def addBands(self, *_):
                return self

            def mask(self):
                return self

            def rename(self, *_):
                return self

        fake_ee = types.SimpleNamespace(
            Image=lambda *_: FakeImage(),
            data=types.SimpleNamespace(computePixels=lambda *_: b"not a decoded array"),
        )
        original_validate = module.validate_asset_info
        module.validate_asset_info = lambda _: spec
        try:
            with self.assertRaisesRegex(module.DiagnosticError, "not a structured NumPy array"):
                module.live_pair_diagnostics(selected, fake_ee, object())
        finally:
            module.validate_asset_info = original_validate


if __name__ == "__main__":
    unittest.main()
