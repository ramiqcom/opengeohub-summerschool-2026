from concurrent.futures import ThreadPoolExecutor
from subprocess import check_call, check_output

import geopandas as gpd

from ..utils import logger

CPU_PER_PROCESS = 4
OUTPUT_LOCAL = "./output"
OUTPUT_VOLUME = "/usr/src/app/output"
CLOUD_PREFIX = "gs://gee-ramiqcom-s4g-bucket/opengeohub_summerschool_2026"
S2_CLOUD_PREFIX = f"{CLOUD_PREFIX}/s2"
S1_CLOUD_PREFIX = f"{CLOUD_PREFIX}/s1"
LST_CLOUD_PREFIX = f"{CLOUD_PREFIX}/lst"
RESOLUTION = 10

TRAIN_PARQUET = f"{OUTPUT_LOCAL}/train_only_biomass.parquet"
TEST_PARQUET = f"{OUTPUT_LOCAL}/test_only_biomass.parquet"
GRIDS = "https://storage.googleapis.com/gee-ramiqcom-s4g-bucket/opengeohub_summerschool_2026/roi/tiles_v2.geojson"

logger.info("Load grids")
grids_df = gpd.read_file(GRIDS)

logger.info("Load train sample")
train_df = gpd.read_parquet(TRAIN_PARQUET)

logger.info("Load test")
test_df = gpd.read_parquet(TEST_PARQUET)


def run_s2(name: str, roi, sql_where: str = "", dates: tuple[str, str] | None = None):
    start_date, end_date = dates

    logger.info(f"Run S2 {name}")

    cmd = f"""docker container run \
                --name s2_{name} \
                --rm \
                --cpus {CPU_PER_PROCESS} \
                -v {OUTPUT_LOCAL}:{OUTPUT_VOLUME} \
                -e S2_SOURCE=planetary_computer \
                -e S2_START_DATE={start_date} \
                -e S2_END_DATE={end_date} \
                -e S2_ROI_INPUT={roi} \
                -e S2_ROI_SQL_WHERE="{sql_where}" \
                -e S2_RESOLUTION={RESOLUTION} \
                -e S2_BANDS='["B02", "B03", "B04", "B08", "B11", "B12"]' \
                -e S2_OUTPUT_PREFIX={name} \
                eu.gcr.io/ramadhan-s4g/rs-open-source-docker-base:latest \
                .venv/bin/python -m modules.s2_l2a_composite \
    """

    check_call(cmd, shell=True)

    logger.info("Upload S2 data")
    check_call(
        f"gcloud storage cp {OUTPUT_LOCAL}/{name}*S2*.tif {S2_CLOUD_PREFIX}/",
        shell=True,
    )

    check_call(f"rm {OUTPUT_LOCAL}/{name}*S2*.tif", shell=True)


def run_lst(name: str, roi, sql_where: str = "", dates: tuple[str, str] | None = None):
    start_date, end_date = dates

    logger.info(f"Run LST {name}")

    cmd = f"""docker container run \
                --name lst_{name} \
                --rm \
                --cpus {CPU_PER_PROCESS} \
                -v {OUTPUT_LOCAL}:{OUTPUT_VOLUME} \
                -e LANDSAT_LST_SOURCE=planetary_computer \
                -e LANDSAT_LST_START_DATE={start_date} \
                -e LANDSAT_LST_END_DATE={end_date} \
                -e LANDSAT_LST_ROI_INPUT={roi} \
                -e LANDSAT_LST_ROI_SQL_WHERE="{sql_where}" \
                -e LANDSAT_LST_RESOLUTION=30 \
                -e LANDSAT_LST_OUTPUT_PREFIX={name} \
                eu.gcr.io/ramadhan-s4g/rs-open-source-docker-base:latest \
                .venv/bin/python -m modules.landsat_lst_composite \
    """

    check_call(cmd, shell=True)

    logger.info("Upload LST data")
    check_call(
        f"gcloud storage cp {OUTPUT_LOCAL}/{name}*_Landsat_LST_composite_*.tif {LST_CLOUD_PREFIX}/",
        shell=True,
    )

    check_call(f"rm {OUTPUT_LOCAL}/{name}*_Landsat_LST_composite_*.tif", shell=True)


def run_s1(name: str, roi, sql_where: str = "", dates: tuple[str, str] | None = None):
    logger.info(f"Run S1 {year}")

    cmd = f"""docker container run \
                --name s1_{name} \
                --rm \
                --cpus {CPU_PER_PROCESS} \
                -v {OUTPUT_LOCAL}:{OUTPUT_VOLUME} \
                -e S1_ROI_INPUT={roi} \
                -e S1_ROI_SQL_WHERE="{sql_where}" \
                -e S1_START_DATE="{dates[0]}" \
                -e S1_END_DATE="{dates[1]}" \
                -e S1_BANDS='["vv", "vh"]' \
                -e S1_RESOLUTION={RESOLUTION} \
                -e S1_OUTPUT_PREFIX={name} \
                eu.gcr.io/ramadhan-s4g/rs-open-source-docker-base:latest \
                .venv/bin/python -m modules.s1_rtc_composite \
        """

    check_call(cmd, shell=True)

    logger.info("Upload S1 data")
    check_call(
        f"gcloud storage cp {OUTPUT_LOCAL}/{name}*S1*.tif {S1_CLOUD_PREFIX}/",
        shell=True,
    )

    check_call(f"rm {OUTPUT_LOCAL}/{name}*S1*.tif", shell=True)


done_s2 = check_output(
    f"gcloud storage ls {S2_CLOUD_PREFIX}", shell=True, text=True
).split("\n")[:-1]
done_s2 = ["_".join(path.split("/")[-1].split("_")[:3]) for path in done_s2]

done_s1 = check_output(
    f"gcloud storage ls {S1_CLOUD_PREFIX}", shell=True, text=True
).split("\n")[:-1]
done_s1 = ["_".join(path.split("/")[-1].split("_")[:3]) for path in done_s1]

with ThreadPoolExecutor(2) as executor:
    jobs = []
    for index in range(len(grids_df)):
        grid = grids_df[index : index + 1]
        tile_id = grid.iloc[0]["tile_id"]

        xmin, ymin, xmax, ymax = tuple(grid.total_bounds)

        tile_filter = f"tile_id = '{tile_id}'"

        train_bbox = train_df.cx[xmin:xmax, ymin:ymax]
        test_bbox = test_df.cx[xmin:xmax, ymin:ymax]

        years = list(set([*train_bbox["year"].unique(), *test_bbox["year"].unique()]))

        for year in years:
            name = f"tile_{tile_id}_{year}"

            date_start = f"{year}-06-01"
            date_end = f"{year}-07-31"
            date_range = (date_start, date_end)

            if name not in done_s2:
                jobs.append(
                    executor.submit(
                        run_s2,
                        name,
                        GRIDS,
                        tile_filter,
                        date_range,
                    )
                )

            if name not in done_s1:
                jobs.append(
                    executor.submit(
                        run_s1,
                        name,
                        GRIDS,
                        tile_filter,
                        date_range,
                    )
                )

            jobs.append(
                executor.submit(
                    run_lst,
                    name,
                    GRIDS,
                    tile_filter,
                    date_range,
                )
            )

    for job in jobs:
        try:
            job.result()
        except Exception as e:
            logger.info(f"Error: {e}")
