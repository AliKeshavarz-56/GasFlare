// Coordinate-free template for the two exact Landsat C2 T2 Level-1 samples.
// Keep the separately supplied private configuration out of tracked files.
// The script performs read-only EE visualization; it defines no exports.

// PRIVATE CONFIG: supply this object locally when using the template. Do not
// commit coordinates or private sample asset identifiers.
var PRIVATE_CONFIG = null;
if (PRIVATE_CONFIG === null) {
  throw new Error('Load the separately supplied private sample configuration.');
}

var WINDOW = 9;
var EXPECTED_PRODUCTS = [
  'LC08_L1GT_032205_20250107_20250121_02_T2',
  'LC09_L1GT_032205_20250216_20250216_02_T2'
];
var REQUIRED_BANDS = ['B10', 'QA_PIXEL', 'QA_RADSAT'];
var QA_PIXEL_BITS = [
  ['Fill (bit 0)', 0], ['Dilated cloud (bit 1)', 1],
  ['Cirrus (bit 2)', 2], ['Cloud (bit 3)', 3],
  ['Cloud shadow (bit 4)', 4], ['Snow (bit 5)', 5]
];

function makeSample(sample) {
  var image = ee.Image(sample.assetId);
  var info = image.getInfo();
  if (info.properties.LANDSAT_PRODUCT_ID !== sample.productId) {
    throw new Error('Asset/product ID mismatch for ' + sample.label);
  }
  var bands = info.bands;
  var b10 = bands.filter(function (band) { return band.id === 'B10'; })[0];
  if (!b10 || !b10.crs || !b10.crs_transform || b10.crs_transform.length !== 6) {
    throw new Error('B10 native CRS/affine transform missing for ' + sample.label);
  }
  REQUIRED_BANDS.forEach(function (name) {
    var band = bands.filter(function (item) { return item.id === name; })[0];
    if (!band || band.crs !== b10.crs ||
        JSON.stringify(band.crs_transform) !== JSON.stringify(b10.crs_transform)) {
      throw new Error('Required bands do not share the B10 grid: ' + sample.label);
    }
  });

  var t = b10.crs_transform;
  var a = t[0], b = t[1], c = t[2], d = t[3], e = t[4], f = t[5];
  var determinant = a * e - b * d;
  if (!isFinite(determinant) || determinant === 0) throw new Error('Invalid B10 affine transform.');

  // Transform the private point into the exact asset CRS, invert the full
  // affine transform, and floor to the containing pixel as Python does.
  var point = ee.Geometry.Point(sample.coordinates, 'EPSG:4326');
  var projectedPoint = point.transform(b10.crs, 1);
  var xy = projectedPoint.coordinates().getInfo();
  var dx = xy[0] - c, dy = xy[1] - f;
  var col = Math.floor((e * dx - b * dy) / determinant);
  var row = Math.floor((-d * dx + a * dy) / determinant);
  var leftCol = col - Math.floor(WINDOW / 2);
  var topRow = row - Math.floor(WINDOW / 2);
  var gridTransform = [a, b, c + a * leftCol + b * topRow,
                       d, e, f + d * leftCol + e * topRow];
  var window = ee.Geometry.Polygon([[
    [gridTransform[2], gridTransform[5]],
    [gridTransform[2] + WINDOW * a, gridTransform[5] + WINDOW * d],
    [gridTransform[2] + WINDOW * a + WINDOW * b,
     gridTransform[5] + WINDOW * d + WINDOW * e],
    [gridTransform[2] + WINDOW * b, gridTransform[5] + WINDOW * e],
    [gridTransform[2], gridTransform[5]]
  ]], b10.crs, false);

  var values = image.select(REQUIRED_BANDS);
  var nativeMasks = values.mask().rename(['mask_B10', 'mask_QA_PIXEL', 'mask_QA_RADSAT']);
  var valid = nativeMasks.reduce(ee.Reducer.min()).eq(1).rename('all_band_masks_valid');
  var props = info.properties;
  ['RADIANCE_MULT_BAND_10', 'RADIANCE_ADD_BAND_10',
   'K1_CONSTANT_BAND_10', 'K2_CONSTANT_BAND_10'].forEach(function (key) {
    if (props[key] === undefined || props[key] === null || !isFinite(Number(props[key]))) {
      throw new Error('Missing exact-product coefficient ' + key + ' for ' + sample.label);
    }
  });

  var dn = image.select('B10').updateMask(valid).rename('B10_scaled_Level_1_DN');
  var radiance = dn.multiply(Number(props.RADIANCE_MULT_BAND_10))
    .add(Number(props.RADIANCE_ADD_BAND_10)).updateMask(dn.multiply(Number(props.RADIANCE_MULT_BAND_10))
      .add(Number(props.RADIANCE_ADD_BAND_10)).gt(0)).rename('B10_radiance_W_m2_sr_um');
  var bt = ee.Image.constant(Number(props.K2_CONSTANT_BAND_10))
    .divide(ee.Image.constant(Number(props.K1_CONSTANT_BAND_10)).divide(radiance).add(1).log())
    .rename('B10_brightness_temperature_K');

  var qa = image.select('QA_PIXEL');
  var qaLayers = QA_PIXEL_BITS.map(function (entry) {
    return qa.bitwiseAnd(1 << entry[1]).neq(0).updateMask(image.select('QA_PIXEL').mask())
      .rename(entry[0]);
  });
  var qaRadsat = image.select('QA_RADSAT');
  // Landsat 8/9 QA_RADSAT bit 9 denotes dropped pixels; it is not B10 saturation.
  var dropped = qaRadsat.bitwiseAnd(1 << 9).neq(0)
    .updateMask(qaRadsat.mask()).rename('Dropped_pixel_QA_RADSAT_bit_9');

  print(sample.label + ' product metadata', ee.Dictionary(props).select([
    'LANDSAT_PRODUCT_ID', 'system:time_start', 'RADIANCE_MULT_BAND_10',
    'RADIANCE_ADD_BAND_10', 'K1_CONSTANT_BAND_10', 'K2_CONSTANT_BAND_10',
    'SATURATION_BAND_10'
  ]));
  print(sample.label + ' window convention', '9x9 native B10 pixels; containing pixel at row/column floor of inverse affine; window starts 4 rows/columns before it');
  print(sample.label + ' pixel grid', {crs: b10.crs, transform: gridTransform});

  Map.addLayer(ee.Image().byte().paint(sample.footprint, 1, 2),
    {palette: ['00ffff']}, sample.label + ' scene footprint', true);
  Map.addLayer(point, {color: 'ffffff'}, sample.label + ' sample point', true);
  Map.addLayer(ee.Image().byte().paint(window, 1, 1),
    {palette: ['ffff00']}, sample.label + ' exact 9x9 window', true);
  Map.addLayer(dn.clip(window), {min: 0, max: 20000, palette: ['101010', 'ffd166', 'ffffff']},
    sample.label + ' B10 scaled Level-1 DN (all native masks)', false);
  Map.addLayer(radiance.clip(window), {min: 0, max: 20, palette: ['101010', 'ef476f', 'ffd166', 'ffffff']},
    sample.label + ' B10 radiance W/(m^2 sr um)', false);
  Map.addLayer(bt.clip(window), {min: 250, max: 350, palette: ['264653', '2a9d8f', 'e9c46a', 'e76f51']},
    sample.label + ' B10 brightness temperature K', false);
  Map.addLayer(valid.selfMask().clip(window), {palette: ['00ff00']},
    sample.label + ' valid intersection of three native masks', false);
  Map.addLayer(nativeMasks.select('mask_B10').clip(window), {min: 0, max: 1}, sample.label + ' native B10 mask', false);
  Map.addLayer(nativeMasks.select('mask_QA_PIXEL').clip(window), {min: 0, max: 1}, sample.label + ' native QA_PIXEL mask', false);
  Map.addLayer(nativeMasks.select('mask_QA_RADSAT').clip(window), {min: 0, max: 1}, sample.label + ' native QA_RADSAT mask', false);
  qaLayers.forEach(function (layer) {
    Map.addLayer(layer.clip(window).selfMask(), {palette: ['ff4d6d']}, sample.label + ' ' + layer.bandNames().getInfo()[0], false);
  });
  Map.addLayer(dropped.clip(window).selfMask(), {palette: ['ff00ff']}, sample.label + ' QA_RADSAT dropped bit 9', false);
  Map.centerObject(window, 17);
}

if (!PRIVATE_CONFIG.samples || PRIVATE_CONFIG.samples.length !== 2) {
  throw new Error('Private config must contain exactly two samples.');
}
PRIVATE_CONFIG.samples.forEach(function (sample, index) {
  if (sample.productId !== EXPECTED_PRODUCTS[index]) {
    throw new Error('Private configuration must contain the two approved exact products in order.');
  }
});
PRIVATE_CONFIG.samples.forEach(makeSample);

print('Legend', 'DN = stored scaled Level-1 B10; radiance = ML*DN+AL in W/(m^2 sr um); BT = K2/ln(1+K1/radiance) in K. Each layer visibility is independently toggleable.');
print('Time', 'Each exact product timestamp is printed above in UTC metadata; this is not a time-series composite.');
print('Limitations', 'QA flags are interpretive layers, not extra mask rules. QA_RADSAT bit 9 is dropped-pixel status, not B10 saturation. BT is sensor-equivalent brightness temperature, not surface or flare temperature.');
