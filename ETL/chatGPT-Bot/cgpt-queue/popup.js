const $ = (id) => document.getElementById(id);

function parseCSV(text) {
  const rows = [];
  let row = [], field = "", inQ = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (inQ) {
      if (c === '"') {
        if (text[i + 1] === '"') { field += '"'; i++; }
        else inQ = false;
      } else field += c;
    } else if (c === '"') inQ = true;
    else if (c === ",") { row.push(field); field = ""; }
    else if (c === "\n") { row.push(field); rows.push(row); row = []; field = ""; }
    else if (c !== "\r") field += c;
  }
  if (field.length || row.length) { row.push(field); rows.push(row); }

  const clean = rows.filter((r) => r.some((c) => c.trim()));
  if (!clean.length) return [];

  const head = clean[0].map((h) => h.trim().toLowerCase());
  const isHeader = head.some((h) => ["prompt", "text", "description", "caption"].includes(h));
  let col = -1;
  if (isHeader) {
    col = head.findIndex((h) => ["prompt", "text", "description", "caption"].includes(h));
    if (col < 0) col = head.length - 1;
  }
  const body = isHeader ? clean.slice(1) : clean;
  return body.map((r) => (isHeader ? (r[col] || "") : r.join(",")).trim()).filter(Boolean);
}

function parseInput(text) {
  const t = text.trim();
  if (!t) return [];
  if (t.includes(",") && /(^|\n)\s*(id|prompt|text)\s*,/i.test(t)) return parseCSV(t);
  return t.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
}

async function activeTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  return tab;
}

async function render() {
  const { cgptStatus, cgptIdx = 0, cgptTotal } = await chrome.storage.local.get(["cgptStatus", "cgptIdx", "cgptTotal"]);
  if (cgptStatus && cgptStatus.status) {
    $("status").textContent = cgptStatus.status + (cgptTotal ? `\n\nprogress: ${cgptIdx}/${cgptTotal}` : "");
  } else if (cgptIdx) {
    $("status").textContent = `Progress: ${cgptIdx}${cgptTotal ? "/" + cgptTotal : ""}`;
  }
}

$("load").onclick = () => $("file").click();
$("file").onchange = async (e) => {
  const f = e.target.files[0];
  if (!f) return;
  $("prompts").value = await f.text();
};

$("reset").onclick = async () => {
  await chrome.storage.local.set({ cgptIdx: 0, cgptErrors: [], cgptStatus: { status: "Idle. Progress reset." } });
  render();
};

$("start").onclick = async () => {
  const prompts = parseInput($("prompts").value);
  if (!prompts.length) { $("status").textContent = "No prompts."; return; }

  const tab = await activeTab();
  if (!tab || !/chatgpt\.com/.test(tab.url || "")) {
    $("status").textContent = "Switch to your ChatGPT tab, then press Start.";
    return;
  }

  const payload = {
    type: "start",
    prompts,
    delayMs: (parseInt($("delay").value, 10) || 5) * 1000,
    folder: ($("folder").value || "chatgpt-batch").replace(/\/+$/, "")
  };

  try {
    await chrome.tabs.sendMessage(tab.id, payload);
    $("status").textContent = `Started ${prompts.length} prompt(s).`;
  } catch (e) {
    $("status").textContent = "Content script not loaded - refresh the ChatGPT tab once.";
  }
};

$("stop").onclick = async () => {
  const tab = await activeTab();
  if (tab) { try { await chrome.tabs.sendMessage(tab.id, { type: "stop" }); } catch (e) {} }
};

chrome.runtime.onMessage.addListener((msg) => {
  if (msg && msg.type === "status") render();
});
chrome.storage.onChanged.addListener(render);
render();