# Roseires NISAR acquisition inventory

The [catalog snapshot](nisar_catalog.json) contains every NASA CMR hit for the study bounds (34.35° E, 11.71° N to 34.48° E, 11.79° N) and the requested window. It records UTC start and stop, scene and CMR identifiers, footprint polygons, product settings, source links, file sizes and CMR checksums. A catalog footprint intersects the study bounds before any claim about usable HH cells can be made.

- [PROVISIONAL GCOV, June 17–October 23, 2026](https://cmr.earthdata.nasa.gov/search/concepts/C2854338529-ASF.html) returned 38 granules. All report GCOV 1.0.11, release P05023.
- [VALIDATED GCOV, October 21–23, 2026](https://cmr.earthdata.nasa.gov/search/concepts/C3622241360-ASF.html) returned zero for these bounds. [ASF documents the separate validated collection](https://nisar-docs.asf.alaska.edu/availability-overview/).
- Excluded from the pilot-compatible set were 10 hits on ascending track 129 frame 008, nine on descending track 122 frame 082 and nine on descending track 122 frame 083. Different viewing geometry can change backscatter independently of the inlet.

## Ascending track 057, frame 007

All ten entries have Frequency A HH and 20 MHz range bandwidth in CMR. SHSH has HH only and DHDH has HH and HV. Eight new scenes were extracted via authenticated HTTP range reads. Each verified GeoTIFF has 317,106 usable Float32 HH cells, including all 108 cells of the fixed inlet outline. The manifest records the common native-to-study cell-center offset of −5.104 m east and +1.975 m north.

| Start UTC in 2026 | CMR granule | Mode | Status | Independent optical evidence in InfraSAR |
| --- | --- | --- | --- | --- |
| Jun 18 03:19:04 | G4248910954-ASF | SHSH | Verified radar-only | — |
| Jun 30 03:19:03 | G4242802037-ASF | DHDH | Verified radar-only | — |
| Jul 12 03:19:03 | G4257667130-ASF | DHDH | Verified radar-only | — |
| Jul 24 03:19:02 | G4260716822-ASF | DHDH | Verified radar-only | — |
| Aug 17 03:19:01 | G4285211632-ASF | DHDH | Verified radar-only holdout | — |
| Aug 29 03:19:01 | G4293121640-ASF | DHDH | Published pilot | Sentinel‑2 Aug 26 |
| Sep 10 03:19:00 | G4308125414-ASF | DHDH | Verified radar-only | — |
| Sep 22 03:19:00 | G4321351928-ASF | SHSH | Verified radar-only | — |
| Oct 4 03:19:00 | G4343127383-ASF | DHDH | Verified radar-only holdout | — |
| Oct 16 03:19:01 | G4374297537-ASF | DHDH | Published pilot | Sentinel‑2 Oct 15 |

The [crop manifest](outputs/timeline/manifest.json) records SHA-256 hashes and CMR provenance for the eight standalone GeoTIFFs. All ten published passes are provisional. Only the two pilot passes have independently paired Sentinel‑2 evidence in InfraSAR. The catalog has no matching August 5 granule.

## What the sequence shows

Summarize each observation with the median of its 108 inlet cells. For each pair, subtract the earlier dB value from the later dB value at each of those same cells, then take the median and quartiles of the differences. Compare consecutive observations **within** each polarization mode.

| UTC date in 2026 | Mode | Median HH (dB) | Median change from preceding pass of the same mode (dB) |
| --- | --- | ---: | ---: |
| Jun 18 | SHSH | −18.97 | — |
| Jun 30 | DHDH | −19.47 | — |
| Jul 12 | DHDH | −17.28 | +2.15 |
| Jul 24 | DHDH | −17.51 | −0.20 |
| Aug 17 | DHDH | −10.22 | +7.28 |
| Aug 29 | DHDH | −11.92 | −1.30 |
| Sep 10 | DHDH | −19.57 | −8.56 |
| Sep 22 | SHSH | −20.21 | −0.99 |
| Oct 4 | DHDH | −18.01 | +1.65 |
| Oct 16 | DHDH | −16.32 | +2.22 |

The pilot's Aug 29–Oct 16 cellwise median decrease of 4.32 dB fell within a more variable DHDH sequence. The largest adjacent median decrease was 8.56 dB between Aug 29 and Sep 10, followed by increases through mid-October. The differences varied across cells, and the observations are spaced weeks apart. The two SHSH observations have their own comparison. Independent evidence would be needed to attribute the radar-only changes to water transitions.

## Reproduce

Use the existing `roseires-pipeline` environment, with GDAL HDF5 support. Run from the repository root on a machine that can resolve NASA's endpoints.

```sh
conda run -n roseires-pipeline python roseires-pipeline/catalog_nisar.py
conda run -n roseires-pipeline python roseires-pipeline/extract_nisar.py \
  2026-08-17 2026-10-04 2026-09-10 2026-09-22 \
  2026-06-18 2026-06-30 2026-07-12 2026-07-24
conda run -n roseires-pipeline python roseires-pipeline/analyze_nisar_timeline.py
conda run -n roseires-pipeline python scripts/build_site.py
```

The extractor reads `EARTHDATA_TOKEN` from `.env` in the repository or its parent (or the file given by `--env-file`). Use `--source-dir data/NISAR` to extract from downloaded originals and verify complete-file checksums against CMR. When streaming, the full-file checksum stays marked unverified. The manifest records the crop SHA-256, the native source window and grid offset, no-data, and the number of usable cells across the crop and within the 108-cell outline.

The extractor requires a north-up Float32 20 m UTM 36N dataset and selects the nearest native sample for each study-grid cell at the same spacing. It writes only the source window with the study-grid georeference and lossless compression. The site build checks scan timing, product metadata, checksums, grid and coverage before embedding dB values derived from the linear power GeoTIFF. Radar smoothing remains a display control. The verified crops and manifest are tracked in `outputs/timeline/`. Keep source HDF5s in the ignored `data/NISAR/` directory.

The timeline accepts individual radar files without a companion optical observation. To export those files for local browser import, run `build_infrasar.py --radar-json-dir <directory>` with the desired standalone build arguments. Swipe requires matching geometry, maturity, product version, release and polarization mode. The outline is the fixed pilot area. The new observations are evidence of backscatter levels, with any classification or repeated inundation requiring additional validation. The whole-crop pilot scores and the NASA POWER and MODIS investigations use their existing data and methods.
