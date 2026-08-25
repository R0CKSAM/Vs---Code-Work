const state = {
  records: [],
  metadata: null,
  filters: {
    target: "All",
    region: "All",
    channel: "All",
    timeBand: "All",
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

const filters = {
  target: document.getElementById("targetFilter"),
  region: document.getElementById("regionFilter"),
  channel: document.getElementById("channelFilter"),
  timeBand: document.getElementById("timeBandFilter"),
  weekControl: document.getElementById("weekFilterControl"),
  weekToggle: document.getElementById("weekFilterToggle"),
  weekSummary: document.getElementById("weekFilterSummary"),
  weekPanel: document.getElementById("weekFilterPanel"),
  weekWrap: document.getElementById("weekFilter"),
  weekSelectAll: document.getElementById("weekSelectAll"),
  reset: document.getElementById("resetFilters"),
};

const cards = {
  kpis: document.getElementById("kpiGrid"),
  regionMetricTabs: document.getElementById("regionMetricTabs"),
  regionalHeatmap: document.getElementById("regionalHeatmap"),
  regionalChartWrap: document.getElementById("regionalChartWrap"),
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
  state.filters.weeks = [...payload.metadata.weeks];

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

function buildFilterControls() {
  populateSelect(filters.target, state.metadata.targets, "All");
  populateSelect(filters.region, state.metadata.regions, "All");
  populateSelect(filters.channel, state.metadata.channels, "All");
  populateSelect(filters.timeBand, state.metadata.time_bands, "All");

  filters.weekWrap.innerHTML = "";
  state.metadata.weeks.forEach((week) => {
    const label = document.createElement("label");
    label.className = "week-pill";
    const input = document.createElement("input");
    input.type = "checkbox";
    input.value = week;
    input.checked = true;
    input.addEventListener("change", () => {
      const checked = getSelectedWeekValues();
      state.filters.weeks = checked.length ? checked : [];
      updateWeekFilterSummary();
      render();
    });
    label.append(input, document.createTextNode(week));
    filters.weekWrap.append(label);
  });

  filters.target.addEventListener("change", () => {
    state.filters.target = filters.target.value;
    render();
  });
  filters.region.addEventListener("change", () => {
    state.filters.region = filters.region.value;
    render();
  });
  filters.channel.addEventListener("change", () => {
    state.filters.channel = filters.channel.value;
    render();
  });
  filters.timeBand.addEventListener("change", () => {
    state.filters.timeBand = filters.timeBand.value;
    render();
  });
  filters.weekToggle.addEventListener("click", () => {
    setWeekFilterOpen(!filters.weekControl.classList.contains("open"));
  });
  filters.weekSelectAll.addEventListener("click", () => {
    state.filters.weeks = [...state.metadata.weeks];
    syncWeekFilterInputs();
    updateWeekFilterSummary();
    render();
  });
  filters.reset.addEventListener("click", resetFilters);
  document.addEventListener("click", handleGlobalClick);
  document.addEventListener("keydown", handleGlobalKeydown);
  updateWeekFilterSummary();
}

function populateSelect(element, items, defaultValue) {
  element.innerHTML = "";
  [defaultValue, ...items].forEach((item) => {
    const option = document.createElement("option");
    option.value = item;
    option.textContent = item;
    element.append(option);
  });
  element.value = defaultValue;
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
      renderRegionalAnalysis(getFilteredRecords());
    });
    cards.regionMetricTabs.append(button);
  });
}

function resetFilters() {
  state.filters = {
    target: "All",
    region: "All",
    channel: "All",
    timeBand: "All",
    weeks: [...state.metadata.weeks],
  };

  filters.target.value = "All";
  filters.region.value = "All";
  filters.channel.value = "All";
  filters.timeBand.value = "All";
  syncWeekFilterInputs();
  updateWeekFilterSummary();
  setWeekFilterOpen(false);

  render();
}

function getSelectedWeekValues() {
  return Array.from(filters.weekWrap.querySelectorAll("input:checked")).map((node) => node.value);
}

function syncWeekFilterInputs() {
  const selectedWeeks = new Set(state.filters.weeks);
  Array.from(filters.weekWrap.querySelectorAll("input")).forEach((input) => {
    input.checked = selectedWeeks.has(input.value);
  });
}

function updateWeekFilterSummary() {
  const selectedWeeks = state.filters.weeks;
  const totalWeeks = state.metadata?.weeks?.length || 0;

  if (!selectedWeeks.length || selectedWeeks.length === totalWeeks) {
    filters.weekSummary.textContent = "All weeks";
    return;
  }

  if (selectedWeeks.length <= 2) {
    filters.weekSummary.textContent = selectedWeeks.join(", ");
    return;
  }

  filters.weekSummary.textContent = `${selectedWeeks.length} weeks selected`;
}

function setWeekFilterOpen(isOpen) {
  filters.weekControl.classList.toggle("open", isOpen);
  filters.weekToggle.setAttribute("aria-expanded", String(isOpen));
  filters.weekPanel.hidden = !isOpen;
}

function handleGlobalClick(event) {
  if (!filters.weekControl.contains(event.target)) {
    setWeekFilterOpen(false);
  }
}

function handleGlobalKeydown(event) {
  if (event.key === "Escape") {
    setWeekFilterOpen(false);
  }
}

function getFilteredRecords() {
  return state.records.filter((record) => {
    const targetMatch = state.filters.target === "All" || record.target === state.filters.target;
    const regionMatch = state.filters.region === "All" || record.region === state.filters.region;
    const channelMatch = state.filters.channel === "All" || record.channel === state.filters.channel;
    const timeBandMatch = state.filters.timeBand === "All" || record.time_band === state.filters.timeBand;
    const weekMatch = state.filters.weeks.length === 0 || state.filters.weeks.includes(record.year_week);
    return targetMatch && regionMatch && channelMatch && timeBandMatch && weekMatch;
  });
}

function buildCharts() {
  state.charts.weeklyAma = createChart("weeklyAmaChart", "line");
  state.charts.reachAma = createChart("reachAmaChart", "scatter");
  state.charts.reachTsv = createChart("reachTsvChart", "scatter");
  state.charts.amaTsv = createChart("amaTsvChart", "scatter");
  state.charts.regional = createChart("regionalChart", "bar");
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

  const sectionIds = ["summarySection", "weeklySection", "reachAmaSection", "reachTsvSection", "amaTsvSection", "regionalSection"];
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
                return `${label}: ${xLabel} ${formatValue(point.x)} | ${yLabel} ${formatValue(point.y)}`;
              }
              return `${context.dataset.label}: ${formatValue(context.raw)}`;
            },
          },
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
  renderRegionalAnalysis(filtered);
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

  setRegionalChartHeight(regionRows.length);
  state.charts.regional.data.labels = regionRows.map((row) => row.region);
  state.charts.regional.data.datasets = [
    {
      label: metricLabels[state.regionMetric],
      data: regionRows.map((row) => row[state.regionMetric]),
      backgroundColor: regionRows.map((_, index) => {
        const ratio = regionRows.length <= 1 ? 1 : 1 - index / (regionRows.length - 1);
        return `rgba(21, 199, 190, ${0.25 + ratio * 0.7})`;
      }),
      borderRadius: 10,
      borderSkipped: false,
    },
  ];
  state.charts.regional.options.indexAxis = "y";
  state.charts.regional.options.layout = { padding: { right: 12 } };
  state.charts.regional.options.plugins.legend.display = false;
  state.charts.regional.options.scales.x.title = { display: true, text: metricLabels[state.regionMetric] };
  state.charts.regional.options.scales.y.title = { display: false, text: "Region" };
  state.charts.regional.options.scales.x.ticks = {
    color: "#657486",
    font: { size: 11 },
    callback(value) {
      return formatAxisTick(value);
    },
  };
  state.charts.regional.options.scales.y.ticks = {
    color: "#657486",
    font: { size: 11 },
    autoSkip: false,
  };
  state.charts.regional.resize();
  state.charts.regional.update();

  renderRegionalHeatmap(regionRows);
}

function setRegionalChartHeight(regionCount) {
  const nextHeight = Math.max(360, regionCount * 34);
  cards.regionalChartWrap.style.height = `${nextHeight}px`;
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

function buildActiveSelectionLabel() {
  const parts = [];
  if (state.filters.target !== "All") {
    parts.push(state.filters.target);
  }
  if (state.filters.region !== "All") {
    parts.push(state.filters.region);
  }
  if (state.filters.channel !== "All") {
    parts.push(state.filters.channel);
  }
  return parts.length ? parts.join(" / ") : "All Data";
}

function getChannelColor(channel) {
  const channelIndex = state.metadata?.channels?.indexOf(channel) ?? -1;
  if (channelIndex === -1) {
    return "#475569";
  }
  return channelPalette[channelIndex % channelPalette.length];
}

init().catch((error) => {
  console.error(error);
  document.body.innerHTML = `<main class="main-content"><div class="card"><div class="empty-state">Unable to load dashboard data. ${error.message}</div></div></main>`;
});
