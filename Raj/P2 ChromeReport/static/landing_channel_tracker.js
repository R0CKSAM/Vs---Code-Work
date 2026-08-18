(function () {
  const root = document.getElementById("landingTrackerTable");
  if (!root) return;

  const state = {
    payload: null,
    filters: {
      band: [],
      market: [],
      city: [],
      headend: [],
      state_name: [],
      district: [],
      feed: [],
      mso: [],
      channel_type: "landing_1",
      week_from: "",
      week_to: "",
      change: "",
    },
    page: 1,
    pageSize: 30,
    standalone: Boolean(window.__LANDING_TRACKER_STANDALONE_DATA__),
    initial: window.__LANDING_TRACKER_INITIAL_DATA__ || null,
  };

  const tableHead = document.getElementById("landingTrackerTableHead");
  const tableBody = document.getElementById("landingTrackerTableBody");
  const resultCount = document.getElementById("trackerResultCount");
  const pageInfo = document.getElementById("trackerPageInfo");
  const scrollHint = document.getElementById("trackerScrollHint");
  const resetButton = document.getElementById("trackerResetButton");
  const downloadButton = document.getElementById("trackerDownloadButton");
  const fullscreenBtn = document.getElementById("trackerFullscreenButton");
  const panel = root.closest(".landing-tracker-panel");
  const tableWrap = root.closest(".landing-tracker-table-wrap");
  let lazyRenderPending = false;

  function normalizeText(val) {
    return String(val || "").trim();
  }

  function getVisibleRowCount(totalCount) {
    return Math.min(totalCount, Math.max(1, state.page) * state.pageSize);
  }

  function updateLazyScrollHint(visibleCount, totalCount) {
    if (!scrollHint) return;
    if (totalCount > visibleCount) {
      scrollHint.textContent = `Scroll to load more (${visibleCount.toLocaleString("en-IN")} of ${totalCount.toLocaleString("en-IN")} visible)`;
      return;
    }
    scrollHint.textContent = totalCount ? `All ${totalCount.toLocaleString("en-IN")} records loaded` : "No records";
  }

  function maybeLoadMoreRows(force = false) {
    if (!tableWrap || lazyRenderPending) return;
    const filteredRecords = filterRecords();
    const visibleCount = getVisibleRowCount(filteredRecords.length);
    if (visibleCount >= filteredRecords.length) return;
    const nearBottom = tableWrap.scrollTop + tableWrap.clientHeight >= tableWrap.scrollHeight - 160;
    const underfilled = tableWrap.scrollHeight <= tableWrap.clientHeight + 40;
    if (!force && !nearBottom && !underfilled) return;
    lazyRenderPending = true;
    state.page += 1;
    render();
    lazyRenderPending = false;
  }

  function getMultiSelect(id) {
    return {
      button: document.getElementById(id),
      menu: document.getElementById(`${id}Menu`),
      search: document.getElementById(`${id}Search`),
      options: document.getElementById(`${id}Options`),
    };
  }

  const controls = {
    band: getMultiSelect("trackerBandFilter"),
    market: getMultiSelect("trackerMarketFilter"),
    city: getMultiSelect("trackerCityFilter"),
    headend: getMultiSelect("trackerHeadendFilter"),
    state_name: getMultiSelect("trackerStateFilter"),
    district: getMultiSelect("trackerDistrictFilter"),
    feed: getMultiSelect("trackerFeedFilter"),
    mso: getMultiSelect("trackerMsoFilter"),
    channel_type: getMultiSelect("trackerChannelTypeFilter"),
    week_from: getMultiSelect("trackerWeekFromFilter"),
    week_to: getMultiSelect("trackerWeekToFilter"),
    change: getMultiSelect("trackerChangeFilter"),
  };

  function closeAllMenus(except = null) {
    Object.values(controls).forEach((ctrl) => {
      if (ctrl.menu && ctrl.menu !== except) {
        ctrl.menu.hidden = true;
      }
    });
  }

  function updateButtonLabel(ctrl, selected, placeholder) {
    if (!ctrl.button) return;
    if (!selected || (Array.isArray(selected) && selected.length === 0)) {
      ctrl.button.textContent = placeholder;
    } else if (Array.isArray(selected)) {
      ctrl.button.textContent = `${selected.length} selected`;
    } else {
      ctrl.button.textContent = selected;
    }
  }

  function parseWeekNumber(wkStr) {
    const match = String(wkStr || "").match(/\d+/);
    return match ? parseInt(match[0], 10) : 0;
  }

  function syncDefaultWeekFilters() {
    const allWeeks = state.payload?.weeks || [];
    if (allWeeks.length === 0) return;

    if (!state.filters.week_from || !allWeeks.includes(state.filters.week_from)) {
      state.filters.week_from = allWeeks.length >= 2 ? allWeeks[allWeeks.length - 2] : allWeeks[0];
    }
    if (!state.filters.week_to || !allWeeks.includes(state.filters.week_to)) {
      state.filters.week_to = allWeeks[allWeeks.length - 1];
    }
  }

  function getVisibleWeeks() {
    const allWeeks = state.payload?.weeks || [];
    if (allWeeks.length === 0) return [];

    syncDefaultWeekFilters();

    let fromIdx = allWeeks.indexOf(state.filters.week_from);
    let toIdx = allWeeks.indexOf(state.filters.week_to);

    if (fromIdx === -1) fromIdx = allWeeks.length >= 2 ? allWeeks.length - 2 : 0;
    if (toIdx === -1) toIdx = allWeeks.length - 1;

    if (fromIdx > toIdx) {
      const tmp = fromIdx;
      fromIdx = toIdx;
      toIdx = tmp;
    }

    return allWeeks.slice(fromIdx, toIdx + 1);
  }

  function getFilteredSourceRecords(ignoreKey = "") {
    const allRecords = state.payload?.records || [];
    return allRecords.filter((rec) => {
      for (const key of Object.keys(controls)) {
        if (key === ignoreKey || key === "channel_type" || key === "week_from" || key === "week_to" || key === "change") continue;
        const sel = state.filters[key];
        if (Array.isArray(sel) && sel.length > 0) {
          const recVal = normalizeText(rec[key]);
          if (!sel.includes(recVal)) return false;
        }
      }
      return true;
    });
  }

  function getWeekChannelName(weekObj, channelTypeKey) {
    if (channelTypeKey === "landing_1") return weekObj.channel_1 || "";
    if (channelTypeKey === "landing_2") return weekObj.channel_2 || "";
    if (channelTypeKey === "landing_3") return weekObj.channel_3 || "";
    if (channelTypeKey === "barker_1") return weekObj.barker_1 || "";
    if (channelTypeKey === "barker_2") return weekObj.barker_2 || "";
    return "";
  }

  function hasChannelChange(record, visibleWeeks) {
    if (!record || !Array.isArray(visibleWeeks) || visibleWeeks.length < 2) return false;
    const channelTypeKey = state.filters.channel_type || "landing_1";
    let previousName = "";

    for (let index = 0; index < visibleWeeks.length; index += 1) {
      const weekObj = record.weeks?.[visibleWeeks[index]] || {};
      const currentName = normalizeText(getWeekChannelName(weekObj, channelTypeKey)).toUpperCase();
      if (index > 0 && previousName && currentName && previousName !== currentName) {
        return true;
      }
      previousName = currentName;
    }
    return false;
  }

  function getWeekCellParts(weekObj, channelTypeKey) {
    let channelName = "";
    let lcnVal = "";
    let genreVal = "";

    if (channelTypeKey === "landing_1") {
      channelName = weekObj.channel_1 || "";
      lcnVal = weekObj.lcn_1 || "";
      genreVal = weekObj.genre_1 || "";
    } else if (channelTypeKey === "landing_2") {
      channelName = weekObj.channel_2 || "";
      lcnVal = weekObj.lcn_2 || "";
      genreVal = weekObj.genre_2 || "";
    } else if (channelTypeKey === "landing_3") {
      channelName = weekObj.channel_3 || "";
      lcnVal = weekObj.lcn_3 || "";
      genreVal = weekObj.genre_3 || "";
    } else if (channelTypeKey === "barker_1") {
      channelName = weekObj.barker_1 || "";
      lcnVal = weekObj.lcn_b1 || "";
    } else if (channelTypeKey === "barker_2") {
      channelName = weekObj.barker_2 || "";
      lcnVal = weekObj.lcn_b2 || "";
    }

    return { channelName, lcnVal, genreVal };
  }

  function getAvailableOptionsFor(key) {
    if (key === "channel_type") {
      return [
        { value: "landing_1", label: "Landing Channel 1" },
        { value: "landing_2", label: "Landing Channel 2" },
        { value: "landing_3", label: "Landing Channel 3" },
        { value: "barker_1", label: "Barker 1" },
        { value: "barker_2", label: "Barker 2" },
      ];
    }
    if (key === "week_from" || key === "week_to") {
      const weeks = state.payload?.weeks || [];
      return weeks.map((w) => ({ value: w, label: w }));
    }
    if (key === "change") {
      return [
        { value: "Changed", label: "Changed" },
        { value: "No Change", label: "No Change" },
      ];
    }

    const scopedRecords = getFilteredSourceRecords(key);
    const set = new Set();
    scopedRecords.forEach((r) => {
      const v = normalizeText(r[key]);
      if (v) set.add(v);
    });
    return Array.from(set).sort((a, b) => a.localeCompare(b));
  }

  function renderMultiSelectMenu(key, ctrl, placeholder) {
    if (!ctrl.options) return;
    const options = getAvailableOptionsFor(key);
    const selected = state.filters[key];
    const query = normalizeText(ctrl.search?.value).toLowerCase();

    const frag = document.createDocumentFragment();

    const isSingleSelect = (key === "channel_type" || key === "week_from" || key === "week_to" || key === "change");

    if (!isSingleSelect) {
      const selectAllBtn = document.createElement("button");
      selectAllBtn.type = "button";
      selectAllBtn.className = "filter-option-action";
      selectAllBtn.textContent = "Select All";
      selectAllBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        state.filters[key] = options.map((o) => (typeof o === "object" ? o.value : o));
        updateButtonLabel(ctrl, state.filters[key], placeholder);
        renderMultiSelectMenu(key, ctrl, placeholder);
        state.page = 1;
        render();
      });

      const clearBtn = document.createElement("button");
      clearBtn.type = "button";
      clearBtn.className = "filter-option-action";
      clearBtn.textContent = "Clear";
      clearBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        state.filters[key] = [];
        updateButtonLabel(ctrl, state.filters[key], placeholder);
        renderMultiSelectMenu(key, ctrl, placeholder);
        state.page = 1;
        render();
      });

      const actionsRow = document.createElement("div");
      actionsRow.className = "filter-actions-row";
      actionsRow.appendChild(selectAllBtn);
      actionsRow.appendChild(clearBtn);
      frag.appendChild(actionsRow);
    }

    const optList = options.filter((o) => {
      const label = typeof o === "object" ? o.label : o;
      return !query || String(label).toLowerCase().includes(query);
    });

    optList.forEach((opt) => {
      const val = typeof opt === "object" ? opt.value : opt;
      const label = typeof opt === "object" ? opt.label : opt;
      const row = document.createElement("label");
      row.className = "filter-checkbox-row";

      if (isSingleSelect) {
        const radio = document.createElement("input");
        radio.type = "radio";
        radio.name = `tracker_${key}`;
        radio.value = val;
        radio.checked = selected === val;
        radio.addEventListener("change", () => {
          state.filters[key] = val;

          // Auto-adjust week ranges if week_from > week_to
          const allWeeks = state.payload?.weeks || [];
          if (key === "week_from" && state.filters.week_to) {
            const fromIdx = allWeeks.indexOf(val);
            const toIdx = allWeeks.indexOf(state.filters.week_to);
            if (fromIdx > toIdx) state.filters.week_to = val;
          } else if (key === "week_to" && state.filters.week_from) {
            const fromIdx = allWeeks.indexOf(state.filters.week_from);
            const toIdx = allWeeks.indexOf(val);
            if (toIdx < fromIdx) state.filters.week_from = val;
          }

          updateButtonLabel(ctrl, label, placeholder);
          ctrl.menu.hidden = true;
          state.page = 1;
          render();
        });
        const txt = document.createElement("span");
        txt.textContent = label;
        row.appendChild(radio);
        row.appendChild(txt);
      } else {
        const chk = document.createElement("input");
        chk.type = "checkbox";
        chk.value = val;
        chk.checked = Array.isArray(selected) && selected.includes(val);
        chk.addEventListener("change", (e) => {
          e.stopPropagation();
          if (chk.checked) {
            if (!state.filters[key].includes(val)) state.filters[key].push(val);
          } else {
            state.filters[key] = state.filters[key].filter((v) => v !== val);
          }
          updateButtonLabel(ctrl, state.filters[key], placeholder);
          state.page = 1;
          render();
        });
        const txt = document.createElement("span");
        txt.textContent = label;
        row.appendChild(chk);
        row.appendChild(txt);
      }
      frag.appendChild(row);
    });

    ctrl.options.replaceChildren(frag);
  }

  function bindMultiSelect(key, ctrl, placeholder) {
    if (!ctrl.button) return;
    ctrl.button.addEventListener("click", (e) => {
      e.stopPropagation();
      const next = ctrl.menu?.hidden ?? false;
      closeAllMenus(ctrl.menu);
      if (ctrl.menu) ctrl.menu.hidden = !next;
      if (next) {
        if (ctrl.search) ctrl.search.value = "";
        renderMultiSelectMenu(key, ctrl, placeholder);
        if (ctrl.search) requestAnimationFrame(() => ctrl.search.focus());
      }
    });

    if (ctrl.search) {
      ctrl.search.addEventListener("click", (e) => e.stopPropagation());
      ctrl.search.addEventListener("input", () => {
        renderMultiSelectMenu(key, ctrl, placeholder);
      });
    }
  }

  function filterRecords() {
    if (!state.payload?.records) return [];
    const visibleWeeks = getVisibleWeeks();

    return state.payload.records.filter((rec) => {
      for (const key of Object.keys(controls)) {
        if (key === "channel_type" || key === "week_from" || key === "week_to" || key === "change") continue;
        const sel = state.filters[key];
        if (Array.isArray(sel) && sel.length > 0) {
          const recVal = normalizeText(rec[key]);
          if (!sel.includes(recVal)) return false;
        }
      }

      const rowChanged = hasChannelChange(rec, visibleWeeks);
      if (state.filters.change === "Changed" && !rowChanged) return false;
      if (state.filters.change === "No Change" && rowChanged) return false;
      return true;
    });
  }

  function renderTableHead(visibleWeeks) {
    if (!tableHead) return;
    const tr = document.createElement("tr");

    const baseCols = [
      "Band", "Market", "City", "Headend", "State", "District", "MSO"
    ];

    baseCols.forEach((colLabel) => {
      const th = document.createElement("th");
      th.textContent = colLabel;
      tr.appendChild(th);
    });

    visibleWeeks.forEach((wk) => {
      const th = document.createElement("th");
      th.textContent = `${wk} (Landing Channel Name - LCN - Genre)`;
      th.className = "tracker-week-head";
      tr.appendChild(th);
    });

    tableHead.replaceChildren(tr);
  }

  function renderTableBody(records, visibleWeeks) {
    if (!tableBody) return;
    const totalCount = records.length;

    if (totalCount === 0) {
      if (resultCount) resultCount.textContent = "0 records";
      if (pageInfo) pageInfo.textContent = "Showing 0 of 0";
      updateLazyScrollHint(0, 0);
      tableBody.innerHTML = `<tr><td colspan="100%" class="landing-empty-state">No records found.<br/><span style="font-size:0.75rem; font-weight:400; color:var(--muted);">Try adjusting your filters.</span></td></tr>`;
      return;
    }

    const visibleCount = getVisibleRowCount(totalCount);
    const pageRecords = records.slice(0, visibleCount);

    if (resultCount) resultCount.textContent = `${totalCount.toLocaleString("en-IN")} records`;
    if (pageInfo) pageInfo.textContent = `Showing ${pageRecords.length.toLocaleString("en-IN")} of ${totalCount.toLocaleString("en-IN")}`;
    updateLazyScrollHint(pageRecords.length, totalCount);

    const channelTypeKey = state.filters.channel_type || "landing_1";
    const frag = document.createDocumentFragment();

    pageRecords.forEach((rec) => {
      const tr = document.createElement("tr");

      ["band", "market", "city", "headend", "state_name", "district", "mso"].forEach((colKey) => {
        const td = document.createElement("td");
        const val = rec[colKey] || "--";
        td.textContent = val;
        td.title = val;
        tr.appendChild(td);
      });

      let prevChannelName = "";

      visibleWeeks.forEach((wk, weekIdx) => {
        const weekObj = rec.weeks?.[wk] || {};
        let channelName = "";
        let lcnVal = "";
        let genreVal = "";

        ({ channelName, lcnVal, genreVal } = getWeekCellParts(weekObj, channelTypeKey));

        const tdWeek = document.createElement("td");
        const cellParts = [];
        if (channelName) cellParts.push(channelName);
        if (lcnVal) cellParts.push(lcnVal);
        if (genreVal) cellParts.push(genreVal);

        const displayText = cellParts.length > 0 ? cellParts.join(" - ") : "--";
        tdWeek.textContent = displayText;
        tdWeek.title = displayText;

        // Channel Name Change Highlighting Rule:
        // Compare ONLY Landing Channel Name. Ignore LCN & Genre changes.
        const normPrev = normalizeText(prevChannelName).toUpperCase();
        const normCurr = normalizeText(channelName).toUpperCase();

        const hasChannelNameChanged = weekIdx > 0 &&
          normPrev !== "" &&
          normCurr !== "" &&
          normPrev !== normCurr;

        if (hasChannelNameChanged) {
          tdWeek.className = "tracker-cell-changed";
        }

        prevChannelName = channelName;
        tr.appendChild(tdWeek);
      });

      frag.appendChild(tr);
    });

    tableBody.replaceChildren(frag);
  }

  function render() {
    const visibleWeeks = getVisibleWeeks();
    const filteredRecords = filterRecords();
    renderTableHead(visibleWeeks);
    renderTableBody(filteredRecords, visibleWeeks);
    syncFilterLabels();
    window.requestAnimationFrame(() => maybeLoadMoreRows());
  }

  function exportTrackerExcel() {
    const downloader = window.__downloadExcelWorkbook;
    const excelCell = window.__excelCell || ((value, style = "cell", options = {}) => ({ value, style, ...options }));
    if (!downloader) return;

    const visibleWeeks = getVisibleWeeks();
    const filteredRecords = filterRecords();
    const channelTypeKey = state.filters.channel_type || "landing_1";
    const channelTypeLabel = {
      landing_1: "Landing Channel 1",
      landing_2: "Landing Channel 2",
      landing_3: "Landing Channel 3",
      barker_1: "Barker 1",
      barker_2: "Barker 2",
    }[channelTypeKey] || channelTypeKey;

    const headerRow = [
      excelCell("Band", "header"),
      excelCell("Market", "header"),
      excelCell("City", "header"),
      excelCell("Headend", "header"),
      excelCell("State", "header"),
      excelCell("District", "header"),
      excelCell("MSO", "header"),
      excelCell("Change Status", "header"),
      ...visibleWeeks.map((week) => excelCell(`${week} (${channelTypeLabel})`, "header")),
    ];

    const rows = filteredRecords.map((rec, rowIndex) => {
      const rowChanged = hasChannelChange(rec, visibleWeeks);
      const rowStyle = rowIndex % 2 === 0 ? "cell" : "altRow";
      const baseCells = [
        excelCell(rec.band || "", rowStyle),
        excelCell(rec.market || "", rowStyle),
        excelCell(rec.city || "", rowStyle),
        excelCell(rec.headend || "", rowStyle),
        excelCell(rec.state_name || "", rowStyle),
        excelCell(rec.district || "", rowStyle),
        excelCell(rec.mso || "", rowStyle),
        excelCell(rowChanged ? "Changed" : "No Change", rowChanged ? "positive" : "neutral"),
      ];

      const weekCells = visibleWeeks.map((week) => {
        const weekObj = rec.weeks?.[week] || {};
        const { channelName, lcnVal, genreVal } = getWeekCellParts(weekObj, channelTypeKey);
        const parts = [];
        if (channelName) parts.push(channelName);
        if (lcnVal) parts.push(lcnVal);
        if (genreVal) parts.push(genreVal);
        return excelCell(parts.length ? parts.join(" - ") : "--", rowStyle);
      });

      return [...baseCells, ...weekCells];
    });

    downloader("landing_channel_change_tracker", [
      {
        name: "Landing Tracker",
        columns: [95, 120, 120, 150, 110, 120, 140, 95, ...visibleWeeks.map(() => 220)],
        rows: [
          [excelCell("Landing Channel Change Tracker", "title", { mergeAcross: Math.max(0, headerRow.length - 1) })],
          [excelCell(`Channel Type: ${channelTypeLabel} | Weeks: ${visibleWeeks.join(" to ") || "N/A"} | Rows: ${filteredRecords.length}`, "meta", { mergeAcross: Math.max(0, headerRow.length - 1) })],
          headerRow,
          ...rows,
        ],
      },
    ]);
  }

  function syncFilterLabels() {
    syncDefaultWeekFilters();
    const allWeeks = state.payload?.weeks || [];
    const defaultFrom = state.filters.week_from || (allWeeks.length >= 2 ? allWeeks[allWeeks.length - 2] : (allWeeks[0] || "Week From"));
    const defaultTo = state.filters.week_to || (allWeeks.length >= 1 ? allWeeks[allWeeks.length - 1] : "Week To");

    const placeholders = {
      band: "All Bands",
      market: "All Markets",
      city: "All Cities",
      headend: "All Headends",
      state_name: "All States",
      district: "All Districts",
      feed: "All Feeds",
      mso: "All MSO",
      channel_type: "Landing Channel 1",
      week_from: defaultFrom,
      week_to: defaultTo,
      change: "All Changes",
    };
    Object.keys(controls).forEach((key) => {
      const selected = state.filters[key];
      updateButtonLabel(controls[key], selected, placeholders[key]);
    });
  }

  function bindControls() {
    const allWeeks = state.payload?.weeks || [];
    const defaultFrom = state.filters.week_from || (allWeeks.length >= 2 ? allWeeks[allWeeks.length - 2] : (allWeeks[0] || "Week From"));
    const defaultTo = state.filters.week_to || (allWeeks.length >= 1 ? allWeeks[allWeeks.length - 1] : "Week To");

    const placeholders = {
      band: "All Bands",
      market: "All Markets",
      city: "All Cities",
      headend: "All Headends",
      state_name: "All States",
      district: "All Districts",
      feed: "All Feeds",
      mso: "All MSO",
      channel_type: "Landing Channel 1",
      week_from: defaultFrom,
      week_to: defaultTo,
      change: "All Changes",
    };

    Object.keys(controls).forEach((key) => {
      bindMultiSelect(key, controls[key], placeholders[key]);
    });

    document.addEventListener("click", (e) => {
      if (!e.target.closest(".filter-select")) closeAllMenus();
    });

    if (resetButton) {
      resetButton.addEventListener("click", () => {
        state.filters = {
          band: [],
          market: [],
          city: [],
          headend: [],
          state_name: [],
          district: [],
          feed: [],
          mso: [],
          channel_type: "landing_1",
          week_from: "",
          week_to: "",
          change: "",
        };
        syncDefaultWeekFilters();
        state.page = 1;
        render();
      });
    }

    if (downloadButton) {
      downloadButton.addEventListener("click", exportTrackerExcel);
    }

    if (fullscreenBtn) {
      fullscreenBtn.addEventListener("click", () => {
        if (!panel) return;
        const isActive = panel.classList.contains("landing-tracker-fullscreen");
        if (isActive) {
          panel.classList.remove("landing-tracker-fullscreen");
          fullscreenBtn.textContent = "Full Screen";
        } else {
          panel.classList.add("landing-tracker-fullscreen");
          fullscreenBtn.textContent = "Exit Full Screen";
        }
      });
    }

    if (tableWrap) {
      tableWrap.addEventListener("scroll", () => maybeLoadMoreRows());
    }
  }

  function init() {
    const reportBundle = window.__CHROME_REPORT_DATA__ || {};
    if (reportBundle.landing) {
      state.payload = reportBundle.landing;
    } else if (state.standalone && window.__LANDING_TRACKER_STANDALONE_DATA__) {
      state.payload = window.__LANDING_TRACKER_STANDALONE_DATA__;
    } else if (state.initial) {
      state.payload = state.initial;
    }

    bindControls();
    if (state.payload) {
      syncDefaultWeekFilters();
      render();
    }
  }

  window.initLandingTrackerDashboard = function (data) {
    if (data) state.payload = data;
    syncDefaultWeekFilters();
    render();
  };

  init();
})();
