# InfraSAR at Roseires

Open `roseires-shoreline-comparator.html` in a current desktop or mobile browser. The explorer opens on the August and October NISAR passes. Drag the handle, use its arrow keys, and choose **Show reservoir** to find the dam northwest of the study inlet.

The standalone HTML carries the original 20 m NISAR radar, frozen radar classifications, and DAHITI station 216 values. It can fetch the four public Sentinel‑2 classifications. **Data details** also accepts the scored pipeline comparator and the original aligned mask. Imported HTML is read as raster data. The terrain basemap is retrieved separately when internet access is available.

## Make an offline copy with the processed pilot observations

From the extracted pipeline folder, run:

```sh
conda run --no-capture-output -n roseires-pipeline python roseires-visuals/build_infrasar.py \
  --pilot roseires-pipeline/outputs/pilot/comparator.html \
  --patch ../roseires_outlined_patch_mask.tif
open roseires-visuals/roseires-shoreline-comparator.html
```

Leave off `--patch` if that file is elsewhere. The explorer can recover the outline from the original study window if the water map reproduces both the 108-cell extent and the reported median. If the revised mosaic changed the outline, supply the original mask. To add a scored holdout, pass `--observations roseires-pipeline/outputs/holdout/comparator.html` when building. Timeline markers come from the files loaded and use the actual acquisition dates. The date scrubber also includes DAHITI observations.

The two original single-tile SCL exports can be embedded using `--august-scl` and `--october-scl` when a scored comparator is unavailable. The explorer computes usable coverage from the classes available on both dates.
