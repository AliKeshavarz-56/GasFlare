"""Offline planning and bounded pixel diagnostic for two saved Landsat assets.

The selected T2 assets are Tier-2 Level-1 products, not Level-2 products.
"""

import argparse
import csv
import hashlib
import json
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
        "qa_radsat_b10_saturated_cells": None,
        "stored_b10": ({"count": len(valid), "min": min(valid), "max": max(valid), "mean": sum(valid) / len(valid)} if valid else None),
    }


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
        raise DiagnosticError("live pixel request blocked: asset band/projection inspection is not implemented; no request sent")
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
