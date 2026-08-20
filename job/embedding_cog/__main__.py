import json
from concurrent.futures import ThreadPoolExecutor
from subprocess import check_call, check_output
from tempfile import TemporaryDirectory

import geopandas as gpd

from ..utils import logger

BUCKET_PREFIX = "gee-ramiqcom-s4g-bucket/opengeohub_summerschool_2026"
TILES = f"https://storage.googleapis.com/{BUCKET_PREFIX}/roi/tiles_v2.geojson"
META_PREFIX = "dataforgood-fb-data/forests/v2/global/dinov3_global_chm_v2_ml3"
TILES_EMBEDDING = (
    "gs://alphaearth_foundations/satellite_embedding/v1/annual/aef_index.gpkg"
)
RESOLUTION = 10

folder = TemporaryDirectory(delete=False)
TILES_LOCAL = f"{folder.name}/TILES_LOCAL.gpkg"
check_call(f"gcloud storage cp {TILES_EMBEDDING} {TILES_LOCAL}", shell=True)

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


def reproject(path, bbox):
    folder = TemporaryDirectory(delete=False)
    o = f"{folder.name}/o.tif"
    check_call(
        f"""gdal raster reproject \
            -r lanczos \
            --bbox-crs=EPSG:4326 \
            --resolution={RESOLUTION / 111_000},{RESOLUTION / 111_000} \
            --bbox={bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]} \
            -f COG \
            -d EPSG:4326 \
            --co="COMPRESS=ZSTD" \
            {path} \
            {o} \
        """,
        shell=True,
    )
    return o


def run_per_tile(index):
    tile_id = tile_ids[index]

    logger.info(f"Run tile {tile_id} {index + 1} / {len(tile_ids)}")

    bbox = tuple(tiles_df.iloc[index : index + 1].total_bounds)

    with TemporaryDirectory() as folder:
        logger.info("Filter tiles")
        read_tiles = json.loads(
            check_output(
                f"""gdal vector pipeline \
                    ! read {TILES_LOCAL} \
                    ! filter --where="year = {2020}" --bbox={bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]} \
                    ! info --features -f json \
                """,
                shell=True,
                text=True,
            )
        )["layers"][0]["features"]

        image_paths = [
            feat["properties"]["path"].replace("gs://", "/vsigs/")
            for feat in read_tiles
        ]

        logger.info("Reproject")
        with ThreadPoolExecutor(4) as executor:
            jobs = [executor.submit(reproject, path, bbox) for path in image_paths]
            results = [job.result() for job in jobs]

        logger.info("COG embedding")
        chm = f"{folder}/embedding.tif"
        check_call(
            f"""gdal raster pipeline \
                ! mosaic \
                  --resolution=average \
                  {" ".join(results)} \
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

        logger.info("Upload Embedding")
        check_call(
            f"gcloud storage cp {chm} gs://{BUCKET_PREFIX}/embedding/{tile_id}.tif",
            shell=True,
        )


if __name__ == "__main__":
    main()
