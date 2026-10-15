let queueInterval = null;
let isProcessing = false;
let lastKnownImageCount = 0;

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (!message?.action) return;

  if (message.action === "START_QUEUE") {
    startQueue();
  }

  if (message.action === "PAUSE_QUEUE") {
    stopQueueLoop();
  }

  if (message.action === "RESUME_QUEUE") {
    startQueue();
  }

  if (message.action === "RESET_QUEUE") {
    stopQueueLoop();
    isProcessing = false;
    lastKnownImageCount = countImagesInConversation();
  }
});

async function startQueue() {
  stopQueueLoop();

  lastKnownImageCount = countImagesInConversation();

  queueInterval = setInterval(async () => {
    const state = await chrome.storage.local.get([
      "masterPrompt",
      "prompts",
      "currentIndex",
      "running",
      "paused"
    ]);

    if (!state.running || state.paused) return;
    if (isProcessing) return;

    const prompts = state.prompts || [];
    const currentIndex = state.currentIndex || 0;

    if (currentIndex >= prompts.length) {
      await chrome.storage.local.set({ running: false });
      stopQueueLoop();
      console.log("Queue completed.");
      return;
    }

    const isGeneratingNow = detectGenerationInProgress();
    const currentImageCount = countImagesInConversation();

    if (isGeneratingNow) {
      return;
    }

    if (currentImageCount > lastKnownImageCount) {
      lastKnownImageCount = currentImageCount;
    }

    const nextPromptLine = prompts[currentIndex];
    await sendPrompt(nextPromptLine, state.masterPrompt || "");

  }, 4000);
}

function stopQueueLoop() {
  if (queueInterval) {
    clearInterval(queueInterval);
    queueInterval = null;
  }
}

function detectTextarea() {
  return document.querySelector('textarea, div[contenteditable="true"]');
}

function detectSendButton() {
  const buttons = [...document.querySelectorAll("button")];
  return buttons.find(btn => {
    const label = (btn.innerText || btn.getAttribute("aria-label") || "").toLowerCase();
    return label.includes("send") || btn.querySelector("svg");
  });
}

function detectGenerationInProgress() {
  const pageText = document.body.innerText.toLowerCase();
  if (pageText.includes("stop generating")) return true;

  const buttons = [...document.querySelectorAll("button")];
  const stopBtn = buttons.find(btn => {
    const label = (btn.innerText || btn.getAttribute("aria-label") || "").toLowerCase();
    return label.includes("stop");
  });

  return !!stopBtn;
}

function countImagesInConversation() {
  return document.querySelectorAll("main img").length;
}

async function sendPrompt(promptLine, masterPrompt) {
  isProcessing = true;

  try {
    const textArea = detectTextarea();
    const sendButton = detectSendButton();

    if (!textArea) {
      console.warn("Prompt box not found.");
      isProcessing = false;
      return;
    }

    const finalPrompt = buildFinalPrompt(promptLine, masterPrompt);

    if (textArea.tagName.toLowerCase() === "textarea") {
      textArea.focus();
      textArea.value = finalPrompt;
      textArea.dispatchEvent(new Event("input", { bubbles: true }));
    } else {
      textArea.focus();
      textArea.innerHTML = "";
      document.execCommand("insertText", false, finalPrompt);
      textArea.dispatchEvent(new Event("input", { bubbles: true }));
    }

    await sleep(800);

    if (sendButton) {
      sendButton.click();
    } else {
      textArea.dispatchEvent(new KeyboardEvent("keydown", {
        key: "Enter",
        code: "Enter",
        which: 13,
        keyCode: 13,
        bubbles: true
      }));
    }

    const data = await chrome.storage.local.get(["currentIndex"]);
    await chrome.storage.local.set({
      currentIndex: (data.currentIndex || 0) + 1
    });

    console.log("Sent:", promptLine);
  } catch (error) {
    console.error("Error sending prompt:", error);
  } finally {
    setTimeout(() => {
      isProcessing = false;
    }, 2500);
  }
}

function buildFinalPrompt(promptLine, masterPrompt) {
  let frameNo = "";
  let scenePrompt = promptLine;

  if (promptLine.includes("||")) {
    const parts = promptLine.split("||");
    frameNo = parts[0].trim();
    scenePrompt = parts.slice(1).join("||").trim();
  }

  return `${masterPrompt}

Frame label: ${frameNo}

Scene description:
${scenePrompt}

Generate only one single frame image for this prompt.`;
}

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}