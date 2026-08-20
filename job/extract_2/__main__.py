from concurrent.futures import ThreadPoolExecutor
from subprocess import check_call
from tempfile import TemporaryDirectory

import geopandas as gpd
import rasterio as rio

from ..utils import logger

OUTPUT_PREFIX = "/usr/src/app/output"

# EXTRACT_TRAIN_PARQUET = f"{OUTPUT_PREFIX}/extract_train.parquet"
EXTRACT_TRAIN_PARQUET_V2 = f"{OUTPUT_PREFIX}/extract_train_v2.parquet"

# EXTRACT_TEST_PARQUET = f"{OUTPUT_PREFIX}/extract_test.parquet"
EXTRACT_TEST_PARQUET_V2 = f"{OUTPUT_PREFIX}/extract_test_v2.parquet"

BANDS_CHM_META = ["CHM_META"]
BANDS_CHM_ETH = ["CHM_ETH"]
BANDS_CHM_ALS = ["CHM_ALS"]
BANDS_CANOPY_DENSITY = ["CANOPY_DENSITY"]
BANDS_TREE_RATIO = ["TREE_RATIO"]
BANDS_AGB_GEDI = ["AGB_GEDI"]
BANDS_AGB_ALS = ["AGB_ALS"]
BANDS_LST = ["LST"]
BANDS_DEM = ["elevation"]
BANDS_TERRAIN = ["slope", "aspect", "tri", "tpi", "hillshade"]
BANDS_EMBEDDINGS = [f"A{index}" for index in range(64)]

folder = TemporaryDirectory(delete=False)

check_call(
    f"gcloud storage cp -r gs://gee-ramiqcom-s4g-bucket/opengeohub_summerschool_2026/embedding {folder.name}/.",
    shell=True,
)
logger.info("Make VRT embedding")
vrt_embedding = f"{folder.name}/embedding.vrt"
check_call(
    f"""gdal raster mosaic -f VRT --resolution=average {folder.name}/embedding/*.tif {vrt_embedding}""",
    shell=True,
)

data_sources = [
    # dict(
    #     bands=BANDS_CHM_ETH,
    #     source="gs://gee-ramiqcom-s4g-bucket/opengeohub_summerschool_2026/eth_chm/ETH_CHM.tif",
    # ),
    # dict(
    #     bands=BANDS_CHM_META,
    #     source="gs://gee-ramiqcom-s4g-bucket/opengeohub_summerschool_2026/meta_chm/META_CHM.tif",
    # ),
    # dict(
    #     bands=BANDS_CHM_ALS,
    #     source="gs://gee-ramiqcom-s4g-bucket/opengeohub_summerschool_2026/als_canopy_height/als_canopy_height.tif",
    # ),
    # dict(
    #     bands=BANDS_CANOPY_DENSITY,
    #     source="gs://gee-ramiqcom-s4g-bucket/opengeohub_summerschool_2026/canopy_density/canopy_density_2020.tif",
    # ),
    # dict(
    #     bands=BANDS_DEM,
    #     source="gs://gee-ramiqcom-s4g-bucket/opengeohub_summerschool_2026/nasadem/opengeohub_summerschool_2026_NASADEM_30m.tif",
    # ),
    # dict(
    #     bands=BANDS_TERRAIN,
    #     source="gs://gee-ramiqcom-s4g-bucket/opengeohub_summerschool_2026/terrain/terrain.tif",
    # ),
    # dict(
    #     bands=BANDS_LST,
    #     source="gs://gee-ramiqcom-s4g-bucket/opengeohub_summerschool_2026/lst/opengeohub_Landsat_LST_composite_2025-06-01_2025-06-30_100m.tif",
    # ),
    # dict(bands=BANDS_EMBEDDINGS, source=vrt_embedding, download=False),
    dict(
        bands=BANDS_AGB_GEDI,
        source="gs://gee-ramiqcom-s4g-bucket/opengeohub_summerschool_2026/biomass_GEDI/Biomass_predicted_by_GEDI_Sentinel_based_model_2020_COG.tif",
    ),
    dict(
        bands=BANDS_AGB_ALS,
        source="gs://gee-ramiqcom-s4g-bucket/opengeohub_summerschool_2026/biomass_ALS/Biomass_predicted_by_ALS_Sentinel_based_model_2020_COG.tif",
    ),
    dict(
        bands=BANDS_TREE_RATIO,
        source="gs://gee-ramiqcom-s4g-bucket/opengeohub_summerschool_2026/gedi_tree_ratio/gedi_tree_ratio.tif",
    ),
]


def downloads(index):
    folder = TemporaryDirectory(delete=False)
    data_dict = data_sources[index]

    if "download" not in data_dict:
        local = f"{folder.name}/image.tif"
        check_call(f"gcloud storage cp {data_dict['source']} {local}", shell=True)
        data_sources[index]["local_source"] = local
    elif not data_dict["download"]:
        data_sources[index]["local_source"] = data_dict["source"]


with ThreadPoolExecutor(8) as executor:
    jobs = [executor.submit(downloads, index) for index in range(len(data_sources))]
    for job in jobs:
        try:
            job.result()
        except Exception as e:
            logger.info(f"Error: {e}")


# extract value
def extract(df, coords, bands, source):
    logger.info(f"Extract {bands}")
    with rio.open(source) as src:
        df[bands] = [data for data in src.sample(coords)]


logger.info("Load train")
train_df = gpd.read_parquet(EXTRACT_TRAIN_PARQUET_V2)
coords = [coord for coord in zip(train_df.geometry.x, train_df.geometry.y)]

logger.info("Extract train")
with ThreadPoolExecutor(8) as executor:
    jobs = [
        executor.submit(extract, train_df, coords, data["bands"], data["local_source"])
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
test_df = gpd.read_parquet(EXTRACT_TEST_PARQUET_V2)
coords = [coord for coord in zip(test_df.geometry.x, test_df.geometry.y)]

logger.info("Extract test")
with ThreadPoolExecutor(8) as executor:
    jobs = [
        executor.submit(extract, test_df, coords, data["bands"], data["local_source"])
        for data in data_sources
    ]
    for job in jobs:
        try:
            job.result()
        except Exception as e:
            logger.info(f"Error: {e}")

logger.info("Save test")
test_df.to_parquet(EXTRACT_TEST_PARQUET_V2)
