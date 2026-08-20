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


def load_als(index):
    grid = grids_df[index : index + 1]
    tile_id = grid.iloc[0]["tile_id"]

    logger.info(f"Run {tile_id} {index + 1} / {len(tile_ids)}")

    xmin, ymin, xmax, ymax = tuple(grid.total_bounds)

    train_bbox = train_df.cx[xmin:xmax, ymin:ymax]
    test_bbox = test_df.cx[xmin:xmax, ymin:ymax]

    years = list(set([*train_bbox["year"].unique(), *test_bbox["year"].unique()]))

    for year in years:
        name = f"tile_{tile_id}_{year}"

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
            f"/vsicurl/https://zenodo.org/records/{data_id}/files/Predicted_tree_coverage_ratio_from_GEDI_Sentinel_based_UNET_model_{year}_batch_{index}.tif?download=1"
            for no in range(14)
        ]

        with TemporaryDirectory() as folder:
            text = f"{folder}/tree.txt"
            with open(text, "w") as file:
                file.write("\n".join(paths))

            canopy = f"{folder}/tree.tif"
            check_call(
                f"""gdal raster pipeline \
                    ! mosaic --resolution=average @{text} \
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
        jobs.append(executor.submit(load_als, index))

    for job in jobs:
        try:
            job.result()
        except Exception as e:
            logger.info(f"Error: {e}")
