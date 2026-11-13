"""One-shot, bounded Earth Engine acquisition for the two selected B10 windows.

Run only after reviewing and explicitly authorizing this command. Outputs are
restricted local artifacts and must not be committed.
"""

import json
from pathlib import Path

import ee
import numpy as np

from landsat_night_pixel_diagnostic_2025 import (
    DiagnosticError, matrix_summary, pixel_grid, preprocess_b10, select_pairs, validate_asset_info,
)


OUTPUT = Path(__file__).resolve().parents[2] / "data" / "derived" / "landsat" / "restricted_b10_samples_2025.npz"
PROJECT = "indigo-bloom-501712-p0"
BANDS = ("B10", "QA_PIXEL", "QA_RADSAT")
COEFFICIENTS = ("RADIANCE_MULT_BAND_10", "RADIANCE_ADD_BAND_10", "K1_CONSTANT_BAND_10", "K2_CONSTANT_BAND_10")


def main():
    selected = select_pairs()
    ee.Initialize(project=PROJECT)
    archive = {}
    manifest = {"purpose": "two exact 9x9 B10 samples", "samples": []}
    for index, row in enumerate(selected):
        asset = ee.Image(row["asset_id"])
        info = asset.getInfo()
        spec = validate_asset_info(info)
        props = info.get("properties", {})
        if props.get("LANDSAT_PRODUCT_ID") != row["footprint_product_id"]:
            raise DiagnosticError("asset product ID does not match saved selected pair")
        coefficients = {key: props.get(key) for key in COEFFICIENTS}
        if any(value is None for value in coefficients.values()):
            raise DiagnosticError("exact-product B10 coefficients are missing")
        grid = pixel_grid(float(row["longitude"]), float(row["latitude"]), spec["transform"], spec["projection"])
        expression = asset.select(list(BANDS)).addBands(asset.select(list(BANDS)).mask().rename(["mask_" + name for name in BANDS]))
        payload = ee.data.computePixels({
            "expression": expression, "fileFormat": "NUMPY_NDARRAY",
            "grid": {"dimensions": {"width": 9, "height": 9}, "affineTransform": {
                "scaleX": grid[0], "shearX": grid[1], "translateX": grid[2],
                "shearY": grid[3], "scaleY": grid[4], "translateY": grid[5]}, "crsCode": spec["projection"]},
        })
        if getattr(getattr(payload, "dtype", None), "names", None) is None:
            raise DiagnosticError("pixel response is not a structured NumPy array")
        for name in BANDS:
            for prefix, field in (("value", name), ("mask", "mask_" + name)):
                if field not in payload.dtype.names or payload[field].shape != (9, 9):
                    raise DiagnosticError("pixel response lacks expected 9x9 field: " + field)
                archive[f"{index}_{prefix}_{name}"] = payload[field]
        manifest["samples"].append({
            "product_id": props["LANDSAT_PRODUCT_ID"], "asset_id": row["asset_id"],
            "collection": row["collection"], "projection": spec["projection"],
            "transform": spec["transform"], "sample_transform": grid,
            "coefficients": coefficients, "coefficient_source": "exact asset properties",
            "window": [9, 9], "band_masks_saved": True,
        })
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    archive["manifest_json"] = np.array(json.dumps(manifest, sort_keys=True))
    np.savez_compressed(OUTPUT, **archive)
    print(f"Saved two restricted 9x9 samples to {OUTPUT}")


def process_saved():
    """Offline conversion and per-sample PNG/JSON outputs from the saved NPZ."""
    import matplotlib.pyplot as plt

    if not OUTPUT.is_file():
        raise DiagnosticError(f"missing local sample archive: {OUTPUT}")
    with np.load(OUTPUT, allow_pickle=False) as saved:
        manifest = json.loads(str(saved["manifest_json"].item()))
        result = {"samples": []}
        figure_paths = []
        for index, sample in enumerate(manifest["samples"]):
            dn = saved[f"{index}_value_B10"]
            masks = {name: saved[f"{index}_mask_{name}"] != 0 for name in BANDS}
            valid = masks["B10"] & masks["QA_PIXEL"] & masks["QA_RADSAT"]
            converted = preprocess_b10(dn.tolist(), valid.tolist(), sample["coefficients"])
            result["samples"].append({
                "product_id": sample["product_id"], "coefficients": sample["coefficients"],
                "total_pixels": 81, "valid_pixels": int(valid.sum()),
                "B10_DN": matrix_summary(dn.tolist(), valid.tolist(), "scaled Level-1 DN"),
                "radiance": matrix_summary(converted["radiance"], converted["valid_mask"], "W/(m^2 sr um)"),
                "brightness_temperature": matrix_summary(converted["brightness_temperature_k"], converted["valid_mask"], "K"),
                "qa_radsat_b10_saturation": "unknown",
            })
            fig, axes = plt.subplots(1, 2, figsize=(8, 4), constrained_layout=True)
            for ax, matrix, title, unit in (
                (axes[0], dn.astype(float), "B10 scaled Level-1 DN", "DN"),
                (axes[1], np.asarray(converted["brightness_temperature_k"], dtype=float), "Brightness temperature", "K"),
            ):
                shown = np.ma.array(matrix, mask=~valid)
                image = ax.imshow(shown, cmap="inferno", interpolation="nearest")
                ax.set_title(title)
                ax.set_xlabel("Column (9x9 window)")
                ax.set_ylabel("Row (9x9 window)")
                fig.colorbar(image, ax=ax, label=unit)
            fig.suptitle(sample["product_id"])
            figure_path = OUTPUT.with_name(f"restricted_b10_sample_{index + 1}.png")
            fig.savefig(figure_path, dpi=160)
            figure_paths.append(figure_path)
            plt.close(fig)
    report_path = OUTPUT.with_name("restricted_b10_sample_statistics.json")
    report_path.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
    print(f"Saved local per-sample statistics to {report_path}")
    for figure_path in figure_paths:
        print(f"Saved local 9x9 visualization to {figure_path}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--process-saved", action="store_true", help="process the existing local sample archive without network access")
    args = parser.parse_args()
    process_saved() if args.process_saved else main()
