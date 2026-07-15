const columns = [
    "week",
    "transmission",
    "mso",
    "market",
    "mso_type",
    "city",
    "head_end",
    "channel_name",
    "band",
    "tv_channel_no",
    "cr_no",
    "w1_frequency",
    "w2_frequency",
    "w3_frequency",
    "w4_frequency",
    "change_status",
];

const filterColumns = [
    "week",
    "transmission",
    "mso",
    "market",
    "mso_type",
    "city",
    "head_end",
    "channel_name",
    "band",
    "tv_channel_no",
    "cr_no",
    "change_status",
];

const filterLabels = {
    week: "Week",
    transmission: "Transmission",
    mso: "MSO",
    market: "Market",
    mso_type: "MSO Type",
    city: "City",
    head_end: "Head End",
    channel_name: "Channel Name",
    band: "Band",
    tv_channel_no: "TV Channel No",
    cr_no: "CR No",
    change_status: "Change Status",
};

const defaultChannel = "India TV";

const state = {
    records: [],
    selectedFilters: {},
    dataTable: null,
    chartInstances: [],
    fullDataLoaded: false,
    chartDataLoaded: false,
};

const elements = {
    columnFilters: document.getElementById("columnFilters"),
    refreshButton: document.getElementById("refreshButton"),
    viewAnalyticsButton: document.getElementById("viewAnalyticsButton"),
    fullscreenButton: document.getElementById("fullscreenButton"),
    resetFiltersButton: document.getElementById("resetFilters"),
    applyFiltersButton: document.getElementById("applyFilters"),
    sourceFilesPill: document.getElementById("sourceFilesPill"),
    statusPill: document.getElementById("statusPill"),
    filterStatus: document.getElementById("filterStatus"),
    errorBox: document.getElementById("errorBox"),
    tableLoading: document.getElementById("tableLoading"),
    analyticsPanel: document.getElementById("analyticsPanel"),
    analyticsStatus: document.getElementById("analyticsStatus"),
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

function resetSelectionState() {
    state.selectedFilters = Object.fromEntries(
        filterColumns.map((column) => [column, new Set()])
    );
    state.selectedFilters.channel_name = new Set([defaultChannel]);
}

function safeNumber(value) {
    const number = Number(value);
    return Number.isFinite(number) ? number : null;
}

function compareClass(current, previous) {
    const currentValue = safeNumber(current);
    const previousValue = safeNumber(previous);
    if (currentValue === null || previousValue === null) return "compare-same";
    if (currentValue > previousValue) return "compare-up";
    if (currentValue < previousValue) return "compare-down";
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

function getUniqueOptions(column) {
    return [...new Set(state.records.map((record) => record[column]).filter(Boolean))].sort((a, b) =>
        String(a).localeCompare(String(b), undefined, { sensitivity: "base" })
    );
}

function updateTriggerText(card) {
    const column = card.dataset.column;
    const selected = [...state.selectedFilters[column]];
    const textWrap = card.querySelector(".filter-trigger-text");

    if (!selected.length) {
        textWrap.innerHTML = '<span class="filter-placeholder">All values</span>';
        return;
    }

    const visible = selected.slice(0, 2)
        .map((value) => `<span class="filter-chip">${value}</span>`)
        .join("");
    const extra = selected.length > 2 ? `<span class="filter-count">+${selected.length - 2} more</span>` : "";
    textWrap.innerHTML = `${visible}${extra}`;
}

function renderFilterOptions(card, query = "") {
    const column = card.dataset.column;
    const optionsWrap = card.querySelector(".filter-options");
    const lowerQuery = query.trim().toLowerCase();
    const options = getUniqueOptions(column).filter((value) =>
        String(value).toLowerCase().includes(lowerQuery)
    );

    optionsWrap.innerHTML = options
        .map((value) => `
            <label class="filter-option">
                <input type="checkbox" value="${String(value).replaceAll('"', "&quot;")}" ${state.selectedFilters[column].has(value) ? "checked" : ""}>
                <span>${value}</span>
            </label>
        `)
        .join("");
}

function createFilterCard(column) {
    const card = document.createElement("div");
    card.className = "filter-card";
    card.dataset.column = column;
    card.innerHTML = `
        <label class="filter-label">${filterLabels[column]}</label>
        <button type="button" class="filter-trigger">
            <span class="filter-trigger-text"></span>
            <span>▼</span>
        </button>
        <div class="filter-menu">
            <input class="filter-search" type="search" placeholder="Search ${filterLabels[column]}...">
            <div class="filter-menu-actions">
                <button type="button" class="select-all">Select All</button>
                <button type="button" class="clear-filter">Clear</button>
            </div>
            <div class="filter-options"></div>
        </div>
    `;

    updateTriggerText(card);
    renderFilterOptions(card);
    return card;
}

function renderFilters() {
    elements.columnFilters.innerHTML = "";
    filterColumns.forEach((column) => {
        elements.columnFilters.appendChild(createFilterCard(column));
    });
    elements.filterStatus.textContent = state.fullDataLoaded
        ? "Filters are live and update the table immediately."
        : "Fetching latest data...";
}

function closeOtherMenus(currentCard) {
    document.querySelectorAll(".filter-card.open").forEach((card) => {
        if (card !== currentCard) {
            card.classList.remove("open");
        }
    });
}

function bindFilterEvents() {
    elements.columnFilters.addEventListener("click", (event) => {
        const card = event.target.closest(".filter-card");
        const trigger = event.target.closest(".filter-trigger");

        if (trigger && card) {
            closeOtherMenus(card);
            card.classList.toggle("open");
            return;
        }

        if (event.target.closest(".clear-filter") && card) {
            state.selectedFilters[card.dataset.column].clear();
            renderFilterOptions(card, card.querySelector(".filter-search").value);
            updateTriggerText(card);
            applyFilters();
            return;
        }

        if (event.target.closest(".select-all") && card) {
            getUniqueOptions(card.dataset.column).forEach((value) => state.selectedFilters[card.dataset.column].add(value));
            renderFilterOptions(card, card.querySelector(".filter-search").value);
            updateTriggerText(card);
            applyFilters();
        }
    });

    elements.columnFilters.addEventListener("input", (event) => {
        const card = event.target.closest(".filter-card");
        if (!card) return;

        if (event.target.classList.contains("filter-search")) {
            renderFilterOptions(card, event.target.value);
            return;
        }

        if (event.target.type === "checkbox") {
            const { column } = card.dataset;
            if (event.target.checked) {
                state.selectedFilters[column].add(event.target.value);
            } else {
                state.selectedFilters[column].delete(event.target.value);
            }
            updateTriggerText(card);
            applyFilters();
        }
    });

    document.addEventListener("click", (event) => {
        if (!event.target.closest(".filter-card")) {
            document.querySelectorAll(".filter-card.open").forEach((card) => card.classList.remove("open"));
        }
    });
}

function recordMatches(record) {
    return filterColumns.every((column) => {
        const selected = state.selectedFilters[column];
        if (!selected || !selected.size) return true;
        return selected.has(record[column]);
    });
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
    if (state.dataTable) {
        state.dataTable.destroy();
        $("#reportTable").empty().append(`
            <thead>
                <tr>
                    <th>Week</th>
                    <th>Transmission</th>
                    <th>MSO</th>
                    <th>Market</th>
                    <th>MSO Type</th>
                    <th>City</th>
                    <th>Head End</th>
                    <th>Channel Name</th>
                    <th>Band</th>
                    <th>TV Channel No</th>
                    <th>CR No</th>
                    <th>W1 Frequency</th>
                    <th>W2 Frequency</th>
                    <th>W3 Frequency</th>
                    <th>W4 Frequency</th>
                    <th>Change Status</th>
                </tr>
            </thead>
            <tbody></tbody>
        `);
    }

    $.fn.dataTable.ext.search = $.fn.dataTable.ext.search.filter((fn) => !fn.__chromeReportFilter);
    const customFilter = (settings, _, dataIndex) => {
        if (settings.nTable.id !== "reportTable") return true;
        const record = state.records[dataIndex];
        return record ? recordMatches(record) : true;
    };
    customFilter.__chromeReportFilter = true;
    $.fn.dataTable.ext.search.push(customFilter);

    state.dataTable = new DataTable("#reportTable", {
        data: state.records,
        columns: [
            { data: "week" },
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
            { data: "w1_frequency", render: (data) => `<span class="compare-same">${data ?? ""}</span>` },
            { data: "w2_frequency", render: (data, _, row) => `<span class="${compareClass(data, row.w1_frequency)}">${data ?? ""}</span>` },
            { data: "w3_frequency", render: (data, _, row) => `<span class="${compareClass(data, row.w2_frequency)}">${data ?? ""}</span>` },
            { data: "w4_frequency", render: (data, _, row) => `<span class="${compareClass(data, row.w3_frequency)}">${data ?? ""}</span>` },
            { data: "change_status", render: (data) => `<span class="${changeStatusClass(data)}">${data}</span>` },
        ],
        paging: true,
        searching: true,
        ordering: true,
        info: true,
        responsive: true,
        fixedHeader: true,
        scrollX: true,
        scrollY: "540px",
        pageLength: 25,
        lengthMenu: [10, 25, 50, 100],
        order: [[7, "asc"]],
        deferRender: true,
        dom: "Bfrtip",
        buttons: ["copyHtml5", "csvHtml5", "excelHtml5", "print"],
        language: {
            search: "Global Search:",
            lengthMenu: "Show _MENU_ rows",
            emptyTable: "Fetching latest data...",
        },
        drawCallback: function () {
            const visibleRecords = this.api().rows({ search: "applied" }).data().toArray();
            updateKpis(visibleRecords);
            elements.statusPill.textContent = `${visibleRecords.length.toLocaleString()} visible records`;
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
    elements.statusPill.textContent = "KPI ready, table loading in background";
}

async function loadMergedData() {
    setLoading(true, "Fetching latest data...");
    elements.filterStatus.textContent = "Fetching latest data...";
    await loadScript("data/merged_data.js");

    const mergedData = window.CHROME_REPORT_MERGED_DATA;
    if (!mergedData || !Array.isArray(mergedData.records)) {
        throw new Error("Missing data/merged_data.js. Run python/generate_json.py first.");
    }

    state.records = mergedData.records;
    state.fullDataLoaded = true;
    resetSelectionState();
    renderFilters();
    buildTable();
    applyFilters();
    setLoading(false);
    elements.filterStatus.textContent = "Filters are live and update results instantly.";
}

async function loadChartAssets() {
    if (!window.Chart) {
        await loadScript("https://cdn.jsdelivr.net/npm/chart.js");
    }
    if (!state.chartDataLoaded) {
        await loadScript("data/chart_data.js");
        state.chartDataLoaded = true;
    }
}

function destroyCharts() {
    state.chartInstances.forEach((chart) => chart.destroy());
    state.chartInstances = [];
}

function buildAnalyticsCharts() {
    const chartData = window.CHROME_REPORT_CHART_DATA;
    if (!chartData) {
        throw new Error("Missing data/chart_data.js. Run python/generate_json.py first.");
    }

    destroyCharts();
    const commonOptions = {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: { labels: { color: "#f8fafc" } },
        },
        scales: {
            x: { ticks: { color: "#cbd5e1" }, grid: { color: "rgba(148,163,184,0.15)" } },
            y: { ticks: { color: "#cbd5e1" }, grid: { color: "rgba(148,163,184,0.15)" } },
        },
    };

    state.chartInstances.push(new Chart(document.getElementById("trendChart"), {
        type: "line",
        data: {
            labels: chartData.weekly_trend.labels,
            datasets: [{ label: "Average Frequency", data: chartData.weekly_trend.values, borderColor: "#3b82f6", backgroundColor: "rgba(59,130,246,0.2)" }],
        },
        options: commonOptions,
    }));

    state.chartInstances.push(new Chart(document.getElementById("marketChart"), {
        type: "bar",
        data: {
            labels: chartData.top_markets.labels,
            datasets: [{ label: "Changed Records", data: chartData.top_markets.values, backgroundColor: "#22c55e" }],
        },
        options: commonOptions,
    }));

    state.chartInstances.push(new Chart(document.getElementById("msoChart"), {
        type: "bar",
        data: {
            labels: chartData.top_msos.labels,
            datasets: [{ label: "Changed Records", data: chartData.top_msos.values, backgroundColor: "#facc15" }],
        },
        options: commonOptions,
    }));

    state.chartInstances.push(new Chart(document.getElementById("distributionChart"), {
        type: "doughnut",
        data: {
            labels: chartData.frequency_distribution.labels,
            datasets: [{ data: chartData.frequency_distribution.values, backgroundColor: ["#3b82f6", "#22c55e", "#facc15", "#ef4444", "#8b5cf6", "#14b8a6", "#f97316"] }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { labels: { color: "#f8fafc" } } },
        },
    }));
}

async function openAnalytics() {
    try {
        elements.analyticsPanel.hidden = false;
        elements.analyticsStatus.textContent = "Loading analytics...";
        await loadChartAssets();
        buildAnalyticsCharts();
        elements.analyticsStatus.textContent = "Analytics loaded on demand";
    } catch (error) {
        showError(error.message);
        elements.analyticsStatus.textContent = "Analytics failed to load";
    }
}

async function initializeDashboard() {
    clearError();
    setLoading(true, "Fetching latest data...");
    resetSelectionState();
    elements.columnFilters.innerHTML = "";

    try {
        await loadKpiSummary();
        setTimeout(async () => {
            try {
                await loadMergedData();
            } catch (error) {
                showError(error.message);
                setLoading(false);
                elements.statusPill.textContent = "Table load failed";
            }
        }, 50);
    } catch (error) {
        showError(error.message);
        setLoading(false);
        elements.statusPill.textContent = "KPI load failed";
    }
}

function bindButtons() {
    elements.refreshButton.addEventListener("click", () => {
        window.location.reload();
    });
    elements.viewAnalyticsButton.addEventListener("click", openAnalytics);
    elements.resetFiltersButton.addEventListener("click", () => {
        resetSelectionState();
        renderFilters();
        applyFilters();
    });
    elements.applyFiltersButton.addEventListener("click", applyFilters);

    elements.fullscreenButton.addEventListener("click", async () => {
        if (!document.fullscreenElement) {
            await document.documentElement.requestFullscreen();
            elements.fullscreenButton.textContent = "Exit Full Screen";
        } else {
            await document.exitFullscreen();
            elements.fullscreenButton.textContent = "Full Screen";
        }
    });

    document.addEventListener("fullscreenchange", () => {
        elements.fullscreenButton.textContent = document.fullscreenElement ? "Exit Full Screen" : "Full Screen";
    });
}

bindFilterEvents();
bindButtons();
initializeDashboard();
