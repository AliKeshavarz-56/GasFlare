import importlib.util
import tempfile
import unittest
from pathlib import Path

from shapely.geometry import MultiPolygon, Polygon, mapping


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "data" / "screen_landsat_candidate_footprints_2025.py"


def load_module():
    spec = importlib.util.spec_from_file_location("candidate_footprint_screen_under_test", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def footprint(geometry, satellite="LC08", product_id="LC08_TEST_20250101_02_T2"):
    return {"geometry": geometry, "product_id": product_id,
            "collection": f"LANDSAT/{satellite}/C02/T2", "asset_id": f"asset-{product_id}",
            "satellite": satellite}


class CandidateFootprintTests(unittest.TestCase):
    def setUp(self):
        self.mod = load_module()
        self.square = Polygon([(0, 0), (2, 0), (2, 2), (0, 2), (0, 0)])

    def candidate(self, row, longitude, latitude):
        return {"candidate_id": f"c{row}", "candidate_row_number": row,
                "longitude": longitude, "latitude": latitude, "year": "2025"}

    def test_inside_point_matches_footprint(self):
        pairs, summary = self.mod.screen([self.candidate(7, 1, 1)], [footprint(self.square)])
        self.assertEqual(pairs[0]["relationship"], "inside")
        self.assertEqual(pairs[0]["candidate_row_number"], 7)
        self.assertEqual(summary[0]["status"], "matched")
        self.assertEqual(summary[0]["match_count"], 1)

    def test_boundary_point_is_reported_separately(self):
        pairs, _ = self.mod.screen([self.candidate(2, 0, 1)], [footprint(self.square)])
        self.assertEqual(pairs[0]["relationship"], "on_boundary")

    def test_outside_point_does_not_match(self):
        pairs, summary = self.mod.screen([self.candidate(3, 3, 1)], [footprint(self.square)])
        self.assertEqual(pairs, [])
        self.assertEqual(summary[0]["status"], "unmatched")
        self.assertEqual(summary[0]["match_count"], 0)

    def test_unmatched_candidates_remain_in_summary(self):
        candidates = [self.candidate(1, 1, 1), self.candidate(2, 4, 4)]
        _, summary = self.mod.screen(candidates, [footprint(self.square)])
        self.assertEqual([row["status"] for row in summary], ["matched", "unmatched"])
        self.assertEqual([row["candidate_row_number"] for row in summary], [1, 2])

    def test_multi_satellite_pairs_have_deterministic_order_and_counts(self):
        candidates = [self.candidate(1, 1, 1)]
        footprints = [footprint(self.square, "LC09", "LC09_TEST_02_T2"),
                      footprint(self.square, "LC08", "LC08_TEST_02_T2")]
        pairs, summary = self.mod.screen(candidates, footprints)
        self.assertEqual([pair["collection"] for pair in pairs],
                         ["LANDSAT/LC08/C02/T2", "LANDSAT/LC09/C02/T2"])
        self.assertEqual((summary[0]["matched_lc08"], summary[0]["matched_lc09"]), (1, 1))

    def test_footprint_loader_rejects_invalid_geometry_without_repair(self):
        invalid = Polygon([(0, 0), (2, 2), (0, 2), (2, 0), (0, 0)])
        data = {"type": "FeatureCollection", "features": [{
            "type": "Feature", "geometry": mapping(invalid), "properties": {
                "collection": "LANDSAT/LC08/C02/T2", "LANDSAT_PRODUCT_ID": "LC08_TEST_02_T2"}}]}
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "invalid.geojson"
            import json
            path.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(self.mod.ScreeningError):
                self.mod.load_footprints(path)

    def test_footprint_loader_accepts_multipolygon(self):
        multi = MultiPolygon([self.square, Polygon([(3, 0), (4, 0), (4, 1), (3, 1), (3, 0)])])
        data = {"type": "FeatureCollection", "features": [{
            "type": "Feature", "geometry": mapping(multi), "properties": {
                "collection": "LANDSAT/LC08/C02/T2", "LANDSAT_PRODUCT_ID": "LC08_TEST_02_T2"}}]}
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "multi.geojson"
            import json
            path.write_text(json.dumps(data), encoding="utf-8")
            footprints, crs = self.mod.load_footprints(path)
        self.assertEqual(footprints[0]["geometry"].geom_type, "MultiPolygon")
        self.assertIsNone(crs)


if __name__ == "__main__":
    unittest.main()
