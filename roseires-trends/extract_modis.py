#!/usr/bin/env python3
"""Extract Roseires monthly reservoir area and provenance from the local MOD28C3 archive."""

import argparse
import csv
from datetime import date, timedelta
import hashlib
from pathlib import Path
import re

from analyze_modis import CSV_PATH


ARCHIVE = Path(__file__).resolve().parents[1] / "data" / "MOD28C3"
GRANULE = re.compile(r"MOD28C3\.A(\d{4})(\d{3})\.061\.(\d{13})\.hdf")
FIELDS = ("month_utc", "lake_id", "grand_id", "dam_longitude_deg", "dam_latitude_deg",
          "lake_area_km2", "source_lake_area_km2", "status", "source_granule", "granule_sha256")


def granules_by_month(directory):
    by_month = {}
    for path in sorted(directory.glob("MOD28C3.A*.061.*.hdf")):
        match = GRANULE.fullmatch(path.name)
        if not match:
            raise ValueError(f"Invalid MOD28C3.061 filename: {path.name}")
        year, day = (int(value) for value in match.groups()[:2])
        month = date(year, 1, 1) + timedelta(days=day - 1)
        if month.year != year or month.day != 1:
            raise ValueError(f"Expected a first-of-month granule: {path.name}")
        # The final filename component is the production timestamp.
        by_month[month] = path
    if not by_month:
        raise ValueError(f"No MOD28C3.061 HDF files in {directory}")
    return by_month


def read_granule(path, hdf, read_mode):
    file = hdf(str(path), read_mode)
    try:
        tables = file.vstart()
        try:
            table = tables.attach("lake_evaporation")
            try:
                fields = ("lake_ID", "lake_longitude", "lake_latitude", "lake_area")
                area_index = table._fields.index("lake_area")
                fill = float(table.attr("_FillValue").get().split(",")[area_index])
                table.setfields(*fields)
                matches = [row for row in table.read(table._nrecs) if row[0] == 111]
            finally:
                table.detach()
        finally:
            tables.end()
    finally:
        file.close()
    if len(matches) != 1:
        raise ValueError(f"Expected a single lake ID 111 in {path.name}")
    _, longitude, latitude, area = matches[0]
    if abs(longitude - 34.39) > .01 or abs(latitude - 11.798) > .01:
        raise ValueError(f"Lake ID 111 does not match Roseires in {path.name}")
    missing = area == fill
    return {
        "dam_longitude_deg": longitude, "dam_latitude_deg": latitude,
        "lake_area_km2": None if missing else area, "source_lake_area_km2": area,
        "status": "fill_value" if missing else "published", "source_granule": path.name,
        "granule_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def extract(directory, output):
    try:
        from pyhdf.HDF import HDF, HC
        import pyhdf.VS  # Registers the Vdata interface used by HDF.vstart().
    except ImportError as error:
        raise RuntimeError("Install PyHDF to read the original HDF4 files.") from error
    granules = granules_by_month(directory)
    month = min(granules)
    rows = []
    while month <= max(granules):
        row = {"month_utc": month.isoformat()[:7], "lake_id": 111, "grand_id": 4483, "status": "no_granule"}
        if month in granules:
            row.update(read_granule(granules[month], HDF, HC.READ))
        rows.append(row)
        month = (month + timedelta(days=32)).replace(day=1)
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=ARCHIVE)
    parser.add_argument("--output", type=Path, default=CSV_PATH)
    args = parser.parse_args()
    extract(args.input_dir, args.output)


if __name__ == "__main__":
    main()
