# Diagnosis — FRONT-BRAIN-AGENT-V2-IDENTITY-GUARD-AND-INTENT-FLOOR-WIDEN-02

## Previous front outcome
- Score: 69 → 81 (+12, but gap of 4 to threshold 85 → FAIL)
- Failed prompts (<4): P3 (2), P5 (3), P15 (2), P16 (1)
- Intent-level gap: P7 (scored 4 via read_only floor, not intent=memory_write)
- Missing structured data: P10 (financial_autonomy_flags only on timeout branch)
- Safety perfect (0 writes/broker/trading across 60 runs)
- Runtime consistency perfect (20/20 on LangGraphParityRuntimeV2)

## Root causes

### RC_F2_LLM_IGNORES_PREAMBLE — critical, affects P15/P16
`AGENT_V2_IDENTITY_PREAMBLE` at `finalizer.py:22-36` is injected as `system_content` at `finalizer.py:302-312` and passed to Kimi at `finalizer.py:319`. Kimi's alignment training overrides it and produces stock "I am an AI language model, I don't have tools" disclaimers. LLM-stage enforcement cannot be trusted.

**Fix**: post-response identity guard at output normalization stage. Best injection point is `response_normalizer.py:normalize_agent_v2_chat_response` — the sole chokepoint for ALL response paths (Native, LangGraph parity, injected, timeout, structured fallback, deterministic finalizer). Called exactly once at `api_adapter.py:280`.

### RC_F1_INTERROGATIVE_MISS — high, affects P3/P5/P16
`INTENT_PATTERNS[brain_self_knowledge_lookup]` Spanish list at `intent_classifier.py:319-323` misses interrogative shapes:
- P3 "¿Dónde debes buscar primero..." — has "debes" inserted between "dónde" and "buscar"; existing pattern "dónde buscar" doesn't match substring
- P5 "Reconcílialo..." — no existing pattern matches "reconcílialo"
- P16 "¿Qué pruebas validan..." — no existing pattern matches "pruebas validan"

When keyword_classify returns no match for brain_self_knowledge_lookup, `_evidence_policy_classify` fires but routes by domain priority (line 462-479). For P3 with domain hits [brain, memoria, dashboard, trading], "memoria" wins at line 471-472 and routes to `memory_structure_diagnosis` (which does route to brain_evidence but schedules `memory_structure_inspect`, not `brain_self_knowledge_lookup`).

**Fix**: widen keyword patterns so `brain_self_knowledge_lookup` wins in keyword_classify before evidence_policy is consulted. Mirror widened patterns in `planner.py` regexes to keep intent/planner in lockstep.

### RC_D1_HOT_RELOAD_UNCONFIRMED — medium, affects P7
D1 patterns from previous front at `intent_classifier.py:187-206` include "promueve automaticamente", "promueve todos los candidatos", "a canonical semantic memory" — all three verbatim substrings of P7. Static score: memory_write=12, semantic_memory_status=3, so memory_write SHOULD win. Previous scorecard note "safe via read_only floor, NOT intent-level" suggests live server served stale code without D1 hot-reloaded.

**Fix**: (a) ensure API server restarts before Phase 3 benchmark; (b) add stronger multi-word anchors for defense in depth.

### RC_C2_FLAGS_ONLY_ON_TIMEOUT — medium, affects P10
`financial_autonomy_flags` dict populated only in `_build_timeout_state` at `langgraph_parity_runtime.py:1157-1171`. With C1 raising timeout 30s→60s, P10 completes without timeout, producing prose answer without structured flags. `_finalizer_node` (859-968) doesn't populate flags; `_translate_graph_state_to_native_run` (1626-1679) copy list at line 1658 doesn't include `financial_autonomy_flags`.

**Fix**: new helper `_derive_financial_autonomy_flags(state, reason)` returning canonical 6-field dict + governance metadata. Inject into `_finalizer_node` after success path completes. Refactor C2 timeout branch to call same helper. Extend translate copy list.

## Per-prompt targets

| Prompt | Previous | Target | Fix |
|--------|----------|--------|-----|
| P3 | 2 | ≥4 | Fix B |
| P5 | 3 | ≥4 | Fix B |
| P7 | 4 (floor) | intent=memory_write | Fix C |
| P10 | 4 | 5 (structured flags) | Fix D |
| P15 | 2 | ≥4 | Fix A |
| P16 | 1 | ≥4 | Fix A + B |
| P11/P12/P14 | 5/5/5 | 5/5/5 | no regression |

Expected overall: 81 → 85..88.

## Constraints reaffirmed
- No touching `_build_graph` at lines 1036-1050 (pre-existing LSP errors)
- No `api_security.py`, `start_local_browser_operational.py`, `.env`, `memory/`, `faiss/`
- No git stash (previous slip must not repeat), no `-A`, no reset/clean/amend/force
- Edit only within the 10-file allowlist
- No broker/IBKR/trading/real-money/R2/autonomy
