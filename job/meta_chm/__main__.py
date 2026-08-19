import json
from concurrent.futures import ThreadPoolExecutor
from subprocess import check_call, check_output
from tempfile import TemporaryDirectory

import geopandas as gpd

from ..utils import logger

BUCKET_PREFIX = "gee-ramiqcom-s4g-bucket/opengeohub_summerschool_2026"
TILES = f"https://storage.googleapis.com/{BUCKET_PREFIX}/roi/tiles_v2.geojson"
META_PREFIX = "dataforgood-fb-data/forests/v2/global/dinov3_global_chm_v2_ml3"
TILES_CHM = f"/vsis3/{META_PREFIX}/tiles.geojson"
CHM_PREFIX = f"/vsis3/{META_PREFIX}/chm"
RESOLUTION = 10

tiles_df = gpd.read_file(TILES)
tile_ids = tiles_df["tile_id"].unique()


def main():
    with ThreadPoolExecutor(8) as executor:
        jobs = []
        for index in range(len(tile_ids)):
            jobs.append(executor.submit(run_per_tile, index))

        for job in jobs:
            try:
                job.result()
            except Exception as e:
                logger.info(f"Error: {e}")


def run_per_tile(index):
    tile_id = tile_ids[index]

    logger.info(f"Run tile {tile_id} {index + 1} / {len(tile_ids)}")

    bbox = tuple(tiles_df.iloc[index : index + 1].total_bounds)

    with TemporaryDirectory() as folder:
        logger.info("Filter tiles")
        read_tiles = json.loads(
            check_output(
                f"""gdal vector pipeline \
                    ! read {TILES_CHM} \
                    ! filter --bbox={bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]} \
                    ! info --features -f json \
                """,
                shell=True,
                text=True,
            )
        )["layers"][0]["features"]

        image_paths = [
            f"{CHM_PREFIX}/{feat['properties']['tile']}.tif" for feat in read_tiles
        ]

        logger.info("COG CHM")
        chm = f"{folder}/chm.tif"
        check_call(
            f"""gdal raster pipeline \
                ! mosaic \
                  --resolution=average \
                  {" ".join(image_paths)} \
                ! reproject \
                  -r lanczos \
                  -d EPSG:4326 \
                  --resolution={RESOLUTION / 111_000},{RESOLUTION / 111_000} \
                  --bbox-crs=EPSG:4326 \
                  --bbox={bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]} \
                ! write \
                  -f COG \
                  --co="COMPRESS=ZSTD" \
                  --co="STATISTICS=YES" \
                  --co="OVERVIEWS=IGNORE_EXISTING" \
                  --co="OVERVIEW_RESAMPLING=LANCZOS" \
                  --co="RESAMPLING=LANCZOS" \
                  {chm} \
            """,
            shell=True,
        )

        logger.info("Upload CHM")
        check_call(
            f"gcloud storage cp {chm} gs://{BUCKET_PREFIX}/meta_chm/{tile_id}.tif",
            shell=True,
        )


if __name__ == "__main__":
    main()
