# Landsat Coverage Provenance Status

## Preliminary status

The current daytime geometries have been used for preliminary calculations, but stable linkage of all of them to their daytime assets has not been confirmed. Numbers and maps are not ready for publication until this audit is complete.

The two nighttime scene identities and the match between the January 15 Landsat 9 scene and its recorded R2 selection are assessed separately from the unresolved daytime linkage. This identity evidence does not confirm a temporal pair or a final region of interest.

## Audit method and limits

The corrected builder constructs requested properties and geometry from the same server-side image. The stable asset identifier is an ordinary feature property; feature IDs and array order are not used as image identity. Offline tests cover missing and duplicate keys, asset/index mismatch, satellite/collection/product/spacecraft mismatch, and serialization of the actual Earth Engine Python API object graph without a metadata request. This serialization test does not establish server execution.

The authorized run used the saved query, bounds, and filters unchanged and returned counts of 7 and 5 (12 total). Its retained error log reports that metadata validation stopped on asset/index and satellite/collection/product identity mismatches. However, the unvalidated response file from that run is not present in its output directory, so its raw records cannot be inspected or validated offline. The exact cause of the mismatch and the source identity of all 12 records remain unresolved; the log alone does not establish whether the validator or the returned identities caused the failure. No retry was made.

An older, separate 12-feature output lacks the explicit source asset and source index properties required by the current validator. Its product, spacecraft, and attributed collection fields are mutually consistent, but that does not prove asset provenance or reconstruct the missing response. Local Earth Engine library documentation says FeatureCollection merge prefixes feature IDs; these generated IDs are not evidence of source image identity, and the documentation does not establish what happened to the missing run's source properties. Offline serialization tests do not establish server execution.

No refreshed union comparison, symmetric-difference measurement, coverage recalculation, county table, or complete 24-combination intersection audit was produced after the failed validation. Earlier totals, areas, and maps remain provisional and were not recalculated from this run. Geometry unions and intersections remain geometric screening, not pixel validity or temporal coincidence.

No temporal pair or final ROI is approved by this status note. Detailed identifiers, geometry, boundary material, local paths, tables, and maps remain in private local outputs.
