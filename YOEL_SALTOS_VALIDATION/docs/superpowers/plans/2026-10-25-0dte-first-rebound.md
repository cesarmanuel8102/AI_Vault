# 0DTE First-Rebound Variants Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compare ATM and nearest-OTM 0DTE long options using the frozen first-rebound signal in 2025 through October 25, 2026.

**Architecture:** A new QuantConnect project reuses the pure signal helper but owns its 0DTE contract selection, sizing, and same-day lifecycle. Two parameterized backtests differ only by strike mode.

**Tech Stack:** Python, QuantConnect LEAN Cloud, pytest.

**Spec:** `docs/superpowers/specs/2026-10-25-0dte-first-rebound-design.md`

## Global Constraints

- Do not change the frozen signal.
- No stop loss, averaging, overnight hold, expiry, or exercise.
- TP is 35%; allocation is at most 10% of available cash and equity.
- Backtests run sequentially on the single cloud node.

## Review Focus

- Missing 0DTE chain must skip without substituting another expiry.
- ATM and OTM selectors must differ only in strike selection.
- Entry state must require a filled order.
- Every entry must close by 15:55 ET that day.
- Final holdings must be zero.

---

### Task 1: Pure contract selection and sizing

**Files:**
- Create: `zero_dte_core.py`
- Test: `test_zero_dte_core.py`

**Interfaces:**
- Produces: `select_strike(strikes, spot, right, mode)` and `contract_quantity(cash, equity, ask)`.

- [ ] Write failing unit tests for ATM, call OTM, put OTM, absent strike, and 10% sizing caps.
- [ ] Run tests and confirm RED.
- [ ] Implement minimal pure functions.
- [ ] Run tests and confirm GREEN.

### Task 2: QuantConnect algorithm

**Files:**
- Create: `Yoel 0DTE First Rebound 20261025/main.py`
- Create: `Yoel 0DTE First Rebound 20261025/first_rebound_core.py`
- Create: `Yoel 0DTE First Rebound 20261025/zero_dte_core.py`
- Create: `Yoel 0DTE First Rebound 20261025/config.json`
- Test: `test_qc_zero_dte_contract.py`

**Interfaces:**
- Consumes: frozen first-rebound selector and Task 1 pure helpers.
- Produces: parameter `strike_mode` with values `atm` and `otm`.

- [ ] Write failing source-contract tests for dates, TP, no stop, 15:55 exit, and filled-order publication.
- [ ] Run tests and confirm RED.
- [ ] Implement the isolated algorithm.
- [ ] Run complete pytest and py_compile verification.

### Task 3: Cloud evidence and report

**Files:**
- Create: `zero_dte_atm_raw.json`
- Create: `zero_dte_otm_raw.json`
- Create: `analyze_zero_dte.py`
- Create: `zero_dte_summary.json`
- Create: `INFORME_0DTE_PRIMER_REBOTE_2026-10-25.md`

**Interfaces:**
- Consumes: completed QC payloads.
- Produces: per-variant return, drawdown, Sharpe, PF, yearly and symbol attribution.

- [ ] Push the project and run ATM then OTM sequentially.
- [ ] Reject any run with errors, holdings, or lifecycle mismatch.
- [ ] Generate deterministic summary and Spanish report.
- [ ] Run full tests, compilation, and summary consistency assertions.
