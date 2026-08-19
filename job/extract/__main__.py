from concurrent.futures import ThreadPoolExecutor

import geopandas as gpd
import rasterio as rio

from ..utils import logger

DATA_PREFIX = "/usr/src/app/data"
OUTPUT_PREFIX = "/usr/src/app/output"

TRAIN_PARQUET = f"{OUTPUT_PREFIX}/train_only_biomass.parquet"
TEST_PARQUET = f"{OUTPUT_PREFIX}/test_only_biomass.parquet"
EXTRACT_TRAIN_PARQUET = f"{OUTPUT_PREFIX}/extract_train.parquet"
EXTRACT_TEST_PARQUET = f"{OUTPUT_PREFIX}/extract_test.parquet"
SUBMISSION_CSV = f"{DATA_PREFIX}/sample_submission.csv"

BANDS_S2 = ["BLUE", "GREEN", "RED", "NIR", "SWIR1", "SWIR2"]
# BANDS_S2_DIST = [f"{b}_DIST" for b in BANDS_S2]
BANDS_S1 = ["VV", "VH"]
# BANDS_S1_DIST = [f"{b}_DIST" for b in BANDS_S1]

logger.info("Load train")
train_df = gpd.read_parquet(TRAIN_PARQUET)


def run_per_tile(index, df, tile_ids):
    tile_id = tile_ids[index]
    tile_sample = df[df["tile_id"] == tile_id]
    coords = [coord for coord in zip(tile_sample.geometry.x, tile_sample.geometry.y)]
    years = tile_sample["year"].unique()

    for year in years:
        logger.info(f"Run {tile_id} {year} {index + 1} / {len(tile_ids)}")

        df_mask = (df["tile_id"] == tile_id) & (df["year"] == year)

        with rio.open(
            f"gs://gee-ramiqcom-s4g-bucket/opengeohub_summerschool_2026/s2/tile_{tile_id}_{year}_S2_L2A_composite_{year}-06-01_{year}-07-31_10m.tif"
        ) as src:
            df.loc[df_mask, BANDS_S2] = [data for data in src.sample(coords)]

        # with rio.open(
        #     f"gs://gee-ramiqcom-s4g-bucket/opengeohub_summerschool_2026/s2_distance/tile_{tile_id}_{year}_S2_L2A_composite_{year}-06-01_{year}-07-31_10m.tif"
        # ) as src:
        #     df.loc[
        #         df_mask,
        #         BANDS_S2_DIST,
        #     ] = [data for data in src.sample(coords)]

        with rio.open(
            f"gs://gee-ramiqcom-s4g-bucket/opengeohub_summerschool_2026/s1/tile_{tile_id}_{year}_S1_RTC_composite_{year}-06-01_{year}-07-31_10m.tif"
        ) as src:
            df.loc[df_mask, BANDS_S1] = [data for data in src.sample(coords)]

        # with rio.open(
        #     f"gs://gee-ramiqcom-s4g-bucket/opengeohub_summerschool_2026/s1_distance/tile_{tile_id}_{year}_S1_RTC_composite_{year}-06-01_{year}-07-31_10m.tif"
        # ) as src:
        #     df.loc[
        #         df_mask,
        #         BANDS_S1_DIST,
        #     ] = [data for data in src.sample(coords)]


tile_ids = train_df["tile_id"].unique()

logger.info("Extract train")
with ThreadPoolExecutor(8) as executor:
    jobs = []
    for index in range(len(tile_ids)):
        jobs.append(executor.submit(run_per_tile, index, train_df, tile_ids))
    for job in jobs:
        try:
            job.result()
        except Exception as e:
            logger.info(f"Error: {e}")

# to parquet
logger.info("Save train")
train_df.to_parquet(EXTRACT_TRAIN_PARQUET)

logger.info("Load test")
test_df = gpd.read_parquet(TEST_PARQUET)

tile_ids = test_df["tile_id"].unique()

logger.info("Extract test")
with ThreadPoolExecutor(8) as executor:
    jobs = []
    for index in range(len(tile_ids)):
        jobs.append(executor.submit(run_per_tile, index, test_df, tile_ids))
    for job in jobs:
        try:
            job.result()
        except Exception as e:
            logger.info(f"Error: {e}")

# to parquet
logger.info("Save test")
test_df.to_parquet(EXTRACT_TEST_PARQUET)
