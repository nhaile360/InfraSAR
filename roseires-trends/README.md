# Long-term observations near Roseires

## MODIS reservoir surface area

[NASA Terra MODIS MOD28C3.061](https://modis.gsfc.nasa.gov/data/dataprod/mod28.php) supplies monthly surface area in km² for Roseires (lake ID 111, GRanD ID 4483). The [derived source CSV](roseires_modis_monthly_surface_area.csv) includes the original granule name and its SHA-256 checksum. It contains 235 published values, 77 product fill values, and five months without a granule between March 2000 and July 2026. Fill values and unavailable months appear as gaps.

The January 2013 breakpoint reflects the [recorded dam heightening](https://www.hydropower.org/sediment-management-case-studies/sudan-roseires). The interrupted fit includes a level shift, calendar year centered at 2013, a change in slope at the breakpoint, and calendar-month effects. The separate post-2013 fit estimates a slope with its own calendar-month effects. Both fits use January–May and October–December, when coverage is comparable across the two eras. June is sparsely observed, and July–September has no pre-2013 estimates. The plot shows every published month.

The build reproduces the estimated **+164.07 km²** shift (95% CI 107.55 to 220.59) and **−1.26 km²/year** slope since 2013 (95% CI −3.34 to +0.82, p = .234). Both use Bartlett Newey–West uncertainty with 12 calendar-month lags, the n/(n−k) correction, and a two-sided normal approximation. The post-2013 interval includes zero. The timing alone does not establish the cause of the shift.

```sh
python roseires-trends/analyze_modis.py
python scripts/build_site.py
```

For future extraction, install PyHDF in the analysis environment and run `python roseires-trends/extract_modis.py` from the repository root. It reads the original HDF4 granules from `data/MOD28C3/` and rewrites the derived CSV. Use `--output PATH` for a comparison copy. To check an individual month, run `shasum -a 256 data/MOD28C3/<source_granule>` and compare it with `granule_sha256` in the CSV.

## Long-term precipitation near Roseires

InfraSAR's current long-term investigation uses NASA POWER corrected precipitation for one MERRA-2 grid cell near Roseires, Sudan. The precipitation record covers January 1981 through December 2024.

### Result

| Analysis | Years | Change in annual precipitation total | 95% interval | Two-sided p |
| --- | ---: | ---: | ---: | ---: |
| Primary, 1981–2024 | 44 | +1.52 mm/year | −9.99 to +13.04 mm/year | 0.795 |
| Exploratory, 1981–2002 | 22 | −17.55 mm/year | −40.37 to +5.28 mm/year | 0.132 |
| Exploratory, 2003–2024 | 22 | +48.17 mm/year | +37.09 to +59.26 mm/year | <0.001 |

The interval for the full record includes zero. The record supports calculating a long-term linear summary, with limited evidence for a steady increase or decrease. The shorter windows are sensitivity views. A level shift within a window can produce an apparent trend under a linear model.

### Source and transformations

- [NASA POWER original monthly request](https://power.larc.nasa.gov/api/temporal/monthly/point?parameters=PRECTOTCORR&community=AG&longitude=34.4673&latitude=11.7285&start=1981&end=2024&format=JSON). Retrieved November 15, 2026. The response identifies API v2.10.0, MERRA-2, local solar time, and PRECTOTCORR in mm/day. The request uses the inlet coordinates. The returned point is 11.729° N, 34.467° E, within POWER’s 0.5° latitude × 0.625° longitude meteorological grid.
- [nasa-power-roseires.json](nasa-power-roseires.json) preserves all numerical source values and response metadata in formatted JSON. It includes 528 monthly values and 44 source annual summary values with month code `13`. The source sentinel is `−999`. All 528 months passed the completeness check, including legitimate zero values.
- [power-analysis.json](power-analysis.json) records the source snapshot hash, unaltered monthly rates, the number of calendar days per month, converted monthly totals, calendar-year totals, model fits, and diagnostics. Each monthly mean rate is multiplied by the actual days in the month, including leap days. The analysis fits complete calendar-year totals. Only months 01–12 enter the fit. InfraSAR fills no gaps, removes no outliers, and applies no smoothing.
- PRECTOTCORR is an observation-corrected reanalysis estimate. It inherits limitations from the model, the underlying observing products, and their spatial support. The regression interval describes sampling uncertainty under the fitted time-series model. It does not include systematic product errors or establish that the estimate is representative of the Blue Nile catchment. [POWER data methodology](https://power.larc.nasa.gov/docs/methodology/data/sources_meteorology/) · [NASA MERRA-2 documentation](https://ntrs.nasa.gov/api/citations/20160005045/downloads/20160005045.pdf)

### Seasonal and temporal checks

June through September accounts for **77.9%** of estimated precipitation. Complete calendar-year totals include each seasonal cycle once. The slope is the change in annual accumulation, measured in millimeters per additional calendar year.

The ordinary least-squares fit has lag-one annual residual autocorrelation of approximately **0.75**. The primary interval uses Bartlett-weighted Newey–West covariance with three annual lags, the `n/(n−2)` correction, and an approximate two-sided normal test at the 5% level. One- and five-lag sensitivity checks also include zero. With 44 years and substantial serial dependence, treat the intervals as approximate. [Newey–West covariance reference](https://www.statsmodels.org/stable/generated/statsmodels.stats.sandwich_covariance.cov_hac.html)

An exploratory screen compares the full-record line with step-plus-line fits. It allows one or two changes in level, keeps at least eight years per segment, and includes two parameters per searched breakpoint in its BIC penalty. The best one-step fit starts a new segment in **2014** (ΔBIC ≈ −29.1). The best two-step fit starts new segments in **2000** and **2014** (ΔBIC ≈ −36.0). This nominal BIC comparison does not adjust for residual dependence or provide a calibrated significance test for the breakpoints. The dates are diagnostic. Their causes have not been established and they do not define the primary fit.

### Relationship to the inlet

The inlet evidence covers the August–October 2026 NISAR and Sentinel‑2 acquisitions and DAHITI heights. The precipitation record covers a much larger atmospheric grid cell and ends in 2024. The two investigations answer questions about different processes, areas, and periods. The rainfall slope establishes neither a reservoir-area trend in km²/year nor a cause for the observed shoreline change.

### Reproduce

From the repository root, use the existing `roseires-pipeline` environment with NumPy.

```sh
conda run -n roseires-pipeline python roseires-trends/analyze_power.py
conda run -n roseires-pipeline python -m unittest discover -s roseires-trends -p 'test_*.py'
```

### Reading the Phase 4 charts

The annual plot shows one dot per complete calendar year, the fitted OLS line, and its pointwise 95% interval for the fitted mean. The band uses the same Newey–West coefficient covariance as the slope test. It measures uncertainty in the mean fit at each year. The displayed slope interval concerns change per year, and neither interval includes systematic reanalysis error. Monthly views show either the original mean rate or the accumulation calculated from that rate. The annual inference stays fixed when switching between those displays.

Annual totals range from **295.77 mm (2011)** to **1,370.67 mm (1987)**, with a standard deviation of **338.12 mm**. The estimated full-record slope of +1.52 mm/year is small relative to its standard error of 5.88 mm/year. Lag-one residual autocorrelation is 0.747. Including one, three, or five years of lagged residual dependence changes the interval but all three include zero.

| Newey–West lag | Full-record 95% slope interval (mm/year) | Two-sided p |
| ---: | ---: | ---: |
| 1 year | −7.77 to +10.82 | 0.748 |
| 3 years | −9.99 to +13.04 | 0.795 |
| 5 years | −11.00 to +14.05 | 0.811 |

The Theil–Sen estimate is **+0.52 mm/year** for the full record. It is the median of all pairwise annual slopes and serves as a descriptive check against unusually wet or dry years. A conventional Mann–Kendall significance test assumes independence. Serial dependence in this record makes that unadjusted test unsuitable for independent corroboration.

Custom windows require ten complete consecutive years and use the same three-lag calculation. All custom-window intervals and tests are exploratory, including the 2014–2024 fit (+4.21 mm/year, 95% CI −9.09 to +17.52; p = 0.535). The 2003–2024 increase includes the possible 2014 level shift. Its nominal p-value cannot confirm a break selected by inspecting the same record. June–September seasonality is retained in the monthly view and each calendar-year total contains one complete seasonal cycle.
