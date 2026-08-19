from concurrent.futures import ThreadPoolExecutor
from subprocess import check_call
from tempfile import TemporaryDirectory

from ..utils import logger

DEM = "/vsigs/gee-ramiqcom-s4g-bucket/opengeohub_summerschool_2026/nasadem/opengeohub_summerschool_2026_NASADEM_30m.tif"

with TemporaryDirectory() as folder:
    slope = f"{folder}/slope.tif"
    aspect = f"{folder}/aspect.tif"
    tri = f"{folder}/tri.tif"
    tpi = f"{folder}/tpi.tif"
    hillshade = f"{folder}/hillshade.tif"

    logger.info("Run terrain analysis")
    with ThreadPoolExecutor(8) as executor:
        jobs = [
            executor.submit(
                check_call,
                f"gdal raster slope  --xscale=111120 --yscale=111120 --unit=percent {DEM} {slope}",
                shell=True,
            ),
            executor.submit(
                check_call,
                f"gdal raster aspect {DEM} {aspect}",
                shell=True,
            ),
            executor.submit(
                check_call,
                f"gdal raster hillshade --variant=multidirectional --xscale=111120 --yscale=111120 {DEM} {hillshade}",
                shell=True,
            ),
            executor.submit(
                check_call,
                f"gdal raster tri {DEM} {tri}",
                shell=True,
            ),
            executor.submit(
                check_call,
                f"gdal raster tpi {DEM} {tpi}",
                shell=True,
            ),
        ]

        for job in jobs:
            try:
                job.result()
            except Exception as e:
                logger.info(f"Error: {e.args}")

    logger.info("Create stack")
    stack = f"{folder}/terrain.tif"
    check_call(
        f"""gdal raster pipeline \
            ! stack {" ".join([slope, aspect, tri, tpi, hillshade])} \
            ! set-type --ot=Float32 \
            ! reproject --dst-nodata=NaN \
            ! write -f COG --co="COMPRESS=ZSTD" {stack}
            """,
        shell=True,
    )

    logger.info("Upload COG")
    check_call(
        f"gcloud storage cp {stack} gs://gee-ramiqcom-s4g-bucket/opengeohub_summerschool_2026/terrain/terrain.tif",
        shell=True,
    )
