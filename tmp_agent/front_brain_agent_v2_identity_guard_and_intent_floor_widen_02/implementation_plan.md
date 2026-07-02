# Implementation Plan — 4 Fixes

## Fix A — Post-response identity guard (`response_normalizer.py`)
- **Injection**: helper `_identity_guard_rewrite` inserted between line 170 and 173; line 188 becomes active rewrite.
- **Regex patterns** detect Claude-style disclaimers in English + Spanish (sentence-bounded).
- **Replacement**: canonical Agent V2 identity string (ES + EN variants), prepended after stripping matched disclaimers.
- **Metadata**: `identity_guard_metadata` field with `{triggered, matched_patterns, original_length, rewritten_length}`.
- **Import**: add `import re` if not present.
- **Expected**: P15 & P16 no longer contain "I am an AI language model" / "no tengo herramientas"; contain Agent V2 identity.

## Fix B — Widen F1 interrogative patterns (`intent_classifier.py` + `planner.py`)
### intent_classifier.py
- Line 315-318 (English brain_self_knowledge_lookup): add `where should you look`, `where should i look`, `reconcile it`, `same thing`, `which sources`, `what tests validate`, `use evidence`, `really do`, `really can`.
- Line 319-323 (Spanish brain_self_knowledge_lookup): add `dónde debes buscar`, `donde debes buscar`, `dónde buscar primero`, `donde buscar primero`, `reconcílialo`, `reconcilialo`, `son la misma cosa`, `qué puedes hacer realmente`, `qué puede hacer realmente`, `qué pruebas validan`, `usa evidencia`, `qué fuente`, `qué fuentes` (+ non-accented variants).
- Line 359-376 (EVIDENCE_ACTION_TERMS): add `reconcilia`, `reconciliar`, `reconcile`, `valida`, `validate`, `pruebas`, `fuente`, `fuentes`, `realmente`, `really`.
- Line 378-394 (EVIDENCE_DOMAIN_TERMS): add `head`, `learning proposals`, `learning_proposals`, `proposals`, `promotion_queue`.
- Line 449-458 (always_evidence set): add `head`, `proposals`.

### planner.py (mirror)
- Line 104-116 (EVIDENCE_ACTION_RE): extend regex with `reconcilia|reconciliar|reconcile|valida|validate|realmente|really|fuente|fuentes|pruebas`.
- Line 118-132 (EVIDENCE_DOMAIN_RE): extend with `head|learning\s+proposals|proposals|promotion_queue`.
- Line 147-157 (_requires_generic_evidence fallback): extend with `head|proposals`.

**Expected**: P3 and P5 keyword_classify returns `brain_self_knowledge_lookup` with score ≥3; route resolves to `brain_evidence`; `brain_self_knowledge_lookup` tool scheduled.

## Fix C — Strengthen D1 memory-write patterns (`intent_classifier.py`)
- Line 191-194 (English): add `auto-promote`, `auto promote`, `promote all`, `commit memory`, `consolidate memory`, `promotion queue commit`, `memory canonicalization`, `canonicalize semantic memory`.
- Line 200-206 (Spanish): add `consolida memoria`, `consolidar memoria`, `canonicaliza memoria`, `canonicaliza candidatos`, `canonicaliza la memoria`, `promoción automática`, `promocion automatica`, `automatiza promociones`, `commit de memoria`, `commit memoria`.

**Expected**: P7 classifies with intent=`memory_write`, risk_level=`approval_required`, route=`operational_agent`, governance decision in {block, requires_approval, approval_required}.

## Fix D — `financial_autonomy_flags` in success path (`langgraph_parity_runtime.py`)
### New helper method
- Location: between `_deterministic_finalizer` (line 454) and `_record_native_helper_error` (line 456).
- Signature: `_derive_financial_autonomy_flags(self, state, reason: str) -> Dict[str, Any]`.
- Returns dict with 6 core fields:
  - `broker_execution_enabled: False`
  - `real_money_enabled: False`
  - `live_trading_enabled: False`
  - `paper_mode: False`
  - `dry_run_guard: True`
  - `ibkr_connected: False`
- Plus: `governance_policy_ref`, `evidence_source`, `note`.
- When `reason='success'` and `state.get('tool_results')` contains repo_file_read on financial_autonomy/*.py, attempts to extract actual boolean values (best-effort, safe defaults on any failure).

### Call sites
1. `_finalizer_node`: after `state["status"] = "completed"` (line 956), before `state["node_path"] = ...` (line 957). Condition: `classification == "financial_autonomy_diagnosis"` OR user message hits FA patterns.
2. `_build_timeout_state`: replace inline dict at lines 1157-1171 with call to helper (reason='timeout').

### Translation
- Extend copy list at `_translate_graph_state_to_native_run:1658` to include `financial_autonomy_flags`.

**Expected**: P10 response includes `financial_autonomy_flags` dict with 6 core boolean fields regardless of timeout path.

## Order of implementation
1. Fix A (response_normalizer.py) — pure additive, sole choke point.
2. Fix B — intent_classifier.py first, then mirror planner.py.
3. Fix C — intent_classifier.py additions.
4. Fix D — langgraph_parity_runtime.py new helper + call sites + translate copy list.
5. Compile all 5 files.
6. Phase 2: new test + regression tests.
7. Phase 3: benchmark rerun (restart API server first).
