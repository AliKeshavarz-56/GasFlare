import importlib.util
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/gee/acquire_landsat_metadata_resumable_2025.py"
SPEC = importlib.util.spec_from_file_location("resumable_acquisition", SCRIPT)
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


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
    Image = lambda *_: SimpleNamespace(geometry=lambda: {}, toDictionary=lambda _keys: {},
                                       id=lambda: "asset", get=lambda _key: "index")
    Dictionary = FakeDictionary
    Feature = lambda geometry, properties: {"geometry": geometry, "properties": properties.to_dict()}
    FeatureCollection = lambda features: SimpleNamespace(getInfo=lambda: {"features": features})


class AcquisitionTests(unittest.TestCase):
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
        units = mod.make_units(date(2025, 1, 1), date(2025, 1, 2), 1)[::2][:3]
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
            self.assertEqual(mod.run(directory, FakeEE, geometry, units), 0)
            self.assertEqual(StopsSecond.n, calls)
            self.assertTrue(json.loads(raw.read_text(encoding="utf-8"))["features"])


if __name__ == "__main__":
    unittest.main()
