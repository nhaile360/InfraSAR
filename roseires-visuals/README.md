# InfraSAR at Roseires

Open `InfraSAR-Roseires.html` at the repository root or use the [deployed explorer](https://nhaile360.github.io/InfraSAR/). **2026 shoreline** opens the August and October Sentinel‑2 water maps. Switch to **Radar image** to compare the NISAR passes. Drag the divider or use its arrow keys, Home and End. Drag the map to pan, use the zoom buttons or pinch on touch screens. **Show reservoir** fits the full shoreline reference, and **Hide study layers** shows the context alone. **Long-term observations** opens the NASA POWER rainfall and MODIS reservoir surface-area analyses.

**Compare locations** starts with the inlet and a nearby spot classified as land on both dates. Choose which point to move, then tap the map or drag a marker. The active card shows that location's HH backscatter, optical classes and change between dates. Use **Show both** to fit the two points or **Reset examples** to restore the original comparison. The **Timeline** controls the map and reading charts. When more than two observations from one sensor are loaded, select two dates from that sensor on the timeline to open them in **Swipe dates**.

The standalone HTML carries the 20 m NISAR radar values in dB, frozen radar classifications, both Sentinel‑2 tiles for each optical date, the scored pilot, the original inlet mask, DAHITI station 216 values, the HydroLAKES shoreline, and the [NASA POWER analysis](../roseires-trends/README.md). **Data details** links to the original HH power GeoTIFFs and accepts scientific observations. Imported HTML is read as raster data. When online, the main map requests Esri World Topographic Map imagery for the visible extent and zoom level. It draws the cached overview as you pan into areas that are still loading. The shoreline, footprint and location markers remain available offline.

## Radar display and provenance

The [August 29](https://cmr.earthdata.nasa.gov/search/concepts/G4293121640-ASF.umm_json) and [October 16](https://cmr.earthdata.nasa.gov/search/concepts/G4374297537-ASF.umm_json) ASF records identify NISAR L-band L2 Provisional GCOV V1, product version **1.0.11**, composite release **P05023**, ascending track 57, frame 7. Both have 20 MHz Frequency A and dual HH/HV polarizations. The site uses the `/science/LSAR/GCOV/grids/frequencyA/HHHH` HH power diagonal, a multilooked, terrain-corrected gamma-zero measurement. The [ASF guide](https://nisar-docs.asf.alaska.edu/gcov/#pixel-spacing) specifies 20 m posting for this bandwidth. Posting describes sample spacing. Effective spatial resolution also depends on the radar impulse response, adaptive multilooking and terrain.

The extraction requests the HDF5 band in UTM 36N at its native posting of 20 m. The 711 × 446 crop uses a geographic extent projected into UTM and nearest-neighbor sampling. Its origin is not snapped to a 20 m multiple. Nearest-neighbor sampling selects a source cell and can shift its reported center by up to half a cell in each axis when both grids use the same CRS and spacing. GeoTIFF Float32 storage and Deflate compression are lossless. The builder converts positive HH power to dB with `10 × log10(power)` and stores that Float32 array with zlib. Both embedded arrays match that conversion from the GeoTIFF for all 317,106 cells per scene. ASF requires Earthdata login for direct HDF5 reads, so the original HDF5 values were not separately re-read for this audit.

Coherent radar leaves speckle even after the product's adaptive multilooking. The prior renderer magnified the texture with nearest-neighbor canvas scaling and clipped 4.76% of August and 2.98% of October cells above −5 dB. The new display uses a common −24 to 0 dB ramp (1.64% and 1.16% above 0 dB). **Radar display → Interpolated** interpolates display colors only. **Original cells** shows the same values with nearest-neighbor rendering. Neither mode applies a speckle filter, changes the crop or modifies the scientific comparisons. Water and change classifications retain their discrete cell boundaries. Unmeasured and uncovered cells are transparent. Clouds, shadow and ambiguous observed classes have their own legend entries.

ASF lists 10 m GCOV posting for 40 MHz acquisitions. It is not available from the 20 MHz pilot measurements. [GSLC](https://nisar-docs.asf.alaska.edu/amplitude/) posts complex single-look data more finely in some directions, with different radiometry and speckle characteristics. A terrain-corrected comparison would require its own processing and validation.

## Reservoir reference

The bundled [shoreline geometry](src/roseires-reservoir.json) is HydroLAKES v1.0 feature **1543**, Roseires Reservoir ([Messager et al., 2016](https://doi.org/10.1038/ncomms13603), [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)). It is derived from the SRTM Water Body Data layer and depicts a historical shoreline. The query recorded in the file requests its rings in EPSG:32636 with 20 m display generalization and coordinates rounded to a meter. The yellow outline is the original 108-cell inlet mask. It becomes a location marker when the exact outline is too small to read. The dashed rectangle marks the local study raster, which covers part of the reservoir.

In **Map changes**, **Compare change maps** pairs a NISAR threshold-based water-change candidate map with the Sentinel‑2 scene-class changes. The side labels show each sensor's actual observation dates. The two indicators are independent and can disagree.

## Make an offline copy with the processed pilot observations

From the repository root, regenerate the analysis and build the standalone explorer.

```sh
conda run --no-capture-output -n roseires-pipeline python roseires-trends/analyze_power.py
conda run --no-capture-output -n roseires-pipeline python roseires-visuals/build_infrasar.py \
  --pilot roseires-pipeline/outputs/pilot/comparator.html \
  --patch roseires-pipeline/outputs/pilot/inlet_patch_mask.tif \
  --output InfraSAR-Roseires.html
open InfraSAR-Roseires.html
```

Leave off `--patch` if that file is elsewhere. The explorer can recover the outline from the original study window if the water map reproduces both the 108-cell extent and the reported median. If the revised mosaic changed the outline, supply the original mask. To add a scored holdout, pass `--observations roseires-pipeline/outputs/holdout/comparator.html` when building. Timeline markers come from the files loaded and use the actual acquisition dates. The date scrubber also includes DAHITI observations.

The two original single-tile SCL exports can be embedded using `--august-scl` and `--october-scl` when a scored comparator is unavailable. The explorer computes usable coverage from the classes available on both dates.
