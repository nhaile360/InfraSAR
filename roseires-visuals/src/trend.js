"use strict";

function setupTrend(investigation) {
  if (!investigation?.windows.length) return;
  const section = $("trend-investigation");
  const period = $("trend-period");
  const chart = $("trend-chart");
  const scales = section.querySelectorAll("[data-trend-scale]");
  const number = new Intl.NumberFormat("en-US", {maximumFractionDigits: 2});
  const signed = new Intl.NumberFormat("en-US", {maximumFractionDigits: 2, signDisplay: "exceptZero"});
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
    const monthly = scale === "monthly";
    const plotLeft = 40, plotRight = width - 15, plotTop = 12, plotBottom = height - 29;
    const step = monthly ? 4 : 400;
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
    const tickYears = Array.from({length: tickCount}, (_, i) => Math.round(fit.start + (fit.end - fit.start) * i / (tickCount - 1)));
    tickYears.forEach((year, i) => {
      ctx.textAlign = i === 0 ? "left" : i === tickCount - 1 ? "right" : "center";
      ctx.fillText(String(year), X(year), height - 12);
    });
    ctx.strokeStyle = "#277a70";
    ctx.lineWidth = monthly ? 1.15 : 2;
    ctx.beginPath();
    series.forEach(({time, value}, i) => {
      if (i === 0) ctx.moveTo(X(time), Y(value));
      else ctx.lineTo(X(time), Y(value));
    });
    ctx.stroke();
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

  function refresh() {
    const fit = investigation.windows[Number(period.value)];
    const monthly = scale === "monthly";
    const [low, high] = fit.ci95_mm_per_year;
    const significant = fit.p_two_sided < .05;
    $("trend-scope").textContent = investigation.source.product + " · " + fit.start + "–" + fit.end
      + " · " + fit.n_years + " complete years (" + (fit.n_years * 12) + " months)";
    $("trend-slope").textContent = signed.format(fit.slope_mm_per_year) + " mm/year";
    $("trend-interval").textContent = number.format(low) + " to " + number.format(high) + " mm/year";
    $("trend-significance").textContent = significant ? "Significant in this fit" : "Inconclusive";
    $("trend-p").textContent = fit.p_two_sided < .001 ? "p < .001" : "p = " + fit.p_two_sided.toFixed(3);
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
      series = investigation.monthly.filter(row => withinPeriod(Number(row.month.slice(0, 4)))).map(row => {
        const [year, month] = row.month.split("-").map(Number);
        return {label: row.month, time: year + (month - 1) / 12, value: row.source_mm_day, monthlyTotal: row.total_mm};
      });
    } else {
      series = investigation.annual.filter(row => withinPeriod(row.year)).map(row => ({
        label: String(row.year), time: row.year, value: row.total_mm,
      }));
    }
    const headings = monthly ? ["Month", "Source (mm/day)", "Calculated total (mm)"] : ["Year", "Calculated total (mm)"];
    const head = node("tr");
    for (const label of headings) {
      const cell = node("th", label);
      cell.scope = "col";
      head.append(cell);
    }
    $("trend-table-head").replaceChildren(head);
    $("trend-table-title").textContent = $("trend-chart-unit").textContent;
    $("trend-table-body").replaceChildren(...series.map(({label, value, monthlyTotal}) => {
      const row = node("tr");
      row.append(node("td", label), node("td", number.format(value)));
      if (monthly) row.append(node("td", number.format(monthlyTotal)));
      return row;
    }));
    draw();
  }

  const {source, diagnostics, coverage} = investigation;
  const shifts = diagnostics.level_shift_screen.at(-1).first_years_after_shift;
  $("trend-source").href = source.request;
  $("trend-method").textContent = "Multiply each monthly mean by its calendar days and sum the 12 months. "
    + coverage.complete_months + " source months passed the completeness check. InfraSAR filled no gaps. "
    + "Fit a line to the yearly totals with Newey–West uncertainty to account for dependence between years.";
  $("trend-diagnostics").textContent = (diagnostics.june_september_fraction * 100).toFixed(0)
    + "% of the estimated rainfall falls from June through September. The annual model’s lag-one residual correlation is "
    + diagnostics.annual_residual_acf_1_to_6[0].toFixed(2) + ". An exploratory check suggests level shifts around "
    + shifts.join(" and ") + ". Their causes remain unknown, and the linear fit summarizes only the selected period.";
  $("trend-controls").addEventListener("submit", event => event.preventDefault());
  period.addEventListener("change", refresh);
  for (const button of scales) {
    button.addEventListener("click", () => {
      scale = button.dataset.trendScale;
      for (const item of scales) item.setAttribute("aria-pressed", String(item === button));
      refresh();
    });
  }
  section.hidden = false;
  $("trend-link").hidden = false;
  new ResizeObserver(draw).observe(chart);
  refresh();
}

const frozenPilotScores = seed.bundles.find(bundle => bundle.pair === "pilot")?.metrics;
if (frozenPilotScores?.fixed?.gain && frozenPilotScores?.local?.gain) {
  const score = $("pilot-score");
  const percent = value => (100 * value).toFixed(2) + "%";
  score.textContent = "Across the crop, radar-only water-gain precision against Sentinel‑2 was "
    + percent(frozenPilotScores.fixed.gain.precision) + " for the fixed rule and "
    + percent(frozenPilotScores.local.gain.precision)
    + " for the local rule. Most radar water-gain flags on cells with usable optical data were false alarms against this reference.";
  score.hidden = false;
}

setupTrend(seed.trend);
