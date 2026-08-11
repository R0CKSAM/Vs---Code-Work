(function() {
  const state = {
    view: 'table', // 'table' or 'graph'
    isPlotlyLoaded: false,
    loading: false
  };

  const DEFAULT_CHANNELS = ["India TV", "Aaj Tak", "News18 India", "Republic Bharat"];
  const CHANNEL_COLORS = {
    "india tv": "#2f67ea",
    "aaj tak": "#ef4444",
    "news18 india": "#10b981",
    "republic bharat": "#f97316"
  };

  function normalizeText(txt) {
    return String(txt || "").trim();
  }

  function loadPlotly() {
    return new Promise((resolve, reject) => {
      if (window.Plotly) {
        state.isPlotlyLoaded = true;
        resolve();
        return;
      }
      if (document.getElementById('plotly-script')) {
        const script = document.getElementById('plotly-script');
        script.addEventListener('load', resolve);
        script.addEventListener('error', reject);
        return;
      }
      const script = document.createElement('script');
      script.id = 'plotly-script';
      script.src = 'https://cdn.plot.ly/plotly-2.32.0.min.js';
      script.async = true;
      script.onload = () => {
        state.isPlotlyLoaded = true;
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
    const container = document.getElementById("otsGraphContainer");
    const loadingEl = document.getElementById("otsGraphLoading");
    const emptyEl = document.getElementById("otsGraphEmpty");

    loadingEl.hidden = false;
    emptyEl.hidden = true;
    container.style.display = 'none';

    try {
      await loadPlotly();
    } catch (e) {
      console.error("Failed to load Plotly", e);
      loadingEl.hidden = true;
      emptyEl.textContent = "Failed to load charting library.";
      emptyEl.hidden = false;
      return;
    }

    const data = parseTableData();
    let records = data.records;
    const weeks = data.weeks;

    if (records.length === 0 || weeks.length === 0) {
      window.Plotly.purge(container);
      loadingEl.hidden = true;
      emptyEl.textContent = "No data available to graph.";
      emptyEl.hidden = false;
      return;
    }

    const channels = Array.from(new Set(records.map(r => r.channel)));
    const traces = [];

    const anyDefaultPresent = channels.some(c => DEFAULT_CHANNELS.some(dc => dc.toLowerCase() === c.toLowerCase()));

    channels.forEach(channel => {
      const record = records.find(r => r.channel === channel);
      const isDefault = DEFAULT_CHANNELS.some(dc => dc.toLowerCase() === channel.toLowerCase());
      
      const xData = [];
      const yData = [];
      const sizeData = [];
      const colorData = [];
      const textData = [];
      
      weeks.forEach(week => {
        let val = record.weeks[week];
        if (val && val !== "NA") {
          xData.push(week);
          yData.push(channel);
          const numVal = parseFloat(val);
          sizeData.push(numVal);
          colorData.push(numVal);
          textData.push(`Week: ${week}<br>Channel: ${channel}<br>OTS: ${numVal}%`);
        }
      });

      const visible = (anyDefaultPresent) ? (isDefault ? true : 'legendonly') : true;

      traces.push({
        name: channel,
        x: xData,
        y: yData,
        mode: 'markers',
        marker: {
          size: sizeData,
          sizemode: 'area',
          sizeref: 2,
          sizemin: 4,
          color: colorData,
          colorscale: 'Tealgrn',
          showscale: false
        },
        text: textData,
        hoverinfo: 'text',
        visible: visible
      });
    });

    const currentMarketName = records.map(r => r.market).filter((v, i, a) => a.indexOf(v) === i).join(', ');
    const titleText = currentMarketName.length < 50 ? `OTS Distribution - ${currentMarketName}` : 'OTS Distribution - Multiple Markets';

    const layout = {
      title: titleText,
      xaxis: { title: '' },
      yaxis: { title: '', automargin: true },
      hovermode: 'closest',
      margin: { l: 150, r: 20, t: 50, b: 50 },
      showlegend: true
    };

    const config = { responsive: true };

    loadingEl.hidden = true;
    container.style.display = 'block';
    window.Plotly.newPlot(container, traces, layout, config);
  }

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

  window.ChromeReportGraph = {
    toggleView,
    setup: function() {
      setupTableObserver();
    }
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', window.ChromeReportGraph.setup);
  } else {
    window.ChromeReportGraph.setup();
  }
})();
