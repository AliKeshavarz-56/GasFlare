# TASK-003-A-R1: Product Semantics Resolution

Date: 2026-11-13. This addendum supplements, and does not replace, `landsat_night_pixel_diagnostic_2026-11-13.md`. The two selected pairs and candidate row 4 are unchanged.

## Resolution

The earlier report's Level-2 interpretation was an implementation/reporting error, not a property of either selected asset. In `LANDSAT/LC08/C02/T2` and `LANDSAT/LC09/C02/T2`, `T2` denotes Collection Tier 2. The accepted metadata run records the exact collection IDs and product IDs ending in `_02_T2`. The selected products are `LC08_L1GT_..._02_T2` and `LC09_L1TP_..._02_T2`: both are Collection 2 Tier 2 Level-1 products. `L1GT` is Level-1 Systematic Terrain; `L1TP` is Level-1 Precision and Terrain. This distinction is also explicit in USGS's Collection 2 Level-1 and Levels of Processing pages.

The prior report incorrectly treated the `/T2` collection suffix as a Level-2 product designation, then consulted Level-2 semantics. The references were therefore wrong for the selected assets; the source asset selection was not changed. No automatic substitution to T2_L2, TOA, or another collection was made.

## Official references checked

- Google Earth Engine Data Catalog, LC08 C02 T2: https://developers.google.com/earth-engine/datasets/catalog/LANDSAT_LC08_C02_T2 (HTTP 403 from this environment).
- Google Earth Engine Data Catalog, LC09 C02 T2: https://developers.google.com/earth-engine/datasets/catalog/LANDSAT_LC09_C02_T2 (HTTP 403).
- Google Earth Engine Data Catalog, LC08 C02 T1: https://developers.google.com/earth-engine/datasets/catalog/LANDSAT_LC08_C02_T1 (HTTP 403; checked as an official catalog route, not used to substitute or assert the selected asset's live properties).
- Google Earth Engine Data Catalog, LC09 C02 T1: https://developers.google.com/earth-engine/datasets/catalog/LANDSAT_LC09_C02_T1 (HTTP 403; same limitation).
- USGS, Landsat Collection 2 Level-1 Data: https://www.usgs.gov/landsat-missions/landsat-collection-2-level-1-data. It states Level-1 products are calibrated scaled DN; T1/T2 are collection tiers; Level-1 spectral bands 1-11 include the Landsat 8-9 thermal band; per-scene metadata provides radiometric scaling factors.
- USGS, Landsat Levels of Processing: https://www.usgs.gov/landsat-missions/landsat-levels-processing. It defines L1TP and L1GT and describes their different geometric correction levels.
- USGS, Landsat Collection 2 Quality Assessment Bands: https://www.usgs.gov/landsat-missions/landsat-collection-2-quality-assessment-bands. QA_PIXEL bits 0-5 and QA_RADSAT assignments are documented for L8/9; QA_PIXEL and QA_RADSAT are Level-1 bands carried unchanged into Level-2.
- USGS, Landsat 8-9 OLI/TIRS Collection 2 Level-1 Data Format Control Book, v7, March 25, 2025: https://www.usgs.gov/media/files/landsat-8-9-olitirs-collection-2-level-1-data-format-control-book. Official PDF: https://d9-wret.s3.us-west-2.amazonaws.com/assets/palladium/production/s3fs-public/media/files/LSDS-1822_Landsat8-9-OLI-TIRS_C2_L1_DataFormatControlBook-v7.pdf.

## B10, QA, and grid interpretation

For Collection 2 Level-1, B10 is the Landsat 8/9 TIRS thermal spectral band delivered as scaled unsigned 16-bit DN. Conversion to radiance requires the scene's own `RADIANCE_MULT_BAND_10` and `RADIANCE_ADD_BAND_10` metadata; conversion to TOA brightness temperature additionally requires that scene's `K1_CONSTANT_BAND_10` and `K2_CONSTANT_BAND_10`. No numerical coefficient is borrowed from another product. The selected metadata record saved in the accepted run includes neither these coefficients nor band definitions or projection transforms, so no conversion or stored-value unit claim beyond Level-1 scaled DN was applied.

USGS defines QA_PIXEL bits 0-5 as fill, dilated cloud, cirrus, cloud, cloud shadow, and snow for L8/9. In QA_RADSAT, L8/9 bit 9 is dropped pixel and bits 7, 10, and 12-15 are unused; the table does not define a B10 saturation flag. Scene-level `SATURATION_BAND_10`, if present, is not a per-pixel saturation count. The previous Level-1 preview is consistent with these documented QA semantics but does not establish the selected assets' actual band mask or projection.

The required sampling grid is each selected asset's actual B10 projection and affine transform. The prior metadata retrieval recorded scene metadata and vector footprints only. It did not inspect image band types, B10 projection/transform, masks, or image pixels. A direct authenticated-runtime metadata inspection was attempted, but `ee.Initialize()` failed fetching the Earth Engine discovery document with HTTP 403 before either asset was queried. Thus no image access request or pixel request was made; the documentation/catalog 403 and this API discovery 403 are distinct access failures. Processing dependent on actual asset properties is stopped rather than inferred.

## Execution and tests

The diagnostic now labels and validates the selected collections as the exact requested C02/T2 collections and validates that both selected product IDs are Level-1 `_02_T2`; pair selection remains deterministic and unchanged. The `--live` path remains fail-closed with an accurate reason: live asset band/projection inspection is not implemented, and no request is sent. The offline plan is not a pixel test.

Synthetic tests and the existing screening regression are to be reported separately from live execution. For this revision, live pixel requests: **0**. LC08 selected pair: product semantics resolved to Level-1 L1GT / Tier 2, pixel result not run. LC09 selected pair: product semantics resolved to Level-1 L1TP / Tier 2, pixel result not run. No replacement pairs, exports, footprint refetch, preview changes, flare detection, or model training occurred.

The remaining blocker is specifically authorized access to the Earth Engine API discovery endpoint and live inspection of each exact selected asset's band names/types, B10 projection and affine transform, masks, and scene-specific radiometric coefficients/metadata. No image-access request was made, so no image permission failure was observed. Documentation-page HTTP 403 is a documentation-fetch failure, not an image-access error.
