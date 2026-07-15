const state = {
  response: null,
  filters: {
    market: "",
    mso_type: "",
    city: "",
    search: "",
  },
  sortKey: "channel_name",
  sortDirection: "asc",
  page: 1,
  pageSize: 30,
  loading: false,
};

const tableColumns = [
  { key: "transmission", label: "TRANSMISSION" },
  { key: "market", label: "MARKET" },
  { key: "mso_type", label: "MSO TYPE" },
  { key: "city", label: "CITY" },
  { key: "head_end", label: "HEAD-END" },
  { key: "channel_name", label: "CHANNEL NAME" },
  { key: "band", label: "BAND" },
  { key: "tv_ch_no", label: "TV CH. No." },
  { key: "crn_no", label: "CRN No." },
  { key: "name", label: "NAME" },
];

const marketFilter = document.getElementById("marketFilter");
const msoFilter = document.getElementById("msoFilter");
const cityFilter = document.getElementById("cityFilter");
const searchInput = document.getElementById("searchInput");
const resultCount = document.getElementById("resultCount");
const pageInfo = document.getElementById("pageInfo");
const fullscreenButton = document.getElementById("fullscreenButton");

function formatNumber(value) {
  return new Intl.NumberFormat().format(value);
}

function createOption(value, label) {
  const option = document.createElement("option");
  option.value = value;
  option.textContent = label;
  return option;
}

function populateSelect(select, values, allLabel, selectedValue) {
  select.innerHTML = "";
  select.appendChild(createOption("", allLabel));
  values.forEach((value) => select.appendChild(createOption(value, value)));
  select.value = selectedValue || "";
}

function buildTableHead(weeks) {
  const tableHead = document.getElementById("tableHead");
  const tr = document.createElement("tr");
  const columns = [
    ...tableColumns,
    ...weeks.map((week) => ({ key: week, label: week })),
    { key: "change_status", label: "CHANGE" },
  ];

  columns.forEach((column) => {
    const th = document.createElement("th");
    const isActive = state.sortKey === column.key;
    const suffix = isActive ? (state.sortDirection === "asc" ? " ▲" : " ▼") : "";
    th.textContent = `${column.label}${suffix}`;
    th.className = "sortable";
    th.addEventListener("click", () => handleSort(column.key));
    tr.appendChild(th);
  });

  tableHead.replaceChildren(tr);
}

function updateKpis(summary) {
  document.getElementById("kpiTotal").textContent = formatNumber(summary.total_channels);
  document.getElementById("kpiIncrease").textContent = formatNumber(summary.increased);
  document.getElementById("kpiDecrease").textContent = formatNumber(summary.decreased);
  document.getElementById("kpiNoChange").textContent = formatNumber(summary.no_change);
}

function renderTable(weeks, table) {
  const tableBody = document.getElementById("tableBody");
  resultCount.textContent = `${formatNumber(table.total_count)} records`;
  pageInfo.textContent = `Page ${table.page} of ${table.total_pages}`;

  if (!table.records.length) {
    const template = document.getElementById("emptyStateTemplate");
    tableBody.replaceChildren(template.content.cloneNode(true));
    return;
  }

  const fragment = document.createDocumentFragment();
  table.records.forEach((record) => {
    const tr = document.createElement("tr");

    tableColumns.forEach((column) => {
      const td = document.createElement("td");
      td.textContent = record[column.key] ?? "";
      tr.appendChild(td);
    });

    weeks.forEach((week, index) => {
      const td = document.createElement("td");
      td.textContent = record.frequencies[week] ?? "-";
      const status = index === 0 ? "missing" : record.changes[week];
      td.classList.add(`status-${status}`);
      tr.appendChild(td);
    });

    const changeTd = document.createElement("td");
    changeTd.textContent = record.change_status;
    changeTd.classList.add(record.change_status === "NO" ? "change-no" : "change-yes");
    tr.appendChild(changeTd);

    fragment.appendChild(tr);
  });

  tableBody.replaceChildren(fragment);
}

function syncFilterControls(payload) {
  populateSelect(marketFilter, payload.filters.markets, "All Markets", state.filters.market);
  populateSelect(msoFilter, payload.filters.mso_types, "All MSO Types", state.filters.mso_type);
  populateSelect(cityFilter, payload.filters.cities, "All Cities", state.filters.city);
  searchInput.value = state.filters.search;
}

function setLoading(loading) {
  state.loading = loading;
  document.body.classList.toggle("loading", loading);
}

async function fetchDashboard() {
  const params = new URLSearchParams({
    market: state.filters.market,
    mso_type: state.filters.mso_type,
    city: state.filters.city,
    search: state.filters.search,
    page: String(state.page),
    page_size: String(state.pageSize),
    sort_key: state.sortKey,
    sort_direction: state.sortDirection,
  });

  setLoading(true);
  try {
    const response = await fetch(`/api/frequency?${params.toString()}`);
    state.response = await response.json();
    syncFilterControls(state.response);
    buildTableHead(state.response.weeks);
    updateKpis(state.response.summary);
    renderTable(state.response.weeks, state.response.table);
  } finally {
    setLoading(false);
  }
}

function handleSort(key) {
  if (state.sortKey === key) {
    state.sortDirection = state.sortDirection === "asc" ? "desc" : "asc";
  } else {
    state.sortKey = key;
    state.sortDirection = "asc";
  }
  state.page = 1;
  fetchDashboard();
}

async function toggleFullscreen() {
  if (!document.fullscreenElement) {
    await document.documentElement.requestFullscreen();
    fullscreenButton.textContent = "EXIT FULL SCREEN \u2715";
  } else {
    await document.exitFullscreen();
    fullscreenButton.textContent = "FULL SCREEN \u26F6";
  }
}

function bindEvents() {
  marketFilter.addEventListener("change", () => {
    state.filters.market = marketFilter.value;
    state.page = 1;
    fetchDashboard();
  });

  msoFilter.addEventListener("change", () => {
    state.filters.mso_type = msoFilter.value;
    state.page = 1;
    fetchDashboard();
  });

  cityFilter.addEventListener("change", () => {
    state.filters.city = cityFilter.value;
    state.page = 1;
    fetchDashboard();
  });

  searchInput.addEventListener("input", () => {
    state.filters.search = searchInput.value.trim();
    state.page = 1;
    window.clearTimeout(searchInput._debounce);
    searchInput._debounce = window.setTimeout(fetchDashboard, 250);
  });

  document.getElementById("resetButton").addEventListener("click", () => {
    state.filters = { market: "", mso_type: "", city: "", search: "" };
    state.sortKey = "channel_name";
    state.sortDirection = "asc";
    state.page = 1;
    fetchDashboard();
  });

  document.getElementById("prevPage").addEventListener("click", () => {
    if (!state.response || state.response.table.page <= 1) return;
    state.page = state.response.table.page - 1;
    fetchDashboard();
  });

  document.getElementById("nextPage").addEventListener("click", () => {
    if (!state.response || state.response.table.page >= state.response.table.total_pages) return;
    state.page = state.response.table.page + 1;
    fetchDashboard();
  });

  document.getElementById("printButton").addEventListener("click", () => window.print());
  document.getElementById("refreshButton").addEventListener("click", () => {
    state.page = 1;
    fetchDashboard();
  });
  document.getElementById("exportButton").addEventListener("click", exportFilteredData);
  fullscreenButton.addEventListener("click", toggleFullscreen);
  document.addEventListener("fullscreenchange", () => {
    fullscreenButton.textContent = document.fullscreenElement ? "EXIT FULL SCREEN \u2715" : "FULL SCREEN \u26F6";
  });
}

async function exportFilteredData() {
  const response = await fetch("/api/export", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      market: state.filters.market,
      mso_type: state.filters.mso_type,
      city: state.filters.city,
      search: state.filters.search,
    }),
  });
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "chrome_report_filtered.xlsx";
  link.click();
  URL.revokeObjectURL(url);
}

bindEvents();
fetchDashboard();
