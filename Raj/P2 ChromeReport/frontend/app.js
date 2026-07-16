const api = axios.create({
    baseURL: "http://127.0.0.1:8000",
    timeout: 60000,
});

const filterKeys = [
    "Transmission",
    "Market",
    "MSO",
    "City",
    "MSO Type",
    "Head End",
    "Channel Name",
    "TV Channel No",
    "CR No",
    "Band",
    "Changed State",
    "Week",
];

const rowFilterKeys = [
    "Transmission",
    "Market",
    "MSO",
    "City",
    "MSO Type",
    "Head End",
    "Channel Name",
    "TV Channel No",
    "CR No",
    "Band",
    "Changed State",
];

const state = {
    metadata: null,
    metadataPromise: null,
    activeFilters: createEmptyFilters(),
    pendingFilters: createEmptyFilters(),
    gridApi: null,
    sortModel: [],
    weekColumns: [],
    weekLabels: {},
    openDropdownKey: null,
    currentView: "frequency",
};

const elements = {
    summaryWeeks: document.getElementById("summaryWeeks"),
    summaryChannels: document.getElementById("summaryChannels"),
    summaryMarkets: document.getElementById("summaryMarkets"),
    sourceFilesBadge: document.getElementById("sourceFilesBadge"),
    lastRefreshBadge: document.getElementById("lastRefreshBadge"),
    totalRecords: document.getElementById("toolbarTotalRecords"),
    gridStatus: document.getElementById("gridStatus"),
    filterPanel: document.getElementById("filterPanel"),
    applyFiltersButton: document.getElementById("applyFiltersButton"),
    resetFiltersButton: document.getElementById("resetFiltersButton"),
    clearFiltersButton: document.getElementById("clearFiltersButton"),
    refreshDataButton: document.getElementById("refreshDataButton"),
    exportCsvButton: document.getElementById("exportCsvButton"),
    exportExcelButton: document.getElementById("exportExcelButton"),
    fullscreenButton: document.getElementById("fullscreenButton"),
    fullscreenPanel: document.getElementById("fullscreenPanel"),
    tableTitle: document.getElementById("tableTitle"),
    frequencyViewButton: document.getElementById("frequencyViewButton"),
    rankViewButton: document.getElementById("rankViewButton"),
    bandViewButton: document.getElementById("bandViewButton"),
};

function createEmptyFilters() {
    return Object.fromEntries(filterKeys.map((key) => [key, []]));
}

function activeFilterPayload() {
    return Object.fromEntries(
        Object.entries(state.activeFilters).filter(([key, values]) => rowFilterKeys.includes(key) && values.length)
    );
}

function queryParams(page, pageSize) {
    return {
        page,
        page_size: pageSize,
        filters: JSON.stringify(activeFilterPayload()),
        sort_model: JSON.stringify(state.sortModel),
        search: "",
        mode: state.currentView,
    };
}

function escapeHtml(value) {
    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
}

function slugify(value) {
    return String(value).toLowerCase().replace(/[^a-z0-9]+/g, "-");
}

function cssEscape(value) {
    return window.CSS && window.CSS.escape ? window.CSS.escape(value) : value.replace(/"/g, '\\"');
}

function weekLabel(columnKey) {
    return state.weekLabels?.[columnKey] || state.metadata?.week_labels?.[columnKey] || columnKey;
}

function selectedCount(key) {
    return state.pendingFilters[key]?.length ?? 0;
}

function selectionSummary(key) {
    const values = state.pendingFilters[key] ?? [];
    if (!values.length) {
        return key === "Week" ? "All Weeks" : "All";
    }
    if (values.length === 1) {
        return values[0];
    }
    return `${values[0]} +${values.length - 1}`;
}

function filterOptionsMap() {
    return {
        "Transmission": state.metadata?.transmissions ?? [],
        "Market": state.metadata?.markets ?? [],
        "MSO": state.metadata?.msos ?? [],
        "City": state.metadata?.cities ?? [],
        "MSO Type": state.metadata?.mso_types ?? [],
        "Head End": state.metadata?.head_ends ?? [],
        "Channel Name": state.metadata?.channel_names ?? [],
        "TV Channel No": state.metadata?.tv_channel_numbers ?? [],
        "CR No": state.metadata?.cr_numbers ?? [],
        "Band": state.metadata?.bands ?? [],
        "Changed State": state.metadata?.status_options ?? ["Changed", "Unchanged"],
        "Week": (state.metadata?.weeks ?? []).map((key) => weekLabel(key)),
    };
}

function buildFilterDropdown(id, values) {
    const selectedValues = state.pendingFilters[id] ?? [];
    const isOpen = state.openDropdownKey === id;
    return `
        <div class="col-xxl-2 col-xl-3 col-lg-4 col-md-6 filter-dropdown-wrap ${isOpen ? "is-open" : ""}" data-dropdown="${id}">
            <button class="filter-trigger ${isOpen ? "is-open" : ""}" type="button" data-dropdown-trigger="${id}">
                <span class="filter-trigger-labels">
                    <span class="filter-name">${escapeHtml(id)}</span>
                    <span class="filter-value" id="value-${id}">${escapeHtml(selectionSummary(id))}</span>
                </span>
                <span class="filter-trigger-meta">
                    <span class="filter-count-badge" id="count-${id}">${selectedValues.length}</span>
                    <span>▼</span>
                </span>
            </button>
            <div class="filter-menu" data-dropdown-menu="${id}">
                <input class="form-control form-control-sm filter-search" data-search="${id}" type="search" placeholder="Search ${escapeHtml(id)}">
                <div class="filter-menu-actions">
                    <button class="btn btn-outline-secondary btn-sm" data-select-all="${id}" type="button">Select All</button>
                    <button class="btn btn-outline-secondary btn-sm" data-clear="${id}" type="button">Clear</button>
                </div>
                <div class="filter-option-list">
                    ${values.map((value) => `
                        <div class="form-check">
                            <input class="form-check-input" data-filter="${id}" type="checkbox" value="${escapeHtml(value)}" id="${id}-${slugify(value)}" ${selectedValues.includes(String(value)) ? "checked" : ""}>
                            <label class="form-check-label" for="${id}-${slugify(value)}">${escapeHtml(value)}</label>
                        </div>
                    `).join("")}
                    <div class="filter-option-empty" id="empty-${id}" hidden>No matching values</div>
                </div>
            </div>
        </div>
    `;
}

function renderFilterSkeleton() {
    elements.filterPanel.innerHTML = `
        <div class="col-12">
            <div class="grid-status">
                <span class="status-spinner"></span>
                <span>Loading filter values...</span>
            </div>
        </div>
    `;
}

function renderFilters() {
    if (!state.metadata) {
        renderFilterSkeleton();
        return;
    }
    const options = filterOptionsMap();
    elements.filterPanel.innerHTML = filterKeys.map((key) => buildFilterDropdown(key, options[key] ?? [])).join("");
    bindFilterEvents();
}

function updateFilterVisual(key) {
    const badge = document.getElementById(`count-${key}`);
    const value = document.getElementById(`value-${key}`);
    if (badge) {
        badge.textContent = String(selectedCount(key));
    }
    if (value) {
        value.textContent = selectionSummary(key);
    }
}

function closeAllDropdowns() {
    state.openDropdownKey = null;
    elements.filterPanel.querySelectorAll("[data-dropdown]").forEach((node) => node.classList.remove("is-open"));
    elements.filterPanel.querySelectorAll("[data-dropdown-trigger]").forEach((node) => node.classList.remove("is-open"));
}

function openDropdown(key) {
    closeAllDropdowns();
    state.openDropdownKey = key;
    elements.filterPanel.querySelector(`[data-dropdown="${cssEscape(key)}"]`)?.classList.add("is-open");
    elements.filterPanel.querySelector(`[data-dropdown-trigger="${cssEscape(key)}"]`)?.classList.add("is-open");
}

function syncCheckboxes(key) {
    const selected = new Set(state.pendingFilters[key] ?? []);
    elements.filterPanel.querySelectorAll(`[data-filter="${cssEscape(key)}"]`).forEach((checkbox) => {
        checkbox.checked = selected.has(checkbox.value);
    });
    updateFilterVisual(key);
}

function bindFilterEvents() {
    elements.filterPanel.querySelectorAll("[data-dropdown-trigger]").forEach((button) => {
        button.addEventListener("click", (event) => {
            event.stopPropagation();
            const key = button.dataset.dropdownTrigger;
            if (state.openDropdownKey === key) {
                closeAllDropdowns();
            } else {
                openDropdown(key);
            }
        });
    });

    elements.filterPanel.querySelectorAll("[data-dropdown-menu]").forEach((menu) => {
        menu.addEventListener("click", (event) => event.stopPropagation());
    });

    elements.filterPanel.querySelectorAll("[data-search]").forEach((input) => {
        input.addEventListener("input", (event) => {
            const key = event.target.dataset.search;
            const query = event.target.value.trim().toLowerCase();
            let visible = 0;
            elements.filterPanel.querySelectorAll(`[data-filter="${cssEscape(key)}"]`).forEach((checkbox) => {
                const text = checkbox.nextElementSibling.textContent.toLowerCase();
                const show = text.includes(query);
                checkbox.closest(".form-check").hidden = !show;
                if (show) {
                    visible += 1;
                }
            });
            const empty = document.getElementById(`empty-${key}`);
            if (empty) {
                empty.hidden = visible !== 0;
            }
        });
    });

    elements.filterPanel.querySelectorAll("[data-select-all]").forEach((button) => {
        button.addEventListener("click", () => {
            const key = button.dataset.selectAll;
            state.pendingFilters[key] = [...(filterOptionsMap()[key] ?? [])];
            syncCheckboxes(key);
        });
    });

    elements.filterPanel.querySelectorAll("[data-clear]").forEach((button) => {
        button.addEventListener("click", () => {
            const key = button.dataset.clear;
            state.pendingFilters[key] = [];
            syncCheckboxes(key);
        });
    });

    elements.filterPanel.querySelectorAll("[data-filter]").forEach((checkbox) => {
        checkbox.addEventListener("change", (event) => {
            const key = event.target.dataset.filter;
            state.pendingFilters[key] = [...elements.filterPanel.querySelectorAll(`[data-filter="${cssEscape(key)}"]:checked`)].map((item) => item.value);
            updateFilterVisual(key);
        });
    });
}

function normalizeNumeric(value) {
    if (value === null || value === undefined || value === "" || value === "NA" || value === "Multiple") {
        return null;
    }
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
}

function renderWeekCell(value, previousValue) {
    let cssClass = "same";
    let prefix = "";
    if (state.currentView === "band") {
        const currentText = String(value ?? "").trim();
        const previousText = String(previousValue ?? "").trim();
        if (currentText && previousText && currentText !== previousText) {
            cssClass = "increase";
            prefix = "▲ ";
        }
    } else {
        const current = normalizeNumeric(value);
        const previous = normalizeNumeric(previousValue);
        if (current !== null && previous !== null) {
            if (state.currentView === "rank") {
                if (current < previous) {
                    cssClass = "decrease";
                    prefix = "▲ ";
                } else if (current > previous) {
                    cssClass = "increase";
                    prefix = "▼ ";
                }
            } else if (current > previous) {
                cssClass = "increase";
                prefix = "▲ ";
            } else if (current < previous) {
                cssClass = "decrease";
                prefix = "▼ ";
            }
        }
    }
    const displayValue = value === null || value === undefined || value === "" ? "NA" : value;
    return `<span class="week-cell ${cssClass}">${prefix}${displayValue}</span>`;
}

function renderStatusCell(value) {
    const normalized = String(value || "→ No Change");
    const cssClass = normalized.startsWith("↑") ? "increase" : normalized.startsWith("↓") ? "decrease" : "same";
    return `<span class="status-pill ${cssClass}">${escapeHtml(normalized)}</span>`;
}

function renderTextCell(value) {
    const normalized = String(value ?? "").trim();
    return escapeHtml(normalized || "--");
}

function createWeekColumn(columnKey, previousColumnKey) {
    return {
        headerName: weekLabel(columnKey),
        field: columnKey,
        minWidth: 105,
        width: 105,
        sortable: true,
        filter: false,
        suppressMenu: true,
        suppressHeaderMenuButton: true,
        cellRenderer: (params) => renderWeekCell(params.value, previousColumnKey ? params.data?.[previousColumnKey] : null),
    };
}

function getVisibleWeekKeys() {
    if (state.activeFilters.Week.length) {
        return state.weekColumns.filter((field) => state.activeFilters.Week.includes(weekLabel(field)));
    }
    return state.weekColumns;
}

function buildColumnDefs() {
    const visibleWeeks = getVisibleWeekKeys();
    const pinned = [
        { headerName: "Market", field: "Market", pinned: "left", minWidth: 190, width: 190, sortable: true, filter: false, suppressMenu: true, suppressHeaderMenuButton: true, cellRenderer: (params) => renderTextCell(params.value) },
        { headerName: "MSO", field: "MSO", pinned: "left", minWidth: 130, width: 130, sortable: true, filter: false, suppressMenu: true, suppressHeaderMenuButton: true, cellRenderer: (params) => renderTextCell(params.value) },
        { headerName: "City", field: "City", pinned: "left", minWidth: 105, width: 105, sortable: true, filter: false, suppressMenu: true, suppressHeaderMenuButton: true, cellRenderer: (params) => renderTextCell(params.value) },
        { headerName: "Head End", field: "Head End", pinned: "left", minWidth: 148, width: 148, sortable: true, filter: false, suppressMenu: true, suppressHeaderMenuButton: true, cellRenderer: (params) => renderTextCell(params.value) },
        { headerName: "Channel Name", field: "Channel Name", pinned: "left", minWidth: 148, width: 148, sortable: true, filter: false, suppressMenu: true, suppressHeaderMenuButton: true, cellRenderer: (params) => renderTextCell(params.value) },
        { headerName: "CR No", field: "CR No", pinned: "left", minWidth: 92, width: 92, sortable: true, filter: false, suppressMenu: true, suppressHeaderMenuButton: true, cellRenderer: (params) => renderTextCell(params.value) },
    ];
    const weeks = visibleWeeks.map((key, index) => createWeekColumn(key, index > 0 ? visibleWeeks[index - 1] : null));
    return [
        ...pinned,
        ...weeks,
        { headerName: "Status", field: state.currentView === "frequency" ? "Frequency Status" : state.currentView === "rank" ? "Rank Status" : "Band Status", minWidth: 126, width: 126, sortable: true, filter: false, suppressMenu: true, suppressHeaderMenuButton: true, cellRenderer: (params) => renderStatusCell(params.value) },
    ];
}

function rebuildGridColumns() {
    if (!state.gridApi) {
        return;
    }
    state.gridApi.setGridOption("columnDefs", buildColumnDefs());
}

function setGridStatus(message, loading = false) {
    elements.gridStatus.innerHTML = loading
        ? `<span class="status-spinner"></span><span>${escapeHtml(message)}</span>`
        : escapeHtml(message);
}

function updateHeaderAndKpis(totalRows = 0) {
    elements.totalRecords.textContent = totalRows.toLocaleString();
    elements.summaryWeeks.textContent = String(state.metadata?.totals?.weeks ?? 0);
    elements.summaryChannels.textContent = Number(state.metadata?.totals?.channels ?? 0).toLocaleString();
    elements.summaryMarkets.textContent = Number(state.metadata?.totals?.markets ?? 0).toLocaleString();
}

function updateExportLinks() {
    const params = new URLSearchParams(queryParams(1, 1000));
    elements.exportCsvButton.href = `${api.defaults.baseURL}/export/csv?${params.toString()}`;
    elements.exportExcelButton.href = `${api.defaults.baseURL}/export/excel?${params.toString()}`;
}

function updateViewUi() {
    const titles = {
        frequency: "Frequency Distribution",
        rank: "Rank Distribution",
        band: "Band Distribution",
    };
    elements.tableTitle.textContent = titles[state.currentView];
    const buttonMap = {
        frequency: elements.frequencyViewButton,
        rank: elements.rankViewButton,
        band: elements.bandViewButton,
    };
    Object.entries(buttonMap).forEach(([view, button]) => {
        if (view === state.currentView) {
            button.classList.remove("btn-outline-primary");
            button.classList.add("btn-primary");
        } else {
            button.classList.remove("btn-primary");
            button.classList.add("btn-outline-primary");
        }
    });
}

function createDatasource() {
    return {
        getRows: async (params) => {
            const startRow = params.startRow || 0;
            const endRow = params.endRow || 100;
            const pageSize = Math.max(endRow - startRow, 1);
            const page = Math.floor(startRow / pageSize) + 1;
            state.sortModel = params.sortModel || [];
            updateExportLinks();
            setGridStatus("Loading data...", true);
            state.gridApi?.showLoadingOverlay();
            try {
                const response = await api.get("/data", { params: queryParams(page, pageSize) });
                const payload = response.data;
                state.weekColumns = payload.week_columns || [];
                state.weekLabels = payload.week_labels || {};
                rebuildGridColumns();
                updateHeaderAndKpis(payload.total_rows);
                setGridStatus(`${payload.total_rows.toLocaleString()} records available`);
                params.successCallback(payload.rows, payload.total_rows);
                if (payload.total_rows === 0) {
                    state.gridApi?.showNoRowsOverlay();
                } else {
                    state.gridApi?.hideOverlay();
                }
            } catch (error) {
                console.error(error);
                setGridStatus("Failed to load data");
                state.gridApi?.showNoRowsOverlay();
                params.failCallback();
            }
        },
    };
}

function reloadGrid() {
    if (!state.gridApi) {
        return;
    }
    updateExportLinks();
    state.gridApi.setGridOption("datasource", createDatasource());
}

function applyFilters() {
    state.activeFilters = Object.fromEntries(Object.entries(state.pendingFilters).map(([key, values]) => [key, [...values]]));
    closeAllDropdowns();
    rebuildGridColumns();
    reloadGrid();
}

function clearAllFilters(reload = false) {
    state.pendingFilters = createEmptyFilters();
    state.activeFilters = createEmptyFilters();
    closeAllDropdowns();
    renderFilters();
    if (reload) {
        rebuildGridColumns();
        reloadGrid();
    }
}

async function loadMetadata(force = false) {
    if (state.metadata && !force) {
        renderFilters();
        updateHeaderAndKpis(state.metadata.totals?.records ?? 0);
        return state.metadata;
    }
    if (state.metadataPromise && !force) {
        return state.metadataPromise;
    }
    renderFilterSkeleton();
    state.metadataPromise = api.get("/metadata")
        .then((response) => {
            state.metadata = response.data;
            state.weekColumns = state.metadata.weeks || [];
            state.weekLabels = state.metadata.week_labels || {};
            elements.sourceFilesBadge.textContent = (state.metadata.source_files || []).join(" | ") || "No files";
            elements.lastRefreshBadge.textContent = new Date().toLocaleString();
            updateHeaderAndKpis(state.metadata.totals?.records ?? 0);
            renderFilters();
            updateViewUi();
            rebuildGridColumns();
            return state.metadata;
        })
        .catch((error) => {
            console.error(error);
            elements.sourceFilesBadge.textContent = "Metadata unavailable";
            throw error;
        })
        .finally(() => {
            state.metadataPromise = null;
        });
    return state.metadataPromise;
}

function buildGrid() {
    const gridOptions = {
        columnDefs: buildColumnDefs(),
        defaultColDef: {
            resizable: true,
            sortable: true,
            filter: false,
            floatingFilter: false,
            suppressMenu: true,
            suppressHeaderMenuButton: true,
        },
        rowModelType: "infinite",
        cacheBlockSize: 100,
        maxBlocksInCache: 10,
        blockLoadDebounceMillis: 40,
        pagination: true,
        paginationPageSize: 100,
        paginationPageSizeSelector: [100, 250, 500],
        rowSelection: "multiple",
        animateRows: false,
        suppressCellFocus: true,
        rowBuffer: 0,
        overlayLoadingTemplate: '<span class="ag-overlay-loading-center">Loading data...</span>',
        overlayNoRowsTemplate: '<span class="ag-overlay-loading-center">No matching records found.</span>',
        onGridReady: (event) => {
            state.gridApi = event.api;
            event.api.setGridOption("datasource", createDatasource());
        },
    };
    agGrid.createGrid(document.getElementById("frequencyGrid"), gridOptions);
}

async function refreshDataset() {
    setGridStatus("Refreshing dataset...", true);
    await api.post("/refresh");
    state.metadata = null;
    state.metadataPromise = null;
    await loadMetadata(true);
    reloadGrid();
}

async function toggleFullscreen() {
    if (document.fullscreenElement === elements.fullscreenPanel) {
        await document.exitFullscreen();
    } else {
        await elements.fullscreenPanel.requestFullscreen();
    }
}

function bindEvents() {
    elements.applyFiltersButton.addEventListener("click", applyFilters);
    elements.resetFiltersButton.addEventListener("click", () => clearAllFilters(true));
    elements.clearFiltersButton.addEventListener("click", () => clearAllFilters(true));
    elements.refreshDataButton.addEventListener("click", async () => {
        try {
            await refreshDataset();
        } catch (error) {
            console.error(error);
            setGridStatus("Refresh failed");
        }
    });
    elements.fullscreenButton.addEventListener("click", async () => {
        try {
            await toggleFullscreen();
        } catch (error) {
            console.error(error);
        }
    });
    elements.frequencyViewButton.addEventListener("click", () => {
        state.currentView = "frequency";
        updateViewUi();
        rebuildGridColumns();
        reloadGrid();
    });
    elements.rankViewButton.addEventListener("click", () => {
        state.currentView = "rank";
        updateViewUi();
        rebuildGridColumns();
        reloadGrid();
    });
    elements.bandViewButton.addEventListener("click", () => {
        state.currentView = "band";
        updateViewUi();
        rebuildGridColumns();
        reloadGrid();
    });
    document.addEventListener("fullscreenchange", () => {
        elements.fullscreenButton.textContent = document.fullscreenElement === elements.fullscreenPanel ? "Exit Full Screen" : "Full Screen";
    });
    document.addEventListener("click", (event) => {
        if (!event.target.closest("#filterPanel")) {
            closeAllDropdowns();
        }
    });
    document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") {
            closeAllDropdowns();
        }
    });
}

async function initialize() {
    bindEvents();
    renderFilterSkeleton();
    updateViewUi();
    buildGrid();
    updateExportLinks();
    loadMetadata().catch(() => undefined);
}

initialize().catch((error) => {
    console.error(error);
    setGridStatus("Unable to initialize dashboard");
});
