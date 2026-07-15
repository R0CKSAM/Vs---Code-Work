const columns = [
    { key: "transmission", label: "Transmission", filterable: true },
    { key: "mso", label: "MSO", filterable: true },
    { key: "market", label: "Market", filterable: true },
    { key: "mso_type", label: "MSO Type", filterable: true },
    { key: "city", label: "City", filterable: true },
    { key: "head_end", label: "Head End", filterable: true },
    { key: "channel_name", label: "Channel Name", filterable: true },
    { key: "band", label: "Band", filterable: true },
    { key: "tv_channel_no", label: "TV Channel No", filterable: true },
    { key: "cr_no", label: "CR No", filterable: true },
    { key: "w1_frequency", label: "Week 1 Frequency", filterable: false },
    { key: "w2_frequency", label: "Week 2 Frequency", filterable: false },
    { key: "w3_frequency", label: "Week 3 Frequency", filterable: false },
    { key: "w4_frequency", label: "Week 4 Frequency", filterable: false },
    { key: "change_status", label: "Change Status", filterable: true },
];

const defaultChannel = "India TV";

const state = {
    records: [],
    dataTable: null,
    selectedFilters: {},
    popupColumn: null,
    popupSearch: "",
};

const elements = {
    refreshButton: document.getElementById("refreshButton"),
    fullscreenButton: document.getElementById("fullscreenButton"),
    applyFiltersButton: document.getElementById("applyFilters"),
    resetFiltersButton: document.getElementById("resetFilters"),
    sourceFilesPill: document.getElementById("sourceFilesPill"),
    statusPill: document.getElementById("statusPill"),
    errorBox: document.getElementById("errorBox"),
    tableLoading: document.getElementById("tableLoading"),
    tableHead: document.getElementById("reportTableHead"),
    tableFrame: document.getElementById("tableFrame"),
    kpiTotalRecords: document.getElementById("kpiTotalRecords"),
    kpiTotalMarkets: document.getElementById("kpiTotalMarkets"),
    kpiTotalMsos: document.getElementById("kpiTotalMsos"),
    kpiTotalChannels: document.getElementById("kpiTotalChannels"),
    kpiChangedRecords: document.getElementById("kpiChangedRecords"),
    kpiNoChangeRecords: document.getElementById("kpiNoChangeRecords"),
    kpiIndiaTvAvg: document.getElementById("kpiIndiaTvAvg"),
    kpiHighestChannel: document.getElementById("kpiHighestChannel"),
    kpiHighestChannelValue: document.getElementById("kpiHighestChannelValue"),
};

function initializeFilterState() {
    state.selectedFilters = Object.fromEntries(
        columns.filter((column) => column.filterable).map((column) => [column.key, new Set()])
    );
}

function safeNumber(value) {
    if (value === "NA" || value === "" || value === null || value === undefined) {
        return null;
    }
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
}

function compareClass(current, previous) {
    const currentValue = safeNumber(current);
    const previousValue = safeNumber(previous);
    if (currentValue === null || previousValue === null) return "compare-same";
    if (currentValue < previousValue) return "compare-down";
    if (currentValue > previousValue) return "compare-up";
    return "compare-same";
}

function changeStatusClass(value) {
    return value === "CHANGED" ? "change-changed" : "change-no-change";
}

function clearError() {
    elements.errorBox.hidden = true;
    elements.errorBox.textContent = "";
}

function showError(message) {
    elements.errorBox.hidden = false;
    elements.errorBox.textContent = message;
}

function setLoading(active, message = "Fetching latest data...") {
    elements.tableLoading.hidden = !active;
    elements.tableLoading.textContent = message;
}

function setSummaryKpis(summary) {
    elements.kpiTotalRecords.textContent = (summary.record_count || 0).toLocaleString();
    elements.kpiTotalMarkets.textContent = (summary.total_markets || 0).toLocaleString();
    elements.kpiTotalMsos.textContent = (summary.total_msos || 0).toLocaleString();
    elements.kpiTotalChannels.textContent = (summary.total_channels || 0).toLocaleString();
    elements.kpiChangedRecords.textContent = (summary.changed_records || 0).toLocaleString();
    elements.kpiNoChangeRecords.textContent = (summary.no_change_records || 0).toLocaleString();
    elements.kpiIndiaTvAvg.textContent = summary.india_tv_average_frequency || 0;
    elements.kpiHighestChannel.textContent = summary.highest_frequency_channel || "-";
    elements.kpiHighestChannelValue.textContent = summary.highest_frequency_value
        ? `Peak frequency ${summary.highest_frequency_value}`
        : "No matching records";
}

function displayFrequency(value) {
    if (value === null || value === undefined || value === "") {
        return "NA";
    }
    return String(value);
}

function normalizeRecord(record) {
    return {
        ...record,
        w1_frequency: displayFrequency(record.w1_frequency),
        w2_frequency: displayFrequency(record.w2_frequency),
        w3_frequency: displayFrequency(record.w3_frequency),
        w4_frequency: displayFrequency(record.w4_frequency),
    };
}

function recordMatches(record) {
    return Object.entries(state.selectedFilters).every(([key, selected]) => {
        if (!selected.size) return true;
        return selected.has(record[key]);
    });
}

function getColumnOptions(columnKey) {
    return [...new Set(state.records.map((record) => record[columnKey]).filter(Boolean))].sort((a, b) =>
        String(a).localeCompare(String(b), undefined, { sensitivity: "base" })
    );
}

function getVisibleFilterOptions(columnKey) {
    const query = state.popupSearch.trim().toLowerCase();
    return getColumnOptions(columnKey).filter((value) =>
        String(value).toLowerCase().includes(query)
    );
}

function filterButtonClass(columnKey) {
    return state.selectedFilters[columnKey]?.size ? "header-filter-button active" : "header-filter-button";
}

function renderTableHeader() {
    elements.tableHead.innerHTML = `
        <tr>
            ${columns.map((column) => `
                <th data-column="${column.key}">
                    <div class="header-cell">
                        <div class="header-top">
                            <span class="header-label">${column.label}</span>
                            ${column.filterable ? `<button type="button" class="${filterButtonClass(column.key)}" data-filter-button="${column.key}">&#9662;</button>` : ""}
                        </div>
                    </div>
                </th>
            `).join("")}
        </tr>
    `;
}

function renderFilterPopup(columnKey, anchor) {
    removeFilterPopup();

    const popup = document.createElement("div");
    popup.id = "headerFilterPopup";
    popup.className = "filter-popup";
    popup.dataset.column = columnKey;

    const options = getVisibleFilterOptions(columnKey);
    popup.innerHTML = `
        <input class="filter-popup-search" type="search" placeholder="Search ${columns.find((column) => column.key === columnKey).label}..." value="${escapeHtml(state.popupSearch)}">
        <div class="filter-popup-actions">
            <button type="button" data-action="select-all">Select All</button>
            <button type="button" data-action="clear">Clear Selection</button>
        </div>
        <div class="filter-popup-options">
            ${options.map((value) => `
                <label class="filter-popup-option">
                    <input type="checkbox" value="${escapeHtml(value)}" ${state.selectedFilters[columnKey].has(value) ? "checked" : ""}>
                    <span>${escapeHtml(value)}</span>
                </label>
            `).join("")}
        </div>
    `;

    document.body.appendChild(popup);
    const rect = anchor.getBoundingClientRect();
    popup.style.top = `${rect.bottom + 6}px`;
    popup.style.left = `${Math.max(12, rect.left - 200 + rect.width)}px`;
}

function removeFilterPopup() {
    document.getElementById("headerFilterPopup")?.remove();
}

function updateKpis(records) {
    const totalRecords = records.length;
    const totalMarkets = new Set(records.map((record) => record.market).filter(Boolean)).size;
    const totalMsos = new Set(records.map((record) => record.mso).filter(Boolean)).size;
    const totalChannels = new Set(records.map((record) => record.channel_name).filter(Boolean)).size;
    const changedRecords = records.filter((record) => record.change_status === "CHANGED").length;
    const noChangeRecords = records.filter((record) => record.change_status === "NO CHANGE").length;

    const indiaTvValues = records
        .filter((record) => record.channel_name === defaultChannel)
        .flatMap((record) => [record.w1_frequency, record.w2_frequency, record.w3_frequency, record.w4_frequency])
        .map(safeNumber)
        .filter((value) => value !== null);

    const indiaTvAverage = indiaTvValues.length
        ? (indiaTvValues.reduce((sum, value) => sum + value, 0) / indiaTvValues.length).toFixed(2)
        : "0";

    let highestChannel = "-";
    let highestValue = null;
    records.forEach((record) => {
        [record.w1_frequency, record.w2_frequency, record.w3_frequency, record.w4_frequency]
            .map(safeNumber)
            .filter((value) => value !== null)
            .forEach((value) => {
                if (highestValue === null || value > highestValue) {
                    highestValue = value;
                    highestChannel = record.channel_name;
                }
            });
    });

    elements.kpiTotalRecords.textContent = totalRecords.toLocaleString();
    elements.kpiTotalMarkets.textContent = totalMarkets.toLocaleString();
    elements.kpiTotalMsos.textContent = totalMsos.toLocaleString();
    elements.kpiTotalChannels.textContent = totalChannels.toLocaleString();
    elements.kpiChangedRecords.textContent = changedRecords.toLocaleString();
    elements.kpiNoChangeRecords.textContent = noChangeRecords.toLocaleString();
    elements.kpiIndiaTvAvg.textContent = indiaTvAverage;
    elements.kpiHighestChannel.textContent = highestChannel;
    elements.kpiHighestChannelValue.textContent = highestValue === null ? "No matching records" : `Peak frequency ${highestValue}`;
}

function buildTable() {
    renderTableHeader();

    if (state.dataTable) {
        state.dataTable.destroy();
    }

    $.fn.dataTable.ext.search = $.fn.dataTable.ext.search.filter((fn) => !fn.__chromeHeaderFilter);
    const customFilter = (settings, _, dataIndex) => {
        if (settings.nTable.id !== "reportTable") return true;
        const record = state.records[dataIndex];
        return record ? recordMatches(record) : true;
    };
    customFilter.__chromeHeaderFilter = true;
    $.fn.dataTable.ext.search.push(customFilter);

    state.dataTable = new DataTable("#reportTable", {
        data: state.records,
        columns: [
            { data: "transmission" },
            { data: "mso" },
            { data: "market" },
            { data: "mso_type" },
            { data: "city" },
            { data: "head_end" },
            { data: "channel_name" },
            { data: "band" },
            { data: "tv_channel_no" },
            { data: "cr_no" },
            { data: "w1_frequency", render: (data) => `<span class="compare-same">${displayFrequency(data)}</span>` },
            { data: "w2_frequency", render: (data, _, row) => `<span class="${compareClass(data, row.w1_frequency)}">${displayFrequency(data)}</span>` },
            { data: "w3_frequency", render: (data, _, row) => `<span class="${compareClass(data, row.w2_frequency)}">${displayFrequency(data)}</span>` },
            { data: "w4_frequency", render: (data, _, row) => `<span class="${compareClass(data, row.w3_frequency)}">${displayFrequency(data)}</span>` },
            { data: "change_status", render: (data) => `<span class="${changeStatusClass(data)}">${data}</span>` },
        ],
        paging: true,
        searching: false,
        ordering: true,
        info: true,
        fixedHeader: true,
        scrollX: true,
        scrollY: "540px",
        pageLength: 25,
        lengthMenu: [25, 50, 100],
        order: [[6, "asc"]],
        deferRender: true,
        autoWidth: false,
        dom: "lrtip",
        columnDefs: [
            { targets: 0, width: "90px" },
            { targets: 1, width: "100px" },
            { targets: 2, width: "90px" },
            { targets: 3, width: "90px" },
            { targets: 4, width: "90px" },
            { targets: 5, width: "100px" },
            { targets: 6, width: "120px" },
            { targets: 7, width: "60px" },
            { targets: 8, width: "80px" },
            { targets: 9, width: "80px" },
            { targets: 10, width: "90px" },
            { targets: 11, width: "90px" },
            { targets: 12, width: "90px" },
            { targets: 13, width: "90px" },
            { targets: 14, width: "100px" },
        ],
        language: {
            lengthMenu: "Show _MENU_ rows",
            emptyTable: "Fetching latest data...",
        },
        drawCallback: function () {
            const visibleRecords = this.api().rows({ search: "applied" }).data().toArray();
            updateKpis(visibleRecords);
            elements.statusPill.textContent = `${visibleRecords.length.toLocaleString()} visible records`;
            renderTableHeader();
        },
        initComplete: function () {
            setLoading(false);
        },
    });
}

function applyFilters() {
    if (state.dataTable) {
        state.dataTable.draw();
    }
}

function setMeta(summary) {
    const sourceFiles = summary?.source_files || [];
    elements.sourceFilesPill.textContent = sourceFiles.length ? sourceFiles.join(" | ") : "Source files not available";
}

function loadScript(src) {
    return new Promise((resolve, reject) => {
        const script = document.createElement("script");
        script.src = `${src}?v=${Date.now()}`;
        script.onload = resolve;
        script.onerror = () => reject(new Error(`Unable to load ${src}`));
        document.body.appendChild(script);
    });
}

async function loadKpiSummary() {
    const summary = window.CHROME_REPORT_KPI_SUMMARY;
    if (!summary) {
        throw new Error("Missing data/kpi_summary.js. Run python/generate_json.py first.");
    }
    setSummaryKpis(summary);
    setMeta(summary);
    elements.statusPill.textContent = "KPI ready, table loading";
}

async function loadMergedData() {
    setLoading(true, "Fetching latest data...");
    await loadScript("data/merged_data.js");
    const mergedData = window.CHROME_REPORT_MERGED_DATA;
    if (!mergedData || !Array.isArray(mergedData.records)) {
        throw new Error("Missing data/merged_data.js. Run python/generate_json.py first.");
    }
    state.records = mergedData.records.map(normalizeRecord);
    buildTable();
    applyFilters();
}

function bindButtons() {
    elements.refreshButton.addEventListener("click", () => window.location.reload());
    elements.applyFiltersButton.addEventListener("click", () => {
        removeFilterPopup();
        state.popupColumn = null;
        state.popupSearch = "";
        applyFilters();
    });
    elements.resetFiltersButton.addEventListener("click", () => {
        initializeFilterState();
        state.popupSearch = "";
        state.popupColumn = null;
        removeFilterPopup();
        renderTableHeader();
        applyFilters();
    });
    elements.fullscreenButton.addEventListener("click", async () => {
        if (!document.fullscreenElement) {
            await elements.tableFrame.requestFullscreen();
        } else {
            await document.exitFullscreen();
        }
    });
    document.addEventListener("fullscreenchange", () => {
        elements.fullscreenButton.textContent = document.fullscreenElement ? "Exit Full Screen" : "Full Screen";
    });
}

function bindHeaderFilters() {
    document.addEventListener("click", (event) => {
        const filterButton = event.target.closest("[data-filter-button]");
        if (filterButton) {
            const columnKey = filterButton.dataset.filterButton;
            if (state.popupColumn === columnKey) {
                state.popupColumn = null;
                state.popupSearch = "";
                removeFilterPopup();
            } else {
                state.popupColumn = columnKey;
                state.popupSearch = "";
                renderFilterPopup(columnKey, filterButton);
            }
            return;
        }

        const popup = event.target.closest("#headerFilterPopup");
        if (!popup) {
            state.popupColumn = null;
            state.popupSearch = "";
            removeFilterPopup();
            return;
        }

        const columnKey = popup.dataset.column;
        if (event.target.matches("[data-action='select-all']")) {
            getVisibleFilterOptions(columnKey).forEach((value) => state.selectedFilters[columnKey].add(value));
            renderFilterPopup(columnKey, document.querySelector(`[data-filter-button="${columnKey}"]`));
            renderTableHeader();
            applyFilters();
            return;
        }

        if (event.target.matches("[data-action='clear']")) {
            state.selectedFilters[columnKey].clear();
            renderFilterPopup(columnKey, document.querySelector(`[data-filter-button="${columnKey}"]`));
            renderTableHeader();
            applyFilters();
            return;
        }
    });

    document.addEventListener("input", (event) => {
        const popup = event.target.closest("#headerFilterPopup");
        if (!popup) return;
        const columnKey = popup.dataset.column;

        if (event.target.classList.contains("filter-popup-search")) {
            state.popupSearch = event.target.value;
            renderFilterPopup(columnKey, document.querySelector(`[data-filter-button="${columnKey}"]`));
            return;
        }

        if (event.target.type === "checkbox") {
            if (event.target.checked) {
                state.selectedFilters[columnKey].add(event.target.value);
            } else {
                state.selectedFilters[columnKey].delete(event.target.value);
            }
            renderFilterPopup(columnKey, document.querySelector(`[data-filter-button="${columnKey}"]`));
            renderTableHeader();
            applyFilters();
        }
    });
}

async function initializeDashboard() {
    clearError();
    initializeFilterState();
    bindButtons();
    bindHeaderFilters();

    try {
        await loadKpiSummary();
        await loadMergedData();
    } catch (error) {
        showError(error.message);
        setLoading(false);
        elements.statusPill.textContent = "Dashboard failed to load";
    }
}

function escapeHtml(value) {
    return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
}

initializeDashboard();
