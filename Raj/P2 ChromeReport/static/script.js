const state = {
  response: null,
  view: "frequency",
  filters: {
    market: "",
    city: "",
    mso_type: "",
    head_end: "",
    crn_no: "",
    channel_name: "",
    band: "",
    week: "",
    change: "",
  },
  sortKey: "flow_order",
  sortDirection: "asc",
  page: 1,
  pageSize: 30,
  loading: false,
};

const tableColumns = [
  { key: "market", label: "MARKET" },
  { key: "city", label: "CITY" },
  { key: "mso_type", label: "MSO TYPE" },
  { key: "head_end", label: "HEAD-END" },
  { key: "crn_no", label: "CRN No." },
  { key: "channel_name", label: "CHANNEL NAME" },
];

const marketFilter = document.getElementById("marketFilter");
const cityFilter = document.getElementById("cityFilter");
const msoTypeFilter = document.getElementById("msoTypeFilter");
const headendFilter = document.getElementById("headendFilter");
const crnFilter = document.getElementById("crnFilter");
const channelFilter = document.getElementById("channelFilter");
const bandFilter = document.getElementById("bandFilter");
const weekFilter = document.getElementById("weekFilter");
const changeFilter = document.getElementById("changeFilter");
const resultCount = document.getElementById("resultCount");
const pageInfo = document.getElementById("pageInfo");
const fullscreenButton = document.getElementById("fullscreenButton");
const exitFullscreenButton = document.getElementById("exitFullscreenButton");
const statusMessage = document.getElementById("statusMessage");
const generatedAt = document.getElementById("generatedAt");
const totalRecords = document.getElementById("totalRecords");
const tableTitle = document.getElementById("tableTitle");
const focusSummary = document.getElementById("focusSummary");
const tableFullscreenScope = document.querySelector(".table1-scope");
const filterPanel = document.querySelector(".filter-panel");
const tablePanel = document.querySelector(".table-panel");
const tableWrap = document.querySelector(".table-wrap");
const viewButtons = {
  frequency: document.getElementById("frequencyViewButton"),
  rank: document.getElementById("rankViewButton"),
  band: document.getElementById("bandViewButton"),
};
const fullscreenState = {
  active: false,
  usingNativeFullscreen: false,
  windowScrollY: 0,
  tableScrollTop: 0,
  tableScrollLeft: 0,
};
const filterOrder = [
  "market",
  "city",
  "mso_type",
  "head_end",
  "crn_no",
  "channel_name",
  "band",
  "week",
  "change",
];

function formatNumber(value) {
  return new Intl.NumberFormat().format(value);
}

function formatTimestamp(value) {
  if (!value) return "--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "--";
  return date.toLocaleString("en-IN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

function createOption(value, label) {
  const option = document.createElement("option");
  option.value = value;
  option.textContent = label;
  return option;
}

function populateSelect(select, values, allLabel, selectedValue) {
  const normalizedValues = Array.isArray(values) ? values.filter((value) => value !== null && value !== undefined && String(value).trim() !== "") : [];
  const safeSelectedValue = normalizedValues.includes(selectedValue) ? selectedValue : "";
  select.innerHTML = "";
  select.appendChild(createOption("", allLabel));
  normalizedValues.forEach((value) => select.appendChild(createOption(value, value)));
  select.value = safeSelectedValue;
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
  if (state.view === "rank") {
    document.querySelector(".compact-kpi:nth-child(2) span").textContent = "Rank Improved";
    document.querySelector(".compact-kpi:nth-child(3) span").textContent = "Rank Declined";
    document.getElementById("kpiIncrease").textContent = formatNumber(summary.improved ?? 0);
    document.getElementById("kpiDecrease").textContent = formatNumber(summary.declined ?? 0);
    return;
  }
  if (state.view === "band") {
    document.querySelector(".compact-kpi:nth-child(2) span").textContent = "Band Changed";
    document.querySelector(".compact-kpi:nth-child(3) span").textContent = "Band Stable";
    document.getElementById("kpiIncrease").textContent = formatNumber(summary.changed ?? 0);
    document.getElementById("kpiDecrease").textContent = formatNumber(summary.stable ?? 0);
    return;
  }
  document.querySelector(".compact-kpi:nth-child(2) span").textContent = "Frequency Increased";
  document.querySelector(".compact-kpi:nth-child(3) span").textContent = "Frequency Decreased";
  document.getElementById("kpiIncrease").textContent = formatNumber(summary.increased ?? 0);
  document.getElementById("kpiDecrease").textContent = formatNumber(summary.decreased ?? 0);
}

function updateHeaderMeta(payload) {
  generatedAt.textContent = formatTimestamp(payload.generated_at);
  totalRecords.textContent = formatNumber(payload.table.total_count);
}

function renderFocusSummary(items) {
  if (!focusSummary) {
    return;
  }

  if (!items?.length) {
    focusSummary.innerHTML = '<div class="focus-line">No channel summary available for the current filters.</div>';
    return;
  }

  const html = items
    .map((item) => {
      const latestBits = [];
      if (item.latest_positive) {
        latestBits.push(`${formatNumber(item.latest_positive)} ${item.positive_label} in ${item.latest_week}`);
      }
      if (item.latest_negative) {
        latestBits.push(`${formatNumber(item.latest_negative)} ${item.negative_label} in ${item.latest_week}`);
      }
      const latestText = latestBits.length ? ` Latest: ${latestBits.join(", ")}.` : "";
      return `
        <div class="focus-line">
          <strong>${item.label}</strong>
          <span>${formatNumber(item.records)} rows, ${formatNumber(item.positive)} ${item.positive_label}, ${formatNumber(item.negative)} ${item.negative_label}, ${formatNumber(item.no_change)} stable.${latestText}</span>
        </div>
      `;
    })
    .join("");

  focusSummary.innerHTML = html;
}

function renderTable(weeks, table) {
  const tableBody = document.getElementById("tableBody");
  resultCount.textContent = `${formatNumber(table.total_count)} records`;
  pageInfo.textContent = `Page ${table.page} of ${table.total_pages}`;
  const viewConfig = getViewConfig();

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
      const value = record[viewConfig.series][week];
      const rawStatus = index === 0 ? "baseline" : record[viewConfig.changes][week];
      const status = value === null || value === undefined || value === "" ? "missing" : rawStatus;
      td.classList.add(`status-${status}`);
      td.textContent = formatWeekValue(value, status, index === 0);
      tr.appendChild(td);
    });

    const changeTd = document.createElement("td");
    changeTd.textContent = record[viewConfig.status];
    changeTd.classList.add(record[viewConfig.status] === "NO" ? "change-no" : "change-yes");
    tr.appendChild(changeTd);

    fragment.appendChild(tr);
  });

  tableBody.replaceChildren(fragment);
}

function getPageSize() {
  if (!fullscreenState.active) {
    return 30;
  }
  const viewportHeight = window.innerHeight || 900;
  return Math.max(45, Math.floor((viewportHeight - 230) / 26));
}

function formatWeekValue(value, status, isBaseline) {
  if (value === null || value === undefined || value === "") return "NA";
  if (isBaseline || status === "baseline" || status === "missing" || status === "no_change") {
    return String(value);
  }
  if (state.view === "rank") {
    if (status === "improve") return `▲ ${value}`;
    if (status === "decline") return `▼ ${value}`;
    return String(value);
  }
  if (state.view === "band") {
    if (status === "change") return `• ${value}`;
    return String(value);
  }
  if (status === "increase") return `▲ ${value}`;
  if (status === "decrease") return `▼ ${value}`;
  return String(value);
}

function updateViewMeta() {
  const titles = {
    frequency: {
      title: "Weekly Frequency Analysis",
    },
    rank: {
      title: "Weekly Rank Analysis",
    },
    band: {
      title: "Weekly Band Analysis",
    },
  };
  tableTitle.textContent = titles[state.view].title;
  Object.entries(viewButtons).forEach(([view, button]) => {
    button.classList.toggle("active", view === state.view);
  });
}

function renderStatusMessage(payload) {
  if (payload.message) {
    statusMessage.hidden = false;
    statusMessage.textContent = `${payload.message} Folder: ${payload.data_directory}`;
    return;
  }
  statusMessage.hidden = true;
  statusMessage.textContent = "";
}

function syncFilterControls(payload) {
  populateSelect(marketFilter, payload.filters.markets, "All Markets", state.filters.market);
  populateSelect(cityFilter, payload.filters.cities, "All Cities", state.filters.city);
  populateSelect(msoTypeFilter, payload.filters.mso_types, "All MSO Types", state.filters.mso_type);
  populateSelect(headendFilter, payload.filters.head_ends, "All Headend", state.filters.head_end);
  populateSelect(crnFilter, payload.filters.crn_numbers, "All CRN No", state.filters.crn_no);
  populateSelect(channelFilter, payload.filters.channels, "All Channels", state.filters.channel_name);
  populateSelect(bandFilter, payload.filters.bands, "All Bands", state.filters.band);
  populateSelect(weekFilter, payload.filters.weeks, "All Weeks", state.filters.week);
  populateSelect(changeFilter, payload.filters.change_options, "All Changes", state.filters.change);

  state.filters.market = marketFilter.value;
  state.filters.city = cityFilter.value;
  state.filters.mso_type = msoTypeFilter.value;
  state.filters.head_end = headendFilter.value;
  state.filters.crn_no = crnFilter.value;
  state.filters.channel_name = channelFilter.value;
  state.filters.band = bandFilter.value;
  state.filters.week = weekFilter.value;
  state.filters.change = changeFilter.value;
}

function setLoading(loading) {
  state.loading = loading;
  document.body.classList.toggle("loading", loading);
}

async function fetchDashboard() {
  const params = new URLSearchParams({
    view: state.view,
    market: state.filters.market,
    city: state.filters.city,
    mso_type: state.filters.mso_type,
    head_end: state.filters.head_end,
    crn_no: state.filters.crn_no,
    channel_name: state.filters.channel_name,
    band: state.filters.band,
    week: state.filters.week,
    change: state.filters.change,
    page: String(state.page),
    page_size: String(state.pageSize),
    sort_key: state.sortKey,
    sort_direction: state.sortDirection,
  });

  setLoading(true);
  try {
    const response = await fetch(`/api/frequency?${params.toString()}`);
    state.response = await response.json();
    updateViewMeta();
    syncFilterControls(state.response);
    buildTableHead(state.response.weeks);
    updateKpis(state.response.summary);
    updateHeaderMeta(state.response);
    renderFocusSummary(state.response.focus_channels);
    renderStatusMessage(state.response);
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

function syncFullscreenButtons() {
  const label = fullscreenState.active ? "Exit Full Screen" : "Full Screen";
  fullscreenButton.textContent = label;
  if (exitFullscreenButton) {
    exitFullscreenButton.hidden = !fullscreenState.active;
  }
}

function setFullscreen(active) {
  if (!tableFullscreenScope || !tableWrap || fullscreenState.active === active) return;

  if (active) {
    fullscreenState.windowScrollY = window.scrollY || window.pageYOffset || 0;
    fullscreenState.tableScrollTop = tableWrap.scrollTop;
    fullscreenState.tableScrollLeft = tableWrap.scrollLeft;
    fullscreenState.active = true;
    document.body.classList.add("table-fullscreen-active");
    tableFullscreenScope.classList.add("table1-scope-fullscreen");
    filterPanel?.classList.add("table1-scope-child");
    tablePanel?.classList.add("table1-scope-child");
    state.pageSize = getPageSize();
    if (state.response) {
      state.page = 1;
      fetchDashboard();
    }
    requestAnimationFrame(() => {
      tableWrap.scrollTop = fullscreenState.tableScrollTop;
      tableWrap.scrollLeft = fullscreenState.tableScrollLeft;
    });
  } else {
    fullscreenState.tableScrollTop = tableWrap.scrollTop;
    fullscreenState.tableScrollLeft = tableWrap.scrollLeft;
    fullscreenState.active = false;
    document.body.classList.remove("table-fullscreen-active");
    tableFullscreenScope.classList.remove("table1-scope-fullscreen");
    filterPanel?.classList.remove("table1-scope-child");
    tablePanel?.classList.remove("table1-scope-child");
    state.pageSize = getPageSize();
    if (state.response) {
      state.page = 1;
      fetchDashboard();
    }
    requestAnimationFrame(() => {
      window.scrollTo({ top: fullscreenState.windowScrollY, behavior: "auto" });
      tableWrap.scrollTop = fullscreenState.tableScrollTop;
      tableWrap.scrollLeft = fullscreenState.tableScrollLeft;
    });
  }
  syncFullscreenButtons();
}

async function enterNativeFullscreen() {
  if (!tableFullscreenScope?.requestFullscreen) {
    return false;
  }
  try {
    fullscreenState.usingNativeFullscreen = true;
    await tableFullscreenScope.requestFullscreen();
    return true;
  } catch (error) {
    fullscreenState.usingNativeFullscreen = false;
    return false;
  }
}

async function exitNativeFullscreen() {
  if (!document.fullscreenElement) {
    return false;
  }
  try {
    await document.exitFullscreen();
    return true;
  } catch (error) {
    return false;
  }
}

async function toggleFullscreen() {
  if (fullscreenState.active) {
    if (fullscreenState.usingNativeFullscreen && document.fullscreenElement === tableFullscreenScope) {
      const exited = await exitNativeFullscreen();
      if (!exited) {
        fullscreenState.usingNativeFullscreen = false;
        setFullscreen(false);
      }
      return;
    }
    setFullscreen(false);
    return;
  }

  const entered = await enterNativeFullscreen();
  if (!entered) {
    fullscreenState.usingNativeFullscreen = false;
    setFullscreen(true);
  }
}

function autoApplySelect(select, key) {
  select.addEventListener("change", () => {
    state.filters[key] = select.value;
    const changedIndex = filterOrder.indexOf(key);
    if (changedIndex >= 0) {
      filterOrder.slice(changedIndex + 1).forEach((nextKey) => {
        state.filters[nextKey] = "";
      });
    }
    state.page = 1;
    fetchDashboard();
  });
}

function bindEvents() {
  autoApplySelect(marketFilter, "market");
  autoApplySelect(cityFilter, "city");
  autoApplySelect(msoTypeFilter, "mso_type");
  autoApplySelect(headendFilter, "head_end");
  autoApplySelect(crnFilter, "crn_no");
  autoApplySelect(channelFilter, "channel_name");
  autoApplySelect(bandFilter, "band");
  autoApplySelect(weekFilter, "week");
  autoApplySelect(changeFilter, "change");

  document.getElementById("resetButton").addEventListener("click", () => {
    state.filters = {
      market: "",
      city: "",
      mso_type: "",
      head_end: "",
      crn_no: "",
      channel_name: "",
      band: "",
      week: "",
      change: "",
    };
    state.sortKey = "flow_order";
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

  document.getElementById("refreshButton").addEventListener("click", () => {
    state.page = 1;
    fetchDashboard();
  });
  document.getElementById("downloadDashboardButton").addEventListener("click", () => {
    window.location.href = "/download/dashboard";
  });
  Object.entries(viewButtons).forEach(([view, button]) => {
    button.addEventListener("click", () => {
      state.view = view;
      state.page = 1;
      fetchDashboard();
    });
  });
  fullscreenButton.addEventListener("click", toggleFullscreen);
  if (exitFullscreenButton) {
    exitFullscreenButton.addEventListener("click", async () => {
      if (fullscreenState.usingNativeFullscreen && document.fullscreenElement === tableFullscreenScope) {
        const exited = await exitNativeFullscreen();
        if (!exited) {
          fullscreenState.usingNativeFullscreen = false;
          setFullscreen(false);
        }
        return;
      }
      setFullscreen(false);
    });
  }
  document.addEventListener("fullscreenchange", () => {
    const isTableFullscreen = document.fullscreenElement === tableFullscreenScope;
    fullscreenState.usingNativeFullscreen = isTableFullscreen;
    if (isTableFullscreen && !fullscreenState.active) {
      setFullscreen(true);
      return;
    }
    if (!isTableFullscreen && fullscreenState.active) {
      fullscreenState.usingNativeFullscreen = false;
      setFullscreen(false);
    }
  });
  window.addEventListener("resize", () => {
    const nextPageSize = getPageSize();
    if (nextPageSize !== state.pageSize) {
      state.pageSize = nextPageSize;
      if (state.response) {
        state.page = 1;
        fetchDashboard();
      }
    }
  });
}

bindEvents();
updateViewMeta();
syncFullscreenButtons();
fetchDashboard();
