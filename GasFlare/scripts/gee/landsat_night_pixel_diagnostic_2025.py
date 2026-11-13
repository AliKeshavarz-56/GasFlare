"""Offline planning and bounded pixel diagnostic for two saved Landsat assets.

The selected T2 assets are Tier-2 Level-1 products, not Level-2 products.
"""

import argparse
import csv
import hashlib
import io
import json
import math
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = ROOT.parent
PAIR_TABLE = ROOT / "data" / "derived" / "worldbank" / "khuzestan_candidate_scene_intersections_2025.csv"
CANDIDATES = PROJECT_ROOT / "data" / "derived" / "worldbank" / "khuzestan_flare_candidates_2025.csv"
RUN = ROOT / "data" / "derived" / "landsat" / "metadata_runs" / "20261113T083518397766Z-30c3f6be"
INPUTS = {
    "candidate_csv": CANDIDATES,
    "pair_table": PAIR_TABLE,
    "audit_csv": RUN / "audit.csv",
    "metadata_geojson": RUN / "metadata.geojson",
    "manifest": RUN / "manifest.json",
}
SATELLITES = ("LC08", "LC09")
WINDOW = 9
REQUIRED_BANDS = ("B10", "QA_PIXEL", "QA_RADSAT")
QA_PIXEL_BITS = {"fill": 0, "dilated_cloud": 1, "cirrus": 2, "cloud": 3, "cloud_shadow": 4, "snow": 5}
QA_RADSAT_DROPPED_BIT = 9
COLLECTIONS = {"LC08": "LANDSAT/LC08/C02/T2", "LC09": "LANDSAT/LC09/C02/T2"}


class DiagnosticError(ValueError):
    pass


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def select_pairs(pair_path=PAIR_TABLE, candidate_path=CANDIDATES):
    with candidate_path.open(encoding="utf-8-sig", newline="") as stream:
        candidates = list(csv.DictReader(stream))
    if len(candidates) != 201:
        raise DiagnosticError("candidate row count mismatch")
    with pair_path.open(encoding="utf-8-sig", newline="") as stream:
        pairs = list(csv.DictReader(stream))
    selected = []
    for satellite in SATELLITES:
        eligible = [row for row in pairs if row["collection"].split("/")[1] == satellite]
        if not eligible:
            raise DiagnosticError(f"no pair for {satellite}")
        selected.append(min(eligible, key=lambda row: (int(row["candidate_row_number"]), row["asset_id"], row["footprint_product_id"])))
    if len(selected) != 2 or {row["collection"].split("/")[1] for row in selected} != set(SATELLITES):
        raise DiagnosticError("selection did not yield exactly one pair per satellite")
    for row in selected:
        satellite = row["collection"].split("/")[1]
        if row["collection"] != COLLECTIONS[satellite]:
            raise DiagnosticError(f"unexpected collection for {satellite}: {row['collection']}")
        if "_L1" not in row["footprint_product_id"] or not row["footprint_product_id"].endswith("_02_T2"):
            raise DiagnosticError("selected asset is not the expected Collection 2 Tier 2 Level-1 product")
    return selected


def qa_summary(values):
    counts = {name: 0 for name in QA_PIXEL_BITS}
    for raw in values:
        value = int(raw)
        for name, bit in QA_PIXEL_BITS.items():
            counts[name] += bool(value & (1 << bit))
    return counts


def inspect_window(arrays, band_masks):
    missing = [band for band in REQUIRED_BANDS if band not in arrays]
    if missing:
        raise DiagnosticError("missing required bands: " + ", ".join(missing))
    if any(len(arrays[band]) != WINDOW or any(len(row) != WINDOW for row in arrays[band]) for band in REQUIRED_BANDS):
        raise DiagnosticError("every required band must be exactly 9x9")
    valid_mask = [[all(band_masks[b][y][x] for b in REQUIRED_BANDS) for x in range(WINDOW)] for y in range(WINDOW)]
    valid = [arrays["B10"][y][x] for y in range(WINDOW) for x in range(WINDOW) if valid_mask[y][x]]
    total = WINDOW * WINDOW
    return {
        "total_cells": total,
        "valid_cells": len(valid),
        "masked_cells": total - len(valid),
        "qa_pixel": qa_summary([arrays["QA_PIXEL"][y][x] for y in range(WINDOW) for x in range(WINDOW) if band_masks["QA_PIXEL"][y][x]]),
        "qa_radsat_dropped_cells": sum(bool(int(arrays["QA_RADSAT"][y][x]) & (1 << QA_RADSAT_DROPPED_BIT)) for y in range(WINDOW) for x in range(WINDOW) if band_masks["QA_RADSAT"][y][x]),
        "qa_radsat_b10_saturated_cells": None,
        "stored_b10": ({"count": len(valid), "min": min(valid), "max": max(valid), "mean": sum(valid) / len(valid)} if valid else None),
    }


def validate_asset_info(info):
    bands = {band.get("id"): band for band in info.get("bands", [])}
    missing = [name for name in REQUIRED_BANDS if name not in bands]
    if missing:
        raise DiagnosticError("missing required asset bands: " + ", ".join(missing))
    if bands["B10"].get("data_type", {}).get("precision") != "int":
        raise DiagnosticError("B10 data type is not integer Level-1 DN")
    if any(bands[name].get("data_type", {}).get("precision") != "int" for name in ("QA_PIXEL", "QA_RADSAT")):
        raise DiagnosticError("QA band data type is not integer")
    projection = bands["B10"].get("crs")
    transform = bands["B10"].get("crs_transform")
    if not projection or not isinstance(transform, list) or len(transform) != 6:
        raise DiagnosticError("B10 projection or affine transform is missing")
    try:
        values = [float(value) for value in transform]
    except (TypeError, ValueError):
        raise DiagnosticError("B10 affine transform is invalid")
    determinant = values[0] * values[4] - values[1] * values[3]
    if not all(math.isfinite(value) for value in values) or abs(determinant) < 1e-15:
        raise DiagnosticError("B10 affine transform is invalid")
    pixel_width = math.hypot(values[0], values[3])
    pixel_height = math.hypot(values[1], values[4])
    if projection not in {"EPSG:32638", "EPSG:32639", "EPSG:32640", "EPSG:32641"} or abs(pixel_width - 30) > 0.01 or abs(pixel_height - 30) > 0.01:
        raise DiagnosticError("B10 projection or 30 m grid is incompatible with the diagnostic")
    if any(bands[name].get("crs") != projection or bands[name].get("crs_transform") != transform for name in REQUIRED_BANDS):
        raise DiagnosticError("required bands do not share the B10 projection and transform")
    props = info.get("properties", {})
    coefficients = {key: props.get(key) for key in (
        "RADIANCE_MULT_BAND_10", "RADIANCE_ADD_BAND_10", "K1_CONSTANT_BAND_10", "K2_CONSTANT_BAND_10"
    )}
    return {"projection": projection, "transform": values, "bands": bands, "coefficients": coefficients}


def pixel_grid(longitude, latitude, transform):
    a, b, c, d, e, f = transform
    determinant = a * e - b * d
    dx, dy = longitude - c, latitude - f
    col = math.floor((e * dx - b * dy) / determinant)
    row = math.floor((-d * dx + a * dy) / determinant)
    return [a, b, c + a * (col - WINDOW // 2) + b * (row - WINDOW // 2),
            d, e, f + d * (col - WINDOW // 2) + e * (row - WINDOW // 2)]


def clean_error(exc):
    message = " ".join(str(exc).split())
    if "<html" in message.lower() or "<!doctype" in message.lower():
        status = re.search(r"\bHTTP(?:Error)?\s+(\d{3})\b", message, flags=re.IGNORECASE)
        return f"HTTP {status.group(1)}; response body suppressed" if status else "HTML response body suppressed"
    message = re.sub(r"https?://\S+", "<url-redacted>", message, flags=re.IGNORECASE)
    message = re.sub(r"(?i)(authorization|token|credential|password|secret)(\s*[:=]\s*)\S+", r"\1\2<redacted>", message)
    return message[:240]


def live_pair_diagnostics(selected, ee_api, numpy_api):
    # Complete both metadata inspections before issuing any pixel request.
    inspected = []
    for row in selected:
        asset_id = row["asset_id"]
        info = ee_api.Image(asset_id).getInfo()
        spec = validate_asset_info(info)
        product = info.get("properties", {}).get("LANDSAT_PRODUCT_ID")
        if product != row["footprint_product_id"]:
            raise DiagnosticError("live product metadata does not match saved selection")
        inspected.append((row, spec))

    results = []
    for row, spec in inspected:
        grid = pixel_grid(float(row["longitude"]), float(row["latitude"]), spec["transform"])
        image = ee_api.Image(row["asset_id"])
        expression = image.select(list(REQUIRED_BANDS)).addBands(
            image.select(list(REQUIRED_BANDS)).mask().rename(["mask_" + name for name in REQUIRED_BANDS])
        )
        payload = ee_api.data.computePixels({
            "expression": expression, "fileFormat": "NUMPY_NDARRAY",
            "grid": {"dimensions": {"width": WINDOW, "height": WINDOW}, "affineTransform": {
                "scaleX": grid[0], "shearX": grid[1], "translateX": grid[2],
                "shearY": grid[3], "scaleY": grid[4], "translateY": grid[5]}, "crsCode": spec["projection"]},
        })
        pixels = numpy_api.load(io.BytesIO(payload))
        arrays, masks = {}, {}
        for name in REQUIRED_BANDS:
            if name not in pixels.dtype.names:
                raise DiagnosticError("pixel response is missing required band: " + name)
            plane = pixels[name]
            arrays[name] = plane.tolist()
            masks[name] = (pixels["mask_" + name] != 0).tolist()
        summary = inspect_window(arrays, masks)
        summary["b10_unit"] = "scaled Level-1 DN; no radiometric conversion applied"
        summary["conversion_coefficients_available"] = all(value is not None for value in spec["coefficients"].values())
        summary["radiometric_conversion"] = "not performed; raw scaled DN only"
        summary["qa_radsat_b10_saturated_cells"] = None
        results.append(summary)
    return results


def classify_request(error, valid_cells):
    if error:
        return "request_error"
    return "reviewable_data" if valid_cells else "no_valid_data"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--offline-plan", action="store_true", help="validate hashes and print restricted sample plan")
    parser.add_argument("--live", action="store_true", help="perform bounded Earth Engine request (requires authenticated asset inspection)")
    args = parser.parse_args(argv)
    if args.live:
        import ee
        import numpy as np
        selected = select_pairs()
        try:
            ee.Initialize(project="indigo-bloom-501712-p0")
        except Exception as exc:
            raise DiagnosticError(f"initialization failed ({type(exc).__name__}): {clean_error(exc)}") from None
        try:
            results = live_pair_diagnostics(selected, ee, np)
        except Exception as exc:
            if isinstance(exc, DiagnosticError):
                raise
            raise DiagnosticError(f"live diagnostic failed ({type(exc).__name__}): {clean_error(exc)}") from None
        print(json.dumps({"pairs": results}, sort_keys=True))
        return 0
    if not args.offline_plan:
        parser.error("choose --offline-plan or --live")
    if args.offline_plan:
        for label, path in INPUTS.items():
            if not path.is_file():
                raise DiagnosticError(f"missing input: {label}")
        selected = select_pairs()
        manifest = json.loads(INPUTS["manifest"].read_text(encoding="utf-8"))
        if manifest.get("run_id") != RUN.name:
            raise DiagnosticError("accepted metadata run ID mismatch")
        hashes = {label: sha256(path) for label, path in INPUTS.items()}
        print("Offline plan only: selection and input hashes validated; no pixel request was made.")
        print(json.dumps({"selected_pair_count": len(selected), "candidate_rows": [int(row["candidate_row_number"]) for row in selected], "input_sha256": hashes}, sort_keys=True))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
