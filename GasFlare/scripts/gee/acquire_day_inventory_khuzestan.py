"""Checkpointed daytime Landsat and Sentinel-2 metadata inventory for Khuzestan."""

import hashlib
import json
import os
import re
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

import geopandas as gpd
from shapely.geometry import mapping
from shapely.ops import unary_union


ROOT = Path(__file__).resolve().parents[2]
BOUNDARY = Path(os.environ.get(
    "KHZ_INVENTORY_BOUNDARY", ROOT / "data" / "boundaries" / "khuzestan_province_wgs84.geojson"
)).expanduser()
BOUNDARY_REPORT = Path(os.environ.get(
    "KHZ_INVENTORY_BOUNDARY_REPORT", ROOT / "docs" / "feasibility" / "khuzestan_owner_boundary_validation.json"
)).expanduser()
OUT_ROOT = Path(os.environ.get(
    "KHZ_INVENTORY_OUTPUT_ROOT", ROOT / "data" / "derived" / "daily_inventory_khuzestan_private"
)).expanduser()
START = date(2024, 1, 1)
END = date(2026, 11, 18)
PROJECT = os.environ.get("KHZ_INVENTORY_EE_PROJECT")
LANDSAT = (
    "LANDSAT/LC08/C02/T1", "LANDSAT/LC08/C02/T2",
    "LANDSAT/LC09/C02/T1", "LANDSAT/LC09/C02/T2",
)
SENTINEL = ("COPERNICUS/S2_SR_HARMONIZED",)
LANDSAT_PROPERTIES = (
    "LANDSAT_PRODUCT_ID", "system:index", "system:time_start", "DATE_ACQUIRED",
    "SCENE_CENTER_TIME", "SPACECRAFT_ID", "PROCESSING_LEVEL", "COLLECTION_CATEGORY",
    "SUN_ELEVATION", "WRS_PATH", "WRS_ROW", "CLOUD_COVER",
)
SENTINEL_PROPERTIES = (
    "system:index", "system:time_start", "PRODUCT_ID", "DATATAKE_IDENTIFIER",
    "SPACECRAFT_NAME", "PROCESSING_BASELINE", "MEAN_SOLAR_ZENITH_ANGLE",
    "MGRS_TILE", "CLOUDY_PIXEL_PERCENTAGE",
)


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".pending", dir=path.parent)
    temp = Path(temp_name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    except Exception:
        temp.unlink(missing_ok=True)
        raise


def validate_saved_part(raw_path, record):
    """Validate a saved FeatureCollection against its checkpoint, without network access."""
    raw_path = Path(raw_path)
    payload = raw_path.read_bytes()
    response = json.loads(payload)
    features = response.get("features") if isinstance(response, dict) else None
    if response.get("type") != "FeatureCollection" or not isinstance(features, list):
        raise ValueError("Saved response is not a GeoJSON FeatureCollection")
    expected = record.get("count")
    if not isinstance(expected, int) or isinstance(expected, bool) or len(features) != expected:
        raise ValueError("Saved response count does not match the received count")
    if record.get("received_count") != len(features):
        raise ValueError("Saved response count does not match the checkpoint")
    collection = record["collection"]
    solar_property = "SUN_ELEVATION" if collection.startswith("LANDSAT/") else "MEAN_SOLAR_ZENITH_ANGLE"
    identities = set()
    for feature in features:
        props = feature.get("properties") or {}
        if props.get("collection_id") != collection:
            raise ValueError("Feature collection_id does not match checkpoint")
        time_start = props.get("system:time_start")
        if not isinstance(time_start, (int, float)) or isinstance(time_start, bool):
            raise ValueError("Feature is missing numeric system:time_start")
        acquired = datetime.fromtimestamp(time_start / 1000, tz=timezone.utc).date().isoformat()
        if not record["start"] <= acquired < record["end"]:
            raise ValueError("Feature timestamp is outside the checkpoint interval")
        solar = props.get(solar_property)
        if record["kind"] == "day":
            is_day = isinstance(solar, (int, float)) and not isinstance(solar, bool)
            is_day = is_day and (solar > 0 if collection.startswith("LANDSAT/") else 0 <= solar < 90)
            if not is_day:
                raise ValueError("Solar metadata does not satisfy the daytime filter")
        elif solar is not None:
            raise ValueError("Missing-solar partition contains a non-null value")
        identity = props.get("source_asset_id") or feature.get("id") or props.get("system:index")
        if not isinstance(identity, str) or not identity:
            raise ValueError("Feature is missing a stable scene identifier")
        if identity in identities:
            raise ValueError("Saved response contains duplicate scene identifiers")
        identities.add(identity)
        geometry = feature.get("geometry")
        if not isinstance(geometry, dict) or geometry.get("type") not in {"Polygon", "MultiPolygon"}:
            raise ValueError("Feature is missing polygon footprint geometry")
        if not geometry.get("coordinates"):
            raise ValueError("Feature footprint geometry has no coordinates")
        if solar_property not in props:
            raise ValueError(f"Feature is missing required metadata: {solar_property}")
    digest = hashlib.sha256(payload).hexdigest()
    if record.get("sha256") and record["sha256"] != digest:
        raise ValueError("Saved response SHA-256 does not match checkpoint")
    return {"count": len(features), "sha256": digest, "size_bytes": len(payload)}


def recover_saved_part(sensor_dir, unit_id):
    """Promote a previously failed saved response after local validation only."""
    sensor_dir = Path(sensor_dir)
    manifest_path = sensor_dir / "manifest_private.json"
    status_path = sensor_dir / f"{unit_id}.status.json"
    record = json.loads(status_path.read_text(encoding="utf-8"))
    if record.get("status") != "failed_stopped" or record.get("unit_id") != unit_id:
        raise ValueError("Only the matching failed_stopped checkpoint may be recovered")
    raw_name = record.get("raw_response")
    if not isinstance(raw_name, str) or Path(raw_name).name != raw_name:
        raise ValueError("Checkpoint raw response path is invalid")
    raw_path = sensor_dir / raw_name
    validation = validate_saved_part(raw_path, record)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    key = (record["collection"], record["start"], record["end"], record["kind"])
    matching = [part for part in manifest["parts"] if
                (part["collection"], part["start"], part["end"], part["kind"]) == key]
    if len(matching) > 1 or (matching and matching[0].get("unit_id") != unit_id):
        raise ValueError("Manifest contains a conflicting partition; refusing duplicate recovery")
    if matching and matching[0].get("status") == "success":
        raise ValueError("Manifest already marks this partition successful")
    now = datetime.now(timezone.utc).isoformat()
    recovered = dict(record)
    recovered.update({"status": "success", "recovered_from_saved_response": True,
                      "recovery_validation_utc": now, "sha256": validation["sha256"],
                      "received_count": validation["count"], "size_bytes": validation["size_bytes"]})
    recovered["initial_failure"] = {"error": record.get("error"), "failed_utc": record.get("failed_utc")}
    atomic_json(status_path, recovered)
    if matching:
        manifest["parts"].remove(matching[0])
    manifest["parts"].append(recovered)
    manifest["status"] = "stopped_on_first_error"
    manifest["recovery"] = {"unit_id": unit_id, "method": "validated_saved_response",
                            "recovered_utc": now, "online_requests_made": 0}
    atomic_json(manifest_path, manifest)
    return recovered


def local_region():
    boundary_report = json.loads(BOUNDARY_REPORT.read_text(encoding="utf-8"))
    output = boundary_report.get("derived_output") or {}
    if (boundary_report.get("status") != "PASS" or Path(output.get("path", "")).name != BOUNDARY.name
            or output.get("sha256") != sha256(BOUNDARY) or output.get("feature_count") != 1):
        raise ValueError("Khuzestan boundary validation/provenance does not match saved geometry")
    frame = gpd.read_file(BOUNDARY)
    if frame.crs is None or not frame.crs.equals("EPSG:4326") or len(frame) != 1:
        raise ValueError("Khuzestan boundary CRS or feature count is invalid")
    feature = frame.iloc[0]
    props = feature.drop(labels=[frame.geometry.name]).to_dict()
    if (str(props.get("Name_1", "")).strip().casefold() != "khuzestan"
            or str(props.get("نام_ف", "")).strip() != "خوزستان"):
        raise ValueError("Saved boundary country/province identity is not Khuzestan")
    geom = feature.geometry
    if geom is None or geom.is_empty or not geom.is_valid:
        raise ValueError("Khuzestan geometry is null, empty, or invalid")
    return mapping(geom)


def intervals():
    cursor = START
    while cursor < END:
        if cursor.month == 12:
            following = date(cursor.year + 1, 1, 1)
        else:
            following = date(cursor.year, cursor.month + 1, 1)
        following = min(following, END)
        yield cursor, following
        cursor = following


def sentinel_sun_elevation(solar_zenith):
    if isinstance(solar_zenith, (int, float)) and not isinstance(solar_zenith, bool):
        return 90.0 - solar_zenith
    return None


def safe_error(exc):
    message = re.sub(r"(?i)(token|authorization|credential|password)(\s*[:=]\s*)\S+",
                     r"\1\2[redacted]", str(exc))
    return {"type": type(exc).__name__, "message": message[:800]}


def run_sensor(ee, sensor, collections, region, directory, max_new_parts):
    props = LANDSAT_PROPERTIES if sensor == "landsat" else SENTINEL_PROPERTIES
    solar_property = "SUN_ELEVATION" if sensor == "landsat" else "MEAN_SOLAR_ZENITH_ANGLE"
    sensor_dir = directory / sensor
    sensor_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = sensor_dir / "manifest_private.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {
        "sensor": sensor, "status": "in_progress", "date_interval": [START.isoformat(), END.isoformat()],
        "collection_ids": list(collections), "parts": [], "retry": False,
    }
    indexed = {(p["collection"], p["start"], p["end"], p["kind"]): p for p in manifest["parts"]}
    completed_new = 0
    for collection_id in collections:
        for start, end in intervals():
            for kind in ("day", "solar_missing"):
                key = (collection_id, start.isoformat(), end.isoformat(), kind)
                if key in indexed and indexed[key].get("status") == "success":
                    continue
                unit_id = hashlib.sha256(json.dumps(key, separators=(",", ":")).encode()).hexdigest()
                raw_path = sensor_dir / f"{unit_id}.geojson"
                status_path = sensor_dir / f"{unit_id}.status.json"
                record = {"collection": collection_id, "start": key[1], "end": key[2], "kind": kind,
                          "unit_id": unit_id, "status": "started", "retry": False,
                          "started_utc": datetime.now(timezone.utc).isoformat()}
                atomic_json(status_path, record)
                try:
                    images = ee.ImageCollection(collection_id).filterDate(key[1], key[2]).filterBounds(region)
                    if sensor == "landsat":
                        images = images.filter(ee.Filter.gt(solar_property, 0)) if kind == "day" else images.filter(ee.Filter.Not(ee.Filter.notNull([solar_property])))
                    else:
                        images = images.filter(ee.Filter.lt(solar_property, 90)) if kind == "day" else images.filter(ee.Filter.Not(ee.Filter.notNull([solar_property])))
                    count = images.size().getInfo()
                    record.update({"count": count, "count_completed_utc": datetime.now(timezone.utc).isoformat()})
                    atomic_json(status_path, record)
                    if count:
                        ordered = images.sort("system:time_start").toList(count)
                        features = ee.FeatureCollection(ordered.map(lambda image: ee.Feature(
                            ee.Image(image).geometry(), ee.Dictionary(ee.Image(image).toDictionary(list(props)))
                            .set("source_asset_id", ee.Image(image).id())
                            .set("collection_id", collection_id))))
                        response = features.getInfo()
                    else:
                        response = {"type": "FeatureCollection", "features": []}
                    features = response.get("features") if isinstance(response, dict) else None
                    if (response.get("type") != "FeatureCollection" or not isinstance(features, list)
                            or len(features) != count):
                        raise ValueError("Metadata FeatureCollection count/type mismatch")
                    for feature in features:
                        p = feature.get("properties", {})
                        solar = p.get(solar_property)
                        is_day = (isinstance(solar, (int, float)) and not isinstance(solar, bool)
                                  and ((solar > 0) if sensor == "landsat" else (0 <= solar < 90)))
                        if kind == "day" and not is_day:
                            raise ValueError("Solar metadata does not satisfy daytime filter")
                        if kind == "solar_missing" and solar is not None:
                            raise ValueError("Missing-solar partition contains a non-null value")
                        p["sensor"] = sensor
                        p["source_asset_id"] = p.get("source_asset_id") or feature.get("id")
                        if sensor == "sentinel2":
                            p["SUN_ELEVATION"] = sentinel_sun_elevation(solar)
                    payload = json.dumps(response, ensure_ascii=False, separators=(",", ":")).encode()
                    temp = raw_path.with_name(raw_path.name + ".pending")
                    with temp.open("wb") as stream:
                        stream.write(payload)
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.replace(temp, raw_path)
                    record.update({"status": "success", "raw_response": raw_path.name, "received_count": count,
                                   "sha256": hashlib.sha256(payload).hexdigest(), "size_bytes": len(payload),
                                   "completed_utc": datetime.now(timezone.utc).isoformat()})
                    atomic_json(status_path, record)
                    indexed[key] = record
                    manifest["parts"] = list(indexed.values())
                    manifest["status"] = "in_progress"
                    atomic_json(manifest_path, manifest)
                    completed_new += 1
                    if completed_new >= max_new_parts:
                        return None
                except Exception as exc:
                    record.update({"status": "failed_stopped", "error": safe_error(exc),
                                   "failed_utc": datetime.now(timezone.utc).isoformat()})
                    atomic_json(status_path, record)
                    manifest.update({"status": "stopped_on_first_error", "failed_part": record})
                    atomic_json(manifest_path, manifest)
                    return False
    manifest.update({"status": "complete", "completed_utc": datetime.now(timezone.utc).isoformat(),
                     "script_sha256": sha256(Path(__file__))})
    atomic_json(manifest_path, manifest)
    return True


def main():
    if not PROJECT:
        raise ValueError("Set KHZ_INVENTORY_EE_PROJECT in the local environment")
    scope = local_region()
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    resume = os.environ.get("KHZ_INVENTORY_RUN_ID")
    if resume:
        run_id = resume
        directory = OUT_ROOT / run_id
        if not directory.is_dir():
            raise FileNotFoundError("Requested checkpoint directory does not exist")
        common = json.loads((directory / "run_manifest_private.json").read_text(encoding="utf-8"))
        if (common.get("roi", {}).get("sha256") != sha256(BOUNDARY)
                or common.get("date_interval") != {"start_inclusive": START.isoformat(), "end_exclusive": END.isoformat()}):
            raise ValueError("Checkpoint scope does not match the fixed Khuzestan inventory")
    else:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        directory = OUT_ROOT / run_id
        directory.mkdir(exist_ok=False)
    common_path = directory / "run_manifest_private.json"
    if resume:
        common = json.loads(common_path.read_text(encoding="utf-8"))
        common.update({"status": "preflight_passed", "resume_started_utc": datetime.now(timezone.utc).isoformat(),
                       "resume_script_sha256": sha256(Path(__file__))})
    else:
        common = {"run_id": run_id, "status": "preflight_passed", "project": PROJECT,
                  "roi": {"source": str(BOUNDARY.relative_to(ROOT)), "validation": str(BOUNDARY_REPORT.relative_to(ROOT)),
                          "sha256": sha256(BOUNDARY), "crs": "EPSG:4326", "country": "Iran", "province": "Khuzestan"},
                  "date_interval": {"start_inclusive": START.isoformat(), "end_exclusive": END.isoformat()},
                  "partitioning": "calendar months; Landsat T1/T2 separately; daytime and missing-solar separately",
                  "cloud_threshold_percent": None, "automatic_retry": False,
                  "pixel_sample_thumbnail_download_export_mosaic": False,
                  "script_sha256": sha256(Path(__file__)), "created_utc": datetime.now(timezone.utc).isoformat()}
    atomic_json(common_path, common)
    try:
        import ee
        ee.Initialize(project=PROJECT)
    except Exception as exc:
        common.update({"status": "stopped_on_initialization_error", "error": safe_error(exc),
                       "failed_utc": datetime.now(timezone.utc).isoformat()})
        atomic_json(directory / "run_manifest_private.json", common)
        print(f"Earth Engine initialization failed: {type(exc).__name__}; local checkpoints retained.")
        return 2
    region = ee.Geometry(scope, proj="EPSG:4326", geodesic=False)
    max_new_parts = int(os.environ.get("KHZ_INVENTORY_MAX_PARTS", "1"))
    if max_new_parts < 1:
        raise ValueError("KHZ_INVENTORY_MAX_PARTS must be positive")
    for sensor, collections in (("landsat", LANDSAT), ("sentinel2", SENTINEL)):
        result = run_sensor(ee, sensor, collections, region, directory, max_new_parts)
        if result is False:
            common.update({"status": "stopped_on_first_error", "stopped_sensor": sensor,
                           "updated_utc": datetime.now(timezone.utc).isoformat()})
            atomic_json(directory / "run_manifest_private.json", common)
            return 2
        sensor_manifest = directory / sensor / "manifest_private.json"
        if result is None:
            common.update({"status": "checkpoint_saved", "updated_utc": datetime.now(timezone.utc).isoformat()})
            atomic_json(directory / "run_manifest_private.json", common)
            return 0
        if not sensor_manifest.exists() or json.loads(sensor_manifest.read_text(encoding="utf-8")).get("status") != "complete":
            common.update({"status": "checkpoint_saved", "updated_utc": datetime.now(timezone.utc).isoformat()})
            atomic_json(directory / "run_manifest_private.json", common)
            return 0
    common.update({"status": "complete", "completed_utc": datetime.now(timezone.utc).isoformat()})
    atomic_json(directory / "run_manifest_private.json", common)
    return 0


if __name__ == "__main__":
    sys.exit(main())
