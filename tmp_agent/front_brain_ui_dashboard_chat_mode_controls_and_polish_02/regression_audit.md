# Phase 1 — Regression Audit

Front: `FRONT-BRAIN-UI-DASHBOARD-CHAT-MODE-CONTROLS-AND-POLISH-02`

## Previous mode selector (pre-modernization)

`index.html` lines 93–97 had:
```html
<div id="chat-mode-selector" class="mode-segment">
  <button id="dash-mode-read" class="mode-btn active" onclick="setChatMode('read_only')">📖 READ</button>
  <button id="dash-mode-build" class="mode-btn" onclick="setChatMode('build')">🔨 BUILD</button>
  <button id="dash-mode-auto" class="mode-btn" onclick="setChatMode('auto')">⚙ AUTO</button>
</div>
```
`app.js` had `setChatMode(mode)` which updated `dashChatMode` and toggled `.active`.

## Current state (post-modernization)

| Item | Finding |
|------|---------|
| State object | `S.chat.mode = 'read_only'` — **hardcoded**, no setter |
| `sendChat()` | Sends `mode: S.chat.mode` — contract correct, but value can never change |
| Composer HTML | Static `<span class="mode-badge">READ_ONLY</span>` — **not a selector** |
| `initChat()` | Wires Enter-to-send, resize, send, new-chat — **no mode listeners** |

## Confirmed regressions

- **mode_is_hardcoded_to_read_only:** true
- **build_auto_modes_impossible_to_select:** true
- **mode_selector_regression:** **true**

## Response fields displayed vs missing

**Displayed:** run_id, classification, model/provider, mode_effective (always read_only), blocked_tools, trace_url, provider_degraded, fallback_reason, raw_cot_exposed.

**Missing:** mode_requested, auto_decision, mode_escalation_required, mode_escalation_reason, required_permission, expected_write_scope, confirmation_id.

## Bugs found

- **Fallback false-alarm:** warning strip shows "Fallback used: none" even when `fallback_reason === 'none'` (truthy string). Should be suppressed.

## Classification

| Dimension | Status |
|-----------|--------|
| mode_selector_regression | **true** |
| chat_functionality_status | **partial** (send/receive works; mode locked to read_only) |
| inspector_metadata_status | **partial** (missing mode_requested/auto_decision/escalation/permission/write_scope/confirmation_id) |
| dashboard_visual_status | **improved** (modern shell preserved) |

## Required fixes

1. **FIX-1:** Add segmented mode selector `[READ][BUILD][AUTO]` to chat composer.
2. **FIX-2:** Wire selector to update `S.chat.mode` + composer badge + nav badge.
3. **FIX-3:** READ→`read_only`, BUILD→`build`, AUTO→`auto` (contract preserved).
4. **FIX-4:** Display `mode_requested`, `mode_effective`, `auto_decision` in inspector.
5. **FIX-5:** Display escalation card (`mode_escalation_required`, `mode_escalation_reason`, `required_permission`, `expected_write_scope`, `confirmation_id`) inside assistant bubble when present.
6. **FIX-6:** Fix fallback false-alarm (suppress when `fallback_reason === 'none'`).
7. **FIX-7:** Add safety helper text under selector.
8. **FIX-8:** Reflect selected mode in top bar / chat status line.
9. **FIX-9:** Show user bubble mode subtly.
10. **FIX-10:** Make "NOT CONNECTED" conversation history look intentional.

## Conclusion

**REGRESSION_AUDIT_CONFIRMED** — mode selector regression is real; chat works for read_only only; inspector missing several mode/escalation fields; fallback false-alarm bug present. Fixes scoped and safe (frontend-only).
