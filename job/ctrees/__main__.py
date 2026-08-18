from concurrent.futures import ThreadPoolExecutor
from subprocess import check_call
from tempfile import TemporaryDirectory

import geopandas as gpd
import rioxarray  # noqa: F401
import xarray as xr
from arraylake import Client
from dotenv import load_dotenv

from ..utils import MAX_WORKERS, logger

load_dotenv()

CPU_PER_PROCESS = 4
OUTPUT_LOCAL = "./output"
OUTPUT_VOLUME = "/usr/src/app/output"
CLOUD_PREFIX = "gs://gee-ramiqcom-s4g-bucket/opengeohub_summerschool_2026"
CTRESS_PREFIX = f"{CLOUD_PREFIX}/ctrees_biomass"
RESOLUTION = 10

TRAIN_PARQUET = f"{OUTPUT_VOLUME}/train_only_biomass.parquet"
TEST_PARQUET = f"{OUTPUT_VOLUME}/test_only_biomass.parquet"
GRIDS = "https://storage.googleapis.com/gee-ramiqcom-s4g-bucket/opengeohub_summerschool_2026/roi/tiles.geojson"

logger.info("Load grids")
grids_df = gpd.read_file(GRIDS)

logger.info("Load train sample")
train_df = gpd.read_parquet(TRAIN_PARQUET)

logger.info("Load test")
test_df = gpd.read_parquet(TEST_PARQUET)

client = Client()
repo = client.get_repo("Space4Good/agb_ctrees")
session = repo.readonly_session(branch="main")
ds = xr.open_zarr(session.store, zarr_format=3, group="aboveground_biomass")


def filter_data(tile_id, bbox, year):
    with TemporaryDirectory() as folder:
        name = f"tile_{tile_id}_{year}"

        logger.info(f"Filter dataset {tile_id}")
        image = (
            ds.sel(
                time=f"{year}-01-01",
                y=slice(bbox[3], bbox[1]),
                x=slice(bbox[0], bbox[2]),
            )["agb"].astype("float32")
            / 10
        )

        logger.info(f"Save dataset {name}")
        raster_output = f"{folder}/output.tif"
        image = image.rio.write_crs("EPSG:4326")
        image.rio.to_raster(
            raster_output,
            driver="COG",
            compress="ZSTD",
            resampling="lanczos",
            dtype="float32",
            STATISTICS="YES",
        )

        check_call(
            f"gcloud storage cp {raster_output} {CTRESS_PREFIX}/{name}.tif",
            shell=True,
        )


with ThreadPoolExecutor(MAX_WORKERS) as executor:
    jobs = []
    for index in range(len(grids_df)):
        grid = grids_df[index : index + 1]
        xmin, ymin, xmax, ymax = tuple(grid.total_bounds)
        tile_id = grid.iloc[0]["tile_id"]
        tile_filter = f"tile_id = '{tile_id}'"

        train_bbox = train_df.cx[xmin:xmax, ymin:ymax]
        test_bbox = test_df.cx[xmin:xmax, ymin:ymax]

        years = list(set([*train_bbox["year"].unique(), *test_bbox["year"].unique()]))

        for year in years:
            jobs.append(
                executor.submit(filter_data, tile_id, (xmin, ymin, xmax, ymax), year)
            )

    for job in jobs:
        try:
            job.result()
        except Exception as e:
            logger.info(f"Error: {e}")
