# Roseires NISAR acquisition inventory

The [catalog snapshot](nisar_catalog.json) contains every NASA CMR hit for the study bounds (34.35° E, 11.71° N to 34.48° E, 11.79° N) and the requested window. It records UTC start and stop, scene and CMR identifiers, footprint polygons, product settings, source links, file sizes and CMR checksums. A catalog footprint intersects the study bounds before any claim about usable HH cells can be made.

- [PROVISIONAL GCOV, June 17–October 23, 2026](https://cmr.earthdata.nasa.gov/search/concepts/C2854338529-ASF.html) returned 38 granules. All report GCOV 1.0.11, release P05023.
- [VALIDATED GCOV, October 21–23, 2026](https://cmr.earthdata.nasa.gov/search/concepts/C3622241360-ASF.html) returned zero for these bounds. [ASF documents the separate validated collection](https://nisar-docs.asf.alaska.edu/availability-overview/).
- Excluded from the pilot-compatible set were 10 hits on ascending track 129 frame 008, nine on descending track 122 frame 082 and nine on descending track 122 frame 083. Different viewing geometry can change backscatter independently of the inlet.

## Ascending track 057, frame 007

All ten entries have Frequency A HH and 20 MHz range bandwidth in CMR. SHSH has HH only and DHDH has HH and HV. The GeoTIFFs for the two pilot entries are already verified. Posting, usable overlap and crop checksums for the other eight require access to the native files.

| Start UTC in 2026 | CMR granule | Mode | Status | Independent optical evidence in InfraSAR |
| --- | --- | --- | --- | --- |
| Jun 18 03:19:04 | G4248910954-ASF | SHSH | Pending HH verification | — |
| Jun 30 03:19:03 | G4242802037-ASF | DHDH | Pending HH verification | — |
| Jul 12 03:19:03 | G4257667130-ASF | DHDH | Pending HH verification | — |
| Jul 24 03:19:02 | G4260716822-ASF | DHDH | Pending HH verification | — |
| Aug 17 03:19:01 | G4285211632-ASF | DHDH | Holdout, pending HH verification | — |
| Aug 29 03:19:01 | G4293121640-ASF | DHDH | Published pilot | Sentinel‑2 Aug 26 |
| Sep 10 03:19:00 | G4308125414-ASF | DHDH | Pending HH verification | — |
| Sep 22 03:19:00 | G4321351928-ASF | SHSH | Pending HH verification | — |
| Oct 4 03:19:00 | G4343127383-ASF | DHDH | Holdout, pending HH verification | — |
| Oct 16 03:19:01 | G4374297537-ASF | DHDH | Published pilot | Sentinel‑2 Oct 15 |

The authenticated workspace request failed to resolve the ASF hostname. An unauthenticated range request from a connected environment redirected to Earthdata Login. The supplied bearer was read locally and the request never reached NASA. Only the two verified pilot radar observations are published. The catalog has no matching August 5 granule, and the August–October signal cannot yet be placed in a verified multi-pass sequence.

## Reproduce

Use the existing `roseires-pipeline` environment, with GDAL HDF5 support. Run from the repository root on a machine that can resolve NASA's endpoints.

```sh
conda run -n roseires-pipeline python roseires-pipeline/catalog_nisar.py
conda run -n roseires-pipeline python roseires-pipeline/extract_nisar.py \
  2026-08-17 2026-10-04 2026-09-10 2026-09-22 \
  2026-06-18 2026-06-30 2026-07-12 2026-07-24
conda run -n roseires-pipeline python scripts/build_site.py
```

The extractor reads `EARTHDATA_TOKEN` from `.env` in the repository or its parent (or the file given by `--env-file`). Use `--source-dir data/NISAR` to extract from downloaded originals and verify complete-file checksums against CMR. When streaming, the full-file checksum stays marked unverified. The manifest records the crop SHA-256, the native source window and grid offset, no-data, and the number of usable cells across the crop and within the 108-cell outline.

The extractor requires a north-up Float32 20 m UTM 36N dataset and selects the nearest native sample for each study-grid cell at the same spacing. It writes only the source window with the study-grid georeference and lossless compression. The site build checks scan timing, product metadata, checksums, grid and coverage before embedding dB values derived from the linear power GeoTIFF. Radar smoothing remains a display control. Commit verified crops and the manifest in `outputs/timeline/`. Keep source HDF5s in the ignored `data/NISAR/` directory.

The timeline accepts individual radar files without a companion optical observation. To export those files for local browser import, run `build_infrasar.py --radar-json-dir <directory>` with the desired standalone build arguments. Swipe requires matching geometry, maturity, product version, release and polarization mode. The outline is the fixed pilot area. The new observations are evidence of backscatter levels, with any classification or repeated inundation requiring additional validation. The whole-crop pilot scores and the NASA POWER and MODIS investigations use their existing data and methods.
