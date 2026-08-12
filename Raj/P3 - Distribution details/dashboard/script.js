const DATA_PATHS = {
  filters: "./data/filters.json",
  headends: "./data/headends.json",
  comparisonIndex: "./data/comparison/index.json",
};

const state = {
  filters: {
    states: [],
    markets: [],
    locations: [],
    weeks: [],
    lcns: [],
    channels: [],
    summary: null,
  },
  headends: [],
  comparison: [],
  comparisonIndex: [],
  filteredHeadends: [],
  filteredComparison: [],
  tables: {
    headends: null,
    comparison: null,
  },
  selects: {
    lcn: null,
    channel: null,
  },
};

const hasDataTables = typeof DataTable !== "undefined";
const hasTomSelect = typeof TomSelect !== "undefined";

document.addEventListener("DOMContentLoaded", async () => {
  bindEvents();
  showLoading("headends");
  showLoading("comparison");
  try {
    await initializeDashboard();
  } catch (error) {
    showError("headends", `Dashboard initialization failed. ${error.message}`);
    showError("comparison", `Dashboard initialization failed. ${error.message}`);
    hideLoading("headends");
    hideLoading("comparison");
  }
});

function bindEvents() {
  document.getElementById("locationFilter").addEventListener("change", filterHeadends);
  document.getElementById("stateFilter").addEventListener("change", filterHeadends);
  document.getElementById("marketFilter").addEventListener("change", filterHeadends);
  document.getElementById("resetHeadendFilters").addEventListener("click", resetDistributionFilters);

  document.getElementById("applyComparisonFilters").addEventListener("click", async () => {
    showLoading("comparison");
    await loadComparison();
  });
  document.getElementById("resetComparisonFilters").addEventListener("click", resetComparisonFilters);
  document.getElementById("weekFromFilter").addEventListener("change", async () => {
    showLoading("comparison");
    await loadComparison();
  });
  document.getElementById("weekToFilter").addEventListener("change", async () => {
    showLoading("comparison");
    await loadComparison();
  });

  document.getElementById("exportHeadendsCsv").addEventListener("click", () => {
    exportRows(state.filteredHeadends, headendColumns(), "headends.csv");
  });
  document.getElementById("exportHeadendsExcel").addEventListener("click", () => {
    exportRows(state.filteredHeadends, headendColumns(), "headends.xls", "\t");
  });
  document.getElementById("exportComparisonCsv").addEventListener("click", () => {
    exportRows(state.filteredComparison, comparisonColumns(), "comparison.csv");
  });
  document.getElementById("exportComparisonExcel").addEventListener("click", () => {
    exportRows(state.filteredComparison, comparisonColumns(), "comparison.xls", "\t");
  });
}

async function initializeDashboard() {
  await Promise.allSettled([loadFilters(), loadHeadends()]);
  loadDashboardSummary();
}

async function loadJson(path) {
  const response = await fetch(path, { cache: "no-store" });
  if (!response.ok) {
    throw new Error(`Unable to load ${path}. HTTP ${response.status}`);
  }
  return response.json();
}

async function loadFilters() {
  try {
    const payload = await loadJson(DATA_PATHS.filters);
    state.filters = {
      states: ensureArray(payload.states),
      markets: ensureArray(payload.markets),
      locations: ensureArray(payload.locations),
      weeks: ensureArray(payload.weeks),
      lcns: ensureArray(payload.lcns),
      channels: ensureArray(payload.channels),
      comparison_pairs: ensureArray(payload.comparison_pairs),
      summary: payload.summary ?? null,
    };

    loadDashboardSummary();

    populateSelect("locationFilter", state.filters.locations, "All Locations");
    populateSelect("stateFilter", state.filters.states, "All States");
    populateSelect("marketFilter", state.filters.markets, "All Markets");
    populateSelect("weekFromFilter", state.filters.weeks, "All Weeks");
    populateSelect("weekToFilter", state.filters.weeks, "All Weeks");
    populateMultiSelect("lcnFilter", [], "Select LCN values", "lcn");
    populateMultiSelect("channelFilter", [], "Select channel names", "channel");
    await loadComparisonIndex();
  } catch (error) {
    showError("headends", `Filter data could not be loaded. ${error.message}`);
    showError("comparison", `Filter data could not be loaded. ${error.message}`);
  }
}

function loadDashboardSummary() {
  const summary = state.filters.summary || {};
  const headendCount = summary.total_headends ?? state.headends.length;
  const channelCount = summary.total_channel_rows ?? state.comparison.length;
  const lastUpdated = summary.last_updated || (state.filters.weeks.length ? state.filters.weeks[state.filters.weeks.length - 1] : "Not available");

  document.getElementById("summaryHeadends").textContent = formatNumber(headendCount);
  document.getElementById("summaryChannels").textContent = formatNumber(channelCount);
  document.getElementById("summaryLastUpdated").textContent = lastUpdated || "Not available";
}

async function loadHeadends() {
  try {
    clearError("headends");
    const rows = await loadJson(DATA_PATHS.headends);
    state.headends = ensureArray(rows).map(normalizeHeadendRecord);
    state.filteredHeadends = [...state.headends];
    loadDashboardSummary();
    renderHeadendTable(state.filteredHeadends);
  } catch (error) {
    state.headends = [];
    state.filteredHeadends = [];
    showError("headends", `Headend data could not be loaded. ${error.message}`);
    renderHeadendTable([]);
  } finally {
    hideLoading("headends");
  }
}

function renderHeadendTable(rows) {
  if (state.tables.headends) {
    state.tables.headends.destroy();
    state.tables.headends = null;
  }

  const tableElement = document.getElementById("headendsTable");
  const tbody = tableElement.querySelector("tbody");
  tbody.innerHTML = "";

  if (!hasDataTables) {
    rows.forEach((row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${escapeHtml(row.headend_id)}</td>
        <td>${escapeHtml(row.network_name)}</td>
        <td>${escapeHtml(row.headend_location)}</td>
        <td>${escapeHtml(row.state)}</td>
        <td>${escapeHtml(row.barc_market)}</td>
        <td>${escapeHtml(formatNumber(row.stbs))}</td>
        <td>${escapeHtml(row.landing_channel)}</td>
        <td>${escapeHtml(row.second_landing_channel)}</td>
        <td>${escapeHtml(row.barker_channel)}</td>
        <td>${escapeHtml(row.second_barker_channel)}</td>
      `;
      tbody.appendChild(tr);
    });
    document.getElementById("headendRecordCount").textContent = formatNumber(rows.length);
    toggleHidden("headendsEmpty", rows.length !== 0);
    return;
  }

  state.tables.headends = new DataTable(tableElement, {
    data: rows,
    responsive: true,
    autoWidth: false,
    scrollX: true,
    pageLength: 10,
    lengthMenu: [10, 25, 50, 100],
    deferRender: true,
    columns: [
      { data: "headend_id", title: "Headend ID" },
      { data: "network_name", title: "Network Name" },
      { data: "headend_location", title: "Headend Location" },
      { data: "state", title: "State" },
      { data: "barc_market", title: "BARC Market" },
      { data: "stbs", title: "STBs", render: (value) => escapeHtml(formatNumber(value)) },
      { data: "landing_channel", title: "Landing Channel", defaultContent: "" },
      { data: "second_landing_channel", title: "Second Landing Channel", defaultContent: "" },
      { data: "barker_channel", title: "Barker Channel", defaultContent: "" },
      { data: "second_barker_channel", title: "2nd Barker Channel", defaultContent: "" },
    ],
    language: {
      emptyTable: "No headend records available.",
      zeroRecords: "No headend records match the current search.",
      search: "",
      searchPlaceholder: "Search channel distribution...",
    },
    order: [[1, "asc"]],
  });

  document.getElementById("headendRecordCount").textContent = formatNumber(rows.length);
  toggleHidden("headendsEmpty", rows.length !== 0);
}

function filterHeadends() {
  const location = document.getElementById("locationFilter").value;
  const stateValue = document.getElementById("stateFilter").value;
  const market = document.getElementById("marketFilter").value;

  state.filteredHeadends = state.headends.filter((row) => {
    const matchesLocation = !location || row.headend_location === location;
    const matchesState = !stateValue || row.state === stateValue;
    const matchesMarket = !market || row.barc_market === market;
    return matchesLocation && matchesState && matchesMarket;
  });

  renderHeadendTable(state.filteredHeadends);
}

async function loadComparison() {
  try {
    clearError("comparison");
    const selectedPair = resolveSelectedComparisonPair();
    if (!selectedPair) {
      state.comparison = [];
      state.filteredComparison = [];
      refreshComparisonFilterOptions([]);
      showError("comparison", "Select a valid Week From and Week To combination to load comparison data.");
      renderComparisonTable([]);
      hideLoading("comparison");
      return;
    }

    clearError("comparison");
    const rows = await loadJson(selectedPair.file);
    state.comparison = ensureArray(rows).map(normalizeComparisonRecord);
    state.filteredComparison = [...state.comparison];
    refreshComparisonFilterOptions(state.comparison);
    loadDashboardSummary();
    renderComparisonTable(state.filteredComparison);
  } catch (error) {
    state.comparison = [];
    state.filteredComparison = [];
    refreshComparisonFilterOptions([]);
    showError("comparison", `Comparison data could not be loaded. ${error.message}`);
    renderComparisonTable([]);
  } finally {
    hideLoading("comparison");
  }
}

async function loadComparisonIndex() {
  try {
    const payload = await loadJson(DATA_PATHS.comparisonIndex);
    state.comparisonIndex = ensureArray(payload);

    const latestPair = state.comparisonIndex[state.comparisonIndex.length - 1];
    if (latestPair) {
      document.getElementById("weekFromFilter").value = latestPair.week_from || "";
      document.getElementById("weekToFilter").value = latestPair.week_to || "";
      showLoading("comparison");
      await loadComparison();
    } else {
      renderComparisonTable([]);
      hideLoading("comparison");
    }
  } catch (error) {
    state.comparisonIndex = [];
    showError("comparison", `Comparison index could not be loaded. ${error.message}`);
    renderComparisonTable([]);
    hideLoading("comparison");
  }
}

function renderComparisonTable(rows) {
  if (state.tables.comparison) {
    state.tables.comparison.destroy();
    state.tables.comparison = null;
  }

  const tableElement = document.getElementById("comparisonTable");
  const tbody = tableElement.querySelector("tbody");
  tbody.innerHTML = "";

  if (!hasDataTables) {
    rows.forEach((row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${escapeHtml(row.headend_id)}</td>
        <td>${escapeHtml(String(row.lcn))}</td>
        <td>${escapeHtml(row.week_from)}</td>
        <td>${escapeHtml(row.week_to)}</td>
        <td>${escapeHtml(row.week_from_channel)}</td>
        <td>${escapeHtml(row.week_to_channel)}</td>
        <td>${renderStatusBadge(asText(row.status))}</td>
      `;
      tbody.appendChild(tr);
    });
    document.getElementById("comparisonRecordCount").textContent = formatNumber(rows.length);
    toggleHidden("comparisonEmpty", rows.length !== 0);
    return;
  }

  state.tables.comparison = new DataTable(tableElement, {
    data: rows,
    responsive: true,
    autoWidth: false,
    scrollX: true,
    pageLength: 10,
    lengthMenu: [10, 25, 50, 100],
    deferRender: true,
    columns: [
      { data: "headend_id", title: "Headend ID" },
      { data: "lcn", title: "LCN Number" },
      { data: "week_from", title: "Week From" },
      { data: "week_to", title: "Week To" },
      { data: "week_from_channel", title: "Channel (Week From)", defaultContent: "" },
      { data: "week_to_channel", title: "Channel (Week To)", defaultContent: "" },
      { data: "status", title: "Status", render: (value) => renderStatusBadge(asText(value)) },
    ],
    language: {
      emptyTable: "No comparison records available.",
      zeroRecords: "No comparison records match the current search.",
      search: "",
      searchPlaceholder: "Search week-wise comparison...",
    },
    order: [[2, "desc"], [0, "asc"]],
    columnDefs: [{ orderable: false, targets: 6 }],
  });

  document.getElementById("comparisonRecordCount").textContent = formatNumber(rows.length);
  toggleHidden("comparisonEmpty", rows.length !== 0);
}

function filterComparison() {
  const selectedPair = resolveSelectedComparisonPair();
  if (!selectedPair) {
    state.filteredComparison = [];
    renderComparisonTable([]);
    return;
  }

  const weekFrom = document.getElementById("weekFromFilter").value;
  const weekTo = document.getElementById("weekToFilter").value;
  const lcns = getMultiValues("lcn");
  const channels = getMultiValues("channel");

  state.filteredComparison = state.comparison.filter((row) => {
    const matchesWeekFrom = !weekFrom || row.week_from === weekFrom;
    const matchesWeekTo = !weekTo || row.week_to === weekTo;
    const matchesLcn = lcns.length === 0 || lcns.includes(String(row.lcn));
    const matchesChannel =
      channels.length === 0 ||
      channels.includes(row.week_from_channel) ||
      channels.includes(row.week_to_channel);
    return matchesWeekFrom && matchesWeekTo && matchesLcn && matchesChannel;
  });

  renderComparisonTable(state.filteredComparison);
}

function resetDistributionFilters() {
  document.getElementById("locationFilter").value = "";
  document.getElementById("stateFilter").value = "";
  document.getElementById("marketFilter").value = "";
  state.filteredHeadends = [...state.headends];
  renderHeadendTable(state.filteredHeadends);
}

function resetComparisonFilters() {
  const latestPair = state.comparisonIndex[state.comparisonIndex.length - 1];
  document.getElementById("weekFromFilter").value = latestPair?.week_from || "";
  document.getElementById("weekToFilter").value = latestPair?.week_to || "";
  if (state.selects.lcn) {
    state.selects.lcn.clear(true);
  }
  if (state.selects.channel) {
    state.selects.channel.clear(true);
  }
  showLoading("comparison");
  loadComparison();
}

function showLoading(section) {
  toggleHidden(`${section}Loading`, false);
}

function hideLoading(section) {
  toggleHidden(`${section}Loading`, true);
}

function populateSelect(selectId, values, placeholder) {
  const select = document.getElementById(selectId);
  select.innerHTML = `<option value="">${placeholder}</option>`;
  values.forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    select.appendChild(option);
  });
}

function populateMultiSelect(selectId, values, placeholder, type) {
  const select = document.getElementById(selectId);
  select.innerHTML = "";

  values.forEach((value) => {
    const option = document.createElement("option");
    option.value = String(value);
    option.textContent = String(value);
    select.appendChild(option);
  });

  if (select.tomselect) {
    select.tomselect.destroy();
  }

  const useNativeMultiSelect = !hasTomSelect || values.length > 1500;

  if (useNativeMultiSelect) {
    state.selects[type] = null;
    select.setAttribute("size", "6");
    select.setAttribute("title", placeholder);
    select.setAttribute("multiple", "multiple");
    select.addEventListener("change", () => {
      if (type === "channel" || type === "lcn") {
        filterComparison();
      }
    });
    return;
  }

  state.selects[type] = new TomSelect(select, {
    plugins: ["remove_button"],
    create: false,
    persist: false,
    hideSelected: true,
    maxOptions: 3000,
    placeholder,
    closeAfterSelect: false,
    onChange: () => {
      if (type === "channel" || type === "lcn") {
        filterComparison();
      }
    },
  });
}

function refreshComparisonFilterOptions(rows) {
  const lcnValues = Array.from(
    new Set(rows.map((row) => String(row.lcn || "").trim()).filter(Boolean))
  ).sort((left, right) => lcnSort(left, right));

  const channelValues = Array.from(
    new Set(
      rows.flatMap((row) => [row.week_from_channel, row.week_to_channel]).map((value) => asText(value)).filter(Boolean)
    )
  ).sort((left, right) => left.localeCompare(right, undefined, { sensitivity: "base" }));

  populateMultiSelect("lcnFilter", lcnValues, "Select LCN values", "lcn");
  populateMultiSelect("channelFilter", channelValues, "Select channel names", "channel");
}

function resolveSelectedComparisonPair() {
  const weekFrom = document.getElementById("weekFromFilter").value;
  const weekTo = document.getElementById("weekToFilter").value;

  if (!weekFrom || !weekTo) {
    return null;
  }

  return (
    state.comparisonIndex.find((item) => item.week_from === weekFrom && item.week_to === weekTo) || null
  );
}

function getMultiValues(type) {
  const select = state.selects[type];
  if (!select) {
    const nativeSelect = document.getElementById(type === "lcn" ? "lcnFilter" : "channelFilter");
    return Array.from(nativeSelect.selectedOptions).map((option) => option.value);
  }
  const value = select.getValue();
  return Array.isArray(value) ? value : value ? [value] : [];
}

function lcnSort(left, right) {
  const leftText = String(left).trim();
  const rightText = String(right).trim();
  const leftNum = /^\d+$/.test(leftText) ? Number(leftText) : null;
  const rightNum = /^\d+$/.test(rightText) ? Number(rightText) : null;

  if (leftNum !== null && rightNum !== null) {
    return leftNum - rightNum;
  }
  return leftText.localeCompare(rightText, undefined, { sensitivity: "base", numeric: true });
}

function showError(section, message) {
  const target = document.getElementById(`${section}Error`);
  target.textContent = message;
  toggleHidden(`${section}Error`, false);
}

function clearError(section) {
  const target = document.getElementById(`${section}Error`);
  target.textContent = "";
  toggleHidden(`${section}Error`, true);
}

function toggleHidden(id, shouldHide) {
  document.getElementById(id).classList.toggle("hidden", shouldHide);
}

function normalizeHeadendRecord(row) {
  return {
    headend_id: asText(row.headend_id),
    network_name: asText(row.network_name),
    headend_location: asText(row.headend_location),
    state: asText(row.state),
    barc_market: asText(row.barc_market),
    stbs: row.stbs ?? "",
    landing_channel: asText(row.landing_channel),
    second_landing_channel: asText(row.second_landing_channel),
    barker_channel: asText(row.barker_channel),
    second_barker_channel: asText(row.second_barker_channel),
  };
}

function normalizeComparisonRecord(row) {
  return {
    headend_id: asText(row.headend_id),
    lcn: row.lcn ?? "",
    week_from: asText(row.week_from),
    week_to: asText(row.week_to),
    week_from_channel: asText(row.week_from_channel),
    week_to_channel: asText(row.week_to_channel),
    status: asText(row.status),
  };
}

function renderStatusBadge(status) {
  const safeStatus = status || "Unknown";
  const badgeClass = {
    Same: "badge-same",
    Changed: "badge-changed",
    Added: "badge-added",
    Removed: "badge-removed",
  }[safeStatus] || "badge-removed";
  return `<span class="status-badge ${badgeClass}">${escapeHtml(safeStatus)}</span>`;
}

function exportRows(rows, columns, filename, delimiter = ",") {
  if (!rows.length) {
    return;
  }
  const header = columns.map((column) => column.title).join(delimiter);
  const body = rows
    .map((row) => columns.map((column) => sanitizeExportValue(row[column.key], delimiter)).join(delimiter))
    .join("\n");
  const blob = new Blob([`${header}\n${body}`], { type: "text/plain;charset=utf-8;" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(link.href);
}

function sanitizeExportValue(value, delimiter) {
  const text = String(value ?? "");
  if (delimiter === "\t") {
    return text.replace(/\t/g, " ");
  }
  const escaped = text.replace(/"/g, "\"\"");
  return /[",\n]/.test(escaped) ? `"${escaped}"` : escaped;
}

function headendColumns() {
  return [
    { title: "Headend ID", key: "headend_id" },
    { title: "Network Name", key: "network_name" },
    { title: "Headend Location", key: "headend_location" },
    { title: "State", key: "state" },
    { title: "BARC Market", key: "barc_market" },
    { title: "STBs", key: "stbs" },
    { title: "Landing Channel", key: "landing_channel" },
    { title: "Second Landing Channel", key: "second_landing_channel" },
    { title: "Barker Channel", key: "barker_channel" },
    { title: "2nd Barker Channel", key: "second_barker_channel" },
  ];
}

function comparisonColumns() {
  return [
    { title: "Headend ID", key: "headend_id" },
    { title: "LCN Number", key: "lcn" },
    { title: "Week From", key: "week_from" },
    { title: "Week To", key: "week_to" },
    { title: "Channel (Week From)", key: "week_from_channel" },
    { title: "Channel (Week To)", key: "week_to_channel" },
    { title: "Status", key: "status" },
  ];
}

function ensureArray(value) {
  return Array.isArray(value) ? value : [];
}

function asText(value) {
  return value == null ? "" : String(value).trim();
}

function formatNumber(value) {
  if (value === "" || value == null || Number.isNaN(Number(value))) {
    return value === "" ? "" : String(value ?? "");
  }
  return new Intl.NumberFormat("en-IN").format(Number(value));
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}
