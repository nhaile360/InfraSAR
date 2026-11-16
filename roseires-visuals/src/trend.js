"use strict";

function drawTrendLine(ctx, series, X, Y) {
  let connected = false;
  ctx.beginPath();
  for (const {time, value} of series) {
    if (value === null) {
      connected = false;
      continue;
    }
    if (connected) ctx.lineTo(X(time), Y(value));
    else ctx.moveTo(X(time), Y(value));
    connected = true;
  }
  ctx.stroke();
}

function monthlyTime(month) {
  const [year, number] = month.split("-").map(Number);
  return year + (number - 1) / 12;
}

function setupTrend(investigation, reservoir, explorer) {
  if (!investigation?.windows.length) return;
  const section = $("trend-investigation");
  const variable = $("trend-variable");
  const period = $("trend-period");
  const chart = $("trend-chart");
  const inspector = $("trend-inspect");
  const yearStart = $("trend-start"), yearEnd = $("trend-end");
  const firstYear = investigation.annual[0].year, lastYear = investigation.annual.at(-1).year;
  const yearGap = explorer.min_years - 1;
  for (let year = firstYear; year <= lastYear; year++) {
    for (const [select, include] of [[yearStart, year <= lastYear - yearGap], [yearEnd, year >= firstYear + yearGap]]) {
      if (!include) continue;
      const option = node("option", String(year));
      option.value = String(year);
      select.append(option);
    }
  }
  yearStart.value = firstYear;
  yearEnd.value = lastYear;
  const scales = section.querySelectorAll("[data-trend-scale]");
  const number = new Intl.NumberFormat("en-US", {maximumFractionDigits: 2});
  const signed = new Intl.NumberFormat("en-US", {maximumFractionDigits: 2, signDisplay: "exceptZero"});
  const pValue = value => value < .001 ? "p < .001" : "p = " + value.toFixed(3);
  const areaMode = () => variable.value === "modis";
  let scale = "annual";
  let series = [];
  let inspected = 0;
  const boundsForFit = () => period.value === "custom" ? [Number(yearStart.value), Number(yearEnd.value)]
    : [investigation.windows[Number(period.value)].start, investigation.windows[Number(period.value)].end];
  const selectedFit = () => explorer.windows[boundsForFit().join("-")];
  const fullRecord = () => period.value === "0";
  const annualMode = () => !areaMode() && scale === "annual";

  function inspect(index) {
    inspected = clamp(index, 0, series.length - 1);
    const row = series[inspected];
    if (!row) return;
    inspector.value = inspected;
    let detail;
    if (areaMode()) {
      const value = row.value === null ? (row.status === "fill_value" ? "NASA fill value" : "No granule") : number.format(row.value) + " km²";
      detail = [row.label, value, reservoir.source.product];
    } else if (annualMode()) {
      const fit = selectedFit();
      const fitted = fit.fitted_start_mm + (row.time - fit.start) * fit.slope_mm_per_year;
      detail = [row.label, number.format(row.value) + " mm calendar-year total", number.format(fitted) + " mm fitted", "NASA POWER / MERRA-2 · 12 of 12 months"];
    } else {
      detail = [row.label, number.format(row.monthlyRate) + " mm/day monthly mean",
        number.format(row.monthlyTotal) + " mm accumulation over " + row.days + " days", "NASA POWER / MERRA-2 · source value present"];
    }
    $("trend-tooltip").textContent = detail.join(" · ");
    inspector.setAttribute("aria-valuetext", detail.join(", "));
    draw();
  }

  investigation.windows.forEach((fit, index) => {
    const option = node("option", fit.start + "–" + fit.end + " · " + fit.label);
    option.value = String(index);
    period.append(option);
  });

  const custom = node("option", "Custom range · exploratory");
  custom.value = "custom";
  period.append(custom);

  function plotEdges(width) {
    return {plotLeft: 52, plotRight: width - 16};
  }

  function draw() {
    const frame = redrawTo(chart);
    if (!frame || !series.length) return;
    const {ctx, width, height} = frame;
    const area = areaMode(), annual = annualMode();
    const {plotLeft, plotRight} = plotEdges(width);
    const plotTop = 14, plotBottom = height - 33;
    const fit = annual ? selectedFit() : null;
    const band = fit ? series.map(({time}) => {
      const t = time - fit.start;
      const [variance0, covariance, variance1] = fit.fit_covariance;
      const fitted = fit.fitted_start_mm + t * fit.slope_mm_per_year;
      const half = 1.95996398454 * Math.sqrt(Math.max(0, variance0 + 2 * t * covariance + t * t * variance1));
      return {time, fitted, low:fitted-half, high:fitted+half};
    }) : [];
    const step = area || scale === "monthly-total" ? 100 : annual ? 300 : 4;
    const ceiling = Math.max(step, Math.ceil(Math.max(...series.map(point => point.value), ...band.map(row => row.high)) / step) * step);
    const floor = Math.floor(Math.min(0, ...band.map(row => row.low)) / step) * step;
    const X = time => plotLeft + (time - series[0].time) * (plotRight - plotLeft) / (series.at(-1).time - series[0].time);
    const Y = value => plotBottom - (value - floor) * (plotBottom - plotTop) / (ceiling - floor);
    ctx.clearRect(0, 0, width, height);
    ctx.font = "12px system-ui";
    ctx.fillStyle = "#49635f";
    ctx.strokeStyle = "#d5ddd2";
    ctx.lineWidth = 1;
    ctx.textAlign = "right";
    ctx.textBaseline = "middle";
    for (let value = floor; value <= ceiling; value += step) {
      const y = Y(value);
      ctx.beginPath();
      ctx.moveTo(plotLeft, y);
      ctx.lineTo(plotRight, y);
      ctx.stroke();
      ctx.fillText(String(value), plotLeft - 6, y);
    }
    const tickCount = width < 480 ? 3 : 6;
    const first = series[0].time, last = series.at(-1).time;
    for (let i = 0; i < tickCount; i++) {
      const year = first + (last - first) * i / (tickCount - 1);
      ctx.textAlign = i === 0 ? "left" : i === tickCount - 1 ? "right" : "center";
      ctx.fillText(String(Math.floor(year)), X(year), height - 12);
    }
    if (band.length) {
      ctx.fillStyle = "#c089583d";
      ctx.beginPath();
      band.forEach((row, index) => index ? ctx.lineTo(X(row.time), Y(row.high)) : ctx.moveTo(X(row.time), Y(row.high)));
      for (const row of [...band].reverse()) ctx.lineTo(X(row.time), Y(row.low));
      ctx.closePath();
      ctx.fill();
    }
    ctx.strokeStyle = "#277a70";
    ctx.lineWidth = annual ? 1.5 : 1.1;
    if (!annual) drawTrendLine(ctx, series, X, Y);
    if (annual || area) for (const row of series) {
      if (row.value !== null) dot(ctx, X(row.time), Y(row.value), annual ? 3.4 : 1.6, "#277a70");
    }
    if (annual || area) {
      ctx.strokeStyle = "#9d4e27";
      ctx.lineWidth = 2;
      ctx.setLineDash([5, 4]);
      ctx.beginPath();
      if (annual) {
        ctx.moveTo(X(fit.start), Y(fit.fitted_start_mm));
        ctx.lineTo(X(fit.end), Y(fit.fitted_end_mm));
      } else {
        const x = X(monthlyTime(reservoir.break_month));
        ctx.moveTo(x, plotTop);
        ctx.lineTo(x, plotBottom);
      }
      ctx.stroke();
      ctx.setLineDash([]);
    }
    const active = series[inspected], x = X(active.time);
    ctx.strokeStyle = "#49635f";
    ctx.lineWidth = 1;
    ctx.beginPath(); ctx.moveTo(x, plotTop); ctx.lineTo(x, plotBottom); ctx.stroke();
    if (active.value !== null) dot(ctx, x, Y(active.value), 5, "#194e44", true);
  }

  function renderTable(headings, cells) {
    const head = node("tr");
    for (const label of headings) {
      const cell = node("th", label);
      cell.scope = "col";
      head.append(cell);
    }
    $("trend-table-head").replaceChildren(head);
    $("trend-table-title").textContent = $("trend-chart-unit").textContent;
    $("trend-table-body").replaceChildren(...series.map(item => {
      const row = node("tr");
      row.append(...cells(item).map(value => node("td", value)));
      return row;
    }));
  }

  const rainfallTitle = $("trend-title").textContent;
  const rainfallContext = $("trend-context").textContent;
  const {source, diagnostics, coverage} = investigation;
  const shifts = diagnostics.level_shift_screen.at(-1).first_years_after_shift;
  const annualValues = investigation.annual.map(row => row.total_mm);
  const lags = [investigation.windows[0], ...diagnostics.hac_sensitivity].sort((a, b) => a.hac_lags_years - b.hac_lags_years);
  for (const fit of lags) {
    const row = node("tr");
    for (const cell of [fit.hac_lags_years, fit.ci95_mm_per_year.map(signed.format).join(" to "), pValue(fit.p_two_sided)]) {
      row.append(node("td", String(cell)));
    }
    $("rainfall-lags").append(row);
  }
  const post2014 = explorer.windows["2014-2024"];
  $("rainfall-breaks").textContent = "An exploratory screen flagged level shifts around " + shifts.join(" and ")
    + ". One straight line can hide changes in level. The 2003–2024 window includes the possible 2014 shift. "
    + "The 2014–2024 slope is " + signed.format(post2014.slope_mm_per_year) + " mm/year (95% CI "
    + post2014.ci95_mm_per_year.map(signed.format).join(" to ") + "). Both windows are exploratory.";

  function refreshRainfall() {
    const fit = selectedFit();
    const monthly = !annualMode();
    const totals = scale === "monthly-total";
    const [low, high] = fit.ci95_mm_per_year;
    const significant = fit.p_two_sided < .05;
    $("trend-scope").textContent = investigation.source.product + (fullRecord() ? " · Full record" : " · Exploratory") + " · " + fit.start + "–" + fit.end
      + " · " + fit.n_years + " complete years (" + (fit.n_years * 12) + " months)";
    $("trend-slope").textContent = signed.format(fit.slope_mm_per_year) + " mm/year";
    $("trend-interval").textContent = number.format(low) + " to " + number.format(high) + " mm/year";
    $("trend-significance").textContent = significant ? "Exploratory · interval excludes zero" : "Inconclusive";
    $("trend-p").textContent = pValue(fit.p_two_sided);
    const direction = signed.format(fit.slope_mm_per_year) + " mm per year in the fitted annual total. ";
    $("trend-interpretation").textContent = direction + (significant
      ? "This selected window excludes zero under the fitted model. Its nominal p-value cannot independently confirm a change point."
      : "The 95% interval gives a range of slopes compatible with the model, including zero. The p-value is the chance of a test statistic at least this extreme assuming zero trend and the model assumptions. The result leaves increases and decreases plausible.");
    $("trend-chart-unit").textContent = totals ? "Monthly precipitation accumulation (mm)"
      : monthly ? "Monthly mean precipitation (mm/day)" : "Calendar-year precipitation total (mm)";
    $("trend-chart-key").textContent = monthly
      ? (totals ? "Line · NASA POWER monthly rate multiplied by calendar days." : "Line · NASA POWER monthly means.")
        + " The slope and test still use the annual totals."
      : "Dots · complete annual totals. Dashed line · fitted trend. Shading · pointwise 95% interval for the fitted mean, distinct from the slope interval above.";
    chart.setAttribute("aria-label", $("trend-chart-unit").textContent + " for " + fit.start + " to " + fit.end);

    const withinPeriod = year => year >= fit.start && year <= fit.end;
    if (monthly) {
      series = investigation.monthly.filter(row => withinPeriod(Number(row.month.slice(0, 4)))).map(row => ({
        label: row.month, time: monthlyTime(row.month), value: totals ? row.total_mm : row.source_mm_day, monthlyTotal: row.total_mm, monthlyRate: row.source_mm_day, days: row.days,
      }));
    } else {
      series = investigation.annual.filter(row => withinPeriod(row.year)).map(row => ({
        label: String(row.year), time: row.year, value: row.total_mm,
      }));
    }
    const headings = monthly ? ["Month", "Source (mm/day)", "Calculated total (mm)"] : ["Year", "Calculated total (mm)"];
    renderTable(headings, ({label, value, monthlyRate, monthlyTotal}) => monthly
      ? [label, number.format(monthlyRate), number.format(monthlyTotal)]
      : [label, number.format(value)]);
    $("rainfall-variability").textContent = "Annual totals ranged from " + number.format(Math.min(...annualValues)) + " to "
      + number.format(Math.max(...annualValues)) + " mm in 1981–2024. For this window, residual standard deviation is "
      + number.format(fit.residual_sd_mm) + " mm and lag-one residual autocorrelation is "
      + number.format(fit.residual_acf1) + ". Similar deviations in nearby years reduce independent evidence.";
    $("rainfall-robust").textContent = "Theil–Sen slope for this window: " + signed.format(fit.theil_sen_mm_per_year)
      + " mm/year. This median pairwise slope checks sensitivity to extreme years. A plain Mann–Kendall test assumes independence and needs adjustment for serial dependence here.";
    $("trend-method").textContent = "Multiply each monthly mean by its calendar days and sum the 12 months. "
      + coverage.complete_months + " source months passed the completeness check. InfraSAR filled no gaps. "
      + "Fit a line to the yearly totals with Newey–West uncertainty to account for dependence between years.";
    $("trend-diagnostics").textContent = (diagnostics.june_september_fraction * 100).toFixed(0)
      + "% of the estimated rainfall falls from June through September. The annual model’s lag-one residual correlation is "
      + diagnostics.annual_residual_acf_1_to_6[0].toFixed(2) + ". An exploratory check suggests level shifts around "
      + shifts.join(" and ") + ". Their causes remain unknown, and the linear fit summarizes only the selected period.";
  }

  function refreshArea() {
    const {monthly, coverage: counts, shift_km2: shift, post_slope_km2_per_year: slope} = reservoir;
    const interval = (fit, unit) => "95% CI " + fit.ci95.map(value => number.format(value)).join(" to ") + " " + unit;
    const significant = slope.p_two_sided < .05;
    $("trend-scope").textContent = reservoir.source.product + " · " + monthly[0].month + " to " + monthly.at(-1).month
      + " · " + counts.published + " published measurements";
    $("trend-shift").textContent = signed.format(shift.estimate) + " km²";
    $("trend-shift-ci").textContent = interval(shift, "km²");
    $("trend-slope").textContent = signed.format(slope.estimate) + " km²/year";
    $("trend-post-ci").textContent = interval(slope, "km²/year");
    $("trend-significance").textContent = significant ? "Significant in this fit" : "Inconclusive";
    $("trend-p").textContent = pValue(slope.p_two_sided);
    $("trend-interpretation").textContent = "The estimated shift coincides with the 2013 dam heightening. "
      + (significant ? "The interval for the later trend excludes zero under this model."
        : "The interval for the later trend includes zero.");
    $("trend-chart-unit").textContent = "Monthly reservoir surface area (km²)";
    $("trend-chart-key").textContent = "Dots and connected lines show published monthly measurements. "
      + "Gaps show " + counts.fill_value + " fill-value months and " + counts.no_granule
      + " months without a granule. Dashed marker at January 2013.";
    chart.setAttribute("aria-label", "Monthly reservoir surface area in square kilometers from "
      + monthly[0].month + " to " + monthly.at(-1).month + ", with gaps for unavailable months.");
    series = monthly.map(row => ({
      label: row.month, time: monthlyTime(row.month), value: row.area_km2, status: row.status,
    }));
    const statusLabels = {published: "Published", fill_value: "NASA fill value", no_granule: "No granule"};
    renderTable(["Month", "Surface area (km²)", "Source status"], ({label, value, status}) => [
      label, value === null ? "—" : number.format(value), statusLabels[status],
    ]);
    $("trend-method").textContent = "The level-shift model uses January 2013 as the breakpoint, allows different slopes before and after, "
      + "and adjusts for calendar month. A separate season-adjusted fit estimates the trend since 2013. "
      + "Both use 12-calendar-month Newey–West confidence intervals.";
    $("trend-diagnostics").textContent = "The fits use January–May and October–December, the months with comparable coverage "
      + "before and after the breakpoint. The chart includes all published months. The timing of the shift alone cannot establish its cause.";
  }

  function refresh() {
    const area = areaMode();
    $("trend-title").textContent = area ? "How has the reservoir’s surface area changed?" : rainfallTitle;
    $("trend-context").textContent = area
      ? "Explore NASA Terra MODIS monthly surface area and compare the period around the 2013 dam heightening with the years that followed."
      : rainfallContext;
    $("trend-period-field").hidden = area;
    $("trend-scale").hidden = area;
    $("trend-custom").hidden = area || period.value !== "custom";
    $("rainfall-evidence").hidden = area;
    $("trend-interval-card").hidden = area;
    $("trend-shift-card").hidden = !area;
    $("trend-post-ci").hidden = !area;
    $("rainfall-sources").hidden = area;
    $("modis-sources").hidden = !area;
    $("trend-slope-label").textContent = area ? "Trend since 2013" : "Change in annual total";
    $("trend-significance-label").textContent = area ? "Evidence for a later trend" : "Statistical significance";
    if (area) refreshArea();
    else refreshRainfall();
    inspector.max = series.length - 1;
    inspect(0);
  }

  $("trend-source").href = source.request;
  if (location.protocol === "file:") {
    $("modis-csv").href = "https://github.com/nhaile360/InfraSAR/blob/main/roseires-trends/roseires_modis_monthly_surface_area.csv";
  }
  $("trend-controls").addEventListener("submit", event => event.preventDefault());
  variable.addEventListener("change", refresh);
  period.addEventListener("change", refresh);
  yearStart.addEventListener("change", () => {
    if (Number(yearEnd.value) - Number(yearStart.value) < yearGap) yearEnd.value = Number(yearStart.value) + yearGap;
    refresh();
  });
  yearEnd.addEventListener("change", () => {
    if (Number(yearEnd.value) - Number(yearStart.value) < yearGap) yearStart.value = Number(yearEnd.value) - yearGap;
    refresh();
  });
  inspector.addEventListener("input", () => inspect(Number(inspector.value)));
  inspector.addEventListener("focus", () => inspect(Number(inspector.value)));
  function probe(event) {
    const box = chart.getBoundingClientRect();
    const {plotLeft, plotRight} = plotEdges(box.width);
    const fraction = clamp((event.clientX - box.left - plotLeft) / (plotRight - plotLeft), 0, 1);
    const time = series[0].time + fraction * (series.at(-1).time - series[0].time);
    const index = series.reduce((nearest, row, i) => Math.abs(row.time - time) < Math.abs(series[nearest].time - time) ? i : nearest, 0);
    if (index !== inspected) inspect(index);
  }
  chart.addEventListener("pointermove", event => { if (event.pointerType === "mouse") probe(event); });
  chart.addEventListener("click", probe);
  for (const button of scales) {
    button.addEventListener("click", () => {
      scale = button.dataset.trendScale;
      for (const item of scales) item.setAttribute("aria-pressed", String(item === button));
      refresh();
    });
  }
  new ResizeObserver(draw).observe(chart);
  refresh();
}

const frozenPilotScores = seed.bundles.find(bundle => bundle.pair === "pilot")?.metrics;
if (frozenPilotScores?.fixed?.gain && frozenPilotScores?.local?.gain) {
  const score = $("pilot-score");
  const percent = value => (100 * value).toFixed(2) + "%";
  score.textContent = "Across the study area, only "
    + percent(frozenPilotScores.fixed.gain.precision) + " of radar water-gain flags (fixed rule) and "
    + percent(frozenPilotScores.local.gain.precision)
    + " (local rule) matched a water gain in the usable Sentinel‑2 data. Radar darkening alone was an unreliable guide to new water in this pilot.";
  score.hidden = false;
}

function showInvestigation(hash, focus=false) {
  const historical = hash === "#trend-investigation";
  $("shoreline").hidden = historical;
  $("trend-investigation").hidden = !historical;
  for (const item of $("investigations").querySelectorAll("a")) {
    if (item.hash === (historical ? "#trend-investigation" : "#shoreline")) item.setAttribute("aria-current","location");
    else item.removeAttribute("aria-current");
  }
  if (historical) pause();
  else requestDraw();
  if (focus) {
    const nav = $("investigations");
    const rect = nav.getBoundingClientRect();
    if (rect.top < 0 || rect.bottom > innerHeight) nav.scrollIntoView({block:"start",behavior:"instant"});
    const target = historical ? $("trend-title") : document.querySelector('[data-view][aria-pressed="true"]');
    target?.focus({preventScroll:true});
  }
}

setupTrend(seed.trend, seed.modis, seed.rainfall_explorer);
for (const item of document.querySelectorAll("a[data-investigation]")) {
  item.addEventListener("click", event => {
    if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    event.preventDefault();
    if (location.hash !== item.hash) history.pushState(null,"",item.hash);
    showInvestigation(item.hash,true);
  });
}
window.addEventListener("hashchange",()=>showInvestigation(location.hash));
showInvestigation(location.hash);
