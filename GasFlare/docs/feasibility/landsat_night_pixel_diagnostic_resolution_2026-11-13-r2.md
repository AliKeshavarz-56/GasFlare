# TASK-003-A-R2: Bounded Live Diagnostic

Date: 2026-11-13. This addendum records the live-path implementation and controlled execution attempt; prior reports remain unchanged.

## Implementation

The prior `--live` branch stopped immediately with a hard-coded message because asset band and projection inspection had not been implemented. The revised path initializes Earth Engine first, then inspects only the two deterministic saved selections (candidate row 4 for each of LC08 and LC09). It validates the live product ID against the saved Level-1 `_02_T2` product, required B10/QA_PIXEL/QA_RADSAT bands, integer DN/QA types, a valid affine transform, the expected 30 m UTM grid, and a shared projection/transform before any pixel request. Both assets must pass inspection before a pixel request is made.

For assets that pass, the path requests only one 9x9 B10-native, point-centered window per asset and includes each required band's mask. It reports valid/masked cells, QA_PIXEL bits 0-5, QA_RADSAT dropped-pixel bit 9, and stored B10 DN summary. No radiometric conversion is implemented; coefficients are inspected for availability but output remains raw scaled DN and no replacement value is synthesized. QA_RADSAT does not define a B10 saturation bit for these products; B10 saturation is therefore reported as unavailable, not inferred. No raw pixel arrays, coordinates, candidate or asset identifiers are printed.

Errors are reduced to stage, exception type, and sanitized message. URLs and HTML response bodies are suppressed to avoid logging credentials or sensitive headers. Discovery/initialization failure exits before asset access; no retry is made.

## Verification

- Runtime: `C:\Users\ali\miniforge3\python.exe`; Python 3.14.7; `earthengine-api` 1.7.43; NumPy 2.5.3.
- Synthetic diagnostic and footprint regression tests: 20 passed.
- `git diff --check`: passed.
- Offline plan: validated exactly two selections and candidate rows `[4, 4]`; this is not a pixel test.

## Controlled Live Attempt

The designated local Python was available, and one `--live` invocation was made using existing authentication and project configuration. Earth Engine initialization/discovery failed with `HttpError`, HTTP 403. The sanitized message is `HTTP 403; response body suppressed`. Execution stopped at initialization; neither asset was inspected, no pixel request was made, and no retry occurred.

| Pair | Initialization | Asset inspection | Pixel retrieval | Interpretation |
| --- | --- | --- | --- | --- |
| Saved LC08 pair, row 4 | Failed: HTTP 403 | Not attempted | Not attempted | Not performed |
| Saved LC09 pair, row 4 | Failed: HTTP 403 | Not attempted | Not attempted | Not performed |

TASK-003-A status remains **pixel test not performed**. The access blocker is Earth Engine discovery/initialization HTTP 403 in the designated local environment, before asset access. No claim is made about image permissions, pixels, masks, QA, B10 values, or scientific suitability. The same pair selection is retained; no replacement, collection search, footprint refetch, export, preview change, flare detection, bulk extraction, or model training was performed.
