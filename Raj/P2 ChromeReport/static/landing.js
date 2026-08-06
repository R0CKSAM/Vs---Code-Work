(function () {
  const root = document.getElementById("landingTable");
  if (!root) return;

  const CHANNEL_TYPE_MAP = {
    landing_1: "Landing 1 View",
    landing_2: "Landing 2 View",
    landing_3: "Landing 3 View",
    barker_1: "Barker 1 View",
    barker_2: "Barker 2 View",
  };

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
      crn_no: [],
      sfrn_number: [],
      mso: [],
      channel_type: "landing_1",
      week_from: "",
      week_to: "",
      search: "",
    },
    page: 1,
    pageSize: 30,
    sortKey: "market",
    sortDirection: "asc",
    loading: false,
    standalone: Boolean(window.__LANDING_STANDALONE_DATA__),
    initial: window.__LANDING_INITIAL_DATA__ || null,
  };

  const viewTitle = document.getElementById("landingViewTitle");
  const tableHead = document.getElementById("landingTableHead");
  const tableBody = document.getElementById("landingTableBody");
  const resultCount = document.getElementById("landingResultCount");
  const pageInfo = document.getElementById("landingPageInfo");
  const prevPageBtn = document.getElementById("landingPrevPage");
  const nextPageBtn = document.getElementById("landingNextPage");
  const searchInput = document.getElementById("landingSearchInput");
  const resetButton = document.getElementById("landingResetButton");
  const fullscreenBtn = document.getElementById("landingFullscreenButton");
  const panel = root.closest(".landing-panel");

  // Summary KPI elements
  const kpiRows = document.getElementById("landingKpiTotalRows");
  const kpiMarket = document.getElementById("landingKpiTotalMarket");
  const kpiCity = document.getElementById("landingKpiTotalCity");
  const kpiMso = document.getElementById("landingKpiTotalMso");
  const kpiHeadend = document.getElementById("landingKpiTotalHeadend");
  const kpiChannel = document.getElementById("landingKpiTotalChannel");
  const kpiBand = document.getElementById("landingKpiTotalBand");

  function normalizeText(val) {
    return String(val || "").trim();
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
    band: getMultiSelect("landingBandFilter"),
    market: getMultiSelect("landingMarketFilter"),
    city: getMultiSelect("landingCityFilter"),
    headend: getMultiSelect("landingHeadendFilter"),
    state_name: getMultiSelect("landingStateFilter"),
    district: getMultiSelect("landingDistrictFilter"),
    feed: getMultiSelect("landingFeedFilter"),
    crn_no: getMultiSelect("landingCrnFilter"),
    sfrn_number: getMultiSelect("landingSfrnFilter"),
    mso: getMultiSelect("landingMsoFilter"),
    channel_type: getMultiSelect("landingChannelTypeFilter"),
    week_from: getMultiSelect("landingWeekFromFilter"),
    week_to: getMultiSelect("landingWeekToFilter"),
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

    if (fromIdx === -1) fromIdx = Math.max(0, allWeeks.length - 2);
    if (toIdx === -1) toIdx = allWeeks.length - 1;

    // Validation: Week From cannot be greater than Week To
    if (fromIdx > toIdx) {
      toIdx = fromIdx;
      state.filters.week_to = allWeeks[toIdx];
    }

    return allWeeks.slice(fromIdx, toIdx + 1);
  }

  function getFilteredSourceRecords(ignoreKey = "") {
    const allRecords = state.payload?.records || [];
    return allRecords.filter((rec) => {
      for (const key of Object.keys(controls)) {
        if (key === ignoreKey || key === "channel_type" || key === "week_from" || key === "week_to") continue;
        const sel = state.filters[key];
        if (Array.isArray(sel) && sel.length > 0) {
          const recVal = normalizeText(rec[key]);
          if (!sel.includes(recVal)) return false;
        }
      }
      return true;
    });
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
      const allWeeks = state.payload?.weeks || [];
      return allWeeks.map((wk) => ({ value: wk, label: wk }));
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

    if (key !== "channel_type" && key !== "week_from" && key !== "week_to") {
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

      if (key === "channel_type" || key === "week_from" || key === "week_to") {
        const radio = document.createElement("input");
        radio.type = "radio";
        radio.name = `landing_${key}`;
        radio.value = val;
        radio.checked = selected === val;
        radio.addEventListener("change", () => {
          state.filters[key] = val;
          const allWeeks = state.payload?.weeks || [];
          if (key === "week_from") {
            const fIdx = allWeeks.indexOf(val);
            const tIdx = allWeeks.indexOf(state.filters.week_to);
            if (fIdx > tIdx) state.filters.week_to = val;
          } else if (key === "week_to") {
            const tIdx = allWeeks.indexOf(val);
            const fIdx = allWeeks.indexOf(state.filters.week_from);
            if (tIdx < fIdx) state.filters.week_from = val;
          }
          updateButtonLabel(ctrl, val, placeholder);
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
    const q = normalizeText(state.filters.search).toLowerCase();

    return state.payload.records.filter((rec) => {
      for (const key of Object.keys(controls)) {
        if (key === "channel_type" || key === "week_from" || key === "week_to") continue;
        const sel = state.filters[key];
        if (Array.isArray(sel) && sel.length > 0) {
          const recVal = normalizeText(rec[key]);
          if (!sel.includes(recVal)) return false;
        }
      }

      if (q) {
        const haystack = [
          rec.band, rec.market, rec.city, rec.headend, rec.state_name, rec.district, rec.feed, rec.mso, rec.crn_no, rec.sf_crn, rec.put_up_lcn, rec.put_up_channel,
          ...Object.values(rec.weeks || {}).flatMap((w) => [w.channel_1, w.channel_2, w.channel_3, w.barker_1, w.barker_2, w.lcn_1, w.lcn_2, w.lcn_3, w.lcn_b1, w.lcn_b2, w.genre_1, w.genre_2, w.genre_3]),
        ].map(normalizeText).join(" ").toLowerCase();
        if (!haystack.includes(q)) return false;
      }
      return true;
    });
  }

  function renderTableHead(visibleWeeks) {
    if (!tableHead) return;
    const channelTypeKey = state.filters.channel_type || "landing_1";
    const viewLabel = CHANNEL_TYPE_MAP[channelTypeKey] || "Landing 1 View";
    if (viewTitle) viewTitle.textContent = viewLabel;

    const trGroup = document.createElement("tr");

    const baseCols = [
      { key: "band", label: "Band" },
      { key: "market", label: "Market" },
      { key: "city", label: "City" },
      { key: "headend", label: "Headend" },
      { key: "state_name", label: "State" },
      { key: "district", label: "District" },
      { key: "feed", label: "Feed" },
      { key: "crn_no", label: "CRN No" },
      { key: "sf_crn", label: "SF CRN" },
      { key: "mso", label: "MSO" },
      { key: "put_up_lcn", label: "Put-Up LCN" },
      { key: "put_up_channel", label: "Put-Up Channel" },
    ];

    baseCols.forEach((col) => {
      const th = document.createElement("th");
      th.textContent = col.label;
      th.rowSpan = 2;
      trGroup.appendChild(th);
    });

    visibleWeeks.forEach((wk) => {
      const th = document.createElement("th");
      th.textContent = wk;
      th.className = "landing-week-group-head";
      trGroup.appendChild(th);
    });

    const thChange = document.createElement("th");
    thChange.textContent = "Change Status";
    thChange.rowSpan = 2;
    trGroup.appendChild(thChange);

    const trSub = document.createElement("tr");
    const isBarker = channelTypeKey.startsWith("barker");
    const subLabel = isBarker ? "Barker Channel Name - LCN No" : "Landing Channel Name - LCN No";

    visibleWeeks.forEach(() => {
      const th = document.createElement("th");
      th.textContent = subLabel;
      th.className = "landing-subhead";
      trSub.appendChild(th);
    });

    tableHead.replaceChildren(trGroup, trSub);
  }

  function updateKpis(filteredRecords, visibleWeeks) {
    if (kpiRows) kpiRows.textContent = filteredRecords.length.toLocaleString("en-IN");
    if (kpiMarket) kpiMarket.textContent = new Set(filteredRecords.map((r) => r.market).filter(Boolean)).size;
    if (kpiCity) kpiCity.textContent = new Set(filteredRecords.map((r) => r.city).filter(Boolean)).size;
    if (kpiMso) kpiMso.textContent = new Set(filteredRecords.map((r) => r.mso).filter(Boolean)).size;
    if (kpiHeadend) kpiHeadend.textContent = new Set(filteredRecords.map((r) => r.headend).filter(Boolean)).size;
    if (kpiBand) kpiBand.textContent = new Set(filteredRecords.map((r) => r.band).filter(Boolean)).size;

    if (kpiChannel) {
      const channelSet = new Set();
      const channelTypeKey = state.filters.channel_type || "landing_1";
      filteredRecords.forEach((r) => {
        visibleWeeks.forEach((wk) => {
          const wObj = r.weeks?.[wk] || {};
          let ch = "";
          if (channelTypeKey === "landing_1") ch = wObj.channel_1;
          else if (channelTypeKey === "landing_2") ch = wObj.channel_2;
          else if (channelTypeKey === "landing_3") ch = wObj.channel_3;
          else if (channelTypeKey === "barker_1") ch = wObj.barker_1;
          else if (channelTypeKey === "barker_2") ch = wObj.barker_2;
          if (ch && ch.trim()) channelSet.add(ch.trim());
        });
      });
      kpiChannel.textContent = channelSet.size;
    }
  }

  function renderTableBody(records, visibleWeeks) {
    if (!tableBody) return;
    const totalCount = records.length;

    if (totalCount === 0) {
      if (resultCount) resultCount.textContent = "0 records";
      if (pageInfo) pageInfo.textContent = "Page 1 of 1";
      tableBody.innerHTML = `<tr><td colspan="100%" class="landing-empty-state">No Landing Channel data found.<br/><span style="font-size:0.75rem; font-weight:400; color:var(--muted);">Try changing filters.</span></td></tr>`;
      return;
    }

    const totalPages = Math.max(1, Math.ceil(totalCount / state.pageSize));
    if (state.page > totalPages) state.page = totalPages;

    const startIdx = (state.page - 1) * state.pageSize;
    const pageRecords = records.slice(startIdx, startIdx + state.pageSize);

    if (resultCount) resultCount.textContent = `${totalCount.toLocaleString("en-IN")} records`;
    if (pageInfo) pageInfo.textContent = `Page ${state.page} of ${totalPages}`;

    const channelTypeKey = state.filters.channel_type || "landing_1";
    const frag = document.createDocumentFragment();

    pageRecords.forEach((rec) => {
      const tr = document.createElement("tr");

      ["band", "market", "city", "headend", "state_name", "district", "feed", "crn_no", "sf_crn", "mso", "put_up_lcn", "put_up_channel"].forEach((colKey, idx) => {
        const td = document.createElement("td");
        const val = rec[colKey] || "--";
        td.textContent = val;
        td.title = val;
        if (idx < 4) {
          td.className = `landing-sticky-col landing-sticky-col-${idx + 1}`;
        }
        tr.appendChild(td);
      });

      let prevChannelName = "";
      let hasRowChanged = false;

      visibleWeeks.forEach((wk, weekIdx) => {
        const weekObj = rec.weeks?.[wk] || {};
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

        const tdWeek = document.createElement("td");
        const tooltipText = `Channel: ${channelName || "--"}${lcnVal ? " | LCN: " + lcnVal : ""}${genreVal ? " | Genre: " + genreVal : ""}`;
        tdWeek.title = tooltipText;

        const hasChanged = weekIdx > 0 &&
          normalizeText(prevChannelName).toUpperCase() !== "" &&
          normalizeText(channelName).toUpperCase() !== "" &&
          normalizeText(prevChannelName).toUpperCase() !== normalizeText(channelName).toUpperCase();

        if (hasChanged) {
          hasRowChanged = true;
          const spanChan = document.createElement("span");
          spanChan.className = "landing-channel-changed";
          spanChan.textContent = channelName || "--";
          tdWeek.appendChild(spanChan);
          if (lcnVal) {
            const txtLcn = document.createTextNode(` - ${lcnVal}`);
            tdWeek.appendChild(txtLcn);
          }
        } else {
          const displayText = `${channelName || "--"}${lcnVal ? " - " + lcnVal : ""}`;
          tdWeek.textContent = displayText;
        }

        prevChannelName = channelName;
        tr.appendChild(tdWeek);
      });

      // Change Status Column
      const tdStatus = document.createElement("td");
      tdStatus.style.textAlign = "center";
      const statusBadge = document.createElement("span");
      if (hasRowChanged) {
        statusBadge.className = "landing-badge-changed";
        statusBadge.textContent = "Change";
      } else {
        statusBadge.className = "landing-badge-no-change";
        statusBadge.textContent = "No Change";
      }
      tdStatus.appendChild(statusBadge);
      tr.appendChild(tdStatus);

      frag.appendChild(tr);
    });

    tableBody.replaceChildren(frag);
  }

  function render() {
    const visibleWeeks = getVisibleWeeks();
    const filteredRecords = filterRecords();
    renderTableHead(visibleWeeks);
    renderTableBody(filteredRecords, visibleWeeks);
    updateKpis(filteredRecords, visibleWeeks);
    syncFilterLabels();
  }

  function syncFilterLabels() {
    const placeholders = {
      band: "All Bands",
      market: "All Markets",
      city: "All Cities",
      headend: "All Headends",
      state_name: "All States",
      district: "All Districts",
      feed: "All Feeds",
      crn_no: "All CRN No",
      sfrn_number: "All SF CRN",
      mso: "All MSO",
      channel_type: "Landing Channel 1",
      week_from: "Week From",
      week_to: "Week To",
    };
    Object.keys(controls).forEach((key) => {
      const selected = state.filters[key];
      let labelText = selected;
      if (key === "channel_type") labelText = CHANNEL_TYPE_MAP[selected] || "Landing Channel 1";
      updateButtonLabel(controls[key], labelText, placeholders[key]);
    });
  }

  function bindControls() {
    const placeholders = {
      band: "All Bands",
      market: "All Markets",
      city: "All Cities",
      headend: "All Headends",
      state_name: "All States",
      district: "All Districts",
      feed: "All Feeds",
      crn_no: "All CRN No",
      sfrn_number: "All SF CRN",
      mso: "All MSO",
      channel_type: "Landing Channel 1",
      week_from: "Week From",
      week_to: "Week To",
    };

    Object.keys(controls).forEach((key) => {
      bindMultiSelect(key, controls[key], placeholders[key]);
    });

    document.addEventListener("click", (e) => {
      if (!e.target.closest(".filter-select")) closeAllMenus();
    });

    if (searchInput) {
      searchInput.addEventListener("input", () => {
        state.filters.search = searchInput.value;
        state.page = 1;
        render();
      });
    }

    if (resetButton) {
      resetButton.addEventListener("click", () => {
        const allWeeks = state.payload?.weeks || [];
        state.filters = {
          band: [],
          market: [],
          city: [],
          headend: [],
          state_name: [],
          district: [],
          feed: [],
          crn_no: [],
          sfrn_number: [],
          mso: [],
          channel_type: "landing_1",
          week_from: allWeeks.length >= 2 ? allWeeks[allWeeks.length - 2] : (allWeeks[0] || ""),
          week_to: allWeeks.length >= 1 ? allWeeks[allWeeks.length - 1] : "",
          search: "",
        };
        if (searchInput) searchInput.value = "";
        state.page = 1;
        render();
      });
    }

    if (prevPageBtn) {
      prevPageBtn.addEventListener("click", () => {
        if (state.page > 1) {
          state.page -= 1;
          render();
        }
      });
    }

    if (nextPageBtn) {
      nextPageBtn.addEventListener("click", () => {
        const filteredRecords = filterRecords();
        const totalPages = Math.max(1, Math.ceil(filteredRecords.length / state.pageSize));
        if (state.page < totalPages) {
          state.page += 1;
          render();
        }
      });
    }

    if (fullscreenBtn) {
      fullscreenBtn.addEventListener("click", () => {
        if (!panel) return;
        fullscreenState.active = !fullscreenState.active;
        if (fullscreenState.active) {
          panel.classList.add("landing-panel-fullscreen");
          fullscreenBtn.textContent = "Exit Full Screen";
        } else {
          panel.classList.remove("landing-panel-fullscreen");
          fullscreenBtn.textContent = "Full Screen";
        }
      });
    }
  }

  function init() {
    if (state.standalone && window.__LANDING_STANDALONE_DATA__) {
      state.payload = window.__LANDING_STANDALONE_DATA__;
    } else if (state.initial) {
      state.payload = state.initial;
    }

    bindControls();
    if (state.payload) {
      syncDefaultWeekFilters();
      render();
    }
  }

  window.initLandingDashboard = function (data) {
    if (data) {
      state.payload = data;
      syncDefaultWeekFilters();
    }
    render();
  };

  init();
})();
