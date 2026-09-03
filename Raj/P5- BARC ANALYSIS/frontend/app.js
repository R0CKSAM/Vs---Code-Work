const state = {
  records: [],
  metadata: null,
  filters: {
    target: [],
    region: [],
    channel: [],
    timeBand: [],
    weeks: [],
  },
  regionMetric: "ama",
  charts: {},
  modalChart: null,
};

const metricLabels = {
  ama: "AMA (000s)",
  tsv: "TSV",
  viewing_minutes: "Viewing Minutes (000)",
  cume_reach: "Cumulative Reach (000)",
};

const metricColors = {
  ama: "#15c7be",
  tsv: "#183247",
  viewing_minutes: "#f4bb42",
  cume_reach: "#f26d6d",
};

const channelPalette = [
  "#0f766e",
  "#2563eb",
  "#dc2626",
  "#7c3aed",
  "#ea580c",
  "#0891b2",
  "#65a30d",
  "#be123c",
  "#4f46e5",
  "#059669",
  "#c2410c",
  "#1d4ed8",
  "#9333ea",
];

const filterConfigs = {
  target: { label: "targets", metadataKey: "targets" },
  region: { label: "regions", metadataKey: "regions" },
  channel: { label: "channels", metadataKey: "channels" },
  timeBand: { label: "time bands", metadataKey: "time_bands" },
  weeks: { label: "weeks", metadataKey: "weeks" },
};

const filters = {
  reset: document.getElementById("resetFilters"),
};

const cards = {
  kpis: document.getElementById("kpiGrid"),
  regionMetricTabs: document.getElementById("regionMetricTabs"),
  regionalHeatmap: document.getElementById("regionalHeatmap"),
  modal: document.getElementById("chartModal"),
  modalTitle: document.getElementById("chartModalTitle"),
  closeModal: document.getElementById("closeChartModal"),
  modalCanvas: document.getElementById("chartModalCanvas"),
};

const formatters = {
  integer: new Intl.NumberFormat("en-IN", { maximumFractionDigits: 0 }),
  compact: new Intl.NumberFormat("en-IN", {
    notation: "compact",
    maximumFractionDigits: 1,
  }),
  decimal: new Intl.NumberFormat("en-IN", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  }),
};

async function init() {
  const payload = await loadPayload();
  state.records = payload.records;
  state.metadata = payload.metadata;
  hydrateFilterState();

  buildFilterControls();
  buildRegionMetricTabs();
  buildCharts();
  bindModalEvents();
  bindSectionTabs();
  initSectionObserver();
  render();
}

async function loadPayload() {
  if (window.__DASHBOARD_PAYLOAD__) {
    return window.__DASHBOARD_PAYLOAD__;
  }

  const response = await fetch("./assets/dashboard_payload.json");
  return response.json();
}

function hydrateFilterState() {
  state.filters.target = [...state.metadata.targets];
  state.filters.region = [...state.metadata.regions];
  state.filters.channel = [...state.metadata.channels];
  state.filters.timeBand = [...state.metadata.time_bands];
  state.filters.weeks = [...state.metadata.weeks];
}

function buildFilterControls() {
  Object.entries(filterConfigs).forEach(([key, config]) => {
    const control = getFilterElements(key);
    const items = getFilterItems(key);

    control.options.innerHTML = "";
    items.forEach((item) => {
      const label = document.createElement("label");
      label.className = "filter-option";
      const input = document.createElement("input");
      input.type = "checkbox";
      input.value = item;
      input.checked = true;
      input.addEventListener("change", () => {
        const selected = getSelectedFilterValues(key);
        state.filters[key] = selected.length ? selected : [];
        updateFilterSummary(key);
        render();
      });
      const text = document.createElement("span");
      text.textContent = item;
      label.append(input, text);
      control.options.append(label);
    });

    control.toggle.addEventListener("click", () => {
      const shouldOpen = !control.control.classList.contains("open");
      Object.keys(filterConfigs).forEach((filterKey) => {
        if (filterKey !== key) {
          setFilterOpen(filterKey, false);
        }
      });
      setFilterOpen(key, shouldOpen);
    });
    control.selectAll.addEventListener("click", () => {
      state.filters[key] = [...items];
      syncFilterInputs(key);
      updateFilterSummary(key);
      render();
    });
    control.clear.addEventListener("click", () => {
      state.filters[key] = [];
      syncFilterInputs(key);
      updateFilterSummary(key);
      render();
    });

    updateFilterSummary(key);
  });

  filters.reset.addEventListener("click", resetFilters);
  document.addEventListener("click", handleGlobalClick);
  document.addEventListener("keydown", handleGlobalKeydown);
}

function buildRegionMetricTabs() {
  cards.regionMetricTabs.innerHTML = "";
  Object.entries(metricLabels).forEach(([metric, label]) => {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = label;
    button.className = metric === state.regionMetric ? "active" : "";
    button.addEventListener("click", () => {
      state.regionMetric = metric;
      buildRegionMetricTabs();
      renderRegionalAnalysis(getRegionalRecords());
    });
    cards.regionMetricTabs.append(button);
  });
}

function resetFilters() {
  hydrateFilterState();
  Object.keys(filterConfigs).forEach((key) => {
    syncFilterInputs(key);
    updateFilterSummary(key);
    setFilterOpen(key, false);
  });

  render();
}

function getFilterElements(key) {
  const filterIdBase = key === "weeks" ? "week" : key;
  if (!filters[key]) {
    filters[key] = {
      control: document.getElementById(`${filterIdBase}FilterControl`),
      toggle: document.getElementById(`${filterIdBase}FilterToggle`),
      summary: document.getElementById(`${filterIdBase}FilterSummary`),
      panel: document.getElementById(`${filterIdBase}FilterPanel`),
      options: document.getElementById(key === "weeks" ? "weekFilter" : `${filterIdBase}FilterOptions`),
      selectAll: document.getElementById(key === "weeks" ? "weekSelectAll" : `${filterIdBase}FilterSelectAll`),
      clear: document.getElementById(key === "weeks" ? "weekFilterClear" : `${filterIdBase}FilterClear`),
    };
  }
  return filters[key];
}

function getFilterItems(key) {
  const config = filterConfigs[key];
  return [...state.metadata[config.metadataKey]];
}

function getSelectedFilterValues(key) {
  const control = getFilterElements(key);
  return Array.from(control.options.querySelectorAll("input:checked")).map((node) => node.value);
}

function syncFilterInputs(key) {
  const selected = new Set(state.filters[key]);
  const control = getFilterElements(key);
  Array.from(control.options.querySelectorAll("input")).forEach((input) => {
    input.checked = selected.has(input.value);
  });
}

function updateFilterSummary(key) {
  const selected = state.filters[key];
  const items = getFilterItems(key);
  const { label } = filterConfigs[key];
  const control = getFilterElements(key);

  if (!selected.length || selected.length === items.length) {
    if (!selected.length) {
      control.summary.textContent = `No ${label}`;
      return;
    }
    control.summary.textContent = `All ${label}`;
    return;
  }

  if (selected.length <= 2) {
    control.summary.textContent = selected.join(", ");
    return;
  }

  control.summary.textContent = `${selected.length} ${label} selected`;
}

function setFilterOpen(key, isOpen) {
  const control = getFilterElements(key);
  control.control.classList.toggle("open", isOpen);
  control.toggle.setAttribute("aria-expanded", String(isOpen));
  control.panel.hidden = !isOpen;
}

function handleGlobalClick(event) {
  Object.keys(filterConfigs).forEach((key) => {
    const control = getFilterElements(key);
    if (!control.control.contains(event.target)) {
      setFilterOpen(key, false);
    }
  });
}

function handleGlobalKeydown(event) {
  if (event.key === "Escape") {
    Object.keys(filterConfigs).forEach((key) => setFilterOpen(key, false));
  }
}

function getFilteredRecords() {
  return state.records.filter((record) => {
    const targetMatch = state.filters.target.length > 0 && state.filters.target.includes(record.target);
    const regionMatch = state.filters.region.length > 0 && state.filters.region.includes(record.region);
    const channelMatch = state.filters.channel.length > 0 && state.filters.channel.includes(record.channel);
    const timeBandMatch = state.filters.timeBand.length > 0 && state.filters.timeBand.includes(record.time_band);
    const weekMatch = state.filters.weeks.length > 0 && state.filters.weeks.includes(record.year_week);
    return targetMatch && regionMatch && channelMatch && timeBandMatch && weekMatch;
  });
}

function getRegionalRecords() {
  return state.records.filter((record) => {
    const targetMatch = state.filters.target.length > 0 && state.filters.target.includes(record.target);
    const channelMatch = state.filters.channel.length > 0 && state.filters.channel.includes(record.channel);
    const timeBandMatch = state.filters.timeBand.length > 0 && state.filters.timeBand.includes(record.time_band);
    const weekMatch = state.filters.weeks.length > 0 && state.filters.weeks.includes(record.year_week);
    return targetMatch && channelMatch && timeBandMatch && weekMatch;
  });
}

function buildCharts() {
  state.charts.weeklyAma = createChart("weeklyAmaChart", "line");
  state.charts.reachAma = createChart("reachAmaChart", "scatter");
  state.charts.reachTsv = createChart("reachTsvChart", "scatter");
  state.charts.amaTsv = createChart("amaTsvChart", "scatter");
}

function bindModalEvents() {
  document.querySelectorAll("[data-expand-chart]").forEach((button) => {
    button.addEventListener("click", () => openChartModal(button.dataset.expandChart));
  });

  cards.closeModal.addEventListener("click", closeChartModal);
  cards.modal.addEventListener("click", (event) => {
    if (event.target.dataset.closeModal === "true") {
      closeChartModal();
    }
  });
}

function bindSectionTabs() {
  document.querySelectorAll("[data-section-target]").forEach((button) => {
    button.addEventListener("click", () => {
      const target = document.getElementById(button.dataset.sectionTarget);
      if (!target) {
        return;
      }
      target.scrollIntoView({ behavior: "smooth", block: "start" });
      setActiveSectionTab(button.dataset.sectionTarget);
    });
  });
}

function initSectionObserver() {
  if (!("IntersectionObserver" in window)) {
    return;
  }

  const sectionIds = ["weeklySection", "reachAmaSection", "reachTsvSection", "amaTsvSection", "regionalSection"];
  const observer = new IntersectionObserver(
    (entries) => {
      const visible = entries
        .filter((entry) => entry.isIntersecting)
        .sort((left, right) => left.boundingClientRect.top - right.boundingClientRect.top)[0];

      if (visible) {
        setActiveSectionTab(visible.target.id);
      }
    },
    { rootMargin: "-20% 0px -65% 0px", threshold: 0.01 }
  );

  sectionIds.forEach((id) => {
    const element = document.getElementById(id);
    if (element) {
      observer.observe(element);
    }
  });
}

function setActiveSectionTab(sectionId) {
  document.querySelectorAll("[data-section-target]").forEach((button) => {
    button.classList.toggle("active", button.dataset.sectionTarget === sectionId);
  });
}

function createChart(id, type) {
  const ctx = document.getElementById(id).getContext("2d");
  return new Chart(ctx, {
    type,
    data: { datasets: [] },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: { duration: 400 },
      plugins: {
        legend: {
          position: "bottom",
          labels: {
            usePointStyle: true,
            boxWidth: 10,
            font: {
              size: 11,
            },
          },
        },
        tooltip: {
          callbacks: {
            label(context) {
              if (context.raw && typeof context.raw === "object" && "x" in context.raw) {
                const label = context.dataset.label || "";
                const point = context.raw;
                const xLabel = context.chart.options.scales.x.title.text;
                const yLabel = context.chart.options.scales.y.title.text;
                return `${label}: ${xLabel} ${formatTooltipValue(point.x)} | ${yLabel} ${formatTooltipValue(point.y)}`;
              }
              return `${context.dataset.label}: ${formatTooltipValue(context.raw)}`;
            },
          },
        },
        pointLabels: {
          enabled: false,
        },
      },
      scales: {
        x: {
          grid: { color: "rgba(22, 32, 44, 0.08)" },
          ticks: { color: "#657486", font: { size: 11 } },
          title: { color: "#657486", font: { size: 11, weight: "600" } },
        },
        y: {
          grid: { color: "rgba(22, 32, 44, 0.08)" },
          ticks: { color: "#657486", font: { size: 11 } },
          title: { color: "#657486", font: { size: 11, weight: "600" } },
        },
      },
    },
  });
}

function render() {
  const filtered = getFilteredRecords();
  renderKpis(filtered);
  renderWeeklyAma(filtered);
  renderScatterCharts(filtered);
  renderRegionalAnalysis(getRegionalRecords());
}

function renderKpis(records) {
  const totals = records.reduce(
    (accumulator, row) => {
      accumulator.ama += row.ama;
      accumulator.tsv += row.tsv;
      accumulator.viewing_minutes += row.viewing_minutes;
      accumulator.cume_reach += row.cume_reach;
      return accumulator;
    },
    { ama: 0, tsv: 0, viewing_minutes: 0, cume_reach: 0 }
  );

  const channelSummary = groupBy(records, "channel");
  const topChannel = [...channelSummary.entries()]
    .map(([channel, rows]) => ({
      channel,
      ama: sum(rows, "ama"),
    }))
    .sort((a, b) => b.ama - a.ama)[0];

  const kpis = [
    { label: "Total AMA", value: formatCompactMetric(totals.ama), accent: metricColors.ama },
    { label: "Total Cume Reach", value: formatCompactMetric(totals.cume_reach), accent: metricColors.cume_reach },
    { label: "Avg TSV", value: formatters.decimal.format(records.length ? totals.tsv / records.length : 0), accent: metricColors.tsv },
    { label: "Leading Channel", value: topChannel ? topChannel.channel : "No data", accent: metricColors.viewing_minutes },
  ];

  cards.kpis.innerHTML = "";
  kpis.forEach((kpi) => {
    const card = document.createElement("article");
    card.className = "kpi-card";
    card.innerHTML = `<span>${kpi.label}</span><strong>${kpi.value}</strong>`;
    card.style.borderTop = `4px solid ${kpi.accent}`;
    cards.kpis.append(card);
  });
}

function renderWeeklyAma(records) {
  const weeks = [...new Set(records.map((row) => row.year_week))].sort(weekSorter);
  const channelMap = new Map();
  records.forEach((row) => {
    if (!channelMap.has(row.channel)) {
      channelMap.set(row.channel, new Map());
    }
    const weekMap = channelMap.get(row.channel);
    weekMap.set(row.year_week, (weekMap.get(row.year_week) || 0) + row.ama);
  });

  const topChannels = [...channelMap.entries()]
    .map(([channel, weekMap]) => ({
      channel,
      totalAma: [...weekMap.values()].reduce((total, value) => total + value, 0),
      weekMap,
    }))
    .filter((item) => item.channel !== "Hindi News")
    .sort((a, b) => b.totalAma - a.totalAma)
    .slice(0, 6);

  const palette = ["#15c7be", "#183247", "#f4bb42", "#f26d6d", "#7ce6df", "#607d8b"];
  state.charts.weeklyAma.data.labels = weeks;
  state.charts.weeklyAma.data.datasets = topChannels.map((item, index) => ({
    label: item.channel,
    data: weeks.map((week) => item.weekMap.get(week) || 0),
    borderColor: palette[index % palette.length],
    backgroundColor: palette[index % palette.length],
    borderWidth: 2.2,
    pointRadius: 3,
    tension: 0.25,
  }));
  state.charts.weeklyAma.options.scales.x.title = { display: true, text: "Week" };
  state.charts.weeklyAma.options.scales.y.title = { display: true, text: "AMA (000s)" };
  state.charts.weeklyAma.update();
}

function renderScatterCharts(records) {
  const channelPoints = [...groupBy(records, "channel").entries()]
    .map(([channel, rows]) => ({
      channel,
      ama: sum(rows, "ama"),
      tsv: average(rows, "tsv"),
      cume_reach: sum(rows, "cume_reach"),
    }))
    .filter((item) => item.channel !== "Hindi News");

  renderScatter(state.charts.reachAma, channelPoints, {
    xMetric: "cume_reach",
    yMetric: "ama",
    xLabel: "Cumulative Reach (000)",
    yLabel: "AMA (000s)",
    color: metricColors.ama,
  });

  renderScatter(state.charts.reachTsv, channelPoints, {
    xMetric: "cume_reach",
    yMetric: "tsv",
    xLabel: "Cumulative Reach (000)",
    yLabel: "TSV",
    color: metricColors.tsv,
  });

  renderScatter(state.charts.amaTsv, channelPoints, {
    xMetric: "ama",
    yMetric: "tsv",
    xLabel: "AMA (000s)",
    yLabel: "TSV",
    color: metricColors.cume_reach,
  });
}

function renderScatter(chart, rows, config) {
  chart.data.datasets = rows.map((row) => ({
    label: row.channel,
    data: [{ x: row[config.xMetric], y: row[config.yMetric] }],
    backgroundColor: getChannelColor(row.channel),
    borderColor: getChannelColor(row.channel),
    pointBorderColor: "#ffffff",
    pointBorderWidth: 1.5,
    pointRadius: sizeFromMetric(row.ama),
    pointHoverRadius: sizeFromMetric(row.ama) + 2,
  }));
  chart.options.plugins.legend.display = false;
  chart.options.plugins.pointLabels.enabled = true;
  chart.options.scales.x.title = { display: true, text: config.xLabel };
  chart.options.scales.y.title = { display: true, text: config.yLabel };
  chart.update();
}

function renderRegionalAnalysis(records) {
  const regionRows = [...groupBy(records, "region").entries()]
    .map(([region, rows]) => ({
      region,
      ama: sum(rows, "ama"),
      tsv: average(rows, "tsv"),
      viewing_minutes: sum(rows, "viewing_minutes"),
      cume_reach: sum(rows, "cume_reach"),
    }))
    .sort((a, b) => b[state.regionMetric] - a[state.regionMetric]);

  renderRegionalHeatmap(regionRows);
}

function renderRegionalHeatmap(rows) {
  if (!rows.length) {
    cards.regionalHeatmap.innerHTML = '<div class="empty-state">No data matches the current filters.</div>';
    return;
  }

  const metricKeys = ["ama", "tsv", "viewing_minutes", "cume_reach"];
  const ranges = Object.fromEntries(
    metricKeys.map((metric) => [
      metric,
      {
        min: Math.min(...rows.map((row) => row[metric])),
        max: Math.max(...rows.map((row) => row[metric])),
      },
    ])
  );

  const table = document.createElement("table");
  table.className = "heatmap-table";
  table.innerHTML = `
    <thead>
      <tr>
        <th>Region</th>
        <th>AMA</th>
        <th>TSV</th>
        <th>Viewing Min</th>
        <th>Cume Reach</th>
      </tr>
    </thead>
    <tbody></tbody>
  `;

  const tbody = table.querySelector("tbody");
  rows.forEach((row) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${row.region}</td>
      <td class="metric-cell">${formatCompactMetric(row.ama)}</td>
      <td class="metric-cell">${formatters.decimal.format(row.tsv)}</td>
      <td class="metric-cell">${formatCompactMetric(row.viewing_minutes)}</td>
      <td class="metric-cell">${formatCompactMetric(row.cume_reach)}</td>
    `;
    metricKeys.forEach((metric, index) => {
      const cell = tr.children[index + 1];
      const { min, max } = ranges[metric];
      const ratio = max === min ? 1 : (row[metric] - min) / (max - min);
      cell.style.background = `rgba(21, 199, 190, ${0.12 + ratio * 0.72})`;
    });
    tbody.append(tr);
  });

  cards.regionalHeatmap.innerHTML = "";
  cards.regionalHeatmap.append(table);
}

function openChartModal(chartId) {
  const sourceCanvas = document.getElementById(chartId);
  if (!sourceCanvas) {
    return;
  }

  const title = sourceCanvas.closest("[data-chart-card]")?.querySelector("h3")?.textContent || "Chart";
  cards.modalTitle.textContent = title;
  cards.modal.hidden = false;

  if (state.modalChart) {
    state.modalChart.destroy();
  }

  const sourceChart = Chart.getChart(sourceCanvas);
  if (!sourceChart) {
    return;
  }

  const config = cloneChartConfig(sourceChart);
  state.modalChart = new Chart(cards.modalCanvas.getContext("2d"), config);
  requestAnimationFrame(() => {
    if (state.modalChart) {
      state.modalChart.resize();
      state.modalChart.update();
    }
  });
}

function closeChartModal() {
  cards.modal.hidden = true;
  if (state.modalChart) {
    state.modalChart.destroy();
    state.modalChart = null;
  }
}

function cloneChartConfig(sourceChart) {
  const sourceConfig = sourceChart.config._config || sourceChart.config;
  return cloneValue(sourceConfig);
}

function cloneValue(value) {
  if (Array.isArray(value)) {
    return value.map((item) => cloneValue(item));
  }

  if (value && typeof value === "object") {
    const output = {};
    Object.entries(value).forEach(([key, item]) => {
      output[key] = cloneValue(item);
    });
    return output;
  }

  return value;
}

function groupBy(records, key) {
  return records.reduce((map, row) => {
    const value = row[key];
    if (!map.has(value)) {
      map.set(value, []);
    }
    map.get(value).push(row);
    return map;
  }, new Map());
}

function sum(rows, key) {
  return rows.reduce((total, row) => total + row[key], 0);
}

function average(rows, key) {
  return rows.length ? sum(rows, key) / rows.length : 0;
}

function weekSorter(left, right) {
  const leftWeek = Number(left.replace(/\D+/g, ""));
  const rightWeek = Number(right.replace(/\D+/g, ""));
  return leftWeek - rightWeek;
}

function sizeFromMetric(value) {
  if (!Number.isFinite(value) || value <= 0) {
    return 6;
  }
  return Math.min(16, Math.max(6, Math.sqrt(value) / 2.4));
}

function formatCompactMetric(value) {
  if (!Number.isFinite(value)) {
    return "0";
  }
  return formatters.compact.format(value);
}

function formatValue(value) {
  if (!Number.isFinite(value)) {
    return "0";
  }
  return value >= 1000 ? formatCompactMetric(value) : formatters.decimal.format(value);
}

function formatAxisTick(value) {
  if (!Number.isFinite(value)) {
    return "0";
  }
  return value >= 1000 ? formatCompactMetric(value) : formatters.integer.format(value);
}

function formatTooltipValue(value) {
  if (!Number.isFinite(value)) {
    return "0.00";
  }
  return Number(value).toFixed(2);
}

function getChannelColor(channel) {
  const channelIndex = state.metadata?.channels?.indexOf(channel) ?? -1;
  if (channelIndex === -1) {
    return "#475569";
  }
  return channelPalette[channelIndex % channelPalette.length];
}

Chart.register({
  id: "pointLabels",
  afterDatasetsDraw(chart, _args, pluginOptions) {
    if (!pluginOptions?.enabled || chart.config.type !== "scatter") {
      return;
    }

    const { ctx, chartArea } = chart;
    const placedLabelBoxes = [];
    const labelCandidates = [];

    ctx.save();
    ctx.font = '10px "Manrope", sans-serif';
    ctx.fillStyle = "#475569";
    ctx.textBaseline = "middle";

    chart.data.datasets.forEach((dataset, datasetIndex) => {
      const meta = chart.getDatasetMeta(datasetIndex);
      const point = meta.data[0];
      if (!point) {
        return;
      }

      labelCandidates.push({
        label: dataset.label,
        x: point.x,
        y: point.y,
        radius: dataset.pointRadius || 6,
      });
    });

    labelCandidates
      .sort((left, right) => right.radius - left.radius)
      .forEach((candidate) => {
        const placement = findScatterLabelPlacement(ctx, chartArea, candidate, placedLabelBoxes);
        if (!placement) {
          return;
        }

        ctx.textAlign = placement.align;
        ctx.fillText(candidate.label, placement.textX, placement.textY);
        placedLabelBoxes.push(placement.box);
      });

    ctx.restore();
  },
});

function findScatterLabelPlacement(ctx, chartArea, candidate, placedLabelBoxes) {
  const labelWidth = ctx.measureText(candidate.label).width;
  const halfHeight = 6;
  const gap = Math.max(10, candidate.radius + 4);
  const placements = [
    { dx: gap, dy: -gap, align: "left" },
    { dx: gap, dy: gap, align: "left" },
    { dx: -gap, dy: -gap, align: "right" },
    { dx: -gap, dy: gap, align: "right" },
    { dx: 0, dy: -(gap + 2), align: "center" },
    { dx: 0, dy: gap + 2, align: "center" },
  ];

  for (const placement of placements) {
    const textX = candidate.x + placement.dx;
    const textY = candidate.y + placement.dy;
    const box = buildLabelBox(textX, textY, labelWidth, halfHeight, placement.align);
    if (!isLabelBoxInsideChart(box, chartArea)) {
      continue;
    }
    if (placedLabelBoxes.some((placedBox) => doLabelBoxesOverlap(box, placedBox))) {
      continue;
    }
    return { textX, textY, align: placement.align, box };
  }

  return null;
}

function buildLabelBox(textX, textY, labelWidth, halfHeight, align) {
  if (align === "right") {
    return {
      left: textX - labelWidth,
      right: textX,
      top: textY - halfHeight,
      bottom: textY + halfHeight,
    };
  }

  if (align === "center") {
    return {
      left: textX - labelWidth / 2,
      right: textX + labelWidth / 2,
      top: textY - halfHeight,
      bottom: textY + halfHeight,
    };
  }

  return {
    left: textX,
    right: textX + labelWidth,
    top: textY - halfHeight,
    bottom: textY + halfHeight,
  };
}

function isLabelBoxInsideChart(box, chartArea) {
  return (
    box.left >= chartArea.left + 2 &&
    box.right <= chartArea.right - 2 &&
    box.top >= chartArea.top + 2 &&
    box.bottom <= chartArea.bottom - 2
  );
}

function doLabelBoxesOverlap(left, right) {
  return !(
    left.right < right.left ||
    left.left > right.right ||
    left.bottom < right.top ||
    left.top > right.bottom
  );
}

init().catch((error) => {
  console.error(error);
  document.body.innerHTML = `<main class="main-content"><div class="card"><div class="empty-state">Unable to load dashboard data. ${error.message}</div></div></main>`;
});
