# Landsat Coverage Provenance Status

## Preliminary status

The current daytime geometries have been used for preliminary calculations, but stable linkage of all of them to their daytime assets has not been confirmed. Numbers and maps are not ready for publication until this audit is complete.

The two nighttime scene identities and the match between the January 15 Landsat 9 scene and its recorded R2 selection are assessed separately from the unresolved daytime linkage. This identity evidence does not confirm a temporal pair or a final region of interest.

## Audit method and limits

The correction records each image's asset identifier, system index, product identifier, spacecraft, acquisition time, WRS path/row, solar elevation, and geometry together in one server-side feature. The stable asset identifier is an ordinary feature property; feature IDs and array order are not used as image identity. Offline tests cover missing and duplicate keys, asset/index mismatch, and satellite/collection/product/spacecraft mismatch.

The single authorized refresh used the saved query unchanged and returned counts of 7 and 5 (12 total). Metadata transfer then stopped on a server-side dictionary API error before any result list or footprints were returned. No retry was made. Thus no refreshed geometry validation, symmetric-difference measurement, coverage recalculation, or 24-combination intersection rebuild is available. The output is isolated from the prior run. Geometry unions and intersections remain preliminary geometric screening, not pixel validity or temporal coincidence.

No temporal pair or final ROI is approved by this status note. Detailed identifiers, geometry, boundary material, local paths, tables, and maps remain in private local outputs.
