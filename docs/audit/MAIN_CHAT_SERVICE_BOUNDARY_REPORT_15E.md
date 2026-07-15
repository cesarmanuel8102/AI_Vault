# FRONT-BRAIN-MAIN-ROUTER-CHAT-SERVICE-BOUNDARY-15E

Status: `COMPLETED_SERVICE_BOUNDARY`

## Decision

15E created a real service boundary for `POST /chat` without moving the FastAPI decorator. The route remains in `tmp_agent/brain_v9/main.py`, but the operational body now lives in `tmp_agent/brain_v9/core/chat_entrypoint_service.py`.

## Baseline

- Initial HEAD: `f97a273`
- Initial origin: `f97a273`
- Initial `main.py` lines: `2851`
- Initial app endpoint count: `51`
- Initial `POST /chat` wrapper/body lines: `404`
- Backup branch: `backup/main-chat-service-boundary-pre-15e-f97a273`

## Service Boundary

Service file created: `tmp_agent/brain_v9/core/chat_entrypoint_service.py`

Main service API:

- `ChatEntrypointRuntime`
- `chat_entrypoint_runtime_field_count`
- `handle_chat_entrypoint(req, runtime)`

`main.py` now owns only:

- `_build_chat_entrypoint_runtime()`
- `@app.post("/chat")`
- thin wrapper delegating to `handle_chat_entrypoint`

## Metrics

- Wrapper line count before: `404`
- Wrapper line count after: `4`
- Dependency count before: `24`
- Dependency count after in wrapper: `2` (`handle_chat_entrypoint`, `_build_chat_entrypoint_runtime`)
- Dataclass/provider field count: `16`
- Endpoint count before: `51`
- Endpoint count after: `51`
- `main.py` line count before: `2851`
- `main.py` line count after: `2466`

## Behavior Preservation

Preserved in the service:

- `ChatResponse` response shape
- trivial fastpath
- curated learning fastpath
- PAD/GOD flow
- pending action extraction and permission fields
- trace emission
- local-network guarded fastpath
- native `handle_user_message` routing
- timeout behavior
- Tool01 trace/result field propagation

## Validation Plan Executed

- `python -m py_compile tmp_agent/brain_v9/main.py`
- `python -m py_compile tmp_agent/brain_v9/core/chat_runtime_helpers.py`
- `python -m py_compile tmp_agent/brain_v9/core/chat_entrypoint_service.py`
- `python -m py_compile tests/unit/test_chat_entrypoint_service_15e.py`
- `python -m py_compile tests/contract/test_main_chat_service_boundary_15e.py`
- `python tests/unit/test_chat_entrypoint_service_15e.py`
- `python tests/contract/test_main_chat_service_boundary_15e.py`
- 15D / 15C / 15B regression contracts
- nontrading focused block with 15E included
- 15E unit script: `CHAT_ENTRYPOINT_SERVICE_15E_OK`
- 15E unit pytest: `8 passed`
- 15E contract script: `MAIN_CHAT_SERVICE_BOUNDARY_15E_OK`
- 15E contract pytest: `9 passed`
- 15B-15E focused regression: `39 passed`
- nontrading focused block with 15E: `229 passed, 3 skipped`
- P0 nontrading security smoke: `19 passed`

## No-Touch Confirmation

15E did not modify:

- `tmp_agent/brain_v9/core/session.py`
- `tmp_agent/brain_v9/core/session_agent_route.py`
- SCVL internals
- `tmp_agent/brain_v9/core/semantic_memory_faiss.py`
- `memory/semantic/*`
- FAISS files
- `tmp_agent/state/*`
- trading/risk/IBKR/QC internals
- runtime ledgers/journals/snapshots

## 15F Readiness

15F can now perform the final move: relocate the thin `@app.post("/chat")` wrapper from `main.py` to `chat_entrypoint_routes.py` using the existing `ChatEntrypointRuntime` provider boundary.

Recommended next front: `FRONT-BRAIN-MAIN-ROUTER-CHAT-FINAL-MOVE-15F`
