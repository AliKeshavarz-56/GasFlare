import importlib.util
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/gee/acquire_day_inventory_khuzestan.py"
SPEC = importlib.util.spec_from_file_location("khuzestan_day_inventory", SCRIPT)
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


class DayInventoryTests(unittest.TestCase):
    def test_fixed_interval_month_partitions_have_no_gaps_or_overlap(self):
        parts = list(mod.intervals())
        self.assertEqual(parts[0], (date(2024, 1, 1), date(2024, 2, 1)))
        self.assertEqual(parts[-1], (date(2026, 11, 1), date(2026, 11, 18)))
        self.assertEqual(len(parts), 35)
        self.assertTrue(all(a[1] == b[0] for a, b in zip(parts, parts[1:])))

    def test_fixed_dates_and_tiers(self):
        self.assertEqual(mod.START.isoformat(), "2024-01-01")
        self.assertEqual(mod.END.isoformat(), "2026-11-18")
        self.assertEqual(mod.LANDSAT, (
            "LANDSAT/LC08/C02/T1", "LANDSAT/LC08/C02/T2",
            "LANDSAT/LC09/C02/T1", "LANDSAT/LC09/C02/T2"))

    def test_sentinel_solar_conversion_preserves_missing_values(self):
        self.assertEqual(mod.sentinel_sun_elevation(30.5), 59.5)
        self.assertIsNone(mod.sentinel_sun_elevation(None))
        self.assertIsNone(mod.sentinel_sun_elevation("30.5"))
        self.assertIsNone(mod.sentinel_sun_elevation(True))

    def test_landsat_fields_include_required_metadata(self):
        self.assertTrue({"SUN_ELEVATION", "WRS_PATH", "WRS_ROW", "CLOUD_COVER"}
                        .issubset(mod.LANDSAT_PROPERTIES))

    def test_sentinel_fields_include_required_metadata(self):
        self.assertTrue({"MEAN_SOLAR_ZENITH_ANGLE", "MGRS_TILE", "CLOUDY_PIXEL_PERCENTAGE"}
                        .issubset(mod.SENTINEL_PROPERTIES))

    def test_atomic_json_preserves_previous_file_when_replace_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text('{"valid":true}', encoding="utf-8")
            with patch.object(mod.os, "replace", side_effect=PermissionError("denied")):
                with self.assertRaises(PermissionError):
                    mod.atomic_json(path, {"valid": False})
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"valid": True})
            self.assertEqual(list(Path(directory).glob("*.pending")), [])

    def test_saved_part_validation_enforces_count_collection_time_solar_and_footprint(self):
        feature = {"type": "Feature", "id": "scene-1", "geometry": {
            "type": "Polygon", "coordinates": [[[49, 31], [50, 31], [50, 32], [49, 31]]]},
            "properties": {"collection_id": "LANDSAT/LC08/C02/T1", "source_asset_id": "scene-1",
                           "system:index": "scene-1", "system:time_start": 1746256469793,
                           "SUN_ELEVATION": 64.3}}
        record = {"collection": "LANDSAT/LC08/C02/T1", "start": "2025-05-01", "end": "2025-06-01",
                  "kind": "day", "count": 1, "received_count": 1}
        with tempfile.TemporaryDirectory() as directory:
            raw = Path(directory) / "response.geojson"
            raw.write_text(json.dumps({"type": "FeatureCollection", "features": [feature]}), encoding="utf-8")
            result = mod.validate_saved_part(raw, record)
            self.assertEqual(result["count"], 1)
            self.assertEqual(result["sha256"], mod.sha256(raw))
            record["count"] = 2
            with self.assertRaisesRegex(ValueError, "count"):
                mod.validate_saved_part(raw, record)

    def test_recovery_refuses_manifest_duplicate_without_changing_state(self):
        with tempfile.TemporaryDirectory() as directory:
            sensor_dir = Path(directory)
            unit_id = "unit"
            record = {"collection": "LANDSAT/LC08/C02/T1", "start": "2025-05-01", "end": "2025-06-01",
                      "kind": "day", "unit_id": unit_id, "status": "failed_stopped",
                      "raw_response": "unit.geojson", "count": 0, "received_count": 0}
            (sensor_dir / "unit.status.json").write_text(json.dumps(record), encoding="utf-8")
            (sensor_dir / "unit.geojson").write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
            manifest = {"status": "stopped_on_first_error", "parts": [dict(record, status="success")]}
            (sensor_dir / "manifest_private.json").write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "already marks"):
                mod.recover_saved_part(sensor_dir, unit_id)
            saved_status = json.loads((sensor_dir / "unit.status.json").read_text(encoding="utf-8"))
            self.assertEqual(saved_status["status"], "failed_stopped")


if __name__ == "__main__":
    unittest.main()
