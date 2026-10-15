chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg && msg.type === "download") {
    chrome.downloads.download(
      { url: msg.url, filename: msg.filename, saveAs: false, conflictAction: "uniquify" },
      (id) => {
        if (chrome.runtime.lastError) {
          sendResponse({ ok: false, err: chrome.runtime.lastError.message });
        } else {
          sendResponse({ ok: true, id });
        }
      }
    );
    return true;
  }
});
