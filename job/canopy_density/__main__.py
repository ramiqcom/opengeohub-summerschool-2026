import os
from concurrent.futures import ThreadPoolExecutor
from subprocess import check_call
from tempfile import TemporaryDirectory

import geopandas as gpd
from pystac_client import Client

from ..utils import logger

OUTPUT_VOLUME = "/usr/src/app/output"

os.environ["AWS_S3_ENDPOINT"] = "eodata.dataspace.copernicus.eu"
os.environ["AWS_VIRTUAL_HOSTING"] = "FALSE"
os.environ["AWS_NO_SIGN_REQUEST"] = "NO"

STAC = "https://stac.dataspace.copernicus.eu/v1"
COL_NAME = "clms_vlcc_tree-cover-density_europe_10m_yearly_v1"
ROI = "https://storage.googleapis.com/gee-ramiqcom-s4g-bucket/opengeohub_summerschool_2026/roi/tiles_v2.geojson"

CLOUD_PREFIX = "gs://gee-ramiqcom-s4g-bucket/opengeohub_summerschool_2026"
RESOLUTION = 10

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


def load_density(index):
    grid = grids_df[index : index + 1]
    tile_id = grid.iloc[0]["tile_id"]

    logger.info(f"Run {tile_id} {index + 1} / {len(tile_ids)}")

    xmin, ymin, xmax, ymax = tuple(grid.total_bounds)

    train_bbox = train_df.cx[xmin:xmax, ymin:ymax]
    test_bbox = test_df.cx[xmin:xmax, ymin:ymax]

    years = list(set([*train_bbox["year"].unique(), *test_bbox["year"].unique()]))

    for year in years:
        name = f"tile_{tile_id}_{year}"

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
                canopy = f"{folder}/canopy.tif"
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
                            {canopy}
                  """,
                    shell=True,
                )

                check_call(
                    f"gcloud storage cp {canopy} gs://gee-ramiqcom-s4g-bucket/opengeohub_summerschool_2026/canopy_density/{name}.tif",
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
