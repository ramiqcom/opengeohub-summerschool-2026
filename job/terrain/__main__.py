from concurrent.futures import ThreadPoolExecutor
from subprocess import check_call, check_output
from tempfile import TemporaryDirectory

from ..utils import logger

DEM = "/vsigs/gee-ramiqcom-s4g-bucket/opengeohub_summerschool_2026/nasadem/opengeohub_summerschool_2026_NASADEM_30m.tif"

with ThreadPoolExecutor(8) as executor:
  jobs = []
