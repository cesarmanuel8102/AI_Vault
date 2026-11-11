# Delta/DTE First-Rebound Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Run eight comparable QuantConnect backtests across four delta/DTE contracts and two profit targets.

**Architecture:** Extend the pure contract-selection helpers, then adapt the existing cloud algorithm to subscribe a bounded candidate set and choose by live model delta. Preserve all signal, sizing, cost and exit assumptions.

**Tech Stack:** Python, pytest, QuantConnect LEAN Cloud, LEAN CLI.

**Spec:** `docs/superpowers/specs/2026-10-26-delta-dte-first-rebound-design.md`

## Global Constraints

- No signal or universe changes.
- No stop loss or additional quality filter.
- TP values are exactly 10% and 15%.
- Every result must come from a completed QuantConnect cloud backtest.

## Review Focus

- DTE 0 must never silently substitute a later expiry.
- DTE 7/14 selection must never choose an expired contract.
- Put deltas must be compared by absolute value.
- Contracts without valid quotes or delta must not be selected.
- Effective delta and DTE must be visible in results.

---

### Task 1: Pure expiry and delta selectors

**Files:**
- Modify: `zero_dte_core.py`
- Test: `test_zero_dte_core.py`

- [ ] Add failing tests for exact 0DTE, nearest non-expired expiry and absolute-delta selection.
- [ ] Run focused tests and observe the expected failures.
- [ ] Implement the minimal selectors.
- [ ] Run focused and complete local tests.

### Task 2: QuantConnect integration

**Files:**
- Modify: `Yoel 0DTE First Rebound 20261025/main.py`
- Modify: `Yoel 0DTE First Rebound 20261025/zero_dte_core.py`
- Test: `test_qc_zero_dte_contract.py`

- [ ] Add failing source-contract tests for parameters, bounded subscriptions and recorded effective delta/DTE.
- [ ] Integrate candidate subscriptions and delta-based entry selection.
- [ ] Push and compile the cloud project.

### Task 3: Eight-run matrix and report

**Files:**
- Create: `delta_dte_matrix_manifest.json`
- Create: `INFORME_DELTA_DTE_2026-10-26.md`

- [ ] Run all four variants at TP 10% and 15%.
- [ ] Fetch immutable raw results and calculate comparable statistics.
- [ ] Write a verdict based on expectancy after costs, not hit rate alone.
