(function () {
  const root = document.getElementById("nbhdTable");
  if (!root) return;
  const NO_DATA_LABEL = "NA";

  const state = {
    payload: null,
    filters: {
      market: "",
      city: "",
      head_end: "",
      week_from: "",
      week_to: "",
      change: "",
    },
    page: 1,
    pageSize: 30,
    loading: false,
    standalone: Boolean(window.__NBHD_STANDALONE_DATA__),
    initial: window.__NBHD_INITIAL_DATA__ || null,
    report: {
      open: false,
      headend: "",
      week_from: "",
      week_to: "",
    },
  };

  const DEFAULT_REPORT_CHANNELS = [
    { label: "INDIA TV", key: "INDIATV" },
    { label: "AAJ TAK", key: "AAJTAK" },
    { label: "NEWS 18 INDIA", key: "NEWS18INDIA" },
    { label: "REPUBLIC BHARAT", key: "REPUBLICBHARAT" },
  ];
  const DEFAULT_REPORT_CHANNEL_KEYS = DEFAULT_REPORT_CHANNELS.map((channel) => channel.key);

  function getSingleSelectControl(id) {
    return {
      button: document.getElementById(id),
      menu: document.getElementById(`${id}Menu`),
      search: document.getElementById(`${id}Search`),
      options: document.getElementById(`${id}Options`),
    };
  }
  function getMultiSelectControl(id) {
    return {
      button: document.getElementById(id),
      menu: document.getElementById(`${id}Menu`),
      search: document.getElementById(`${id}Search`),
      options: document.getElementById(`${id}Options`),
    };
  }
  const marketFilter = getSingleSelectControl("nbhdMarketFilter");
  const cityFilter = getSingleSelectControl("nbhdCityFilter");
  const headendFilter = getSingleSelectControl("nbhdHeadendFilter");
  const weekFromFilter = getSingleSelectControl("nbhdWeekFromFilter");
  const weekToFilter = getSingleSelectControl("nbhdWeekToFilter");
  const changeFilter = getSingleSelectControl("nbhdChangeFilter");
  const reportToggleButton = document.getElementById("nbhdReportToggleButton");
  const reportLauncher = document.getElementById("nbhdReportLauncher");
  const reportPanel = document.getElementById("nbhdReportPanel");
  const reportMeta = document.getElementById("nbhdReportMeta");
  const reportCount = document.getElementById("nbhdReportCount");
  const reportStatus = document.getElementById("nbhdReportStatusMessage");
  const reportContent = document.getElementById("nbhdReportContent");
  const reportHeadendFilter = getSingleSelectControl("nbhdReportHeadendFilter");
  const reportWeekFromFilter = getSingleSelectControl("nbhdReportWeekFromFilter");
  const reportWeekToFilter = getSingleSelectControl("nbhdReportWeekToFilter");
  const reportResetButton = document.getElementById("nbhdReportResetButton");
  const reportHideButton = document.getElementById("nbhdReportHideButton");
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
  const fullscreenState = {
    active: false,
    windowScrollY: 0,
    tableScrollTop: 0,
    tableScrollLeft: 0,
    usingNativeFullscreen: false,
  };

  function normalizeText(value) {
    return String(value ?? "").replace(/\s+/g, " ").trim();
  }

  function normalizePayloadShape(payload) {
    if (!payload || typeof payload !== "object") {
      return {
        generated_at: "",
        weeks: [],
        filters: { markets: [], cities: [], head_ends: [] },
        table: { records: [], total_count: 0 },
        message: "",
        source_directory: "",
      };
    }

    if (payload.table && Array.isArray(payload.table.records)) {
      return payload;
    }

    const records = Array.isArray(payload.records) ? payload.records : [];
    const markets = Array.from(new Set(records.map((record) => record.market).filter((value) => String(value || "").trim() !== "")))
      .sort((left, right) => left.localeCompare(right, undefined, { numeric: true }));
    const cities = Array.from(new Set(records.map((record) => record.city).filter((value) => String(value || "").trim() !== "")))
      .sort((left, right) => left.localeCompare(right, undefined, { numeric: true }));
    const headends = Array.from(new Set(records.map((record) => record.head_end).filter((value) => String(value || "").trim() !== "")))
      .sort((left, right) => left.localeCompare(right, undefined, { numeric: true }));

    return {
      ...payload,
      weeks: Array.isArray(payload.weeks) ? payload.weeks : [],
      filters: payload.filters || {
        markets,
        cities,
        head_ends: headends,
      },
      table: {
        records,
        total_count: typeof payload.total_count === "number" ? payload.total_count : records.length,
      },
    };
  }

  function updateButton(control, value, placeholder) {
    if (control?.button) control.button.textContent = value || placeholder;
  }

  function closeMenus(exceptControl = null) {
    [
      marketFilter,
      cityFilter,
      headendFilter,
      weekFromFilter,
      weekToFilter,
      changeFilter,
      reportHeadendFilter,
      reportWeekFromFilter,
      reportWeekToFilter,
    ].forEach((control) => {
      if (control !== exceptControl && control?.menu) control.menu.hidden = true;
    });
  }

  function renderOptions(control, values, selectedValue, placeholder, onSelect) {
    if (!control?.options) return;
    const safeValues = Array.isArray(values) ? values.filter((value) => String(value || "").trim() !== "") : [];
    const query = String(control.search?.value || "").trim().toLowerCase();
    const fragment = document.createDocumentFragment();
    [{ value: "", label: placeholder }, ...safeValues.map((value) => ({ value, label: value }))]
      .filter((option) => !query || String(option.label).toLowerCase().includes(query))
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

  function getConstrainedWeekOptions(allWeeks, key) {
    const weeks = Array.isArray(allWeeks) ? allWeeks.filter((value) => String(value || "").trim() !== "") : [];
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

  function populateSearchInput(control, values, placeholder, selectedValue, onSelect) {
    const safeValues = Array.isArray(values) ? values.filter((value) => String(value || "").trim() !== "") : [];
    const fallback = safeValues.includes(selectedValue) ? selectedValue : "";
    updateButton(control, fallback, placeholder);
    renderOptions(control, safeValues, fallback, placeholder, (value) => {
      onSelect(value);
      closeMenus();
    });
    return fallback;
  }

  function getPageSize() {
    if (!fullscreenState.active) {
      return 30;
    }
    const wrapHeight = tableWrap?.clientHeight || Math.max((window.innerHeight || 900) - 220, 320);
    const headerRows = tableHead?.querySelectorAll("tr") || [];
    const headerHeight = Array.from(headerRows).reduce((total, row) => total + (row.getBoundingClientRect().height || 0), 0) || 56;
    const sampleRow = tableBody?.querySelector("tr");
    const rowHeight = sampleRow?.getBoundingClientRect().height || 24;
    const usableHeight = Math.max(wrapHeight - headerHeight - 8, rowHeight);
    return Math.max(30, Math.floor(usableHeight / rowHeight));
  }

  function getVisibleWeeks(payload) {
    const allWeeks = payload.weeks || [];
    if (!allWeeks.length) return [];
    if (state.filters.week_from || state.filters.week_to) {
      const fromIndex = state.filters.week_from && allWeeks.includes(state.filters.week_from) ? allWeeks.indexOf(state.filters.week_from) : 0;
      const toIndex = state.filters.week_to && allWeeks.includes(state.filters.week_to) ? allWeeks.indexOf(state.filters.week_to) : allWeeks.length - 1;
      const start = Math.min(fromIndex, toIndex);
      const end = Math.max(fromIndex, toIndex);
      return allWeeks.slice(start, end + 1);
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

  function getFrequencyChangeDirection(previousRaw, currentRaw) {
    const previousMissing = previousRaw === null || previousRaw === undefined || previousRaw === "";
    const currentMissing = currentRaw === null || currentRaw === undefined || currentRaw === "";
    if (previousMissing && currentMissing) return "";
    if (previousMissing && !currentMissing) return "Increase";
    if (!previousMissing && currentMissing) return "Decrease";
    const previousValue = Number(previousRaw);
    const currentValue = Number(currentRaw);
    if (Number.isNaN(previousValue) || Number.isNaN(currentValue) || currentValue === previousValue) return "";
    return currentValue < previousValue ? "Increase" : "Decrease";
  }

  function getRecordChangeMeta(record, weeks) {
    let changed = false;
    let hasIncrease = false;
    let hasDecrease = false;
    if (weeks.length <= 1) {
      return { changed, hasIncrease, hasDecrease };
    }
    for (let index = 1; index < weeks.length; index += 1) {
      const previousWeek = weeks[index - 1];
      const currentWeek = weeks[index];
      const previousChannel = String(record.channels?.[previousWeek] || "").trim();
      const currentChannel = String(record.channels?.[currentWeek] || "").trim();
      const previousGenre = String(record.genres?.[previousWeek] || "").trim();
      const currentGenre = String(record.genres?.[currentWeek] || "").trim();
      if (previousChannel !== currentChannel || previousGenre !== currentGenre) {
        changed = true;
      }
      const frequencyDirection = getFrequencyChangeDirection(record.frequencies?.[previousWeek], record.frequencies?.[currentWeek]);
      if (frequencyDirection) changed = true;
      if (frequencyDirection === "Increase") hasIncrease = true;
      if (frequencyDirection === "Decrease") hasDecrease = true;
    }
    return { changed, hasIncrease, hasDecrease };
  }

  function populateSelect(select, values, label, selectedValue, onSelect) {
    return populateSearchInput(select, values, label, selectedValue, onSelect);
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
    state.filters.market = populateSelect(marketFilter, payload.filters.markets, "All Markets", state.filters.market, (value) => applyFilter("market", value));
    state.filters.city = populateSelect(cityFilter, payload.filters.cities, "All Cities", state.filters.city, (value) => applyFilter("city", value));
    state.filters.head_end = populateSelect(headendFilter, payload.filters.head_ends, "All Headends", state.filters.head_end, (value) => applyFilter("head_end", value));
    state.filters.week_from = populateSelect(weekFromFilter, getConstrainedWeekOptions(payload.weeks || [], "week_from"), "From Week", state.filters.week_from, (value) => applyFilter("week_from", value));
    state.filters.week_to = populateSelect(weekToFilter, getConstrainedWeekOptions(payload.weeks || [], "week_to"), "To Week", state.filters.week_to, (value) => applyFilter("week_to", value));
    state.filters.change = populateSelect(changeFilter, ["Changed", "No Change", "Increase", "Decrease"], "All Changes", state.filters.change, (value) => applyFilter("change", value));
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
        emptyTh.textContent = NO_DATA_LABEL;
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
        td.textContent = NO_DATA_LABEL;
        td.className = "nbhd-group-start";
        tr.appendChild(td);
        return;
      }
      weeks.forEach((week, weekIndex) => {
        const td = document.createElement("td");
        const value = record[groupConfig.key][week];
        td.textContent = value === null || value === undefined || value === "" ? NO_DATA_LABEL : String(value);
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
          if (!currentGenre || currentGenre === NO_DATA_LABEL) {
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
    state.payload = normalizePayloadShape(payload);
    state.pageSize = getPageSize();
    syncFilters(state.payload);
    renderStatus(state.payload);
    resultCount.textContent = `${new Intl.NumberFormat().format(state.payload.table.total_count)} rows`;
    renderTable(state.payload);
    renderReportPanel();
  }

  function normalizeChannelKey(value) {
    return normalizeText(value).toUpperCase().replace(/[^A-Z0-9]+/g, "");
  }

  function formatHeadendContext(record) {
    const parts = [normalizeText(record.market), normalizeText(record.city)].filter(Boolean);
    return parts.join(" | ");
  }

  function getAllSourceRecords() {
    if (state.standalone) {
      const source = normalizePayloadShape(window.__NBHD_STANDALONE_DATA__);
      const sourceTable = source.table || {};
      return sourceTable.records || source?.records || [];
    }
    return state.payload?.table?.records || [];
  }

  function getCurrentTableRecords() {
    return state.payload?.table?.records || [];
  }

  function getReportAvailableWeeks() {
    const payload = normalizePayloadShape(state.payload || window.__NBHD_STANDALONE_DATA__ || { weeks: [] });
    return (payload.weeks || []).filter((value) => normalizeText(value) !== "");
  }

  function getReportConstrainedWeekOptions(key) {
    const weeks = getReportAvailableWeeks();
    if (key === "week_from") {
      const toIndex = state.report.week_to && weeks.includes(state.report.week_to) ? weeks.indexOf(state.report.week_to) : weeks.length - 1;
      return weeks.slice(0, toIndex + 1);
    }
    if (key === "week_to") {
      const fromIndex = state.report.week_from && weeks.includes(state.report.week_from) ? weeks.indexOf(state.report.week_from) : 0;
      return weeks.slice(fromIndex);
    }
    return weeks;
  }

  function getReportVisibleWeeks() {
    const weeks = getReportAvailableWeeks();
    if (!weeks.length) return [];
    if (state.report.week_from || state.report.week_to) {
      const fromIndex = state.report.week_from && weeks.includes(state.report.week_from) ? weeks.indexOf(state.report.week_from) : Math.max(0, weeks.length - 2);
      const toIndex = state.report.week_to && weeks.includes(state.report.week_to) ? weeks.indexOf(state.report.week_to) : weeks.length - 1;
      const start = Math.min(fromIndex, toIndex);
      const end = Math.max(fromIndex, toIndex);
      const selected = weeks.slice(start, end + 1);
      return selected.length >= 2 ? [selected[0], selected[selected.length - 1]] : selected;
    }
    return weeks.slice(Math.max(0, weeks.length - 2));
  }

  function getBaseReportRecords() {
    return getCurrentTableRecords();
  }

  function getReportHeadends(records) {
    return Array.from(
      new Set(records.map((record) => normalizeText(record.head_end)).filter(Boolean))
    ).sort((left, right) => left.localeCompare(right, undefined, { numeric: true }));
  }

  function getAllReportChannels(records) {
    const values = new Map();
    records.forEach((record) => {
      Object.values(record.channels || {}).forEach((value) => {
        const text = normalizeText(value);
        if (!text || text === NO_DATA_LABEL) return;
        const key = normalizeChannelKey(text);
        if (!values.has(key)) values.set(key, text);
      });
    });
    return Array.from(values.values()).sort((left, right) => left.localeCompare(right, undefined, { numeric: true }));
  }

  function getReportChannelOptions(records) {
    const reportWeeks = getReportVisibleWeeks();
    const values = new Map();
    records.forEach((record) => {
      reportWeeks.forEach((week) => {
        const value = normalizeText(record.channels?.[week]);
        if (!value || value === NO_DATA_LABEL) return;
        const key = normalizeChannelKey(value);
        if (!values.has(key)) values.set(key, value);
      });
    });
    return Array.from(values.values()).sort((left, right) => left.localeCompare(right, undefined, { numeric: true }));
  }

  function updateMultiSelectButton(button, selectedValues, allValues, emptyLabel, noun) {
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

  function getPreferredReportHeadend(records, weeks, channels) {
    const selectedChannels = Array.isArray(channels) && channels.length ? channels : DEFAULT_REPORT_CHANNELS.map((channel) => channel.label);
    if (!Array.isArray(weeks) || weeks.length < 2) {
      return "";
    }
    const previousWeek = weeks[0];
    const currentWeek = weeks[weeks.length - 1];
    const grouped = new Map();
    records.forEach((record) => {
      const headend = normalizeText(record.head_end);
      if (!headend) return;
      if (!grouped.has(headend)) grouped.set(headend, []);
      grouped.get(headend).push(record);
    });

    for (const [headend, groupRecords] of grouped.entries()) {
      const previousMap = buildHeadendMaps(groupRecords, previousWeek);
      const currentMap = buildHeadendMaps(groupRecords, currentWeek);
      for (const channel of selectedChannels) {
        const channelKey = normalizeChannelKey(channel);
        const previousPosition = previousMap.channelPositions.get(channelKey);
        const currentPosition = currentMap.channelPositions.get(channelKey);
        if (previousPosition === undefined || currentPosition === undefined) continue;
        const previousLower = neighborAt(previousMap, previousPosition, -1);
        const previousUpper = neighborAt(previousMap, previousPosition, 1);
        const currentLower = neighborAt(currentMap, currentPosition, -1);
        const currentUpper = neighborAt(currentMap, currentPosition, 1);
        if (previousLower !== currentLower || previousUpper !== currentUpper) {
          return headend;
        }
      }
    }

    return Array.from(grouped.keys())[0] || "";
  }

  function getContextReportWeeks(allWeeks) {
    const weeks = Array.isArray(allWeeks) ? allWeeks.filter((value) => normalizeText(value) !== "") : [];
    if (!weeks.length) return [];
    const fallbackFrom = weeks.includes(state.filters.week_from)
      ? state.filters.week_from
      : (weeks.length >= 2 ? weeks[weeks.length - 2] : weeks[0]);
    const fallbackTo = weeks.includes(state.filters.week_to)
      ? state.filters.week_to
      : weeks[weeks.length - 1];
    const weekFrom = weeks.includes(state.report.week_from) ? state.report.week_from : fallbackFrom;
    const weekTo = weeks.includes(state.report.week_to) ? state.report.week_to : fallbackTo;
    const fromIndex = weeks.indexOf(weekFrom);
    const toIndex = weeks.indexOf(weekTo);
    if (fromIndex < 0 || toIndex < 0) return weeks.slice(Math.max(0, weeks.length - 2));
    return weeks.slice(Math.min(fromIndex, toIndex), Math.max(fromIndex, toIndex) + 1);
  }

  function getChangedReportHeadends(records, weeks) {
    if (!Array.isArray(weeks) || weeks.length < 2) {
      return getReportHeadends(records);
    }
    const previousWeek = weeks[0];
    const currentWeek = weeks[weeks.length - 1];
    const grouped = new Map();
    records.forEach((record) => {
      const headend = normalizeText(record.head_end);
      if (!headend) return;
      if (!grouped.has(headend)) grouped.set(headend, []);
      grouped.get(headend).push(record);
    });

    const changedHeadends = [];
    for (const [headend, groupRecords] of grouped.entries()) {
      const previousMap = buildHeadendMaps(groupRecords, previousWeek);
      const currentMap = buildHeadendMaps(groupRecords, currentWeek);
      let hasChange = false;
      for (const { key } of DEFAULT_REPORT_CHANNELS) {
        const previousPosition = previousMap.channelPositions.get(key);
        const currentPosition = currentMap.channelPositions.get(key);
        if (previousPosition === undefined || currentPosition === undefined) continue;
        const previousLower = neighborAt(previousMap, previousPosition, -1);
        const previousUpper = neighborAt(previousMap, previousPosition, 1);
        const currentLower = neighborAt(currentMap, currentPosition, -1);
        const currentUpper = neighborAt(currentMap, currentPosition, 1);
        if (previousLower !== currentLower || previousUpper !== currentUpper) {
          hasChange = true;
          break;
        }
      }
      if (hasChange) {
        changedHeadends.push(headend);
      }
    }

    return changedHeadends.sort((left, right) => left.localeCompare(right, undefined, { numeric: true }));
  }

  function syncReportSelections(context) {
    if (!context.headends.includes(state.report.headend)) {
      if (state.filters.head_end && context.headends.includes(state.filters.head_end)) {
        state.report.headend = state.filters.head_end;
      } else {
        state.report.headend = getPreferredReportHeadend(getAllSourceRecords(), context.allWeeks, DEFAULT_REPORT_CHANNELS.map((channel) => channel.label))
          || context.headends[0]
          || "";
      }
    }

    const allWeeks = context.allWeeks || [];
    if (!allWeeks.includes(state.report.week_from)) {
      if (allWeeks.includes(state.filters.week_from)) {
        state.report.week_from = state.filters.week_from;
      } else {
        state.report.week_from = allWeeks.length >= 2 ? allWeeks[allWeeks.length - 2] : (allWeeks[0] || "");
      }
    }
    if (!allWeeks.includes(state.report.week_to)) {
      if (allWeeks.includes(state.filters.week_to)) {
        state.report.week_to = state.filters.week_to;
      } else {
        state.report.week_to = allWeeks[allWeeks.length - 1] || "";
      }
    }
    if (
      state.report.week_from
      && state.report.week_to
      && allWeeks.includes(state.report.week_from)
      && allWeeks.includes(state.report.week_to)
      && allWeeks.indexOf(state.report.week_from) > allWeeks.indexOf(state.report.week_to)
    ) {
      state.report.week_from = state.report.week_to;
    }
  }

  function buildReportContext() {
    const records = getAllSourceRecords();
    const allWeeks = getReportAvailableWeeks();
    const activeWeeks = getContextReportWeeks(allWeeks);
    return {
      headends: getChangedReportHeadends(records, activeWeeks),
      allWeeks,
    };
  }

  function renderReportFilters(context) {
    state.report.headend = populateSelect(
      reportHeadendFilter,
      context.headends,
      "Select Headend",
      state.report.headend,
      (value) => {
        state.report.headend = value;
        renderReportPanel();
      }
    );
    state.report.week_from = populateSelect(
      reportWeekFromFilter,
      getReportConstrainedWeekOptions("week_from"),
      "Previous Week",
      state.report.week_from,
      (value) => {
        state.report.week_from = value;
        const weeks = getReportAvailableWeeks();
        const fromIndex = weeks.indexOf(state.report.week_from);
        const toIndex = weeks.indexOf(state.report.week_to);
        if (fromIndex >= 0 && toIndex >= 0 && fromIndex > toIndex) {
          state.report.week_to = value;
        }
        renderReportPanel();
      }
    );
    state.report.week_to = populateSelect(
      reportWeekToFilter,
      getReportConstrainedWeekOptions("week_to"),
      "Current Week",
      state.report.week_to,
      (value) => {
        state.report.week_to = value;
        const weeks = getReportAvailableWeeks();
        const fromIndex = weeks.indexOf(state.report.week_from);
        const toIndex = weeks.indexOf(state.report.week_to);
        if (fromIndex >= 0 && toIndex >= 0 && fromIndex > toIndex) {
          state.report.week_from = value;
        }
        renderReportPanel();
      }
    );
  }

  function buildHeadendMaps(records, week) {
    const byPosition = new Map();
    const channelPositions = new Map();
    records.forEach((record) => {
      const channel = normalizeText(record.channels?.[week]);
      const position = Number(record.position);
      if (!channel || Number.isNaN(position)) return;
      byPosition.set(position, channel);
      channelPositions.set(normalizeChannelKey(channel), position);
    });
    return { byPosition, channelPositions };
  }

  function neighborAt(mapState, position, offset) {
    return normalizeText(mapState.byPosition.get(position + offset)) || "NA";
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

  function setReportVisibility(open) {
    state.report.open = open;
    if (reportPanel) {
      reportPanel.hidden = !open;
      reportPanel.style.display = open ? "block" : "none";
    }
    if (reportLauncher) {
      reportLauncher.hidden = open;
      reportLauncher.style.display = open ? "none" : "flex";
    }
  }
  function showReportError(message) {
    setReportVisibility(true);
    if (reportCount) reportCount.textContent = "0 narratives";
    renderReportStatus(message);
    if (reportContent) {
      reportContent.innerHTML = `<div class="nbhd-report-empty">${message}</div>`;
    }
  }
  function closeReportPanel() {
    state.report.open = false;
    setReportVisibility(false);
    requestAnimationFrame(() => {
      reportLauncher?.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  }
  function buildReportNarratives() {
    const payload = normalizePayloadShape(state.payload || window.__NBHD_STANDALONE_DATA__ || { weeks: [] });
    const allWeeks = payload.weeks || [];
    const weekFrom = state.report.week_from;
    const weekTo = state.report.week_to;
    const fromIndex = allWeeks.includes(weekFrom) ? allWeeks.indexOf(weekFrom) : -1;
    const toIndex = allWeeks.includes(weekTo) ? allWeeks.indexOf(weekTo) : -1;
    const weeks = fromIndex >= 0 && toIndex >= 0
      ? allWeeks.slice(Math.min(fromIndex, toIndex), Math.max(fromIndex, toIndex) + 1)
      : [];
    if (weeks.length < 2) {
      return {
        weeks,
        headend: normalizeText(state.report.headend),
        rows: [],
        totalRows: 0,
        message: "Select previous and current week in the report filters to generate the neighbour change report.",
      };
    }

    const previousWeek = weeks[0];
    const currentWeek = weeks[weeks.length - 1];
    const baseRecords = getAllSourceRecords();
    const selectedHeadend = normalizeText(state.report.headend);
    if (!selectedHeadend) {
      return {
        weeks,
        headend: "",
        rows: [],
        totalRows: 0,
        message: "Select a Headend in the report filters to generate the neighbour change report.",
      };
    }

    const groupRecords = baseRecords.filter((record) => normalizeText(record.head_end) === selectedHeadend);
    if (!groupRecords.length) {
      return {
        weeks,
        headend: selectedHeadend,
        rows: [],
        totalRows: 0,
        message: "No headend data is available for the selected report filters.",
      };
    }

    const previousMap = buildHeadendMaps(groupRecords, previousWeek);
    const currentMap = buildHeadendMaps(groupRecords, currentWeek);
    const availableChannels = new Map();
    getReportChannelOptions(groupRecords).forEach((value) => {
      availableChannels.set(normalizeChannelKey(value), normalizeText(value));
    });
    const rows = [];

    DEFAULT_REPORT_CHANNELS.forEach(({ label, key }) => {
      const channelLabel = availableChannels.get(key) || label;
      const channelKey = key;
      const previousPosition = previousMap.channelPositions.get(channelKey);
      const currentPosition = currentMap.channelPositions.get(channelKey);
      if (previousPosition === undefined || currentPosition === undefined) return;

      const previousLower = neighborAt(previousMap, previousPosition, -1);
      const previousUpper = neighborAt(previousMap, previousPosition, 1);
      const currentLower = neighborAt(currentMap, currentPosition, -1);
      const currentUpper = neighborAt(currentMap, currentPosition, 1);
      if (previousLower === currentLower && previousUpper === currentUpper) return;

      rows.push({
        channel: channelLabel,
        previous_position: `${previousLower} <- ${channelLabel} -> ${previousUpper}`,
        current_position: `${currentLower} <- ${channelLabel} -> ${currentUpper}`,
        status: "Changed",
        summary: `${channelLabel} moved from between ${previousLower} and ${previousUpper} to between ${currentLower} and ${currentUpper}.`,
      });
    });

    return {
      weeks,
      headend: selectedHeadend,
      rows,
      totalRows: rows.length,
      message: rows.length ? "" : `No neighbour changes detected for the selected channels in ${selectedHeadend}.`,
    };
  }

  function renderReportPanel() {
    if (!reportPanel || !reportContent) return;
    setReportVisibility(state.report.open);
    if (reportToggleButton) reportToggleButton.textContent = "Neighbour Change Report";
    if (!state.report.open) return;
    try {
      const context = buildReportContext();
      syncReportSelections(context);
      renderReportFilters(context);
      const reportData = buildReportNarratives();
      const previousWeek = reportData.weeks[0];
      const currentWeek = reportData.weeks[reportData.weeks.length - 1];
      if (reportMeta) {
        reportMeta.textContent = previousWeek && currentWeek
          ? `Neighbour comparison for ${reportData.headend || "the selected headend"} from ${previousWeek} to ${currentWeek}.`
          : "Select previous and current week to compare neighbourhood positions.";
      }
      if (reportCount) {
        reportCount.textContent = `${reportData.totalRows} narrative${reportData.totalRows === 1 ? "" : "s"}`;
      }

      renderReportStatus(reportData.message);
      if (reportData.message) {
        reportContent.innerHTML = `<div class="nbhd-report-empty">${reportData.message}</div>`;
        return;
      }

      const section = document.createElement("section");
      section.className = "nbhd-report-group";

      const header = document.createElement("div");
      header.className = "nbhd-report-group-header";
      const title = document.createElement("h4");
      title.textContent = reportData.headend || "Selected Headend";
      header.append(title);

      const tableWrap = document.createElement("div");
      tableWrap.className = "nbhd-report-table-wrap";
      const table = document.createElement("table");
      table.className = "nbhd-report-table";
      const tbodyRows = reportData.rows.map((row) => `
        <tr>
          <td>${row.channel}</td>
          <td>${row.previous_position}</td>
          <td>${row.current_position}</td>
          <td>${row.status}</td>
        </tr>
      `).join("");
      table.innerHTML = `
        <thead>
          <tr>
            <th>Channel</th>
            <th>Previous Position</th>
            <th>Current Position</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>${tbodyRows}</tbody>
      `;
      tableWrap.appendChild(table);

      const summaryTitle = document.createElement("h4");
      summaryTitle.className = "nbhd-report-summary-title";
      summaryTitle.textContent = "Summary";
      const summaryList = document.createElement("ul");
      summaryList.className = "nbhd-report-list";
      reportData.rows.forEach((row) => {
        const item = document.createElement("li");
        item.textContent = row.summary;
        summaryList.appendChild(item);
      });

      section.append(header, tableWrap, summaryTitle, summaryList);
      reportContent.replaceChildren(section);
    } catch (error) {
      if (reportCount) reportCount.textContent = "0 narratives";
      renderReportStatus("Neighbour change report could not be generated.");
      reportContent.innerHTML = `<div class="nbhd-report-empty">Neighbour change report could not be generated.</div>`;
      console.error("NBHD report render failed", error);
    }
  }

  function resetReportFilters() {
    state.report.open = true;
    state.report.headend = "";
    state.report.week_from = "";
    state.report.week_to = "";
    renderReportPanel();
  }

  function openReportPanel() {
    state.report.open = true;
    setReportVisibility(true);
    reportContent.replaceChildren();
    renderReportStatus("");
    renderReportPanel();
    requestAnimationFrame(() => {
      reportPanel?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  function matchesRecord(record, filters, weeks) {
    const changeMeta = getRecordChangeMeta(record, weeks);
    if (filters.market && record.market !== filters.market) return false;
    if (filters.city && record.city !== filters.city) return false;
    if (filters.head_end && record.head_end !== filters.head_end) return false;
    if (filters.change === "Changed" && !changeMeta.changed) return false;
    if (filters.change === "No Change" && changeMeta.changed) return false;
    if (filters.change === "Increase" && !changeMeta.hasIncrease) return false;
    if (filters.change === "Decrease" && !changeMeta.hasDecrease) return false;
    return true;
  }

  function groupKey(record) {
    return `${record.market}||${record.city}||${record.head_end}`;
  }

  function sortGroupRecords(records) {
    return records.slice().sort((left, right) => Number(left.position || 0) - Number(right.position || 0));
  }

  function recordMatchesBaseFilters(record, filters) {
    if (filters.market && record.market !== filters.market) return false;
    if (filters.city && record.city !== filters.city) return false;
    if (filters.head_end && record.head_end !== filters.head_end) return false;
    return true;
  }

  function groupMatchesChangeFilter(records, changeFilter, weeks) {
    if (!changeFilter) return true;
    if (changeFilter === "No Change") {
      return records.every((record) => {
        const changeMeta = getRecordChangeMeta(record, weeks);
        return !changeMeta.changed && !changeMeta.hasIncrease && !changeMeta.hasDecrease;
      });
    }
    return records.some((record) => {
      const changeMeta = getRecordChangeMeta(record, weeks);
      if (changeFilter === "Changed") return changeMeta.changed;
      if (changeFilter === "Increase") return changeMeta.hasIncrease;
      if (changeFilter === "Decrease") return changeMeta.hasDecrease;
      return true;
    });
  }

  function filterGroupedRecords(allRecords, filters, weeks) {
    const baseRecords = allRecords.filter((record) => recordMatchesBaseFilters(record, filters));
    if (!filters.change) {
      return baseRecords;
    }

    const grouped = new Map();
    baseRecords.forEach((record) => {
      const key = groupKey(record);
      if (!grouped.has(key)) grouped.set(key, []);
      grouped.get(key).push(record);
    });

    const flattened = [];
    grouped.forEach((groupRecords) => {
      const sortedGroup = sortGroupRecords(groupRecords);
      if (groupMatchesChangeFilter(sortedGroup, filters.change, weeks)) {
        flattened.push(...sortedGroup);
      }
    });
    return flattened;
  }

  function buildStandalonePayload() {
    const source = window.__NBHD_STANDALONE_DATA__;
    const sourceTable = source.table || {};
    const allRecords = sourceTable.records || source.records || [];
    const visibleWeeks = getVisibleWeeks(source);
    const filtered = filterGroupedRecords(allRecords, state.filters, visibleWeeks);

    function optionsFor(key, field) {
      const scopedFilters = { ...state.filters, [key]: "" };
      return Array.from(new Set(
        filterGroupedRecords(allRecords, scopedFilters, visibleWeeks)
          .map((record) => record[field])
          .filter((value) => String(value || "").trim() !== "")
      )).sort((left, right) => left.localeCompare(right));
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
        total_headends: new Set(filtered.map((record) => groupKey(record))).size,
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

  function applyFilter(key, value) {
    state.filters[key] = value;
    if (key === "week_from" || key === "week_to") {
      const weeks = state.payload?.weeks || window.__NBHD_STANDALONE_DATA__?.weeks || [];
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

  function bindSelect(select, key) {
    if (!select?.button) return;
    select.button.addEventListener("click", (event) => {
      event.stopPropagation();
      const next = select.menu?.hidden ?? false;
      closeMenus();
      if (select.menu) select.menu.hidden = !next;
      if (next && select.search) {
        select.search.value = "";
        select.search.dispatchEvent(new Event("input"));
        requestAnimationFrame(() => select.search?.focus());
      }
    });
    if (select.search) {
      select.search.addEventListener("click", (event) => event.stopPropagation());
      select.search.addEventListener("input", () => {
        const source =
          key === "market" ? (state.payload?.filters.markets || []) :
          key === "city" ? (state.payload?.filters.cities || []) :
          key === "head_end" ? (state.payload?.filters.head_ends || []) :
          key === "change" ? ["Changed", "No Change", "Increase", "Decrease"] :
          getConstrainedWeekOptions(state.payload?.weeks || [], key);
        renderOptions(select, source, state.filters[key], key === "market" ? "All Markets" : key === "city" ? "All Cities" : key === "head_end" ? "All Headends" : key === "change" ? "All Changes" : key === "week_from" ? "From Week" : "To Week", (value) => applyFilter(key, value));
      });
    }
  }

  function bindReportSelect(control, renderOptionsForControl) {
    if (!control?.button) return;
    control.button.addEventListener("click", (event) => {
      event.stopPropagation();
      const next = control.menu?.hidden ?? false;
      closeMenus();
      if (control.menu) control.menu.hidden = !next;
      if (next && control.search) {
        control.search.value = "";
        renderOptionsForControl();
        requestAnimationFrame(() => control.search?.focus());
      }
    });
    if (control.search) {
      control.search.addEventListener("click", (event) => event.stopPropagation());
      control.search.addEventListener("input", renderOptionsForControl);
    }
  }

  function bindReportWeekSelect(control, key, placeholder) {
    if (!control?.button) return;
    const renderWeekOptions = () => {
      const values = getReportConstrainedWeekOptions(key);
      const selectedValue = state.report[key];
      renderOptions(control, values, selectedValue, placeholder, (value) => {
        state.report[key] = value;
        const weeks = getReportAvailableWeeks();
        const fromIndex = state.report.week_from && weeks.includes(state.report.week_from) ? weeks.indexOf(state.report.week_from) : -1;
        const toIndex = state.report.week_to && weeks.includes(state.report.week_to) ? weeks.indexOf(state.report.week_to) : -1;
        if (fromIndex >= 0 && toIndex >= 0 && fromIndex > toIndex) {
          if (key === "week_from") state.report.week_to = value;
          else state.report.week_from = value;
        }
        renderReportPanel();
        closeMenus();
      });
    };

    control.button.addEventListener("click", (event) => {
      event.stopPropagation();
      const next = control.menu?.hidden ?? false;
      closeMenus();
      if (control.menu) control.menu.hidden = !next;
      if (next) {
        renderWeekOptions();
        if (control.search) {
          control.search.value = "";
          requestAnimationFrame(() => control.search?.focus());
        }
      }
    });

    if (control.search) {
      control.search.addEventListener("click", (event) => event.stopPropagation());
      control.search.addEventListener("input", renderWeekOptions);
    }
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
      requestAnimationFrame(() => {
        state.pageSize = getPageSize();
        if (state.payload) {
          render(state.payload);
        }
        tableWrap.scrollTop = fullscreenState.tableScrollTop;
        tableWrap.scrollLeft = fullscreenState.tableScrollLeft;
      });
    } else {
      fullscreenState.tableScrollTop = tableWrap.scrollTop;
      fullscreenState.tableScrollLeft = tableWrap.scrollLeft;
      fullscreenState.active = false;
      document.body.classList.remove("nbhd-fullscreen-active");
      panel.classList.remove("nbhd-panel-fullscreen");
      requestAnimationFrame(() => {
        state.pageSize = getPageSize();
        if (state.payload) {
          render(state.payload);
        }
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
    state.filters.week_from = "";
    state.filters.week_to = "";
    state.filters.change = "";
    state.page = 1;
    fetchPayload(false);
  }

  bindSelect(marketFilter, "market");
  bindSelect(cityFilter, "city");
  bindSelect(headendFilter, "head_end");
  bindSelect(weekFromFilter, "week_from");
  bindSelect(weekToFilter, "week_to");
  bindSelect(changeFilter, "change");
  bindReportSelect(reportHeadendFilter, () => {
    renderOptions(
      reportHeadendFilter,
      buildReportContext().headends,
      state.report.headend,
      "Select Headend",
      (value) => {
        state.report.headend = value;
        renderReportPanel();
        closeMenus();
      }
    );
  });
  bindReportWeekSelect(reportWeekFromFilter, "week_from", "Previous Week");
  bindReportWeekSelect(reportWeekToFilter, "week_to", "Current Week");
  document.addEventListener("click", (event) => {
    if (!event.target.closest(".filter-select") && !event.target.closest(".ots-multiselect")) closeMenus();
  });
  if (refreshButton) {
    refreshButton.addEventListener("click", () => fetchPayload(true));
  }
  if (resetButton) {
    resetButton.addEventListener("click", resetFilters);
  }
  if (reportToggleButton) {
    reportToggleButton.addEventListener("click", openReportPanel);
  }
  if (reportHideButton) {
    reportHideButton.addEventListener("click", closeReportPanel);
  }
  if (reportResetButton) {
    reportResetButton.addEventListener("click", resetReportFilters);
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
  if (state.initial) {
    render(normalizePayloadShape(state.initial));
  }
  syncFullscreenButtons();
  fetchPayload(false);
})();


