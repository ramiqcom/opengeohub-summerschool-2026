import ee from "@google/earthengine";

console.log("Authenticating");

const key = JSON.parse(Deno.env.get("GOOGLE_PRIVATE_KEY"));

await authenticateViaPrivateKey(key);

console.log("Authenticated");

const roi =
  "https://storage.googleapis.com/gee-ramiqcom-s4g-bucket/opengeohub_summerschool_2026/roi/tiles.geojson";

console.log("Loading ROI");

const mosaixRoiJson = await (await fetch(roi)).json();

console.log("Running GEDI task");

await gediTask();

async function authenticateViaPrivateKey(
  key: Record<string, any>,
): Promise<void> {
  return await new Promise((resolve, reject) => {
    ee.data.authenticateViaPrivateKey(
      key,
      () =>
        ee.initialize(null, null, resolve, (error: string) =>
          reject(new Error(error)),
        ),
      (error: string) => reject(new Error(error)),
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

async function gediTask() {
  const l2a: ee.ImageCollection = ee.ImageCollection(
    "LARSE/GEDI/GEDI02_A_002_MONTHLY",
  );
  const l4a: ee.ImageCollection = ee.ImageCollection(
    "LARSE/GEDI/GEDI04_A_002_MONTHLY",
  );
  const l2b: ee.ImageCollection = ee.ImageCollection(
    "LARSE/GEDI/GEDI02_B_002_MONTHLY",
  );
  const roi: ee.FeatureCollection = ee.FeatureCollection(mosaixRoiJson);
  const bounds: ee.Geometry = roi.bounds();

  const gediList = [
    { name: "CHM", col: l2a, multiplier: 1, preprocess: chmPreprocess },
    {
      name: "treecover",
      col: l2b,
      multiplier: 100,
      preprocess: treecoverPreprocess,
    },
    { name: "AGB", col: l4a, multiplier: 1, preprocess: agbPreprocess },
  ];

  const filter = ee.Filter.and(ee.Filter.bounds(bounds));

  const gediImage = ee.Image(
    gediList.map((dict) => {
      const name = dict.name;
      const col = dict.col;
      const multiplier = dict.multiplier;
      const preprocess = dict.preprocess;
      const image = col
        .filter(filter)
        .map(preprocess)
        .mean()
        .multiply(multiplier);
      return image.toFloat().rename(name);
    }),
  );

  const table = gediImage.sample({
    scale: 25,
    region: bounds,
    geometries: true,
  });

  const task = ee.batch.Export.table.toCloudStorage({
    collection: table,
    description: "GEDI_summerschool",
    bucket: "gee-ramiqcom-s4g-bucket",
    fileNamePrefix: "opengeohub_summerschool_2026/gedi_gee/GEDI",
    fileFormat: "geojson",
  });

  await exportTask(task);
}

function chmPreprocess(image: ee.Image) {
  const mask = image
    .select("quality_flag")
    .and(image.select("degrade_flag").eq(0));
  return image.select("rh98").updateMask(mask);
}

function treecoverPreprocess(image: ee.Image) {
  const mask = image
    .select("l2b_quality_flag")
    .and(image.select("degrade_flag").eq(0));
  return image.select("cover").updateMask(mask);
}

function agbPreprocess(image: ee.Image) {
  const mask = image
    .select("l2_quality_flag")
    .and(image.select("l4_quality_flag"))
    .and(image.select("degrade_flag").eq(0));
  return image.select("agbd").updateMask(mask);
}
