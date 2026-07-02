# Test Results — FRONT-BRAIN-AGENT-V2-IDENTITY-GUARD-AND-INTENT-FLOOR-WIDEN-02

## Summary

**45 tests, 45 passed, 0 failed, 0 skipped**. No regressions. Duration: ~86s initial run; ~113s post-Phase-3 re-verification. Re-run after the two mid-Phase-3 edits (Fix D reinforcement) confirms zero regression.

- `py_compile` on all **6** modified files + new test: **OK**.
- 11 new tests (this front): **11/11 PASS**.
- 34 regression tests (4 prior fronts): **34/34 PASS**.

## New Test File — This Front

`tests/smoke/test_brain_agent_v2_identity_guard_intent_floor_widen_02.py` — 11/11 PASS

| # | Test | Fix Validated |
|---|------|---------------|
| 1 | `test_p3_donde_debes_buscar_routes_to_brain_evidence` | Fix B — P3 exact prompt |
| 2 | `test_p5_reconcilialo_routes_to_brain_evidence` | Fix B — P5 exact prompt |
| 3 | `test_p15_qua_puedes_hacer_realmente_routes_to_evidence_or_direct` | Fix B — P15 exact prompt |
| 4 | `test_p16_que_pruebas_validan_routes_to_brain_evidence` | Fix B — P16 exact prompt |
| 5 | `test_p7_promueve_automaticamente_is_memory_write` | Fix C — P7 exact prompt |
| 6 | `test_identity_guard_strips_english_claude_disclaimer` | Fix A — EN disclaimer strip |
| 7 | `test_identity_guard_strips_spanish_claude_disclaimer` | Fix A — ES disclaimer strip |
| 8 | `test_identity_guard_no_op_on_clean_answer` | Fix A — no false-positive rewrites |
| 9 | `test_normalize_response_applies_identity_guard_and_stashes_metadata` | Fix A — end-to-end integration |
| 10 | `test_finalizer_success_path_emits_canonical_financial_autonomy_flags` | Fix D — success path |
| 11 | `test_identity_replacement_constants_contain_required_markers` | Fix A — constants sanity |

Exact benchmark prompts (verbatim from `benchmark_plan.json`) used for P3/P5/P7/P15/P16 apples-to-apples with Phase 3 live benchmark.

## Post-Phase-3 Re-Verification

Two mid-Phase-3 edits were added after live smoke revealed a LangGraph state-propagation issue (see `patch_results.md` "Fix D reinforcement"):

1. `langgraph_parity_runtime.py` — defensive re-derivation block in `_translate_graph_state_to_native_run` (~L1770-1774).
2. `api_adapter.py` — explicit `financial_autonomy_flags` pull in `raw_response` (~L279).

All 45 tests were re-run after these edits: **45/45 PASS, 113.10s**. No regression detected. Fix D reinforcement is additionally verified in-band by the Phase 3 smoke probe (`_smoke_probe.py`) which confirms P10 returns a 10-key `financial_autonomy_flags` dict in the response body.

## Regression Tests — Prior Fronts (No Regression)

### `test_brain_agent_v2_intent_floor_identity_preamble_repair_01.py` — 10/10 PASS

**Critical backward-compat assertions preserved by Fix D**:

- `test_langgraph_timeout_financial_autonomy_emits_structured_flags` expects `flags.get("broker_execution_enabled") == "unknown"`, `real_money_enabled == "unknown"`, `live_trading_active == "unknown"`. Preserved by Fix D helper's `reason="timeout"` branch which keeps legacy string values AND adds new canonical False fields side-by-side.
- `test_langgraph_timeout_non_financial_prompt_stays_short_and_direct` expects `"financial_autonomy_flags" not in state` on non-financial-autonomy timeout. Preserved via `_financial_autonomy_flags = None` initialization plus `if _financial_autonomy_flags is not None: _state["financial_autonomy_flags"] = _financial_autonomy_flags` guard. Fix D reinforcement's defensive re-derivation block also respects this: it only re-derives on the success path (`status=completed` with no error), so timeout paths are unaffected.

### `test_brain_agent_v2_self_knowledge_index_v1.py` — 7/7 PASS

Self-knowledge index domains, tool gateway read-only dispatch, planner ordering, classifier routing, langgraph runtime self-knowledge tool execution — all pass. (3 SwigPy warnings unrelated to this front.)

### `test_brain_agent_v2_agentic_benchmark_gap_repair_08f8_r1d.py` — 12/12 PASS

Self-development, financial-autonomy dryrun, trace truthfulness, memory-structure read-only tools, live-trading fail-closed, langgraph architecture evidence, dashboard-queue discrepancy, promotion queue reconciliation, finalizer prompt payload retention, active review count, generic self-knowledge, casual chat direct-assistant — all pass.

### `test_evidence_tool_routing_repair_08f8_r1c.py` — 5/5 PASS

Problem prompt routes to brain_evidence, executes tools, produces evidence finalizer, new evidence tools registered, evidence tools are read-only — all pass.

## Fix Coverage Matrix

| Fix | New-Test Coverage | Regression Coverage | Live-Benchmark Coverage | Total Signal |
|-----|-------------------|---------------------|-------------------------|--------------|
| Fix A (identity guard) | 4 new tests | 1 preamble marker regression | 20 responses, 0 disclaimers | Strong |
| Fix B (evidence policy widen) | 4 new tests (P3/P5/P15/P16) | 4 regression (P3/P5/P15/P16 alt prompts) | P3/P5/P15/P16 all routed to brain_evidence | Strong |
| Fix C (memory_write DiP) | 1 new test (P7 exact prompt) | 1 regression (D1 P7 alt prompt) | P7 live: intent=memory_write, gov=approval_required | Strong |
| Fix D (financial flags success) | 1 new test (success path) | 2 regression (timeout FA legacy dict; non-financial timeout empty) | P10 live: 10-key dict with 6 required flags | Strong |
| Fix D reinforcement (two-part) | Covered by Fix D test + in-band smoke | N/A (defensive only) | P10 live: dict actually surfaces in response body | Strong |

## Warnings (Pre-Existing, Not From This Front)

- `builtin type SwigPyPacked has no __module__ attribute` (x1)
- `builtin type SwigPyObject has no __module__ attribute` (x1)
- `builtin type swigvarlink has no __module__ attribute` (x1)

Source: `test_langgraph_runtime_executes_self_knowledge_tool` triggers import of `faiss` C-extension which emits these warnings. Not introduced by this front.

## Gate: PHASE_2_PASS + PHASE_3_REVERIFY_PASS

- 45/45 tests pass (initial): ✅
- 45/45 tests pass (post-Phase-3 re-verification): ✅
- `py_compile` all 6 modified files: ✅
- Fix A/B/C/D coverage: ✅
- Fix D reinforcement covered by Phase 3 smoke probe: ✅
- No regression in prior-front test files: ✅
- Backward-compat contracts preserved: ✅

**PHASE 2 + PHASE 3 test gates satisfied.**
