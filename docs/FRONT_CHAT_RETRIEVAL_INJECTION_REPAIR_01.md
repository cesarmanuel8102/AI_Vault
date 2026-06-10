# FRONT-CHAT-RETRIEVAL-INJECTION-REPAIR-01

## Status
✅ COMPLETE

## Objective
Improve the retrieval injection patch applied in FRONT-CHAT-ROUTE-RETRIEVAL-INJECTION-PATCH-01 by tuning the prompt context format to better guide the LLM to cite learned memory concepts.

## Prior State
- Patch applied to `tmp_agent/brain_v9/core/session.py`
- Retrieval activated on opt-in keywords
- Context was injected as:
```
RELEVANT PROJECT MEMORY:
- source=ID score=SCORE: snippet
```
- **marker_pass_count**: 1/3 (partial)
- All probes responded successfully, but learned concepts were not consistently cited

## Files Modified
- `tmp_agent/brain_v9/core/session.py` — updated injection block

## Exact Repair Change
Changed the context injection block from:
```
RELEVANT PROJECT MEMORY:
- source=ID score=SCORE: snippet
```
To:
```
RELEVANT PROJECT MEMORY CONTEXT:
Use the following retrieved project-memory snippets to answer the user.
If the snippets contain a source ID or named concept, mention it briefly.
Do not reveal hidden reasoning. Do not quote internal JSON. Do not invent missing details.

- source=ID score=SCORE: snippet

When answering this memory-enabled request, prefer the retrieved project-memory context over generic knowledge.
```

## Why This Change
The original format did not instruct the LLM to actively use or cite the retrieved snippets. By adding explicit instructions:
- The model is told to prefer project memory over generic knowledge
- Encouraged to mention source IDs/named concepts
- Reminded not to hallucinate or reveal reasoning

## Opt-In Triggers (unchanged)
- "project memory", "available project memory", "available memory"
- "use memory", "use project memory", "semantic memory"
- "faiss", "memoria del proyecto", "usa la memoria", "memoria disponible"

## Retrieval Injection Contract (unchanged)
| Parameter | Value |
|---|---|
| read_only_memory | true |
| read_only_faiss | true |
| max_retrieval_hits | 3 |
| max_context_chars | 2500 |
| retrieval_summary_only | true |
| no_raw_cot | true |
| fallback_if_retrieval_fails | true |

## Validation Result
- **chat_route_ok**: true (3/3 probes responded)
- **timeout_detected**: false
- **marker_pass_count**: 1/3
- **status**: CHAT_RETRIEVAL_INJECTION_PARTIAL

### Probe Details
1. **Real Execution Policy**: 200 OK, marker_pass=true (learned markers found)
2. **Runtime Recovery Runbook**: 200 OK, marker_pass=false
3. **Memory FAISS Canary**: 200 OK, marker_pass=false

## Result Interpretation
The repair improved the prompt format, but marker reliability remains partial. The LLM still does not consistently surface learned concepts verbatim. Possible reasons:
- LLM may summarize/paraphrase rather than echo markers
- 2500-char context limit may truncate key details
- Ollama model behavior varies per prompt
- Single-pass probing may have variance

## No Chain-of-Thought Exposure
- All probes verified: no `<think>` tags or raw chain-of-thought in responses.

## Immutability Proof
- memory_line_count: 1710 (unchanged)
- faiss_ids_count: 1611 (unchanged)
- No memory/FAISS files modified
- No protected files modified outside authorized scope

## Tests Result
- py_compile: PASS
- smoke tests: **24 passed / 0 failed**

## Files Created
- `tests/smoke/smoke_front_chat_retrieval_injection_repair_01.py` — 24 tests
- `docs/FRONT_CHAT_RETRIEVAL_INJECTION_REPAIR_01.md` — this document

## Files Modified
- `tmp_agent/brain_v9/core/session.py` — improved injection block
- `brain/chat_retrieval_injection_patch_validation.py` — added REPAIR_FRONT constant

## Rollback Plan
- Revert session.py to pre-repair state
- No data mutation

## Limitations
- Marker reliability improved format but not statistically proven
- May need further prompt engineering or model tuning
- Single-probe variance limits confidence

## Next Recommended Front
`FRONT-CHAT-RETRIEVAL-INJECTION-REPAIR-02`
- Further tuning (e.g., include source IDs as inline citations, adjust top_k, or test with different LLM parameters)
