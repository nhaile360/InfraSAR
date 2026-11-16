#!/usr/bin/env python3
"""Inventory NASA CMR NISAR GCOV granules intersecting the Roseires study bounds."""

import argparse
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


CMR = "https://cmr.earthdata.nasa.gov/search/granules.umm_json"
BOUNDS = (34.35, 11.71, 34.48, 11.79)
COLLECTIONS = {
    "PROVISIONAL": ("NISAR_L2_GCOV_PROVISIONAL_V1", "C2854338529-ASF", "2026-06-17"),
    "VALIDATED": ("NISAR_L2_GCOV_V1", "C3622241360-ASF", "2026-10-21"),
}
PILOT_OPTICAL = {"2026-08-29": "2026-08-26", "2026-10-16": "2026-10-15"}
END = "2026-10-23"
CATALOG = Path(__file__).with_name("nisar_catalog.json")


def search(concept, start):
    params = {"collection_concept_id": concept, "bounding_box": ",".join(map(str, BOUNDS)),
              "temporal": f"{start}T00:00:00Z,{END}T23:59:59Z", "page_size": 100}
    url = f"{CMR}?{urlencode(params)}"
    headers = {}
    seen = set()
    while True:
        with urlopen(Request(url, headers=headers), timeout=35) as response:
            items = json.load(response)["items"]
            cursor = response.headers.get("CMR-Search-After")
        yield from items
        if len(items) < params["page_size"]:
            return
        if not cursor or cursor in seen:
            raise RuntimeError("CMR paging stopped before the inventory was complete.")
        seen.add(cursor)
        headers["CMR-Search-After"] = cursor


def granule(item, maturity, collection):
    meta, entry = item["meta"], item["umm"]
    attr = {a["Name"]: a["Values"] for a in entry["AdditionalAttributes"]}
    identifiers = {a["IdentifierType"]: a["Identifier"] for a in entry["DataGranule"]["Identifiers"]}
    start_end = entry["TemporalExtent"]["RangeDateTime"]
    acquired = start_end["BeginningDateTime"]
    identity = entry["GranuleUR"]
    mode = identity.split("_")[9]
    track = int(attr["TRACK_NUMBER"][0])
    frame = int(attr["FRAME_NUMBER"][0])
    direction = attr["ASCENDING_DESCENDING"][0]
    pol = attr["FREQUENCY_A_POLARIZATION"]
    bandwidth = int(attr["FREQUENCY_A_RANGE_BANDWIDTH"][0])
    version, release = attr["PRODUCT_VERSION"][0], identifiers.get("CRID")
    archive = next(a for a in entry["DataGranule"]["ArchiveAndDistributionInformation"]
                   if a["Name"] == identity + ".h5")
    url = next(a["URL"] for a in entry["RelatedUrls"]
               if a["Type"] == "GET DATA" and a["URL"].endswith("/" + archive["Name"]))
    geometry = entry["SpatialExtent"]["HorizontalSpatialDomain"]["Geometry"]
    optical = PILOT_OPTICAL.get(acquired[:10]) if (track, direction, frame) == (57, "ASCENDING", 7) else None
    if (track, direction, frame) != (57, "ASCENDING", 7):
        status = "different track, direction or frame"
    elif (maturity, version, release, bandwidth) != ("PROVISIONAL", "1.0.11", "P05023", 20) or "HH" not in pol:
        status = "different product, release, bandwidth or missing HH"
    elif optical:
        status = "verified pilot"
    else:
        status = "awaiting native HH verification"
    return {"concept_id": meta["concept-id"], "cmr_revision": meta["revision-id"], "id": identity,
            "collection": collection, "maturity": maturity, "datetime": acquired, "end": start_end["EndingDateTime"],
            "track": track, "direction": direction, "frame": frame, "frequency_a_mhz": bandwidth,
            "frequency_a_polarizations": pol, "mode": mode, "version": version, "release": release,
            "footprint": geometry, "source_url": url, "source_size_bytes": archive["SizeInBytes"],
            "source_checksum": archive.get("Checksum"), "optical_date": optical, "status": status}


def inventory():
    rows = []
    queries = {}
    for maturity, (collection, concept, start) in COLLECTIONS.items():
        fetched = list(search(concept, start))
        queries[maturity] = {"collection": collection, "concept_id": concept, "start": start,
                             "end_inclusive": END, "hits": len(fetched)}
        rows.extend(granule(item, maturity, collection) for item in fetched)
    return {"bounding_box_lon_lat": BOUNDS, "queries": queries,
            "granules": sorted(rows, key=lambda row: (row["datetime"], row["id"]))}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=CATALOG)
    args = parser.parse_args()
    args.output.write_text(json.dumps(inventory(), indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
