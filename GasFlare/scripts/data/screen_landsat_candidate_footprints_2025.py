"""Screen 2025 flare candidates against saved Landsat scene footprints."""

import argparse
import csv
import hashlib
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

from shapely.geometry import Point, shape


ROOT = Path(__file__).resolve().parents[2]
INPUT = ROOT.parent / "data" / "derived" / "worldbank" / "khuzestan_flare_candidates_2025.csv"
FOOTPRINTS = ROOT / "data" / "derived" / "landsat" / "metadata_runs" / "20261113T083518397766Z-30c3f6be" / "metadata.geojson"
OUTPUT_ROOT = ROOT / "data" / "derived" / "worldbank"
EXPECTED_INPUT_SHA256 = "207f8a827e63e495903529805acf991390b1a0b4cfc2722e3e87bed35bede491"
EXPECTED_ROWS = 201
EXPECTED_YEAR = "2025"
SATELLITES = ("LC08", "LC09")
PAIR_FIELDS = ("candidate_id", "candidate_row_number", "longitude", "latitude", "year",
               "footprint_product_id", "collection", "asset_id", "relationship")
SUMMARY_FIELDS = ("candidate_id", "candidate_row_number", "longitude", "latitude", "year",
                  "match_count", "matched_lc08", "matched_lc09", "status")


class ScreeningError(ValueError):
    """Raised when an input fails a screening precondition."""


def load_candidates(path=INPUT):
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != EXPECTED_INPUT_SHA256:
        raise ScreeningError(f"candidate CSV SHA-256 mismatch: {digest}")
    with path.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {"id", "lat", "lon", "Year", "spatial_status", "crs_assumption"}
        missing = sorted(required - set(reader.fieldnames or ()))
        if missing:
            raise ScreeningError(f"candidate CSV missing columns: {', '.join(missing)}")
        rows = []
        for row_number, row in enumerate(reader, 1):
            if row["Year"].strip() != EXPECTED_YEAR:
                raise ScreeningError(f"candidate row {row_number} has year {row['Year']!r}, expected 2025")
            try:
                longitude, latitude = float(row["lon"]), float(row["lat"])
            except (TypeError, ValueError):
                raise ScreeningError(f"candidate row {row_number} has nonnumeric coordinates") from None
            if not math.isfinite(longitude) or not math.isfinite(latitude):
                raise ScreeningError(f"candidate row {row_number} has non-finite coordinates")
            if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
                raise ScreeningError(f"candidate row {row_number} has out-of-range coordinates")
            rows.append({"candidate_id": row["id"], "candidate_row_number": row_number,
                         "longitude": longitude, "latitude": latitude, "year": row["Year"].strip(),
                         "spatial_status": row["spatial_status"], "crs_assumption": row["crs_assumption"]})
    if len(rows) != EXPECTED_ROWS:
        raise ScreeningError(f"candidate CSV row count is {len(rows)}, expected {EXPECTED_ROWS}")
    return rows


def load_footprints(path=FOOTPRINTS):
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("type") != "FeatureCollection" or not isinstance(data.get("features"), list):
        raise ScreeningError("footprints must be a GeoJSON FeatureCollection")
    footprints = []
    for index, feature in enumerate(data["features"], 1):
        if not isinstance(feature, dict) or feature.get("type") != "Feature" or not isinstance(feature.get("properties"), dict):
            raise ScreeningError(f"footprint feature {index} is not a valid GeoJSON Feature")
        properties = feature["properties"]
        product_id, collection = properties.get("LANDSAT_PRODUCT_ID"), properties.get("collection")
        satellite = next((value for value in SATELLITES if isinstance(collection, str) and collection.startswith(f"LANDSAT/{value}/")), None)
        if satellite is None or not isinstance(product_id, str) or not product_id.startswith(satellite + "_"):
            raise ScreeningError(f"footprint feature {index} has unsupported or inconsistent collection/product ID")
        try:
            geometry = shape(feature.get("geometry"))
        except Exception as exc:
            raise ScreeningError(f"footprint feature {index} geometry cannot be parsed: {exc}") from exc
        if geometry.geom_type not in {"Polygon", "MultiPolygon"} or geometry.is_empty or not geometry.is_valid:
            raise ScreeningError(f"footprint feature {index} has empty, invalid, or non-polygon geometry")
        if not all(math.isfinite(value) for value in geometry.bounds):
            raise ScreeningError(f"footprint feature {index} has non-finite bounds")
        footprints.append({"geometry": geometry, "product_id": product_id, "collection": collection,
                           "asset_id": properties.get("asset_id", ""), "satellite": satellite})
    return footprints, data.get("crs")


def screen(candidates, footprints):
    pairs = []
    summary = []
    for candidate in candidates:
        point = Point(candidate["longitude"], candidate["latitude"])
        candidate_pairs = []
        for footprint in footprints:
            geometry = footprint["geometry"]
            if geometry.contains(point):
                relation = "inside"
            elif geometry.touches(point):
                relation = "on_boundary"
            else:
                continue
            candidate_pairs.append({**{key: candidate[key] for key in SUMMARY_FIELDS[:5]}, "footprint_product_id": footprint["product_id"],
                                    "collection": footprint["collection"], "asset_id": footprint["asset_id"],
                                    "relationship": relation})
        pairs.extend(candidate_pairs)
        counts = Counter(pair["collection"].split("/")[1] for pair in candidate_pairs)
        summary.append({**{key: candidate[key] for key in SUMMARY_FIELDS[:5]}, "match_count": len(candidate_pairs),
                        "matched_lc08": counts["LC08"], "matched_lc09": counts["LC09"],
                        "status": "matched" if candidate_pairs else "unmatched"})
    pairs.sort(key=lambda row: (row["candidate_row_number"], row["collection"], row["footprint_product_id"]))
    return pairs, summary


def write_csv(path, rows, fields):
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=INPUT)
    parser.add_argument("--footprints", type=Path, default=FOOTPRINTS)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_ROOT)
    args = parser.parse_args(argv)
    try:
        candidates = load_candidates(args.input)
        footprints, crs = load_footprints(args.footprints)
    except (OSError, json.JSONDecodeError, ScreeningError) as exc:
        print(f"precheck failed: {exc}", file=sys.stderr)
        return 2
    ids = Counter(row["candidate_id"] for row in candidates)
    duplicates = {key: count for key, count in sorted(ids.items()) if count > 1}
    print(json.dumps({"candidate_rows": len(candidates), "duplicate_candidate_ids": duplicates,
                      "spatial_status": dict(Counter(row["spatial_status"] for row in candidates)),
                      "crs_assumption": dict(Counter(row["crs_assumption"] for row in candidates))}, sort_keys=True))
    pair_path = args.output_dir / "khuzestan_candidate_scene_intersections_2025.csv"
    summary_path = args.output_dir / "khuzestan_candidate_scene_summary_2025.csv"
    if pair_path.exists() or summary_path.exists():
        print("output already exists; refusing to overwrite", file=sys.stderr)
        return 2
    pairs, summary = screen(candidates, footprints)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(pair_path, pairs, PAIR_FIELDS)
    write_csv(summary_path, summary, SUMMARY_FIELDS)
    status_counts = Counter(row["status"] for row in summary)
    satellite_counts = Counter(row["collection"].split("/")[1] for row in footprints)
    print(json.dumps({"candidate_rows": len(candidates), "footprint_features": len(footprints),
                      "footprint_crs": crs, "footprint_collection_counts": dict(sorted(satellite_counts.items())),
                      "duplicate_candidate_ids": duplicates, "pair_count": len(pairs),
                      "candidate_status_counts": dict(sorted(status_counts.items())),
                      "output_dir": str(args.output_dir)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
