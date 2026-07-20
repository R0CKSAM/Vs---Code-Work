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
      search: "",
    },
    page: 1,
    pageSize: 30,
    sortKey: "market",
    sortDirection: "asc",
    loading: false,
    standalone: Boolean(window.__OTS_STANDALONE_DATA__),
    initial: window.__OTS_INITIAL_DATA__ || null,
  };

  const marketButton = document.getElementById("otsMarketButton");
  const marketMenu = document.getElementById("otsMarketMenu");
  const marketOptions = document.getElementById("otsMarketOptions");
  const channelButton = document.getElementById("otsChannelButton");
  const channelMenu = document.getElementById("otsChannelMenu");
  const channelOptions = document.getElementById("otsChannelOptions");
  const weekFromFilter = document.getElementById("otsWeekFromFilter");
  const weekToFilter = document.getElementById("otsWeekToFilter");
  const changeFilter = document.getElementById("otsChangeFilter");
  const searchInput = document.getElementById("otsSearchInput");
  const resultCount = document.getElementById("otsResultCount");
  const tableHead = document.getElementById("otsTableHead");
  const tableBody = document.getElementById("otsTableBody");
  const statusMessage = document.getElementById("otsStatusMessage");
  const refreshButton = document.getElementById("otsRefreshButton");
  const resetButton = document.getElementById("otsResetButton");
  const fullscreenButton = document.getElementById("otsFullscreenButton");
  const exitFullscreenButton = document.getElementById("otsExitFullscreenButton");
  const exportExcelButton = document.getElementById("otsExportExcelButton");
  const exportCsvButton = document.getElementById("otsExportCsvButton");
  const prevPageButton = document.getElementById("otsPrevPage");
  const nextPageButton = document.getElementById("otsNextPage");
  const pageInfo = document.getElementById("otsPageInfo");
  const tableWrap = root.closest(".ots-table-wrap");
  const panel = root.closest(".ots-panel");

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

  function createOption(value, label) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    return option;
  }

  function normalizeText(value) {
    return String(value || "").trim();
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
    const startIndex = state.filters.week_from && allWeeks.includes(state.filters.week_from) ? allWeeks.indexOf(state.filters.week_from) : 0;
    const endIndex = state.filters.week_to && allWeeks.includes(state.filters.week_to) ? allWeeks.indexOf(state.filters.week_to) : allWeeks.length - 1;
    const from = Math.min(startIndex, endIndex);
    const to = Math.max(startIndex, endIndex);
    return allWeeks.slice(from, to + 1);
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

  // Apply the standalone filters locally so exported HTML behaves like the live server.
  function filterStandaloneRecords(records, payload) {
    const visibleWeeks = getVisibleWeeks(payload);
    const search = normalizeText(state.filters.search).toLowerCase();
    return records.filter((record) => {
      if (state.filters.markets.length && !state.filters.markets.includes(record.market)) return false;
      if (state.filters.channels.length && !state.filters.channels.includes(record.channel)) return false;
      if (search && !`${record.market} ${record.channel}`.toLowerCase().includes(search)) return false;
      if (state.filters.change) {
        if (getChangeMeta(record, visibleWeeks).type !== state.filters.change) return false;
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
  function renderMultiSelectOptions(container, values, selectedValues, key) {
    if (!container) return;
    const selected = new Set(selectedValues);
    const fragment = document.createDocumentFragment();

    values.forEach((value) => {
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

  function populateSelect(select, values, label, selectedValue) {
    const safeValues = Array.isArray(values) ? values.filter((value) => normalizeText(value) !== "") : [];
    const fallback = safeValues.includes(selectedValue) ? selectedValue : "";
    select.innerHTML = "";
    select.appendChild(createOption("", label));
    safeValues.forEach((value) => select.appendChild(createOption(value, value)));
    select.value = fallback;
    return fallback;
  }

  function populateMappedSelect(select, values, labels, placeholder, selectedValue) {
    const safeValues = Array.isArray(values) ? values.filter((value) => normalizeText(value) !== "") : [];
    const fallback = safeValues.includes(selectedValue) ? selectedValue : "";
    select.innerHTML = "";
    select.appendChild(createOption("", placeholder));
    safeValues.forEach((value) => select.appendChild(createOption(value, labels[value] || value)));
    select.value = fallback;
    return fallback;
  }

  // Sync all OTS filters from the newest payload while preserving current selections when possible.
  function syncControls(payload) {
    const filterData = payload.filters || {};
    renderMultiSelectOptions(marketOptions, filterData.markets || [], state.filters.markets, "markets");
    renderMultiSelectOptions(channelOptions, filterData.channels || [], state.filters.channels, "channels");
    state.filters.markets = state.filters.markets.filter((value) => (filterData.markets || []).includes(value));
    state.filters.channels = state.filters.channels.filter((value) => (filterData.channels || []).includes(value));
    updateMultiSelectButton(marketButton, state.filters.markets, "All Markets", "markets selected");
    updateMultiSelectButton(channelButton, state.filters.channels, "All Channels", "channels selected");
    state.filters.week_from = populateSelect(weekFromFilter, payload.weeks || [], "From Week", state.filters.week_from);
    state.filters.week_to = populateSelect(weekToFilter, payload.weeks || [], "To Week", state.filters.week_to);
    state.filters.change = populateMappedSelect(
      changeFilter,
      ["increase", "decrease", "no_change"],
      { increase: "Increase", decrease: "Decrease", no_change: "No Change" },
      "All Changes",
      state.filters.change
    );
    if (searchInput) {
      searchInput.value = state.filters.search;
    }
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

    weeks.forEach((week) => {
      const td = document.createElement("td");
      td.textContent = formatOtsValue(record.ots_values?.[week]);
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
  }

  function buildStandalonePayload() {
    const source = window.__OTS_STANDALONE_DATA__;
    const allRecords = source.table?.records || source.records || [];
    const filtered = filterStandaloneRecords(allRecords, source);
    const visibleWeeks = getVisibleWeeks(source);

    function optionValues(key) {
      const scoped = allRecords.filter((record) => {
        const search = normalizeText(state.filters.search).toLowerCase();
        if (search && !`${record.market} ${record.channel}`.toLowerCase().includes(search)) return false;
        if (key !== "markets" && state.filters.markets.length && !state.filters.markets.includes(record.market)) return false;
        if (key !== "channels" && state.filters.channels.length && !state.filters.channels.includes(record.channel)) return false;
        if (key !== "change" && state.filters.change && getChangeMeta(record, visibleWeeks).type !== state.filters.change) return false;
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
    if (state.filters.search) params.set("search", state.filters.search);
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

  function buildExportQuery() {
    const params = new URLSearchParams();
    state.filters.markets.forEach((value) => params.append("market", value));
    state.filters.channels.forEach((value) => params.append("channel", value));
    if (state.filters.week_from) params.set("week_from", state.filters.week_from);
    if (state.filters.week_to) params.set("week_to", state.filters.week_to);
    if (state.filters.change) params.set("change", state.filters.change);
    if (state.filters.search) params.set("search", state.filters.search);
    return params.toString();
  }

  function exportStandaloneCsv() {
    const payload = state.payload;
    const weeks = payload.visible_weeks || [];
    const rows = sortRecords(payload.table.records || [], weeks);
    const lines = [[ "Market", "Channel", ...weeks, "Change" ]];
    rows.forEach((record) => {
      lines.push([
        record.market,
        record.channel,
        ...weeks.map((week) => formatOtsValue(record.ots_values?.[week])),
        getChangeMeta(record, weeks).text,
      ]);
    });
    const csv = lines
      .map((row) => row.map((cell) => `"${String(cell ?? "").replace(/"/g, '""')}"`).join(","))
      .join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "ots_comparison.csv";
    link.click();
    URL.revokeObjectURL(link.href);
  }

  function exportStandaloneExcel() {
    const payload = state.payload;
    const weeks = payload.visible_weeks || [];
    const rows = sortRecords(payload.table.records || [], weeks);
    const html = `
      <table>
        <tr><th>Market</th><th>Channel</th>${weeks.map((week) => `<th>${week}</th>`).join("")}<th>Change</th></tr>
        ${rows
          .map(
            (record) =>
              `<tr><td>${record.market}</td><td>${record.channel}</td>${weeks.map((week) => `<td>${formatOtsValue(record.ots_values?.[week])}</td>`).join("")}<td>${getChangeMeta(record, weeks).text}</td></tr>`
          )
          .join("")}
      </table>`;
    const blob = new Blob([html], { type: "application/vnd.ms-excel" });
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = "ots_comparison.xls";
    link.click();
    URL.revokeObjectURL(link.href);
  }

  function resetFilters() {
    state.filters = {
      markets: [],
      channels: [],
      week_from: "",
      week_to: "",
      change: "",
      search: "",
    };
    state.page = 1;
    fetchPayload(false);
  }

  bindMenu(marketButton, marketMenu);
  bindMenu(channelButton, channelMenu);

  document.addEventListener("click", (event) => {
    if (!event.target.closest(".ots-multiselect")) closeMenus();
  });

  if (weekFromFilter) {
    weekFromFilter.addEventListener("change", () => {
      state.filters.week_from = weekFromFilter.value;
      state.page = 1;
      fetchPayload(false);
    });
  }
  if (weekToFilter) {
    weekToFilter.addEventListener("change", () => {
      state.filters.week_to = weekToFilter.value;
      state.page = 1;
      fetchPayload(false);
    });
  }
  if (changeFilter) {
    changeFilter.addEventListener("change", () => {
      state.filters.change = changeFilter.value;
      state.page = 1;
      fetchPayload(false);
    });
  }
  if (searchInput) {
    searchInput.addEventListener("input", () => {
      state.filters.search = searchInput.value;
      state.page = 1;
      fetchPayload(false);
    });
  }
  if (refreshButton) refreshButton.addEventListener("click", () => fetchPayload(true));
  if (resetButton) resetButton.addEventListener("click", resetFilters);
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
  if (exportExcelButton) {
    exportExcelButton.addEventListener("click", () => {
      if (state.standalone) {
        exportStandaloneExcel();
        return;
      }
      window.location.href = `/download/ots/excel?${buildExportQuery()}`;
    });
  }
  if (exportCsvButton) {
    exportCsvButton.addEventListener("click", () => {
      if (state.standalone) {
        exportStandaloneCsv();
        return;
      }
      window.location.href = `/download/ots/csv?${buildExportQuery()}`;
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

  if (state.initial) {
    render(state.initial);
  }
  syncFullscreenButtons();
  fetchPayload(false);
})();
