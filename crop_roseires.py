"""Stream the two selected Roseires NISAR GCOV scenes to aligned GeoTIFFs."""

import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory


WORKSPACE = Path(__file__).resolve().parent
ARCHIVE = (
    "https://nisar.asf.earthdatacloud.nasa.gov"
    "/NISAR/NISAR_L2_GCOV_PROVISIONAL_V1"
)
SCENES = {
    "2026-08-29": "NISAR_L2_PR_GCOV_029_057_A_007_2005_DHDH_A_20260829T031901_20260829T031935_P05023_N_F_J_001",
    "2026-10-16": "NISAR_L2_PR_GCOV_033_057_A_007_2005_DHDH_A_20261016T031901_20261016T031935_P05023_N_F_J_001",
}


def load_token():
    for line in (WORKSPACE / ".env").read_text(encoding="utf-8").splitlines():
        key, _, value = line.partition("=")
        if key.strip() == "EARTHDATA_TOKEN":
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
                value = value[1:-1]
            if re.fullmatch(r"[A-Za-z0-9._~+/-]+=*", value):
                return value
            break
    raise ValueError("Set EARTHDATA_TOKEN in the local .env file.")


def main():
    gdalwarp = shutil.which("gdalwarp")
    if gdalwarp is None:
        print("Install GDAL 3.9 or newer before running this script.", file=sys.stderr)
        return 1

    try:
        token = load_token()
    except (OSError, ValueError) as error:
        print(error, file=sys.stderr)
        return 1

    gdal_environment = os.environ.copy()
    gdal_environment.update(
        GDAL_HTTP_AUTH="BEARER",
        GDAL_HTTP_BEARER=token,
        GDAL_HTTP_NETRC="NO",
        GDAL_HTTP_TIMEOUT="45",
        GDAL_HTTP_MAX_RETRY="2",
        CPL_CURL_VERBOSE="NO",
        CPL_DEBUG="OFF",
        GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
    )
    output = WORKSPACE / "roseires-crops"
    output.mkdir(exist_ok=True)
    for date, scene in SCENES.items():
        target = output / f"roseires_{date}_HHHH.tif"
        if target.is_file() and target.stat().st_size > 0:
            print(f"Already saved: {target.name}")
            continue
        source = f'HDF5:"/vsicurl/{ARCHIVE}/{scene}/{scene}.h5"://science/LSAR/GCOV/grids/frequencyA/HHHH'
        with TemporaryDirectory(dir=output) as directory:
            partial = Path(directory) / target.name
            command = [
                gdalwarp, "-of", "GTiff",
                "-te_srs", "EPSG:4326", "-te", "34.35", "11.71", "34.48", "11.79",
                "-t_srs", "EPSG:32636", "-tr", "20", "20", "-r", "near",
                "-co", "COMPRESS=DEFLATE", "-co", "TILED=YES",
                "-dstnodata", "nan", source, str(partial),
            ]
            print(f"Cropping {date} ...", flush=True)
            result = subprocess.run(command, env=gdal_environment, check=False)
            if result.returncode != 0 or not partial.is_file() or partial.stat().st_size == 0:
                print(f"GDAL could not produce the {date} crop.", file=sys.stderr)
                return 1
            partial.replace(target)
        print(f"Saved: {target.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
