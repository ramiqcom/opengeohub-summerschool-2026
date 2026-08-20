import ee from '@google/earthengine';

console.log('Authenticating');

const key = JSON.parse(Deno.env.get('GOOGLE_PRIVATE_KEY'));

await authenticateViaPrivateKey(key);

console.log('Authenticated');

const roi =
  'https://storage.googleapis.com/gee-ramiqcom-s4g-bucket/opengeohub_summerschool_2026/roi/tiles.geojson';

console.log('Loading ROI');

const roiJson = await (await fetch(roi)).json();

const tiles = roiJson['features'].map((feat) => feat['properties']['tile_id']);

console.log('Running Embedding task');
tiles.slice(0, 1).map(async (tile_id: string) => {
  console.log(`Run ${tile_id}`);
  await embeddingTask(tile_id);
});

async function authenticateViaPrivateKey(
  key: Record<string, any>
): Promise<void> {
  return await new Promise((resolve, reject) => {
    ee.data.authenticateViaPrivateKey(
      key,
      () =>
        ee.initialize(null, null, resolve, (error: string) =>
          reject(new Error(error))
        ),
      (error: string) => reject(new Error(error))
    );
  });
}

async function evaluateGee(object: ee.Element) {
  return await new Promise((resolve, reject) => {
    object.evaluate((result: any, error: string | undefined) => {
      if (error) {
        reject(new Error(error));
      } else {
        resolve(result);
      }
    });
  });
}

async function exportTask(task: ee.batch.Export<any>) {
  return await new Promise((resolve, reject) => {
    task.start((_, error: string | undefined) => {
      if (error) {
        reject(new Error(error));
      } else {
        resolve(undefined);
      }
    });
  });
}

async function embeddingTask(tile_id: string) {
  const col: ee.ImageCollection = ee.ImageCollection(
    'GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL'
  );

  const roi: ee.FeatureCollection = ee
    .FeatureCollection(roiJson)
    .filter(ee.Filter.eq('tile_id', tile_id));
  const bounds: ee.Geometry = roi.bounds();

  const filter = ee.Filter.and(
    ee.Filter.bounds(bounds),
    ee.Filter.date('2020-01-01', '2020-12-31')
  );

  let image = col.filter(filter);
  image = image.mosaic().clip(bounds);

  const task = ee.batch.Export.image.toCloudStorage({
    image: image,
    crs: 'EPSG:4326',
    region: await evaluateGee(bounds),
    maxPixels: 1e13,
    scale: 10,
    description: `summerschool_embedding/${tile_id}`,
    bucket: 'gee-ramiqcom-s4g-bucket',
    fileNamePrefix: `opengeohub_summerschool_2026/embedding/${tile_id}`,
    fileFormat: 'GeoTIFF',
    formatOptions: {
      cloudOptimized: true,
      noData: -9999,
    },
  });

  await exportTask(task);
}
