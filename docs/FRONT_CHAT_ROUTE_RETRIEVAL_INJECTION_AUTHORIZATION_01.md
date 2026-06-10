# FRONT-CHAT-ROUTE-RETRIEVAL-INJECTION-AUTHORIZATION-01

## Status
✅ COMPLETE

## Objective
Prepare a controlled authorization request for injecting FAISS retrieval context into the `/chat` route. This front is planning-only: no protected files are modified.

## Prior State
- `/chat` responds normally (CHAT_ROUTE_OK)
- Direct FAISS retrieval works (15/15 top-1)
- Live chat probes show no learned memory markers
- `protected_runtime_change_required`: true

## Why This Is Authorization-Only
Modifying `session.py` (the chat LLM routing) is a protected runtime change. Per governance rules, any change to `session.py`, `main.py`, or `execution_gate.py` requires explicit user authorization. This front produces the authorization package without applying the patch.

## Current /chat Flow
```
main.py:1377  @app.post("/chat")
main.py:1745   asyncio.wait_for(session.chat(), timeout=30)
session.py:341 session.chat()
session.py:951  _route_to_llm(msg_stripped, intent, history, model_priority)
session.py:2275 _route_to_llm() builds system prompt + calls llm.query()
llm.py:773      _ollama() POST to Ollama (per-model timeout 60-90s)
```

## Direct Retrieval Proof Summary
All 3 controlled batch records retrieved as top-1 via FAISS:
- controlled_batch_01_real_execution_policy: rank=1, score=0.7538
- controlled_batch_01_runtime_recovery_runbook: rank=1, score=0.7091
- controlled_batch_01_memory_faiss_canary_doc: rank=1, score=0.7243

## Live Chat Probe Result Summary
- 3/3 probes responded successfully (no timeout)
- 0/3 probes showed learned memory markers
- Conclusion: `/chat` does not currently inject retrieval context

## Proposed Insertion Point
- **File**: `tmp_agent/brain_v9/core/session.py`
- **Function**: `_route_to_llm()`
- **Line**: ~2280 (immediately after entering the function)
- **Action**: Query FAISS for relevant context and compact it into a context string before building the system prompt.
- **Protected file**: Yes

## Protected Files Requiring Authorization
| File | Reason | Risk | Optional |
|---|---|---|---|
| `tmp_agent/brain_v9/core/session.py` | Retrieval context must be injected before system prompt build | Medium | No |
| `tmp_agent/brain_v9/core/llm.py` | May need timeout adjustment for embedding call | Low | Yes |
| `tmp_agent/brain_v9/main.py` | May need asyncio envelope adjustment | Low | Yes |

## Retrieval Injection Contract
| Parameter | Value |
|---|---|
| read_only_memory | true |
| read_only_faiss | true |
| max_retrieval_hits | 3 |
| max_context_chars | 2500 |
| retrieval_summary_only | true |
| no_raw_cot | true |
| timeout_budget_s | 20 |
| fallback_if_retrieval_fails | true |
| no_trading | true |
| no_b8 | true |
| no_connectors | true |
| no_external_network | true |

## Future Patch Plan
If authorized, the next front (`FRONT-CHAT-ROUTE-RETRIEVAL-INJECTION-PATCH-01`) will:
1. Add opt-in trigger detection in `session.py`
2. Call `get_semantic_memory_faiss().search()` with top_k=3
3. Compact hits into ≤2500 char context string
4. Inject context into system prompt or pass as parameter
5. Fallback to no-retrieval on any error
6. Adjust timeouts if needed
7. No modification to memory/semantic/* or FAISS index

## Safety Constraints
- Strict opt-in keywords required before retrieval ("memory", "project knowledge")
- Compact markdown-like context only (no raw JSON dumps)
- Short embedding timeout (5s max)
- Fallback to no-retrieval on any error
- Rollback: revert session.py changes only; no data mutation

## Tests Result
- py_compile: PASS
- smoke tests: **24 passed / 0 failed**

## Files Created
- `brain/chat_retrieval_injection_authorization.py` — authorization module
- `tests/smoke/smoke_front_chat_retrieval_injection_authorization_01.py` — 24 tests
- `docs/FRONT_CHAT_ROUTE_RETRIEVAL_INJECTION_AUTHORIZATION_01.md` — this document

## Immutability Proof
- memory_line_count: 1710 (unchanged)
- faiss_ids_count: 1611 (unchanged)
- No protected files modified

## Final Status
**AUTHORIZATION_REQUIRED**

## Next Recommended Front
`FRONT-CHAT-ROUTE-RETRIEVAL-INJECTION-PATCH-01`
- Only if user explicitly authorizes modification of `tmp_agent/brain_v9/core/session.py`

If denied:
`FRONT-CHAT-GROUNDED-RESPONSE-EVAL-WITHOUT-INJECTION-01`
