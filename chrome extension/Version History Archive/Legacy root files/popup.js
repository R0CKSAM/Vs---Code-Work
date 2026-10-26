async function getActiveTab() {
  const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
  return tabs[0];
}

function parsePromptLines(raw) {
  return raw
    .split("\n")
    .map(line => line.trim())
    .filter(Boolean);
}

async function saveState(partial = {}) {
  const existing = await chrome.storage.local.get([
    "masterPrompt",
    "prompts",
    "currentIndex",
    "running",
    "paused"
  ]);

  const updated = {
    masterPrompt: existing.masterPrompt || "",
    prompts: existing.prompts || [],
    currentIndex: existing.currentIndex || 0,
    running: existing.running || false,
    paused: existing.paused || false,
    ...partial
  };

  await chrome.storage.local.set(updated);
  refreshStatus();
}

async function refreshStatus() {
  const data = await chrome.storage.local.get([
    "prompts",
    "currentIndex",
    "running",
    "paused"
  ]);

  const total = (data.prompts || []).length;
  const current = data.currentIndex || 0;

  let status = "Idle";
  if (data.running && !data.paused) status = "Running";
  if (data.paused) status = "Paused";
  if (!data.running && current >= total && total > 0) status = "Completed";

  document.getElementById("statusText").textContent = status;
  document.getElementById("progressText").textContent = `${Math.min(current, total)} / ${total}`;
}

async function notifyContentScript(action) {
  const tab = await getActiveTab();
  if (!tab?.id) return;

  try {
    await chrome.tabs.sendMessage(tab.id, { action });
  } catch (e) {
    console.warn("Content script not reachable:", e);
  }
}

document.getElementById("saveBtn").addEventListener("click", async () => {
  const masterPrompt = document.getElementById("masterPrompt").value.trim();
  const promptLines = parsePromptLines(document.getElementById("promptList").value);

  await saveState({
    masterPrompt,
    prompts: promptLines,
    currentIndex: 0,
    running: false,
    paused: false
  });

  alert("Saved successfully.");
});

document.getElementById("startBtn").addEventListener("click", async () => {
  const masterPrompt = document.getElementById("masterPrompt").value.trim();
  const promptLines = parsePromptLines(document.getElementById("promptList").value);

  await saveState({
    masterPrompt,
    prompts: promptLines,
    currentIndex: 0,
    running: true,
    paused: false
  });

  await notifyContentScript("START_QUEUE");
});

document.getElementById("pauseBtn").addEventListener("click", async () => {
  await saveState({ paused: true, running: false });
  await notifyContentScript("PAUSE_QUEUE");
});

document.getElementById("resumeBtn").addEventListener("click", async () => {
  await saveState({ paused: false, running: true });
  await notifyContentScript("RESUME_QUEUE");
});

document.getElementById("resetBtn").addEventListener("click", async () => {
  await saveState({
    currentIndex: 0,
    running: false,
    paused: false
  });
  await notifyContentScript("RESET_QUEUE");
});

document.addEventListener("DOMContentLoaded", async () => {
  const data = await chrome.storage.local.get(["masterPrompt", "prompts"]);
  document.getElementById("masterPrompt").value = data.masterPrompt || "";
  document.getElementById("promptList").value = (data.prompts || []).join("\n");
  refreshStatus();
});