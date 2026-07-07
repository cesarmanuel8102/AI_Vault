# FRONT-BRAIN-UI-CHAT-BACKEND-STREAMING-EVENTS-04 — Design Notes

## Existing flow
- `POST /brain-dashboard/chat` in `dashboard_routes.py:345` proxies to `http://127.0.0.1:8091/v2/chat/agent` via urllib, returns JSON with content/run_id/trace_url/metadata.
- `GET /brain-dashboard/agent-v2/runs/{run_id}/trace` in `dashboard_routes.py:415` proxies to 8091 trace endpoint.
- `app.js sendChat()` does `fetch('/brain-dashboard/chat')`, gets JSON, updates timeline with local-only events, then calls `loadTraceForRun(runId)` after response.
- Timeline events are all client-side: `request_prepared`, `mode_selected`, `request_sent`, `waiting_provider`, `response_received`, etc.
- No real streaming exists today.

## New endpoint: POST /brain-dashboard/chat/stream
- Content-Type: `text/event-stream`
- Uses FastAPI `StreamingResponse` with a generator that yields SSE events.
- Reuses same urllib proxy logic to 8091 as `/brain-dashboard/chat`.
- Emits real lifecycle events as they happen, not after.

## Event sequence
1. `request.accepted` — immediately
2. `mode.selected` — immediately after
3. `backend.call.started` — before urllib call
4. `backend.call.completed` — after urllib returns (or `stream.error` on failure)
5. `response.metadata` — run_id, trace_url, classification, mode, provider, blocked_tools
6. `response.final` — content
7. `trace.fetch.started` — if run_id exists
8. `trace.fetch.completed` — after trace proxy call (or `trace.limit` if unavailable)
9. `trace.enriched` — tools/evidence/governance/provider summary from trace
10. `trace.limit` — if tool details not exposed live (truthful)
11. `stream.completed` — end

## Honesty rule
No fake tool.started/tool.completed events. The current backend does not expose live tool events during execution. We emit `trace.limit` truthfully stating that live tool events are not exposed and post-response trace enrichment is used.

## UI changes
- `sendChat()` switches to streaming via `fetch('/brain-dashboard/chat/stream')` with ReadableStream reader.
- Events drive timeline updates in real-time.
- Fallback to legacy `/brain-dashboard/chat` if stream fails before first event.
- No changes to READ/BUILD/AUTO, inspector, safety locks, sanitizer, or trace link.

## Files
- `dashboard_routes.py` — add `/chat/stream` endpoint + SSE generator
- `app.js` — rewrite `sendChat()` to use streaming, keep legacy fallback
- `styles.css` — add streaming event visual distinctions
- `index.html` — cache busting if needed