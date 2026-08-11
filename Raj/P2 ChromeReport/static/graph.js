(function() {
  const state = {
    view: 'table', // 'table' or 'graph'
    chartInstance: null,
    isEchartsLoaded: false,
    loading: false
  };

  const DEFAULT_CHANNELS = ["India TV", "Aaj Tak", "News18 India", "Republic Bharat"];
  const CHANNEL_COLORS = {
    "india tv": "#2f67ea",
    "aaj tak": "#ef4444",
    "news18 india": "#10b981",
    "republic bharat": "#f97316"
  };

  function getRandomColor() {
    const letters = '0123456789ABCDEF';
    let color = '#';
    for (let i = 0; i < 6; i++) {
      color += letters[Math.floor(Math.random() * 16)];
    }
    return color;
  }

  function getChannelColor(channelName) {
    const lower = String(channelName || "").trim().toLowerCase();
    return CHANNEL_COLORS[lower] || getRandomColor();
  }

  function normalizeText(txt) {
    return String(txt || "").trim();
  }

  function loadEcharts() {
    return new Promise((resolve, reject) => {
      if (window.echarts) {
        state.isEchartsLoaded = true;
        resolve();
        return;
      }
      if (document.getElementById('echarts-script')) {
        // already loading
        const script = document.getElementById('echarts-script');
        script.addEventListener('load', resolve);
        script.addEventListener('error', reject);
        return;
      }
      const script = document.createElement('script');
      script.id = 'echarts-script';
      script.src = 'https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js';
      script.async = true;
      script.onload = () => {
        state.isEchartsLoaded = true;
        resolve();
      };
      script.onerror = reject;
      document.head.appendChild(script);
    });
  }

  function parseTableData() {
    const tableHead = document.getElementById("otsTableHead");
    const tableBody = document.getElementById("otsTableBody");
    if (!tableHead || !tableBody) return { weeks: [], records: [] };

    const headTr = tableHead.querySelector("tr");
    if (!headTr) return { weeks: [], records: [] };

    const ths = Array.from(headTr.querySelectorAll("th"));
    // First two columns are typically Market, Channel. Then weeks, then Change.
    // Let's dynamically find weeks.
    const weeks = [];
    const weekIndices = [];
    ths.forEach((th, idx) => {
      const text = normalizeText(th.textContent);
      if (text.toLowerCase().startsWith("wk-")) {
        weeks.push(text);
        weekIndices.push(idx);
      }
    });

    const marketIdx = ths.findIndex(th => normalizeText(th.textContent).toLowerCase() === 'market');
    const channelIdx = ths.findIndex(th => normalizeText(th.textContent).toLowerCase() === 'channel');

    if (marketIdx === -1 || channelIdx === -1 || weeks.length === 0) {
      return { weeks: [], records: [] };
    }

    const records = [];
    const trs = Array.from(tableBody.querySelectorAll("tr"));
    trs.forEach(tr => {
      if (tr.querySelector('.empty-state')) return;
      const tds = Array.from(tr.querySelectorAll("td"));
      if (tds.length < Math.max(marketIdx, channelIdx, ...weekIndices) + 1) return;

      const market = normalizeText(tds[marketIdx].textContent);
      const channel = normalizeText(tds[channelIdx].textContent);
      const weekData = {};

      weekIndices.forEach((idx, i) => {
        const val = normalizeText(tds[idx].textContent);
        weekData[weeks[i]] = val;
      });

      records.push({ market, channel, weeks: weekData });
    });

    return { weeks, records };
  }

  function toggleView(viewType) {
    if (state.view === viewType) return;
    state.view = viewType;

    const tableWrap = document.querySelector(".ots-table-wrap");
    const paginationBar = document.querySelector(".ots-pagination-bar");
    const graphWrap = document.getElementById("otsGraphWrap");
    const btnTable = document.getElementById("btnViewTable");
    const btnGraph = document.getElementById("btnViewGraph");

    if (viewType === 'table') {
      if (tableWrap) tableWrap.hidden = false;
      if (paginationBar) paginationBar.hidden = false;
      if (graphWrap) graphWrap.hidden = true;
      if (btnTable) btnTable.classList.add("active");
      if (btnGraph) btnGraph.classList.remove("active");
      
      // Cleanup chart when leaving to save memory, or keep it. Prompt says "Destroy chart instance when leaving Graph View"
      if (state.chartInstance) {
        state.chartInstance.dispose();
        state.chartInstance = null;
      }
    } else {
      if (tableWrap) tableWrap.hidden = true;
      if (paginationBar) paginationBar.hidden = true;
      if (graphWrap) graphWrap.hidden = false;
      if (btnGraph) btnGraph.classList.add("active");
      if (btnTable) btnTable.classList.remove("active");

      renderGraphView();
    }
  }

  async function renderGraphView() {
    const graphWrap = document.getElementById("otsGraphWrap");
    const container = document.getElementById("otsGraphContainer");
    const loadingEl = document.getElementById("otsGraphLoading");
    const emptyEl = document.getElementById("otsGraphEmpty");

    loadingEl.hidden = false;
    emptyEl.hidden = true;

    try {
      await loadEcharts();
    } catch (e) {
      console.error("Failed to load ECharts", e);
      loadingEl.hidden = true;
      emptyEl.textContent = "Failed to load charting library.";
      emptyEl.hidden = false;
      return;
    }

    if (!state.chartInstance) {
      state.chartInstance = window.echarts.init(container);
    }

    // 1. Parse data from table
    const data = parseTableData();
    let records = data.records;
    const weeks = data.weeks;

    // 2. Filter for Delhi by default if multiple markets exist
    const distinctMarkets = Array.from(new Set(records.map(r => r.market.toLowerCase())));
    if (distinctMarkets.length > 1) {
      const delhiRecords = records.filter(r => r.market.toLowerCase().includes("delhi"));
      if (delhiRecords.length > 0) {
        records = delhiRecords;
      } else {
        // If no delhi, just take the first market to avoid overlapping lines
        const firstMarket = distinctMarkets[0];
        records = records.filter(r => r.market.toLowerCase() === firstMarket);
      }
    }

    if (records.length === 0 || weeks.length === 0) {
      state.chartInstance.clear();
      loadingEl.hidden = true;
      emptyEl.textContent = "No data available to graph.";
      emptyEl.hidden = false;
      return;
    }

    // 3. Prepare ECharts Options
    const channels = Array.from(new Set(records.map(r => r.channel)));
    const legendSelected = {};
    const seriesList = [];

    channels.forEach(channel => {
      // Determine if default selected
      const isDefault = DEFAULT_CHANNELS.some(dc => dc.toLowerCase() === channel.toLowerCase());
      legendSelected[channel] = isDefault;

      const record = records.find(r => r.channel === channel);
      const seriesData = [];
      
      weeks.forEach(week => {
        let val = record.weeks[week];
        if (val && val !== "NA") {
          seriesData.push([week, channel, parseFloat(val)]);
        }
      });

      seriesList.push({
        name: channel,
        type: 'line',
        symbol: 'circle',
        symbolSize: 8,
        data: seriesData,
        itemStyle: { color: getChannelColor(channel) },
        lineStyle: { width: 3 },
        emphasis: { focus: 'series' }
      });
    });

    // Make sure at least one channel is selected if the defaults weren't present
    if (!Object.values(legendSelected).some(v => v === true)) {
      channels.forEach(c => legendSelected[c] = true);
    }

    const currentMarketName = records[0].market;

    const option = {
      title: {
        text: `OTS Distribution - ${currentMarketName}`,
        left: 'center',
        top: 10
      },
      tooltip: {
        trigger: 'item',
        formatter: function (params) {
          const week = params.value[0];
          const channel = params.value[1];
          const ots = params.value[2];
          return `
            <div style="font-weight:bold;margin-bottom:4px;border-bottom:1px solid #ccc;padding-bottom:4px;">${channel}</div>
            Week: ${week}<br/>
            OTS: ${ots}%
          `;
        }
      },
      legend: {
        type: 'scroll',
        bottom: 10,
        selected: legendSelected,
        data: channels
      },
      toolbox: {
        feature: {
          dataZoom: { yAxisIndex: 'none' },
          restore: {},
          saveAsImage: { name: 'ots_distribution_graph' }
        },
        right: 20,
        top: 10
      },
      grid: {
        left: '3%',
        right: '4%',
        bottom: '15%',
        top: '15%',
        containLabel: true
      },
      dataZoom: [
        { type: 'slider', xAxisIndex: 0, filterMode: 'none' },
        { type: 'inside', xAxisIndex: 0, filterMode: 'none' },
        { type: 'slider', yAxisIndex: 0, filterMode: 'none', right: 10 },
        { type: 'inside', yAxisIndex: 0, filterMode: 'none' }
      ],
      xAxis: {
        type: 'category',
        data: weeks,
        boundaryGap: false,
        axisLine: { onZero: false }
      },
      yAxis: {
        type: 'category',
        data: channels,
        axisLine: { onZero: false }
      },
      series: seriesList
    };

    state.chartInstance.setOption(option, true);
    loadingEl.hidden = true;
    emptyEl.hidden = true;
  }

  // Hook into the main render function if possible, to automatically update graph if it's visible
  // We can setup a MutationObserver on the tableBody to know when data changes.
  function setupTableObserver() {
    const tableBody = document.getElementById("otsTableBody");
    if (!tableBody) return;
    const observer = new MutationObserver(() => {
      if (state.view === 'graph') {
        renderGraphView();
      }
    });
    observer.observe(tableBody, { childList: true, subtree: true });
  }

  // Expose methods to global scope so HTML can bind to them
  window.ChromeReportGraph = {
    toggleView,
    setup: function() {
      setupTableObserver();
      // Handle window resize
      window.addEventListener('resize', () => {
        if (state.chartInstance && state.view === 'graph') {
          state.chartInstance.resize();
        }
      });
    }
  };

  // Run setup if DOM is already loaded
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', window.ChromeReportGraph.setup);
  } else {
    window.ChromeReportGraph.setup();
  }

})();
