# Roseires shoreline change

See the [NISAR timeline inventory and extraction workflow](NISAR_TIMELINE.md) for the full CMR search and individual HH observations.

Use the two independent change maps to examine agreement at an inlet or across the full 711 × 446 cell NISAR crop. The optical map is a comparison reference. Clouds, shadow, ambiguous classes, tile gaps, source no-data and conflicting overlap labels remain visible.

## Start with 36PXU

Create the environment once on each computer. From the project directory containing
`roseires-pipeline/` and `roseires-crops/`, run:

```bash
conda env create -f roseires-pipeline/environment.yml
conda run --no-capture-output -n roseires-pipeline python roseires-pipeline/pipeline.py extract --pair pilot
```

If Conda is missing, install [Miniforge](https://github.com/conda-forge/miniforge#macos)
for your Mac, initialize the shell when prompted, and open a new Terminal window.
If the environment already exists, skip the create command. The environment supplies Python,
GDAL, and the HDF5 driver. The pipeline finds GDAL on its PATH.

The extractor looks for the Sentinel-2C acquisitions on **August 26** and **October 15, 2026**. It requires 36PXT and 36PXU from the same platform and pass, crops their SCL bands onto the original NISAR grid using nearest-neighbor resampling, and records source IDs, UTC acquisition times, per-tile raster crops and UTM bounds in `outputs/pilot`. It reports the share of the full crop with usable optical classes on both dates.

If the catalog does not resolve the two tiles, supply a JSON file with the exact scene IDs, UTC timestamps and SCL paths or public HTTPS URLs. The JSON is keyed by **radar date**, then by **tile**. Repeat this structure for the October epoch. Relative paths are resolved beside the manifest. Example structure (replace the UTC placeholders with the actual acquired times):

```json
{
  "2026-08-29": {
    "36PXT": {"id": "S2C_36PXT_20260826_0_L2A", "datetime": "2026-08-26T<actual time>Z", "scl": "aug_36PXT_20260826_SCL.tif"},
    "36PXU": {"id": "<verified scene ID>", "datetime": "<verified UTC time>", "scl": "aug_36PXU_20260826_SCL.tif"}
  }
}
```

Pass it with `--optical-manifest path/to/manifest.json`. Use original tile SCL rasters with the tile footprint intact. An already padded, single-tile export can obscure the origin of its missing values.

## Make the comparison

```bash
conda run --no-capture-output -n roseires-pipeline python roseires-pipeline/pipeline.py predict --pair pilot
conda run --no-capture-output -n roseires-pipeline python roseires-pipeline/pipeline.py score --pair pilot
open roseires-pipeline/outputs/pilot/comparator.html
```

The radar stage reads only HH rasters. It freezes GeoTIFFs and their hashes in `radar_predictions.json` before scoring. Fixed baseline: water at HH ≤ −17 dB. Local rule: 3 × 3 median, per-date midpoint between the open-water 90th percentile and land 10th percentile in predeclared radar control areas, ±0.75 dB ambiguity band. If the control distributions overlap within that band, the local rule abstains. These are candidate rules for this pilot.

In overlap, a usable classification is preferred. A land/water conflict remains uncertain, and the viewer exposes both underlying tile codes. Usable optical classes are 4/5 for land and 6 for water. Class 7 is ambiguous (including possible low-probability cloud), and classes 8–10 are cloud. Optical missing coverage maps to 255 inside the raw merged SCL band. Optical class 0 is source no-data. In the comparison, radar changes over invalid optical pixels are unverified. Counts for each direction include misses where radar abstains; false alarms are measured only where the optical reference is usable.

## Run the separate date pair

```bash
conda run --no-capture-output -n roseires-pipeline python roseires-pipeline/pipeline.py fetch-radar --pair holdout
conda run --no-capture-output -n roseires-pipeline python roseires-pipeline/pipeline.py all --pair holdout
open roseires-pipeline/outputs/holdout/comparator.html
```

The holdout uses NISAR **August 17 and October 4, 2026**, the same track, frame, polarization and processing version with neither pilot radar scene reused. It chooses the nearest co-acquired optical tile pair within three calendar days of each radar date, using acquisition time rather than the agreement score. Radar download uses the existing local Earthdata token. Keep the pilot prediction policy fixed before running the holdout. The viewer lets you switch radar rules and click a cell to inspect HH values, optical classes and acquisition dates.
