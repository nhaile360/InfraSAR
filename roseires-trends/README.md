# Long-term precipitation near Roseires

InfraSAR's current long-term investigation uses NASA POWER corrected precipitation for one MERRA-2 grid cell near Roseires, Sudan. The precipitation record covers January 1981 through December 2024. Reservoir surface-area analysis is pending access to the original MODIS granules.

## Result

| Analysis | Years | Change in annual precipitation total | 95% interval | Two-sided p |
| --- | ---: | ---: | ---: | ---: |
| Primary, 1981–2024 | 44 | +1.52 mm/year | −9.99 to +13.04 mm/year | 0.795 |
| Exploratory, 1981–2002 | 22 | −17.55 mm/year | −40.37 to +5.28 mm/year | 0.132 |
| Exploratory, 2003–2024 | 22 | +48.17 mm/year | +37.09 to +59.26 mm/year | <0.001 |

The interval for the full record includes zero. The record supports calculating a long-term linear summary, with limited evidence for a steady increase or decrease. The shorter windows are sensitivity views. A level shift within a window can produce an apparent trend under a linear model.

## Source and transformations

- [NASA POWER original monthly request](https://power.larc.nasa.gov/api/temporal/monthly/point?parameters=PRECTOTCORR&community=AG&longitude=34.4673&latitude=11.7285&start=1981&end=2024&format=JSON). Retrieved November 15, 2026. The response identifies API v2.10.0, MERRA-2, local solar time, and PRECTOTCORR in mm/day. The request uses the inlet coordinates. The returned point is 11.729° N, 34.467° E, within POWER’s 0.5° latitude × 0.625° longitude meteorological grid.
- [nasa-power-roseires.json](nasa-power-roseires.json) preserves all numerical source values and response metadata in formatted JSON. It includes 528 monthly values and 44 source annual summary values with month code `13`. The source sentinel is `−999`. All 528 months passed the completeness check, including legitimate zero values.
- [power-analysis.json](power-analysis.json) records the source snapshot hash, unaltered monthly rates, the number of calendar days per month, converted monthly totals, calendar-year totals, model fits, and diagnostics. Each monthly mean rate is multiplied by the actual days in the month, including leap days. The analysis fits complete calendar-year totals. Only months 01–12 enter the fit. InfraSAR fills no gaps, removes no outliers, and applies no smoothing.
- PRECTOTCORR is an observation-corrected reanalysis estimate. It inherits limitations from the model, the underlying observing products, and their spatial support. The regression interval describes sampling uncertainty under the fitted time-series model. It does not include systematic product errors or establish that the estimate is representative of the Blue Nile catchment. [POWER data methodology](https://power.larc.nasa.gov/docs/methodology/data/sources_meteorology/) · [NASA MERRA-2 documentation](https://ntrs.nasa.gov/api/citations/20160005045/downloads/20160005045.pdf)

## Seasonal and temporal checks

June through September accounts for **77.9%** of estimated precipitation. Complete calendar-year totals include each seasonal cycle once. The slope is the change in annual accumulation, measured in millimeters per additional calendar year.

The ordinary least-squares fit has lag-one annual residual autocorrelation of approximately **0.75**. The primary interval uses Bartlett-weighted Newey–West covariance with three annual lags, the `n/(n−2)` correction, and an approximate two-sided normal test at the 5% level. One- and five-lag sensitivity checks also include zero. With 44 years and substantial serial dependence, treat the intervals as approximate. [Newey–West covariance reference](https://www.statsmodels.org/stable/generated/statsmodels.stats.sandwich_covariance.cov_hac.html)

An exploratory screen compares the full-record line with step-plus-line fits. It allows one or two changes in level, keeps at least eight years per segment, and includes two parameters per searched breakpoint in its BIC penalty. The best one-step fit starts a new segment in **2014** (ΔBIC ≈ −29.1). The best two-step fit starts new segments in **2000** and **2014** (ΔBIC ≈ −36.0). This nominal BIC comparison does not adjust for residual dependence or provide a calibrated significance test for the breakpoints. The dates are diagnostic. Their causes have not been established and they do not define the primary fit.

## Relationship to the inlet and status of MODIS

The inlet evidence covers the August–October 2026 NISAR and Sentinel‑2 acquisitions and DAHITI heights. The precipitation record covers a much larger atmospheric grid cell and ends in 2024. The two investigations answer questions about different processes, areas, and periods. The rainfall slope establishes neither a reservoir-area trend in km²/year nor a cause for the observed shoreline change.

NASA's MOD28C3 Collection 6.1 guide assigns Roseires `lake_ID=111`, corresponding to **GRanD ID 4483**. NASA's catalogue lists the collection and 312 monthly granules. Direct data access redirected to Earthdata Login, and the local execution environment could not resolve NASA endpoints. The reservoir time-series portal did not return the Roseires values in this session. No monthly Roseires area values were qualified. [Collection catalogue](https://cmr.earthdata.nasa.gov/search/concepts/C2565791057-LPCLOUD.html) · [Collection 6.1 user guide](https://lpdaac.usgs.gov/documents/1116/MOD28_User_Guide_V61.pdf)

With authenticated access, download one consistent Terra or Aqua collection and retain the granule IDs, production times, dates, and checksums. Read each HDF4 `lake_evaporation` table with an HDF4 Vdata reader and verify the coordinates and ID before extracting `lake_area`. Check the `−9999` fill value, available quality metadata, product-level enhancement and interpolation, and coverage by month. Collection 7 documents a contamination fraction. Confirm the actual field in the chosen collection and preserve published versus locally processed values. Examine the documented 2013 dam heightening as a candidate break before fitting reservoir-area trends. A possible break alone does not establish an operational cause. [Collection 7 user guide](https://modis-land.gsfc.nasa.gov/pdf/MODIS_MOD28_User_Guide_1.3_20260226_C7.pdf) · [Roseires dam heightening](https://www.hydropower.org/sediment-management-case-studies/sudan-roseires)

## Reproduce

From the repository root, use the existing `roseires-pipeline` environment with NumPy.

```sh
conda run -n roseires-pipeline python roseires-trends/analyze_power.py
conda run -n roseires-pipeline python -m unittest discover -s roseires-trends -p 'test_*.py'
```
