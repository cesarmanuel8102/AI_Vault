# Visual Surface Audit — Corrective Patch

Date: 2026-06-17
Front: FRONT-BRAIN-AGENT-V2-CHAT-MODE-SWITCH-READ-BUILD-AUTO-01

## Defects Identified

1. **8091 mode selector unclear**: Confusing controls (`model-select` dropdown + `agent-toggle` button + hidden `mode-select` dropdown) instead of clear mode buttons
2. **8092 no visible mode selector**: No mode controls in "Chat with Brain" panel
3. **NL mode commands unreliable**: Phrases like `"hazlo en build"` not parsed deterministically
4. **Port-safe route probe silent substitution**: Explicit `8092` URLs silently replaced by `8091`

## Fixes Applied

### 8091 UI (`ui/index.html`)
- Replaced `<select id="mode-select">` + `<button id="agent-toggle">` with segmented `[📖 READ] [🔨 BUILD] [⚙ AUTO]` buttons
- `sendMessage()` now reads `currentMode` from buttons instead of hardcoding `'read_only'`
- Added inline `detectModeInMessage()` for Spanish/English natural-language mode switching
- Response meta line displays: `Mode: READ|BUILD|AUTO (auto=read|build_required)`
- Added `renderEscalationPanel()` with "Cambiar a BUILD" button when escalation_required

### 8092 Dashboard (`dashboard/static/index.html`, `app.js`)
- Added segmented mode selector buttons above chat textarea
- Cache-busted `<script src="/static/app.js?v=2">` to prevent stale cached JS
- `chat()` transmits `dashChatMode` to proxy; meta line shows effective mode

### Backend Wiring
- `dashboard_routes.py`: proxy forwards mode and returns all mode fields
- `tool_gateway.py`: `_route_probe` preserves explicit URLs/ports; only normalizes bare relative paths
- `governance.py`: `parse_mode_from_message()` with deterministic pattern matching
- `api_adapter.py`: `chat_agent()` applies NL-detected mode if present

## Verification

- Existing smoke tests: **20/20 PASS**
- NL parser unit tests: **16/16 PASS**
- Port-safe route probe tests: **4/4 PASS**
- UI wiring assertions: **PASS** (all buttons wired, all JS variables present)
- Python syntax check: **ALL COMPILE OK**
