# MAIN_ROUTER_SESSION_LIFECYCLE_REPORT_15A

Status: PARTIALLY_COMPLETED_WITH_DEFERRED

Front: FRONT-BRAIN-MAIN-ROUTER-SESSION-LIFECYCLE-15A

## State

- Branch: `codex/own-capital-sustainable-return`
- HEAD initial: `93ce681`
- HEAD final local: pending final docs commit at report creation time
- Origin at start: `93ce681`
- Backup branch: `backup/main-router-pre-15a-93ce681`
- Push: not performed

## Commits Created

- `e5382d3` - `refactor(routes): split session lifecycle endpoints`

## Endpoint Counts

Before 15A:

- `MAIN_PY_LINES`: 3258
- `APP_ENDPOINTS`: 59
- `APP_GET`: 16
- `APP_POST`: 40
- `APP_DELETE`: 3
- `APP_PUT`: 0
- `APP_PATCH`: 0

After 15A route commit:

- `MAIN_PY_LINES`: 3083
- `APP_ENDPOINTS`: 53
- `APP_GET`: 15
- `APP_POST`: 37
- `APP_DELETE`: 1
- `APP_PUT`: 0
- `APP_PATCH`: 0

Net reduction:

- Lines removed from `main.py`: 175
- Decorators removed from `main.py`: 6

## Router Created

- `tmp_agent/brain_v9/routes/chat_session_lifecycle_routes.py`

## Routes Moved

- `DELETE /sessions/{session_id}`
- `DELETE /sessions/{session_id}/memory`
- `POST /agent`
- `POST /dev`
- `GET /godmode/status`
- `POST /godmode`

## Provider Boundary

The router does not import `main.py` or `session.py`. Runtime state is passed through:

- `configure_active_sessions_provider(lambda: active_sessions)`
- `configure_chat_runtime_provider(_chat_session_runtime_payload)`

The runtime payload provides:

- active session access
- agent executor getter/setter
- `get_or_create_session`
- canonical agent fastpath
- response summarizer
- GOD task executor
- PAD authenticated session map
- unsafe-dev and safe-mode config flags

## Deferred Routes

- `POST /chat`
  - Reason: primary BrainSession route has large PAD/GOD/chat runtime dependency graph, trace emission, native routing, permission/pending-action handling, and response shaping. Moving it safely needs a dedicated chat-entrypoint front and likely a smaller provider boundary.
- `POST /chat/introspectivo`
  - Reason: paired with `ChatRequest`/`ChatResponse` and introspective orchestrator flow.
- `GET /chat/introspectivo/debug`
  - Reason: debug shell remains coupled to introspective orchestrator helper.

## Tests Run

- `python -m py_compile tmp_agent/brain_v9/main.py`
- `python -m py_compile tmp_agent/brain_v9/routes/chat_session_lifecycle_routes.py`
- `python -m py_compile tests/contract/test_main_routes_chat_session_lifecycle_split_15a.py`
- `python tests/contract/test_main_routes_chat_session_lifecycle_split_15a.py`
- `python tests/contract/test_main_routes_readonly_extra_split_13f.py`
- `python tests/contract/test_main_routes_readonly_diagnostics_split_13e.py`
- `python tests/contract/test_main_routes_validators_observability_split_13d.py`
- `python tests/contract/test_main_routes_health_status_deferred_split_13c.py`
- `python tests/contract/test_main_routes_startup_state_adapter_13b.py`
- `python tests/contract/test_main_routes_health_status_split_13a.py`
- `python tests/contract/test_main_routes_curated_knowledge_split_14a.py`
- `python tests/contract/test_main_routes_gate_tool_split_14b.py`
- `python tests/contract/test_main_routes_dashboard_shell_split_14c.py`
- `python tests/contract/test_main_routes_dev_debug_split_14e.py`
- `python tests/contract/test_main_routes_memory_semantic_split_14b.py`
- `python tests/contract/test_main_routes_governance_control_split_14c.py`
- `python tests/contract/test_main_routes_trace_streaming_split_14d.py`
- `python tests/contract/test_main_routes_provider_readonly_split_14e.py`
- `python tests/contract/test_main_routes_strategy_readonly_split_14f.py`
- `python tests/contract/test_main_routes_remaining_control_split_14h.py`
- `python tests/contract/test_main_router_topology_contract_12b.py`
- `python tests/contract/test_main_router_dev_surface_guard_12c.py`
- `python tests/contract/test_main_router_surface_matrix_12d.py`
- `python tests/contract/test_main_router_auth_permission_contract_12e.py`
- `python tests/contract/test_main_router_side_effect_boundary_12f.py`
- `python tests/unit/test_ollama_config_session_message_11d_c.py`
- `python tests/unit/test_ollama_config_centralization_11d_b.py`
- `python tests/integration/test_autonomy_e2e_memory_tool_fallback_11c.py`
- `python tests/unit/test_scvl_final_answer_gate_01.py`
- `python tests/unit/test_scvl_semantic_promotion_gate_01.py`

All validation passed.

## Failures / Reverts

- No block reverted.
- Contract drift fixed:
  - 12B/12C/12D/12F now classify session delete routes in `chat_session_lifecycle_routes.py`.
  - 14C now classifies `godmode` as moved to `chat_session_lifecycle_routes.py`.

## Files Touched

- `tmp_agent/brain_v9/main.py`
- `tmp_agent/brain_v9/routes/chat_session_lifecycle_routes.py`
- `tests/contract/test_main_routes_chat_session_lifecycle_split_15a.py`
- `tests/contract/test_main_router_topology_contract_12b.py`
- `tests/contract/test_main_router_surface_matrix_12d.py`
- `tests/contract/test_main_router_dev_surface_guard_12c.py`
- `tests/contract/test_main_router_side_effect_boundary_12f.py`
- `tests/contract/test_main_routes_governance_control_split_14c.py`
- `.github/workflows/brain-agent-v2-hygiene.yml`
- `.github/workflows/nontrading-smoke-regression.yml`
- `docs/audit/MAIN_ROUTER_SESSION_LIFECYCLE_REPORT_15A.md`

## No-Touch Confirmation

Confirmed not modified:

- `tmp_agent/brain_v9/core/session.py`
- `tmp_agent/brain_v9/core/session_agent_route.py`
- `tmp_agent/brain_v9/core/session_scvl_gate.py`
- `tmp_agent/brain_v9/core/scvl_promotion_gate.py`
- `tmp_agent/brain_v9/core/semantic_memory_faiss.py`
- `memory/semantic/*`
- FAISS files
- `tmp_agent/state/*`
- trading/risk/IBKR/QC internals
- SCVL internals
- runtime ledgers/journals/snapshots

## Push Recommendation

No push performed. Push can be authorized after operator review.

## Next Front

Recommended next front:

`FRONT-BRAIN-MAIN-ROUTER-CHAT-ENTRYPOINT-15B`

Scope should focus only on `POST /chat` and the introspective chat routes, with explicit dependency budget and runtime provider design before patching.
