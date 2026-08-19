from concurrent.futures import ThreadPoolExecutor
from subprocess import check_call, check_output
from tempfile import TemporaryDirectory

import geopandas as gpd
import rasterio as rio

from ..utils import logger

OUTPUT_PREFIX = "/usr/src/app/output"

EXTRACT_TRAIN_PARQUET = f"{OUTPUT_PREFIX}/extract_train.parquet"
EXTRACT_TRAIN_PARQUET_V2 = f"{OUTPUT_PREFIX}/extract_train_v2.parquet"

EXTRACT_TEST_PARQUET = f"{OUTPUT_PREFIX}/extract_test.parquet"
EXTRACT_TEST_PARQUET_V2 = f"{OUTPUT_PREFIX}/extract_test_v2.parquet"

BANDS_CHM_META = ["CHM_META"]
BANDS_CHM_ETH = ["CHM_ETH"]
BANDS_DEM = ["elevation"]
BANDS_TERRAIN = ["slope", "aspect", "tri", "tpi", "hillshade"]

folder = TemporaryDirectory(delete=False)

# data list
logger.info("Create ETH COG")
eth_list = check_output(
    "gcloud storage ls gs://gee-ramiqcom-s4g-bucket/opengeohub_summerschool_2026/eth_chm/",
    shell=True,
    text=True,
).split("\n")[:-1]
eth_list = [path.replace("gs://", "/vsigs/") for path in eth_list]

vrt_eth = f"{folder.name}/eth.tif"
check_call(f"""gdal raster mosaic -f COG {" ".join(eth_list)} {vrt_eth}""", shell=True)
check_call(
    f"gcloud storage cp {vrt_eth} gs://gee-ramiqcom-s4g-bucket/opengeohub_summerschool_2026/eth_chm/ETH_CHM.tif",
    shell=True,
)

logger.info("Create META COG")
meta_list = check_output(
    "gcloud storage ls gs://gee-ramiqcom-s4g-bucket/opengeohub_summerschool_2026/meta_chm/",
    shell=True,
    text=True,
).split("\n")[:-1]
meta_list = [path.replace("gs://", "/vsigs/") for path in eth_list]

vrt_meta = f"{folder.name}/meta.tif"
check_call(
    f"""gdal raster mosaic -f COG {" ".join(meta_list)} {vrt_meta}""", shell=True
)
check_call(
    f"gcloud storage cp {vrt_meta} gs://gee-ramiqcom-s4g-bucket/opengeohub_summerschool_2026/meta_chm/META_CHM.tif",
    shell=True,
)

data_sources = [
    dict(bands=BANDS_CHM_ETH, source=vrt_eth),
    dict(bands=BANDS_CHM_META, source=vrt_meta),
    dict(
        bands=BANDS_DEM,
        source="https://storage.googleapis.com/gee-ramiqcom-s4g-bucket/opengeohub_summerschool_2026/nasadem/opengeohub_summerschool_2026_NASADEM_30m.tif",
    ),
    dict(
        bands=BANDS_TERRAIN,
        source="https://storage.googleapis.com/gee-ramiqcom-s4g-bucket/opengeohub_summerschool_2026/terrain/terrain.tif",
    ),
]


# create VRT eth
def extract(df, coords, bands, source):
    logger.info(f"Extract {bands}")
    with rio.open(source) as src:
        df[bands] = [data for data in src.sample(coords)]


logger.info("Load train")
train_df = gpd.read_parquet(EXTRACT_TRAIN_PARQUET)
coords = [coord for coord in zip(train_df.geometry.x, train_df.geometry.y)]

logger.info("Extract train")
with ThreadPoolExecutor(8) as executor:
    jobs = [
        executor.submit(extract, train_df, coords, data["bands"], data["source"])
        for data in data_sources
    ]
    for job in jobs:
        try:
            job.result()
        except Exception as e:
            logger.info(f"Error: {e}")

logger.info("Save train")
train_df.to_parquet(EXTRACT_TRAIN_PARQUET_V2)

logger.info("Load test")
test_df = gpd.read_parquet(EXTRACT_TEST_PARQUET)
coords = [coord for coord in zip(test_df.geometry.x, test_df.geometry.y)]

logger.info("Extract test")
with ThreadPoolExecutor(8) as executor:
    jobs = [
        executor.submit(extract, test_df, coords, data["bands"], data["source"])
        for data in data_sources
    ]
    for job in jobs:
        try:
            job.result()
        except Exception as e:
            logger.info(f"Error: {e}")

logger.info("Save test")
test_df.to_parquet(EXTRACT_TEST_PARQUET_V2)
