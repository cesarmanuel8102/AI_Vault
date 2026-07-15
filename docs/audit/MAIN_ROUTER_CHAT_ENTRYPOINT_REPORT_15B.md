# MAIN ROUTER CHAT ENTRYPOINT REPORT 15B

status: PARTIALLY_COMPLETED_WITH_DEFERRED

## Baseline

- HEAD initial: 7b8f591
- Branch: codex/own-capital-sustainable-return
- Scope: FRONT-BRAIN-MAIN-ROUTER-CHAT-ENTRYPOINT-15B
- Push: not performed

## Routes moved

- GET /chat/introspectivo/debug
- POST /chat/introspectivo

Moved to:

- tmp_agent/brain_v9/routes/chat_entrypoint_routes.py

## Routes deferred

- POST /chat

Reason:
POST /chat remains in main.py because it exceeds the dependency budget and owns PAD/GOD, native routing, trace emission, curated fastpath, network tools, harmful-intrusion guard, pending permission extraction, response shaping, timeout handling, and model/native fallback semantics. Moving it safely would require a large provider and would risk behavior drift.

## Dependency budget

- provider dependency count for moved introspective routes: 3
  - active_sessions
  - get_or_create_session
  - system_identity
- POST /chat dependency count: 27

POST /chat dependency inventory:

1. ChatRequest
2. ChatResponse
3. _trivial_chat_fastpath
4. _looks_like_curated_learning_probe
5. answer_chat_probe
6. _format_curated_probe_response
7. _pad_authenticated_sessions
8. BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS
9. get_gate
10. _execute_god_chat_task
11. _pad_audit
12. protocolo_autenticacion_desarrollador import path
13. datetime
14. json
15. traceback
16. harmful intrusion guard keywords
17. brain_v9.agent.tools.detect_local_network
18. brain_v9.agent.tools.scan_local_network
19. _emit_agent_trace_internal
20. asyncio.wait_for
21. handle_user_message
22. active_sessions
23. native_chat context source
24. timeout error handling
25. pending_action regex extraction
26. tool trace emission
27. final ChatResponse extension fields

Decision:
POST /chat deferred until a dedicated chat-runtime extraction front can split PAD/GOD, network fastpaths, trace emission, and pending-action shaping into smaller helpers without touching session.py internals.

## main.py metrics

Before:

- lines: 3083
- app endpoints: 53
- app.get: 15
- app.post: 37
- app.delete: 1

After:

- lines: 2918
- app endpoints: 51
- app.get: 14
- app.post: 36
- app.delete: 1

## Behavior preservation

- Introspective response model preserved as ChatResponse shape.
- Introspective request model preserved as ChatRequest shape.
- Orchestrator state extraction preserved.
- Introspective memory save behavior preserved.
- Introspective network auto-execution behavior preserved.
- No session.py internals modified.
- No SCVL internals modified.
- No memory/semantic runtime data modified.
- No FAISS modified.
- No trading/QC/IBKR modified.

## Tests planned/executed

- py_compile main.py
- py_compile chat_entrypoint_routes.py
- py_compile 15B contract
- 15B contract script and pytest
- 15A contract regression
- 13A-13F route contracts
- 14A-14H route contracts
- 12B-12F router contracts
- 11D config tests
- 11C autonomy fallback test
- SCVL final answer and semantic promotion gates
- P0 nontrading security smoke
- nontrading Agent V2 block with 15B contract added

## Failures/reverts

- none at report creation time

## No-touch confirmation

No intended changes to:

- tmp_agent/brain_v9/core/session.py
- tmp_agent/brain_v9/core/session_agent_route.py
- tmp_agent/brain_v9/core/session_scvl_gate.py
- tmp_agent/brain_v9/core/scvl_promotion_gate.py
- tmp_agent/brain_v9/core/semantic_memory_faiss.py
- memory/semantic/*
- FAISS files
- tmp_agent/state/*
- trading/risk/IBKR/QC internals

## Push recommendation

Push only after local validation passes and final commits are created.

## Next front

FRONT-BRAIN-MAIN-ROUTER-CHAT-RUNTIME-DECOMPOSITION-15C
