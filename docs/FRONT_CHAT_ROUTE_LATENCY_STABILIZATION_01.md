# FRONT-CHAT-ROUTE-LATENCY-STABILIZATION-01

## Status
✅ COMPLETE

## Objective
Diagnose and stabilize the `/chat` route latency after previous timeout symptoms. Establish diagnosis tooling, latency policies, and a stabilization module without modifying protected files.

## Prior Problem
In `FRONT-BRAIN-LEARNING-VERIFICATION-CHAT-AND-DIRECT-01`, direct memory/FAISS/API verification passed, but the conversational `/chat` route reported partial availability (`PARTIAL_CHAT_NOT_AVAILABLE_DIRECT_VERIFIED`). This front investigates whether the root cause was a transient timeout or a structural latency issue.

## Discovery Result
- **File**: `tmp_agent/brain_v9/main.py`
- **Route**: `@app.post("/chat", response_model=ChatResponse)` at line 1377
- **Handler**: `async def chat(req: ChatRequest)` at line 1378
- **Flow**: `main.py` → `session.chat()` in `session.py` → `_route_to_llm()` → `llm.query()` → `aiohttp POST` to Ollama
- **Timeout layers**:
  - Main envelope: 30s (`asyncio.wait_for` in `main.py`)
  - LLM envelope: 12s (`asyncio.wait_for` in `session.py` `_route_to_llm()`)
  - Per-model timeout: 60s–90s in `llm.py`
- **Memory/FAISS search**: Not triggered by `/chat` in standard path. Short-term conversation history is loaded from JSON files, not FAISS.
- **Protected files involved**: `session.py`, `main.py`, `llm.py` (no changes made)

## Service Health Result
- **Port 8090**: Active, healthy, `/chat` route mounted in OpenAPI
- **Port 8010/8000**: Down
- **Live `/chat` test**: Responded successfully within 15s timeout
- **Classification**: `CHAT_ROUTE_OK`

## Diagnosis Classification
`CHAT_ROUTE_OK`

- `service_running`: true
- `chat_route_found`: true
- `chat_route_ok`: true
- `timeout_detected`: false
- `protected_runtime_change_required`: false

## Code Fix Applied
No protected runtime files were modified.

The stabilization is **policy-only**:
- `brain/chat_route_latency_diagnostic.py` — read-only diagnostic tool
- `brain/chat_route_latency_stabilization.py` — latency policy and compact-context builder

These modules can be imported by authorized runtime patches later without touching protected files now.

## Latency Policy
| Parameter | Value |
|---|---|
| max_prompt_chars | 2000 |
| max_context_chars | 4000 |
| max_model_timeout_s | 12 |
| max_envelope_timeout_s | 30 |
| fallback_response_on_timeout | "The request timed out due to high load. Please try again..." |
| retrieval_summary_only | true |
| no_raw_cot | true |
| stream | false |

## No Chain-of-Thought Exposure Guarantee
- `no_raw_cot` enforced in all payloads
- Fallback response never includes internal reasoning

## Immutability Proof
- memory_line_count: 1710 (unchanged)
- faiss_ids_count: 1611 (unchanged)
- semantic_memory.jsonl SHA unchanged
- semantic_memory_faiss.index SHA unchanged
- semantic_memory_faiss_ids.json SHA unchanged
- No protected files modified

## Tests Result
- py_compile: PASS
- smoke tests: **24 passed / 0 failed**

## Files Created
- `brain/chat_route_latency_diagnostic.py` — diagnostic module
- `brain/chat_route_latency_stabilization.py` — stabilization policy module
- `tests/smoke/smoke_front_chat_route_latency_stabilization_01.py` — 24 tests
- `docs/FRONT_CHAT_ROUTE_LATENCY_STABILIZATION_01.md` — this document

## Limitations
- If future `/chat` timeouts recur, protected files (`session.py`, `main.py`, `llm.py`) will need authorized changes.
- Policy module does not mount routes or alter runtime behavior by itself.
- Live test succeeded at runtime; intermittent latency spikes may require deeper profiling (Ollama load, model warm-up).

## Next Recommended Front
`FRONT-CHAT-ROUTE-LEARNING-RETRIEVAL-INTEGRATION-VERIFY-01`
- Verify that controlled batch retrieval results can be injected into chat context without timeout increase.
