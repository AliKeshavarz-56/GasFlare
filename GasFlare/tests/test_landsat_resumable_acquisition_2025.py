import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/gee/acquire_landsat_metadata_resumable_2025.py"
SPEC = importlib.util.spec_from_file_location("resumable_acquisition", SCRIPT)
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)
RUNNER = SCRIPT.with_name("run_landsat_metadata_trial_2025.py")
sys.path.insert(0, str(SCRIPT.parent))
RUN_SPEC = importlib.util.spec_from_file_location("trial_runner", RUNNER)
runner = importlib.util.module_from_spec(RUN_SPEC)
RUN_SPEC.loader.exec_module(runner)


class FakeSize:
    def getInfo(self):
        return 1


class FakeList:
    def map(self, fn):
        return [fn("image")]


class FakeDictionary:
    def __init__(self, value): self.value = dict(value)
    def set(self, key, value):
        self.value[key] = value
        return self

    def to_dict(self):
        return self.value


class FakeCollection:
    def filterDate(self, *_): return self
    def filterBounds(self, *_): return self
    def filter(self, *_): return self
    def sort(self, *_): return self
    def size(self): return FakeSize()
    def toList(self, _): return FakeList()


class FakeEE:
    Filter = SimpleNamespace(gt=lambda *_: None, lt=lambda *_: None)
    Geometry = lambda *_: None
    ImageCollection = lambda *_: FakeCollection()
    Image = lambda *_: SimpleNamespace(geometry=lambda: {"type": "Polygon", "coordinates": []},
                                       toDictionary=lambda _keys: {"SPACECRAFT_ID": "LANDSAT_8",
                                          "WRS_PATH": 1, "WRS_ROW": 2, "system:time_start": 1735689600000,
                                          "SUN_ELEVATION": 10},
                                       id=lambda: "LANDSAT/LC08/C02/T1/asset", get=lambda _key: "index")
    Dictionary = FakeDictionary
    Feature = lambda geometry, properties: {"geometry": geometry, "properties": properties.to_dict()}
    FeatureCollection = lambda features: SimpleNamespace(getInfo=lambda: {"type": "FeatureCollection", "features": features})


class AcquisitionTests(unittest.TestCase):
    def trial(self, **overrides):
        events = []
        class API:
            __version__ = "offline-test"
            def Initialize(self, **_):
                events.append("initialize")
                if overrides.get("initialize_error"):
                    raise RuntimeError("init failed")
            def Geometry(self, *_args, **_kwargs):
                events.append("geometry")
                if overrides.get("geometry_error"):
                    raise RuntimeError("geometry failed")
                return object()
        api = API()
        api.Initialize = api.Initialize
        def prepare():
            events.append("local")
            if overrides.get("preflight_error"):
                raise ValueError("local failed")
            return {"type": "Polygon", "coordinates": []}
        def fake_run(_directory, _api, _region, units):
            events.append("count")
            if overrides.get("count_error"):
                raise TimeoutError("count failed")
            events.append("metadata")
            return 0
        old_run = runner.run
        runner.run = fake_run
        try:
            with tempfile.TemporaryDirectory() as tmp:
                result = runner.execute(Path(tmp) / "run", ee_api=api, scope_preparer=prepare)
                report = json.loads((Path(tmp) / "run" / "run_status_private.json").read_text())
        finally:
            runner.run = old_run
        return result, events, report

    def test_trial_orders_local_initialization_geometry_then_count(self):
        result, events, report = self.trial()
        self.assertEqual(result, 0)
        self.assertEqual(events, ["local", "initialize", "geometry", "count", "metadata"])
        self.assertEqual(report["status"], "success")

    def test_initialization_failure_stops_before_geometry_and_count(self):
        result, events, report = self.trial(initialize_error=True)
        self.assertEqual(result, 2)
        self.assertEqual(events, ["local", "initialize"])
        self.assertEqual(report["status"], "failed")
        self.assertIsNone(report["count"])
        self.assertEqual(report["failed_stage"], "earth_engine_initialization")

    def test_geometry_failure_stops_before_count(self):
        result, events, report = self.trial(geometry_error=True)
        self.assertEqual(result, 2)
        self.assertEqual(events, ["local", "initialize", "geometry"])
        self.assertEqual(report["failed_stage"], "earth_engine_geometry_construction")

    def test_count_failure_stops_without_metadata_or_retry(self):
        result, events, report = self.trial(count_error=True)
        self.assertEqual(result, 2)
        self.assertEqual(events, ["local", "initialize", "geometry", "count"])
        self.assertEqual(events.count("count"), 1)
        self.assertNotIn("metadata", events)
        self.assertEqual(report["status"], "failed")

    def test_early_preflight_failure_leaves_status_and_no_ee_calls(self):
        result, events, report = self.trial(preflight_error=True)
        self.assertEqual(result, 2)
        self.assertEqual(events, ["local"])
        self.assertTrue(report["stages"])
        self.assertIsNone(report["count"])

    def test_import_has_no_initialization_or_network(self):
        code = ("import importlib.util,sys,pathlib; p=sys.argv[1]; "
                "sys.path.insert(0,str(pathlib.Path(p).parent)); "
                "s=importlib.util.spec_from_file_location('import_probe',p); "
                "m=importlib.util.module_from_spec(s); s.loader.exec_module(m)")
        completed = subprocess.run([sys.executable, "-c", code, str(RUNNER)],
                                   capture_output=True, text=True, check=False)
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_authorized_trial_is_exactly_one_unit(self):
        unit = mod.make_trial_unit()
        self.assertEqual(unit["query"], {
            "collection": "LANDSAT/LC08/C02/T1", "start_inclusive": "2025-01-01",
            "end_exclusive": "2025-01-02", "partition": "day", "property": "SUN_ELEVATION",
            "operator": "gt", "value": 0, "cloud_filter": None, "wrs_filter": None,
            "limit": None, "geometry": "exact verified A union; no simplification or bbox"})
        self.assertEqual(len(mod.make_units(date(2025, 1, 1), date(2025, 1, 2), 1)), 8)

    def test_count_partitions_and_collection_tiers_reconcile(self):
        counts = {
            "LANDSAT/LC08/C02/T1": {"total": 310, "day": 310, "night": 0, "zero": 0, "missing_or_null": 0},
            "LANDSAT/LC08/C02/T2": {"total": 56, "day": 10, "night": 46, "zero": 0, "missing_or_null": 0},
            "LANDSAT/LC09/C02/T1": {"total": 311, "day": 311, "night": 0, "zero": 0, "missing_or_null": 0},
            "LANDSAT/LC09/C02/T2": {"total": 52, "day": 8, "night": 44, "zero": 0, "missing_or_null": 0},
        }
        summary = mod.summarize_counts(counts)
        self.assertEqual((summary["total"], summary["tier1"], summary["tier2"]), (729, 621, 108))
        self.assertEqual((summary["day"], summary["night"]), (639, 90))
        self.assertEqual([counts[c]["total"] for c in mod.COLLECTIONS], [310, 56, 311, 52])
        self.assertEqual(sum(counts[c]["total"] for c in mod.COLLECTIONS), 729)
        self.assertEqual(summary["day"] + summary["night"] + summary["zero"] + summary["missing_or_null"], summary["total"])
        self.assertEqual(summary["tier1"] + summary["tier2"], summary["total"])
        counts["LANDSAT/LC08/C02/T2"]["day"] += 1
        with self.assertRaisesRegex(ValueError, "partition counts"):
            mod.summarize_counts(counts)

    def test_inconsistent_collection_total_is_rejected(self):
        counts = {
            "LANDSAT/LC08/C02/T1": {"total": 310, "day": 310, "night": 0, "zero": 0, "missing_or_null": 0},
            "LANDSAT/LC08/C02/T2": {"total": 56, "day": 10, "night": 46, "zero": 0, "missing_or_null": 0},
            "LANDSAT/LC09/C02/T1": {"total": 311, "day": 311, "night": 0, "zero": 0, "missing_or_null": 0},
            "LANDSAT/LC09/C02/T2": {"total": 52, "day": 8, "night": 44, "zero": 0, "missing_or_null": 0},
        }
        counts["LANDSAT/LC09/C02/T2"]["total"] = 51
        with self.assertRaisesRegex(ValueError, "partition counts"):
            mod.summarize_counts(counts)

    def test_units_have_nonoverlapping_half_open_date_boundaries(self):
        units = mod.make_units(date(2025, 1, 1), date(2025, 2, 1), 14)
        intervals = sorted({(u["query"]["start_inclusive"], u["query"]["end_exclusive"]) for u in units})
        self.assertEqual(intervals, [("2025-01-01", "2025-01-15"),
                                     ("2025-01-15", "2025-01-29"),
                                     ("2025-01-29", "2025-02-01")])
        self.assertTrue(all(a[1] == b[0] for a, b in zip(intervals, intervals[1:])))
        self.assertEqual(len(units), 24)
        self.assertEqual(len({u["id"] for u in units}), len(units))

    def test_successful_unit_survives_stop_and_is_not_requested_again(self):
        units = mod.make_units(date(2025, 1, 1), date(2025, 1, 2), 1)[:2]
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            geometry = object()
            class StopsSecond(FakeEE):
                n = 0
                @staticmethod
                def ImageCollection(_):
                    StopsSecond.n += 1
                    if StopsSecond.n == 2:
                        raise TimeoutError("synthetic timeout")
                    return FakeCollection()
            first = units[0]
            self.assertEqual(mod.run(directory, StopsSecond, geometry, units), 2)
            raw = directory / f"{first['id']}.geojson"
            self.assertTrue(raw.exists())
            self.assertTrue(mod.verified_success(first, directory))
            calls = StopsSecond.n
            self.assertEqual(mod.run(directory, FakeEE, geometry, [first]), 0)
            self.assertEqual(StopsSecond.n, calls)
            self.assertTrue(json.loads(raw.read_text(encoding="utf-8"))["features"])


if __name__ == "__main__":
    unittest.main()
