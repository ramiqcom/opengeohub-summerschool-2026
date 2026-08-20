from concurrent.futures import ThreadPoolExecutor
from subprocess import check_call
from tempfile import TemporaryDirectory

import geopandas as gpd

from ..utils import logger

OUTPUT_VOLUME = "/usr/src/app/output"

ROI = "https://storage.googleapis.com/gee-ramiqcom-s4g-bucket/opengeohub_summerschool_2026/roi/tiles_v2.geojson"

CLOUD_PREFIX = "gs://gee-ramiqcom-s4g-bucket/opengeohub_summerschool_2026"
RESOLUTION = 10

TRAIN_PARQUET = f"{OUTPUT_VOLUME}/train_only_biomass.parquet"
TEST_PARQUET = f"{OUTPUT_VOLUME}/test_only_biomass.parquet"
GRIDS = "https://storage.googleapis.com/gee-ramiqcom-s4g-bucket/opengeohub_summerschool_2026/roi/tiles_v2.geojson"

logger.info("Load grids")
grids_df = gpd.read_file(GRIDS)

logger.info("Load train sample")
train_df = gpd.read_parquet(TRAIN_PARQUET)

logger.info("Load test")
test_df = gpd.read_parquet(TEST_PARQUET)

tile_ids = grids_df["tile_id"].unique()

year = 2020

data_id = ""
if year == 2021:
    data_id = 15032553
elif year == 2020:
    data_id = 15032488
elif year == 2019:
    data_id = 15032448
elif year == 2018:
    data_id = 15032393
elif year == 2017:
    data_id = 15032307

paths = [
    f"https://zenodo.org/records/{data_id}/files/Predicted_tree_coverage_ratio_from_GEDI_Sentinel_based_UNET_model_{year}_batch_{no}.tif?download=1"
    for no in range(14)
]


def download(path):
    folder = TemporaryDirectory(delete=False)
    o = f"{folder.name}/output.tif"
    check_call(f"curl {path} -X GET -o {o}", shell=True)
    return o


logger.info("Download all data")

with ThreadPoolExecutor(8) as executor:
    jobs = [executor.submit(download, path) for path in paths]
    results = [job.result() for job in jobs]

logger.info("Create VRT")

folder = TemporaryDirectory(delete=False)
vrt = f"{folder.name}/tree.vrt"
check_call(f"""gdal raster mosaic -f VRT {" ".join(results)} {vrt}""", shell=True)


def load_tree(index):
    grid = grids_df[index : index + 1]
    tile_id = grid.iloc[0]["tile_id"]

    logger.info(f"Run {tile_id} {index + 1} / {len(tile_ids)}")

    xmin, ymin, xmax, ymax = tuple(grid.total_bounds)

    name = f"tile_{tile_id}"

    with TemporaryDirectory() as folder:
        canopy = f"{folder}/tree.tif"
        check_call(
            f"""gdal raster pipeline \
                ! read {vrt} \
                ! reproject -d EPSG:4326 --bbox-crs=EPSG:4326 --bbox={xmin},{ymin},{xmax},{ymax} \
                ! write -f COG --co="COMPRESS=ZSTD" {canopy} \
          """,
            shell=True,
        )

        check_call(
            f"gcloud storage cp {canopy} gs://gee-ramiqcom-s4g-bucket/opengeohub_summerschool_2026/gedi_tree_ratio/{name}.tif",
            shell=True,
        )


with ThreadPoolExecutor(8) as executor:
    jobs = []
    for index in range(len(tile_ids)):
        jobs.append(executor.submit(load_tree, index))

    for job in jobs:
        try:
            job.result()
        except Exception as e:
            logger.info(f"Error: {e}")
