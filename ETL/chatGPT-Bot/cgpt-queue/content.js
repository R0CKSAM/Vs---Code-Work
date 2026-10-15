(() => {
  if (window.__cgptQueue) return;
  window.__cgptQueue = true;

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const q = (sel) => document.querySelector(sel);

  let running = false;
  let stopFlag = false;

  const composer = () =>
    q("#prompt-textarea") ||
    q('div[contenteditable="true"][role="textbox"]') ||
    q('div[contenteditable="true"]');

  const isBusy = () =>
    !!(q('button[data-testid="stop-button"]') ||
       q('button[aria-label="Stop streaming"]') ||
       q('button[aria-label*="Stop"]'));

  const msgCount = () =>
    document.querySelectorAll('div[data-message-author-role="assistant"]').length;

  const imgSrcs = () =>
    new Set([...document.images].map((i) => i.currentSrc || i.src).filter(Boolean));

  function newBigImages(exclude) {
    return [...document.images].filter((img) => {
      const src = img.currentSrc || img.src;
      if (!src || exclude.has(src)) return false;
      const w = img.naturalWidth || img.width;
      const h = img.naturalHeight || img.height;
      return w >= 120 && h >= 120;
    });
  }

  function setComposer(text) {
    const el = composer();
    if (!el) return false;
    el.focus();
    const sel = window.getSelection();
    const range = document.createRange();
    range.selectNodeContents(el);
    sel.removeAllRanges();
    sel.addRange(range);
    document.execCommand("insertText", false, text);
    return true;
  }

  function submit() {
    const el = composer();
    if (!el) return;
    el.dispatchEvent(new KeyboardEvent("keydown", {
      key: "Enter", code: "Enter", keyCode: 13, which: 13,
      bubbles: true, cancelable: true
    }));
  }

  async function ensureSent() {
    await sleep(900);
    if (isBusy()) return true;
    const btn = q('button[data-testid="send-button"]') || q("#composer-submit-button");
    if (btn && !btn.disabled) {
      btn.click();
      await sleep(900);
    }
    return isBusy();
  }

  async function waitForResult(prevMsgs, timeoutMs) {
    const t0 = Date.now();
    let started = false;
    while (Date.now() - t0 < timeoutMs) {
      if (stopFlag) return true;
      if (isBusy()) started = true;
      else if (started && msgCount() > prevMsgs) {
        await sleep(2500);
        return true;
      }
      await sleep(1000);
    }
    return false;
  }

  async function waitForImages(before, timeoutMs) {
    const t0 = Date.now();
    while (Date.now() - t0 < timeoutMs) {
      const found = newBigImages(before);
      if (found.length) return found;
      await sleep(1000);
    }
    return [];
  }

  async function saveImage(img, filename) {
    const src = img.currentSrc || img.src;
    const res = await fetch(src);
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);

    const viaDownloads = await new Promise((resolve) => {
      try {
        chrome.runtime.sendMessage({ type: "download", url, filename }, (r) => {
          void chrome.runtime.lastError;
          resolve(!!(r && r.ok));
        });
      } catch (e) { resolve(false); }
    });

    if (!viaDownloads) {
      const a = document.createElement("a");
      a.href = url;
      a.download = filename.split("/").pop();
      document.body.appendChild(a);
      a.click();
      a.remove();
    }
  }

  function report(data) {
    try {
      chrome.storage.local.set({ cgptStatus: data });
    } catch (e) {}
    return new Promise((resolve) => {
      try {
        chrome.runtime.sendMessage({ type: "status", ...data }, () => {
          void chrome.runtime.lastError;
          resolve();
        });
      } catch (e) { resolve(); }
    });
  }

  async function logError(n, prompt) {
    const { cgptErrors = [] } = await chrome.storage.local.get("cgptErrors");
    cgptErrors.push({ n, prompt, at: new Date().toISOString() });
    await chrome.storage.local.set({ cgptErrors });
  }

  async function runQueue(prompts, delayMs, folder) {
    if (running) return;
    running = true;
    stopFlag = false;

    const { cgptIdx = 0 } = await chrome.storage.local.get("cgptIdx");
    let i = Math.min(cgptIdx, prompts.length);
    const total = prompts.length;
    await chrome.storage.local.set({ cgptTotal: total });

    for (; i < total; i++) {
      if (stopFlag) break;
      const prompt = prompts[i];
      await report({ status: `[${i + 1}/${total}] ${prompt.slice(0, 60)}`, idx: i, running: true });

      const before = imgSrcs();
      const prevMsgs = msgCount();

      if (!setComposer(prompt)) {
        await report({ status: "No composer found. Is this a ChatGPT tab?", running: false });
        running = false;
        return;
      }
      await sleep(250);
      submit();

      if (!(await ensureSent())) {
        await report({ status: `  ! prompt ${i + 1} didn't send - retrying` });
        setComposer(prompt);
        await sleep(400);
        submit();
        await ensureSent();
      }

      if (await waitForResult(prevMsgs, 900000)) {
        const imgs = await waitForImages(before, 60000);
        if (imgs.length) {
          for (let n = 0; n < imgs.length; n++) {
            const base = String(i + 1).padStart(3, "0");
            const name = imgs.length === 1
              ? `${folder}/${base}.png`
              : `${folder}/${base}_${n + 1}.png`;
            await saveImage(imgs[n], name);
          }
          await report({ status: `  saved ${imgs.length} image(s)`, idx: i, running: true });
        } else {
          await report({ status: `  ! reply but no image for #${i + 1}`, idx: i, running: true });
          await logError(i + 1, prompt);
        }
      } else {
        await report({ status: `  ! no reply for #${i + 1} (limit or error)`, idx: i, running: true });
        await logError(i + 1, prompt);
      }

      await chrome.storage.local.set({ cgptIdx: i + 1 });
      await sleep(delayMs + Math.random() * 3000);
    }

    running = false;
    await report({ status: stopFlag ? "Stopped." : "Finished.", running: false, done: true });
  }

  chrome.runtime.onMessage.addListener((msg, _s, sendResponse) => {
    if (!msg) return;
    if (msg.type === "start") {
      runQueue(msg.prompts, msg.delayMs || 5000, msg.folder || "chatgpt-batch");
      sendResponse({ ok: true });
      return true;
    }
    if (msg.type === "stop") { stopFlag = true; sendResponse({ ok: true }); return true; }
    if (msg.type === "ping") { sendResponse({ ok: true, running }); return true; }
  });

  console.log("[cgpt-queue] content script ready");
})();