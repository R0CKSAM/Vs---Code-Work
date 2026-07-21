(function () {
  const source = window.__DASHBOARD_DATA__ || { datasets: {} };
  const datasetKeys = Object.keys(source.datasets || {});
  const state = {
    activeDataset: datasetKeys[0] || "distribution",
    filters: {
      week: "",
      market: "",
      channel: "",
      search: "",
    },
    page: 1,
    pageSize: 50,
  };

  const tabsEl = document.getElementById("datasetTabs");
  const weekFilterEl = document.getElementById("weekFilter");
  const marketFilterEl = document.getElementById("marketFilter");
  const channelFilterEl = document.getElementById("channelFilter");
  const searchInputEl = document.getElementById("searchInput");
  const rowsKpiEl = document.getElementById("rowsKpi");
  const marketsKpiEl = document.getElementById("marketsKpi");
  const channelsKpiEl = document.getElementById("channelsKpi");
  const latestWeekKpiEl = document.getElementById("latestWeekKpi");
  const activeDatasetLabelEl = document.getElementById("activeDatasetLabel");
  const tableTitleEl = document.getElementById("tableTitle");
  const tableCountEl = document.getElementById("tableCount");
  const pageLabelEl = document.getElementById("pageLabel");
  const tableHeadEl = document.getElementById("tableHead");
  const tableBodyEl = document.getElementById("tableBody");

  function getDataset() {
    return source.datasets[state.activeDataset] || { columns: [], records: [], metrics: {} };
  }

  function channelKeyForDataset(dataset) {
    const columnKeys = dataset.columns.map((column) => column.key);
    if (columnKeys.includes("Channel")) return "Channel";
    if (columnKeys.includes("Channel Name")) return "Channel Name";
    return "";
  }

  function marketKeyForDataset(dataset) {
    return dataset.columns.some((column) => column.key === "Market") ? "Market" : "";
  }

  function createOption(value, label) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    return option;
  }

  function sortWeekLabels(values) {
    return [...values].sort((left, right) => {
      const leftMatch = /Wk-(\d{1,2})'(\d{2})/i.exec(String(left));
      const rightMatch = /Wk-(\d{1,2})'(\d{2})/i.exec(String(right));
      if (!leftMatch || !rightMatch) return String(left).localeCompare(String(right));
      const leftYear = Number(`20${leftMatch[2]}`);
      const rightYear = Number(`20${rightMatch[2]}`);
      if (leftYear !== rightYear) return leftYear - rightYear;
      return Number(leftMatch[1]) - Number(rightMatch[1]);
    });
  }

  function uniqueValues(records, key) {
    if (!key) return [];
    const values = new Set();
    records.forEach((record) => {
      const value = record[key];
      if (value !== null && value !== undefined && String(value).trim() !== "") {
        values.add(String(value));
      }
    });
    return key === "Week" ? sortWeekLabels(values) : [...values].sort((left, right) => left.localeCompare(right));
  }

  function populateFilters(dataset) {
    const marketKey = marketKeyForDataset(dataset);
    const channelKey = channelKeyForDataset(dataset);

    weekFilterEl.innerHTML = "";
    marketFilterEl.innerHTML = "";
    channelFilterEl.innerHTML = "";

    weekFilterEl.appendChild(createOption("", "All Weeks"));
    marketFilterEl.appendChild(createOption("", "All Markets"));
    channelFilterEl.appendChild(createOption("", "All Channels"));

    uniqueValues(dataset.records, "Week").forEach((value) => weekFilterEl.appendChild(createOption(value, value)));
    uniqueValues(dataset.records, marketKey).forEach((value) => marketFilterEl.appendChild(createOption(value, value)));
    uniqueValues(dataset.records, channelKey).forEach((value) => channelFilterEl.appendChild(createOption(value, value)));

    weekFilterEl.value = state.filters.week;
    marketFilterEl.value = state.filters.market;
    channelFilterEl.value = state.filters.channel;
    searchInputEl.value = state.filters.search;
  }

  function filterRecords(dataset) {
    const marketKey = marketKeyForDataset(dataset);
    const channelKey = channelKeyForDataset(dataset);
    const query = state.filters.search.trim().toLowerCase();

    return dataset.records.filter((record) => {
      if (state.filters.week && String(record.Week || "") !== state.filters.week) return false;
      if (state.filters.market && String(record[marketKey] || "") !== state.filters.market) return false;
      if (state.filters.channel && String(record[channelKey] || "") !== state.filters.channel) return false;
      if (!query) return true;
      return dataset.columns.some((column) => {
        const value = record[column.key];
        return value !== null && value !== undefined && String(value).toLowerCase().includes(query);
      });
    });
  }

  function updateKpis(dataset, filteredRecords) {
    const marketKey = marketKeyForDataset(dataset);
    const channelKey = channelKeyForDataset(dataset);
    const marketCount = new Set(filteredRecords.map((record) => String(record[marketKey] || "")).filter(Boolean)).size;
    const channelCount = new Set(filteredRecords.map((record) => String(record[channelKey] || "")).filter(Boolean)).size;
    rowsKpiEl.textContent = filteredRecords.length.toLocaleString("en-IN");
    marketsKpiEl.textContent = marketCount.toLocaleString("en-IN");
    channelsKpiEl.textContent = channelCount.toLocaleString("en-IN");
    latestWeekKpiEl.textContent = dataset.metrics.latest_week || "-";
  }

  function renderTable(dataset, filteredRecords) {
    const totalPages = Math.max(1, Math.ceil(filteredRecords.length / state.pageSize));
    if (state.page > totalPages) state.page = totalPages;
    const startIndex = (state.page - 1) * state.pageSize;
    const pageRecords = filteredRecords.slice(startIndex, startIndex + state.pageSize);

    tableHeadEl.innerHTML = "";
    tableBodyEl.innerHTML = "";

    const headerRow = document.createElement("tr");
    dataset.columns.forEach((column) => {
      const th = document.createElement("th");
      th.textContent = column.label;
      headerRow.appendChild(th);
    });
    tableHeadEl.appendChild(headerRow);

    if (!pageRecords.length) {
      const row = document.createElement("tr");
      const cell = document.createElement("td");
      cell.colSpan = Math.max(1, dataset.columns.length);
      cell.className = "empty-row";
      cell.textContent = "No rows match the current filters.";
      row.appendChild(cell);
      tableBodyEl.appendChild(row);
    } else {
      pageRecords.forEach((record) => {
        const row = document.createElement("tr");
        dataset.columns.forEach((column) => {
          const cell = document.createElement("td");
          const value = record[column.key];
          cell.textContent = value === null || value === undefined ? "" : String(value);
          row.appendChild(cell);
        });
        tableBodyEl.appendChild(row);
      });
    }

    tableCountEl.textContent = `${filteredRecords.length.toLocaleString("en-IN")} rows`;
    pageLabelEl.textContent = `Page ${state.page} of ${totalPages}`;
  }

  function groupCounts(records, key) {
    const counts = new Map();
    records.forEach((record) => {
      const value = String(record[key] || "").trim();
      if (!value) return;
      counts.set(value, (counts.get(value) || 0) + 1);
    });
    return [...counts.entries()].sort((left, right) => right[1] - left[1]);
  }

  function groupAverage(records, groupKey, valueKey) {
    const totals = new Map();
    records.forEach((record) => {
      const group = String(record[groupKey] || "").trim();
      const value = Number(record[valueKey]);
      if (!group || Number.isNaN(value)) return;
      const current = totals.get(group) || { sum: 0, count: 0 };
      current.sum += value;
      current.count += 1;
      totals.set(group, current);
    });
    return [...totals.entries()]
      .map(([group, stats]) => [group, Number((stats.sum / stats.count).toFixed(2))])
      .sort((left, right) => right[1] - left[1]);
  }

  function renderCharts(dataset, filteredRecords) {
    const weekCounts = groupCounts(filteredRecords, "Week");
    Plotly.newPlot("weekChart", [{
      type: "bar",
      x: weekCounts.map((item) => item[0]),
      y: weekCounts.map((item) => item[1]),
      marker: { color: "#b6542e" },
      hovertemplate: "%{x}<br>Rows: %{y}<extra></extra>",
    }], {
      margin: { t: 12, r: 12, b: 52, l: 52 },
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      xaxis: { title: "Week" },
      yaxis: { title: "Rows" },
    }, { responsive: true, displayModeBar: false });

    const marketKey = marketKeyForDataset(dataset);
    const channelKey = channelKeyForDataset(dataset);
    const topItems = state.activeDataset === "ots"
      ? groupAverage(filteredRecords, marketKey, "OTS").slice(0, 10)
      : groupCounts(filteredRecords, marketKey).slice(0, 10);
    const chartTitle = state.activeDataset === "ots" ? "Average OTS by Market" : "Rows by Market";

    Plotly.newPlot("marketChart", [{
      type: "bar",
      orientation: "h",
      x: topItems.map((item) => item[1]).reverse(),
      y: topItems.map((item) => item[0]).reverse(),
      marker: { color: "#7a2d12" },
      hovertemplate: state.activeDataset === "ots"
        ? "%{y}<br>Average OTS: %{x}<extra></extra>"
        : "%{y}<br>Rows: %{x}<extra></extra>",
    }], {
      title: { text: chartTitle, font: { size: 14 } },
      margin: { t: 40, r: 12, b: 40, l: 120 },
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      xaxis: { title: state.activeDataset === "ots" ? "Average OTS" : "Rows" },
      yaxis: { automargin: true },
    }, { responsive: true, displayModeBar: false });

    if (channelKey) {
      const selectedChannel = state.filters.channel || "";
      if (selectedChannel && state.activeDataset === "ots") {
        const trendMap = new Map();
        filteredRecords
          .filter((record) => String(record[channelKey] || "") === selectedChannel)
          .forEach((record) => {
            const week = String(record.Week || "");
            const value = Number(record.OTS);
            if (!week || Number.isNaN(value)) return;
            const current = trendMap.get(week) || { sum: 0, count: 0 };
            current.sum += value;
            current.count += 1;
            trendMap.set(week, current);
          });
        const trendEntries = sortWeekLabels(trendMap.keys()).map((week) => {
          const stats = trendMap.get(week);
          return [week, Number((stats.sum / stats.count).toFixed(2))];
        });
        Plotly.addTraces("weekChart", {
          type: "scatter",
          mode: "lines+markers",
          x: trendEntries.map((item) => item[0]),
          y: trendEntries.map((item) => item[1]),
          name: `${selectedChannel} Avg OTS`,
          line: { color: "#1f3c88", width: 3 },
          yaxis: "y2",
          hovertemplate: "%{x}<br>Avg OTS: %{y}<extra></extra>",
        });
        Plotly.relayout("weekChart", {
          yaxis2: { overlaying: "y", side: "right", title: "Avg OTS" },
          legend: { orientation: "h" },
        });
      }
    }
  }

  function buildSpreadsheetXml(dataset, records) {
    const escape = (value) => String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/\"/g, "&quot;");
    const headerCells = dataset.columns.map((column) => `<Cell><Data ss:Type="String">${escape(column.label)}</Data></Cell>`).join("");
    const rows = records.map((record) => {
      const cells = dataset.columns.map((column) => {
        const value = record[column.key];
        const isNumber = column.type === "number" && value !== null && value !== undefined && value !== "";
        const type = isNumber ? "Number" : "String";
        return `<Cell><Data ss:Type="${type}">${escape(value)}</Data></Cell>`;
      }).join("");
      return `<Row>${cells}</Row>`;
    }).join("");
    return `<?xml version="1.0"?>
      <?mso-application progid="Excel.Sheet"?>
      <Workbook xmlns="urn:schemas-microsoft-com:office:spreadsheet"
        xmlns:o="urn:schemas-microsoft-com:office:office"
        xmlns:x="urn:schemas-microsoft-com:office:excel"
        xmlns:ss="urn:schemas-microsoft-com:office:spreadsheet">
        <Worksheet ss:Name="${dataset.name}">
          <Table>
            <Row>${headerCells}</Row>
            ${rows}
          </Table>
        </Worksheet>
      </Workbook>`;
  }

  function exportFilteredTable() {
    const dataset = getDataset();
    const records = filterRecords(dataset);
    const xml = buildSpreadsheetXml(dataset, records);
    const blob = new Blob([xml], { type: "application/vnd.ms-excel" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${state.activeDataset}_filtered.xls`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
  }

  function renderTabs() {
    tabsEl.innerHTML = "";
    datasetKeys.forEach((datasetKey) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = `tab-button${datasetKey === state.activeDataset ? " active" : ""}`;
      button.textContent = source.datasets[datasetKey].name;
      button.addEventListener("click", () => {
        state.activeDataset = datasetKey;
        state.filters = { week: "", market: "", channel: "", search: "" };
        state.page = 1;
        render();
      });
      tabsEl.appendChild(button);
    });
  }

  function render() {
    const dataset = getDataset();
    const filteredRecords = filterRecords(dataset);
    activeDatasetLabelEl.textContent = dataset.name;
    tableTitleEl.textContent = dataset.name;
    populateFilters(dataset);
    updateKpis(dataset, filteredRecords);
    renderTable(dataset, filteredRecords);
    renderCharts(dataset, filteredRecords);
    renderTabs();
  }

  weekFilterEl.addEventListener("change", () => {
    state.filters.week = weekFilterEl.value;
    state.page = 1;
    render();
  });

  marketFilterEl.addEventListener("change", () => {
    state.filters.market = marketFilterEl.value;
    state.page = 1;
    render();
  });

  channelFilterEl.addEventListener("change", () => {
    state.filters.channel = channelFilterEl.value;
    state.page = 1;
    render();
  });

  searchInputEl.addEventListener("input", () => {
    state.filters.search = searchInputEl.value;
    state.page = 1;
    render();
  });

  document.getElementById("resetButton").addEventListener("click", () => {
    state.filters = { week: "", market: "", channel: "", search: "" };
    state.page = 1;
    render();
  });

  document.getElementById("exportButton").addEventListener("click", exportFilteredTable);
  document.getElementById("prevButton").addEventListener("click", () => {
    if (state.page > 1) {
      state.page -= 1;
      render();
    }
  });
  document.getElementById("nextButton").addEventListener("click", () => {
    const dataset = getDataset();
    const totalPages = Math.max(1, Math.ceil(filterRecords(dataset).length / state.pageSize));
    if (state.page < totalPages) {
      state.page += 1;
      render();
    }
  });

  render();
})();
