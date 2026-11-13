# TASK-003-A: Offline Review of User-Reported Pixel Output

Date: 2026-11-13. Offline code and artifact review only; no Earth Engine request or live execution was made.

## User-Reported Result

The user initially reported that a bounded run for each selected pair returned `total_cells=81, valid_cells=0, masked_cells=81, stored_b10=null`, with every reported QA count equal to zero. A subsequent result is also user-reported and was not independently reproduced here:

| Pair | total_cells | valid_cells | masked_cells | B10 min | B10 max | B10 mean |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| First selected pair | 81 | 81 | 0 | 14633 | 16210 | 15348.74074074074 |
| Second selected pair | 81 | 81 | 0 | 19008 | 22242 | 20066.333333333332 |

The user reports zero QA_PIXEL flags and zero dropped cells for both pairs; per-pixel B10 saturation status is unknown (`null`). No radiometric conversion was performed: these are scaled Level-1 DN values. This supports successful access and pixel retrieval for these two pairs and this bounded window only. The changed result after the CRS correction is consistent with the earlier window-placement problem, but absent the historical pixel response and request affine it does not establish that as the definitive historical cause. It does not generalize to whole scenes or demonstrate flare presence/detection. The existing restricted World Bank JSON was not changed.

## Code Findings

- `inspect_window()` defines a cell as valid when all three returned per-band masks (`B10`, `QA_PIXEL`, and `QA_RADSAT`) are true. It does not infer validity from a B10 value, a zero/default, or QA flags. B10 summary values are selected only after this mask intersection. Thus zero valid cells means either the returned B10 mask was false everywhere, a required QA mask was false everywhere, or a response/mask-band issue yielded false masks; the report alone does not distinguish these cases.
- `live_pair_diagnostics()` requests each selected band's mask separately, renames them `mask_B10`, `mask_QA_PIXEL`, and `mask_QA_RADSAT`, and reads those returned fields. No `unmask()` or fill/default operation appears in this diagnostic path. The zero QA summary is computed over cells where the respective QA mask is true, so all-zero QA flags are consistent with genuinely zero-valued QA data. They do not establish this without verifying the returned QA mask and raw QA samples; if its mask were false across the window, the count routine would also report zero counts.
- The selected sample is retained unchanged: candidate `m_348`, row 4, longitude `48.95294797`, latitude `31.20950528` for both saved pairs. Their saved pair-table relationship is `inside` the recorded scene footprint, but that footprint test is not proof of coverage in the image's valid-data mask.
- Before this review, `pixel_grid()` treated those degree-valued longitude/latitude coordinates as if they were in the B10 UTM CRS. That is a definite coordinate-space bug. The 9x9 transform is constructed by taking the containing pixel (`floor` of the affine inverse) and centering a 9x9 grid on it; it preserves the input affine's scale/shear and applies a four-pixel offset. The request passes width and height 9 and uses `spec["projection"]` as CRS. The grid cell order is NumPy row-major (`y`, then `x`) and the affine's negative Y scale is respected.
- The asset CRS and affine transform were not saved in the restricted artifact, so their actual values, alignment, and correspondence to the selected point cannot be established offline. The source code does validate that the live required bands share the B10 grid before requesting pixels.

## Correction and Offline Tests

The grid builder now transforms the saved WGS84 longitude/latitude into the inspected asset CRS using `pyproj` with `always_xy=True` before applying the B10 affine inverse. This keeps the same sample and 9x9 size; it does not move the selected point. Offline tests cover the all-masked case, mixed per-band validity, zero-valued B10 in a valid cell, and zero QA flags under a valid QA mask.

## Certainty and Limits

The coordinate-space mismatch in the previous code is certain and corrected. The direct-mask logic and lack of default/unmask substitution are certain from the inspected source. The user's all-masked result and QA zeros are recorded as reported, but the actual cause is not identified: no captured response array, asset CRS/transform, mask values, or QA samples are available for offline inspection. Night-time acquisition is not a demonstrated cause and is not presumed to explain the complete masking.

## Offline Radiometric Assessment Plan

No conversion was implemented or run. The exact pair semantics are documented in `landsat_night_pixel_diagnostic_resolution_2026-11-13.md`: `LANDSAT/LC08/C02/T2` and `LANDSAT/LC09/C02/T2` are Collection 2 Tier 2 collections, and the selected products are Level-1 (`LC08_L1GT_..._02_T2` and `LC09_L1TP_..._02_T2`), not Level-2. L1GT means Systematic Terrain; L1TP means Precision and Terrain.

The bounded next assessment should remain offline and:

- Reconcile each exact selected product ID against retained pair-selection records and product metadata, recording spacecraft, processing level, collection tier, and processing category independently. Do not infer exact-product coefficients from another scene or from a different collection.
- Locate the exact products' retained MTL metadata, if available, and verify `RADIANCE_MULT_BAND_10`, `RADIANCE_ADD_BAND_10`, `K1_CONSTANT_BAND_10`, and `K2_CONSTANT_BAND_10` separately for each. The method to assess is `L = ML * DN + AL`, followed by `BT_K = K2 / ln(1 + K1 / L)` for positive radiance, using the exact scene-specific constants and documenting units. Coefficients found in other inventory products are not substitutes. Current selected-pair records do not establish that these four coefficients are retained for the exact products; retrieve no online metadata in this phase.
- Explain that TOA brightness temperature is a sensor-equivalent blackbody temperature derived from at-sensor radiance under the Planck conversion. It is not land-surface temperature, which needs surface/emissivity and atmospheric treatment, and is not actual flare temperature, which is not directly inferred from these measurements.
- Check official L8/L9 Collection 2 QA_RADSAT bit definitions against the exact product generation. Existing reviewed USGS documentation assigns no per-pixel B10 saturation bit for L8/L9; bit 9 denotes dropped pixel, and scene-level `SATURATION_BAND_10` is not a per-pixel flag. Thus the reported `null` remains unknown, not unsaturated. Any claim of B10 saturation assessment needs product-specific supporting evidence beyond QA_RADSAT.
- Inventory evidence and gaps before proposing any bounded follow-up: the reported 9x9 DN summaries, QA flag counts, pair IDs and resolved Level-1 semantics are available. Exact-product MTL coefficients, raw paired samples with masks, historical request affine/asset projection, and per-pixel B10 saturation evidence are absent from the reviewed artifacts. If exact MTLs are not retained locally, radiometric conversion must wait for separately authorized acquisition of only those two products' metadata; no values should be guessed or borrowed.

If a live request is later authorized, the minimal pixel validation remains the same exact selected assets and unchanged point/window, reporting only the inspected B10 CRS/affine and derived request affine, per-band mask counts for the existing 9x9 window, and a few paired raw B10/QA values with their masks. Do not unmask, replace samples, expand the window, export data, threshold, or detect flares. No such request was made for this task.
