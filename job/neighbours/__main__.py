from concurrent.futures import ThreadPoolExecutor
from subprocess import check_call, check_output
from tempfile import TemporaryDirectory

from ..utils import logger

PREFIX_S2 = "gs://gee-ramiqcom-s4g-bucket/opengeohub_summerschool_2026/s2"
PREFIX_S1 = "gs://gee-ramiqcom-s4g-bucket/opengeohub_summerschool_2026/s1"

S2_LIST = check_output(f"gcloud storage ls {PREFIX_S2}", shell=True, text=True).split(
    "\n"
)[:-1]
S2_LIST = [path.replace("gs://", "/vsigs/") for path in S2_LIST]

S1_LIST = check_output(f"gcloud storage ls {PREFIX_S1}", shell=True, text=True).split(
    "\n"
)[:-1]
S1_LIST = [path.replace("gs://", "/vsigs/") for path in S1_LIST]


def neighbours(path):
    with TemporaryDirectory() as folder:
        mean = f"{folder}/mean.tif"
        std = f"{folder}/std.tif"

        logger.info(f"Run mean {path}")
        check_call(
            f"""gdal raster neighbours --method=mean --size=3 --kernel=equal -f COG {path} {mean}""",
            shell=True,
        )

        logger.info(f"Run std {path}")
        check_call(
            f"""gdal raster neighbours --method=stddev --size=3 --kernel=equal -f COG {path} {std}""",
            shell=True,
        )

        logger.info(f"Run distance {path}")
        distance = f"{folder}/distance.tif"
        check_call(
            f"""gdal raster calc -f COG -i "A={mean}" -i "B={std}" --calc="A - B" --propagate-nodata --ot=Float32 -o {distance} """,
            shell=True,
        )

        logger.info(f"Upload {path}")
        check_call(
            f"gcloud storage cp {distance} {path.replace('/vsigs/', 'gs://').replace('/s2/', '/s2_distance/').replace('/s1/', '/s1_distance/')}",
            shell=True,
        )


with ThreadPoolExecutor(8) as executor:
    jobs = []
    for path in [*S2_LIST, *S1_LIST]:
        jobs.append(executor.submit(neighbours, path))
    for job in jobs:
        try:
            job.result()
        except Exception as e:
            logger.info(f"Error: {e}")
