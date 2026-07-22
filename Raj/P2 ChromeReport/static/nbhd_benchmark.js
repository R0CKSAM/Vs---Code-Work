(function () {
  const root = document.getElementById("nbhdBenchmarkTable");
  if (!root) return;

  const source = window.__NBHD_BENCHMARK_INITIAL_DATA__
    || window.__CHROME_REPORT_DATA__?.nbhd_benchmark
    || {
      generated_at: "",
      weeks: [],
      records: [],
      message: "INDIA TV comparison data could not be loaded.",
    };

  const columns = [
    { key: "market", label: "Market", type: "text" },
    { key: "city", label: "City", type: "text" },
    { key: "head_end", label: "Headend", type: "text" },
    { key: "channel", label: "Channel", type: "text" },
    { key: "india_frequency", label: "INDIA TV Frequency", type: "number" },
    { key: "channel_frequency", label: "Channel Frequency", type: "number" },
    { key: "difference", label: "Difference from INDIA TV", type: "change" },
    { key: "previous_difference", label: "Previous Week Difference", type: "change" },
    { key: "difference_change", label: "Difference Change", type: "change" },
    { key: "status", label: "Status", type: "status" },
  ];

  const DEFAULT_COLUMN_WIDTHS = {
    market: 190,
    city: 140,
    head_end: 220,
    channel: 170,
    india_frequency: 150,
    channel_frequency: 145,
    difference: 165,
    previous_difference: 170,
    difference_change: 145,
    status: 90,
  };

  const MIN_COLUMN_WIDTH = 88;

  const state = {
    filters: {
      market: "",
      city: "",
      head_end: "",
      week: "",
    },
    sortKey: "difference_change",
    sortDirection: "desc",
    page: 1,
    pageSize: 25,
    columnWidths: {},
  };

  let activeResize = null;

  function getSingleSelectControl(id) {
    return {
      button: document.getElementById(id),
      menu: document.getElementById(`${id}Menu`),
      search: document.getElementById(`${id}Search`),
      options: document.getElementById(`${id}Options`),
    };
  }

  const marketFilter = getSingleSelectControl("nbhdBenchmarkMarketFilter");
  const cityFilter = getSingleSelectControl("nbhdBenchmarkCityFilter");
  const headendFilter = getSingleSelectControl("nbhdBenchmarkHeadendFilter");
  const weekFilter = getSingleSelectControl("nbhdBenchmarkWeekFilter");
  const resetButton = document.getElementById("nbhdBenchmarkResetButton");
  const fullscreenButton = document.getElementById("nbhdBenchmarkFullscreenButton");
  const exitFullscreenButton = document.getElementById("nbhdBenchmarkExitFullscreenButton");
  const prevPageButton = document.getElementById("nbhdBenchmarkPrevPage");
  const nextPageButton = document.getElementById("nbhdBenchmarkNextPage");
  const resultCount = document.getElementById("nbhdBenchmarkResultCount");
  const pageInfo = document.getElementById("nbhdBenchmarkPageInfo");
  const statusMessage = document.getElementById("nbhdBenchmarkStatusMessage");
  const tableHead = document.getElementById("nbhdBenchmarkTableHead");
  const tableBody = document.getElementById("nbhdBenchmarkTableBody");
  const tableWrap = root.closest(".nbhd-benchmark-table-wrap");
  const panel = root.closest(".nbhd-benchmark-panel");

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

  function toChannelKey(value) {
    return normalizeText(value).toUpperCase();
  }

  function uniqueValues(values) {
    return Array.from(new Set((values || []).map((value) => normalizeText(value)).filter(Boolean)));
  }

  function sortWeekLabels(values) {
    return values.slice().sort((left, right) => left.localeCompare(right, undefined, { numeric: true }));
  }

  function availableWeeks() {
    return sortWeekLabels(uniqueValues(source.weeks || []));
  }

  function ensureWeekSelection() {
    if (state.filters.week) return;
    const weeks = availableWeeks();
    if (weeks.length) state.filters.week = weeks[weeks.length - 1];
  }

  function getPreviousWeek(currentWeek) {
    const weeks = availableWeeks();
    const index = weeks.indexOf(currentWeek);
    if (index <= 0) return "";
    return weeks[index - 1];
  }

  function currentWeekLabel() {
    ensureWeekSelection();
    return state.filters.week;
  }

  function previousWeekLabel() {
    return getPreviousWeek(currentWeekLabel());
  }

  function allRecords() {
    return Array.isArray(source.records) ? source.records : [];
  }

  function rowMatches(row, ignoreKey = "") {
    if (ignoreKey !== "market" && state.filters.market && row.market !== state.filters.market) return false;
    if (ignoreKey !== "city" && state.filters.city && row.city !== state.filters.city) return false;
    if (ignoreKey !== "head_end" && state.filters.head_end && row.head_end !== state.filters.head_end) return false;
    return true;
  }

  function getFilterOptions(key) {
    const records = allRecords().filter((row) => rowMatches(row, key));
    return uniqueValues(records.map((row) => row[key])).sort((left, right) => left.localeCompare(right, undefined, { numeric: true }));
  }

  function updateSingleSelectButton(control, value, placeholder) {
    if (control?.button) control.button.textContent = value || placeholder;
  }

  function closeMenus(exceptControl = null) {
    [marketFilter, cityFilter, headendFilter, weekFilter].forEach((control) => {
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
    state.filters.head_end = syncSingleSelect(headendFilter, getFilterOptions("head_end"), "Select Headend", state.filters.head_end, (value) => applyFilter("head_end", value));
    state.filters.week = syncSingleSelect(weekFilter, availableWeeks(), "Select Week", state.filters.week, (value) => applyFilter("week", value));
  }

  function formatNumberValue(value) {
    if (isMissing(value)) return "NA";
    const numeric = Number(value);
    if (Number.isNaN(numeric)) return String(value);
    return Number.isInteger(numeric) ? String(numeric) : numeric.toFixed(2);
  }

  function formatSignedValue(value) {
    if (isMissing(value)) return "NA";
    const numeric = Number(value);
    if (Number.isNaN(numeric)) return String(value);
    const absolute = Number.isInteger(numeric) ? String(Math.abs(numeric)) : Math.abs(numeric).toFixed(2);
    if (numeric > 0) return `+${absolute}`;
    if (numeric < 0) return `-${absolute}`;
    return "0";
  }

  function differenceMeta(previousValue, currentValue, indiaRow) {
    if (indiaRow) return { text: "0", type: "neutral", sortValue: 0, rawValue: 0 };
    if (isMissing(previousValue) && isMissing(currentValue)) return { text: "NA", type: "neutral", sortValue: 0, rawValue: null };
    if (isMissing(previousValue) && !isMissing(currentValue)) {
      const amount = Number(currentValue) || 0;
      return { text: `+${formatNumberValue(currentValue)}`, type: "positive", sortValue: amount || 1, rawValue: amount };
    }
    if (!isMissing(previousValue) && isMissing(currentValue)) {
      const amount = Number(previousValue) || 0;
      return { text: `-${formatNumberValue(previousValue)}`, type: "negative", sortValue: -(amount || 1), rawValue: -amount };
    }
    const delta = Number(currentValue) - Number(previousValue);
    if (delta > 0) return { text: formatSignedValue(delta), type: "positive", sortValue: delta, rawValue: delta };
    if (delta < 0) return { text: formatSignedValue(delta), type: "negative", sortValue: delta, rawValue: delta };
    return { text: "0", type: "neutral", sortValue: 0, rawValue: 0 };
  }

  function changeMeta(previousValue, currentValue, indiaRow) {
    if (indiaRow) return { text: "0", type: "neutral", sortValue: 0, rawValue: 0 };
    if (previousValue === null && currentValue === null) return { text: "NA", type: "neutral", sortValue: 0, rawValue: null };
    if (previousValue === null && currentValue !== null) {
      const amount = Number(currentValue) || 0;
      return { text: `+${formatNumberValue(currentValue)}`, type: "positive", sortValue: amount || 1, rawValue: amount };
    }
    if (previousValue !== null && currentValue === null) {
      const amount = Number(previousValue) || 0;
      return { text: `-${formatNumberValue(previousValue)}`, type: "negative", sortValue: -(amount || 1), rawValue: -amount };
    }
    const delta = Number(currentValue) - Number(previousValue);
    if (delta > 0) return { text: formatSignedValue(delta), type: "positive", sortValue: delta, rawValue: delta };
    if (delta < 0) return { text: formatSignedValue(delta), type: "negative", sortValue: delta, rawValue: delta };
    return { text: "0", type: "neutral", sortValue: 0, rawValue: 0 };
  }

  function statusMeta(change) {
    if (!change || change.rawValue === null || change.rawValue === 0) return { text: "-", type: "neutral", sortValue: 0 };
    if (change.rawValue > 0) return { text: "▲", type: "positive", sortValue: change.rawValue };
    return { text: "▼", type: "negative", sortValue: change.rawValue };
  }

  function filteredBaseRecords() {
    return allRecords().filter((row) => rowMatches(row));
  }

  function buildBenchmarkRows() {
    const week = currentWeekLabel();
    const previousWeek = previousWeekLabel();
    const records = filteredBaseRecords();
    if (!state.filters.head_end) return [];

    const indiaRow = records.find((record) => toChannelKey(record.channel) === "INDIA TV");
    if (!indiaRow) return [];

    return records.map((record) => {
      const currentIndia = indiaRow.frequencies?.[week];
      const currentChannel = record.frequencies?.[week];
      const previousIndia = previousWeek ? indiaRow.frequencies?.[previousWeek] : null;
      const previousChannel = previousWeek ? record.frequencies?.[previousWeek] : null;
      const isIndia = toChannelKey(record.channel) === "INDIA TV";

      const difference = differenceMeta(currentIndia, currentChannel, isIndia);
      const previousDifference = previousWeek ? differenceMeta(previousIndia, previousChannel, isIndia) : { text: "NA", type: "neutral", sortValue: 0, rawValue: null };
      const differenceChange = previousWeek ? changeMeta(previousDifference.rawValue, difference.rawValue, isIndia) : { text: "NA", type: "neutral", sortValue: 0, rawValue: null };
      const status = statusMeta(differenceChange);

      return {
        market: record.market,
        city: record.city,
        head_end: record.head_end,
        channel: record.channel,
        india_frequency: currentIndia,
        channel_frequency: currentChannel,
        difference,
        previous_difference: previousDifference,
        difference_change: differenceChange,
        status,
        isIndia,
      };
    });
  }

  function currentStatusMessage() {
    if (source.message) return source.message;
    if (!state.filters.head_end) return "Select a headend to view the INDIA TV comparison.";
    if (!currentWeekLabel()) return "No week data is available.";
    if (!previousWeekLabel()) return "Previous week data is not available.";
    if (!filteredBaseRecords().some((record) => toChannelKey(record.channel) === "INDIA TV")) {
      return "INDIA TV is not available for the selected headend.";
    }
    return "";
  }

  function compareValues(left, right, direction) {
    const leftText = normalizeText(left).toLowerCase();
    const rightText = normalizeText(right).toLowerCase();
    return direction === "asc"
      ? leftText.localeCompare(rightText, undefined, { numeric: true })
      : rightText.localeCompare(leftText, undefined, { numeric: true });
  }

  function sortedRows() {
    const rows = buildBenchmarkRows();
    const direction = state.sortDirection === "asc" ? "asc" : "desc";
    return rows.sort((left, right) => {
      if (left.isIndia && !right.isIndia) return -1;
      if (!left.isIndia && right.isIndia) return 1;

      let comparison = 0;
      if (["difference", "previous_difference", "difference_change", "status"].includes(state.sortKey)) {
        const leftValue = state.sortKey === "status" ? left.status.sortValue : left[state.sortKey].sortValue;
        const rightValue = state.sortKey === "status" ? right.status.sortValue : right[state.sortKey].sortValue;
        comparison = direction === "asc" ? leftValue - rightValue : rightValue - leftValue;
      } else if (["india_frequency", "channel_frequency"].includes(state.sortKey)) {
        const leftValue = isMissing(left[state.sortKey]) ? Number.NEGATIVE_INFINITY : Number(left[state.sortKey]);
        const rightValue = isMissing(right[state.sortKey]) ? Number.NEGATIVE_INFINITY : Number(right[state.sortKey]);
        comparison = direction === "asc" ? leftValue - rightValue : rightValue - leftValue;
      } else {
        comparison = compareValues(left[state.sortKey], right[state.sortKey], direction);
      }

      if (comparison !== 0) return comparison;
      return compareValues(left.channel, right.channel, "asc");
    });
  }

  function getColumnWidth(columnKey) {
    return state.columnWidths[columnKey] || DEFAULT_COLUMN_WIDTHS[columnKey] || 120;
  }

  function setColumnWidth(columnKey, width) {
    state.columnWidths[columnKey] = Math.max(MIN_COLUMN_WIDTH, Math.round(width));
    buildHeader();
    renderTableBody();
  }

  function stopColumnResize() {
    if (!activeResize) return;
    activeResize.handle?.classList.remove("active");
    activeResize = null;
    document.body.classList.remove("nbhd-benchmark-resizing");
  }

  function handleColumnResize(event) {
    if (!activeResize) return;
    const delta = event.clientX - activeResize.startX;
    setColumnWidth(activeResize.columnKey, activeResize.startWidth + delta);
  }

  function startColumnResize(event, columnKey, handle) {
    event.preventDefault();
    event.stopPropagation();
    activeResize = {
      columnKey,
      startX: event.clientX,
      startWidth: state.columnWidths[columnKey] || handle.closest("th")?.getBoundingClientRect().width || getColumnWidth(columnKey),
      handle,
    };
    handle.classList.add("active");
    document.body.classList.add("nbhd-benchmark-resizing");
  }

  function buildHeader() {
    const row = document.createElement("tr");
    const week = currentWeekLabel();
    columns.forEach((column) => {
      const th = document.createElement("th");
      th.className = `nbhd-benchmark-sortable ${column.type === "text" ? "nbhd-benchmark-text" : "nbhd-benchmark-number"}`;
      th.style.width = `${getColumnWidth(column.key)}px`;
      th.style.minWidth = `${getColumnWidth(column.key)}px`;
      th.style.maxWidth = `${getColumnWidth(column.key)}px`;

      const label = document.createElement("span");
      if (column.key === "india_frequency") {
        label.textContent = `${column.label} (${week || "-"})`;
      } else if (column.key === "channel_frequency") {
        label.textContent = `${column.label} (${week || "-"})`;
      } else {
        label.textContent = column.label;
      }
      if (state.sortKey === column.key) {
        label.textContent += state.sortDirection === "asc" ? " ▲" : " ▼";
      }

      const handle = document.createElement("span");
      handle.className = "nbhd-benchmark-resize-handle";
      handle.title = "Drag to resize column";
      handle.addEventListener("mousedown", (event) => startColumnResize(event, column.key, handle));

      th.append(label, handle);
      th.addEventListener("click", () => {
        if (state.sortKey === column.key) {
          state.sortDirection = state.sortDirection === "asc" ? "desc" : "asc";
        } else {
          state.sortKey = column.key;
          state.sortDirection = column.type === "text" ? "asc" : "desc";
        }
        state.page = 1;
        renderTableBody();
        buildHeader();
      });
      row.appendChild(th);
    });
    tableHead.replaceChildren(row);
  }

  function buildCell(row, column) {
    const td = document.createElement("td");
    td.style.width = `${getColumnWidth(column.key)}px`;
    td.style.minWidth = `${getColumnWidth(column.key)}px`;
    td.style.maxWidth = `${getColumnWidth(column.key)}px`;

    if (column.type === "text") {
      td.className = "nbhd-benchmark-text";
      td.textContent = row[column.key];
      return td;
    }

    if (column.type === "number") {
      const value = row[column.key];
      td.className = `nbhd-benchmark-number${isMissing(value) ? " nbhd-benchmark-na" : ""}`;
      td.textContent = formatNumberValue(value);
      return td;
    }

    if (column.type === "change") {
      const meta = row[column.key];
      td.className = `nbhd-benchmark-number nbhd-benchmark-${meta.type}`;
      if (meta.text === "NA") td.classList.add("nbhd-benchmark-na");
      td.textContent = meta.text;
      return td;
    }

    td.className = `nbhd-benchmark-status-cell nbhd-benchmark-${row.status.type}`;
    td.textContent = row.status.text;
    return td;
  }

  function buildRow(row) {
    const tr = document.createElement("tr");
    if (row.isIndia) tr.className = "nbhd-benchmark-india-row";
    columns.forEach((column) => tr.appendChild(buildCell(row, column)));
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

  function renderTableBody() {
    const rows = sortedRows();
    resultCount.textContent = `${new Intl.NumberFormat().format(rows.length)} rows`;

    const totalPages = Math.max(1, Math.ceil(rows.length / state.pageSize));
    if (state.page > totalPages) state.page = totalPages;
    const pageRows = rows.slice((state.page - 1) * state.pageSize, state.page * state.pageSize);

    pageInfo.textContent = `Page ${state.page} of ${totalPages}`;
    if (prevPageButton) prevPageButton.disabled = state.page <= 1;
    if (nextPageButton) nextPageButton.disabled = state.page >= totalPages;

    if (!pageRows.length) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = columns.length;
      td.className = "empty-state";
      td.textContent = currentStatusMessage() || "No INDIA TV comparison rows match the current filters.";
      tr.appendChild(td);
      tableBody.replaceChildren(tr);
      return;
    }

    const fragment = document.createDocumentFragment();
    pageRows.forEach((row) => fragment.appendChild(buildRow(row)));
    tableBody.replaceChildren(fragment);
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
      document.body.classList.add("nbhd-benchmark-fullscreen-active");
      panel.classList.add("nbhd-benchmark-panel-fullscreen");
    } else {
      fullscreenState.tableScrollTop = tableWrap.scrollTop;
      fullscreenState.tableScrollLeft = tableWrap.scrollLeft;
      fullscreenState.active = false;
      document.body.classList.remove("nbhd-benchmark-fullscreen-active");
      panel.classList.remove("nbhd-benchmark-panel-fullscreen");
    }
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
      fullscreenState.usingNativeFullscreen = false;
      return true;
    } catch (_error) {
      return false;
    }
  }

  async function toggleFullscreen() {
    if (!fullscreenState.active) {
      const usedNative = await enterNativeFullscreen();
      if (!usedNative) setFullscreen(true);
      else syncFullscreenButtons();
      return;
    }
    if (fullscreenState.usingNativeFullscreen) {
      const exited = await exitNativeFullscreen();
      if (!exited) setFullscreen(false);
      return;
    }
    setFullscreen(false);
  }

  function render() {
    syncControls();
    renderStatus();
    buildHeader();
    renderTableBody();
  }

  bindSingleSelect(marketFilter, "market", "All Markets");
  bindSingleSelect(cityFilter, "city", "All Cities");
  bindSingleSelect(headendFilter, "head_end", "Select Headend");
  bindSingleSelect(weekFilter, "week", "Select Week");

  resetButton?.addEventListener("click", () => {
    state.filters.market = "";
    state.filters.city = "";
    state.filters.head_end = "";
    state.filters.week = availableWeeks().slice(-1)[0] || "";
    state.sortKey = "difference_change";
    state.sortDirection = "desc";
    state.page = 1;
    render();
  });

  fullscreenButton?.addEventListener("click", toggleFullscreen);
  exitFullscreenButton?.addEventListener("click", toggleFullscreen);
  prevPageButton?.addEventListener("click", () => {
    if (state.page > 1) {
      state.page -= 1;
      renderTableBody();
    }
  });
  nextPageButton?.addEventListener("click", () => {
    const totalPages = Math.max(1, Math.ceil(sortedRows().length / state.pageSize));
    if (state.page < totalPages) {
      state.page += 1;
      renderTableBody();
    }
  });

  document.addEventListener("click", () => closeMenus());
  document.addEventListener("mousemove", handleColumnResize);
  document.addEventListener("mouseup", stopColumnResize);
  document.addEventListener("mouseleave", stopColumnResize);
  document.addEventListener("fullscreenchange", () => {
    const isPanelFullscreen = document.fullscreenElement === panel;
    fullscreenState.usingNativeFullscreen = isPanelFullscreen;
    if (isPanelFullscreen && !fullscreenState.active) {
      setFullscreen(true);
    } else if (!isPanelFullscreen && fullscreenState.active && fullscreenState.usingNativeFullscreen === false) {
      setFullscreen(false);
    }
  });

  window.addEventListener("resize", () => render());

  render();
})();
