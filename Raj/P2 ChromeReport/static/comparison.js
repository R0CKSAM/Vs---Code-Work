(function () {
  const root = document.getElementById("comparisonTable");
  if (!root) return;

  const source = window.__COMPARISON_INITIAL_DATA__ || window.__CHROME_REPORT_DATA__?.comparison || {
    generated_at: "",
    weeks: [],
    pairs: [],
    rows_by_pair: {},
    message: "Comparison data could not be loaded.",
  };

  const state = {
    filters: {
      market: "",
      city: "",
      head_end: "",
      channel: "",
      week: "",
    },
    sortKey: "market",
    sortDirection: "asc",
    page: 1,
    pageSize: 25,
    columnWidths: {},
  };

  const columns = [
    { key: "market", type: "text" },
    { key: "city", type: "text" },
    { key: "head_end", type: "text" },
    { key: "channel", type: "text" },
    { key: "frequency_previous", type: "number" },
    { key: "frequency_current", type: "number" },
    { key: "frequency_change", type: "change" },
    { key: "rank_previous", type: "number" },
    { key: "rank_current", type: "number" },
    { key: "rank_change", type: "change" },
  ];

  const DEFAULT_COLUMN_WIDTHS = {
    market: 190,
    city: 150,
    head_end: 240,
    channel: 180,
    frequency_previous: 130,
    frequency_current: 130,
    frequency_change: 130,
    rank_previous: 120,
    rank_current: 120,
    rank_change: 120,
  };
  const MIN_COLUMN_WIDTH = 88;
  let activeResize = null;

  function getSingleSelectControl(id) {
    return {
      button: document.getElementById(id),
      menu: document.getElementById(`${id}Menu`),
      search: document.getElementById(`${id}Search`),
      options: document.getElementById(`${id}Options`),
    };
  }

  const marketFilter = getSingleSelectControl("comparisonMarketFilter");
  const cityFilter = getSingleSelectControl("comparisonCityFilter");
  const headendFilter = getSingleSelectControl("comparisonHeadendFilter");
  const channelFilter = getSingleSelectControl("comparisonChannelFilter");
  const weekFilter = getSingleSelectControl("comparisonWeekFilter");
  const resetButton = document.getElementById("comparisonResetButton");
  const fullscreenButton = document.getElementById("comparisonFullscreenButton");
  const exitFullscreenButton = document.getElementById("comparisonExitFullscreenButton");
  const prevPageButton = document.getElementById("comparisonPrevPage");
  const nextPageButton = document.getElementById("comparisonNextPage");
  const resultCount = document.getElementById("comparisonResultCount");
  const pageInfo = document.getElementById("comparisonPageInfo");
  const statusMessage = document.getElementById("comparisonStatusMessage");
  const tableHead = document.getElementById("comparisonTableHead");
  const tableBody = document.getElementById("comparisonTableBody");
  const tableWrap = root.closest(".comparison-table-wrap");
  const panel = root.closest(".comparison-panel");

  const fullscreenState = {
    active: false,
    usingNativeFullscreen: false,
    windowScrollY: 0,
    tableScrollTop: 0,
    tableScrollLeft: 0,
  };

  function normalizeText(value) {
    return String(value || "").trim();
  }

  function isMissing(value) {
    return value === null || value === undefined || value === "";
  }

  function uniqueValues(values) {
    return Array.from(new Set(values.filter((value) => normalizeText(value) !== "")));
  }

  function sortWeekLabels(values) {
    return values.slice().sort((left, right) => left.localeCompare(right, undefined, { numeric: true }));
  }

  function pairList() {
    return Array.isArray(source.pairs) ? source.pairs : [];
  }

  function availableWeeks() {
    return sortWeekLabels(uniqueValues(source.weeks || []));
  }

  function resolveActivePair() {
    const pairs = pairList();
    if (!pairs.length) return null;
    if (state.filters.week) {
      return pairs.find((pair) => pair.week_to === state.filters.week) || null;
    }
    return pairs[pairs.length - 1] || null;
  }

  function ensureWeekSelection() {
    if (state.filters.week) return;
    const activePair = resolveActivePair();
    if (activePair) state.filters.week = activePair.week_to;
  }

  function currentStatusMessage() {
    if (source.message) return source.message;
    if (state.filters.week && !resolveActivePair()) return "Previous week data is not available.";
    return "";
  }

  function activePairRows() {
    ensureWeekSelection();
    const activePair = resolveActivePair();
    if (!activePair) return [];
    const rows = source.rows_by_pair?.[activePair.pair_key] || [];
    return Array.isArray(rows) ? rows : [];
  }

  function rowMatches(row, ignoreKey = "") {
    if (ignoreKey !== "market" && state.filters.market && row.market !== state.filters.market) return false;
    if (ignoreKey !== "city" && state.filters.city && row.city !== state.filters.city) return false;
    if (ignoreKey !== "head_end" && state.filters.head_end && row.head_end !== state.filters.head_end) return false;
    if (ignoreKey !== "channel" && state.filters.channel && row.channel !== state.filters.channel) return false;
    return true;
  }

  function getFilterOptions(key) {
    const rows = activePairRows().filter((row) => rowMatches(row, key));
    return uniqueValues(rows.map((row) => row[key])).sort((left, right) => left.localeCompare(right, undefined, { numeric: true }));
  }

  function formatNumberValue(value) {
    if (isMissing(value)) return "NA";
    const numeric = Number(value);
    if (Number.isNaN(numeric)) return String(value);
    return Number.isInteger(numeric) ? String(numeric) : numeric.toFixed(2);
  }

  function formatDelta(value) {
    const numeric = Number(value);
    if (Number.isNaN(numeric)) return "0";
    const formatted = Number.isInteger(numeric) ? String(Math.abs(numeric)) : Math.abs(numeric).toFixed(2);
    if (numeric > 0) return `+${formatted}`;
    if (numeric < 0) return `-${formatted}`;
    return "0";
  }

  function getFrequencyChangeMeta(previous, current) {
    if (isMissing(previous) && isMissing(current)) return { text: "NA", type: "neutral", sortValue: 0 };
    if (isMissing(previous) && !isMissing(current)) return { text: `+${formatNumberValue(current)}`, type: "positive", sortValue: Number(current) || 1 };
    if (!isMissing(previous) && isMissing(current)) return { text: `-${formatNumberValue(previous)}`, type: "negative", sortValue: -(Number(previous) || 1) };
    const delta = Number(current) - Number(previous);
    if (delta > 0) return { text: formatDelta(delta), type: "positive", sortValue: delta };
    if (delta < 0) return { text: formatDelta(delta), type: "negative", sortValue: delta };
    return { text: "0", type: "neutral", sortValue: 0 };
  }

  function getRankChangeMeta(previous, current) {
    if (isMissing(previous) && isMissing(current)) return { text: "NA", type: "neutral", sortValue: 0 };
    if (isMissing(previous) && !isMissing(current)) return { text: `+${formatNumberValue(current)}`, type: "positive", sortValue: Number(current) || 1 };
    if (!isMissing(previous) && isMissing(current)) return { text: `-${formatNumberValue(previous)}`, type: "negative", sortValue: -(Number(previous) || 1) };
    const delta = Number(previous) - Number(current);
    if (delta > 0) return { text: formatDelta(delta), type: "positive", sortValue: delta };
    if (delta < 0) return { text: formatDelta(delta), type: "negative", sortValue: delta };
    return { text: "0", type: "neutral", sortValue: 0 };
  }

  function updateSingleSelectButton(control, value, placeholder) {
    if (control?.button) control.button.textContent = value || placeholder;
  }

  function closeMenus(exceptControl = null) {
    [marketFilter, cityFilter, headendFilter, channelFilter, weekFilter].forEach((control) => {
      if (control !== exceptControl && control?.menu) control.menu.hidden = true;
    });
  }

  function renderSingleSelectOptions(control, values, selectedValue, placeholder, onSelect) {
    if (!control?.options) return;
    const safeValues = Array.isArray(values) ? values.filter((value) => normalizeText(value) !== "") : [];
    const query = normalizeText(control.search?.value || "").toLowerCase();
    const fragment = document.createDocumentFragment();
    [{ value: "", label: placeholder }, ...safeValues.map((value) => ({ value, label: value }))]
      .filter((option) => !query || String(option.label || "").toLowerCase().includes(query))
      .forEach((option) => {
        const button = document.createElement("button");
        button.type = "button";
        button.className = `filter-option-row${option.value === selectedValue ? " active" : ""}`;
        button.textContent = option.label;
        button.addEventListener("click", () => onSelect(option.value));
        fragment.appendChild(button);
      });
    control.options.replaceChildren(fragment);
  }

  function syncSingleSelect(control, values, placeholder, selectedValue, onSelect) {
    const safeValues = Array.isArray(values) ? values.filter((value) => normalizeText(value) !== "") : [];
    const fallback = safeValues.includes(selectedValue) ? selectedValue : "";
    updateSingleSelectButton(control, fallback, placeholder);
    renderSingleSelectOptions(control, safeValues, fallback, placeholder, (value) => {
      onSelect(value);
      closeMenus();
    });
    return fallback;
  }

  function applyFilter(key, value) {
    state.filters[key] = value;
    state.page = 1;
    render();
  }

  function bindSingleSelect(control, key, placeholder) {
    if (!control?.button) return;
    control.button.addEventListener("click", (event) => {
      event.stopPropagation();
      const next = control.menu?.hidden ?? false;
      closeMenus();
      if (control.menu) control.menu.hidden = !next;
      if (next && control.search) {
        control.search.value = "";
        control.search.dispatchEvent(new Event("input"));
        requestAnimationFrame(() => control.search?.focus());
      }
    });
    if (control.search) {
      control.search.addEventListener("click", (event) => event.stopPropagation());
      control.search.addEventListener("input", () => {
        const values = key === "week" ? availableWeeks() : getFilterOptions(key);
        renderSingleSelectOptions(control, values, state.filters[key], placeholder, (value) => applyFilter(key, value));
      });
    }
  }

  function syncControls() {
    ensureWeekSelection();
    state.filters.market = syncSingleSelect(marketFilter, getFilterOptions("market"), "All Markets", state.filters.market, (value) => applyFilter("market", value));
    state.filters.city = syncSingleSelect(cityFilter, getFilterOptions("city"), "All Cities", state.filters.city, (value) => applyFilter("city", value));
    state.filters.head_end = syncSingleSelect(headendFilter, getFilterOptions("head_end"), "All Headends", state.filters.head_end, (value) => applyFilter("head_end", value));
    state.filters.channel = syncSingleSelect(channelFilter, getFilterOptions("channel"), "All Channels", state.filters.channel, (value) => applyFilter("channel", value));
    state.filters.week = syncSingleSelect(weekFilter, availableWeeks(), "Select Week", state.filters.week, (value) => applyFilter("week", value));
  }

  function filteredRows() {
    return activePairRows().filter((row) => rowMatches(row));
  }

  function sortValue(row, key) {
    if (key === "frequency_change") return getFrequencyChangeMeta(row.frequency_previous, row.frequency_current).sortValue;
    if (key === "rank_change") return getRankChangeMeta(row.rank_previous, row.rank_current).sortValue;
    if (["frequency_previous", "frequency_current", "rank_previous", "rank_current"].includes(key)) {
      if (isMissing(row[key])) return Number.NEGATIVE_INFINITY;
      return Number(row[key]);
    }
    return normalizeText(row[key]).toLowerCase();
  }

  function sortedRows() {
    return filteredRows().slice().sort((left, right) => {
      const leftValue = sortValue(left, state.sortKey);
      const rightValue = sortValue(right, state.sortKey);
      if (leftValue < rightValue) return state.sortDirection === "asc" ? -1 : 1;
      if (leftValue > rightValue) return state.sortDirection === "asc" ? 1 : -1;
      return 0;
    });
  }

  function getColumnLabel(columnKey) {
    const activePair = resolveActivePair();
    const previousWeek = activePair?.week_from || "Week N-1";
    const currentWeek = activePair?.week_to || "Week N";
    const labels = {
      market: "Market",
      city: "City",
      head_end: "Headend",
      channel: "Channel",
      frequency_previous: `Frequency (${previousWeek})`,
      frequency_current: `Frequency (${currentWeek})`,
      frequency_change: "Frequency Change",
      rank_previous: `Rank (${previousWeek})`,
      rank_current: `Rank (${currentWeek})`,
      rank_change: "Rank Change",
    };
    return labels[columnKey] || columnKey;
  }

  function getColGroup() {
    let colGroup = root.querySelector("colgroup");
    if (!colGroup) {
      colGroup = document.createElement("colgroup");
      root.insertBefore(colGroup, tableHead);
    }
    return colGroup;
  }

  function applyColumnWidths() {
    const colGroup = getColGroup();
    const fragment = document.createDocumentFragment();
    columns.forEach((column) => {
      const col = document.createElement("col");
      const width = state.columnWidths[column.key];
      if (width) col.style.width = `${width}px`;
      fragment.appendChild(col);
    });
    colGroup.replaceChildren(fragment);
  }

  function setColumnWidth(columnKey, width) {
    state.columnWidths[columnKey] = Math.max(MIN_COLUMN_WIDTH, Math.round(width));
    applyColumnWidths();
  }

  function stopColumnResize() {
    if (!activeResize) return;
    activeResize.handle?.classList.remove("active");
    activeResize = null;
    document.body.classList.remove("comparison-resizing");
  }

  function handleColumnResize(event) {
    if (!activeResize) return;
    setColumnWidth(activeResize.columnKey, activeResize.startWidth + (event.clientX - activeResize.startX));
  }

  function startColumnResize(event, columnKey, handle) {
    event.preventDefault();
    event.stopPropagation();
    const startWidth = state.columnWidths[columnKey]
      || handle.closest("th")?.getBoundingClientRect().width
      || DEFAULT_COLUMN_WIDTHS[columnKey]
      || 120;
    activeResize = { columnKey, startX: event.clientX, startWidth, handle };
    handle.classList.add("active");
    document.body.classList.add("comparison-resizing");
  }

  function buildHeader() {
    applyColumnWidths();
    const tr = document.createElement("tr");
    columns.forEach((column) => {
      const th = document.createElement("th");
      const isActive = state.sortKey === column.key;
      const suffix = isActive ? (state.sortDirection === "asc" ? " ▲" : " ▼") : "";
      th.className = "comparison-sortable";

      const label = document.createElement("span");
      label.className = "comparison-header-label";
      label.textContent = `${getColumnLabel(column.key)}${suffix}`;

      const handle = document.createElement("span");
      handle.className = "comparison-resize-handle";
      handle.title = "Drag to resize column";
      handle.addEventListener("mousedown", (event) => startColumnResize(event, column.key, handle));

      th.append(label, handle);
      th.addEventListener("click", () => {
        if (state.sortKey === column.key) state.sortDirection = state.sortDirection === "asc" ? "desc" : "asc";
        else {
          state.sortKey = column.key;
          state.sortDirection = "asc";
        }
        render();
      });
      tr.appendChild(th);
    });
    tableHead.replaceChildren(tr);
  }

  function buildRow(row) {
    const tr = document.createElement("tr");
    columns.forEach((column) => {
      const td = document.createElement("td");
      if (column.key === "frequency_change") {
        const meta = getFrequencyChangeMeta(row.frequency_previous, row.frequency_current);
        td.textContent = meta.text;
        td.className = `comparison-change-${meta.type}`;
      } else if (column.key === "rank_change") {
        const meta = getRankChangeMeta(row.rank_previous, row.rank_current);
        td.textContent = meta.text;
        td.className = `comparison-change-${meta.type}`;
      } else {
        td.textContent = column.type === "number" ? formatNumberValue(row[column.key]) : normalizeText(row[column.key]);
        td.className = column.type === "number" ? "comparison-number-cell" : "comparison-text-cell";
      }
      tr.appendChild(td);
    });
    return tr;
  }

  function renderStatus() {
    const message = currentStatusMessage();
    if (message) {
      statusMessage.hidden = false;
      statusMessage.textContent = message;
      return;
    }
    statusMessage.hidden = true;
    statusMessage.textContent = "";
  }

  function renderTable() {
    const rows = sortedRows();
    resultCount.textContent = `${new Intl.NumberFormat().format(rows.length)} rows`;
    const totalPages = Math.max(1, Math.ceil(rows.length / state.pageSize));
    if (state.page > totalPages) state.page = totalPages;
    const pageRows = rows.slice((state.page - 1) * state.pageSize, state.page * state.pageSize);
    pageInfo.textContent = `Page ${state.page} of ${totalPages}`;
    if (prevPageButton) prevPageButton.disabled = state.page <= 1;
    if (nextPageButton) nextPageButton.disabled = state.page >= totalPages;

    buildHeader();
    if (!pageRows.length) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = columns.length;
      td.className = "empty-state";
      td.textContent = currentStatusMessage() || "No comparison rows match the current filters.";
      tr.appendChild(td);
      tableBody.replaceChildren(tr);
      return;
    }
    const fragment = document.createDocumentFragment();
    pageRows.forEach((row) => fragment.appendChild(buildRow(row)));
    tableBody.replaceChildren(fragment);
  }

  function render() {
    renderStatus();
    syncControls();
    renderTable();
  }

  function syncFullscreenButtons() {
    const label = fullscreenState.active ? "Exit Full Screen" : "Full Screen";
    if (fullscreenButton) fullscreenButton.textContent = label;
    if (exitFullscreenButton) exitFullscreenButton.hidden = !fullscreenState.active;
  }

  function setFullscreen(active) {
    if (!panel || !tableWrap || fullscreenState.active === active) return;
    if (active) {
      fullscreenState.windowScrollY = window.scrollY || window.pageYOffset || 0;
      fullscreenState.tableScrollTop = tableWrap.scrollTop;
      fullscreenState.tableScrollLeft = tableWrap.scrollLeft;
      fullscreenState.active = true;
      document.body.classList.add("comparison-fullscreen-active");
      panel.classList.add("comparison-panel-fullscreen");
    } else {
      fullscreenState.tableScrollTop = tableWrap.scrollTop;
      fullscreenState.tableScrollLeft = tableWrap.scrollLeft;
      fullscreenState.active = false;
      document.body.classList.remove("comparison-fullscreen-active");
      panel.classList.remove("comparison-panel-fullscreen");
    }
    render();
    requestAnimationFrame(() => {
      if (!active) window.scrollTo({ top: fullscreenState.windowScrollY, behavior: "auto" });
      tableWrap.scrollTop = fullscreenState.tableScrollTop;
      tableWrap.scrollLeft = fullscreenState.tableScrollLeft;
    });
    syncFullscreenButtons();
  }

  async function enterNativeFullscreen() {
    if (!panel?.requestFullscreen) return false;
    try {
      fullscreenState.usingNativeFullscreen = true;
      await panel.requestFullscreen();
      return true;
    } catch (_error) {
      fullscreenState.usingNativeFullscreen = false;
      return false;
    }
  }

  async function exitNativeFullscreen() {
    if (!document.fullscreenElement) return false;
    try {
      await document.exitFullscreen();
      return true;
    } catch (_error) {
      return false;
    }
  }

  async function toggleFullscreen() {
    if (fullscreenState.active) {
      if (fullscreenState.usingNativeFullscreen && document.fullscreenElement === panel) {
        const exited = await exitNativeFullscreen();
        if (!exited) setFullscreen(false);
        return;
      }
      setFullscreen(false);
      return;
    }
    const entered = await enterNativeFullscreen();
    if (!entered) setFullscreen(true);
  }

  bindSingleSelect(marketFilter, "market", "All Markets");
  bindSingleSelect(cityFilter, "city", "All Cities");
  bindSingleSelect(headendFilter, "head_end", "All Headends");
  bindSingleSelect(channelFilter, "channel", "All Channels");
  bindSingleSelect(weekFilter, "week", "Select Week");

  document.addEventListener("click", (event) => {
    if (!event.target.closest(".filter-select")) closeMenus();
  });
  document.addEventListener("mousemove", handleColumnResize);
  document.addEventListener("mouseup", stopColumnResize);
  document.addEventListener("mouseleave", stopColumnResize);
  document.addEventListener("fullscreenchange", () => {
    const isPanelFullscreen = document.fullscreenElement === panel;
    fullscreenState.usingNativeFullscreen = isPanelFullscreen;
    if (isPanelFullscreen && !fullscreenState.active) {
      setFullscreen(true);
      return;
    }
    if (!isPanelFullscreen && fullscreenState.active) {
      fullscreenState.usingNativeFullscreen = false;
      setFullscreen(false);
    }
  });

  if (resetButton) {
    resetButton.addEventListener("click", () => {
      state.filters = { market: "", city: "", head_end: "", channel: "", week: "" };
      state.page = 1;
      render();
    });
  }
  if (fullscreenButton) fullscreenButton.addEventListener("click", toggleFullscreen);
  if (exitFullscreenButton) {
    exitFullscreenButton.addEventListener("click", async () => {
      if (fullscreenState.usingNativeFullscreen && document.fullscreenElement === panel) {
        const exited = await exitNativeFullscreen();
        if (!exited) setFullscreen(false);
        return;
      }
      setFullscreen(false);
    });
  }
  if (prevPageButton) {
    prevPageButton.addEventListener("click", () => {
      if (state.page > 1) {
        state.page -= 1;
        render();
      }
    });
  }
  if (nextPageButton) {
    nextPageButton.addEventListener("click", () => {
      const totalPages = Math.max(1, Math.ceil(sortedRows().length / state.pageSize));
      if (state.page < totalPages) {
        state.page += 1;
        render();
      }
    });
  }
  window.addEventListener("resize", () => render());

  columns.forEach((column) => {
    state.columnWidths[column.key] = DEFAULT_COLUMN_WIDTHS[column.key] || 120;
  });

  syncFullscreenButtons();
  render();
})();
