(function () {
  const root = document.getElementById("otsTable");
  if (!root) return;

  const state = {
    payload: null,
    filters: {
      markets: [],
      channels: [],
      week_from: "",
      week_to: "",
      change: "",
    },
    page: 1,
    pageSize: 30,
    sortKey: "market",
    sortDirection: "asc",
    loading: false,
    standalone: Boolean(window.__OTS_STANDALONE_DATA__),
    initial: window.__OTS_INITIAL_DATA__ || null,
    columnWidths: {},
    report: {
      open: false,
      markets: [],
      channels: [],
    },
  };
  const DEFAULT_REPORT_CHANNEL_KEYS = ["INDIATV", "AAJTAK", "NEWS18INDIA", "REPUBLICBHARAT"];

  const marketButton = document.getElementById("otsMarketButton");
  const marketMenu = document.getElementById("otsMarketMenu");
  const marketSearchInput = document.getElementById("otsMarketSearch");
  const marketOptions = document.getElementById("otsMarketOptions");
  const channelButton = document.getElementById("otsChannelButton");
  const channelMenu = document.getElementById("otsChannelMenu");
  const channelSearchInput = document.getElementById("otsChannelSearch");
  const channelOptions = document.getElementById("otsChannelOptions");
  function getSingleSelectControl(id) {
    return {
      button: document.getElementById(id),
      menu: document.getElementById(`${id}Menu`),
      search: document.getElementById(`${id}Search`),
      options: document.getElementById(`${id}Options`),
    };
  }
  const weekFromFilter = getSingleSelectControl("otsWeekFromFilter");
  const weekToFilter = getSingleSelectControl("otsWeekToFilter");
  const changeFilter = getSingleSelectControl("otsChangeFilter");
  function getMultiSelectControl(id) {
    return {
      button: document.getElementById(id),
      menu: document.getElementById(`${id}Menu`),
      search: document.getElementById(`${id}Search`),
      options: document.getElementById(`${id}Options`),
    };
  }
  const reportToggleButton = document.getElementById("otsReportToggleButton");
  const reportLauncher = document.getElementById("otsReportLauncher");
  const reportPanel = document.getElementById("otsReportPanel");
  const reportMeta = document.getElementById("otsReportMeta");
  const reportCount = document.getElementById("otsReportCount");
  const reportStatus = document.getElementById("otsReportStatusMessage");
  const reportContent = document.getElementById("otsReportContent");
  const reportMarketFilter = getMultiSelectControl("otsReportMarketFilter");
  const reportChannelFilter = getMultiSelectControl("otsReportChannelFilter");
  const reportResetButton = document.getElementById("otsReportResetButton");
  const reportDownloadButton = document.getElementById("otsReportDownloadButton");
  const reportPrintButton = document.getElementById("otsReportPrintButton");
  const reportHideButton = document.getElementById("otsReportHideButton");
  const resultCount = document.getElementById("otsResultCount");
  const tableHead = document.getElementById("otsTableHead");
  const tableBody = document.getElementById("otsTableBody");
  const statusMessage = document.getElementById("otsStatusMessage");
  const refreshButton = document.getElementById("otsRefreshButton");
  const resetButton = document.getElementById("otsResetButton");
  const fullscreenButton = document.getElementById("otsFullscreenButton");
  const exitFullscreenButton = document.getElementById("otsExitFullscreenButton");
  const prevPageButton = document.getElementById("otsPrevPage");
  const nextPageButton = document.getElementById("otsNextPage");
  const pageInfo = document.getElementById("otsPageInfo");
  const tableWrap = root.closest(".ots-table-wrap");
  const panel = root.closest(".ots-panel");
  const MIN_COLUMN_WIDTH = 80;
  const DEFAULT_COLUMN_WIDTHS = {
    market: 150,
    channel: 180,
    change: 110,
  };
  let activeResize = null;

  const fullscreenState = {
    active: false,
    windowScrollY: 0,
    tableScrollTop: 0,
    tableScrollLeft: 0,
    usingNativeFullscreen: false,
  };

  function getPageSize() {
    if (!fullscreenState.active) return 30;
    const wrapHeight = tableWrap?.clientHeight || Math.max(window.innerHeight - 220, 320);
    const headerHeight = tableHead?.getBoundingClientRect().height || 34;
    const sampleRow = tableBody?.querySelector("tr");
    const rowHeight = sampleRow?.getBoundingClientRect().height || 26;
    const usableHeight = Math.max(wrapHeight - headerHeight - 8, rowHeight);
    return Math.max(30, Math.floor(usableHeight / rowHeight));
  }

  function normalizeText(value) {
    return String(value || "").trim();
  }

  function normalizeChannelKey(value) {
    return normalizeText(value).toUpperCase().replace(/[^A-Z0-9]+/g, "");
  }

  function formatChannelLabel(value) {
    return normalizeText(value).toUpperCase();
  }

  function formatOtsNumber(value) {
    if (value === null || value === undefined || value === "") return "NA";
    return Number(value).toFixed(2);
  }

  function formatDeltaNumber(value) {
    return Number(Math.abs(value)).toFixed(2);
  }

  function getColumnDefinitions(weeks) {
    return [
      { key: "market", label: "MARKET", className: "sticky-col ots-sticky-market" },
      { key: "channel", label: "CHANNEL", className: "sticky-col ots-sticky-channel" },
      ...weeks.map((week) => ({ key: week, label: week })),
      { key: "change", label: "CHANGE" },
    ];
  }

  function getDefaultColumnWidth(key) {
    if (DEFAULT_COLUMN_WIDTHS[key]) return DEFAULT_COLUMN_WIDTHS[key];
    if (String(key).startsWith("Wk-")) return 96;
    return 120;
  }

  function getColGroup() {
    let colGroup = root.querySelector("colgroup");
    if (!colGroup) {
      colGroup = document.createElement("colgroup");
      root.insertBefore(colGroup, tableHead);
    }
    return colGroup;
  }

  function updateStickyOffsets() {
    const marketWidth = state.columnWidths.market || getDefaultColumnWidth("market");
    root.style.setProperty("--ots-market-width", `${marketWidth}px`);
  }

  function applyColumnWidths(columns) {
    const colGroup = getColGroup();
    const fragment = document.createDocumentFragment();
    columns.forEach((column) => {
      const col = document.createElement("col");
      const width = state.columnWidths[column.key];
      if (width) col.style.width = `${width}px`;
      fragment.appendChild(col);
    });
    colGroup.replaceChildren(fragment);
    updateStickyOffsets();
  }

  function setColumnWidth(columnKey, width) {
    state.columnWidths[columnKey] = Math.max(MIN_COLUMN_WIDTH, Math.round(width));
    applyColumnWidths(getColumnDefinitions(state.payload?.visible_weeks || state.payload?.weeks || []));
  }

  function stopColumnResize() {
    if (!activeResize) return;
    activeResize.handle?.classList.remove("active");
    activeResize = null;
    document.body.classList.remove("ots-resizing");
  }

  function handleColumnResize(event) {
    if (!activeResize) return;
    const delta = event.clientX - activeResize.startX;
    setColumnWidth(activeResize.columnKey, activeResize.startWidth + delta);
  }

  function startColumnResize(event, columnKey, handle) {
    event.preventDefault();
    event.stopPropagation();
    const startWidth = state.columnWidths[columnKey]
      || handle.closest("th")?.getBoundingClientRect().width
      || getDefaultColumnWidth(columnKey);
    activeResize = {
      columnKey,
      startX: event.clientX,
      startWidth,
      handle,
    };
    handle.classList.add("active");
    document.body.classList.add("ots-resizing");
  }

  function updateSingleSelectButton(control, value, placeholder, labels = null) {
    if (control?.button) control.button.textContent = value ? (labels?.[value] || value) : placeholder;
  }

  function renderSingleSelectOptions(control, values, selectedValue, placeholder, onSelect, labels = null) {
    if (!control?.options) return;
    const safeValues = Array.isArray(values) ? values.filter((value) => normalizeText(value) !== "") : [];
    const query = normalizeText(control.search?.value || "").toLowerCase();
    const fragment = document.createDocumentFragment();
    [{ value: "", label: placeholder }, ...safeValues.map((value) => ({ value, label: labels?.[value] || value }))]
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

  function syncSingleSelect(control, values, placeholder, selectedValue, onSelect, labels = null) {
    const safeValues = Array.isArray(values) ? values.filter((value) => normalizeText(value) !== "") : [];
    const fallback = safeValues.includes(selectedValue) ? selectedValue : "";
    updateSingleSelectButton(control, fallback, placeholder, labels);
    renderSingleSelectOptions(control, safeValues, fallback, placeholder, (value) => {
      onSelect(value);
      closeMenus();
    }, labels);
    return fallback;
  }

  function getConstrainedWeekOptions(allWeeks, key) {
    const weeks = Array.isArray(allWeeks) ? allWeeks.filter((value) => normalizeText(value) !== "") : [];
    if (key === "week_from") {
      const toIndex = state.filters.week_to && weeks.includes(state.filters.week_to) ? weeks.indexOf(state.filters.week_to) : weeks.length - 1;
      return weeks.slice(0, toIndex + 1);
    }
    if (key === "week_to") {
      const fromIndex = state.filters.week_from && weeks.includes(state.filters.week_from) ? weeks.indexOf(state.filters.week_from) : 0;
      return weeks.slice(fromIndex);
    }
    return weeks;
  }

  // Format one OTS value without changing the stored numeric payload.
  function formatOtsValue(value) {
    if (value === null || value === undefined || value === "") return "-";
    return `${Number(value).toFixed(2)}%`;
  }

  // Build the visible week slice from the selected from/to controls.
  function getVisibleWeeks(payload) {
    const allWeeks = payload.weeks || [];
    if (!allWeeks.length) return [];
    if (state.filters.week_from || state.filters.week_to) {
      const startIndex = state.filters.week_from && allWeeks.includes(state.filters.week_from) ? allWeeks.indexOf(state.filters.week_from) : 0;
      const endIndex = state.filters.week_to && allWeeks.includes(state.filters.week_to) ? allWeeks.indexOf(state.filters.week_to) : allWeeks.length - 1;
      const from = Math.min(startIndex, endIndex);
      const to = Math.max(startIndex, endIndex);
      return allWeeks.slice(from, to + 1);
    }
    return allWeeks.slice(Math.max(0, allWeeks.length - 8));
  }

  // Calculate the change label from the latest two visible weeks.
function getChangeMeta(record, weeks) {
    if (weeks.length < 2) {
      return { text: "0%", type: "no_change", delta: null };
    }
    const previous = record.ots_values?.[weeks[weeks.length - 2]];
    const current = record.ots_values?.[weeks[weeks.length - 1]];
    if (previous === null || previous === undefined || current === null || current === undefined) {
      return { text: "0%", type: "no_change", delta: null };
    }
    const delta = Number((Number(current) - Number(previous)).toFixed(2));
    if (delta > 0) return { text: `▲ +${delta.toFixed(2)}%`, type: "increase", delta };
    if (delta < 0) return { text: `▼ ${delta.toFixed(2)}%`, type: "decrease", delta };
    return { text: "0%", type: "no_change", delta: 0 };
  }

  function matchesChangeFilter(changeType, filterValue) {
    if (!filterValue) return true;
    if (filterValue === "changed") return changeType === "increase" || changeType === "decrease";
    if (filterValue === "no_change") return changeType === "no_change";
    return changeType === filterValue;
  }

  // Apply the standalone filters locally so exported HTML behaves like the live server.
  function filterStandaloneRecords(records, payload) {
    const visibleWeeks = getVisibleWeeks(payload);
    return records.filter((record) => {
      if (state.filters.markets.length && !state.filters.markets.includes(record.market)) return false;
      if (state.filters.channels.length && !state.filters.channels.includes(record.channel)) return false;
      if (state.filters.change) {
        if (!matchesChangeFilter(getChangeMeta(record, visibleWeeks).type, state.filters.change)) return false;
      }
      return true;
    });
  }

  function setLoading(loading) {
    state.loading = loading;
    document.body.classList.toggle("loading", loading);
  }

  function renderStatus(payload) {
    if (payload.message) {
      statusMessage.hidden = false;
      statusMessage.textContent = `${payload.message} Folder: ${payload.source_directory}`;
      return;
    }
    statusMessage.hidden = true;
    statusMessage.textContent = "";
  }

  function updateMultiSelectButton(button, selectedValues, emptyLabel, singularLabel) {
    if (!button) return;
    if (!selectedValues.length) {
      button.textContent = emptyLabel;
      return;
    }
    if (selectedValues.length === 1) {
      button.textContent = selectedValues[0];
      return;
    }
    button.textContent = `${selectedValues.length} ${singularLabel}`;
  }

  // Render one checkbox list used by the custom multi-select filters.
  function renderMultiSelectOptions(container, values, selectedValues, key, query = "") {
    if (!container) return;
    const selected = new Set(selectedValues);
    const fragment = document.createDocumentFragment();
    const normalizedQuery = normalizeText(query).toLowerCase();

    values
      .filter((value) => !normalizedQuery || String(value || "").toLowerCase().includes(normalizedQuery))
      .forEach((value) => {
      const label = document.createElement("label");
      label.className = "ots-option-row";
      const input = document.createElement("input");
      input.type = "checkbox";
      input.checked = selected.has(value);
      input.addEventListener("change", () => {
        const next = new Set(state.filters[key]);
        if (input.checked) next.add(value);
        else next.delete(value);
        state.filters[key] = Array.from(next).sort((left, right) => left.localeCompare(right));
        state.page = 1;
        fetchPayload(false);
      });
      const text = document.createElement("span");
      text.textContent = value;
      label.append(input, text);
      fragment.appendChild(label);
    });

    container.replaceChildren(fragment);
  }

  function updateReportMultiSelectButton(button, selectedValues, allValues, emptyLabel, noun) {
    if (!button) return;
    if (!selectedValues.length || selectedValues.length === allValues.length) {
      button.textContent = emptyLabel;
      return;
    }
    if (selectedValues.length === 1) {
      button.textContent = selectedValues[0];
      return;
    }
    button.textContent = `${selectedValues.length} ${noun}`;
  }

  function renderReportOptions(control, values, selectedValues, onToggle) {
    if (!control?.options) return;
    const query = normalizeText(control.search?.value || "").toLowerCase();
    const selected = new Set(selectedValues);
    const fragment = document.createDocumentFragment();
    values
      .filter((value) => !query || value.toLowerCase().includes(query))
      .forEach((value) => {
        const label = document.createElement("label");
        label.className = "ots-option-row";
        const input = document.createElement("input");
        input.type = "checkbox";
        input.checked = selected.has(value);
        input.addEventListener("change", () => onToggle(value, input.checked));
        const text = document.createElement("span");
        text.textContent = value;
        label.append(input, text);
        fragment.appendChild(label);
      });
    control.options.replaceChildren(fragment);
  }

  // Sync all OTS filters from the newest payload while preserving current selections when possible.
  function syncControls(payload) {
    const filterData = payload.filters || {};
    renderMultiSelectOptions(marketOptions, filterData.markets || [], state.filters.markets, "markets", marketSearchInput?.value || "");
    renderMultiSelectOptions(channelOptions, filterData.channels || [], state.filters.channels, "channels", channelSearchInput?.value || "");
    state.filters.markets = state.filters.markets.filter((value) => (filterData.markets || []).includes(value));
    state.filters.channels = state.filters.channels.filter((value) => (filterData.channels || []).includes(value));
    updateMultiSelectButton(marketButton, state.filters.markets, "All Markets", "markets selected");
    updateMultiSelectButton(channelButton, state.filters.channels, "All Channels", "channels selected");
    state.filters.week_from = syncSingleSelect(weekFromFilter, getConstrainedWeekOptions(payload.weeks || [], "week_from"), "From Week", state.filters.week_from, (value) => applySingleFilter("week_from", value));
    state.filters.week_to = syncSingleSelect(weekToFilter, getConstrainedWeekOptions(payload.weeks || [], "week_to"), "To Week", state.filters.week_to, (value) => applySingleFilter("week_to", value));
    state.filters.change = syncSingleSelect(
      changeFilter,
      ["changed", "no_change", "increase", "decrease"],
      "All Changes",
      state.filters.change,
      (value) => applySingleFilter("change", value),
      { changed: "Changed", increase: "Increase", decrease: "Decrease", no_change: "No Change" }
    );
  }

  function sortRecords(records, weeks) {
    return records.slice().sort((left, right) => {
      let leftValue;
      let rightValue;
      if (state.sortKey === "market" || state.sortKey === "channel") {
        leftValue = normalizeText(left[state.sortKey]).toLowerCase();
        rightValue = normalizeText(right[state.sortKey]).toLowerCase();
      } else if (state.sortKey === "change") {
        leftValue = getChangeMeta(left, weeks).delta ?? 0;
        rightValue = getChangeMeta(right, weeks).delta ?? 0;
      } else {
        leftValue = left.ots_values?.[state.sortKey];
        rightValue = right.ots_values?.[state.sortKey];
        if (leftValue === null || leftValue === undefined) leftValue = -Infinity;
        if (rightValue === null || rightValue === undefined) rightValue = -Infinity;
      }

      if (leftValue < rightValue) return state.sortDirection === "asc" ? -1 : 1;
      if (leftValue > rightValue) return state.sortDirection === "asc" ? 1 : -1;
      return 0;
    });
  }

  function buildHeader(weeks) {
    const tr = document.createElement("tr");
    const columns = [
      { key: "market", label: "MARKET", className: "sticky-col ots-sticky-market" },
      { key: "channel", label: "CHANNEL", className: "sticky-col ots-sticky-channel" },
      ...weeks.map((week) => ({ key: week, label: week })),
      { key: "change", label: "CHANGE" },
    ];

    columns.forEach((column) => {
      const th = document.createElement("th");
      const isActive = state.sortKey === column.key;
      const suffix = isActive ? (state.sortDirection === "asc" ? " ▲" : " ▼") : "";
      th.textContent = `${column.label}${suffix}`;
      th.className = `${column.className || ""} ots-sortable`.trim();
      th.addEventListener("click", () => {
        if (state.sortKey === column.key) {
          state.sortDirection = state.sortDirection === "asc" ? "desc" : "asc";
        } else {
          state.sortKey = column.key;
          state.sortDirection = "asc";
        }
        render(state.payload);
      });
      tr.appendChild(th);
    });

    tableHead.replaceChildren(tr);
  }

  function buildHeader(weeks) {
    const tr = document.createElement("tr");
    const columns = getColumnDefinitions(weeks);
    applyColumnWidths(columns);

    columns.forEach((column) => {
      const th = document.createElement("th");
      const isActive = state.sortKey === column.key;
      const suffix = isActive ? (state.sortDirection === "asc" ? " ▲" : " ▼") : "";
      th.className = `${column.className || ""} ots-sortable`.trim();
      th.dataset.columnKey = column.key;

      const label = document.createElement("span");
      label.className = "ots-header-label";
      label.textContent = `${column.label}${suffix}`;

      const handle = document.createElement("span");
      handle.className = "ots-resize-handle";
      handle.title = "Drag to resize column";
      handle.addEventListener("mousedown", (event) => startColumnResize(event, column.key, handle));

      th.append(label, handle);
      th.addEventListener("click", () => {
        if (state.sortKey === column.key) {
          state.sortDirection = state.sortDirection === "asc" ? "desc" : "asc";
        } else {
          state.sortKey = column.key;
          state.sortDirection = "asc";
        }
        render(state.payload);
      });

      tr.appendChild(th);
    });

    tableHead.replaceChildren(tr);
  }

  function buildRow(record, weeks) {
    const tr = document.createElement("tr");

    [
      { value: record.market, className: "sticky-col ots-sticky-market ots-sticky-body" },
      { value: record.channel, className: "sticky-col ots-sticky-channel ots-sticky-body" },
    ].forEach((column) => {
      const td = document.createElement("td");
      td.textContent = column.value || "";
      td.className = column.className;
      tr.appendChild(td);
    });

    weeks.forEach((week, weekIndex) => {
      const td = document.createElement("td");
      const value = record.ots_values?.[week];
      td.textContent = formatOtsValue(value);
      if (value === null || value === undefined || value === "") {
        td.classList.add("ots-change-no_change");
      } else if (weekIndex > 0) {
        const previous = record.ots_values?.[weeks[weekIndex - 1]];
        if (previous !== null && previous !== undefined && previous !== "") {
          const delta = Number(value) - Number(previous);
          if (delta > 0) td.classList.add("ots-change-increase");
          else if (delta < 0) td.classList.add("ots-change-decrease");
          else td.classList.add("ots-change-no_change");
        }
      }
      tr.appendChild(td);
    });

    const changeMeta = getChangeMeta(record, weeks);
    const changeTd = document.createElement("td");
    changeTd.textContent = changeMeta.text;
    changeTd.className = `ots-change-${changeMeta.type}`;
    tr.appendChild(changeTd);
    return tr;
  }

  function renderTable(payload) {
    const weeks = payload.visible_weeks || payload.weeks || [];
    if (state.sortKey !== "market" && state.sortKey !== "channel" && state.sortKey !== "change" && !weeks.includes(state.sortKey)) {
      state.sortKey = "market";
      state.sortDirection = "asc";
    }
    state.pageSize = getPageSize();
    buildHeader(weeks);
    const sortedRecords = sortRecords(payload.table.records || [], weeks);
    const totalPages = Math.max(1, Math.ceil(sortedRecords.length / state.pageSize));
    if (state.page > totalPages) state.page = totalPages;
    const pageRecords = sortedRecords.slice((state.page - 1) * state.pageSize, state.page * state.pageSize);

    pageInfo.textContent = `Page ${state.page} of ${totalPages}`;
    prevPageButton.disabled = state.page <= 1;
    nextPageButton.disabled = state.page >= totalPages;

    if (!pageRecords.length) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = 3 + weeks.length;
      td.className = "empty-state";
      td.textContent = "No OTS rows match the current filters.";
      tr.appendChild(td);
      tableBody.replaceChildren(tr);
      return;
    }

    const fragment = document.createDocumentFragment();
    pageRecords.forEach((record) => fragment.appendChild(buildRow(record, weeks)));
    tableBody.replaceChildren(fragment);
  }

  function render(payload) {
    state.payload = payload;
    syncControls(payload);
    renderStatus(payload);
    resultCount.textContent = `${new Intl.NumberFormat().format(payload.table.total_count || 0)} records`;
    renderTable(payload);
    renderReportPanel();
  }

  function getAllSourceRecords() {
    if (state.standalone) {
      const source = window.__OTS_STANDALONE_DATA__ || {};
      return source.table?.records || source.records || [];
    }
    return state.payload?.table?.records || [];
  }

  function getReportVisibleWeeks() {
    const payload = state.payload || window.__OTS_STANDALONE_DATA__ || { weeks: [] };
    const visibleWeeks = getVisibleWeeks(payload);
    return visibleWeeks.length >= 2 ? visibleWeeks.slice(-2) : visibleWeeks;
  }

  function getReportBaseRecords() {
    const sourceRecords = getAllSourceRecords();
    return sourceRecords.filter((record) => {
      if (state.filters.markets.length && !state.filters.markets.includes(record.market)) return false;
      if (state.filters.channels.length && !state.filters.channels.includes(record.channel)) return false;
      return true;
    });
  }

  function getReportContext() {
    const baseRecords = getReportBaseRecords();
    const markets = Array.from(new Set(baseRecords.map((record) => normalizeText(record.market)).filter(Boolean)))
      .sort((left, right) => left.localeCompare(right, undefined, { numeric: true }));
    const channels = Array.from(new Set(baseRecords.map((record) => normalizeText(record.channel)).filter(Boolean)))
      .sort((left, right) => left.localeCompare(right, undefined, { numeric: true }));
    return {
      weeks: getReportVisibleWeeks(),
      markets,
      channels,
    };
  }

  function getDefaultReportChannels(options) {
    const defaults = options.filter((value) => DEFAULT_REPORT_CHANNEL_KEYS.includes(normalizeChannelKey(value)));
    return (defaults.length ? defaults : options.slice(0, 4)).slice();
  }

  function syncReportSelections(context) {
    state.report.markets = state.report.markets.filter((value) => context.markets.includes(value));
    if (!state.report.markets.length) state.report.markets = context.markets.slice();

    state.report.channels = state.report.channels.filter((value) => context.channels.includes(value));
    if (!state.report.channels.length) state.report.channels = getDefaultReportChannels(context.channels);
  }

  function buildReportNarratives() {
    const weeks = getReportVisibleWeeks();
    if (weeks.length < 2) {
      return {
        weeks,
        groups: [],
        items: [],
        message: "Select at least two visible weeks to generate the OTS change report.",
      };
    }

    const [previousWeek, currentWeek] = weeks;
    const baseRecords = getReportBaseRecords();
    const selectedMarkets = state.report.markets.length ? state.report.markets : getReportContext().markets;
    const selectedChannels = state.report.channels.length ? state.report.channels : getDefaultReportChannels(getReportContext().channels);
    const groups = [];
    const items = [];

    selectedChannels.forEach((channel) => {
      const channelLabel = formatChannelLabel(channel);
      const narratives = [];

      selectedMarkets.forEach((market) => {
        const record = baseRecords.find((item) => normalizeText(item.market) === market && normalizeChannelKey(item.channel) === normalizeChannelKey(channel));
        if (!record) return;

        const previousValue = record.ots_values?.[previousWeek];
        const currentValue = record.ots_values?.[currentWeek];
        const previousMissing = previousValue === null || previousValue === undefined || previousValue === "";
        const currentMissing = currentValue === null || currentValue === undefined || currentValue === "";

        if ((previousMissing && currentMissing) || (!previousMissing && !currentMissing && Number(previousValue) === Number(currentValue))) {
          return;
        }

        let direction = "increased";
        let delta = 0;

        if (previousMissing && !currentMissing) {
          direction = "increased";
          delta = Number(currentValue);
        } else if (!previousMissing && currentMissing) {
          direction = "decreased";
          delta = Number(previousValue);
        } else {
          delta = Number(currentValue) - Number(previousValue);
          direction = delta >= 0 ? "increased" : "decreased";
        }

        const text = `In ${market} market, ${channelLabel} OTS ${direction} by ${formatDeltaNumber(delta)}% from ${previousWeek} to ${currentWeek}, moving from ${formatOtsNumber(previousValue)} to ${formatOtsNumber(currentValue)}.`;
        narratives.push({ market, text });
        items.push({ channel: channelLabel, market, text });
      });

      if (narratives.length) {
        groups.push({
          channel: channelLabel,
          narratives,
        });
      }
    });

    return {
      weeks,
      groups,
      items,
      message: items.length ? "" : "No OTS changes were observed for the selected channels and markets compared to the previous week.",
    };
  }

  function renderReportStatus(message) {
    if (!reportStatus) return;
    if (message) {
      reportStatus.hidden = false;
      reportStatus.textContent = message;
      return;
    }
    reportStatus.hidden = true;
    reportStatus.textContent = "";
  }

  function renderReportPanel() {
    if (!reportPanel || !reportContent) return;
    reportPanel.hidden = !state.report.open;
    reportPanel.style.display = state.report.open ? "block" : "none";
    if (reportLauncher) {
      reportLauncher.hidden = state.report.open;
      reportLauncher.style.display = state.report.open ? "none" : "flex";
    }
    if (!state.report.open) return;

    const context = getReportContext();
    syncReportSelections(context);

    updateReportMultiSelectButton(reportMarketFilter.button, state.report.markets, context.markets, "All Markets", "markets selected");
    updateReportMultiSelectButton(reportChannelFilter.button, state.report.channels, context.channels, "Default 4 Channels", "channels selected");

    renderReportOptions(reportMarketFilter, context.markets, state.report.markets, (value, checked) => {
      const next = new Set(state.report.markets);
      if (checked) next.add(value);
      else next.delete(value);
      state.report.markets = Array.from(next).sort((left, right) => left.localeCompare(right, undefined, { numeric: true }));
      renderReportPanel();
    });
    renderReportOptions(reportChannelFilter, context.channels, state.report.channels, (value, checked) => {
      const next = new Set(state.report.channels);
      if (checked) next.add(value);
      else next.delete(value);
      state.report.channels = Array.from(next).sort((left, right) => left.localeCompare(right, undefined, { numeric: true }));
      renderReportPanel();
    });

    const reportData = buildReportNarratives();
    const [previousWeek, currentWeek] = reportData.weeks;
    if (reportMeta) {
      reportMeta.textContent = previousWeek && currentWeek
        ? `Channel-wise OTS movement from ${previousWeek} to ${currentWeek}.`
        : "Select at least two visible weeks to compare OTS movement.";
    }
    if (reportCount) {
      reportCount.textContent = `${reportData.items.length} narrative${reportData.items.length === 1 ? "" : "s"}`;
    }

    renderReportStatus(reportData.message);
    if (reportData.message) {
      reportContent.innerHTML = `<div class="ots-report-empty">${reportData.message}</div>`;
      return;
    }

    const fragment = document.createDocumentFragment();
    reportData.groups.forEach((group) => {
      const section = document.createElement("section");
      section.className = "ots-report-group";

      const header = document.createElement("div");
      header.className = "ots-report-group-header";
      const titleWrap = document.createElement("div");
      const title = document.createElement("h4");
      title.textContent = group.channel;
      titleWrap.appendChild(title);
      header.appendChild(titleWrap);

      const list = document.createElement("ul");
      list.className = "ots-report-list";
      group.narratives.forEach((narrative) => {
        const item = document.createElement("li");
        item.textContent = narrative.text;
        list.appendChild(item);
      });

      section.append(header, list);
      fragment.appendChild(section);
    });
    reportContent.replaceChildren(fragment);
  }

  function resetReportFilters() {
    const context = getReportContext();
    state.report.markets = context.markets.slice();
    state.report.channels = getDefaultReportChannels(context.channels);
    renderReportPanel();
  }

  function openReportPanel() {
    const context = getReportContext();
    state.report.open = true;
    state.report.markets = context.markets.slice();
    state.report.channels = getDefaultReportChannels(context.channels);
    renderReportPanel();
    requestAnimationFrame(() => {
      reportPanel?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  function closeReportPanel() {
    state.report.open = false;
    renderReportPanel();
    requestAnimationFrame(() => {
      reportLauncher?.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  }

  function buildReportDocument() {
    const reportData = buildReportNarratives();
    const [previousWeek, currentWeek] = reportData.weeks;
    const content = reportData.message
      ? `<div class="empty">${reportData.message}</div>`
      : reportData.groups.map((group) => `
        <section class="group">
          <h2>${group.channel}</h2>
          <ul>${group.narratives.map((narrative) => `<li>${narrative.text}</li>`).join("")}</ul>
        </section>
      `).join("");
    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>OTS Change Report</title>
  <style>
    body { font-family: Arial, sans-serif; color: #1e293b; margin: 24px; }
    h1 { margin: 0 0 6px; font-size: 22px; }
    .meta { margin-bottom: 18px; color: #64748b; font-size: 13px; }
    .group { border: 1px solid #dbe4f0; border-radius: 12px; margin-bottom: 14px; overflow: hidden; }
    .group h2 { margin: 0; padding: 12px 14px; background: #f8fbff; font-size: 16px; border-bottom: 1px solid #e2e8f0; }
    ul { margin: 0; padding: 14px 18px 16px 34px; }
    li { margin: 6px 0; line-height: 1.55; font-size: 14px; }
    .empty { border: 1px dashed #cbd5e1; border-radius: 12px; padding: 16px; color: #64748b; }
  </style>
</head>
<body>
  <h1>OTS Change Report</h1>
  <div class="meta">${previousWeek && currentWeek ? `Comparison: ${previousWeek} to ${currentWeek}` : "Comparison weeks unavailable"}</div>
  ${content}
</body>
</html>`;
  }

  function downloadReport() {
    const html = buildReportDocument();
    const blob = new Blob([html], { type: "text/html;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = "ots_change_report.html";
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  function printReport() {
    const popup = window.open("", "_blank", "width=1100,height=800");
    if (!popup) return;
    popup.document.open();
    popup.document.write(buildReportDocument());
    popup.document.close();
    popup.focus();
    popup.print();
  }

  function buildStandalonePayload() {
    const source = window.__OTS_STANDALONE_DATA__;
    const allRecords = source.table?.records || source.records || [];
    const filtered = filterStandaloneRecords(allRecords, source);
    const visibleWeeks = getVisibleWeeks(source);

    function optionValues(key) {
      const scoped = allRecords.filter((record) => {
        if (key !== "markets" && state.filters.markets.length && !state.filters.markets.includes(record.market)) return false;
        if (key !== "channels" && state.filters.channels.length && !state.filters.channels.includes(record.channel)) return false;
        if (key !== "change" && state.filters.change && !matchesChangeFilter(getChangeMeta(record, visibleWeeks).type, state.filters.change)) return false;
        return true;
      });
      const field = key === "markets" ? "market" : "channel";
      return Array.from(new Set(scoped.map((record) => record[field]).filter((value) => normalizeText(value) !== ""))).sort((left, right) => left.localeCompare(right));
    }

    return {
      ...source,
      visible_weeks: visibleWeeks,
      filters: {
        markets: optionValues("markets"),
        channels: optionValues("channels"),
      },
      table: {
        records: filtered.map((record) => ({
          market: record.market,
          channel: record.channel,
          ots_values: Object.fromEntries(visibleWeeks.map((week) => [week, record.ots_values?.[week] ?? null])),
        })),
        total_count: filtered.length,
      },
    };
  }

  // Fetch the newest OTS payload for live mode, or rebuild it locally for standalone mode.
  async function fetchPayload(forceRefresh) {
    if (state.standalone) {
      render(buildStandalonePayload());
      return;
    }

    const params = new URLSearchParams();
    state.filters.markets.forEach((value) => params.append("market", value));
    state.filters.channels.forEach((value) => params.append("channel", value));
    if (state.filters.week_from) params.set("week_from", state.filters.week_from);
    if (state.filters.week_to) params.set("week_to", state.filters.week_to);
    if (state.filters.change) params.set("change", state.filters.change);
    if (forceRefresh) params.set("refresh", "1");

    setLoading(true);
    try {
      const response = await fetch(`/api/ots?${params.toString()}`);
      render(await response.json());
    } catch (error) {
      statusMessage.hidden = false;
      statusMessage.textContent = "OTS data could not be loaded.";
    } finally {
      setLoading(false);
    }
  }

  function closeMenus() {
    if (marketMenu) marketMenu.hidden = true;
    if (channelMenu) channelMenu.hidden = true;
    if (weekFromFilter?.menu) weekFromFilter.menu.hidden = true;
    if (weekToFilter?.menu) weekToFilter.menu.hidden = true;
    if (changeFilter?.menu) changeFilter.menu.hidden = true;
    if (reportMarketFilter?.menu) reportMarketFilter.menu.hidden = true;
    if (reportChannelFilter?.menu) reportChannelFilter.menu.hidden = true;
  }

  function bindMenu(button, menu) {
    if (!button || !menu) return;
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      const next = menu.hidden;
      closeMenus();
      menu.hidden = !next;
    });
  }

  function applySingleFilter(key, value) {
    state.filters[key] = value;
    if (key === "week_from" || key === "week_to") {
      const weeks = state.payload?.weeks || window.__OTS_STANDALONE_DATA__?.weeks || [];
      const fromIndex = state.filters.week_from && weeks.includes(state.filters.week_from) ? weeks.indexOf(state.filters.week_from) : -1;
      const toIndex = state.filters.week_to && weeks.includes(state.filters.week_to) ? weeks.indexOf(state.filters.week_to) : -1;
      if (fromIndex >= 0 && toIndex >= 0 && fromIndex > toIndex) {
        if (key === "week_from") state.filters.week_to = state.filters.week_from;
        else state.filters.week_from = state.filters.week_to;
      }
    }
    state.page = 1;
    fetchPayload(false);
  }

  function bindSingleSelect(control, key, placeholder, labels = null) {
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
        const values = key === "change" ? ["changed", "no_change", "increase", "decrease"] : getConstrainedWeekOptions(state.payload?.weeks || [], key);
        renderSingleSelectOptions(control, values, state.filters[key], placeholder, (value) => applySingleFilter(key, value), labels);
      });
    }
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
      document.body.classList.add("ots-fullscreen-active");
      panel.classList.add("ots-panel-fullscreen");
    } else {
      fullscreenState.tableScrollTop = tableWrap.scrollTop;
      fullscreenState.tableScrollLeft = tableWrap.scrollLeft;
      fullscreenState.active = false;
      document.body.classList.remove("ots-fullscreen-active");
      panel.classList.remove("ots-panel-fullscreen");
    }

    state.page = 1;
    render(state.payload);
    requestAnimationFrame(() => {
      if (!active) {
        window.scrollTo({ top: fullscreenState.windowScrollY, behavior: "auto" });
      }
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

  function resetFilters() {
    state.filters = {
      markets: [],
      channels: [],
      week_from: "",
      week_to: "",
      change: "",
    };
    state.page = 1;
    fetchPayload(false);
  }

  bindMenu(marketButton, marketMenu);
  bindMenu(channelButton, channelMenu);
  bindMenu(reportMarketFilter?.button, reportMarketFilter?.menu);
  bindMenu(reportChannelFilter?.button, reportChannelFilter?.menu);
  bindSingleSelect(weekFromFilter, "week_from", "From Week");
  bindSingleSelect(weekToFilter, "week_to", "To Week");
  bindSingleSelect(changeFilter, "change", "All Changes", { changed: "Changed", increase: "Increase", decrease: "Decrease", no_change: "No Change" });

  document.addEventListener("click", (event) => {
    if (!event.target.closest(".ots-multiselect") && !event.target.closest(".filter-select")) closeMenus();
  });

  if (marketSearchInput) marketSearchInput.addEventListener("input", () => renderMultiSelectOptions(marketOptions, state.payload?.filters?.markets || [], state.filters.markets, "markets", marketSearchInput.value));
  if (channelSearchInput) channelSearchInput.addEventListener("input", () => renderMultiSelectOptions(channelOptions, state.payload?.filters?.channels || [], state.filters.channels, "channels", channelSearchInput.value));
  if (reportMarketFilter?.search) reportMarketFilter.search.addEventListener("input", () => renderReportPanel());
  if (reportChannelFilter?.search) reportChannelFilter.search.addEventListener("input", () => renderReportPanel());
  if (refreshButton) refreshButton.addEventListener("click", () => fetchPayload(true));
  if (resetButton) resetButton.addEventListener("click", resetFilters);
  if (fullscreenButton) fullscreenButton.addEventListener("click", toggleFullscreen);
  if (reportToggleButton) reportToggleButton.addEventListener("click", openReportPanel);
  if (reportHideButton) reportHideButton.addEventListener("click", closeReportPanel);
  if (reportResetButton) reportResetButton.addEventListener("click", resetReportFilters);
  if (reportDownloadButton) reportDownloadButton.addEventListener("click", downloadReport);
  if (reportPrintButton) reportPrintButton.addEventListener("click", printReport);
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
        render(state.payload);
      }
    });
  }
  if (nextPageButton) {
    nextPageButton.addEventListener("click", () => {
      const totalPages = Math.max(1, Math.ceil((state.payload?.table.records || []).length / state.pageSize));
      if (state.page < totalPages) {
        state.page += 1;
        render(state.payload);
      }
    });
  }
  window.addEventListener("resize", () => {
    if (!state.payload) return;
    render(state.payload);
  });
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
  document.addEventListener("mousemove", handleColumnResize);
  document.addEventListener("mouseup", stopColumnResize);
  document.addEventListener("mouseleave", stopColumnResize);
  if (state.initial) {
    render(state.initial);
  }
  syncFullscreenButtons();
  fetchPayload(false);
})();
