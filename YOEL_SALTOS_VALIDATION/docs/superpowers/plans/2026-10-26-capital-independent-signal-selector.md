# Capital-Independent Signal Selector Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and validate a causal entry-quality gate plus ranking that is independent of account capital.

**Architecture:** Pure functions in `zero_dte_core.py` calculate causal features, gate candidates, and rank survivors. The QuantConnect algorithm supplies only pre-entry observations and uses the resulting ordering before position sizing. An offline analysis selects one configuration on 2022-2023, confirms it on 2024, and freezes it before a single 2025-2026 run.

**Tech Stack:** Python, pytest, QuantConnect LEAN cloud backtests, existing IB fee and slippage models.

**Spec:** `docs/superpowers/specs/2026-10-26-capital-independent-signal-selector-design.md`

## Global Constraints

- Signal quality must be independent of cash, equity, premium affordability, and quantity.
- All selector inputs must exist by 10:31 ET.
- Keep delta 0.70, DTE 0, TP 10%, exits, fees, slippage, and intraday closeout unchanged.
- Never select thresholds or weights using 2025-2026 results.

## Review Focus

- Zero-range or missing-history candidates must fail closed without division errors.
- Bullish and bearish features must be direction symmetric.
- Ranking must be deterministic under tied scores.
- Option friction may break ranking ties but may not depend on account size.
- A larger account must accept exactly the same signals as a smaller account before sizing.

---

### Task 1: Pure Causal Selector

**Files:**
- Modify: `zero_dte_core.py`
- Modify: `test_zero_dte_core.py`

**Interfaces:**
- Produces: `causal_quality_score(candidate: dict, weights: dict) -> float`
- Produces: `passes_causal_quality_gate(candidate: dict, thresholds: dict) -> bool`
- Produces: `rank_quality_candidates(candidates: list[dict], weights: dict) -> list[dict]`

- [x] Write failing tests for direction symmetry, fail-closed missing values, deterministic ties, and invariance to cash/equity/quantity.
- [x] Run `python -m pytest test_zero_dte_core.py -q` and verify the new tests fail for missing interfaces.
- [x] Implement the three minimal pure functions.
- [x] Run `python -m pytest test_zero_dte_core.py -q` and verify all tests pass.

### Task 2: Algorithm Integration and Trace

**Files:**
- Modify: `Yoel 0DTE First Rebound 20261025/main.py`
- Modify: `test_qc_zero_dte_contract.py`

**Interfaces:**
- Consumes: Task 1 selector functions.
- Produces: causal candidate fields and runtime statistics for gate/ranking decisions.

- [x] Write failing contract tests proving the algorithm supplies only causal fields and applies selection before quantity calculation.
- [x] Run `python -m pytest test_qc_zero_dte_contract.py -q` and verify failure.
- [x] Add parameterized selector mode, thresholds, causal feature capture, and trace statistics.
- [x] Run focused tests, then `python -m pytest -q`.

### Task 3: Discovery and Freeze

**Files:**
- Create: `analyze_causal_signal_selector.py`
- Create: `test_analyze_causal_signal_selector.py`
- Create: `causal_signal_selector_manifest.json`

**Interfaces:**
- Produces: one immutable selector configuration chosen on 2022-2023 and confirmed on 2024.

- [x] Write failing tests for period separation, deterministic selection, minimum trade count, and rejection of configurations with PF at or below 1.
- [x] Implement the analysis and manifest writer.
- [x] Generate or fetch trace evidence for 2022-2024, select candidates without inspecting 2025-2026, and freeze one or declare no viable selector.
- [x] Verify the manifest hashes its inputs and records every tested configuration.

### Task 4: Frozen QuantConnect Validation

**Files:**
- Create: `INFORME_SELECTOR_CAUSAL_2026-10-26.md`
- Add: frozen raw QuantConnect result JSON files.

**Interfaces:**
- Consumes: frozen manifest from Task 3.
- Produces: control-vs-selector results for 2022-2024 and 2025-2026.

- [x] Run identical-capital control and filtered backtests for discovery/confirmation.
- [x] If 2024 is positive, run exactly one frozen 2025-2026 validation.
- [x] Reconcile metrics and verify no parameter drift between runs.
- [x] Run `python -m pytest -q` and `git diff --check -- YOEL_SALTOS_VALIDATION`.
- [x] Report GO only if both prescribed periods are net positive with PF above 1; otherwise report NO-GO and the causal failure.

