# Landsat Coverage Provenance Status

## Preliminary status

The current daytime geometries have been used for preliminary calculations, but stable linkage of all of them to their daytime assets has not been confirmed. Numbers and maps are not ready for publication until this audit is complete.

The two nighttime scene identities and the match between the January 15 Landsat 9 scene and its recorded R2 selection are assessed separately from the unresolved daytime linkage. This identity evidence does not confirm a temporal pair or a final region of interest.

## Audit method and limits

The corrected builder constructs requested properties and geometry from the same server-side image. The stable asset identifier is an ordinary feature property; feature IDs and array order are not used as image identity. Offline tests cover missing and duplicate keys, asset/index mismatch, satellite/collection/product/spacecraft mismatch, and serialization of the actual Earth Engine Python API object graph without a metadata request. This serialization test does not establish server execution.

The authorized run used the saved query, bounds, and filters unchanged and returned counts of 7 and 5 (12 total). Its retained error log reports that metadata validation stopped on asset/index and satellite/collection/product identity mismatches. The prior claim that the unvalidated response was successfully saved is **unconfirmed**: the expected file is absent from the resolved output directory, and the local error/query records do not prove a durable save. Its raw records therefore cannot be inspected or validated offline. The exact reason the file is absent and the cause of the identity mismatch remain unresolved; the log alone does not establish whether the validator or returned identities caused the failure. No retry was made.

An older, separate 12-feature output lacks the explicit source asset and source index properties required by the current validator. Its product, spacecraft, and attributed collection fields are mutually consistent, but that does not prove asset provenance or reconstruct the missing response. Local Earth Engine library documentation says FeatureCollection merge prefixes feature IDs; these generated IDs are not evidence of source image identity, and the documentation does not establish what happened to the missing run's source properties. Offline serialization tests do not establish server execution.

No refreshed union comparison, symmetric-difference measurement, coverage recalculation, county table, or complete 24-combination intersection audit was produced after the failed validation. Earlier totals, areas, and maps remain provisional and were not recalculated from this run. Geometry unions and intersections remain geometric screening, not pixel validity or temporal coincidence.

The builder now resolves its output directory to an absolute path and atomically stores the unvalidated server response before validation, rereads and parses it, and records its absolute path, record count, byte size, and SHA-256 in a private manifest. A storage failure aborts the run before validation. An offline regression test checks that a subsequent identity-validation failure does not remove or alter the saved raw payload. This is preparation for a future explicitly authorized run; it does not recover or explain the missing prior response and makes no claim of server execution. No temporal pair or final ROI is approved by this status note. Detailed identifiers, geometry, boundary material, local paths, tables, and maps remain in private local outputs.
