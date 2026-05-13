(function () {
  if (window.__brainPOHookInstalled) return;
  window.__brainPOHookInstalled = true;

  // Minimum interval between WS-push snapshots (ms).
  // Prevents flooding the bridge while still giving ~4 ticks/sec even in background tabs.
  const WS_PUSH_MIN_INTERVAL_MS = 250;
  let _lastWsPushTime = 0;

  const state = {
    runtime: {},
    ws: {
      event_count: 0,
      outgoing_count: 0,
      last_event_name: null,
      last_socket_url: null,
      last_raw_preview: null,
      last_outgoing_preview: null,
      last_requested_asset: null,
      last_history_asset: null,
      last_stream_symbol: null,
      stream_symbol_match: null,
      hook_mode: "extension_document_start"
    },
    dom: {},
    current: {},
    symbols: []
  };

  function safeText(el) {
    return el ? String(el.textContent || "").trim() : null;
  }

  function safeAttr(el, name) {
    try {
      return el ? String(el.getAttribute(name) || "").trim() : "";
    } catch (_) {
      return "";
    }
  }

  function normalizeSymbol(raw) {
    if (!raw) return null;
    return String(raw)
      .replace(/[\/\s]+/g, "")
      .replace(/OTC$/i, "")
      .replace(/_+/g, "_")
      .replace(/_$/, "")
      .toUpperCase() + "_otc";
  }

  function symbolToPair(symbol) {
    const raw = String(symbol || "").replace(/_otc$/i, "").toUpperCase();
    const match = raw.match(/^([A-Z]{3})([A-Z]{3})$/);
    if (!match) return null;
    return `${match[1]}/${match[2]} OTC`;
  }

  function normalizeDurationSeconds(value) {
    const seconds = Number(value || 0);
    if (!Number.isFinite(seconds) || seconds <= 0) return null;
    if (seconds > 3600) return null;
    return Math.round(seconds);
  }

  function collectPairCandidates(bodyText) {
    const text = String(bodyText || "");
    const pairRegex = /([A-Z]{3}\/[A-Z]{3}\s+OTC)(.{0,160})/g;
    const candidates = [];
    let match;
    while ((match = pairRegex.exec(text)) !== null) {
      const pair = match[1];
      const suffix = String(match[2] || "").replace(/\s+/g, " ").trim();
      let score = 0;
      if (/(?:m\d+\s*)?chart type:|(?:m\d+\s*)?timeframe:|(?:m\d+\s*)?indicators/i.test(suffix)) score += 8;
      if (/chart type|timeframe|indicators|drawings|multi chart/i.test(suffix)) score += 4;
      if (/time00:|amount|payout|buy|sell/i.test(suffix)) score += 3;
      if (/sorry, this trading instrument is currently unavailable/i.test(suffix)) score += 2;
      if (/\+\d{2,3}%/.test(suffix)) score -= 2;
      candidates.push({
        pair,
        context: suffix.slice(0, 96),
        score
      });
      if (candidates.length >= 24) break;
    }
    return candidates;
  }

  function extractActivePair(bodyText) {
    const normalizedText = String(bodyText || "").replace(/\s+/g, " ");
    const focusedPatterns = [
      /([A-Z]{3}\/[A-Z]{3}\s+OTC)\s*(?:M\d+\s*)?Chart type:/i,
      /([A-Z]{3}\/[A-Z]{3}\s+OTC)\s*(?:M\d+\s*)?Timeframe:/i,
      /([A-Z]{3}\/[A-Z]{3}\s+OTC)\s*(?:M\d+\s*)?Indicators/i,
      /([A-Z]{3}\/[A-Z]{3}\s+OTC)\s*(?:M\d+\s*)?Drawings/i,
      /([A-Z]{3}\/[A-Z]{3}\s+OTC)\s*(?:M\d+\s*)?Multi Chart/i,
      /([A-Z]{3}\/[A-Z]{3}\s+OTC)\s*Sorry, this trading instrument is currently unavailable/i,
      /([A-Z]{3}\/[A-Z]{3}\s+OTC)\s*Time00:/i,
      /([A-Z]{3}\/[A-Z]{3}\s+OTC)\s*Amount/i,
      /([A-Z]{3}\/[A-Z]{3}\s+OTC)\s*Payout/i
    ];

    for (const pattern of focusedPatterns) {
      const match = normalizedText.match(pattern);
      if (match) return match[1];
    }

    const candidates = collectPairCandidates(normalizedText).sort((a, b) => b.score - a.score);
    if (candidates.length && candidates[0].score > 0) {
      return candidates[0].pair;
    }

    const fallback = normalizedText.match(/([A-Z]{3}\/[A-Z]{3}\s+OTC|[A-Z]{6}\s+OTC)/);
    return fallback ? fallback[1].replace(/\s+/g, " ").trim() : null;
  }

  function activeDomSymbol() {
    return normalizeSymbol((state.dom && state.dom.pair) || null);
  }

  function extractVisiblePrice() {
    const selectors = [
      "[data-test*='price']",
      "[data-testid*='price']",
      "[class*='price']",
      "[class*='quote']",
      "[class*='rate']"
    ];
    for (const selector of selectors) {
      for (const node of document.querySelectorAll(selector)) {
        const text = safeText(node);
        if (!text) continue;
        const match = text.match(/(\d+\.\d{3,6})/);
        if (match) return Number(match[1]);
      }
    }
    return null;
  }

  function socketPayloadToText(payload) {
    try {
      if (typeof payload === "string") return payload;
      if (payload instanceof ArrayBuffer) {
        return new TextDecoder("utf-8").decode(new Uint8Array(payload));
      }
      if (ArrayBuffer.isView(payload)) {
        return new TextDecoder("utf-8").decode(
          new Uint8Array(payload.buffer, payload.byteOffset, payload.byteLength)
        );
      }
      return String(payload || "");
    } catch (_) {
      try {
        return String(payload || "");
      } catch (_) {
        return "";
      }
    }
  }

  function socketPayloadPreview(payload) {
    try {
      const text = socketPayloadToText(payload);
      if (text && text !== "[object ArrayBuffer]") return text.slice(0, 240);
      if (payload instanceof ArrayBuffer) {
        return Array.from(new Uint8Array(payload).slice(0, 48))
          .map((b) => b.toString(16).padStart(2, "0"))
          .join(" ");
      }
      if (ArrayBuffer.isView(payload)) {
        return Array.from(new Uint8Array(payload.buffer, payload.byteOffset, Math.min(payload.byteLength, 48)))
          .map((b) => b.toString(16).padStart(2, "0"))
          .join(" ");
      }
      return text.slice(0, 240);
    } catch (_) {
      return "";
    }
  }

  function parseOutgoingAssetHints(preview) {
    const text = String(preview || "");
    const changeMatch = text.match(/"changeSymbol",\{"asset":"([^"]+)"/i);
    if (changeMatch) {
      state.ws.last_requested_asset = normalizeSymbol(changeMatch[1]);
    }
    const historyMatch = text.match(/"loadHistoryPeriod",\{"asset":"([^"]+)"/i);
    if (historyMatch) {
      state.ws.last_history_asset = normalizeSymbol(historyMatch[1]);
    }
  }

  function captureDom() {
    try {
      state.runtime = {
        captured_utc: new Date().toISOString(),
        href: location.href,
        reason: "interval",
        is_top_frame: window.top === window,
        referrer: document.referrer || null
      };

      const bodyText = document.body ? document.body.innerText : "";
      const pairCandidates = collectPairCandidates(bodyText);
      const domPair = extractActivePair(bodyText);
      const payoutMatch = bodyText.match(/(\d{2,3})%/);
      const expiryMatch = bodyText.match(/(\d{2}):(\d{2}):(\d{2})/);
      const balanceMatch = bodyText.match(/(\d{1,3}(?:,\d{3})*(?:\.\d+)?)/);
      const domSymbol = normalizeSymbol(domPair);
      const bestPairScore = pairCandidates.length
        ? Math.max(...pairCandidates.map((candidate) => Number(candidate.score || 0)))
        : 0;
      const socketAsset =
        state.ws.last_requested_asset ||
        state.ws.last_history_asset ||
        state.ws.last_stream_symbol ||
        null;
      const preferSocketAsset = Boolean(
        socketAsset &&
        (!domSymbol || (domSymbol !== socketAsset && bestPairScore <= 0))
      );
      const pair = preferSocketAsset ? (symbolToPair(socketAsset) || domPair) : domPair;
      const symbol = preferSocketAsset ? socketAsset : domSymbol;
      const payout = payoutMatch ? Number(payoutMatch[1]) : null;
      const expiryClockSeconds = expiryMatch
        ? (Number(expiryMatch[1]) * 3600) + (Number(expiryMatch[2]) * 60) + Number(expiryMatch[3])
        : null;
      const effectiveDurationSeconds =
        normalizeDurationSeconds(state.current.expiry_seconds) ||
        normalizeDurationSeconds(state.dom.requested_duration_seconds) ||
        60;
      const balance = balanceMatch ? Number(balanceMatch[1].replace(/,/g, "")) : null;
      const visiblePrice = extractVisiblePrice();
      const streamMismatch = state.ws.stream_symbol_match === false;
      const acceptedVisiblePrice = streamMismatch ? null : visiblePrice;

      state.dom = {
        pair,
        payout_pct: payout,
        expiry_raw: expiryMatch ? expiryMatch[0] : null,
        expiry_seconds: effectiveDurationSeconds,
        expiry_clock_seconds: expiryClockSeconds,
        balance_demo: balance,
        visible_price: acceptedVisiblePrice || (streamMismatch ? null : state.current.price) || null,
        pair_detection_mode: preferSocketAsset ? "socket_asset_override" : "dom_text",
        pair_candidates: pairCandidates,
        duration_candidates: collectDurationCandidates(),
        indicator_candidates: collectIndicatorCandidates(),
        indicator_readouts: collectIndicatorReadouts(),
        page_url: location.href,
        is_top_frame: window.top === window,
        title: document.title
      };
      state.ws.visible_symbol = symbol;

      if (symbol) {
        state.current.symbol = symbol;
        state.current.pair = pair;
      }
      if (streamMismatch) {
        state.current.source_timestamp = null;
        state.current.price = null;
      } else if (acceptedVisiblePrice) {
        state.current.price = acceptedVisiblePrice;
      }
      if (payout != null) state.current.payout_pct = payout;
      if (effectiveDurationSeconds) state.current.expiry_seconds = effectiveDurationSeconds;
      if (symbol && !state.symbols.includes(pair)) state.symbols.push(pair);
    } catch (_) {}
  }

  function normalizeDirection(value) {
    const direction = String(value || "").toLowerCase();
    if (["call", "buy", "higher", "up"].includes(direction)) return "call";
    if (["put", "sell", "lower", "down"].includes(direction)) return "put";
    return direction;
  }

  function normalizeWords(value) {
    return String(value || "")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, " ")
      .trim()
      .split(/\s+/)
      .filter(Boolean);
  }

  function nodeLabel(node) {
    return [
      safeText(node),
      safeAttr(node, "aria-label"),
      safeAttr(node, "title"),
      safeAttr(node, "data-test"),
      safeAttr(node, "data-testid")
    ].filter(Boolean).join(" | ");
  }

  function findClickableByText(candidates) {
    const nodes = Array.from(document.querySelectorAll("button, [role='button'], .btn, .button"));
    const normalizedCandidates = candidates.map((value) => normalizeWords(value));
    return nodes.find((node) => {
      const words = normalizeWords(node.textContent || "");
      if (!words.length) return false;
      return normalizedCandidates.some((candidateWords) =>
        candidateWords.length > 0 &&
        candidateWords.every((candidateWord) => words.includes(candidateWord))
      );
    }) || null;
  }

  function collectButtonLabels() {
    return Array.from(document.querySelectorAll("button, [role='button'], .btn, .button"))
      .map((node) => String(node.textContent || "").trim())
      .filter(Boolean)
      .slice(0, 30);
  }

  function collectDurationCandidates() {
    const pattern = /(^|\s)(\d+)\s*(s|sec|secs|second|seconds|m|min|mins|minute|minutes|h|hour|hours)\b/i;
    const collected = Array.from(document.querySelectorAll("button, [role='button'], .btn, .button, [class*='time'], [class*='expiration'], [class*='expiry']"))
      .map((node) => {
        const label = safeText(node) || safeAttr(node, "aria-label") || safeAttr(node, "title");
        return { label, full: nodeLabel(node) };
      })
      .filter((item) => {
        if (!item.label) return false;
        if (pattern.test(item.label)) return true;
        const shorthand = item.label.match(/^m(\d+)$/i);
        if (!shorthand) return false;
        const minutes = Number(shorthand[1]);
        return Number.isFinite(minutes) && minutes > 0 && minutes <= 15;
      })
      .slice(0, 20);

    const bodyText = document.body ? String(document.body.innerText || "") : "";
    const visibleDuration = bodyText.match(/Time\s*(\d{2}):(\d{2}):(\d{2})/i);
    if (visibleDuration) {
      const [, hh, mm, ss] = visibleDuration;
      const totalSeconds = (Number(hh) * 3600) + (Number(mm) * 60) + Number(ss);
      if (totalSeconds > 0 && totalSeconds <= 3600) {
        const label = `${hh}:${mm}:${ss}`;
        if (!collected.some((item) => String(item.label || "").includes(label))) {
          collected.unshift({
            label,
            full: `visible_time_panel:${label}`
          });
        }
      }
    }

    if (state.current.expiry_seconds) {
      const normalized = durationAliases(state.current.expiry_seconds)[0] || `${state.current.expiry_seconds}s`;
      if (!collected.some((item) => parseDurationLabelToSeconds(item.label) === state.current.expiry_seconds)) {
        collected.unshift({
          label: normalized,
          full: `current_expiry_seconds:${state.current.expiry_seconds}`
        });
      }
    }

    return collected.slice(0, 20);
  }

  function collectIndicatorCandidates() {
    const names = ["indicator", "indicators", "rsi", "ema", "sma", "macd", "bollinger", "atr", "vwap", "stochastic"];
    return Array.from(document.querySelectorAll("button, [role='button'], .btn, .button, [class*='indicator'], [class*='study'], [class*='tools']"))
      .map((node) => nodeLabel(node))
      .filter(Boolean)
      .filter((label) => names.some((name) => label.toLowerCase().includes(name)))
      .slice(0, 30);
  }

    function collectIndicatorReadouts() {
      const indicatorPattern = /\b(rsi|ema|sma|macd|bollinger|atr|vwap|stochastic)\b/i;
      const ignoredTokens = [
        "pocketoption",
        "qt demo",
        "buy",
        "sell",
        "payout",
        "tournaments",
        "chat",
        "finance",
        "trading",
        "opened",
        "closed",
        "forecast",
        "order:",
        "social trading",
        "express trades"
      ];
      const seen = new Set();
      const results = [];
      function pushReadout(label, values, source) {
        const cleanLabel = String(label || "").replace(/\s+/g, " ").trim().slice(0, 120);
        const key = cleanLabel.toLowerCase();
        if (!cleanLabel || seen.has(key)) return;
        seen.add(key);
        results.push({
          label: cleanLabel,
          values: (values || []).slice(0, 4),
          source
        });
      }
      for (const node of Array.from(document.querySelectorAll("div, span, label, p"))) {
        const text = safeText(node);
        if (!text) continue;
        if (text.length > 120) continue;
        if ((text.match(/\n/g) || []).length > 3) continue;
        const lower = text.toLowerCase();
        if (!indicatorPattern.test(text)) continue;
        if (ignoredTokens.some((token) => lower.includes(token))) continue;
        const numeric = text.match(/-?\d+(?:\.\d+)?/g);
        if (!numeric || !numeric.length) continue;
        if (numeric.length > 6) continue;
        pushReadout(text, numeric, "dom_indicator_text");
        if (results.length >= 20) break;
      }
      if (!results.length) {
        for (const label of collectIndicatorCandidates()) {
          if (!indicatorPattern.test(String(label || ""))) continue;
          const numeric = String(label || "").match(/-?\d+(?:\.\d+)?/g) || [];
          pushReadout(label, numeric, "indicator_candidate");
          if (results.length >= 20) break;
        }
      }
      if (results.length) return results;

      const bodyText = document.body ? String(document.body.innerText || "") : "";
      const fallbackPatterns = [
        { name: "RSI", pattern: /(RSI\s*14[^\n\r]{0,80}?)(\d+(?:\.\d+)?(?:\s+\d+(?:\.\d+)?){0,3})/i },
        { name: "Stochastic", pattern: /(Stochastic Oscillator\s*14\s*3\s*3[^\n\r]{0,80}?)(\d+(?:\.\d+)?(?:\s+\d+(?:\.\d+)?){0,3})/i },
        { name: "MACD", pattern: /(MACD\s*12\s*26\s*9[^\n\r]{0,80}?)(-?\d+(?:\.\d+)?(?:\s+-?\d+(?:\.\d+)?){0,3})/i },
        { name: "Bollinger", pattern: /(Bollinger Bands\s*5\s*1[^\n\r]{0,80}?)(-?\d+(?:\.\d+)?(?:\s+-?\d+(?:\.\d+)?){0,3})/i }
      ];
      for (const fallback of fallbackPatterns) {
        const match = bodyText.match(fallback.pattern);
        if (!match) continue;
        const values = String(match[2] || "").match(/-?\d+(?:\.\d+)?/g) || [];
        if (!values.length) continue;
        pushReadout(String(match[1] || fallback.name), values, "body_text_fallback");
      }
      return results;
    }

  function durationAliases(seconds) {
    const sec = Number(seconds || 0);
    if (!sec) return [];
    if (sec < 60) return [`${sec}s`, `${sec} sec`, `${sec} seconds`];
    const minutes = Math.round(sec / 60);
    const aliases = [`${minutes}m`, `${minutes} min`, `${minutes} mins`, `${minutes} minute`, `${minutes} minutes`, `M${minutes}`];
    if (minutes % 60 === 0) {
      const hours = Math.round(minutes / 60);
      aliases.push(`${hours}h`, `${hours} hour`, `${hours} hours`);
    }
    return aliases;
  }

  function setTradeAmount(amount) {
    // Strategy 1: input with type=number, inputMode=decimal, or amount-related placeholder
    const inputs = Array.from(document.querySelectorAll("input"));
    let target = inputs.find((input) => {
      const type = String(input.type || "").toLowerCase();
      const mode = String(input.inputMode || "").toLowerCase();
      const placeholder = String(input.placeholder || "").toLowerCase();
      return type === "number" || mode === "decimal" || placeholder.includes("amount") || placeholder.includes("$");
    });

    // Strategy 2: input inside a container whose class or ancestor text contains "amount" or "deal"
    if (!target) {
      target = inputs.find((input) => {
        let el = input.parentElement;
        for (let depth = 0; el && depth < 5; depth += 1, el = el.parentElement) {
          const cls = String(el.className || "").toLowerCase();
          const txt = String(el.textContent || "").toLowerCase().slice(0, 120);
          if (cls.includes("amount") || cls.includes("deal") || (txt.includes("trade") && /\$\d/.test(txt))) {
            return true;
          }
        }
        return false;
      });
    }

    // Strategy 3: input whose current value looks like the existing trade amount (a small number)
    if (!target) {
      target = inputs.find((input) => {
        const val = parseFloat(input.value);
        return !isNaN(val) && val > 0 && val < 100000 && input.offsetParent !== null;
      });
    }

    // Strategy 4: contenteditable element near "Trade" label that contains a dollar amount
    if (!target) {
      const editables = Array.from(document.querySelectorAll("[contenteditable='true'], [contenteditable='']"));
      const amountEditable = editables.find((el) => {
        const txt = String(el.textContent || "").trim();
        if (!/^\$?\d/.test(txt)) return false;
        let parent = el.parentElement;
        for (let d = 0; parent && d < 5; d += 1, parent = parent.parentElement) {
          if (/trade|amount|deal/i.test(String(parent.textContent || "").slice(0, 200))) return true;
        }
        return false;
      });
      if (amountEditable) {
        amountEditable.focus();
        amountEditable.textContent = String(amount);
        amountEditable.dispatchEvent(new Event("input", { bubbles: true }));
        amountEditable.dispatchEvent(new Event("change", { bubbles: true }));
        return true;
      }
    }

    // Strategy 5: PO-specific — look for the amount display element and try to use +/- buttons
    // PO shows "Trade $1" with up/down arrows; we can clear and type via the amount area
    if (!target) {
      const allEls = Array.from(document.querySelectorAll("span, div, input"));
      for (const el of allEls) {
        const txt = String(el.textContent || el.value || "").trim();
        // Match elements showing just a dollar amount like "$1", "$10", "1", "10"
        if (/^\$?\d{1,6}(\.\d{1,2})?$/.test(txt) && el.offsetParent !== null) {
          let parent = el.parentElement;
          for (let d = 0; parent && d < 4; d += 1, parent = parent.parentElement) {
            const parentText = String(parent.textContent || "").slice(0, 200).toLowerCase();
            if (parentText.includes("trade") && !parentText.includes("trading history")) {
              // Found the amount display — check if it or a sibling is an input
              const siblingInput = parent.querySelector("input");
              if (siblingInput) {
                target = siblingInput;
                break;
              }
              // Try clicking the element to activate an input
              el.click();
              // After click, re-scan for newly-visible input
              const newInput = parent.querySelector("input");
              if (newInput) {
                target = newInput;
                break;
              }
              // If element itself is editable via focus
              if (el.tagName === "INPUT" || el.isContentEditable) {
                el.focus();
                el.textContent = String(amount);
                el.dispatchEvent(new Event("input", { bubbles: true }));
                el.dispatchEvent(new Event("change", { bubbles: true }));
                return true;
              }
            }
          }
          if (target) break;
        }
      }
    }

    // Strategy 6: PO Vue/React internal state — try window.__STORE__ or app __vue__ instance
    if (!target) {
      try {
        // Some PO builds expose the trading module on a Vue instance
        const appEl = document.querySelector("#app") || document.querySelector("[data-v-app]");
        if (appEl && appEl.__vue_app__) {
          const store = appEl.__vue_app__.config.globalProperties.$store;
          if (store && typeof store.commit === "function") {
            store.commit("setTradeAmount", Number(amount));
            return true;
          }
        }
        if (appEl && appEl.__vue__) {
          const root = appEl.__vue__;
          if (root.$store && typeof root.$store.commit === "function") {
            root.$store.commit("setTradeAmount", Number(amount));
            return true;
          }
        }
      } catch (_) { /* ignore */ }
    }

    if (!target) return false;
    // Apply value to found input
    const nativeInputValueSetter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value").set;
    nativeInputValueSetter.call(target, String(amount));
    target.focus();
    target.dispatchEvent(new Event("input", { bubbles: true }));
    target.dispatchEvent(new Event("change", { bubbles: true }));
    target.dispatchEvent(new Event("blur", { bubbles: true }));
    return true;
  }

  function clickNode(node) {
    if (!node) return false;
    try {
      node.click();
      return true;
    } catch (_) {
      try {
        node.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true, view: window }));
        return true;
      } catch (_) {
        return false;
      }
    }
  }

  function parseDurationLabelToSeconds(label) {
    const text = String(label || "").trim().toLowerCase();
    if (!text) return null;
    const compact = text.replace(/\s+/g, "");
    let match = compact.match(/^m(\d+)$/i);
    if (match) return Number(match[1]) * 60;
    match = compact.match(/^(\d+)(s|sec|secs|second|seconds)$/i);
    if (match) return Number(match[1]);
    match = compact.match(/^(\d+)(m|min|mins|minute|minutes)$/i);
    if (match) return Number(match[1]) * 60;
    match = compact.match(/^(\d+)(h|hr|hrs|hour|hours)$/i);
    if (match) return Number(match[1]) * 3600;
    return null;
  }

  function findDurationNode(seconds) {
    const aliases = durationAliases(seconds).map((value) => normalizeWords(value).join(" "));
    const nodes = Array.from(
      document.querySelectorAll(
        "button, [role='button'], .btn, .button, [class*='time'], [class*='expiration'], [class*='expiry']"
      )
    );

    for (const node of nodes) {
      const label = nodeLabel(node);
      const normalized = normalizeWords(label).join(" ");
      const parsedSeconds = parseDurationLabelToSeconds(label);
      if (parsedSeconds && Math.abs(parsedSeconds - seconds) <= 1) {
        return { node, label };
      }
      if (aliases.some((alias) => alias && normalized.includes(alias))) {
        return { node, label };
      }
    }
    return null;
  }

  function setDuration(duration) {
    state.dom.requested_duration_seconds = duration;

    const directMatch = findDurationNode(duration);
    if (directMatch && clickNode(directMatch.node)) {
      state.dom.selected_duration_label = directMatch.label;
      return { ok: true, mode: "direct_button", label: directMatch.label };
    }

    const opener = findClickableByText(["expiry"]) ||
      findClickableByText(["expiration"]) ||
      findClickableByText(["time"]) ||
      findClickableByText(["duration"]);

    if (opener && clickNode(opener)) {
      const delayedMatch = findDurationNode(duration);
      if (delayedMatch && clickNode(delayedMatch.node)) {
        state.dom.selected_duration_label = delayedMatch.label;
        return { ok: true, mode: "opened_then_button", label: delayedMatch.label };
      }
    }

    const inputs = Array.from(document.querySelectorAll("input"));
    const durationInput = inputs.find((input) => {
      const hint = [
        safeAttr(input, "placeholder"),
        safeAttr(input, "aria-label"),
        safeAttr(input, "name"),
        safeAttr(input, "id")
      ].join(" ").toLowerCase();
      return ["time", "duration", "expiry", "expiration"].some((token) => hint.includes(token));
    });

    if (durationInput) {
      try {
        const seconds = Number(duration || 0);
        const minutes = seconds >= 60 ? Math.round(seconds / 60) : seconds;
        durationInput.focus();
        durationInput.value = String(minutes);
        durationInput.dispatchEvent(new Event("input", { bubbles: true }));
        durationInput.dispatchEvent(new Event("change", { bubbles: true }));
        state.dom.selected_duration_label = `${minutes}${seconds >= 60 ? "m" : "s"}`;
        return { ok: true, mode: "input_fill", label: state.dom.selected_duration_label };
      } catch (_) {}
    }

    return { ok: false, mode: "not_found", label: null };
  }

  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  function extractDemoBalance() {
    try {
      const text = document.body ? String(document.body.innerText || "") : "";
      const qtMatch = text.match(/QT Demo\s+USD\s+(\d{1,3}(?:,\d{3})*(?:\.\d+)?)/i);
      if (qtMatch) return Number(qtMatch[1].replace(/,/g, ""));
      const genericMatch = text.match(/(?:QT Demo|Demo)\s+(\d{1,3}(?:,\d{3})*(?:\.\d+)?)/i);
      if (genericMatch) return Number(genericMatch[1].replace(/,/g, ""));
    } catch (_) {}
    return null;
  }

  function uniqueStrings(values) {
    return Array.from(new Set((values || []).filter(Boolean).map((value) => String(value))));
  }

  function captureTradeJournalEvidence() {
    const text = document.body ? String(document.body.innerText || "") : "";
    const orderIds = uniqueStrings(
      Array.from(text.matchAll(/Order[:\s]+([a-f0-9-]{8,})/gi)).map((match) => match[1])
    );
    const openTimes = Array.from(text.matchAll(/Open time:\s*([0-9:.]+)/gi)).map((match) => match[1]);
    const closingTimes = Array.from(text.matchAll(/Closing time:\s*([0-9:.]+)/gi)).map((match) => match[1]);
    const forecasts = Array.from(text.matchAll(/Your forecast:\s*(BUY|SELL)/gi)).map((match) => String(match[1] || "").toUpperCase());
    const pnlValues = Array.from(text.matchAll(/(?:Profit|Difference):\s*([+\-]?\$?\d[\d.,]*)/gi)).map((match) => match[1]);
    const tradeOrderPlacedCount = (text.match(/Trade order placed/gi) || []).length;
    const doubleUpCount = (text.match(/Double Up/gi) || []).length;
    const forecastCardCount = (text.match(/Forecast\s+(BUY|SELL)/gi) || []).length;
    const tradesBadgeMatches = Array.from(text.matchAll(/Trades\s*(\d+)/gi)).map((match) => Number(match[1]));
    const tradesBadgeMax = tradesBadgeMatches.length ? Math.max(...tradesBadgeMatches.filter((value) => Number.isFinite(value))) : 0;
    const recentRows = Array.from(document.querySelectorAll("div, li, tr"))
      .map((node) => safeText(node))
      .filter((value) => value && /(Order:|Open time:|Closing time:|Your forecast:|Trade order placed|Double Up|Forecast|AUD\/NZD OTC|AUDNZD_otc)/i.test(value))
      .slice(0, 24);
    const activeTab = findClickableByText(["opened"]) ? "opened_present" : (findClickableByText(["closed"]) ? "closed_present" : null);

    return {
      captured_utc: new Date().toISOString(),
      balance_demo: extractDemoBalance(),
      order_ids: orderIds.slice(0, 12),
      order_count: orderIds.length,
      open_time_count: openTimes.length,
      closing_time_count: closingTimes.length,
      forecasts: forecasts.slice(0, 12),
      pnl_values: pnlValues.slice(0, 12),
      trade_order_placed_count: tradeOrderPlacedCount,
      double_up_count: doubleUpCount,
      forecast_card_count: forecastCardCount,
      trades_badge_max: tradesBadgeMax,
      active_tab_hint: activeTab,
      recent_rows: recentRows,
    };
  }

  function verifyTradeJournalDelta(before, after, direction) {
    const expectedForecast = direction === "call" ? "BUY" : (direction === "put" ? "SELL" : null);
    const beforeOrders = new Set((before.order_ids || []).map((value) => String(value)));
    const afterOrders = new Set((after.order_ids || []).map((value) => String(value)));
    const newOrderIds = Array.from(afterOrders).filter((value) => !beforeOrders.has(value));
    const balanceBefore = Number(before.balance_demo || 0);
    const balanceAfter = Number(after.balance_demo || 0);
    const balanceDelta = Number.isFinite(balanceBefore) && Number.isFinite(balanceAfter)
      ? Math.abs(balanceAfter - balanceBefore)
      : 0;
    const forecastDelta = Math.max(0, (after.forecasts || []).length - (before.forecasts || []).length);
    const openTimeDelta = Math.max(0, Number(after.open_time_count || 0) - Number(before.open_time_count || 0));
    const closingDelta = Math.max(0, Number(after.closing_time_count || 0) - Number(before.closing_time_count || 0));
    const tradeOrderPlacedDelta = Math.max(0, Number(after.trade_order_placed_count || 0) - Number(before.trade_order_placed_count || 0));
    const doubleUpDelta = Math.max(0, Number(after.double_up_count || 0) - Number(before.double_up_count || 0));
    const forecastCardDelta = Math.max(0, Number(after.forecast_card_count || 0) - Number(before.forecast_card_count || 0));
    const tradesBadgeDelta = Math.max(0, Number(after.trades_badge_max || 0) - Number(before.trades_badge_max || 0));
    const matchingForecastSeen = expectedForecast
      ? (after.forecasts || []).includes(expectedForecast) && !(before.forecasts || []).includes(expectedForecast)
      : false;
    const notificationSeen = tradeOrderPlacedDelta > 0;
    const openTradeCardSeen = doubleUpDelta > 0 || tradesBadgeDelta > 0;
    const forecastCardSeen = forecastCardDelta > 0;

    let confirmed = false;
    let confirmationMode = null;

    if (newOrderIds.length > 0) {
      confirmed = true;
      confirmationMode = "new_order_id";
    } else if (notificationSeen && openTradeCardSeen) {
      confirmed = true;
      confirmationMode = "trade_notification_and_open_card";
    } else if (notificationSeen && (forecastCardSeen || matchingForecastSeen)) {
      confirmed = true;
      confirmationMode = "trade_notification_and_forecast_card";
    } else if (openTimeDelta > 0) {
      confirmed = true;
      confirmationMode = "open_trade_row_delta";
    } else if (closingDelta > 0) {
      confirmed = true;
      confirmationMode = "closed_trade_row_delta";
    } else if (forecastDelta > 0 && matchingForecastSeen) {
      confirmed = true;
      confirmationMode = "forecast_row_delta";
    } else if (balanceDelta >= 0.5) {
      confirmed = true;
      confirmationMode = "balance_delta";
    }

    return {
      confirmed,
      confirmation_mode: confirmationMode,
      new_order_ids: newOrderIds.slice(0, 5),
      balance_delta: balanceDelta,
      forecast_delta: forecastDelta,
      open_time_delta: openTimeDelta,
      closing_time_delta: closingDelta,
      trade_order_placed_delta: tradeOrderPlacedDelta,
      double_up_delta: doubleUpDelta,
      forecast_card_delta: forecastCardDelta,
      trades_badge_delta: tradesBadgeDelta,
      notification_seen: notificationSeen,
      open_trade_card_seen: openTradeCardSeen,
      forecast_card_seen: forecastCardSeen,
      matching_forecast_seen: matchingForecastSeen,
    };
  }

  async function executeTradeCommand(command) {
    const trade = command && command.trade ? command.trade : {};
    const direction = normalizeDirection(trade.direction);
    const amountOk = setTradeAmount(trade.amount);
    const durationResult = setDuration(trade.duration);
    const journalBefore = captureTradeJournalEvidence();
    const button = direction === "call"
      ? findClickableByText(["call", "higher", "buy"])
      : findClickableByText(["put", "lower", "sell"]);
    const buttonText = button ? String(button.textContent || "").trim() : null;
    const acceptedButtonLabels = direction === "call"
      ? ["call", "higher", "buy"]
      : ["put", "lower", "sell"];
    const words = normalizeWords(buttonText || "");
    const validTradeButton = acceptedButtonLabels.some((label) => normalizeWords(label).every((word) => words.includes(word)));

    let clicked = false;
    let failureReason = null;
    if (!amountOk) {
      failureReason = "amount_input_not_found";
    } else if (!button) {
      failureReason = "trade_button_not_found";
    } else if (!validTradeButton) {
      failureReason = "trade_button_not_recognized";
    } else {
      try {
        button.click();
        clicked = true;
      } catch (error) {
        failureReason = `trade_click_failed:${String(error)}`;
      }
    }

    let journalAfter = null;
    let confirmation = {
      confirmed: false,
      confirmation_mode: null,
      new_order_ids: [],
      balance_delta: 0,
      forecast_delta: 0,
      open_time_delta: 0,
      closing_time_delta: 0,
      matching_forecast_seen: false,
    };

    if (clicked) {
      for (let attempt = 0; attempt < 8; attempt += 1) {
        await sleep(400);
        journalAfter = captureTradeJournalEvidence();
        confirmation = verifyTradeJournalDelta(journalBefore, journalAfter, direction);
        if (confirmation.confirmed) break;
      }
      if (!journalAfter) {
        journalAfter = captureTradeJournalEvidence();
        confirmation = verifyTradeJournalDelta(journalBefore, journalAfter, direction);
      }
    }

    const resultStatus = !clicked
      ? "failed"
      : (confirmation.confirmed ? "ui_trade_confirmed" : "submitted_demo_click_unverified");

    window.postMessage(
      {
        type: "BRAIN_PO_TRADE_RESULT",
        payload: {
          command_id: command.command_id,
          success: Boolean(clicked && confirmation.confirmed),
          accepted_click: Boolean(clicked),
          ui_trade_confirmed: Boolean(confirmation.confirmed),
          status: resultStatus,
          reason: failureReason,
          trade: trade,
          evidence: {
            amount_input_found: amountOk,
            duration_captured: Boolean(durationResult && durationResult.ok),
            duration_mode: durationResult ? durationResult.mode : null,
            selected_duration_label: durationResult ? durationResult.label : null,
            direction: direction,
            button_text: buttonText,
            candidate_buttons: collectButtonLabels(),
            duration_candidates: collectDurationCandidates(),
            indicator_candidates: collectIndicatorCandidates(),
            indicator_readouts: collectIndicatorReadouts(),
            current_symbol: state.current.symbol || null,
            journal_before: journalBefore,
            journal_after: journalAfter,
            confirmation: confirmation,
            page_url: location.href,
            title: document.title
          },
          captured_utc: new Date().toISOString()
        }
      },
      "*"
    );
  }

  function decodeSocketPayload(payload) {
    try {
      const text = socketPayloadToText(payload);
      state.ws.event_count += 1;
      state.ws.last_raw_preview = socketPayloadPreview(payload);

      let decoded = null;
      if (text.includes("updateStream")) {
        state.ws.last_event_name = "updateStream";
      }

      // ── P-OP55a: Intercept loadHistoryPeriod / historyPeriod responses ──
      // PocketOption sends historical OHLC candles in response to chart
      // load/scroll requests.  Format:
      //   42["historyPeriod", {"asset":"EURUSD_otc","period":60,"data":[[ts,o,c,h,l], ...]}]
      // We forward these to the bridge as BRAIN_PO_HISTORY_CANDLES so the
      // candle buffer gets seeded instantly instead of accumulating from zero.
      if (text.includes("historyPeriod") || text.includes("history")) {
        try {
          const arrIdx = text.indexOf("[");
          if (arrIdx !== -1) {
            const parsed = JSON.parse(text.slice(arrIdx));
            // parsed = ["historyPeriod", {asset, period, data: [...]}]
            if (Array.isArray(parsed) && parsed.length >= 2) {
              let histPayload = null;
              // Handle both ["historyPeriod", {...}] and nested formats
              for (let i = 0; i < parsed.length; i++) {
                const el = parsed[i];
                if (el && typeof el === "object" && !Array.isArray(el) && Array.isArray(el.data)) {
                  histPayload = el;
                  break;
                }
              }
              if (histPayload && histPayload.data && histPayload.data.length > 0) {
                const asset = histPayload.asset || histPayload.symbol || state.ws.last_history_asset || state.ws.last_stream_symbol;
                const period = histPayload.period || 60;
                const symbol = normalizeSymbol(asset);
                // Convert candle data to OHLC objects
                const candles = [];
                for (const row of histPayload.data) {
                  if (Array.isArray(row) && row.length >= 5) {
                    // PO format: [timestamp, open, close, high, low]
                    candles.push({
                      t: Number(row[0]),
                      o: Number(row[1]),
                      c: Number(row[2]),
                      h: Number(row[3]),
                      l: Number(row[4])
                    });
                  }
                }
                if (candles.length > 0 && symbol) {
                  state.ws.last_event_name = "historyPeriod";
                  window.postMessage({
                    type: "BRAIN_PO_HISTORY_CANDLES",
                    payload: {
                      captured_utc: new Date().toISOString(),
                      symbol: symbol,
                      period: period,
                      candle_count: candles.length,
                      candles: candles,
                      source: "browser_bridge_history"
                    }
                  }, "*");
                }
              }
            }
          }
        } catch (_histErr) {}
      }

      const arrayIndex = text.indexOf("[");
      if (arrayIndex !== -1) {
        try {
          decoded = JSON.parse(text.slice(arrayIndex));
        } catch (_) {}
      }
      if (!decoded) return;

      const stack = Array.isArray(decoded) ? [...decoded] : [decoded];
      while (stack.length) {
        const item = stack.shift();
        if (Array.isArray(item)) {
          if (item.length >= 3 && typeof item[0] === "string" && item[0].toUpperCase().includes("OTC")) {
            const [symbolRaw, ts, price] = item;
            const symbol = normalizeSymbol(symbolRaw);
            const numericPrice = Number(price);
            const durationSeconds =
              normalizeDurationSeconds(state.dom.requested_duration_seconds) ||
              normalizeDurationSeconds(state.current.expiry_seconds) ||
              normalizeDurationSeconds(state.dom.expiry_seconds) ||
              60;
            const activeSymbol = activeDomSymbol();
            state.ws.last_stream_symbol = symbol;
            if (activeSymbol && symbol !== activeSymbol) {
              state.ws.stream_symbol_match = false;
              state.current = {
                symbol: activeSymbol,
                pair: state.dom.pair || null,
                source_timestamp: null,
                price: null,
                payout_pct: state.dom.payout_pct || state.current.payout_pct || null,
                expiry_seconds:
                  normalizeDurationSeconds(state.current.expiry_seconds) ||
                  normalizeDurationSeconds(state.dom.expiry_seconds) ||
                  60
              };
              continue;
            }
            if (symbol && Number.isFinite(numericPrice) && numericPrice > 0) {
              state.ws.stream_symbol_match = true;
              state.current = {
                symbol,
                pair: state.dom.pair || (String(symbolRaw).replace("_otc", "").replace(/([A-Z]{3})([A-Z]{3})/, "$1/$2") + " OTC"),
                source_timestamp: ts,
                price: numericPrice,
                payout_pct: state.dom.payout_pct || state.current.payout_pct || null,
                expiry_seconds: durationSeconds
              };
              // PUSH model: send price to bridge immediately on every WS tick,
              // bypassing the setInterval poll which gets throttled in background tabs.
              // Rate-limited to max ~4/sec to avoid flooding the bridge with disk writes.
              var _now = Date.now();
              if (_now - _lastWsPushTime >= WS_PUSH_MIN_INTERVAL_MS) {
                _lastWsPushTime = _now;
                try {
                  window.postMessage(
                    {
                      type: "BRAIN_PO_CAPTURE_RESPONSE",
                      payload: {
                        captured_utc: new Date().toISOString(),
                        runtime: { captured_utc: new Date().toISOString(), reason: "ws_push", href: location.href, is_top_frame: window.top === window },
                        ws: state.ws,
                        dom: state.dom,
                        current: state.current,
                        symbols: state.symbols,
                        source: "browser_bridge"
                      }
                    },
                    "*"
                  );
                } catch (_pushErr) {}
              }
              return;
            }
          }
          stack.push(...item);
        } else if (item && typeof item === "object") {
          stack.push(...Object.values(item));
        }
      }
    } catch (_) {}
  }

  const NativeWebSocket = window.WebSocket;
  window.WebSocket = function (...args) {
    const ws = new NativeWebSocket(...args);
    try {
      state.ws.last_socket_url = args[0];
    } catch (_) {}
    ws.addEventListener("message", (event) => {
      decodeSocketPayload(event.data);
    });
    const nativeSend = ws.send;
    ws.send = function (payload) {
      try {
        state.ws.outgoing_count += 1;
        state.ws.last_outgoing_preview = socketPayloadPreview(payload);
        parseOutgoingAssetHints(state.ws.last_outgoing_preview);
      } catch (_) {}
      return nativeSend.call(this, payload);
    };
    return ws;
  };
  window.WebSocket.prototype = NativeWebSocket.prototype;

  window.addEventListener("message", (event) => {
    if (event.source !== window) return;
    if (!event.data || event.data.type !== "BRAIN_PO_CAPTURE_REQUEST") return;
    captureDom();
    window.postMessage(
      {
        type: "BRAIN_PO_CAPTURE_RESPONSE",
        payload: {
          captured_utc: new Date().toISOString(),
          runtime: state.runtime,
          ws: state.ws,
          dom: state.dom,
          current: state.current,
          symbols: state.symbols,
          source: "browser_bridge"
        }
      },
      "*"
    );
  });

  window.addEventListener("message", (event) => {
    if (event.source !== window) return;
    if (!event.data || event.data.type !== "BRAIN_PO_EXECUTE_TRADE") return;
    executeTradeCommand(event.data.payload);
  });

  // ANTI-FREEZE: Create a silent AudioContext so Chrome/Edge treats this tab
  // as "playing media" and does NOT freeze the main thread when backgrounded.
  // Without this, background tabs get their entire JS execution suspended
  // after ~1-2 minutes, blocking WebSocket event delivery and killing our
  // price feed.  The AudioContext produces zero-amplitude output (inaudible).
  function initAntiFreeze() {
    try {
      var ctx = new (window.AudioContext || window.webkitAudioContext)();
      var osc = ctx.createOscillator();
      var gain = ctx.createGain();
      gain.gain.value = 0.0001;  // effectively silent but nonzero so Chrome doesn't optimize it away
      osc.connect(gain);
      gain.connect(ctx.destination);
      osc.start();
      // Chrome requires user gesture to resume AudioContext.
      // Listen for first click/keydown to resume if suspended.
      function resumeCtx() {
        if (ctx.state === "suspended") ctx.resume();
      }
      document.addEventListener("click", resumeCtx, { once: true });
      document.addEventListener("keydown", resumeCtx, { once: true });
      // Also try resuming immediately (works if already had user gesture)
      resumeCtx();
    } catch (_) {}
  }
  initAntiFreeze();

  // ANTI-FREEZE PLAN B: Inline Web Worker with a fast setInterval.
  // Web Worker threads are NOT subject to background tab throttling.
  // The worker pings the main thread every 500ms; the main thread
  // responds with the latest price state, keeping the message channel
  // active which helps prevent full tab freezing.
  function initWorkerKeepAlive() {
    try {
      var blob = new Blob([
        "setInterval(function(){ postMessage('tick'); }, 500);"
      ], { type: "application/javascript" });
      var worker = new Worker(URL.createObjectURL(blob));
      worker.onmessage = function () {
        // On each worker tick, if we have a price and enough time passed,
        // push a snapshot. This acts as a secondary push channel.
        var now = Date.now();
        if (now - _lastWsPushTime >= 750 && state.current.price) {
          _lastWsPushTime = now;
          try {
            window.postMessage({
              type: "BRAIN_PO_CAPTURE_RESPONSE",
              payload: {
                captured_utc: new Date().toISOString(),
                runtime: { captured_utc: new Date().toISOString(), reason: "worker_keepalive", href: location.href, is_top_frame: window.top === window },
                ws: state.ws,
                dom: state.dom,
                current: state.current,
                symbols: state.symbols,
                source: "browser_bridge"
              }
            }, "*");
          } catch (_) {}
        }
      };
    } catch (_) {}
  }
  initWorkerKeepAlive();

  setInterval(captureDom, 1500);
  captureDom();
})();
