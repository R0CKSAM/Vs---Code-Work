(function () {
  const root = document.getElementById("nbhdTable");
  if (!root) return;
  const NO_DATA_LABEL = "NA";
  const DEFAULT_VISIBLE_WEEK_COUNT = 4;

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
    hasCustomWeekRange: false,
    page: 1,
    pageSize: 30,
    loading: false,
    standalone: Boolean(window.__NBHD_STANDALONE_DATA__),
    initial: window.__NBHD_INITIAL_DATA__ || window.__NBHD_STANDALONE_DATA__ || null,
    report: {
      open: false,
      headend: "",
      channel: "",
      week_from: "",
      week_to: "",
    },
    comparisonReport: {
      open: false,
    },
    reportCache: {
      context: null,
      lastPayload: null,
      narratives: null,
      narrativesForDownload: null,
      lastHeadend: "",
      lastWeeks: [],
      lastChannel: "",
      lastWeeksForDownload: [],
      lastHeadendForDownload: "",
      lastChannelForDownload: "",
      headendsWithChanges: null,
      channelsWithChanges: null,
      lastReportWeeks: [],
    },
  };

  const DEFAULT_REPORT_CHANNELS = [
    { label: "INDIA TV", key: "INDIATV" },
    { label: "AAJ TAK", key: "AAJTAK" },
    { label: "NEWS 18 INDIA", key: "NEWS18INDIA" },
    { label: "REPUBLIC BHARAT", key: "REPUBLICBHARAT" },
  ];
  const DEFAULT_REPORT_CHANNEL_KEYS = DEFAULT_REPORT_CHANNELS.map((channel) => channel.key);
  const INDIA_TV_CHANNEL_KEY = "INDIATV";

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
  const comparisonReportToggleButton = document.getElementById("nbhdComparisonReportToggleButton");
  const reportLauncher = document.getElementById("nbhdReportLauncher");
  const reportPanel = document.getElementById("nbhdReportPanel");
  const reportMeta = document.getElementById("nbhdReportMeta");
  const reportCount = document.getElementById("nbhdReportCount");
  const reportStatus = document.getElementById("nbhdReportStatusMessage");
  const reportContent = document.getElementById("nbhdReportContent");
  const comparisonReportPanel = document.getElementById("nbhdComparisonReportPanel");
  const comparisonReportMeta = document.getElementById("nbhdComparisonReportMeta");
  const comparisonReportCount = document.getElementById("nbhdComparisonReportCount");
  const comparisonReportStatus = document.getElementById("nbhdComparisonReportStatusMessage");
  const comparisonReportContent = document.getElementById("nbhdComparisonReportContent");
  const comparisonReportDownloadButton = document.getElementById("nbhdComparisonReportDownloadButton");
  const comparisonReportHideButton = document.getElementById("nbhdComparisonReportHideButton");
  const reportHeadendFilter = getSingleSelectControl("nbhdReportHeadendFilter");
  const reportChannelFilter = getSingleSelectControl("nbhdReportChannelFilter");
  const reportWeekFromFilter = getSingleSelectControl("nbhdReportWeekFromFilter");
  const reportWeekToFilter = getSingleSelectControl("nbhdReportWeekToFilter");
  const reportResetButton = document.getElementById("nbhdReportResetButton");
  const reportHideButton = document.getElementById("nbhdReportHideButton");
  const reportDownloadButton = document.getElementById("nbhdReportDownloadButton");
  const tableDownloadButton = document.getElementById("nbhdDownloadButton");
  const resultCount = document.getElementById("nbhdResultCount");
  const tableHead = document.getElementById("nbhdTableHead");
  const tableBody = document.getElementById("nbhdTableBody");
  const statusMessage = document.getElementById("nbhdStatusMessage");
  const refreshButton = document.getElementById("nbhdRefreshButton");
  const resetButton = document.getElementById("nbhdResetButton");
  const fullscreenButton = document.getElementById("nbhdFullscreenButton");
  const exitFullscreenButton = document.getElementById("nbhdExitFullscreenButton");
  const pageInfo = document.getElementById("nbhdPageInfo");
  const scrollHint = document.getElementById("nbhdScrollHint");
  const tableWrap = root.closest(".nbhd-table-wrap");
  const panel = root.closest(".nbhd-panel");
  const fullscreenState = {
    active: false,
    windowScrollY: 0,
    tableScrollTop: 0,
    tableScrollLeft: 0,
    usingNativeFullscreen: false,
  };
  let renderFrame = null;
  let reportRenderTimeout = null;
  let lazyRenderPending = false;

  function scheduleRender(payload = state.payload) {
    if (renderFrame !== null) return;
    renderFrame = window.requestAnimationFrame(() => {
      renderFrame = null;
      render(payload);
    });
  }

  function getVisibleRowCount(totalCount) {
    return Math.min(totalCount, Math.max(1, state.page) * state.pageSize);
  }

  function updateLazyScrollHint(visibleCount, totalCount) {
    if (!scrollHint) return;
    if (totalCount > visibleCount) {
      scrollHint.textContent = `Scroll to load more (${new Intl.NumberFormat().format(visibleCount)} of ${new Intl.NumberFormat().format(totalCount)} visible)`;
      return;
    }
    scrollHint.textContent = totalCount ? `All ${new Intl.NumberFormat().format(totalCount)} rows loaded` : "No rows";
  }

  function maybeLoadMoreRows(force = false) {
    if (!tableWrap || lazyRenderPending || !state.payload) return;
    const pages = paginateGroupedRecords(state.payload.table.records || []);
    const totalCount = pages.reduce((sum, page) => sum + page.length, 0);
    const visibleCount = getVisibleRowCount(totalCount);
    if (visibleCount >= totalCount) return;
    const nearBottom = tableWrap.scrollTop + tableWrap.clientHeight >= tableWrap.scrollHeight - 160;
    const underfilled = tableWrap.scrollHeight <= tableWrap.clientHeight + 40;
    if (!force && !nearBottom && !underfilled) return;
    lazyRenderPending = true;
    state.page += 1;
    scheduleRender(state.payload);
    lazyRenderPending = false;
  }

  function isReportCacheValid() {
    const currentHeadend = normalizeText(state.report.headend);
    const currentWeeks = [state.report.week_from, state.report.week_to].filter(Boolean);
    const currentChannel = normalizeText(state.report.channel);
    
    return state.reportCache.context !== null &&
           state.reportCache.lastHeadend === currentHeadend &&
           JSON.stringify(state.reportCache.lastWeeks) === JSON.stringify(currentWeeks) &&
           state.reportCache.lastChannel === currentChannel;
  }

  function getHeadendsAndChannelsWithChanges() {
    // Check cache first
    const currentReportWeeks = [state.report.week_from, state.report.week_to].filter(Boolean);
    if (state.reportCache.headendsWithChanges !== null && 
        state.reportCache.channelsWithChanges !== null &&
        state.payload === state.reportCache.lastPayload &&
        JSON.stringify(state.reportCache.lastReportWeeks) === JSON.stringify(currentReportWeeks)) {
      return {
        headends: state.reportCache.headendsWithChanges,
        channels: state.reportCache.channelsWithChanges
      };
    }
    
    const payload = normalizePayloadShape(state.payload || window.__NBHD_STANDALONE_DATA__ || { weeks: [] });
    const allWeeks = payload.weeks || [];
    
    if (allWeeks.length < 2) {
      // Need at least 2 weeks to detect changes
      const result = { headends: [], channels: [] };
      state.reportCache.headendsWithChanges = result.headends;
      state.reportCache.channelsWithChanges = result.channels;
      state.reportCache.lastPayload = state.payload;
      state.reportCache.lastReportWeeks = currentReportWeeks;
      return result;
    }
    
    // Use the report's selected weeks, or last two weeks if none selected
    const reportWeeks = [state.report.week_from, state.report.week_to].filter(Boolean);
    const previousWeek = reportWeeks.length >= 2 ? reportWeeks[0] : (allWeeks.length >= 2 ? allWeeks[allWeeks.length - 2] : null);
    const currentWeek = reportWeeks.length >= 2 ? reportWeeks[reportWeeks.length - 1] : (allWeeks.length >= 1 ? allWeeks[allWeeks.length - 1] : null);
    
    // If we don't have valid weeks, return empty
    if (!previousWeek || !currentWeek) {
      const result = { headends: [], channels: [] };
      state.reportCache.headendsWithChanges = result.headends;
      state.reportCache.channelsWithChanges = result.channels;
      state.reportCache.lastPayload = state.payload;
      state.reportCache.lastReportWeeks = currentReportWeeks;
      return result;
    }
    
    const baseRecords = getAllSourceRecords();
    const headendsWithChanges = new Set();
    const channelsWithChanges = new Set();
    const targetChannels = getReportTargetChannels(); // Only check the 4 default channels
    
    // Group records by headend for efficient processing
    const headendGroups = new Map();
    baseRecords.forEach((record) => {
      const headend = normalizeText(record.head_end);
      if (!headend) return;
      if (!headendGroups.has(headend)) headendGroups.set(headend, []);
      headendGroups.get(headend).push(record);
    });
    
    // Check each headend for changes - only for the 4 default channels
    for (const [headend, groupRecords] of headendGroups.entries()) {
      const previousMap = buildHeadendMaps(groupRecords, previousWeek);
      const currentMap = buildHeadendMaps(groupRecords, currentWeek);
      
      let headendHasChanges = false;
      
      // Only check the 4 default channels for changes
      for (const { label, key } of targetChannels) {
        const previousPosition = previousMap.channelPositions.get(key);
        const currentPosition = currentMap.channelPositions.get(key);
        
        if (previousPosition === undefined || currentPosition === undefined) continue;
        
        const previousLower = neighborAt(previousMap, previousPosition, -1);
        const previousUpper = neighborAt(previousMap, previousPosition, 1);
        const currentLower = neighborAt(currentMap, currentPosition, -1);
        const currentUpper = neighborAt(currentMap, currentPosition, 1);
        
        // If neighbors changed, this channel has a change
        if (previousLower !== currentLower || previousUpper !== currentUpper) {
          headendHasChanges = true;
          channelsWithChanges.add(label);
        }
      }
      
      if (headendHasChanges) {
        headendsWithChanges.add(headend);
      }
    }
    
    const result = {
      headends: Array.from(headendsWithChanges).sort((a, b) => a.localeCompare(b, undefined, { numeric: true })),
      channels: Array.from(channelsWithChanges).sort((a, b) => a.localeCompare(b, undefined, { numeric: true }))
    };
    
    // Cache the result
    state.reportCache.headendsWithChanges = result.headends;
    state.reportCache.channelsWithChanges = result.channels;
    state.reportCache.lastPayload = state.payload;
    state.reportCache.lastReportWeeks = currentReportWeeks;
    
    return result;
  }

  function invalidateReportCache() {
    state.reportCache = {
      context: null,
      lastPayload: null,
      narratives: null,
      narrativesForDownload: null,
      lastHeadend: "",
      lastWeeks: [],
      lastChannel: "",
      lastWeeksForDownload: [],
      lastHeadendForDownload: "",
      lastChannelForDownload: "",
      headendsWithChanges: null,
      channelsWithChanges: null,
      lastReportWeeks: [],
    };
  }

  setReportVisibility(false);

  function normalizeText(value) {
    return String(value ?? "").replace(/\s+/g, " ").trim();
  }

  function normalizePayloadShape(payload) {
    if (!payload || typeof payload !== "object") {
      return {
        generated_at: "",
        weeks: [],
        visible_weeks: [],
        filters: { markets: [], cities: [], head_ends: [] },
        table: { records: [], total_count: 0 },
        message: "",
        source_directory: "",
      };
    }

    const records = Array.isArray(payload.table?.records)
      ? payload.table.records
      : Array.isArray(payload.records) ? payload.records : [];
    const markets = Array.from(new Set(records.map((record) => record.market).filter((value) => String(value || "").trim() !== "")))
      .sort((left, right) => left.localeCompare(right, undefined, { numeric: true }));
    const cities = Array.from(new Set(records.map((record) => record.city).filter((value) => String(value || "").trim() !== "")))
      .sort((left, right) => left.localeCompare(right, undefined, { numeric: true }));
    const headends = Array.from(new Set(records.map((record) => record.head_end).filter((value) => String(value || "").trim() !== "")))
      .sort((left, right) => left.localeCompare(right, undefined, { numeric: true }));

    return {
      ...payload,
      weeks: Array.isArray(payload.weeks) ? payload.weeks : [],
      visible_weeks: Array.isArray(payload.visible_weeks) ? payload.visible_weeks.filter((value) => String(value || "").trim() !== "") : [],
      filters: {
        ...(payload.filters || {}),
        markets: Array.isArray(payload.filters?.markets) ? payload.filters.markets : markets,
        cities: Array.isArray(payload.filters?.cities) ? payload.filters.cities : cities,
        head_ends: Array.isArray(payload.filters?.head_ends) ? payload.filters.head_ends : headends,
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
      reportChannelFilter,
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
    if (payload.visible_weeks?.length) {
      return payload.visible_weeks.filter((week) => allWeeks.includes(week));
    }
    return allWeeks.slice(Math.max(0, allWeeks.length - DEFAULT_VISIBLE_WEEK_COUNT));
  }

  function syncDefaultWeekFilters(payload) {
    const allWeeks = payload?.weeks || [];
    if (!allWeeks.length) {
      state.filters.week_from = "";
      state.filters.week_to = "";
      state.hasCustomWeekRange = false;
      return;
    }

    const latestWeeks = payload?.visible_weeks?.length
      ? payload.visible_weeks.filter((week) => allWeeks.includes(week))
      : allWeeks.slice(Math.max(0, allWeeks.length - DEFAULT_VISIBLE_WEEK_COUNT));
    const defaultFrom = latestWeeks[0] || "";
    const defaultTo = latestWeeks[latestWeeks.length - 1] || defaultFrom;
    const hasValidFrom = state.filters.week_from && allWeeks.includes(state.filters.week_from);
    const hasValidTo = state.filters.week_to && allWeeks.includes(state.filters.week_to);

    if (!state.hasCustomWeekRange) {
      state.filters.week_from = defaultFrom;
      state.filters.week_to = defaultTo;
      return;
    }

    if (!hasValidFrom && !hasValidTo) {
      state.hasCustomWeekRange = false;
      state.filters.week_from = defaultFrom;
      state.filters.week_to = defaultTo;
      return;
    }

    if (!hasValidFrom) {
      state.filters.week_from = hasValidTo ? state.filters.week_to : defaultFrom;
    }
    if (!hasValidTo) {
      state.filters.week_to = hasValidFrom ? state.filters.week_from : defaultTo;
    }
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
    const previousMissing = previousRaw === null || previousRaw === undefined || previousRaw === "" || previousRaw === NO_DATA_LABEL;
    const currentMissing = currentRaw === null || currentRaw === undefined || currentRaw === "" || currentRaw === NO_DATA_LABEL;
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
      { label: "Channel", key: "channels", className: "nbhd-group-channel" },
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
        const textVal = value === null || value === undefined || value === "" ? NO_DATA_LABEL : String(value);
        td.textContent = textVal;
        const groupEdgeClass = weekIndex === 0 ? "nbhd-group-start" : "";
        td.className = `${groupConfig.className} ${groupEdgeClass}`.trim();
        if (textVal === NO_DATA_LABEL || textVal === "NA") {
          td.classList.add("cell-na", "status-missing", "nbhd-cell-empty");
        }
        if (groupConfig.key === "channels") {
          const current = String(value || "").trim();
          const previousWeek = weekIndex > 0 ? weeks[weekIndex - 1] : "";
          const previous = previousWeek ? String(record[groupConfig.key][previousWeek] || "").trim() : "";
          if (normalizeChannelKey(current) === "INDIATV") {
            td.classList.add("nbhd-cell-india");
          } else if (weekIndex > 0 && current && current !== NO_DATA_LABEL && !previous) {
            td.classList.add("nbhd-cell-new");
          } else if (weekIndex > 0 && current && previous && current !== previous) {
            td.classList.add("nbhd-cell-changed");
          }
        }
        if (groupConfig.key === "frequencies") {
          const currentValue = value === null || value === undefined || value === "" || value === NO_DATA_LABEL ? null : Number(value);
          const previousWeek = weekIndex > 0 ? weeks[weekIndex - 1] : "";
          const previousRaw = previousWeek ? record[groupConfig.key][previousWeek] : null;
          const previousValue = previousRaw === null || previousRaw === undefined || previousRaw === "" || previousRaw === NO_DATA_LABEL ? null : Number(previousRaw);
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
      return `${record.market}||${record.city}||${record.head_end}||${record.group_index || 1}`;
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
      pageInfo.textContent = "Showing 0 of 0";
      updateLazyScrollHint(0, 0);
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
    const flatRecords = pages.flat();
    const visibleCount = getVisibleRowCount(flatRecords.length);
    const pageRecords = flatRecords.slice(0, visibleCount);
    pageInfo.textContent = `Showing ${new Intl.NumberFormat().format(pageRecords.length)} of ${new Intl.NumberFormat().format(flatRecords.length)}`;
    updateLazyScrollHint(pageRecords.length, flatRecords.length);

    const fragment = document.createDocumentFragment();
    pageRecords.forEach((record) => fragment.appendChild(buildRow(record, weeks)));
    tableBody.replaceChildren(fragment);
  }

  function render(payload) {
    state.payload = normalizePayloadShape(payload);
    state.pageSize = getPageSize();
    syncDefaultWeekFilters(state.payload);
    
    // Invalidate report cache when new data is loaded
    invalidateReportCache();
    
    syncFilters(state.payload);
    renderStatus(state.payload);
    resultCount.textContent = `${new Intl.NumberFormat().format(state.payload.table.total_count)} rows`;
    renderTable(state.payload);
    window.requestAnimationFrame(() => maybeLoadMoreRows());
    renderReportPanel();
    renderComparisonReportPanel();
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

  function getReportTargetChannels() {
    const selectedChannel = normalizeText(state.report.channel);
    if (selectedChannel) {
      return [{ label: selectedChannel, key: normalizeChannelKey(selectedChannel) }];
    }
    return DEFAULT_REPORT_CHANNELS;
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

  function getChangedReportHeadends(records, weeks, channels = DEFAULT_REPORT_CHANNELS) {
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
      for (const { key } of channels) {
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
    if (state.report.headend && !context.headends.includes(state.report.headend)) {
      state.report.headend = "";
    }
    if (!state.report.headend && context.headends.length) {
      state.report.headend = getPreferredReportHeadend(
        getAllSourceRecords(),
        context.activeWeeks,
        state.report.channel ? [state.report.channel] : DEFAULT_REPORT_CHANNELS.map((channel) => channel.label)
      );
      if (!context.headends.includes(state.report.headend)) {
        state.report.headend = context.headends[0];
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
    // Use cached context if available and payload hasn't changed
    if (state.reportCache.context !== null && state.payload === state.reportCache.lastPayload) {
      return state.reportCache.context;
    }
    
    const records = getAllSourceRecords();
    const allWeeks = getReportAvailableWeeks();
    const activeWeeks = getContextReportWeeks(allWeeks);
    
    // Get headends and channels with changes for filters
    const { headends, channels } = getHeadendsAndChannelsWithChanges();
    
    const context = {
      headends: headends.length > 0 ? headends : getReportHeadends(records),
      channels: channels.length > 0 ? channels : getAllReportChannels(records),
      allWeeks,
      activeWeeks,
    };
    
    // Cache the context
    state.reportCache.context = context;
    state.reportCache.lastPayload = state.payload;
    
    return context;
  }

  function renderReportFilters(context) {
    state.report.headend = populateSelect(
      reportHeadendFilter,
      context.headends,
      "All Headends",
      state.report.headend,
      (value) => {
        state.report.headend = value;
        renderReportPanel();
      }
    );
    state.report.channel = populateSelect(
      reportChannelFilter,
      context.channels,
      "Default 4 Channels",
      state.report.channel,
      (value) => {
        state.report.channel = value;
        renderReportPanel();
      }
    );
    state.report.week_from = populateSelect(
      reportWeekFromFilter,
      getReportConstrainedWeekOptions("week_from"),
      "Week From",
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
      "Week To",
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
    const genresByPosition = new Map();
    const channelPositions = new Map();
    const frequenciesByPosition = new Map();
    const positions = [];
    records.forEach((record) => {
      const channel = normalizeText(record.channels?.[week]);
      const position = Number(record.position);
      if (!channel || Number.isNaN(position)) return;
      byPosition.set(position, channel);
      genresByPosition.set(position, normalizeText(record.genres?.[week]));
      frequenciesByPosition.set(position, record.frequencies?.[week]);
      channelPositions.set(normalizeChannelKey(channel), position);
      positions.push(position);
    });
    positions.sort((left, right) => left - right);
    return { byPosition, genresByPosition, channelPositions, frequenciesByPosition, positions };
  }

  function getAdjacentPosition(mapState, position, offset) {
    const positions = Array.isArray(mapState?.positions) ? mapState.positions : [];
    if (!positions.length || Number.isNaN(Number(position))) return null;
    if (offset < 0) {
      for (let index = positions.length - 1; index >= 0; index -= 1) {
        if (positions[index] < position) return positions[index];
      }
      return null;
    }
    for (let index = 0; index < positions.length; index += 1) {
      if (positions[index] > position) return positions[index];
    }
    return null;
  }

  function neighborAt(mapState, position, offset) {
    const adjacentPosition = getAdjacentPosition(mapState, position, offset);
    if (adjacentPosition === null || adjacentPosition === undefined) return "NA";
    return normalizeText(mapState.byPosition.get(adjacentPosition)) || "NA";
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
      const hideLauncher = open || state.comparisonReport.open;
      reportLauncher.hidden = hideLauncher;
      reportLauncher.style.display = hideLauncher ? "none" : "flex";
    }
  }
  function setComparisonReportVisibility(open) {
    state.comparisonReport.open = open;
    if (comparisonReportPanel) {
      comparisonReportPanel.hidden = !open;
      comparisonReportPanel.style.display = open ? "block" : "none";
    }
    if (reportLauncher) {
      const hideLauncher = open || state.report.open;
      reportLauncher.hidden = hideLauncher;
      reportLauncher.style.display = hideLauncher ? "none" : "flex";
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
    scheduleRender(state.payload);
    requestAnimationFrame(() => {
      reportLauncher?.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  }
  function closeComparisonReportPanel() {
    state.comparisonReport.open = false;
    setComparisonReportVisibility(false);
    scheduleRender(state.payload);
    requestAnimationFrame(() => {
      reportLauncher?.scrollIntoView({ behavior: "smooth", block: "center" });
    });
  }
  function exportTableExcel() {
    const payload = normalizePayloadShape(state.payload || window.__NBHD_STANDALONE_DATA__ || { weeks: [] });
    const weeks = getVisibleWeeks(payload);
    const records = payload.table?.records || [];
    const excelCell = window.__excelCell || ((value, style = "cell", options = {}) => ({ value, style, ...options }));
    const blankRow = window.__blankExcelRow || ((count = 1) => Array.from({ length: Math.max(1, count) }, () => excelCell("", "cell")));
    const reportData = buildReportNarrativesForDownload();
    const totalHeadends = new Set(records.map((r) => String(r.head_end || "").trim()).filter(Boolean)).size;
    const exportedAt = new Date().toLocaleString("en-IN", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false });

    // ── Sheet 1: Detailed Report ──────────────────────────────────────────
    const colCount = 3 + weeks.length * 3;
    const detailRows = [
      [excelCell("Neighbourhood Comparison – Detailed Report", "title", { mergeAcross: colCount - 1 })],
      [excelCell(`Exported: ${exportedAt}  |  Headends: ${totalHeadends}  |  Rows: ${records.length}`, "meta", { mergeAcross: colCount - 1 })],
      blankRow(colCount),
      [
        excelCell("", "group", { mergeAcross: 2 }),
        excelCell("Channel", "group", { mergeAcross: Math.max(0, weeks.length - 1) }),
        excelCell("Frequency", "group", { mergeAcross: Math.max(0, weeks.length - 1) }),
        excelCell("Genre", "group", { mergeAcross: Math.max(0, weeks.length - 1) }),
      ],
      [
        excelCell("MARKET", "header"),
        excelCell("CITY", "header"),
        excelCell("HEADEND", "header"),
        ...weeks.map((week) => excelCell(week, "header")),
        ...weeks.map((week) => excelCell(week, "header")),
        ...weeks.map((week) => excelCell(week, "header")),
      ],
    ];
    function getFrequencyStyle(index, values) {
      const week = weeks[index];
      const currentValue = values?.[week];
      const currentMissing = currentValue === null || currentValue === undefined || currentValue === "";
      if (index <= 0) return currentMissing ? "cell" : "number";
      const previousValue = values?.[weeks[index - 1]];
      const previousMissing = previousValue === null || previousValue === undefined || previousValue === "";
      if (previousMissing && currentMissing) return "cell";
      if (previousMissing && !currentMissing) return "positive";
      if (!previousMissing && currentMissing) return "negative";
      if (Number(currentValue) > Number(previousValue)) return "positive";
      if (Number(currentValue) < Number(previousValue)) return "negative";
      return "number";
    }
    function getTextChangeStyle(index, values) {
      const week = weeks[index];
      const currentValue = values?.[week];
      const currentMissing = currentValue === null || currentValue === undefined || currentValue === "";
      if (index <= 0) return "cell";
      const previousValue = values?.[weeks[index - 1]];
      const previousMissing = previousValue === null || previousValue === undefined || previousValue === "";
      if (previousMissing && currentMissing) return "cell";
      if (previousMissing && !currentMissing) return "positive";
      if (!previousMissing && currentMissing) return "negative";
      if (String(previousValue) !== String(currentValue)) return "highlight";
      return "cell";
    }
    records.forEach((record, recordIndex) => {
      const rowStyle = "cell";
      detailRows.push([
        excelCell(record.market || "", rowStyle),
        excelCell(record.city || "", rowStyle),
        excelCell(record.head_end || "", rowStyle),
        ...weeks.map((week, weekIndex) => {
          const value = record.channels?.[week];
          const textVal = value === null || value === undefined || value === "" ? "NA" : String(value);
          return excelCell(textVal, getTextChangeStyle(weekIndex, record.channels || {}));
        }),
        ...weeks.map((week, weekIndex) => {
          const value = record.frequencies?.[week];
          return excelCell(value ?? "NA", getFrequencyStyle(weekIndex, record.frequencies || {}));
        }),
        ...weeks.map((week, weekIndex) => excelCell(record.genres?.[week] ?? "NA", getTextChangeStyle(weekIndex, record.genres || {}))),
      ]);
    });

    // ── Sheet 2: Summary Report ───────────────────────────────────────────
    const weekFrom = reportData.weeks?.[0] || "";
    const weekTo = reportData.weeks?.[reportData.weeks.length - 1] || "";
    const changedHeadends = new Set(reportData.rows.map((r) => r.headend)).size;
    const reportRows = [
      [excelCell("Neighbourhood Report – Summary", "title", { mergeAcross: 5 })],
      [excelCell(`Exported: ${exportedAt}`, "meta", { mergeAcross: 5 })],
      blankRow(6),
      [excelCell("Report Scope", "group", { mergeAcross: 5 })],
      [excelCell("Comparison Period", "header"), excelCell(weekFrom && weekTo ? `${weekFrom}  →  ${weekTo}` : "All available weeks", "cell", { mergeAcross: 4 })],
      [excelCell("Headend Filter", "header"), excelCell(reportData.headend || "All Headends", "cell", { mergeAcross: 4 })],
      [excelCell("Channel Filter", "header"), excelCell(reportData.channel || "Default 4 Channels (India TV, Aaj Tak, News 18, Republic Bharat)", "cell", { mergeAcross: 4 })],
      blankRow(6),
      [excelCell("Statistics", "group", { mergeAcross: 5 })],
      [excelCell("Total Neighbour Changes", "header"), excelCell(reportData.totalRows, "number", { mergeAcross: 4 })],
      [excelCell("Headends with Changes", "header"), excelCell(changedHeadends, "number", { mergeAcross: 4 })],
      blankRow(6),
      [excelCell("Neighbour Change Details", "group", { mergeAcross: 5 })],
      [
        excelCell("Headend", "header"),
        excelCell("Channel", "header"),
        excelCell("Previous Position", "header"),
        excelCell("Current Position", "header"),
        excelCell("Status", "header"),
        excelCell("Summary", "header"),
      ],
    ];
    if (!reportData.rows.length) {
      reportRows.push(blankRow(6));
      reportRows.push([excelCell("However, no neighbourhood change.", "textWrap", { mergeAcross: 5 })]);
      reportRows.push(blankRow(6));
    }
    if (reportData.rows.length) {
      reportData.rows.forEach((row, rowIndex) => {
        const isAlt = rowIndex % 2 === 1;
        const rowStyle = isAlt ? "altRow" : "cell";
        reportRows.push([
          excelCell(row.headend, rowStyle),
          excelCell(row.channel, rowStyle),
          excelCell(row.previous_position, isAlt ? "altRowWrap" : "textWrap"),
          excelCell(row.current_position, isAlt ? "altRowWrap" : "textWrap"),
          excelCell(row.status, "positive"),
          excelCell(row.summary, isAlt ? "altRowWrap" : "textWrap"),
        ]);
      });
    } else {
      reportRows.push([
        excelCell("", "cell"),
        excelCell("", "cell"),
        excelCell("", "cell"),
        excelCell("", "cell"),
        excelCell("", "cell"),
        excelCell(reportData.message || "No neighbour change report data available.", "textWrap"),
      ]);
    }

    window.__downloadExcelWorkbook?.("neighbourhood_report", [
      {
        name: "Detailed Report",
        columns: [190, 150, 220, ...weeks.map(() => 160), ...weeks.map(() => 85), ...weeks.map(() => 145)],
        rows: detailRows,
      },
      {
        name: "Summary Report",
        columns: [200, 160, 290, 290, 110, 450],
        rows: reportRows,
      },
    ]);
  }
  function exportReportExcel() {
    const reportData = buildReportNarrativesForDownload();
    const excelCell = window.__excelCell || ((value, style = "cell", options = {}) => ({ value, style, ...options }));
    const blankRow = window.__blankExcelRow || ((count = 1) => Array.from({ length: Math.max(1, count) }, () => excelCell("", "cell")));
    const weekFrom = reportData.weeks?.[0] || "";
    const weekTo = reportData.weeks?.[reportData.weeks.length - 1] || "";
    const changedHeadends = new Set(reportData.rows.map((r) => r.headend)).size;
    const exportedAt = new Date().toLocaleString("en-IN", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", hour12: false });
    const reportRows = [
      [excelCell("Neighbourhood Report – Summary", "title", { mergeAcross: 5 })],
      [excelCell(`Exported: ${exportedAt}`, "meta", { mergeAcross: 5 })],
      blankRow(6),
      [excelCell("Report Scope", "group", { mergeAcross: 5 })],
      [excelCell("Comparison Period", "header"), excelCell(weekFrom && weekTo ? `${weekFrom}  →  ${weekTo}` : "All available weeks", "cell", { mergeAcross: 4 })],
      [excelCell("Headend Filter", "header"), excelCell(reportData.headend || "All Headends", "cell", { mergeAcross: 4 })],
      [excelCell("Channel Filter", "header"), excelCell(reportData.channel || "Default 4 Channels (India TV, Aaj Tak, News 18, Republic Bharat)", "cell", { mergeAcross: 4 })],
      blankRow(6),
      [excelCell("Statistics", "group", { mergeAcross: 5 })],
      [excelCell("Total Neighbour Changes", "header"), excelCell(reportData.totalRows, "number", { mergeAcross: 4 })],
      [excelCell("Headends with Changes", "header"), excelCell(changedHeadends, "number", { mergeAcross: 4 })],
      blankRow(6),
      [excelCell("Neighbour Change Details", "group", { mergeAcross: 5 })],
      [
        excelCell("Headend", "header"),
        excelCell("Channel", "header"),
        excelCell("Previous Position", "header"),
        excelCell("Current Position", "header"),
        excelCell("Status", "header"),
        excelCell("Summary", "header"),
      ],
    ];
    if (!reportData.rows.length) {
      reportRows.push(blankRow(6));
      reportRows.push([excelCell("However, no neighbourhood change.", "textWrap", { mergeAcross: 5 })]);
      reportRows.push(blankRow(6));
    }
    if (reportData.rows.length) {
      reportData.rows.forEach((row, rowIndex) => {
        const isAlt = rowIndex % 2 === 1;
        const rowStyle = isAlt ? "altRow" : "cell";
        reportRows.push([
          excelCell(row.headend, rowStyle),
          excelCell(row.channel, rowStyle),
          excelCell(row.previous_position, isAlt ? "altRowWrap" : "textWrap"),
          excelCell(row.current_position, isAlt ? "altRowWrap" : "textWrap"),
          excelCell(row.status, "positive"),
          excelCell(row.summary, isAlt ? "altRowWrap" : "textWrap"),
        ]);
      });
    } else {
      reportRows.push([
        excelCell("", "cell"),
        excelCell("", "cell"),
        excelCell("", "cell"),
        excelCell("", "cell"),
        excelCell("", "cell"),
        excelCell(reportData.message || "No report data available.", "textWrap"),
      ]);
    }
    window.__downloadExcelWorkbook?.("neighbourhood_change_report", [
      {
        name: "Summary Report",
        columns: [200, 160, 290, 290, 110, 450],
        rows: reportRows,
      },
    ]);
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
    
    const selectedHeadend = normalizeText(state.report.headend);
    const selectedChannel = normalizeText(state.report.channel);
    const currentWeeks = [weekFrom, weekTo].filter(Boolean);
    
    if (isReportCacheValid() && state.reportCache.narratives !== null) {
      return state.reportCache.narratives;
    }

    if (weeks.length < 2) {
      const result = {
        weeks,
        headend: selectedHeadend,
        channel: selectedChannel,
        rows: [],
        totalRows: 0,
        message: "Select previous and current week in the report filters to generate the neighbour change report.",
      };
      state.reportCache.narratives = result;
      state.reportCache.lastHeadend = selectedHeadend;
      state.reportCache.lastWeeks = currentWeeks;
      state.reportCache.lastChannel = selectedChannel;
      return result;
    }

    const previousWeek = weeks[0];
    const currentWeek = weeks[weeks.length - 1];
    const baseRecords = getAllSourceRecords();
    const groupedRecords = new Map();
    baseRecords.forEach((record) => {
      const headend = normalizeText(record.head_end);
      if (!headend || (selectedHeadend && headend !== selectedHeadend)) return;
      if (!groupedRecords.has(headend)) groupedRecords.set(headend, []);
      groupedRecords.get(headend).push(record);
    });

    if (!groupedRecords.size) {
      const result = {
        weeks,
        headend: selectedHeadend,
        channel: selectedChannel,
        rows: [],
        totalRows: 0,
        message: "No headend data is available for the selected report filters.",
      };
      state.reportCache.narratives = result;
      state.reportCache.lastHeadend = selectedHeadend;
      state.reportCache.lastWeeks = currentWeeks;
      state.reportCache.lastChannel = selectedChannel;
      return result;
    }

    const rows = [];
    const targetChannels = getReportTargetChannels();
    const allAvailableChannels = new Map();
    for (const [headend, groupRecords] of groupedRecords.entries()) {
      getReportChannelOptions(groupRecords).forEach((value) => {
        const key = normalizeChannelKey(value);
        if (!allAvailableChannels.has(key)) {
          allAvailableChannels.set(key, normalizeText(value));
        }
      });
    }

    for (const [headend, groupRecords] of groupedRecords.entries()) {
      const previousMap = buildHeadendMaps(groupRecords, previousWeek);
      const currentMap = buildHeadendMaps(groupRecords, currentWeek);

      targetChannels.forEach(({ label, key }) => {
        const channelLabel = allAvailableChannels.get(key) || label;
        const previousPosition = previousMap.channelPositions.get(key);
        const currentPosition = currentMap.channelPositions.get(key);
        if (previousPosition === undefined || currentPosition === undefined) return;

        const previousLower = neighborAt(previousMap, previousPosition, -1);
        const previousUpper = neighborAt(previousMap, previousPosition, 1);
        const currentLower = neighborAt(currentMap, currentPosition, -1);
        const currentUpper = neighborAt(currentMap, currentPosition, 1);
        if (previousLower === currentLower && previousUpper === currentUpper) return;

        rows.push({
          headend,
          channel: channelLabel,
          previous_position: `${previousLower} <- ${channelLabel} -> ${previousUpper}`,
          current_position: `${currentLower} <- ${channelLabel} -> ${currentUpper}`,
          status: "Changed",
          summary: `${headend}: ${channelLabel} moved from between ${previousLower} and ${previousUpper} to between ${currentLower} and ${currentUpper}.`,
        });
      });
    }

    const result = {
      weeks,
      headend: selectedHeadend,
      channel: selectedChannel,
      rows,
      totalRows: rows.length,
      message: rows.length ? "" : `No neighbour changes detected for ${selectedChannel ? selectedChannel : "the selected channels"} in ${selectedHeadend || "all headends"}.`,
    };

    state.reportCache.narratives = result;
    state.reportCache.lastHeadend = selectedHeadend;
    state.reportCache.lastWeeks = currentWeeks;
    state.reportCache.lastChannel = selectedChannel;
    return result;
  }

  function buildReportNarrativesForDownload() {
    const payload = normalizePayloadShape(state.payload || window.__NBHD_STANDALONE_DATA__ || { weeks: [] });
    const allWeeks = payload.weeks || [];
    const weekFrom = state.report.week_from;
    const weekTo = state.report.week_to;
    const fromIndex = allWeeks.includes(weekFrom) ? allWeeks.indexOf(weekFrom) : -1;
    const toIndex = allWeeks.includes(weekTo) ? allWeeks.indexOf(weekTo) : -1;
    const weeks = fromIndex >= 0 && toIndex >= 0
      ? allWeeks.slice(Math.min(fromIndex, toIndex), Math.max(fromIndex, toIndex) + 1)
      : [];
    
    const selectedChannel = normalizeText(state.report.channel);
    const selectedHeadend = normalizeText(state.report.headend);
    const currentWeeks = [weekFrom, weekTo].filter(Boolean);
    
    if (state.reportCache.narrativesForDownload !== null && 
        state.reportCache.lastWeeksForDownload && 
        JSON.stringify(state.reportCache.lastWeeksForDownload) === JSON.stringify(currentWeeks) &&
        state.reportCache.lastHeadendForDownload === selectedHeadend &&
        state.reportCache.lastChannelForDownload === selectedChannel) {
      return state.reportCache.narrativesForDownload;
    }
    
    if (weeks.length < 2) {
      const result = {
        weeks,
        headend: selectedHeadend,
        channel: selectedChannel,
        rows: [],
        totalRows: 0,
        message: "Select previous and current week in the report filters to generate the neighbour change report.",
      };
      state.reportCache.narrativesForDownload = result;
      state.reportCache.lastWeeksForDownload = currentWeeks;
      state.reportCache.lastHeadendForDownload = selectedHeadend;
      state.reportCache.lastChannelForDownload = selectedChannel;
      return result;
    }

    const previousWeek = weeks[0];
    const currentWeek = weeks[weeks.length - 1];
    const baseRecords = getAllSourceRecords();
    const groupedRecords = new Map();
    baseRecords.forEach((record) => {
      const headend = normalizeText(record.head_end);
      if (!headend || (selectedHeadend && headend !== selectedHeadend)) return;
      if (!groupedRecords.has(headend)) groupedRecords.set(headend, []);
      groupedRecords.get(headend).push(record);
    });
    
    if (!groupedRecords.size) {
      const result = {
        weeks,
        headend: selectedHeadend,
        channel: selectedChannel,
        rows: [],
        totalRows: 0,
        message: "No headend data is available for the selected report filters.",
      };
      state.reportCache.narrativesForDownload = result;
      state.reportCache.lastWeeksForDownload = currentWeeks;
      state.reportCache.lastHeadendForDownload = selectedHeadend;
      state.reportCache.lastChannelForDownload = selectedChannel;
      return result;
    }

    const rows = [];
    const targetChannels = getReportTargetChannels();
    
    const allAvailableChannels = new Map();
    for (const [headend, groupRecords] of groupedRecords.entries()) {
      getReportChannelOptions(groupRecords).forEach((value) => {
        const key = normalizeChannelKey(value);
        if (!allAvailableChannels.has(key)) {
          allAvailableChannels.set(key, normalizeText(value));
        }
      });
    }
    
    for (const [headend, groupRecords] of groupedRecords.entries()) {
      const previousMap = buildHeadendMaps(groupRecords, previousWeek);
      const currentMap = buildHeadendMaps(groupRecords, currentWeek);
      
      targetChannels.forEach(({ label, key }) => {
        const channelLabel = allAvailableChannels.get(key) || label;
        const previousPosition = previousMap.channelPositions.get(key);
        const currentPosition = currentMap.channelPositions.get(key);
        if (previousPosition === undefined || currentPosition === undefined) return;

        const previousLower = neighborAt(previousMap, previousPosition, -1);
        const previousUpper = neighborAt(previousMap, previousPosition, 1);
        const currentLower = neighborAt(currentMap, currentPosition, -1);
        const currentUpper = neighborAt(currentMap, currentPosition, 1);
        if (previousLower === currentLower && previousUpper === currentUpper) return;

        rows.push({
          headend,
          channel: channelLabel,
          previous_position: `${previousLower} <- ${channelLabel} -> ${previousUpper}`,
          current_position: `${currentLower} <- ${channelLabel} -> ${currentUpper}`,
          status: "Changed",
          summary: `${headend}: ${channelLabel} moved from between ${previousLower} and ${previousUpper} to between ${currentLower} and ${currentUpper}.`,
        });
      });
    }

    const result = {
      weeks,
      headend: selectedHeadend,
      channel: selectedChannel,
      rows,
      totalRows: rows.length,
      message: rows.length ? "" : `No neighbour changes detected for ${selectedChannel ? selectedChannel : "the selected channels"} in ${selectedHeadend || "all headends"}.`,
    };
    
    state.reportCache.narrativesForDownload = result;
    state.reportCache.lastWeeksForDownload = currentWeeks;
    state.reportCache.lastHeadendForDownload = selectedHeadend;
    state.reportCache.lastChannelForDownload = selectedChannel;
    
    return result;
  }

  function getComparisonSourcePayload() {
    return normalizePayloadShape(window.__NBHD_STANDALONE_DATA__ || state.payload || { weeks: [] });
  }

  function getFrequencySourcePayload() {
    const bundle = window.__CHROME_REPORT_DATA__ || {};
    const frequency = bundle.frequency || {};
    return {
      weeks: Array.isArray(frequency.weeks) ? frequency.weeks.filter((value) => normalizeText(value) !== "") : [],
      records: Array.isArray(frequency.records) ? frequency.records : [],
    };
  }

  function getNeighbourhoodHeadendSet() {
    const payload = getComparisonSourcePayload();
    const records = Array.isArray(payload.table?.records) ? payload.table.records : [];
    return new Set(records.map((record) => normalizeText(record.head_end)).filter(Boolean));
  }

  function buildFrequencyHeadendMaps(records, week) {
    const byPosition = new Map();
    const genresByPosition = new Map();
    const channelPositions = new Map();
    const positions = [];
    records.forEach((record) => {
      const channel = normalizeText(record.channel_name);
      const position = Number(record.frequencies?.[week]);
      if (!channel || Number.isNaN(position)) return;
      byPosition.set(position, channel);
      genresByPosition.set(position, normalizeText(record.genre));
      channelPositions.set(normalizeChannelKey(channel), position);
      positions.push(position);
    });
    positions.sort((left, right) => left - right);
    return { byPosition, genresByPosition, channelPositions, positions };
  }

  function getNearestPosition(mapState, position, direction) {
    const positions = Array.isArray(mapState?.positions) ? mapState.positions : [];
    if (!positions.length || Number.isNaN(Number(position))) return null;
    if (direction < 0) {
      for (let index = positions.length - 1; index >= 0; index -= 1) {
        if (positions[index] < position) return positions[index];
      }
      return null;
    }
    for (let index = 0; index < positions.length; index += 1) {
      if (positions[index] > position) return positions[index];
    }
    return null;
  }

  function getAdjacentChannel(mapState, position, direction) {
    const adjacentPosition = getNearestPosition(mapState, position, direction);
    if (adjacentPosition === null || adjacentPosition === undefined) return "";
    return normalizeText(mapState.byPosition.get(adjacentPosition));
  }

  function getAdjacentGenre(mapState, position, direction) {
    const adjacentPosition = getNearestPosition(mapState, position, direction);
    if (adjacentPosition === null || adjacentPosition === undefined) return "";
    return normalizeText(mapState.genresByPosition.get(adjacentPosition));
  }

  function normalizeGenreFamily(value) {
    const genre = normalizeText(value);
    if (!genre || genre.toUpperCase() === "NA" || genre.toUpperCase() === "BLANK") return "Missing";
    if (genre.toUpperCase().includes("NEWS")) return "News";
    return genre;
  }

  function isNewsGenre(value) {
    return normalizeGenreFamily(value) === "News";
  }

  function formatPercent(value, total) {
    if (!total) return "0.0%";
    return `${((value / total) * 100).toFixed(1)}%`;
  }

  function comparisonMetric(label, count, total) {
    return {
      label,
      count,
      percent: formatPercent(count, total),
    };
  }

  function isMissingGenreValue(value) {
    const family = normalizeGenreFamily(value);
    return family === "Missing";
  }

  function classifyIndiaTvPosition(indiaGenre, aboveChannel, aboveGenre, belowChannel, belowGenre) {
    const hasAbove = normalizeText(aboveChannel) !== "";
    const hasBelow = normalizeText(belowChannel) !== "";
    const indiaIsNews = isNewsGenre(indiaGenre);
    const aboveIsNews = isNewsGenre(aboveGenre);
    const belowIsNews = isNewsGenre(belowGenre);
    const aboveFamily = normalizeGenreFamily(aboveGenre);
    const belowFamily = normalizeGenreFamily(belowGenre);

    if (hasAbove && hasBelow && aboveIsNews && belowIsNews) {
      return "Surrounded by News";
    }
    if (hasAbove && hasBelow && aboveFamily !== belowFamily) {
      return "Between Different Genres";
    }
    if (indiaIsNews && hasAbove && !aboveIsNews) {
      return "India TV Starts News";
    }
    return "Other";
  }

  function buildIndiaTvGenreComparisonReport() {
    const payload = getComparisonSourcePayload();
    const weeks = (payload.weeks || []).filter((value) => normalizeText(value) !== "");
    const currentWeek = weeks[weeks.length - 1] || "";
    const records = getAllSourceRecords();
    const groupedRecords = new Map();

    records.forEach((record) => {
      const market = normalizeText(record.market);
      const city = normalizeText(record.city);
      const headend = normalizeText(record.head_end);
      if (!market || !city || !headend) return;
      const groupKeyValue = `${market}||${city}||${headend}`;
      if (!groupedRecords.has(groupKeyValue)) {
        groupedRecords.set(groupKeyValue, { market, city, headend, records: [] });
      }
      groupedRecords.get(groupKeyValue).records.push(record);
    });

    const detailedRows = [];
    groupedRecords.forEach((group) => {
      const currentMap = buildHeadendMaps(group.records, currentWeek);
      const indiaTvPosition = currentMap.channelPositions.get(INDIA_TV_CHANNEL_KEY);

      if (indiaTvPosition === undefined) {
        detailedRows.push({
          market: group.market,
          city: group.city,
          headend: group.headend,
          indiaPosition: "",
          indiaFrequency: "",
          channelAbove: "",
          genreAbove: "",
          indiaGenre: "",
          channelBelow: "",
          genreBelow: "",
          classification: "Other",
          indiaTvMissing: true,
        });
        return;
      }

      const indiaGenre = normalizeText(currentMap.genresByPosition.get(indiaTvPosition));
      const abovePosition = getAdjacentPosition(currentMap, indiaTvPosition, -1);
      const belowPosition = getAdjacentPosition(currentMap, indiaTvPosition, 1);
      const channelAbove = abovePosition === null ? "" : normalizeText(currentMap.byPosition.get(abovePosition));
      const genreAbove = abovePosition === null ? "" : normalizeText(currentMap.genresByPosition.get(abovePosition));
      const channelBelow = belowPosition === null ? "" : normalizeText(currentMap.byPosition.get(belowPosition));
      const genreBelow = belowPosition === null ? "" : normalizeText(currentMap.genresByPosition.get(belowPosition));

      detailedRows.push({
        market: group.market,
        city: group.city,
        headend: group.headend,
        indiaPosition: indiaTvPosition,
        indiaFrequency: currentMap.frequenciesByPosition.get(indiaTvPosition),
        channelAbove,
        genreAbove,
        indiaGenre,
        channelBelow,
        genreBelow,
        classification: classifyIndiaTvPosition(indiaGenre, channelAbove, genreAbove, channelBelow, genreBelow),
        indiaTvMissing: false,
      });
    });

    const rows = detailedRows.slice();

    rows.sort((left, right) => (
      left.market.localeCompare(right.market, undefined, { numeric: true })
      || left.city.localeCompare(right.city, undefined, { numeric: true })
      || left.headend.localeCompare(right.headend, undefined, { numeric: true })
    ));

    const totalHeadends = rows.length;
    const betweenDifferentGenresCount = rows.filter((row) => row.classification === "Between Different Genres").length;
    const otherCount = rows.filter((row) => row.classification === "Other").length;
    const filteredRows = rows.filter((row) => (
      (row.classification === "Between Different Genres" || row.classification === "Other")
      && normalizeGenreFamily(row.genreBelow) !== "News"
    ));
    const uniqueCombinations = new Map();
    filteredRows.forEach((row) => {
      const key = [
        normalizeText(row.headend),
        normalizeText(row.indiaFrequency),
        normalizeText(row.channelAbove),
        normalizeText(row.genreAbove),
        normalizeText(row.channelBelow),
        normalizeText(row.genreBelow),
        normalizeText(row.classification),
      ].join("||");
      if (!uniqueCombinations.has(key)) {
        uniqueCombinations.set(key, {
          headend: row.headend,
          indiaPosition: row.indiaPosition,
          indiaFrequency: row.indiaFrequency,
          channelAbove: row.channelAbove,
          genreAbove: row.genreAbove,
          channelBelow: row.channelBelow,
          genreBelow: row.genreBelow,
          classification: row.classification,
          locations: [],
        });
      }
      uniqueCombinations.get(key).locations.push(`${row.market} | ${row.city}`);
    });
    const uniqueRows = Array.from(uniqueCombinations.values()).sort((left, right) => (
      left.classification.localeCompare(right.classification, undefined, { numeric: true })
      || left.headend.localeCompare(right.headend, undefined, { numeric: true })
      || String(left.indiaFrequency || "").localeCompare(String(right.indiaFrequency || ""), undefined, { numeric: true })
      || left.channelAbove.localeCompare(right.channelAbove, undefined, { numeric: true })
      || left.channelBelow.localeCompare(right.channelBelow, undefined, { numeric: true })
    ));
    const startingRows = rows.filter((row) => (
      normalizeText(row.genreBelow).toUpperCase() === "HINDI NEWS"
      && normalizeText(row.genreAbove).toUpperCase() !== "HINDI NEWS"
    ));
    const uniqueStartingCombinations = new Map();
    startingRows.forEach((row) => {
      const key = [
        normalizeText(row.headend),
        normalizeText(row.indiaFrequency),
        normalizeText(row.channelAbove),
        normalizeText(row.genreAbove),
        normalizeText(row.channelBelow),
        normalizeText(row.genreBelow),
        normalizeText(row.classification),
      ].join("||");
      if (!uniqueStartingCombinations.has(key)) {
        uniqueStartingCombinations.set(key, {
          headend: row.headend,
          indiaPosition: row.indiaPosition,
          indiaFrequency: row.indiaFrequency,
          channelAbove: row.channelAbove,
          genreAbove: row.genreAbove,
          channelBelow: row.channelBelow,
          genreBelow: row.genreBelow,
          classification: row.classification,
          locations: [],
        });
      }
      uniqueStartingCombinations.get(key).locations.push(`${row.market} | ${row.city}`);
    });
    const uniqueStartingRows = Array.from(uniqueStartingCombinations.values()).sort((left, right) => (
      left.headend.localeCompare(right.headend, undefined, { numeric: true })
      || String(left.indiaFrequency || "").localeCompare(String(right.indiaFrequency || ""), undefined, { numeric: true })
      || left.channelAbove.localeCompare(right.channelAbove, undefined, { numeric: true })
      || left.channelBelow.localeCompare(right.channelBelow, undefined, { numeric: true })
    ));
    const uniqueHeadendCount = new Set(uniqueRows.map((row) => normalizeText(row.headend)).filter(Boolean)).size;
    const uniqueLcnCount = new Set(uniqueRows.map((row) => normalizeText(row.indiaFrequency)).filter(Boolean)).size;
    const filteredBetweenDifferentGenresCount = uniqueRows.filter((row) => row.classification === "Between Different Genres").length;
    const filteredOtherCount = uniqueRows.filter((row) => row.classification === "Other").length;

    return {
      week: currentWeek,
      metrics: [
        comparisonMetric("Unique Combinations", uniqueRows.length, totalHeadends),
        comparisonMetric("Unique Headends", uniqueHeadendCount, totalHeadends),
        comparisonMetric("Unique India TV LCNs", uniqueLcnCount, totalHeadends),
        comparisonMetric("India TV Between Different Genres", filteredBetweenDifferentGenresCount, totalHeadends),
        comparisonMetric("Other", filteredOtherCount, totalHeadends),
      ],
      rows: uniqueRows,
      totalHeadends,
      betweenDifferentGenresCount: filteredBetweenDifferentGenresCount,
      otherCount: filteredOtherCount,
      flaggedHeadends: uniqueRows.length,
      uniqueHeadendCount,
      uniqueLcnCount,
      startingRows: uniqueStartingRows,
      startingCount: uniqueStartingRows.length,
    };
  }

  function exportComparisonReportExcel() {
    const reportData = buildIndiaTvGenreComparisonReport();
    if (!reportData.rows.length) return;
    const excelCell = window.__excelCell || ((value, style = "cell", options = {}) => ({ value, style, ...options }));
    const blankRow = window.__blankExcelRow || ((count = 1) => Array.from({ length: Math.max(1, count) }, () => excelCell("", "cell")));
    const primaryRows = [
      [excelCell(`India TV Genre Positioning Analysis - ${reportData.week || "Latest"}`, "title", { mergeAcross: 3 })],
      [excelCell(`Unique combinations: ${reportData.flaggedHeadends} | Unique headends: ${reportData.uniqueHeadendCount} | Unique India TV LCNs: ${reportData.uniqueLcnCount}`, "meta", { mergeAcross: 3 })],
      blankRow(4),
      [
        excelCell("Headend Name", "header"),
        excelCell("India TV LCN No", "header"),
        excelCell("Channel Above - Genre", "header"),
        excelCell("Channel Below - Genre", "header"),
      ],
      ...reportData.rows.map((row, index) => {
        const rowStyle = index % 2 === 0 ? "cell" : "altRow";
        return [
          excelCell(row.headend || "", rowStyle),
          excelCell(row.indiaFrequency ?? "", rowStyle),
          excelCell(`${row.channelAbove || "NA"} - ${row.genreAbove || "NA"}`, rowStyle),
          excelCell(`${row.channelBelow || "NA"} - ${row.genreBelow || "NA"}`, rowStyle),
        ];
      }),
    ];
    const startingSheetRows = [
      [excelCell(`Starting Channel Cases - ${reportData.week || "Latest"}`, "title", { mergeAcross: 3 })],
      [excelCell(`Unique combinations: ${reportData.startingCount}`, "meta", { mergeAcross: 3 })],
      blankRow(4),
      [
        excelCell("Headend Name", "header"),
        excelCell("India TV LCN No", "header"),
        excelCell("Channel Above - Genre", "header"),
        excelCell("Channel Below - Genre", "header"),
      ],
      ...reportData.startingRows.map((row, index) => {
        const rowStyle = index % 2 === 0 ? "cell" : "altRow";
        return [
          excelCell(row.headend || "", rowStyle),
          excelCell(row.indiaFrequency ?? "", rowStyle),
          excelCell(`${row.channelAbove || "NA"} - ${row.genreAbove || "NA"}`, rowStyle),
          excelCell(`${row.channelBelow || "NA"} - ${row.genreBelow || "NA"}`, rowStyle),
        ];
      }),
    ];
    window.__downloadExcelWorkbook?.("india_tv_genre_unique_combinations", [
      {
        name: "Unique Combinations",
        rows: primaryRows,
      },
      {
        name: "Starting Channel",
        rows: startingSheetRows,
      },
    ]);
  }

  function renderComparisonReportPanel() {
    if (!comparisonReportPanel || !comparisonReportContent) return;
    setComparisonReportVisibility(state.comparisonReport.open);
    if (!state.comparisonReport.open) return;

    const reportData = buildIndiaTvGenreComparisonReport();
    if (comparisonReportMeta) {
      comparisonReportMeta.textContent = reportData.week
        ? `Genre positioning analysis for India TV in ${reportData.week}. Showing only Between Different Genres and Other.`
        : "Genre positioning analysis for India TV.";
    }
    if (comparisonReportCount) {
      comparisonReportCount.textContent = `${reportData.flaggedHeadends} headend${reportData.flaggedHeadends === 1 ? "" : "s"}`;
    }
    if (comparisonReportStatus) {
      comparisonReportStatus.hidden = !reportData.rows.length;
      comparisonReportStatus.textContent = reportData.rows.length
        ? `Unique combinations: ${reportData.flaggedHeadends} | Unique headends: ${reportData.uniqueHeadendCount} | Unique India TV LCNs: ${reportData.uniqueLcnCount} | Between Different Genres: ${reportData.betweenDifferentGenresCount} | Other: ${reportData.otherCount}`
        : "";
    }

    if (!reportData.rows.length) {
      comparisonReportContent.innerHTML = '<div class="nbhd-report-empty">No headends are classified as Between Different Genres or Other.</div>';
      return;
    }

    const table = document.createElement("table");
    table.className = "nbhd-comparison-report-table";
    const thead = document.createElement("thead");
    const headerRow = document.createElement("tr");
    [
      "Headend Name",
      "India TV LCN No",
      "Channel Above - Genre",
      "Channel Below - Genre",
    ].forEach((label) => {
      const th = document.createElement("th");
      th.textContent = label;
      headerRow.appendChild(th);
    });
    thead.appendChild(headerRow);

    const tbody = document.createElement("tbody");
    reportData.rows.forEach((row) => {
      const tr = document.createElement("tr");
      [
        row.headend,
        row.indiaFrequency ?? "NA",
        `${row.channelAbove || "NA"} - ${row.genreAbove || "NA"}`,
        `${row.channelBelow || "NA"} - ${row.genreBelow || "NA"}`,
      ].forEach((value) => {
        const td = document.createElement("td");
        td.textContent = value;
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });

    const detailTitle = document.createElement("h4");
    detailTitle.className = "nbhd-position-section-title";
    detailTitle.textContent = "Unique Combination Detail";

    const startingTitle = document.createElement("h4");
    startingTitle.className = "nbhd-position-section-title";
    startingTitle.textContent = `Starting Channel Detail (${reportData.startingCount})`;

    const startingTable = document.createElement("table");
    startingTable.className = "nbhd-comparison-report-table";
    const startingHead = document.createElement("thead");
    const startingHeaderRow = document.createElement("tr");
    [
      "Headend Name",
      "India TV LCN No",
      "Channel Above - Genre",
      "Channel Below - Genre",
    ].forEach((label) => {
      const th = document.createElement("th");
      th.textContent = label;
      startingHeaderRow.appendChild(th);
    });
    startingHead.appendChild(startingHeaderRow);
    const startingBody = document.createElement("tbody");
    if (reportData.startingRows.length) {
      reportData.startingRows.forEach((row) => {
        const tr = document.createElement("tr");
        [
          row.headend,
          row.indiaFrequency ?? "NA",
          `${row.channelAbove || "NA"} - ${row.genreAbove || "NA"}`,
          `${row.channelBelow || "NA"} - ${row.genreBelow || "NA"}`,
        ].forEach((value) => {
          const td = document.createElement("td");
          td.textContent = value;
          tr.appendChild(td);
        });
        startingBody.appendChild(tr);
      });
    } else {
      const tr = document.createElement("tr");
      const td = document.createElement("td");
      td.colSpan = 4;
      td.textContent = "No starting-channel combinations found.";
      tr.appendChild(td);
      startingBody.appendChild(tr);
    }
    startingTable.append(startingHead, startingBody);

    table.append(thead, tbody);
    comparisonReportContent.replaceChildren(detailTitle, table, startingTitle, startingTable);
  }

  function renderReportPanel() {
    if (!reportPanel || !reportContent) return;
    setReportVisibility(state.report.open);
    if (reportToggleButton) reportToggleButton.textContent = "Neighbour Change Report";
    if (!state.report.open) return;
    
    // Invalidate cache when opening report panel to ensure fresh start
    invalidateReportCache();
    
    // Show loading state immediately
    if (reportStatus) {
      reportStatus.hidden = false;
      reportStatus.textContent = "Loading neighbour change report...";
    }
    if (reportContent) {
      reportContent.innerHTML = '<div class="nbhd-report-loading">Loading report data...</div>';
    }
    
    // Set a maximum loading time to prevent hanging
    const loadingTimeout = setTimeout(() => {
      if (reportStatus) {
        reportStatus.textContent = "Processing report data (this may take a moment)...";
      }
    }, 2000);
    
    // Use debounced processing to prevent UI freezing and rapid re-renders
    if (reportRenderTimeout) {
      clearTimeout(reportRenderTimeout);
    }
    
    // Use requestIdleCallback if available for background processing
    if (window.requestIdleCallback) {
      reportRenderTimeout = null;
      window.requestIdleCallback(() => {
        try {
        const context = buildReportContext();
        syncReportSelections(context);
        renderReportFilters(context);
        const reportData = buildReportNarratives();
        const previousWeek = reportData.weeks[0];
        const currentWeek = reportData.weeks[reportData.weeks.length - 1];
      if (reportMeta) {
        const channelText = reportData.channel || "default 4 channels";
        const headendText = reportData.headend || "all headends";
        reportMeta.textContent = previousWeek && currentWeek
          ? `Neighbour comparison for ${headendText} (${channelText}) from ${previousWeek} to ${currentWeek}.`
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

      const groups = new Map();
      reportData.rows.forEach((row) => {
        const headend = row.headend || "Selected Headend";
        if (!groups.has(headend)) groups.set(headend, []);
        groups.get(headend).push(row);
      });
      const fragment = document.createDocumentFragment();
      groups.forEach((rows, headend) => {
        const section = document.createElement("section");
        section.className = "nbhd-report-group";

        const header = document.createElement("div");
        header.className = "nbhd-report-group-header";
        const title = document.createElement("h4");
        title.textContent = headend;
        header.append(title);

        const tableWrap = document.createElement("div");
        tableWrap.className = "nbhd-report-table-wrap";
        const table = document.createElement("table");
        table.className = "nbhd-report-table";
        const tbodyRows = rows.map((row) => `
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
        rows.forEach((row) => {
          const item = document.createElement("li");
          item.textContent = row.summary;
          summaryList.appendChild(item);
        });

        section.append(header, tableWrap, summaryTitle, summaryList);
        fragment.appendChild(section);
      });
      reportContent.replaceChildren(fragment);
      } catch (error) {
        if (reportCount) reportCount.textContent = "0 narratives";
        renderReportStatus("Neighbour change report could not be generated.");
        reportContent.innerHTML = `<div class="nbhd-report-empty">Neighbour change report could not be generated.</div>`;
        console.error("NBHD report render failed", error);
        clearTimeout(loadingTimeout);
      }
      }, { timeout: 100 }); // Max 100ms delay for idle callback
    } else {
      // Fallback to setTimeout for browsers without requestIdleCallback
      reportRenderTimeout = setTimeout(() => {
        try {
          const context = buildReportContext();
          syncReportSelections(context);
          renderReportFilters(context);
          const reportData = buildReportNarratives();
          const previousWeek = reportData.weeks[0];
          const currentWeek = reportData.weeks[reportData.weeks.length - 1];
          if (reportMeta) {
            const channelText = reportData.channel || "default 4 channels";
            const headendText = reportData.headend || "all headends";
            reportMeta.textContent = previousWeek && currentWeek
              ? `Neighbour comparison for ${headendText} (${channelText}) from ${previousWeek} to ${currentWeek}.`
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

          const groups = new Map();
          reportData.rows.forEach((row) => {
            const headend = row.headend || "Selected Headend";
            if (!groups.has(headend)) groups.set(headend, []);
            groups.get(headend).push(row);
          });
          const fragment = document.createDocumentFragment();
          groups.forEach((rows, headend) => {
            const section = document.createElement("section");
            section.className = "nbhd-report-group";

            const header = document.createElement("div");
            header.className = "nbhd-report-group-header";
            const title = document.createElement("h4");
            title.textContent = headend;
            header.append(title);

            const tableWrap = document.createElement("div");
            tableWrap.className = "nbhd-report-table-wrap";
            const table = document.createElement("table");
            table.className = "nbhd-report-table";
            const tbodyRows = rows.map((row) => `
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
            rows.forEach((row) => {
              const item = document.createElement("li");
              item.textContent = row.summary;
              summaryList.appendChild(item);
            });

            section.append(header, tableWrap, summaryTitle, summaryList);
            fragment.appendChild(section);
          });
          reportContent.replaceChildren(fragment);
        } catch (error) {
          if (reportCount) reportCount.textContent = "0 narratives";
          renderReportStatus("Neighbour change report could not be generated.");
          reportContent.innerHTML = `<div class="nbhd-report-empty">Neighbour change report could not be generated.</div>`;
          console.error("NBHD report render failed", error);
        }
        clearTimeout(loadingTimeout);
      }, 0);
    }
  }

  function resetReportFilters() {
    state.report.open = true;
    state.report.headend = "";
    state.report.channel = "";
    state.report.week_from = "";
    state.report.week_to = "";
    invalidateReportCache();
    renderReportPanel();
  }

  function openReportPanel() {
    state.report.open = true;
    state.comparisonReport.open = false;
    setComparisonReportVisibility(false);
    setReportVisibility(true);
    reportContent.replaceChildren();
    renderReportStatus("");
    scheduleRender(state.payload);
    requestAnimationFrame(() => {
      reportPanel?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
  }

  function openComparisonReportPanel() {
    state.comparisonReport.open = true;
    state.report.open = false;
    setReportVisibility(false);
    setComparisonReportVisibility(true);
    renderComparisonReportPanel();
    requestAnimationFrame(() => {
      comparisonReportPanel?.scrollIntoView({ behavior: "smooth", block: "start" });
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
    return `${record.market}||${record.city}||${record.head_end}||${record.group_index || 1}`;
  }

  function sortGroupRecords(records) {
    return records.slice().sort((left, right) => (
      Number(left.position || 0) - Number(right.position || 0)
      || Number(left.slot_index || 0) - Number(right.slot_index || 0)
    ));
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
      return Array.from(new Set(
        allRecords
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
        channels: Array.from(new Set(
          allRecords
            .flatMap((record) => Object.values(record.channels || {}))
            .filter((value) => String(value || "").trim() !== "")
        )).sort((left, right) => left.localeCompare(right)),
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
      state.hasCustomWeekRange = Boolean(state.filters.week_from || state.filters.week_to);
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

    select.button.addEventListener("keydown", (event) => {
      if (event.key === "ArrowDown" || event.key === "ArrowUp" || event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        closeMenus();
        if (select.menu) select.menu.hidden = false;
        if (select.search) {
          select.search.value = "";
          select.search.dispatchEvent(new Event("input"));
          requestAnimationFrame(() => select.search?.focus());
        } else {
          const firstOpt = select.options?.querySelector("button");
          if (firstOpt) firstOpt.focus();
        }
      }
    });

    if (select.menu) {
      select.menu.addEventListener("keydown", (event) => {
        const items = Array.from(select.options?.querySelectorAll("button") || []);
        const activeEl = document.activeElement;
        const currentIndex = items.indexOf(activeEl);

        if (event.key === "Escape") {
          event.preventDefault();
          select.menu.hidden = true;
          select.button.focus();
        } else if (event.key === "ArrowDown") {
          event.preventDefault();
          const nextIndex = currentIndex < items.length - 1 ? currentIndex + 1 : 0;
          items[nextIndex]?.focus();
        } else if (event.key === "ArrowUp") {
          event.preventDefault();
          const prevIndex = currentIndex > 0 ? currentIndex - 1 : items.length - 1;
          items[prevIndex]?.focus();
        }
      });
    }

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
        invalidateReportCache();
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
    state.hasCustomWeekRange = false;
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
      "All Headends",
      (value) => {
        state.report.headend = value;
        invalidateReportCache();
        renderReportPanel();
        closeMenus();
      }
    );
  });
  bindReportSelect(reportChannelFilter, () => {
    renderOptions(
      reportChannelFilter,
      buildReportContext().channels,
      state.report.channel,
      "Default 4 Channels",
      (value) => {
        state.report.channel = value;
        invalidateReportCache();
        renderReportPanel();
        closeMenus();
      }
    );
  });
  bindReportWeekSelect(reportWeekFromFilter, "week_from", "Week From");
  bindReportWeekSelect(reportWeekToFilter, "week_to", "Week To");
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
  if (comparisonReportToggleButton) {
    comparisonReportToggleButton.addEventListener("click", openComparisonReportPanel);
  }
  if (reportHideButton) {
    reportHideButton.addEventListener("click", closeReportPanel);
  }
  if (comparisonReportHideButton) {
    comparisonReportHideButton.addEventListener("click", closeComparisonReportPanel);
  }
  if (comparisonReportDownloadButton) {
    comparisonReportDownloadButton.addEventListener("click", exportComparisonReportExcel);
  }
  if (reportResetButton) {
    reportResetButton.addEventListener("click", resetReportFilters);
  }
  if (reportDownloadButton) {
    reportDownloadButton.addEventListener("click", exportReportExcel);
  }
  if (tableDownloadButton) {
    tableDownloadButton.addEventListener("click", exportTableExcel);
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
  window.addEventListener("resize", () => {
    if (!state.payload) return;
    const nextPageSize = getPageSize();
    if (nextPageSize !== state.pageSize) {
      state.pageSize = nextPageSize;
      scheduleRender(state.payload);
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
  if (tableWrap) {
    tableWrap.addEventListener("scroll", () => maybeLoadMoreRows());
  }
  if (state.initial) {
    render(normalizePayloadShape(state.initial));
  }
  syncFullscreenButtons();
  fetchPayload(false);
})();
