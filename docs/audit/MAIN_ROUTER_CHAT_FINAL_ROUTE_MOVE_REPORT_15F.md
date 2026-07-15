# FRONT-BRAIN-MAIN-ROUTER-CHAT-FINAL-ROUTE-MOVE-15F

Status: `FULLY_COMPLETED_CHAT_ROUTE_MOVE`

## Decision

`POST /chat` was moved from `tmp_agent/brain_v9/main.py` to `tmp_agent/brain_v9/routes/chat_entrypoint_routes.py`.

The move reuses the 15E service boundary:

- `ChatEntrypointRuntime`
- `handle_chat_entrypoint(req, runtime)`
- `configure_chat_entrypoint_runtime_provider(...)`
- `configure_chat_service_runtime_provider(...)`

## Baseline

- Initial HEAD: `fe08844`
- Initial origin: `fe08844`
- Initial `main.py` lines: `2466`
- Initial `main.py` app endpoint count: `51`
- Initial `main.py` had `@app.post("/chat")`: `true`
- Initial router had `@router.post("/chat")`: `false`
- Initial `/chat` wrapper lines: `4`
- Backup branch: `backup/main-chat-final-route-move-pre-15f-fe08844`

## Final State

- `/chat` moved: `yes`
- `main.py` has `@app.post("/chat")`: `false`
- router has `@router.post("/chat")`: `true`
- service boundary reused: `yes`
- `ChatRequest` / `ChatResponse` are owned by `chat_entrypoint_routes.py`
- `main.py` still registers `chat_entrypoint_router`
- `main.py` registers `configure_chat_entrypoint_runtime_provider(_chat_entrypoint_runtime_payload)` for introspective chat
- `main.py` registers `configure_chat_service_runtime_provider(_build_chat_entrypoint_runtime)` for `POST /chat`

## Metrics

- `main.py` app endpoint count before: `51`
- `main.py` app endpoint count after: `50`
- `main.py` line count before: `2466`
- `main.py` line count after: `2441`
- Remaining `main.py` route count: `50`

## Behavior Preservation

Preserved via `handle_chat_entrypoint`:

- response shape
- `pending_action`
- trace behavior
- native routing/fallback
- timeout behavior
- curated/trivial fastpaths
- PAD/GOD behavior
- network safety behavior
- Tool01 metadata fields

## Validation Plan

- `python -m py_compile tmp_agent/brain_v9/main.py`
- `python -m py_compile tmp_agent/brain_v9/routes/chat_entrypoint_routes.py`
- `python -m py_compile tmp_agent/brain_v9/core/chat_entrypoint_service.py`
- `python -m py_compile tests/contract/test_main_routes_chat_final_route_move_15f.py`
- `python tests/contract/test_main_routes_chat_final_route_move_15f.py`
- `python -m pytest tests/contract/test_main_routes_chat_final_route_move_15f.py -q`
- focused nontrading regression block with 15F included: `240 passed, 3 skipped`
- P0 nontrading security smoke: `19 passed`

## No-Touch Confirmation

15F did not modify:

- `tmp_agent/brain_v9/core/session.py`
- `tmp_agent/brain_v9/core/session_agent_route.py`
- SCVL internals
- `tmp_agent/brain_v9/core/semantic_memory_faiss.py`
- `memory/semantic/*`
- FAISS files
- `tmp_agent/state/*`
- trading/risk/IBKR/QC internals
- runtime ledgers/journals/snapshots

## Next Front

Recommended next front: continue main-router reduction on the remaining high-coupling `main.py` routes, or push 15F and verify CI first.
