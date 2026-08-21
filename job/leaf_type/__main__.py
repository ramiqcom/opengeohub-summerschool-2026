import os
from concurrent.futures import ThreadPoolExecutor
from subprocess import check_call, check_output
from tempfile import TemporaryDirectory

import geopandas as gpd
from pystac_client import Client

from ..utils import logger

OUTPUT_VOLUME = "/usr/src/app/output"

os.environ["AWS_S3_ENDPOINT"] = "eodata.dataspace.copernicus.eu"
os.environ["AWS_VIRTUAL_HOSTING"] = "FALSE"
os.environ["AWS_NO_SIGN_REQUEST"] = "NO"

STAC = "https://stac.dataspace.copernicus.eu/v1"
LAYER_NAME = "leaf_type"
COL_NAME = "clms_vlcc_dominant-leaf-type_europe_10m_yearly_v1"
ROI = "https://storage.googleapis.com/gee-ramiqcom-s4g-bucket/opengeohub_summerschool_2026/roi/tiles_v2.geojson"

CLOUD_PREFIX = "gs://gee-ramiqcom-s4g-bucket/opengeohub_summerschool_2026"
RESOLUTION = 10
OUTPUT_PREFIX = f"{CLOUD_PREFIX}/{LAYER_NAME}"

TRAIN_PARQUET = f"{OUTPUT_VOLUME}/train_only_biomass.parquet"
TEST_PARQUET = f"{OUTPUT_VOLUME}/test_only_biomass.parquet"
GRIDS = "https://storage.googleapis.com/gee-ramiqcom-s4g-bucket/opengeohub_summerschool_2026/roi/tiles_v2.geojson"

catalog = Client.open(STAC)

logger.info("Load grids")
grids_df = gpd.read_file(GRIDS)

logger.info("Load train sample")
train_df = gpd.read_parquet(TRAIN_PARQUET)

logger.info("Load test")
test_df = gpd.read_parquet(TEST_PARQUET)

tile_ids = grids_df["tile_id"].unique()


try:
    all_dones = check_output(
        f"gcloud storage ls {OUTPUT_PREFIX}", shell=True, text=True
    ).split("\n")[:-1]
    all_dones = [
        "_".join(data.split("/")[-1].split(".tif")[0].split("_")[:3])
        for data in all_dones
    ]
    logger.info(all_dones)
except Exception:
    all_dones = []


def load_density(index):
    grid = grids_df[index : index + 1]
    tile_id = grid.iloc[0]["tile_id"]

    logger.info(f"Run {tile_id} {index + 1} / {len(tile_ids)}")

    xmin, ymin, xmax, ymax = tuple(grid.total_bounds)

    train_bbox = train_df.cx[xmin:xmax, ymin:ymax]
    test_bbox = test_df.cx[xmin:xmax, ymin:ymax]

    years = list(set([*train_bbox["year"].unique(), *test_bbox["year"].unique()]))

    for year in years:
        year = max(year, 2018)
        name = f"tile_{tile_id}_{year}"

        if name not in all_dones:
            date_start = f"{year}-01-01"
            date_end = f"{year}-12-31"

            col_filter_year = [
                data
                for data in catalog.search(
                    collections=[COL_NAME],
                    datetime=(date_start, date_end),
                    bbox=(xmin, ymin, xmax, ymax),
                ).items_as_dicts()
            ]

            if len(col_filter_year) > 0:
                paths = [
                    f"{feat['assets']['data']['href'].replace('s3://', '/vsis3/')}"
                    for feat in col_filter_year
                ]

                with TemporaryDirectory() as folder:
                    image = f"{folder}/mosaic.tif"
                    check_call(
                        f"""gdal raster pipeline \
                                ! mosaic {" ".join(paths)} --resolution=average \
                                ! reproject \
                                    -d EPSG:4326 \
                                    --bbox-crs=EPSG:4326 \
                                    --bbox={xmin},{ymin},{xmax},{ymax} \
                                    --resolution={RESOLUTION / 111_000},{RESOLUTION / 111_000} \
                                ! write \
                                    -f COG \
                                    --co="COMPRESS=ZSTD" \
                                    {image}
                        """,
                        shell=True,
                    )

                    check_call(
                        f"gcloud storage cp {image} {OUTPUT_PREFIX}/{name}.tif",
                        shell=True,
                    )
            else:
                logger.info(f"No data in {name}")


with ThreadPoolExecutor(2) as executor:
    jobs = []
    for index in range(len(tile_ids)):
        jobs.append(executor.submit(load_density, index))

    for job in jobs:
        try:
            job.result()
        except Exception as e:
            logger.info(f"Error: {e}")
