(function () {
  const root = document.getElementById("nbhdWeekwiseTable");
  if (!root) return;

  const source = window.__NBHD_WEEKWISE_INITIAL_DATA__ || window.__CHROME_REPORT_DATA__?.nbhd_weekwise || {
    generated_at: "",
    weeks: [],
    columns: [],
    column_labels: {},
    records: [],
    message: "Week-wise neighbourhood comparison data could not be loaded.",
  };

  const DEFAULT_COLUMNS = [
    "week", "market", "city", "head_end",
    "c1", "c2", "c3", "c4", "c5", "c6", "c7", "c8", "c9",
    "genre1", "genre2", "genre3", "genre4", "genre5", "genre6", "genre7", "genre8", "genre9",
  ];
  const DEFAULT_LABELS = {
    week: "Week No",
    market: "Market",
    city: "City",
    head_end: "Headend",
    c1: "Channel 1",
    c2: "Channel 2",
    c3: "Channel 3",
    c4: "Channel 4",
    c5: "Channel 5",
    c6: "Channel 6",
    c7: "Channel 7",
    c8: "Channel 8",
    c9: "Channel 9",
    genre1: "Genre 1",
    genre2: "Genre 2",
    genre3: "Genre 3",
    genre4: "Genre 4",
    genre5: "Genre 5",
    genre6: "Genre 6",
    genre7: "Genre 7",
    genre8: "Genre 8",
    genre9: "Genre 9",
  };
  const DEFAULT_WIDTHS = {
    week: 102,
    market: 190,
    city: 126,
    head_end: 220,
    c1: 118, c2: 118, c3: 118, c4: 118, c5: 118, c6: 118, c7: 118, c8: 118, c9: 118,
    genre1: 112, genre2: 112, genre3: 112, genre4: 112, genre5: 112, genre6: 112, genre7: 112, genre8: 112, genre9: 112,
  };
  const STICKY_COLUMNS = ["week", "market", "city", "head_end"];
  const CHANNEL_COLUMNS = ["c1", "c2", "c3", "c4", "c5", "c6", "c7", "c8", "c9"];
  const GENRE_COLUMNS = ["genre1", "genre2", "genre3", "genre4", "genre5", "genre6", "genre7", "genre8", "genre9"];
  const BATCH_SIZE = 150;
  const LOAD_THRESHOLD = 260;

  const columns = Array.isArray(source.columns) && source.columns.length ? source.columns : DEFAULT_COLUMNS;
  const labels = { ...DEFAULT_LABELS, ...(source.column_labels || {}) };
  const records = Array.isArray(source.records) ? source.records : [];
  const allValuesByColumn = {};
  columns.forEach((column) => {
    allValuesByColumn[column] = allValuesForSourceColumn(column);
  });

  const state = {
    filters: {},
    searches: {},
    openColumn: "",
    renderedCount: BATCH_SIZE,
    loadingMore: false,
    menuAnchor: null,
    searchTimers: {},
    cache: {
      signature: "",
      filteredRows: [],
      channelHeaders: {},
      availableValuesByColumn: {},
    },
  };

  const tableHead = document.getElementById("nbhdWeekwiseTableHead");
  const tableBody = document.getElementById("nbhdWeekwiseTableBody");
  const resultCount = document.getElementById("nbhdWeekwiseResultCount");
  const totalCount = document.getElementById("nbhdWeekwiseTotalCount");
  const activeFiltersSummary = document.getElementById("nbhdWeekwiseActiveFilters");
  const metaLine = document.getElementById("nbhdWeekwiseMeta");
  const pageInfo = document.getElementById("nbhdWeekwisePageInfo");
  const loadState = document.getElementById("nbhdWeekwiseLoadState");
  const resetButton = document.getElementById("nbhdWeekwiseResetButton");
  const downloadButton = document.getElementById("nbhdWeekwiseDownloadButton");
  const hideButton = document.getElementById("nbhdWeekwiseHideButton");
  const fullscreenButton = document.getElementById("nbhdWeekwiseFullscreenButton");
  const exitFullscreenButton = document.getElementById("nbhdWeekwiseExitFullscreenButton");
  const toggleButton = document.getElementById("nbhdWeekwiseToggleButton");
  const statusMessage = document.getElementById("nbhdWeekwiseStatusMessage");
  const panel = document.getElementById("nbhdWeekwisePanel") || root.closest(".nbhd-weekwise-panel");
  const tableWrap = root.closest(".nbhd-weekwise-table-wrap");

  const fullscreenState = {
    active: false,
    usingNativeFullscreen: false,
    windowScrollY: 0,
    tableScrollTop: 0,
    tableScrollLeft: 0,
  };

  const floatingMenu = document.createElement("div");
  floatingMenu.className = "nbhd-weekwise-floating-menu";
  floatingMenu.hidden = true;
  (panel || document.body).appendChild(floatingMenu);

  function normalizeText(value) {
    return String(value ?? "").trim();
  }

  function getColumnValue(row, key) {
    return normalizeText(row?.[key]);
  }

  function isWeekLabel(value) {
    return /^wk-\d{1,2}'\d{2}$/i.test(normalizeText(value));
  }

  function parseWeekKey(value) {
    const match = normalizeText(value).match(/^wk-(\d{1,2})'(\d{2})$/i);
    if (!match) return Number.NEGATIVE_INFINITY;
    return Number(match[2]) * 100 + Number(match[1]);
  }

  function sortValues(values, key = "") {
    return values.slice().sort((left, right) => {
      if (key === "week" || (key === "" && isWeekLabel(left) && isWeekLabel(right))) {
        return parseWeekKey(left) - parseWeekKey(right);
      }
      return left.localeCompare(right, undefined, { numeric: true, sensitivity: "base" });
    });
  }

  function allValuesForSourceColumn(key) {
    return sortValues(
      Array.from(new Set(
        records
          .map((row) => getColumnValue(row, key))
          .filter((value) => value !== "")
      )),
      key,
    );
  }

  function latestWeek() {
    const weeks = source.weeks?.length ? source.weeks.filter(Boolean) : allValuesForSourceColumn("week");
    const sorted = sortValues(weeks, "week");
    return sorted[sorted.length - 1] || "";
  }

  function defaultFilters() {
    const latest = latestWeek();
    const filters = {};
    columns.forEach((column) => {
      filters[column] = null;
    });
    filters.week = latest ? new Set([latest]) : null;
    return filters;
  }

  function getSelectedSet(key) {
    return state.filters[key];
  }

  function selectedCount(key) {
    const selected = getSelectedSet(key);
    if (selected === null) return null;
    return selected.size;
  }

  function activeFilterCount() {
    return columns.reduce((count, key) => count + (getSelectedSet(key) === null ? 0 : 1), 0);
  }

  function filterSignature() {
    return columns.map((column) => {
      const selected = getSelectedSet(column);
      if (selected === null) return `${column}:ALL`;
      return `${column}:${Array.from(selected).sort((left, right) => left.localeCompare(right, undefined, { sensitivity: "base" })).join("||")}`;
    }).join("::");
  }

  function selectedSummaryText(key) {
    const selected = getSelectedSet(key);
    if (selected === null) return "All";
    if (!selected.size) return "0 selected";
    if (selected.size === 1) {
      return `${Array.from(selected)[0]}`;
    }
    return `${selected.size} selected`;
  }

  function rowMatches(row, ignoreKey = "") {
    return columns.every((column) => {
      if (column === ignoreKey) return true;
      const selected = getSelectedSet(column);
      if (selected === null) return true;
      if (!selected.size) return false;
      return selected.has(getColumnValue(row, column));
    });
  }

  function recomputeCache() {
    const signature = filterSignature();
    if (state.cache.signature === signature) {
      return state.cache;
    }

    const filtered = records.filter((row) => rowMatches(row));
    const channelHeaders = {};
    const availableValuesByColumn = {};

    columns.forEach((column) => {
      const valueSet = new Set();
      records.forEach((row) => {
        if (!rowMatches(row, column)) return;
        const value = getColumnValue(row, column);
        if (value) valueSet.add(value);
      });
      availableValuesByColumn[column] = valueSet;
    });

    CHANNEL_COLUMNS.forEach((column) => {
      const counts = new Map();
      filtered.forEach((row) => {
        const value = getColumnValue(row, column);
        if (!value) return;
        counts.set(value, (counts.get(value) || 0) + 1);
      });
      if (!counts.size) {
        channelHeaders[column] = labels[column] || column.toUpperCase();
        return;
      }
      channelHeaders[column] = Array.from(counts.entries()).sort((left, right) => {
        if (right[1] !== left[1]) return right[1] - left[1];
        return left[0].localeCompare(right[0], undefined, { sensitivity: "base" });
      })[0][0];
    });

    state.cache = {
      signature,
      filteredRows: filtered,
      channelHeaders,
      availableValuesByColumn,
    };
    return state.cache;
  }

  function filteredRows() {
    return recomputeCache().filteredRows;
  }

  function visibleRows() {
    return filteredRows().slice(0, state.renderedCount);
  }

  function isValueAvailableForColumn(key, value) {
    return Boolean(recomputeCache().availableValuesByColumn?.[key]?.has(value));
  }

  function resetVisibleRows() {
    state.renderedCount = BATCH_SIZE;
    if (tableWrap) tableWrap.scrollTop = 0;
  }

  function applyDefaultState() {
    state.filters = defaultFilters();
    state.searches = {};
    state.openColumn = "";
    state.menuAnchor = null;
    resetVisibleRows();
  }

  function setColumnFilter(key, selected) {
    state.filters[key] = selected;
    resetVisibleRows();
    render();
  }

  function updateFilterSelection(key, value, checked) {
    const universe = allValuesByColumn[key] || [];
    let selected = getSelectedSet(key);
    if (selected === null) {
      selected = new Set(universe);
    } else {
      selected = new Set(selected);
    }

    if (checked) selected.add(value);
    else selected.delete(value);

    state.filters[key] = selected;
    resetVisibleRows();
    render();
  }

  function selectAllForColumn(key) {
    setColumnFilter(key, null);
  }

  function clearColumnFilter(key) {
    setColumnFilter(key, new Set());
  }

  function closeMenu() {
    state.openColumn = "";
    state.menuAnchor = null;
    floatingMenu.hidden = true;
    floatingMenu.replaceChildren();
  }

  function stickyOffset(key) {
    let offset = 0;
    for (const column of STICKY_COLUMNS) {
      if (column === key) break;
      offset += DEFAULT_WIDTHS[column] || 150;
    }
    return offset;
  }

  function buildColGroup() {
    let colGroup = root.querySelector("colgroup");
    if (!colGroup) {
      colGroup = document.createElement("colgroup");
      root.insertBefore(colGroup, tableHead);
    }
    const fragment = document.createDocumentFragment();
    columns.forEach((column) => {
      const col = document.createElement("col");
      col.style.width = `${DEFAULT_WIDTHS[column] || 150}px`;
      fragment.appendChild(col);
    });
    colGroup.replaceChildren(fragment);
  }

  function dynamicChannelHeader(column) {
    return labels[column] || column.toUpperCase();
  }

  function columnLabel(column) {
    if (CHANNEL_COLUMNS.includes(column)) {
      return dynamicChannelHeader(column);
    }
    return labels[column] || column;
  }

  function columnSubLabel(column) {
    if (CHANNEL_COLUMNS.includes(column)) {
      return selectedSummaryText(column);
    }
    return selectedSummaryText(column);
  }

  function openMenuForColumn(column, anchorButton) {
    state.openColumn = column;
    state.menuAnchor = anchorButton;
  }

  function menuPositionStyle(anchorRect) {
    const desiredWidth = 304;
    const containerRect = panel ? panel.getBoundingClientRect() : { left: 0, top: 0 };
    const viewportWidth = window.innerWidth || document.documentElement.clientWidth || 1400;
    const viewportHeight = window.innerHeight || document.documentElement.clientHeight || 900;
    const top = Math.min(anchorRect.bottom - containerRect.top + 8, viewportHeight - containerRect.top - 420);
    const left = Math.max(12, Math.min(anchorRect.right - containerRect.left - desiredWidth, viewportWidth - containerRect.left - desiredWidth - 12));
    return { top, left, width: desiredWidth };
  }

  function renderMenu() {
    if (!state.openColumn || !state.menuAnchor) {
      closeMenu();
      return;
    }

    const column = state.openColumn;
    const selected = getSelectedSet(column);
    const query = normalizeText(state.searches[column] || "").toLowerCase();
    const values = (allValuesByColumn[column] || []).filter((value) => !query || value.toLowerCase().includes(query));
    const anchorRect = state.menuAnchor.getBoundingClientRect();
    const style = menuPositionStyle(anchorRect);

    floatingMenu.hidden = false;
    floatingMenu.style.top = `${style.top}px`;
    floatingMenu.style.left = `${style.left}px`;
    floatingMenu.style.width = `${style.width}px`;

    const header = document.createElement("div");
    header.className = "nbhd-weekwise-filter-menu-header";

    const title = document.createElement("strong");
    title.textContent = labels[column] || column;

    const stateText = document.createElement("span");
    stateText.className = "nbhd-weekwise-filter-state";
    if (selected === null) stateText.textContent = "All";
    else stateText.textContent = `${selected.size} selected`;
    header.append(title, stateText);

    const search = document.createElement("input");
    search.type = "text";
    search.className = "filter-menu-search";
    search.placeholder = `Search ${labels[column] || column}...`;
    search.autocomplete = "off";
    search.value = state.searches[column] || "";
    search.addEventListener("input", (event) => {
      const value = event.target.value || "";
      clearTimeout(state.searchTimers[column]);
      state.searchTimers[column] = window.setTimeout(() => {
        state.searches[column] = value;
        renderMenu();
      }, 90);
    });

    const actions = document.createElement("div");
    actions.className = "nbhd-weekwise-filter-actions";

    const selectAll = document.createElement("button");
    selectAll.type = "button";
    selectAll.className = "ghost-button";
    selectAll.textContent = "Select All";
    selectAll.addEventListener("click", () => selectAllForColumn(column));

    const clear = document.createElement("button");
    clear.type = "button";
    clear.className = "ghost-button";
    clear.textContent = "Clear";
    clear.addEventListener("click", () => clearColumnFilter(column));

    actions.append(selectAll, clear);

    const list = document.createElement("div");
    list.className = "filter-options-list nbhd-weekwise-options-list";

    if (!values.length) {
      const empty = document.createElement("div");
      empty.className = "filter-option-row";
      empty.textContent = "No matching values";
      list.appendChild(empty);
    } else {
      values.forEach((value) => {
        const row = document.createElement("label");
        row.className = "nbhd-weekwise-option";
        const available = isValueAvailableForColumn(column, value);
        if (!available) row.classList.add("disabled");

        const checkbox = document.createElement("input");
        checkbox.type = "checkbox";
        checkbox.checked = selected === null ? true : selected.has(value);
        checkbox.addEventListener("change", (event) => updateFilterSelection(column, value, event.target.checked));

        const text = document.createElement("span");
        text.textContent = value;

        row.append(checkbox, text);
        list.appendChild(row);
      });
    }

    floatingMenu.replaceChildren(header, search, actions, list);
    requestAnimationFrame(() => {
      const input = floatingMenu.querySelector(".filter-menu-search");
      input?.focus();
      input?.setSelectionRange(input.value.length, input.value.length);
    });
  }

  function refreshOpenMenuPosition() {
    if (!state.openColumn || !state.menuAnchor || floatingMenu.hidden) return;
    const anchorRect = state.menuAnchor.getBoundingClientRect();
    const style = menuPositionStyle(anchorRect);
    floatingMenu.style.top = `${style.top}px`;
    floatingMenu.style.left = `${style.left}px`;
    floatingMenu.style.width = `${style.width}px`;
  }

  function buildHeader() {
    buildColGroup();
    const row = document.createElement("tr");

    columns.forEach((column) => {
      const th = document.createElement("th");
      if (STICKY_COLUMNS.includes(column)) {
        th.classList.add("nbhd-weekwise-sticky-col", `nbhd-weekwise-sticky-${column.replace("_", "-")}`);
        th.style.left = `${stickyOffset(column)}px`;
      }

      const wrap = document.createElement("div");
      wrap.className = "nbhd-weekwise-header-cell";

      const copy = document.createElement("div");
      copy.className = "nbhd-weekwise-header-copy";

      const title = document.createElement("span");
      title.className = "nbhd-weekwise-header-title";
      title.textContent = columnLabel(column);

      const badge = document.createElement("span");
      badge.className = `nbhd-weekwise-header-badge${getSelectedSet(column) !== null ? " active" : ""}`;
      badge.textContent = columnSubLabel(column);

      copy.append(title, badge);

      const button = document.createElement("button");
      button.type = "button";
      button.className = `nbhd-weekwise-filter-button${state.openColumn === column ? " active" : ""}`;
      button.dataset.column = column;
      button.setAttribute("aria-label", `Filter ${labels[column] || column}`);
      button.innerHTML = `<span class="nbhd-weekwise-filter-icon"></span><span class="nbhd-weekwise-filter-count">${getSelectedSet(column) === null ? "" : getSelectedSet(column).size}</span>`;
      button.addEventListener("click", (event) => {
        event.stopPropagation();
        if (state.openColumn === column) {
          closeMenu();
          render();
          return;
        }
        openMenuForColumn(column, button);
        render();
      });

      wrap.append(copy, button);
      th.appendChild(wrap);
      row.appendChild(th);
    });

    tableHead.replaceChildren(row);

    if (state.openColumn) {
      const anchor = tableHead.querySelector(`[data-column="${state.openColumn}"]`);
      if (anchor) {
        state.menuAnchor = anchor;
        renderMenu();
      } else {
        closeMenu();
      }
    }
  }

  function buildCell(row, column) {
    const cell = document.createElement("td");
    const value = getColumnValue(row, column);
    cell.textContent = value || "";
    cell.className = "comparison-text-cell";

    if (STICKY_COLUMNS.includes(column)) {
      cell.classList.add("nbhd-weekwise-sticky-col", "nbhd-weekwise-sticky-body", `nbhd-weekwise-sticky-${column.replace("_", "-")}`);
      cell.style.left = `${stickyOffset(column)}px`;
    }
    if (column === "c5" && value.toUpperCase() === "INDIA TV") {
      cell.classList.add("nbhd-weekwise-india-tv");
    }
    if (GENRE_COLUMNS.includes(column) && value) {
      const normalizedGenre = value.toUpperCase();
      if (normalizedGenre === "HINDI NEWS") {
        // Keep HINDI NEWS unhighlighted.
      } else if (normalizedGenre.includes("NEWS")) {
        cell.classList.add("nbhd-weekwise-news-genre");
      } else {
        cell.classList.add("nbhd-weekwise-non-news-genre");
      }
    }
    if (!value) {
      cell.classList.add("comparison-cell-na");
    }
    return cell;
  }

  function maybeLoadMore() {
    if (!tableWrap || state.loadingMore) return;
    const allRows = filteredRows();
    if (state.renderedCount >= allRows.length) return;

    const remaining = tableWrap.scrollHeight - tableWrap.scrollTop - tableWrap.clientHeight;
    if (remaining > LOAD_THRESHOLD) return;

    state.loadingMore = true;
    if (loadState) loadState.textContent = "Loading more records...";
    window.requestAnimationFrame(() => {
      state.renderedCount = Math.min(state.renderedCount + BATCH_SIZE, allRows.length);
      state.loadingMore = false;
      renderTable();
    });
  }

  function renderTable() {
    const allRows = filteredRows();
    const rows = allRows.slice(0, state.renderedCount);

    buildHeader();

    if (resultCount) resultCount.textContent = `${new Intl.NumberFormat().format(allRows.length)} rows`;
    if (pageInfo) pageInfo.textContent = `Showing ${new Intl.NumberFormat().format(rows.length)} of ${new Intl.NumberFormat().format(allRows.length)}`;

    if (!rows.length) {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = columns.length;
      td.className = "empty-state";
      td.textContent = "No data available for the selected filters.";
      tr.appendChild(td);
      tableBody.replaceChildren(tr);
      if (loadState) loadState.textContent = "No Data Found";
      return;
    }

    const fragment = document.createDocumentFragment();
    rows.forEach((row) => {
      const tr = document.createElement("tr");
      columns.forEach((column) => tr.appendChild(buildCell(row, column)));
      fragment.appendChild(tr);
    });
    tableBody.replaceChildren(fragment);

    if (!loadState) return;
    if (rows.length < allRows.length) {
      loadState.textContent = state.loadingMore ? "Loading more records..." : "Scroll to load more records...";
    } else {
      loadState.textContent = "All records loaded";
    }
  }

  function renderStatus() {
    if (source.message && !records.length) {
      statusMessage.hidden = false;
      statusMessage.textContent = source.message;
      return;
    }
    statusMessage.hidden = true;
    statusMessage.textContent = "";
  }

  function renderSummary() {
    const filtered = filteredRows();
    if (totalCount) {
      totalCount.textContent = `${new Intl.NumberFormat().format(records.length)} total records`;
    }
    if (activeFiltersSummary) {
      const count = activeFilterCount();
      activeFiltersSummary.textContent = count ? `${count} active filter${count === 1 ? "" : "s"}` : "Latest week selected";
    }
    if (metaLine) {
      const weekSet = getSelectedSet("week");
      if (weekSet && weekSet.size === 1) {
        metaLine.textContent = `Showing ${Array.from(weekSet)[0]} by default. Clear any filter to intentionally return zero records.`;
      } else {
        metaLine.textContent = filtered.length
          ? "Multiple selections in a filter use OR logic. Different filters combine with AND logic."
          : "No data available for the selected filters.";
      }
    }
  }

  function render() {
    renderStatus();
    renderSummary();
    renderTable();
  }

  function exportExcel() {
    const downloader = window.__downloadExcelWorkbook;
    const excelCell = window.__excelCell || ((value, style = "cell") => ({ value, style }));
    if (typeof downloader !== "function") return;

    const rows = filteredRows();
    downloader("nbhd_weekwise_comparison_report", [{
      name: "Week-wise NBHD Report",
      columns: columns.map((column) => DEFAULT_WIDTHS[column] || 150),
      rows: [
        columns.map((column) => excelCell(columnLabel(column), "header")),
        ...rows.map((row) => columns.map((column) => excelCell(getColumnValue(row, column), "cell"))),
      ],
    }]);
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
      panel.classList.add("comparison-panel-fullscreen", "nbhd-weekwise-panel-fullscreen");
    } else {
      fullscreenState.tableScrollTop = tableWrap.scrollTop;
      fullscreenState.tableScrollLeft = tableWrap.scrollLeft;
      fullscreenState.active = false;
      document.body.classList.remove("comparison-fullscreen-active");
      panel.classList.remove("comparison-panel-fullscreen", "nbhd-weekwise-panel-fullscreen");
    }
    requestAnimationFrame(() => {
      if (!active) {
        window.scrollTo({ top: fullscreenState.windowScrollY, behavior: "auto" });
      }
      tableWrap.scrollTop = fullscreenState.tableScrollTop;
      tableWrap.scrollLeft = fullscreenState.tableScrollLeft;
      renderMenu();
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

  function setPanelVisibility(open) {
    if (!panel) return;
    panel.hidden = !open;
    panel.style.display = open ? "block" : "none";
    if (!open) closeMenu();
    if (toggleButton) {
      toggleButton.classList.toggle("primary-button", open);
      toggleButton.classList.toggle("ghost-button", !open);
    }
  }

  document.addEventListener("click", (event) => {
    if (state.openColumn && !floatingMenu.contains(event.target) && !event.target.closest(".nbhd-weekwise-filter-button")) {
      closeMenu();
      render();
    }
  });

  window.addEventListener("resize", refreshOpenMenuPosition);
  window.addEventListener("scroll", (event) => {
    if (floatingMenu.contains(event.target)) return;
    refreshOpenMenuPosition();
  }, true);

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

  if (tableWrap) {
    tableWrap.addEventListener("scroll", maybeLoadMore);
    tableWrap.addEventListener("scroll", refreshOpenMenuPosition, { passive: true });
    tableWrap.addEventListener("wheel", (event) => {
      const maxHorizontalScroll = tableWrap.scrollWidth - tableWrap.clientWidth;
      if (maxHorizontalScroll <= 0) return;

      const dominantDelta = Math.abs(event.deltaY) > Math.abs(event.deltaX) ? event.deltaY : event.deltaX;
      const shouldScrollHorizontally = event.shiftKey || Math.abs(event.deltaX) > 0 || (Math.abs(event.deltaY) > 0 && tableWrap.clientWidth < tableWrap.scrollWidth);

      if (!shouldScrollHorizontally) return;

      event.preventDefault();
      tableWrap.scrollLeft += dominantDelta;
      refreshOpenMenuPosition();
    }, { passive: false });
  }

  if (resetButton) {
    resetButton.addEventListener("click", () => {
      applyDefaultState();
      render();
    });
  }
  if (toggleButton) {
    toggleButton.addEventListener("click", () => {
      const nextOpen = panel?.hidden ?? true;
      setPanelVisibility(nextOpen);
      if (nextOpen) {
        render();
        requestAnimationFrame(() => panel?.scrollIntoView({ behavior: "smooth", block: "start" }));
      }
    });
  }
  if (hideButton) {
    hideButton.addEventListener("click", () => setPanelVisibility(false));
  }
  if (downloadButton) downloadButton.addEventListener("click", exportExcel);
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

  applyDefaultState();
  syncFullscreenButtons();
  setPanelVisibility(false);
  render();
})();
