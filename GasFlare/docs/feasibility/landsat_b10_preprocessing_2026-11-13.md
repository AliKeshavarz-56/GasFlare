# B10 Preprocessing for the Two Selected Samples

Date: 2026-11-13. Offline implementation and metadata review only; this work made no Earth Engine or other online request.

## Roadmap Alignment

This bounded task is within roadmap Phase 2, physical preprocessing and labeling: convert Level-1 scaled B10 DN to spectral radiance and sensor-equivalent brightness temperature. The roadmap remains unchanged. The present output is not a labeling or flare-detection result.

## Exact-Product Metadata Review

The selected products are `LC08_L1GT_032205_20250107_20250121_02_T2` and `LC09_L1TP_032205_20250115_20250115_02_T2`. `landsat_owner_boundary_inventory_2025.json` retains all four B10 coefficients for both exact product IDs. The metadata includes:

| Product | ML | AL | K1 | K2 |
| --- | ---: | ---: | ---: | ---: |
| LC08 selected product | 0.0003342 | 0.1 | 774.8853 | 1321.0789 |
| LC09 selected product | 0.00038 | 0.1 | 799.0284 | 1329.2405 |

Coefficient names are `RADIANCE_MULT_BAND_10`, `RADIANCE_ADD_BAND_10`, `K1_CONSTANT_BAND_10`, and `K2_CONSTANT_BAND_10`, respectively. This retained inventory metadata is for these exact products and is not used as a substitute for missing pixel data. Reviewed local artifacts do not contain the paired 9x9 B10/QA arrays and their per-band masks. Consequently no sample conversion, sample statistics, or plot is claimed as generated.

## Implemented Processing Contract

For each unmasked sample, radiance is `ML * DN + AL` (Level-1 B10 radiance, W/(m^2 sr um)); non-finite or non-positive radiance rejects processing. Brightness temperature is `K2 / ln(1 + K1 / radiance)` in kelvin. Masked inputs remain `None` in both derived matrices and are excluded from summaries. The summary reports count, min, max, mean, and explicit unit. A mean DN is never converted and called mean temperature. Celsius is not emitted.

The preprocessing function refuses missing, non-finite, or invalid coefficients and does not provide defaults. Brightness temperature is a sensor-equivalent temperature, not land-surface temperature or actual flare temperature. Existing QA does not confirm or rule out per-pixel B10 saturation. No background suitability or flare-detection claim is made from these windows, and no raw thermal comparison between scenes is conclusive.

## Bounded Acquisition After User Review

The exact command from the actual repository root (`D:\UN\Term1\project\GasFlare`), to be run only after user review/authorization, is:

```powershell
python GasFlare/scripts/gee/acquire_landsat_b10_samples_2025.py
```

It uses the existing deterministic selected pair and coordinates, inspects each exact product, then requests exactly one 9x9 grid per product containing B10, QA_PIXEL, QA_RADSAT and the corresponding masks. Exact asset properties and product IDs are verified before saving a compressed local NPZ with a metadata manifest. It does not search collections, export scenes, retry, or change samples. Output path `GasFlare/data/derived/landsat/restricted_b10_samples_2025.npz` is ignored by Git. The command was not run in this task.

After that local acquisition, the saved samples can be passed through the offline `preprocess_b10()` and `matrix_summary()` functions; plots must use fixed, labeled units/scales, preserve masked cells, and clearly label B10 DN versus brightness temperature (K). Those per-sample tables and 9x9 visualizations remain ungenerated until the real pixel arrays are available.

## Earth Engine Code Editor Template

`GasFlare/scripts/gee/landsat_b10_two_samples_template.js` is a tracked, coordinate-free visualization template for the two exact samples selected by `select_pairs()`: `LC08_L1GT_032205_20250107_20250121_02_T2` and `LC09_L1GT_032205_20250216_20250216_02_T2`. These differ from the LC09 product reported in an earlier diagnostic summary; the latter is not the deterministic selection made by the current selector. The private `PRIVATE_CONFIG.samples` must be supplied separately and locally with exactly two entries in that order, each providing `label`, `productId`, `assetId`, `coordinates` as `[longitude, latitude]`, and `footprint` as an `ee.Geometry`. The template constructs the point from the coordinates. Do not put coordinates, asset IDs, or derived private configuration into tracked files. The Code Editor cannot read a local config file; use a separate private editor buffer/configuration and paste or insert it locally. No network request was made and the template was not run.

The script reads each exact asset's B10 projection/affine transform, projects the point to that CRS, applies the full inverse affine transform and `floor` to select its containing pixel, and sets the 9x9 origin four rows and columns before it. This matches `pixel_grid()` and the Python `computePixels` window convention, including non-zero shear terms. It checks that B10, QA_PIXEL, and QA_RADSAT share that grid. The displayed valid intersection is the conjunction of the three native per-band masks; raw QA bits are separate, toggleable interpretive layers and do not impose extra masking. Radiance and brightness temperature use exact image properties and the Python equations `ML * DN + AL` and `K2 / ln(1 + K1 / radiance)`; non-positive radiance is masked. Layer display ranges only control visualization, not pixel values. Layers can be toggled independently; exact product time and coefficients are printed in the Console.

This is an interactive visualization, not an export or saved 9x9 numerical archive. Do not infer per-pixel B10 saturation from QA_RADSAT: its bit 9 is dropped-pixel status, and Landsat 8/9 Collection 2 QA_RADSAT has no B10 saturation bit. `SATURATION_BAND_10`, when present, is scene-level metadata. The output is sensor-equivalent brightness temperature, not land-surface or flare temperature; windows do not establish background suitability or flare detection. Coordinates and asset identifiers remain sensitive local configuration and must not be published with screenshots or scripts.

For a separate offline-only processing run after acquisition, use:

```powershell
python GasFlare/scripts/gee/acquire_landsat_b10_samples_2025.py --process-saved
```

That command reads only the existing local archive (it does not initialize Earth Engine) and writes the restricted statistics JSON and one labeled 9x9 PNG per sample beside the archive. Files are covered by the same local-artifact ignore rule.

## Local Metadata: Daytime Candidate Status

The existing Tier 1 inventory is province-wide aggregate metadata and representative examples, not a complete same-point daytime scene match. It reports 178 LC08 and 176 LC09 Tier 1 images with positive scene-center sun elevation, but does not provide a daytime product ID, timestamp, processing level, point-specific footprint test, valid mask, or QA evidence for these two samples. The saved point intersection table covers the selected night-scene footprints only. Therefore a suitable daytime image cannot be selected or assumed from the metadata currently available; no new query or sample expansion was performed.

## Acquisition Guardrails

The acquisition validates row-4 provenance, candidate ID/year, inside-footprint relation, and both exact asset/product IDs before initializing Earth Engine. It requests one 9x9 window from each asset and stores B10, QA_PIXEL, QA_RADSAT, per-band masks, CRS, and affine transforms. It refuses to overwrite archive or derivative outputs. World Bank candidate/intersection files, restricted sample artifacts, and private visualization configuration are ignored at the repository root. QA bit layers remain interpretive: native mask validity is not a cloud-free/quality determination.
