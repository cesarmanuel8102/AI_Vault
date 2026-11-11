# Options Operability Backtest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Test the frozen post-shock continuation signal directly with weekly long options, with and without the transcript's reinforcement rule.

**Architecture:** Pure Python helpers own deterministic contract selection, sizing, target replacement and decision-gate logic. A fresh QuantConnect project owns historical option subscriptions, orders and lifecycle accounting. Two cloud backtests differ only by the reinforcement parameter.

**Tech Stack:** Python 3, pytest, QuantConnect LEAN CLI/cloud, US equity and equity-option minute data.

**Spec:** `OPTIONS_OPERABILITY_SPEC.md`

## Global Constraints

- Never modify the frozen signal after observing results.
- Use actual historical contracts and broker fee/fill models; do not synthesize option prices.
- Never allow expiry or exercise.
- Keep previous optimized option algorithms out of the implementation.

## Review Focus

- Friday signals must choose the following Friday, never same-day expiry.
- Calls must be strictly OTM above spot and puts strictly OTM below spot.
- Reinforcement may occur once and may not exceed original premium outlay.
- Replaced targets must use weighted average cost and the full combined quantity.
- Zero bid or stale quote conditions must not create favorable synthetic exits.

---

### Task 1: Pure options rules

**Files:**
- Create: `options_operability_core.py`
- Test: `test_options_operability_core.py`

**Interfaces:**
- Produces: `select_weekly_contract`, `premium_quantity`, `reinforcement_quantity`, `target_price`, and `passes_options_go_gate`.

- [ ] Write failing tests for expiration, OTM strike, sizing, one-time reinforcement bounds, weighted target and GO gate.
- [ ] Run `pytest test_options_operability_core.py -q` and confirm RED.
- [ ] Implement the minimum pure helpers.
- [ ] Run the focused and full test suites and confirm GREEN.

### Task 2: Fresh QuantConnect algorithm

**Files:**
- Create: `Yoel Options Operability 20261025/main.py`
- Create: `Yoel Options Operability 20261025/config.json`

**Interfaces:**
- Consumes: the frozen constants and behavior from Task 1.
- Produces: cloud backtests with complete lifecycle runtime statistics and trade logs.

- [ ] Create the project without importing prior strategy code.
- [ ] Implement unchanged stock signal generation and historical contract discovery.
- [ ] Implement quote-valid entry, +35% target, time/DTE exit and optional reinforcement.
- [ ] Add complete end-of-algorithm counters and structured trade logs.
- [ ] Run a short cloud smoke backtest and repair runtime/API errors only.

### Task 3: Frozen full runs and analysis

**Files:**
- Create: `options_base_raw.json`
- Create: `options_reinforcement_raw.json`
- Create: `analyze_options_results.py`
- Create: `options_summary.json`
- Create: `INFORME_OPCIONES_2026-10-25.md`

**Interfaces:**
- Consumes: both frozen cloud backtest results.
- Produces: a direct stock-versus-options comparison and GO/NO_GO verdict.

- [ ] Run `BASE` over 2022-2025.
- [ ] Run `REINFORCEMENT` over 2022-2025 with no other changes.
- [ ] Parse returns, drawdown, Sharpe, fees, trade outcomes and per-year/per-symbol robustness.
- [ ] Apply the frozen gate and write the Spanish report.
- [ ] Re-run tests and verify all result artifacts exist and agree.

