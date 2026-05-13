(function () {
  if (window.__brainPOContentInstalled) return;
  window.__brainPOContentInstalled = true;

  function injectHook() {
    const script = document.createElement("script");
    script.src = chrome.runtime.getURL("page_hook.js");
    script.async = false;
    (document.head || document.documentElement).appendChild(script);
    script.remove();
  }

  async function postSnapshot(payload) {
    try {
      await fetch("http://127.0.0.1:8765/snapshot", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
      setTimeout(pollCommands, 0);
    } catch (_) {}
  }

  async function fetchNextCommand() {
    try {
      const response = await fetch(`http://127.0.0.1:8765/commands/next?ts=${Date.now()}`);
      if (!response.ok) return null;
      const payload = await response.json();
      return payload.command || null;
    } catch (_) {
      return null;
    }
  }

  async function postCommandResult(payload) {
    try {
      await fetch("http://127.0.0.1:8765/commands/result", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
    } catch (_) {}
  }

  // P-OP55a: Post historical candle data to the bridge for candle buffer seeding
  async function postHistoryCandles(payload) {
    try {
      await fetch("http://127.0.0.1:8765/history-candles", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload)
      });
    } catch (_) {}
  }

  window.addEventListener("message", (event) => {
    if (event.source !== window) return;
    if (!event.data || event.data.type !== "BRAIN_PO_CAPTURE_RESPONSE") return;
    postSnapshot(event.data.payload);
    return;
  });

  window.addEventListener("message", (event) => {
    if (event.source !== window) return;
    if (!event.data || event.data.type !== "BRAIN_PO_TRADE_RESULT") return;
    postCommandResult(event.data.payload);
  });

  // P-OP55a: Forward historical candle data to the bridge server
  window.addEventListener("message", (event) => {
    if (event.source !== window) return;
    if (!event.data || event.data.type !== "BRAIN_PO_HISTORY_CANDLES") return;
    postHistoryCandles(event.data.payload);
  });

  function requestCapture() {
    window.postMessage({ type: "BRAIN_PO_CAPTURE_REQUEST" }, "*");
  }

  function triggerImmediateSync() {
    requestCapture();
    setTimeout(pollCommands, 0);
  }

  const SNAPSHOT_INTERVAL_MS = 750;
  const COMMAND_POLL_INTERVAL_MS = 500;
  const INITIAL_CAPTURE_DELAY_MS = 500;
  const INITIAL_COMMAND_DELAY_MS = 750;

  let commandPollBusy = false;
  async function pollCommands() {
    if (commandPollBusy) return;
    commandPollBusy = true;
    try {
      const command = await fetchNextCommand();
      if (command) {
        window.postMessage({ type: "BRAIN_PO_EXECUTE_TRADE", payload: command }, "*");
      }
    } finally {
      commandPollBusy = false;
    }
  }

  injectHook();
  setTimeout(requestCapture, INITIAL_CAPTURE_DELAY_MS);
  setInterval(requestCapture, SNAPSHOT_INTERVAL_MS);
  setTimeout(pollCommands, INITIAL_COMMAND_DELAY_MS);
  setInterval(pollCommands, COMMAND_POLL_INTERVAL_MS);
  window.addEventListener("focus", triggerImmediateSync);
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) triggerImmediateSync();
  });
})();
