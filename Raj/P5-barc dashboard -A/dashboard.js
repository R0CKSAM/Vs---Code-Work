// JavaScript Engine for BARC Audience Reach & Loyalty Dashboard
// Implements isolated horizontal filters for each graph card.

// Global Dataset Variables
let rawData = [];
let channels = [];
let regions = [];
let weeks = [];
let targets = [];

// Isolated Filter States for each Graph
const states = {
  G1: { target: "", regions: [], weeks: [], channels: [], viewMode: "rank" },
  G2: { target: "", regions: [], weeks: [], channels: [] },
  G3: { target: "", regions: [], weeks: [], channels: [] },
  G4: { target: "", regions: [], weeks: [], channels: [] },
  G5: { target: "", weeks: [], channels: [] } // Graph 5 compares regions, so it has no region filter
};

// Active Region row highlighted in G5 table
let activeRegionRow = "HSM";

// Active Chart Instances (for re-rendering/updating safely)
let chartWeeklyRankInstance = null;
let chartReachAMAInstance = null;
let chartReachTSVInstance = null;
let chartAMATSVInstance = null;
let chartRegionalBarInstance = null;

// Channel Colors Mapping (Consistent across all charts)
const CHANNEL_COLORS = {
  "Aaj Tak": "#ea580c",          // Orange-Red
  "India TV": "#0ea5e9",         // Sky Blue
  "News18 India": "#e11d48",     // Rose Red
  "NDTV India": "#10b981",       // Emerald Green
  "ABP News": "#eab308",         // Yellow
  "News 24": "#3b82f6",          // Royal Blue
  "News Nation": "#a855f7",      // Purple
  "Republic Bharat": "#0d9488",  // Teal
  "Good News Today": "#ec4899",  // Pink
  "Zee News": "#f97316",         // Orange
  "Times Now Navbharat": "#6366f1", // Indigo
  "TV9 Bharatvarsh": "#84cc16",  // Lime
  "Hindi News": "#64748b"        // Slate Gray (aggregate)
};

const COLOR_PALETTE = [
  "#3b82f6", "#10b981", "#a855f7", "#f97316", "#eab308", 
  "#ec4899", "#14b8a6", "#6366f1", "#f43f5e", "#06b6d4"
];

function getChannelColor(channelName, index) {
  if (CHANNEL_COLORS[channelName]) {
    return CHANNEL_COLORS[channelName];
  }
  return COLOR_PALETTE[index % COLOR_PALETTE.length];
}

// ----------------------------------------------------
// Initialization
// ----------------------------------------------------
document.addEventListener("DOMContentLoaded", () => {
  if (typeof DASHBOARD_DATA !== "undefined" && DASHBOARD_DATA.data) {
    rawData = DASHBOARD_DATA.data;
    parseDataset();
    initializeAllFilters();
    setupGlobalEventListeners();
    updateAllCharts();
  } else {
    console.error("DASHBOARD_DATA not found. Please verify data.js is loaded.");
  }
});

// Extract unique filter keys from raw excel data
function parseDataset() {
  const uniqueTargets = new Set();
  const uniqueRegions = new Set();
  const uniqueWeeks = new Set();
  const uniqueChannels = new Set();

  rawData.forEach(row => {
    if (row.Targets) uniqueTargets.add(row.Targets);
    if (row.Regions) uniqueRegions.add(row.Regions);
    if (row["Year&Week"]) uniqueWeeks.add(row["Year&Week"]);
    if (row.Channel) uniqueChannels.add(row.Channel);
  });

  targets = Array.from(uniqueTargets).sort();
  regions = Array.from(uniqueRegions).sort();
  weeks = Array.from(uniqueWeeks).sort((a, b) => {
    const numA = parseInt(a.replace(/[^0-9]/g, ""));
    const numB = parseInt(b.replace(/[^0-9]/g, ""));
    return numA - numB;
  });
  
  // Channels: exclude aggregate "Hindi News" row for channel specific comparisons
  channels = Array.from(uniqueChannels).filter(c => c !== "Hindi News").sort();

  // Initialize active region row
  if (regions.includes("HSM")) activeRegionRow = "HSM";
  else if (regions.length > 0) activeRegionRow = regions[0];

  // Initialize initial states for all 5 graphs
  Object.keys(states).forEach(gId => {
    states[gId].target = targets[0] || "NCCS 15+";
    if (states[gId].regions !== undefined) {
      states[gId].regions = [...regions];
    }
    states[gId].weeks = [...weeks];
    states[gId].channels = [...channels];
  });
}

// Populate filters row in the DOM for each chart card
function initializeAllFilters() {
  buildFiltersForChart("G1", true);
  buildFiltersForChart("G2", true);
  buildFiltersForChart("G3", true);
  buildFiltersForChart("G4", true);
  buildFiltersForChart("G5", false); // G5 (Regional analysis) has no region filter
}

function buildFiltersForChart(graphId, hasRegionFilter) {
  const container = document.getElementById(`filters${graphId}`);
  if (!container) return;
  container.innerHTML = "";

  // 1. Target Group select dropdown
  const targetGroup = document.createElement("div");
  targetGroup.className = "filter-group";
  targetGroup.innerHTML = `
    <label for="target_${graphId}">Target</label>
    <select id="target_${graphId}" class="filter-select">
      ${targets.map(t => `<option value="${t}" ${t === states[graphId].target ? 'selected' : ''}>${t}</option>`).join('')}
    </select>
  `;
  container.appendChild(targetGroup);
  
  targetGroup.querySelector("select").addEventListener("change", (e) => {
    states[graphId].target = e.target.value;
    triggerChartUpdate(graphId);
  });

  // 2. Regions multi-select dropdown (if allowed)
  if (hasRegionFilter) {
    const regionDiv = buildMultiSelectDOM(graphId, "region", regions, states[graphId].regions);
    container.appendChild(regionDiv);
  }

  // 3. Weeks multi-select dropdown
  const weekDiv = buildMultiSelectDOM(graphId, "week", weeks, states[graphId].weeks);
  container.appendChild(weekDiv);

  // 4. Channels multi-select dropdown
  const channelDiv = buildMultiSelectDOM(graphId, "channel", channels, states[graphId].channels);
  container.appendChild(channelDiv);

  // 5. Reset button
  const resetBtn = document.createElement("button");
  resetBtn.className = "btn-reset";
  resetBtn.id = `reset_${graphId}`;
  resetBtn.innerHTML = `
    <svg width="12" height="12" fill="none" viewBox="0 0 24 24" stroke="currentColor">
      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 1121.21 7.89M9 11l3-3 3 3m-3-3v12" />
    </svg> Reset
  `;
  resetBtn.addEventListener("click", () => {
    resetChartState(graphId);
  });
  container.appendChild(resetBtn);
}

// Helper to build custom multiselect dropdown elements with search filter and checkboxes
function buildMultiSelectDOM(graphId, type, items, selectedArray) {
  const div = document.createElement("div");
  div.className = "filter-group";
  
  const labelText = type.charAt(0).toUpperCase() + type.slice(1);
  const dropdownId = `dropdown_${type}_${graphId}`;
  const triggerId = `trigger_${type}_${graphId}`;
  const panelId = `panel_${type}_${graphId}`;
  const searchId = `search_${type}_${graphId}`;
  const optionsId = `options_${type}_${graphId}`;
  const selectAllId = `selectAll_${type}_${graphId}`;
  const clearAllId = `clearAll_${type}_${graphId}`;
  
  div.innerHTML = `
    <label>${labelText}</label>
    <div class="multiselect-dropdown" id="${dropdownId}">
      <button class="multiselect-trigger" id="${triggerId}">All ${labelText}s</button>
      <div class="multiselect-panel" id="${panelId}">
        ${type !== "week" ? `<input type="text" class="multiselect-search" id="${searchId}" placeholder="Search ${type}s...">` : ''}
        <div class="multiselect-actions">
          <button id="${selectAllId}">Select All</button>
          <button id="${clearAllId}">Clear All</button>
        </div>
        <div class="multiselect-options" id="${optionsId}"></div>
      </div>
    </div>
  `;

  const optionsContainer = div.querySelector(`#${optionsId}`);
  
  items.forEach((item, index) => {
    const option = document.createElement("div");
    option.className = "multiselect-option";
    if (selectedArray.includes(item)) option.classList.add("selected");
    option.setAttribute("data-value", item);

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = selectedArray.includes(item);
    checkbox.id = `${graphId}_${type}_opt_${index}`;
    
    const label = document.createElement("label");
    label.htmlFor = `${graphId}_${type}_opt_${index}`;
    label.textContent = item;
    label.style.flexGrow = "1";
    label.style.cursor = "pointer";

    option.appendChild(checkbox);
    option.appendChild(label);
    optionsContainer.appendChild(option);

    const handleToggle = (checked) => {
      checkbox.checked = checked;
      if (checked) {
        if (!selectedArray.includes(item)) selectedArray.push(item);
        option.classList.add("selected");
      } else {
        const idx = selectedArray.indexOf(item);
        if (idx > -1) selectedArray.splice(idx, 1);
        option.classList.remove("selected");
      }
      updateTriggerText(graphId, type, selectedArray, items);
      triggerChartUpdate(graphId);
    };

    option.addEventListener("click", (e) => {
      if (e.target !== checkbox && e.target !== label) {
        handleToggle(!checkbox.checked);
      }
    });

    checkbox.addEventListener("change", () => {
      handleToggle(checkbox.checked);
    });
  });

  // Wait for DOM layout, then set trigger text
  setTimeout(() => updateTriggerText(graphId, type, selectedArray, items), 0);

  // Setup click toggling for dropdown triggers
  const trigger = div.querySelector(`#${triggerId}`);
  const dropdown = div.querySelector(`#${dropdownId}`);
  trigger.addEventListener("click", (e) => {
    e.stopPropagation();
    const wasOpen = dropdown.classList.contains("open");
    document.querySelectorAll(".multiselect-dropdown").forEach(d => d.classList.remove("open"));
    if (!wasOpen) dropdown.classList.add("open");
  });

  // Prevent click closing inside panels
  div.querySelector(`#${panelId}`).addEventListener("click", (e) => {
    e.stopPropagation();
  });

  // Bulk actions: select all
  div.querySelector(`#${selectAllId}`).addEventListener("click", () => {
    selectedArray.length = 0;
    selectedArray.push(...items);
    optionsContainer.querySelectorAll(".multiselect-option").forEach(opt => {
      opt.classList.add("selected");
      opt.querySelector("input").checked = true;
    });
    updateTriggerText(graphId, type, selectedArray, items);
    triggerChartUpdate(graphId);
  });

  // Bulk actions: clear all
  div.querySelector(`#${clearAllId}`).addEventListener("click", () => {
    selectedArray.length = 0;
    optionsContainer.querySelectorAll(".multiselect-option").forEach(opt => {
      opt.classList.remove("selected");
      opt.querySelector("input").checked = false;
    });
    updateTriggerText(graphId, type, selectedArray, items);
    triggerChartUpdate(graphId);
  });

  // Option text search filter
  if (type !== "week") {
    const searchInput = div.querySelector(`#${searchId}`);
    searchInput.addEventListener("input", (e) => {
      const val = e.target.value.toLowerCase();
      optionsContainer.querySelectorAll(".multiselect-option").forEach(opt => {
        const txt = opt.getAttribute("data-value").toLowerCase();
        opt.style.display = txt.includes(val) ? "flex" : "none";
      });
    });
  }

  return div;
}

function updateTriggerText(graphId, type, selectedArray, itemsArray) {
  const trigger = document.getElementById(`trigger_${type}_${graphId}`);
  if (!trigger) return;
  
  if (selectedArray.length === 0) {
    trigger.textContent = "None Selected";
  } else if (selectedArray.length === itemsArray.length) {
    trigger.textContent = `All ${type.charAt(0).toUpperCase() + type.slice(1)}s`;
  } else {
    trigger.textContent = `${selectedArray.length} Selected`;
  }
}

function resetChartState(graphId) {
  states[graphId].target = targets[0] || "NCCS 15+";
  if (states[graphId].regions) states[graphId].regions = [...regions];
  states[graphId].weeks = [...weeks];
  states[graphId].channels = [...channels];
  
  buildFiltersForChart(graphId, graphId !== "G5");
  triggerChartUpdate(graphId);
}

// ----------------------------------------------------
// Global Click & Button Actions
// ----------------------------------------------------
function setupGlobalEventListeners() {
  // Click outside closes all multiselect dropdown panels
  document.addEventListener("click", () => {
    document.querySelectorAll(".multiselect-dropdown").forEach(d => d.classList.remove("open"));
  });

  // Graph 1 View Mode Toggles (Ranking vs AMA trend lines)
  document.getElementById("toggleRankView").addEventListener("click", () => {
    states.G1.viewMode = "rank";
    document.getElementById("toggleRankView").classList.add("active");
    document.getElementById("toggleAMAView").classList.remove("active");
    renderWeeklyRankChart();
  });

  document.getElementById("toggleAMAView").addEventListener("click", () => {
    states.G1.viewMode = "ama";
    document.getElementById("toggleAMAView").classList.add("active");
    document.getElementById("toggleRankView").classList.remove("active");
    renderWeeklyRankChart();
  });
}

// Filter dataset according to a specific graph's state configuration
function getFilteredDataForState(state, excludeChannelFiltering = false) {
  return rawData.filter(row => {
    const matchTarget = row.Targets === state.target;
    const matchRegion = !state.regions || state.regions.includes(row.Regions);
    const matchWeek = state.weeks.includes(row["Year&Week"]);
    const matchChannel = excludeChannelFiltering || state.channels.includes(row.Channel);
    return matchTarget && matchRegion && matchWeek && matchChannel;
  });
}

// Trigger re-render of a single chart
function triggerChartUpdate(graphId) {
  if (graphId === "G1") {
    renderWeeklyRankChart();
    // Update overall KPIs based on Graph 1 filters to show context
    calculateKPIs(getFilteredDataForState(states.G1));
  } 
  else if (graphId === "G2") renderG2();
  else if (graphId === "G3") renderG3();
  else if (graphId === "G4") renderG4();
  else if (graphId === "G5") renderG5();
}

// Render all charts together on initial load
function updateAllCharts() {
  const initialG1Data = getFilteredDataForState(states.G1);
  calculateKPIs(initialG1Data);
  
  renderWeeklyRankChart();
  renderG2();
  renderG3();
  renderG4();
  renderG5();
}

// Calculate top summary stats metrics (based on active G1 parameters)
function calculateKPIs(filtered) {
  const channelMetrics = {};
  let totalViewingMinutes = 0;
  
  filtered.forEach(row => {
    const chan = row.Channel;
    
    // Ignore aggregate baseline channel row
    if (chan === "Hindi News") return;
    
    if (!channelMetrics[chan]) {
      channelMetrics[chan] = { amaSum: 0, viewingMinsSum: 0, reachSum: 0 };
    }
    
    channelMetrics[chan].amaSum += row["AMA 000's"] || 0;
    channelMetrics[chan].viewingMinsSum += row["Viewing Minutes'000"] || 0;
    channelMetrics[chan].reachSum += row["Cume Rch'000"] || 0;
  });
  
  filtered.forEach(row => {
    if (row.Channel !== "Hindi News") {
      totalViewingMinutes += row["Viewing Minutes'000"] || 0;
    }
  });

  let topAMAChannel = "-";
  let topAMAMax = -1;
  let topReachChannel = "-";
  let topReachMax = -1;
  let topLoyaltyChannel = "-";
  let topLoyaltyMax = -1;

  Object.keys(channelMetrics).forEach(chan => {
    const m = channelMetrics[chan];
    const avgAMA = m.amaSum / states.G1.weeks.length;
    const avgReach = m.reachSum / states.G1.weeks.length;
    const tsv = m.reachSum > 0 ? (m.viewingMinsSum / m.reachSum) : 0;
    
    if (avgAMA > topAMAMax) {
      topAMAMax = avgAMA;
      topAMAChannel = chan;
    }
    if (avgReach > topReachMax) {
      topReachMax = avgReach;
      topReachChannel = chan;
    }
    if (tsv > topLoyaltyMax) {
      topLoyaltyMax = tsv;
      topLoyaltyChannel = chan;
    }
  });

  document.getElementById("kpiLeadAMA").textContent = topAMAChannel;
  document.getElementById("kpiLeadAMAVal").textContent = topAMAMax >= 0 ? topAMAMax.toFixed(1) + "k" : "-";

  document.getElementById("kpiLeadReach").textContent = topReachChannel;
  document.getElementById("kpiLeadReachVal").textContent = topReachMax >= 0 ? topReachMax.toFixed(0) + "k" : "-";

  document.getElementById("kpiLeadLoyalty").textContent = topLoyaltyChannel;
  document.getElementById("kpiLeadLoyaltyVal").textContent = topLoyaltyMax >= 0 ? topLoyaltyMax.toFixed(1) + " Min" : "-";

  document.getElementById("kpiTotalMinutes").textContent = (totalViewingMinutes / 1000).toLocaleString(undefined, { maximumFractionDigits: 1 }) + "M Mins";
}

// ----------------------------------------------------
// GRAPH 1: WEEKLY RANKINGS & AMA BUMP LINE CHART
// ----------------------------------------------------
function renderWeeklyRankChart() {
  const ctx = document.getElementById("chartWeeklyRank").getContext("2d");
  if (chartWeeklyRankInstance) {
    chartWeeklyRankInstance.destroy();
  }

  const activeState = states.G1;
  const activeWeeks = activeState.weeks;
  const activeChannels = activeState.channels;

  // Initialize weekly dataset
  const datasetByWeek = {};
  activeWeeks.forEach(wk => {
    datasetByWeek[wk] = {};
    activeChannels.forEach(c => {
      datasetByWeek[wk][c] = { ama: 0 };
    });
  });

  // Filter data using G1 filters
  const rows = getFilteredDataForState(activeState);
  rows.forEach(row => {
    const wk = row["Year&Week"];
    const chan = row.Channel;
    if (datasetByWeek[wk] && datasetByWeek[wk][chan]) {
      datasetByWeek[wk][chan].ama += row["AMA 000's"] || 0;
    }
  });

  // Calculate ranks
  const ranksByWeek = {};
  activeWeeks.forEach(wk => {
    ranksByWeek[wk] = {};
    const chanValues = Object.keys(datasetByWeek[wk]).map(chan => {
      return { channel: chan, val: datasetByWeek[wk][chan].ama };
    });
    chanValues.sort((a, b) => b.val - a.val);
    chanValues.forEach((item, index) => {
      ranksByWeek[wk][item.channel] = index + 1;
    });
  });

  // Format line datasets
  const chartDatasets = activeChannels.map((chan, idx) => {
    const dataPoints = activeWeeks.map(wk => {
      if (activeState.viewMode === "rank") {
        return ranksByWeek[wk][chan] || null;
      } else {
        return datasetByWeek[wk][chan] ? datasetByWeek[wk][chan].ama : 0;
      }
    });

    const color = getChannelColor(chan, idx);
    return {
      label: chan,
      data: dataPoints,
      borderColor: color,
      backgroundColor: color + "20",
      borderWidth: activeState.viewMode === "rank" ? 4 : 2.5,
      pointRadius: 6,
      pointHoverRadius: 8,
      tension: 0.2,
      fill: activeState.viewMode !== "rank"
    };
  });

  chartWeeklyRankInstance = new Chart(ctx, {
    type: "line",
    data: {
      labels: activeWeeks,
      datasets: chartDatasets
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: "bottom",
          labels: { color: "#94a3b8", font: { family: "Outfit", size: 12 } }
        },
        tooltip: {
          mode: "index",
          intersect: false,
          backgroundColor: "#1e293b",
          titleFont: { family: "Outfit", size: 13, weight: "bold" },
          bodyFont: { family: "Outfit", size: 12 },
          borderColor: "rgba(255,255,255,0.1)",
          borderWidth: 1,
          callbacks: {
            label: function(context) {
              const label = context.dataset.label || "";
              const val = context.raw;
              if (activeState.viewMode === "rank") {
                return `${label}: Rank ${val}`;
              } else {
                return `${label}: ${val.toFixed(1)}k AMA`;
              }
            }
          }
        }
      },
      scales: {
        x: {
          grid: { color: "rgba(255,255,255,0.05)" },
          ticks: { color: "#94a3b8", font: { family: "Outfit" } }
        },
        y: {
          grid: { color: "rgba(255,255,255,0.05)" },
          ticks: { 
            color: "#94a3b8", 
            font: { family: "Outfit" },
            stepSize: activeState.viewMode === "rank" ? 1 : undefined
          },
          reversed: activeState.viewMode === "rank",
          min: activeState.viewMode === "rank" ? 1 : undefined,
          max: activeState.viewMode === "rank" ? Math.max(activeChannels.length, 5) : undefined,
          title: {
            display: true,
            text: activeState.viewMode === "rank" ? "Channel Rank" : "AMA (000's)",
            color: "#94a3b8",
            font: { family: "Outfit", size: 12, weight: "bold" }
          }
        }
      }
    }
  });
}

// ----------------------------------------------------
// GRAPH 2: REACH VS AMA SCATTER CHART
// ----------------------------------------------------
function renderG2() {
  const activeState = states.G2;
  const filtered = getFilteredDataForState(activeState);
  
  const stats = aggregateChannelStats(filtered, activeState.channels);
  
  renderScatterChart(
    "chartReachAMA", 
    stats.points.map(p => ({ x: p.reach, y: p.ama, label: p.channel, tsv: p.tsv })),
    "Cume Reach (000's)", 
    "AMA (000's)", 
    stats.avgReach, 
    stats.avgAMA,
    chartReachAMAInstance,
    (inst) => { chartReachAMAInstance = inst; }
  );
}

// ----------------------------------------------------
// GRAPH 3: REACH VS TSV SCATTER CHART
// ----------------------------------------------------
function renderG3() {
  const activeState = states.G3;
  const filtered = getFilteredDataForState(activeState);
  
  const stats = aggregateChannelStats(filtered, activeState.channels);

  renderScatterChart(
    "chartReachTSV", 
    stats.points.map(p => ({ x: p.reach, y: p.tsv, label: p.channel, ama: p.ama })),
    "Cume Reach (000's)", 
    "TSV (Minutes)", 
    stats.avgReach, 
    stats.avgTSV,
    chartReachTSVInstance,
    (inst) => { chartReachTSVInstance = inst; }
  );
}

// ----------------------------------------------------
// GRAPH 4: AMA VS TSV SCATTER CHART
// ----------------------------------------------------
function renderG4() {
  const activeState = states.G4;
  const filtered = getFilteredDataForState(activeState);
  
  const stats = aggregateChannelStats(filtered, activeState.channels);

  renderScatterChart(
    "chartAMATSV", 
    stats.points.map(p => ({ x: p.ama, y: p.tsv, label: p.channel, reach: p.reach })),
    "AMA (000's)", 
    "TSV (Minutes)", 
    stats.avgAMA, 
    stats.avgTSV,
    chartAMATSVInstance,
    (inst) => { chartAMATSVInstance = inst; }
  );
}

// Helper to aggregate stats for scatter plots
function aggregateChannelStats(filtered, activeChannels) {
  const channelData = {};
  activeChannels.forEach(c => {
    channelData[c] = { amaSum: 0, reachSum: 0, viewingMinsSum: 0, count: 0 };
  });

  filtered.forEach(row => {
    const chan = row.Channel;
    if (channelData[chan]) {
      channelData[chan].amaSum += row["AMA 000's"] || 0;
      channelData[chan].reachSum += row["Cume Rch'000"] || 0;
      channelData[chan].viewingMinsSum += row["Viewing Minutes'000"] || 0;
      channelData[chan].count++;
    }
  });

  const points = [];
  let sumAMA = 0, sumReach = 0, sumTSV = 0;
  
  Object.keys(channelData).forEach(chan => {
    const d = channelData[chan];
    if (d.count > 0) {
      const avgAMA = d.amaSum / states.G1.weeks.length;
      const avgReach = d.reachSum / states.G1.weeks.length;
      const avgTSV = d.reachSum > 0 ? (d.viewingMinsSum / d.reachSum) : 0;
      
      points.push({ channel: chan, ama: avgAMA, reach: avgReach, tsv: avgTSV });
      sumAMA += avgAMA;
      sumReach += avgReach;
      sumTSV += avgTSV;
    }
  });

  return {
    points: points,
    avgAMA: points.length > 0 ? (sumAMA / points.length) : 0,
    avgReach: points.length > 0 ? (sumReach / points.length) : 0,
    avgTSV: points.length > 0 ? (sumTSV / points.length) : 0
  };
}

// Low-level scatter plot visual engine using Chart.js datasets
function renderScatterChart(canvasId, points, xLabel, yLabel, midX, midY, currentChartInstance, setChartInstanceCallback) {
  const ctx = document.getElementById(canvasId).getContext("2d");
  if (currentChartInstance) {
    currentChartInstance.destroy();
  }

  const scatterPoints = points.map((p, idx) => {
    return {
      x: p.x,
      y: p.y,
      label: p.label,
      extraInfo: p.tsv !== undefined ? `TSV: ${p.tsv.toFixed(1)}m` : 
                 (p.ama !== undefined ? `AMA: ${p.ama.toFixed(1)}k` : `Reach: ${p.reach.toFixed(0)}k`),
      backgroundColor: getChannelColor(p.label, idx),
      borderColor: getChannelColor(p.label, idx) + "ff",
      pointRadius: 10,
      pointHoverRadius: 12
    };
  });

  const xValues = points.map(p => p.x);
  const yValues = points.map(p => p.y);
  
  const minXVal = Math.min(...xValues, 0) * 0.9;
  const maxXVal = Math.max(...xValues, 10) * 1.1;
  const minYVal = Math.min(...yValues, 0) * 0.9;
  const maxYVal = Math.max(...yValues, 10) * 1.1;

  // Crosshair datasets for horizontal & vertical median quadrant lines
  const crosshairDatasets = [
    {
      type: "line",
      label: "Avg " + xLabel.split(" ")[0],
      data: [{ x: midX, y: minYVal }, { x: midX, y: maxYVal }],
      borderColor: "rgba(255, 255, 255, 0.12)",
      borderWidth: 1.5,
      borderDash: [4, 4],
      pointRadius: 0,
      showLine: true
    },
    {
      type: "line",
      label: "Avg " + yLabel.split(" ")[0],
      data: [{ x: minXVal, y: midY }, { x: maxXVal, y: midY }],
      borderColor: "rgba(255, 255, 255, 0.12)",
      borderWidth: 1.5,
      borderDash: [4, 4],
      pointRadius: 0,
      showLine: true
    }
  ];

  const newChart = new Chart(ctx, {
    type: "scatter",
    data: {
      datasets: [
        {
          label: "Channels",
          data: scatterPoints,
          backgroundColor: scatterPoints.map(p => p.backgroundColor),
          borderColor: scatterPoints.map(p => p.borderColor),
          borderWidth: 1,
          pointRadius: scatterPoints.map(p => p.pointRadius),
          pointHoverRadius: scatterPoints.map(p => p.pointHoverRadius)
        },
        ...crosshairDatasets
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: "#111827",
          titleFont: { family: "Outfit", size: 13, weight: "bold" },
          bodyFont: { family: "Outfit", size: 12 },
          borderColor: "rgba(255,255,255,0.08)",
          borderWidth: 1,
          callbacks: {
            label: function(context) {
              const pt = context.raw;
              if (pt.label) {
                return [
                  `${pt.label}`,
                  `${xLabel}: ${pt.x.toLocaleString(undefined, { maximumFractionDigits: 1 })}`,
                  `${yLabel}: ${pt.y.toLocaleString(undefined, { maximumFractionDigits: 1 })}`,
                  `${pt.extraInfo}`
                ];
              }
              return null;
            }
          }
        }
      },
      scales: {
        x: {
          type: "linear",
          position: "bottom",
          grid: { color: "rgba(255,255,255,0.02)" },
          ticks: { color: "#94a3b8", font: { family: "Outfit" } },
          min: minXVal,
          max: maxXVal,
          title: {
            display: true,
            text: xLabel,
            color: "#94a3b8",
            font: { family: "Outfit", size: 11, weight: "bold" }
          }
        },
        y: {
          grid: { color: "rgba(255,255,255,0.02)" },
          ticks: { color: "#94a3b8", font: { family: "Outfit" } },
          min: minYVal,
          max: maxYVal,
          title: {
            display: true,
            text: yLabel,
            color: "#94a3b8",
            font: { family: "Outfit", size: 11, weight: "bold" }
          }
        }
      }
    }
  });

  setChartInstanceCallback(newChart);
}

// ----------------------------------------------------
// GRAPH 5: REGIONAL ANALYSIS LEADERBOARD & DETAIL
// ----------------------------------------------------
function renderG5() {
  const activeState = states.G5;
  const filteredExcludeChannels = getFilteredDataForState(activeState, true);

  // Group metrics region-wise
  const regionMetrics = {};
  regions.forEach(r => {
    regionMetrics[r] = {
      channels: {},
      totalViewingMins: 0,
      totalReach: 0
    };
    channels.forEach(c => {
      regionMetrics[r].channels[c] = { amaSum: 0, reachSum: 0, viewingMinsSum: 0 };
    });
  });

  filteredExcludeChannels.forEach(row => {
    const reg = row.Regions;
    const chan = row.Channel;
    
    if (regionMetrics[reg] && regionMetrics[reg].channels[chan]) {
      regionMetrics[reg].channels[chan].amaSum += row["AMA 000's"] || 0;
      regionMetrics[reg].channels[chan].reachSum += row["Cume Rch'000"] || 0;
      regionMetrics[reg].channels[chan].viewingMinsSum += row["Viewing Minutes'000"] || 0;
      
      regionMetrics[reg].totalViewingMins += row["Viewing Minutes'000"] || 0;
      regionMetrics[reg].totalReach += row["Cume Rch'000"] || 0;
    }
  });

  const regionalTableBody = document.getElementById("regionalTableBody");
  regionalTableBody.innerHTML = "";

  const regionRowsData = [];
  regions.forEach(reg => {
    const rm = regionMetrics[reg];
    let leadingChan = "-";
    let leadingAMAMax = -1;
    
    Object.keys(rm.channels).forEach(chan => {
      const avgAMA = rm.channels[chan].amaSum / activeState.weeks.length;
      if (avgAMA > leadingAMAMax) {
        leadingAMAMax = avgAMA;
        leadingChan = chan;
      }
    });

    const avgWeeklyReach = rm.totalReach / activeState.weeks.length;
    const avgWeeklyViewingMins = rm.totalViewingMins / activeState.weeks.length;
    const avgWeeklyTSV = rm.totalReach > 0 ? (rm.totalViewingMins / rm.totalReach) : 0;

    regionRowsData.push({
      region: reg,
      leadingChan: leadingChan,
      leadingAMA: leadingAMAMax,
      marketTSV: avgWeeklyTSV,
      marketReach: avgWeeklyReach,
      marketMins: avgWeeklyViewingMins
    });
  });

  // Render leaderboard table rows
  regionRowsData.forEach(item => {
    const tr = document.createElement("tr");
    if (item.region === activeRegionRow) {
      tr.className = "active";
    }

    tr.innerHTML = `
      <td><strong>${item.region}</strong></td>
      <td><span class="badge-channel">${item.leadingChan}</span></td>
      <td>${item.leadingAMA >= 0 ? item.leadingAMA.toFixed(1) + "k" : "-"}</td>
      <td>${item.marketTSV.toFixed(1)} Min</td>
      <td>${item.marketReach.toLocaleString(undefined, { maximumFractionDigits: 0 })}k</td>
      <td>${(item.marketMins).toLocaleString(undefined, { maximumFractionDigits: 0 })}k</td>
    `;

    tr.addEventListener("click", () => {
      document.querySelectorAll("table.regional-table tbody tr").forEach(row => {
        row.classList.remove("active");
      });
      tr.classList.add("active");
      activeRegionRow = item.region;
      renderRegionalDetailChart(regionMetrics[activeRegionRow], activeState);
    });

    regionalTableBody.appendChild(tr);
  });

  // Draw chart for current active region
  if (regionMetrics[activeRegionRow]) {
    renderRegionalDetailChart(regionMetrics[activeRegionRow], activeState);
  }
}

// Render Graph 5 Bar Chart for channels in the selected region
function renderRegionalDetailChart(regionMetric, activeState) {
  const ctx = document.getElementById("chartRegionalBar").getContext("2d");
  if (chartRegionalBarInstance) {
    chartRegionalBarInstance.destroy();
  }

  const activeChannels = activeState.channels;
  const numWeeks = activeState.weeks.length;

  const channelDetails = activeChannels.map((chan, idx) => {
    const cData = regionMetric.channels[chan];
    const avgAMA = cData ? (cData.amaSum / numWeeks) : 0;
    const avgReach = cData ? (cData.reachSum / numWeeks) : 0;
    
    return {
      channel: chan,
      ama: avgAMA,
      reach: avgReach,
      color: getChannelColor(chan, idx)
    };
  });

  // Sort channels in regional bar chart by AMA size to make it a leaderboard
  channelDetails.sort((a, b) => b.ama - a.ama);

  const labels = channelDetails.map(c => c.channel);
  const amaData = channelDetails.map(c => c.ama);
  const reachData = channelDetails.map(c => c.reach);

  chartRegionalBarInstance = new Chart(ctx, {
    type: "bar",
    data: {
      labels: labels,
      datasets: [
        {
          label: "Avg Weekly AMA (000's)",
          data: amaData,
          backgroundColor: "#38bdf8",
          borderColor: "#0ea5e9",
          borderWidth: 1,
          borderRadius: 4
        },
        {
          label: "Avg Weekly Reach (000's) x 0.1",
          data: reachData.map(r => r * 0.1), // scale down to align on same axis scale nicely
          backgroundColor: "#a855f7",
          borderColor: "#8b5cf6",
          borderWidth: 1,
          borderRadius: 4
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          position: "top",
          labels: { color: "#94a3b8", font: { family: "Outfit", size: 11 } }
        },
        tooltip: {
          backgroundColor: "#111827",
          titleFont: { family: "Outfit", size: 12, weight: "bold" },
          bodyFont: { family: "Outfit", size: 11 },
          borderColor: "rgba(255,255,255,0.08)",
          borderWidth: 1,
          callbacks: {
            label: function(context) {
              const datasetLabel = context.dataset.label || "";
              const val = context.raw;
              if (context.datasetIndex === 0) {
                return `${datasetLabel}: ${val.toFixed(1)}k`;
              } else {
                return `Avg Weekly Reach (000's): ${(val * 10).toFixed(0)}k`;
              }
            }
          }
        }
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: { color: "#94a3b8", font: { family: "Outfit", size: 11 } }
        },
        y: {
          grid: { color: "rgba(255,255,255,0.02)" },
          ticks: { color: "#94a3b8", font: { family: "Outfit" } },
          title: {
            display: true,
            text: "Metric Value Scale",
            color: "#94a3b8",
            font: { family: "Outfit", size: 11, weight: "bold" }
          }
        }
      }
    }
  });
}
