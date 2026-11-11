# 0DTE TP 5% Quality Exit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Determine whether a preregistered failure-to-launch exit and one quality filter can make the ATM 0DTE first-rebound strategy profitable out of sample.

**Architecture:** Add pure decision helpers and explicit trade instrumentation, expose only the preregistered parameters, select one rule on 2025, then run that rule unchanged on 2026. QuantConnect remains the execution and fee-model authority.

**Tech Stack:** Python, pytest, QuantConnect Cloud/LEAN API.

**Spec:** `docs/superpowers/specs/2026-10-25-0dte-tp5-quality-exit-design.md`

## Global Constraints

- ATM 0DTE long options, TP 5%, 10% allocation, IBKR fees and USD 0.01 slippage.
- Development data ends 2025-12-31; 2026 is not inspected before variant selection.
- Test only control, 5m/0%, 8m/-2%, and quality plus the selected exit.
- No additional threshold search after seeing 2026.

## Review Focus

- Missing bid at the checkpoint must defer, not fabricate a return.
- Quality filter must be direction symmetric and reject zero-range bars.
- Checkpoint exits must use actual fill time, not signal time.
- All backtests must end flat with entries equal to closes and zero rejected closes.
- Costs and profit factor must be computed from closed trades, not runtime hit rate.

---

### Task 1: Pure exit and quality rules

**Files:**
- Modify: `zero_dte_core.py`
- Modify: `Yoel 0DTE First Rebound 20261025/zero_dte_core.py`
- Test: `test_zero_dte_core.py`

**Interfaces:**
- Produces: `failure_to_launch_due(minutes_held, pnl, checkpoint_minutes, minimum_pnl) -> bool`
- Produces: `quality_signal(direction, open_, high, low, close, relative_volume) -> bool`

- [ ] Write failing tests for threshold boundaries, disabled checkpoints, symmetry, zero range, and volume 1.2.
- [ ] Run `python -m pytest test_zero_dte_core.py -q` and verify RED.
- [ ] Implement the two pure helpers minimally.
- [ ] Run the focused test and verify GREEN.

### Task 2: QuantConnect integration and instrumentation

**Files:**
- Modify: `Yoel 0DTE First Rebound 20261025/main.py`
- Test: `test_qc_zero_dte_contract.py`

**Interfaces:**
- Consumes Task 1 helpers.
- Produces parameters `start_year`, `end_year`, `failure_minutes`, `failure_min_pnl`, `quality_filter`.

- [ ] Write failing source-contract tests for date bounds, entry features, checkpoint exit and runtime statistics.
- [ ] Run the focused test and verify RED.
- [ ] Integrate parameters, quality gating and `FAILURE_EXIT` after TP evaluation.
- [ ] Record relative volume and directional close location in order tags/runtime counters.
- [ ] Run focused tests and full `python -m pytest -q`.

### Task 3: 2025 selection

**Files:**
- Create: `zero_dte_optimization_manifest.json`
- Create: `analyze_zero_dte_optimization.py`
- Test: `test_analyze_zero_dte_optimization.py`

**Interfaces:**
- Produces deterministic net expectancy, profit factor, drawdown, semester stability and selector ranking.

- [ ] Write failing tests for cost-aware metrics and deterministic selection.
- [ ] Implement analyzer and verify tests.
- [ ] Run four sequential 2025 QuantConnect backtests and fetch immutable raw JSON.
- [ ] Select exactly one candidate using the preregistered ranking and freeze it in the manifest.

### Task 4: Locked 2026 validation and report

**Files:**
- Create: `INFORME_0DTE_TP5_OPTIMIZACION_2026-10-25.md`
- Modify: `zero_dte_optimization_manifest.json`

- [ ] Run only the 2026 control and frozen candidate sequentially.
- [ ] Verify completion, flat ending state, order counts, fees and rejection counters.
- [ ] Apply GO / NO-GO / INSUFFICIENT criteria exactly as specified.
- [ ] Run `python -m pytest -q` and `python -m py_compile` on changed Python files.

