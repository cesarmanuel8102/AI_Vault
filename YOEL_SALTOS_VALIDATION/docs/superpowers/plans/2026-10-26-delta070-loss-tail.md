# Delta 0.70 Loss-Tail Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Test a single causal exit for failed 0DTE continuation without altering entries.

**Architecture:** Add pure economics and dual-condition helpers, expose one boolean requiring adverse underlying movement, and reuse the existing failure checkpoint parameters. Execute frozen 2025, 2026 and combined cloud runs.

**Tech Stack:** Python, pytest, QuantConnect LEAN Cloud.

**Spec:** `docs/superpowers/specs/2026-10-26-delta070-loss-tail-design.md`

## Global Constraints

- Contract is delta 0.70, DTE 0; TP is 10%.
- Countermeasure checkpoint is 15 minutes and threshold is -40%.
- No entry filter, ordinary stop or universe change.
- 2026 parameters cannot be changed after observing its result.

## Review Focus

- Both premium loss and adverse underlying movement must be required.
- Directional return must work symmetrically for calls and puts.
- TP must be evaluated before the failure exit.
- Entry time, not signal time, starts the 15-minute clock.
- Disabled parameters must reproduce the control.

---

### Task 1: Pure causal predicate

**Files:**
- Modify: `zero_dte_core.py`
- Test: `test_zero_dte_core.py`

- [x] Add a failing test for the dual condition and direction symmetry.
- [x] Implement the minimal predicate and run the full suite.

### Task 2: Algorithm integration

**Files:**
- Modify: `Yoel 0DTE First Rebound 20261025/main.py`
- Modify: `Yoel 0DTE First Rebound 20261025/zero_dte_core.py`
- Test: `test_qc_zero_dte_contract.py`

- [x] Add a failing source-contract test.
- [x] Integrate the predicate after TP evaluation.
- [x] Reject entries whose estimated roundtrip friction exceeds TP and count them.
- [x] Compile in QuantConnect.

### Task 3: Frozen validation

**Files:**
- Create: `delta070_loss_tail_manifest.json`
- Create: `INFORME_DELTA070_COLA_PERDIDAS_2026-10-26.md`

- [x] Run 2025 discovery, 2026 validation and combined confirmation.
- [x] Fetch raw results and compare against controls.
- [x] Report whether the rule is profitable, merely protective, or rejected.
