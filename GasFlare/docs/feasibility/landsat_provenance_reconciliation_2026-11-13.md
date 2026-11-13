# Landsat provenance reconciliation, 2026-11-13

This read-only reconciliation checked the complete product-ID sets in the inventory referenced by the run manifest, that run's audit CSV and metadata GeoJSON, and the local candidate intersection table. All four sets are identical and contain 90 distinct products: 46 LC08 and 44 LC09. Satellite labels independently parsed from collection names and product-ID prefixes agree throughout. Product-ID acquisition dates match metadata acquisition dates for all products; the common date range is 2025-01-07 through 2025-12-25. The inventory records these night-scene counts in its T2 collections; its T1 collections contain no night scenes.

The intersection table repeats products across candidate matches. The per-candidate maximum of 46 LC08 represents 46 distinct products for a candidate with the full set, not 46 duplicate rows. Earlier 45/45 totals are superseded by this reconciliation; historical reports and generated files were not rewritten. This report contains aggregate validation only and excludes candidate rows, coordinates, and product or asset identifiers.

The candidate coordinate reference system remains unverified. In particular, compatibility with EPSG:4326 is an unverified assumption, so geometric screening results retain that limitation.

No Earth Engine request, preview, pixel analysis, or Export was performed.
