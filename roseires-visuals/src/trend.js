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

function setupTrend(investigation, reservoir) {
  if (!investigation?.windows.length) return;
  const section = $("trend-investigation");
  const variable = $("trend-variable");
  const period = $("trend-period");
  const chart = $("trend-chart");
  const scales = section.querySelectorAll("[data-trend-scale]");
  const number = new Intl.NumberFormat("en-US", {maximumFractionDigits: 2});
  const signed = new Intl.NumberFormat("en-US", {maximumFractionDigits: 2, signDisplay: "exceptZero"});
  const pValue = value => value < .001 ? "p < .001" : "p = " + value.toFixed(3);
  const areaMode = () => variable.value === "modis";
  let scale = "annual";
  let series = [];

  investigation.windows.forEach((fit, index) => {
    const option = node("option", fit.start + "–" + fit.end + " · " + fit.label);
    option.value = String(index);
    period.append(option);
  });

  function draw() {
    const frame = redrawTo(chart);
    if (!frame || !series.length) return;
    const {ctx, width, height} = frame;
    const fit = investigation.windows[Number(period.value)];
    const area = areaMode(), monthly = scale === "monthly" || area;
    const plotLeft = 40, plotRight = width - 15, plotTop = 12, plotBottom = height - 29;
    const step = area ? 100 : monthly ? 4 : 400;
    const maxValue = Math.max(...series.map(point => point.value), monthly ? 0 : fit.fitted_start_mm, monthly ? 0 : fit.fitted_end_mm);
    const ceiling = Math.max(step, Math.ceil(maxValue / step) * step);
    const X = time => plotLeft + (time - series[0].time) * (plotRight - plotLeft) / (series.at(-1).time - series[0].time);
    const Y = value => plotBottom - value * (plotBottom - plotTop) / ceiling;
    ctx.clearRect(0, 0, width, height);
    ctx.font = "11px system-ui";
    ctx.fillStyle = "#49635f";
    ctx.strokeStyle = "#d5ddd2";
    ctx.lineWidth = 1;
    ctx.textAlign = "right";
    ctx.textBaseline = "middle";
    for (let value = 0; value <= ceiling; value += step) {
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
    ctx.strokeStyle = "#277a70";
    ctx.lineWidth = monthly ? 1.15 : 2;
    drawTrendLine(ctx, series, X, Y);
    if (area) {
      for (const {time, value} of series) {
        if (value !== null) dot(ctx, X(time), Y(value), 1.6, "#277a70");
      }
      ctx.strokeStyle = "#9d4e27";
      ctx.setLineDash([5, 4]);
      ctx.beginPath();
      const marker = X(monthlyTime(reservoir.break_month));
      ctx.moveTo(marker, plotTop);
      ctx.lineTo(marker, plotBottom);
      ctx.stroke();
      ctx.setLineDash([]);
      return;
    }
    if (monthly) return;
    ctx.strokeStyle = "#9d4e27";
    ctx.lineWidth = 2;
    ctx.setLineDash([5, 4]);
    ctx.beginPath();
    ctx.moveTo(X(fit.start), Y(fit.fitted_start_mm));
    ctx.lineTo(X(fit.end), Y(fit.fitted_end_mm));
    ctx.stroke();
    ctx.setLineDash([]);
    for (const {time, value} of series) dot(ctx, X(time), Y(value), 2.5, "#277a70");
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

  function refreshRainfall() {
    const fit = investigation.windows[Number(period.value)];
    const monthly = scale === "monthly";
    const [low, high] = fit.ci95_mm_per_year;
    const significant = fit.p_two_sided < .05;
    $("trend-scope").textContent = investigation.source.product + " · " + fit.start + "–" + fit.end
      + " · " + fit.n_years + " complete years (" + (fit.n_years * 12) + " months)";
    $("trend-slope").textContent = signed.format(fit.slope_mm_per_year) + " mm/year";
    $("trend-interval").textContent = number.format(low) + " to " + number.format(high) + " mm/year";
    $("trend-significance").textContent = significant ? "Significant in this fit" : "Inconclusive";
    $("trend-p").textContent = pValue(fit.p_two_sided);
    const explanation = significant
      ? "The fitted interval excludes zero under this model."
      : "The fitted interval includes zero, so the evidence does not establish a steady increase or decrease.";
    $("trend-interpretation").textContent = explanation + (fit.label === "Full record"
      ? " Rainfall varies substantially within and between years."
      : " This shorter window is exploratory and can be sensitive to shifts within the record.");
    $("trend-chart-unit").textContent = monthly ? "Monthly mean precipitation (mm/day)" : "Calendar-year precipitation total (mm)";
    $("trend-chart-key").textContent = monthly
      ? "Green line · NASA POWER monthly estimates in their original units."
      : "Green points · totals calculated from the monthly values. Dashed line · fitted linear trend.";
    chart.setAttribute("aria-label", $("trend-chart-unit").textContent + " for " + fit.start + " to " + fit.end);

    const withinPeriod = year => year >= fit.start && year <= fit.end;
    if (monthly) {
      series = investigation.monthly.filter(row => withinPeriod(Number(row.month.slice(0, 4)))).map(row => ({
        label: row.month, time: monthlyTime(row.month), value: row.source_mm_day, monthlyTotal: row.total_mm,
      }));
    } else {
      series = investigation.annual.filter(row => withinPeriod(row.year)).map(row => ({
        label: String(row.year), time: row.year, value: row.total_mm,
      }));
    }
    const headings = monthly ? ["Month", "Source (mm/day)", "Calculated total (mm)"] : ["Year", "Calculated total (mm)"];
    renderTable(headings, ({label, value, monthlyTotal}) => monthly
      ? [label, number.format(value), number.format(monthlyTotal)]
      : [label, number.format(value)]);
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
    $("trend-interval-card").hidden = area;
    $("trend-shift-card").hidden = !area;
    $("trend-post-ci").hidden = !area;
    $("rainfall-sources").hidden = area;
    $("modis-sources").hidden = !area;
    $("trend-slope-label").textContent = area ? "Trend since 2013" : "Change in annual total";
    $("trend-significance-label").textContent = area ? "Evidence for a later trend" : "Statistical significance";
    if (area) refreshArea();
    else refreshRainfall();
    draw();
  }

  $("trend-source").href = source.request;
  if (location.protocol === "file:") {
    $("modis-csv").href = "https://github.com/nhaile360/InfraSAR/blob/main/roseires-trends/roseires_modis_monthly_surface_area.csv";
  }
  $("trend-controls").addEventListener("submit", event => event.preventDefault());
  variable.addEventListener("change", refresh);
  period.addEventListener("change", refresh);
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

setupTrend(seed.trend, seed.modis);
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
