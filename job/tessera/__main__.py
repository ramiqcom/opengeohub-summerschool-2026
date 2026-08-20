from concurrent.futures import ThreadPoolExecutor
from subprocess import check_call
from tempfile import TemporaryDirectory

import geopandas as gpd

from ..utils import MAX_WORKERS, logger

BUCKET_PREFIX = "gee-ramiqcom-s4g-bucket/opengeohub_summerschool_2026"
TILES = f"https://storage.googleapis.com/{BUCKET_PREFIX}/roi/tiles_v2.geojson"
tiles_df = gpd.read_file(TILES)
tile_ids = tiles_df["tile_id"].unique()
RESOLUTION = 10


def main():
    with ThreadPoolExecutor(int(MAX_WORKERS / 2)) as executor:
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
        logger.info("Download image")

        check_call(
            f""".venv/bin/geotessera download --bbox "{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}" --year 2020 --output {folder}/tessera""",
            shell=True,
        )

        logger.info("COG Tessera")
        cog = f"{folder}/mosaic.tif"
        check_call(
            f"""gdal raster pipeline \
                ! mosaic \
                  --resolution=average \
                  {folder}/tessera/global_0.1_degree_tiff_all/*.tiff \
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
                  {cog} \
            """,
            shell=True,
        )

        logger.info("Upload Tessera")
        check_call(
            f"gcloud storage cp {cog} gs://{BUCKET_PREFIX}/tessera/{tile_id}.tif",
            shell=True,
        )


if __name__ == "__main__":
    main()
