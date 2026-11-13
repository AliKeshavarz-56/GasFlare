# Limited Landsat Night Pixel Diagnostic (TASK-003-A)

Date: 2026-11-13. This diagnostic is restricted to the first deterministic candidate-image pair in each of LC08 and LC09, sorted by numeric candidate row, asset ID, then footprint product ID. The offline plan selected two pairs (both candidate row 4). Restricted identifiers and coordinates are recorded only in the local output, not this report.

## Outcome

**Interpretation unresolved; no live pixel request was made.** The saved metadata identifies the selected assets as `LANDSAT/LC08/C02/T2` and `LANDSAT/LC09/C02/T2`. Official Earth Engine catalog pages for both Level-2 collections returned HTTP 403 in this environment. The available Earth Engine catalog knowledge in the existing preview concerns Level-1 and cannot safely be transferred to Level-2. As the exact selected product's B10 band type/units, QA presence, and projection/transform could not be verified from the accessible catalog, the live operation is fail-closed. No substitute pairs were selected.

## Method and limits

The independent tool verifies local input SHA-256 values, selects the two pairs deterministically, and fixes the proposed diagnostic window at 9 by 9 pixels. A live implementation must use the selected asset's B10 native projection and affine transform, not infer cell size from nominal sensor resolution. It must request only B10, QA_PIXEL, QA_RADSAT when present, and required scene metadata; no collection search, export, full-scene download, or automatic retry is allowed.

Synthetic tests cover deterministic selection, a fully masked window, missing required bands, QA_PIXEL bit counting, request errors versus no valid pixels, and stored-value summaries. Masked samples remain absent, never zero-filled. QA_RADSAT B10 saturation meaning is not inferred from Level-1 notes. The reports' valid-data result is not a judgement of image quality or flare presence. No radiance or temperature conversion was made.

Official references consulted on 2026-11-13:

- USGS, *Landsat Collection 2 Quality Assessment Bands*, current webpage. It defines Landsat 8/9 QA_PIXEL bits 0-5 (fill, dilated cloud, cirrus, cloud, shadow, snow) and the QA_RADSAT assignments. https://www.usgs.gov/landsat-missions/landsat-collection-2-quality-assessment-bands
- USGS, *Landsat 8-9 Collection 2 Level 2 Science Product Guide*, v6, posted 2024-05-23. It describes SR, ST, intermediate and QA products; no Level-2 scale or B10 interpretation was applied here. https://www.usgs.gov/media/files/landsat-8-9-collection-2-level-2-science-product-guide
- Earth Engine catalogs requested but inaccessible (HTTP 403): https://developers.google.com/earth-engine/datasets/catalog/LANDSAT_LC08_C02_T2 and https://developers.google.com/earth-engine/datasets/catalog/LANDSAT_LC09_C02_T2.

Runtime versions: Python 3.14.7, earthengine-api 1.7.43, NumPy 2.5.3. Versions are recorded for reproducibility; the live API was not initialized and no request was sent.

## Project tracking

This task records an unresolved diagnostic, not a project-governance approval. TASK-002-B and TASK-002-C remain “آماده بازبینی”. A proposed roadmap refinement is to insert a bounded product-semantics and pixel-access diagnostic before any bulk patch extraction; this is only پیشنهادی and does not approve a change to scope, architecture, labeling, or schedule. The roadmap and historical/boundary files were not edited.
