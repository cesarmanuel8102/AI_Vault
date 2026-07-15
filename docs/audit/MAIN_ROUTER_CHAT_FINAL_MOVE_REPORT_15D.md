# FRONT-BRAIN-MAIN-ROUTER-CHAT-FINAL-MOVE-15D

Status: `PARTIALLY_COMPLETED_WITH_DEFERRED`

## Decision

`POST /chat` was not moved in 15D. The dependency count still exceeds provider budget, so the safe result is another small helper extraction and explicit deferral to 15E.

## Baseline

- Initial HEAD: `d62c402`
- Initial origin: `d62c402`
- Initial `main.py` lines: `2897`
- Initial app endpoint count: `51`
- Initial `POST /chat` block lines: `454`
- Backup branch: `backup/main-chat-final-move-pre-15d-d62c402`

## Coupling Inventory

Dependency count before: `26`

Concrete direct dependencies still used by `POST /chat` before 15D helper extraction:

- `ChatRequest`
- `ChatResponse`
- `_trivial_chat_fastpath`
- `_looks_like_curated_learning_probe`
- `answer_chat_probe`
- `_format_curated_probe_response`
- `_pad_authenticated_sessions`
- `BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS`
- `datetime`
- `_execute_god_chat_task`
- `json`
- `_pad_audit`
- `sys`
- `re`
- `log`
- `looks_like_harmful_intrusion_request`
- `should_attempt_local_network_tool`
- `detect_local_network`
- `scan_local_network`
- `_emit_agent_trace_internal`
- `asyncio`
- `handle_user_message`
- `active_sessions`
- `has_pending_action_signal`
- `extract_pending_action_from_text`
- `traceback`

Provider key count: `not applicable`

Reason: moving this endpoint now would require a provider boundary larger than `18` keys or a bulk move of PAD/GOD/native runtime behavior. That would violate the controlled final-move rule.

## 15D Helper Extraction

Extracted more pure deterministic PAD/GOD helpers into `tmp_agent/brain_v9/core/chat_runtime_helpers.py`:

- `is_safe_god_existence_question`
- `is_explicit_god_task`
- `extract_god_task_text`
- `parse_pad_credentials`

These helpers preserve behavior and do not import runtime session, memory, FAISS, trading, HTTP clients, subprocess, uvicorn, or order execution code.

Dependency count after: `24`

The route still depends on PAD/GOD state, trace emission, native runtime, network tools, curated fastpaths, and response shaping. The final move is deferred to 15E.

## Metrics

- `POST /chat` moved: `false`
- Endpoint count before: `51`
- Endpoint count after: `51`
- `main.py` line count before: `2897`
- `main.py` line count after: `2851`
- `POST /chat` block lines before: `454`
- `POST /chat` block lines after: `404`

## Validation Plan Executed

- `python -m py_compile tmp_agent/brain_v9/main.py`
- `python -m py_compile tmp_agent/brain_v9/routes/chat_entrypoint_routes.py`
- `python -m py_compile tmp_agent/brain_v9/core/chat_runtime_helpers.py`
- `python -m py_compile tests/contract/test_main_routes_chat_final_move_15d.py`
- `python tests/contract/test_main_routes_chat_final_move_15d.py`
- `python -m pytest tests/contract/test_main_routes_chat_final_move_15d.py -q`
- 15C/15B/15A and router split regressions
- nontrading focused block with 15D included
- Targeted 15C/15D pytest: `20 passed`
- Focused nontrading block with 15D: `212 passed, 3 skipped`
- P0 nontrading security smoke: `19 passed`

## No-Touch Confirmation

15D did not modify:

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

Recommended next front: `FRONT-BRAIN-MAIN-ROUTER-CHAT-SERVICE-BOUNDARY-15E`

15E should extract a service-level `handle_chat(req, runtime)` boundary first, reducing provider keys below `18`; then move the router wrapper.
