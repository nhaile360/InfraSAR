# InfraSAR at Roseires

Open `InfraSAR-Roseires.html` at the repository root in a current desktop or mobile browser. The explorer opens on the August and October NISAR passes. Drag the handle, use its arrow keys, and choose **Show reservoir** to find the dam northwest of the study inlet. **Investigate historical rainfall** opens the NASA POWER analysis.

The standalone HTML carries the original 20 m NISAR radar, frozen radar classifications, both Sentinel‑2 tiles for each optical date, the scored pilot, the original inlet mask, DAHITI station 216 values, and the [NASA POWER analysis](../roseires-trends/README.md). **Data details** also accepts scientific observations. Imported HTML is read as raster data. The terrain basemap is retrieved separately when internet access is available.

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
