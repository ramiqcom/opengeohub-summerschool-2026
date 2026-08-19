import ee from '@google/earthengine';

console.log('Authenticating');

const key = JSON.parse(Deno.env.get('GOOGLE_PRIVATE_KEY'));

await authenticateViaPrivateKey(key);

console.log('Authenticated');

const roi =
  'https://storage.googleapis.com/gee-ramiqcom-s4g-bucket/opengeohub_summerschool_2026/roi/tiles_v2.geojson';

console.log('Loading ROI');

const roiJson = await (await fetch(roi)).json();

console.log('Running CHM export task');
await chmTask();

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

async function chmTask() {
  const roi: ee.FeatureCollection = ee.FeatureCollection(roiJson);
  const bounds: ee.Geometry = roi.bounds();

  const image = ee
    .Image('users/nlang/ETH_GlobalCanopyHeight_2020_10m_v1')
    .clipToCollection(roi)
    .clip(bounds);

  const task = ee.batch.Export.image.toCloudStorage({
    image: image.unmask(-9999),
    crs: 'EPSG:4326',
    region: await evaluateGee(bounds),
    maxPixels: 1e13,
    scale: 10,
    description: `ETH_CHM_summerschool`,
    bucket: 'gee-ramiqcom-s4g-bucket',
    fileNamePrefix: `opengeohub_summerschool_2026/eth_chm/ETH_CHM`,
    fileFormat: 'GeoTIFF',
    formatOptions: {
      cloudOptimized: true,
      noData: -9999,
    },
  });

  await exportTask(task);
}
