"""Resumable metadata-only Landsat acquisition; running requires separate authorization."""

import hashlib
import json
import os
import tempfile
from datetime import date, timedelta, datetime, timezone
from pathlib import Path


COLLECTIONS = (
    "LANDSAT/LC08/C02/T1", "LANDSAT/LC08/C02/T2",
    "LANDSAT/LC09/C02/T1", "LANDSAT/LC09/C02/T2",
)
PARTITIONS = (("day", "gt", 0), ("night", "lt", 0))
PROPERTIES = (
    "LANDSAT_PRODUCT_ID", "system:index", "system:time_start", "DATE_ACQUIRED",
    "SCENE_CENTER_TIME", "SPACECRAFT_ID", "WRS_PATH", "WRS_ROW", "SUN_ELEVATION",
    "PROCESSING_LEVEL", "COLLECTION_CATEGORY", "CLOUD_COVER", "CLOUD_COVER_LAND",
    "IMAGE_QUALITY", "IMAGE_QUALITY_OLI", "IMAGE_QUALITY_TIRS", "SATURATION_BAND_10",
)
START = date(2025, 1, 1)
END = date(2026, 1, 1)


def summarize_counts(counts):
    totals = {collection: sum(counts[collection][key] for key in ("day", "night", "zero", "missing_or_null"))
              for collection in COLLECTIONS}
    if any(totals[c] != counts[c]["total"] for c in COLLECTIONS):
        raise ValueError("Per-collection partition counts do not match total")
    return {
        "total": sum(totals.values()),
        "day": sum(counts[c]["day"] for c in COLLECTIONS),
        "night": sum(counts[c]["night"] for c in COLLECTIONS),
        "zero": sum(counts[c]["zero"] for c in COLLECTIONS),
        "missing_or_null": sum(counts[c]["missing_or_null"] for c in COLLECTIONS),
        "tier1": totals[COLLECTIONS[0]] + totals[COLLECTIONS[2]],
        "tier2": totals[COLLECTIONS[1]] + totals[COLLECTIONS[3]],
    }


def make_units(start=START, end=END, span_days=14):
    if span_days < 1 or end <= start:
        raise ValueError("Invalid unit interval")
    units = []
    cursor = start
    while cursor < end:
        following = min(cursor + timedelta(days=span_days), end)
        for collection in COLLECTIONS:
            for partition, operator, value in PARTITIONS:
                query = {"collection": collection, "start_inclusive": cursor.isoformat(),
                         "end_exclusive": following.isoformat(), "partition": partition,
                         "property": "SUN_ELEVATION", "operator": operator, "value": value,
                         "cloud_filter": None, "wrs_filter": None, "limit": None,
                         "geometry": "exact verified A union; no simplification or bbox"}
                canonical = json.dumps(query, sort_keys=True, separators=(",", ":")).encode()
                uid = hashlib.sha256(canonical).hexdigest()
                units.append({"id": uid, "query": query})
        cursor = following
    return units


def atomic_bytes(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=path.name + ".", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def atomic_json(path, value):
    atomic_bytes(path, json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def verified_success(unit, directory):
    raw_path = directory / f"{unit['id']}.geojson"
    manifest_path = directory / f"{unit['id']}.manifest.json"
    if not raw_path.exists() or not manifest_path.exists():
        return False
    raw = raw_path.read_bytes()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    response = json.loads(raw.decode("utf-8"))
    features = response.get("features") if isinstance(response, dict) else None
    try:
        return (manifest.get("status") == "success" and manifest.get("unit_id") == unit["id"]
                and manifest.get("query") == unit["query"] and isinstance(features, list)
                and manifest.get("count") == len(features) and manifest.get("size_bytes") == len(raw)
                and manifest.get("sha256") == hashlib.sha256(raw).hexdigest())
    except (OSError, UnicodeError, json.JSONDecodeError, AttributeError):
        return False


def acquire_unit(unit, directory, ee_api, scope_geometry):
    q = unit["query"]
    start, end = q["start_inclusive"], q["end_exclusive"]
    collection = (ee_api.ImageCollection(q["collection"]).filterDate(start, end)
                  .filterBounds(scope_geometry))
    collection = collection.filter(getattr(ee_api.Filter, q["operator"])(q["property"], q["value"]))
    count = collection.size().getInfo()
    if count:
        images = collection.sort("system:time_start").toList(count)
        feature_list = images.map(lambda image: ee_api.Feature(
            ee_api.Image(image).geometry(),
            ee_api.Dictionary(ee_api.Image(image).toDictionary(list(PROPERTIES)))
            .set("source_asset_id", ee_api.Image(image).id())
            .set("source_system_index", ee_api.Image(image).get("system:index"))
            .set("collection_id", q["collection"]),
        ))
    else:
        feature_list = []
    features = ee_api.FeatureCollection(feature_list)
    raw_path = directory / f"{unit['id']}.geojson"
    temporary = None
    try:
        response = features.getInfo()
        encoded = json.dumps(response, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        temporary = raw_path.with_name(raw_path.name + ".pending")
        with temporary.open("wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, raw_path)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    reread = raw_path.read_bytes()
    reread_value = json.loads(reread.decode("utf-8"))
    if (reread != encoded or reread_value != response
            or not isinstance(reread_value.get("features"), list)
            or len(reread_value["features"]) != count):
        raise ValueError("Raw response read-back or count mismatch")
    manifest = {"status": "success", "unit_id": unit["id"], "query": q,
                "count": count, "size_bytes": len(reread),
                "sha256": hashlib.sha256(reread).hexdigest(), "raw_response": raw_path.name,
                "completed_utc": datetime.now(timezone.utc).isoformat()}
    atomic_json(directory / f"{unit['id']}.manifest.json", manifest)


def run(directory, ee_api, scope_geometry, units=None):
    """Execute units sequentially, stopping on first error; never retries."""
    units = make_units() if units is None else units
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    for unit in units:
        if verified_success(unit, directory):
            continue
        atomic_json(directory / f"{unit['id']}.manifest.json", {
            "status": "pending", "unit_id": unit["id"], "query": unit["query"]})
        try:
            acquire_unit(unit, directory, ee_api, scope_geometry)
        except Exception as exc:
            atomic_json(directory / f"{unit['id']}.manifest.json", {
                "status": "failed", "unit_id": unit["id"], "query": unit["query"],
                "error_type": type(exc).__name__, "error": str(exc), "retry": False,
                "failed_utc": datetime.now(timezone.utc).isoformat()})
            return 2
    return 0


if __name__ == "__main__":
    raise SystemExit("Not executable without separately authorized runner and verified private scope geometry")
