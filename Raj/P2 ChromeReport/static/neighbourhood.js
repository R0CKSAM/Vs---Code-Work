(function () {
  const root = document.getElementById("nbhdTable");
  if (!root) return;

  const state = {
    payload: null,
    filters: {
      market: "",
      city: "",
      head_end: "",
      week_range: "",
      change: "",
    },
    page: 1,
    pageSize: 30,
    loading: false,
    standalone: Boolean(window.__NBHD_STANDALONE_DATA__),
    initial: window.__NBHD_INITIAL_DATA__ || null,
  };

  const marketFilter = document.getElementById("nbhdMarketFilter");
  const cityFilter = document.getElementById("nbhdCityFilter");
  const headendFilter = document.getElementById("nbhdHeadendFilter");
  const weekRangeFilter = document.getElementById("nbhdWeekRangeFilter");
  const changeFilter = document.getElementById("nbhdChangeFilter");
  const resultCount = document.getElementById("nbhdResultCount");
  const tableHead = document.getElementById("nbhdTableHead");
  const tableBody = document.getElementById("nbhdTableBody");
  const statusMessage = document.getElementById("nbhdStatusMessage");
  const refreshButton = document.getElementById("nbhdRefreshButton");
  const resetButton = document.getElementById("nbhdResetButton");
  const fullscreenButton = document.getElementById("nbhdFullscreenButton");
  const exitFullscreenButton = document.getElementById("nbhdExitFullscreenButton");
  const prevPageButton = document.getElementById("nbhdPrevPage");
  const nextPageButton = document.getElementById("nbhdNextPage");
  const pageInfo = document.getElementById("nbhdPageInfo");
  const tableWrap = root.closest(".nbhd-table-wrap");
  const panel = root.closest(".nbhd-panel");
  const searchInput = document.getElementById("nbhdSearchInput");
  const fullscreenState = {
    active: false,
    windowScrollY: 0,
    tableScrollTop: 0,
    tableScrollLeft: 0,
    usingNativeFullscreen: false,
  };

  function createOption(value, label) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    return option;
  }

  function getWeekClusterController() {
    return window.__CHROME_WEEK_CLUSTER__ || null;
  }

  function buildWeekRangeOptions(weeks) {
    const controller = getWeekClusterController();
    if (controller) {
      return controller.getOptions(weeks || []);
    }

    const safeWeeks = Array.isArray(weeks) ? weeks.filter((week) => String(week || "").trim() !== "") : [];
    const options = [{ value: "all", label: "All Weeks" }];
    for (let index = 0; index < safeWeeks.length; index += 4) {
      const slice = safeWeeks.slice(index, index + 4);
      if (!slice.length) continue;
      const label = slice.length === 1 ? slice[0] : `${slice[0]} to ${slice[slice.length - 1]}`;
      options.push({ value: `${slice[0]}|||${slice[slice.length - 1]}`, label });
    }
    return options;
  }

  function populateOptionList(select, options, selectedValue) {
    const safeOptions = Array.isArray(options) ? options.filter((option) => option && String(option.value || "").trim() !== "") : [];
    const fallback = safeOptions.some((option) => option.value === selectedValue)
      ? selectedValue
      : (safeOptions[0]?.value || "");
    select.innerHTML = "";
    safeOptions.forEach((option) => select.appendChild(createOption(option.value, option.label)));
    select.value = fallback;
    return fallback;
  }

  function getPageSize() {
    if (!fullscreenState.active) {
      return 30;
    }
    const viewportHeight = window.innerHeight || 900;
    return Math.max(45, Math.floor((viewportHeight - 280) / 24));
  }

  function getVisibleWeeks(payload) {
    const allWeeks = payload.weeks || [];
    const controller = getWeekClusterController();
    if (controller) {
      return controller.getVisibleWeeks(allWeeks, state.filters.week_range || controller.getValue(allWeeks));
    }
    return allWeeks.slice(Math.max(0, allWeeks.length - 4));
  }

  function hasChangeInWeeks(record, weeks) {
    if (weeks.length <= 1) return false;
    let previous = "__unset__";
    let sawValue = false;
    for (const week of weeks) {
      const raw = record.channels?.[week];
      const value = raw === null || raw === undefined || raw === "" ? "" : String(raw);
      if (!sawValue) {
        previous = value;
        sawValue = true;
        continue;
      }
      if (value !== previous) return true;
    }
    return false;
  }

  function populateSelect(select, values, label, selectedValue) {
    const safeValues = Array.isArray(values) ? values.filter((value) => String(value || "").trim() !== "") : [];
    const safeSelectedValue = safeValues.includes(selectedValue) ? selectedValue : "";
    select.innerHTML = "";
    select.appendChild(createOption("", label));
    safeValues.forEach((value) => select.appendChild(createOption(value, value)));
    select.value = safeSelectedValue;
    return safeSelectedValue;
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

  function syncFilters(payload) {
    state.filters.market = populateSelect(marketFilter, payload.filters.markets, "All Markets", state.filters.market);
    state.filters.city = populateSelect(cityFilter, payload.filters.cities, "All Cities", state.filters.city);
    state.filters.head_end = populateSelect(headendFilter, payload.filters.head_ends, "All Headends", state.filters.head_end);
    const controller = getWeekClusterController();
    const preferredRange = state.filters.week_range || (controller ? controller.getValue(payload.weeks || []) : "");
    state.filters.week_range = populateOptionList(weekRangeFilter, buildWeekRangeOptions(payload.weeks || []), preferredRange);
    state.filters.change = populateSelect(changeFilter, ["Changed", "No Change"], "All Changes", state.filters.change);
  }

  function buildHeader(weeks) {
    const rowOne = document.createElement("tr");
    const rowTwo = document.createElement("tr");

    [
      { label: "MARKET", className: "sticky-col sticky-market" },
      { label: "CITY", className: "sticky-col sticky-city" },
      { label: "HEADEND", className: "sticky-col sticky-headend" },
    ].forEach((column) => {
      const th = document.createElement("th");
      th.textContent = column.label;
      th.rowSpan = 2;
      th.className = column.className;
      rowOne.appendChild(th);
    });

    [
      { label: "Channel", key: "channel", className: "nbhd-group-channel" },
      { label: "Frequency", key: "frequency", className: "nbhd-group-frequency" },
      { label: "Genre", key: "genre", className: "nbhd-group-genre" },
    ].forEach((group) => {
      const th = document.createElement("th");
      th.textContent = group.label;
      th.colSpan = Math.max(weeks.length, 1);
      th.className = `nbhd-group-head ${group.className}`;
      rowOne.appendChild(th);

      if (weeks.length) {
        weeks.forEach((week, weekIndex) => {
          const weekTh = document.createElement("th");
          weekTh.textContent = week;
          const groupEdgeClass = weekIndex === 0 ? "nbhd-group-start" : "";
          weekTh.className = `nbhd-week-head ${group.className} ${groupEdgeClass}`.trim();
          rowTwo.appendChild(weekTh);
        });
      } else {
        const emptyTh = document.createElement("th");
        emptyTh.textContent = "-";
        emptyTh.className = `nbhd-week-head ${group.className} nbhd-group-start`;
        rowTwo.appendChild(emptyTh);
      }
    });

    tableHead.replaceChildren(rowOne, rowTwo);
  }

  function buildRow(record, weeks) {
    const tr = document.createElement("tr");

    [
      { value: record.market, className: "sticky-col sticky-market sticky-body" },
      { value: record.city, className: "sticky-col sticky-city sticky-body" },
      { value: record.head_end, className: "sticky-col sticky-headend sticky-body" },
    ].forEach((column) => {
      const td = document.createElement("td");
      td.textContent = column.value || "";
      td.className = column.className;
      tr.appendChild(td);
    });

    const groups = [
      { key: "channels", className: "nbhd-group-channel" },
      { key: "frequencies", className: "nbhd-group-frequency" },
      { key: "genres", className: "nbhd-group-genre" },
    ];
    groups.forEach((groupConfig) => {
      if (!weeks.length) {
        const td = document.createElement("td");
        td.textContent = "-";
        td.className = "nbhd-group-start";
        tr.appendChild(td);
        return;
      }
      weeks.forEach((week, weekIndex) => {
        const td = document.createElement("td");
        const value = record[groupConfig.key][week];
        td.textContent = value === null || value === undefined || value === "" ? "-" : String(value);
        const groupEdgeClass = weekIndex === 0 ? "nbhd-group-start" : "";
        td.className = `${groupConfig.className} ${groupEdgeClass}`.trim();
        if (groupConfig.key === "channels") {
          const current = String(value || "").trim();
          const previousWeek = weekIndex > 0 ? weeks[weekIndex - 1] : "";
          const previous = previousWeek ? String(record[groupConfig.key][previousWeek] || "").trim() : "";
          if (current.toUpperCase() === "INDIA TV") {
            td.classList.add("nbhd-cell-india");
          } else if (weekIndex > 0 && current && !previous) {
            td.classList.add("nbhd-cell-new");
          } else if (weekIndex > 0 && current && previous && current !== previous) {
            td.classList.add("nbhd-cell-changed");
          }
        }
        if (groupConfig.key === "frequencies") {
          const currentValue = value === null || value === undefined || value === "" ? null : Number(value);
          const previousWeek = weekIndex > 0 ? weeks[weekIndex - 1] : "";
          const previousRaw = previousWeek ? record[groupConfig.key][previousWeek] : null;
          const previousValue = previousRaw === null || previousRaw === undefined || previousRaw === "" ? null : Number(previousRaw);
          if (currentValue === null || Number.isNaN(currentValue)) {
            td.classList.add("nbhd-cell-empty");
          } else if (weekIndex > 0 && previousValue !== null && !Number.isNaN(previousValue)) {
            if (currentValue > previousValue) td.classList.add("nbhd-cell-decrease");
            else if (currentValue < previousValue) td.classList.add("nbhd-cell-increase");
          }
        }
        if (groupConfig.key === "genres") {
          const currentGenre = String(value || "").trim();
          const previousWeek = weekIndex > 0 ? weeks[weekIndex - 1] : "";
          const previousGenre = previousWeek ? String(record[groupConfig.key][previousWeek] || "").trim() : "";
          if (!currentGenre || currentGenre === "-") {
            td.classList.add("nbhd-cell-empty");
          } else if (weekIndex > 0 && previousGenre && currentGenre !== previousGenre) {
            td.classList.add("nbhd-cell-changed");
          }
        }
        tr.appendChild(td);
      });
    });

    return tr;
  }

  function paginateGroupedRecords(records) {
    const pages = [];
    let currentPage = [];
    let currentCount = 0;

    function groupKey(record) {
      return `${record.market}||${record.city}||${record.head_end}`;
    }

    let currentGroupKey = "";
    let currentGroup = [];

    function pushGroup(group) {
      if (!group.length) return;
      if (currentPage.length && currentCount + group.length > state.pageSize) {
        pages.push(currentPage);
        currentPage = [];
        currentCount = 0;
      }
      currentPage.push(...group);
      currentCount += group.length;
    }

    records.forEach((record) => {
      const key = groupKey(record);
      if (!currentGroup.length) {
        currentGroupKey = key;
        currentGroup = [record];
        return;
      }
      if (key === currentGroupKey) {
        currentGroup.push(record);
        return;
      }
      pushGroup(currentGroup);
      currentGroupKey = key;
      currentGroup = [record];
    });

    pushGroup(currentGroup);
    if (currentPage.length) {
      pages.push(currentPage);
    }

    return pages.length ? pages : [[]];
  }

  function renderTable(payload) {
    const weeks = getVisibleWeeks(payload);
    buildHeader(weeks);

    if (!payload.table.records.length) {
      pageInfo.textContent = "Page 1 of 1";
      if (prevPageButton) prevPageButton.disabled = true;
      if (nextPageButton) nextPageButton.disabled = true;
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = 3 + Math.max(weeks.length, 1) * 3;
      td.className = "empty-state";
      td.textContent = "No neighbourhood rows match the current filters.";
      tr.appendChild(td);
      tableBody.replaceChildren(tr);
      return;
    }

    const pages = paginateGroupedRecords(payload.table.records);
    const totalPages = Math.max(1, pages.length);
    if (state.page > totalPages) {
      state.page = totalPages;
    }
    const pageRecords = pages[state.page - 1] || [];

    pageInfo.textContent = `Page ${state.page} of ${totalPages}`;
    if (prevPageButton) prevPageButton.disabled = state.page <= 1;
    if (nextPageButton) nextPageButton.disabled = state.page >= totalPages;

    const fragment = document.createDocumentFragment();
    pageRecords.forEach((record) => fragment.appendChild(buildRow(record, weeks)));
    tableBody.replaceChildren(fragment);
  }

  function render(payload) {
    state.payload = payload;
    state.pageSize = getPageSize();
    syncFilters(payload);
    renderStatus(payload);
    resultCount.textContent = `${new Intl.NumberFormat().format(payload.table.total_count)} rows`;
    renderTable(payload);
  }

  function matchesRecord(record, filters, weeks) {
    if (filters.market && record.market !== filters.market) return false;
    if (filters.city && record.city !== filters.city) return false;
    if (filters.head_end && record.head_end !== filters.head_end) return false;
    if (filters.change === "Changed" && !hasChangeInWeeks(record, weeks)) return false;
    if (filters.change === "No Change" && hasChangeInWeeks(record, weeks)) return false;
    return true;
  }

  function buildStandalonePayload() {
    const source = window.__NBHD_STANDALONE_DATA__;
    const sourceTable = source.table || {};
    const allRecords = sourceTable.records || source.records || [];
    const visibleWeeks = getVisibleWeeks(source);
    const filtered = allRecords.filter((record) => matchesRecord(record, state.filters, visibleWeeks));

    function optionsFor(key, field) {
      const scopedFilters = { ...state.filters, [key]: "" };
      return Array.from(
        new Set(
          allRecords
            .filter((record) => matchesRecord(record, scopedFilters, visibleWeeks))
            .map((record) => record[field])
            .filter((value) => String(value || "").trim() !== "")
        )
      ).sort((left, right) => left.localeCompare(right));
    }

    return {
      ...source,
      weeks: source.weeks || [],
      filters: {
        markets: optionsFor("market", "market"),
        cities: optionsFor("city", "city"),
        head_ends: optionsFor("head_end", "head_end"),
      },
      summary: {
        total_headends: filtered.length,
      },
      table: {
        records: filtered,
        total_count: filtered.length,
      },
    };
  }

  async function fetchPayload(forceRefresh) {
    if (state.standalone) {
      render(buildStandalonePayload());
      return;
    }

    const params = new URLSearchParams({
      market: state.filters.market,
      city: state.filters.city,
      head_end: state.filters.head_end,
    });
    if (forceRefresh) {
      params.set("refresh", "1");
    }

    setLoading(true);
    try {
      const response = await fetch(`/api/neighbourhood?${params.toString()}`);
      render(await response.json());
    } catch (error) {
      if (state.payload) {
        statusMessage.hidden = false;
        statusMessage.textContent = "Neighbourhood data refresh failed. Showing the last available data.";
      } else {
        statusMessage.hidden = false;
        statusMessage.textContent = "Neighbourhood data could not be loaded.";
      }
    } finally {
      setLoading(false);
    }
  }

  function bindSelect(select, key) {
    select.addEventListener("change", () => {
      state.filters[key] = select.value;
      state.page = 1;
      fetchPayload(false);
    });
  }

  function syncFullscreenButtons() {
    const label = fullscreenState.active ? "Exit Full Screen" : "Full Screen";
    if (fullscreenButton) {
      fullscreenButton.textContent = label;
    }
    if (exitFullscreenButton) {
      exitFullscreenButton.hidden = !fullscreenState.active;
    }
  }

  function setFullscreen(active) {
    if (!panel || !tableWrap || fullscreenState.active === active) return;

    if (active) {
      fullscreenState.windowScrollY = window.scrollY || window.pageYOffset || 0;
      fullscreenState.tableScrollTop = tableWrap.scrollTop;
      fullscreenState.tableScrollLeft = tableWrap.scrollLeft;
      fullscreenState.active = true;
      document.body.classList.add("nbhd-fullscreen-active");
      panel.classList.add("nbhd-panel-fullscreen");
      state.pageSize = getPageSize();
      if (state.payload) {
        render(state.payload);
      }
      requestAnimationFrame(() => {
        tableWrap.scrollTop = fullscreenState.tableScrollTop;
        tableWrap.scrollLeft = fullscreenState.tableScrollLeft;
      });
    } else {
      fullscreenState.tableScrollTop = tableWrap.scrollTop;
      fullscreenState.tableScrollLeft = tableWrap.scrollLeft;
      fullscreenState.active = false;
      document.body.classList.remove("nbhd-fullscreen-active");
      panel.classList.remove("nbhd-panel-fullscreen");
      state.pageSize = getPageSize();
      if (state.payload) {
        render(state.payload);
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
    if (!panel?.requestFullscreen) {
      return false;
    }
    try {
      fullscreenState.usingNativeFullscreen = true;
      await panel.requestFullscreen();
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
      if (fullscreenState.usingNativeFullscreen && document.fullscreenElement === panel) {
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

  function resetFilters() {
    state.filters.market = "";
    state.filters.city = "";
    state.filters.head_end = "";
    state.filters.week_range = getWeekClusterController()?.getValue(state.payload?.weeks || []) || "";
    state.filters.change = "";
    state.page = 1;
    if (searchInput) {
      searchInput.value = "";
    }
    fetchPayload(false);
  }

  bindSelect(marketFilter, "market");
  bindSelect(cityFilter, "city");
  bindSelect(headendFilter, "head_end");
  if (weekRangeFilter) {
    weekRangeFilter.addEventListener("change", () => {
      state.filters.week_range = weekRangeFilter.value;
      state.page = 1;
      const controller = getWeekClusterController();
      if (controller) {
        controller.setValue(state.filters.week_range, state.payload?.weeks || []);
        return;
      }
      fetchPayload(false);
    });
  }
  bindSelect(changeFilter, "change");
  if (refreshButton) {
    refreshButton.addEventListener("click", () => fetchPayload(true));
  }
  if (resetButton) {
    resetButton.addEventListener("click", resetFilters);
  }
  if (fullscreenButton) {
    fullscreenButton.addEventListener("click", toggleFullscreen);
  }
  if (exitFullscreenButton) {
    exitFullscreenButton.addEventListener("click", async () => {
      if (fullscreenState.usingNativeFullscreen && document.fullscreenElement === panel) {
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
      if (!state.payload) return;
      const totalPages = Math.max(1, paginateGroupedRecords(state.payload.table.records || []).length);
      if (state.page < totalPages) {
        state.page += 1;
        render(state.payload);
      }
    });
  }
  window.addEventListener("resize", () => {
    if (!state.payload) return;
    const nextPageSize = getPageSize();
    if (nextPageSize !== state.pageSize) {
      state.pageSize = nextPageSize;
      render(state.payload);
    }
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
  window.addEventListener("chrome:week-cluster-change", (event) => {
    state.filters.week_range = event.detail?.value || "";
    state.page = 1;
    fetchPayload(false);
  });

  if (state.initial) {
    render(state.initial);
  }
  syncFullscreenButtons();
  fetchPayload(false);
})();
