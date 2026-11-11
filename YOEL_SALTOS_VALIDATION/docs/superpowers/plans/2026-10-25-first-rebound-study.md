# First Rebound Study Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Test the transcript's first moving-average rebound concept in stocks and two option expressions under frozen rules.

**Architecture:** Pure helpers define trend/touch acceptance. A fresh LEAN algorithm emits one immutable signal stream and routes it to stock, long-option, or debit-spread lifecycle engines selected by parameter.

**Tech Stack:** Python 3, pytest, QuantConnect LEAN Cloud, US equity and option minute data.

**Spec:** `FIRST_REBOUND_SPEC.md`

## Global Constraints

- No parameter changes after the first full-period result.
- No reuse of optimized Yoel option versions.
- All vehicles consume the same signal definition.
- Costs, bid/ask and failed subscriptions remain in the result.

## Review Focus

- A second touch in the same trend regime must not signal.
- Hourly bars must align to 09:30 ET, not the top of the hour.
- A daily disagreement must block the hourly signal.
- The strongest touched average must be chosen deterministically.
- Options must close before expiry and never average down.

---

### Task 1: Frozen signal helpers

**Files:** Create `first_rebound_core.py`; test `test_first_rebound_core.py`.

- [ ] Write RED tests for bullish/bearish first touch, daily disagreement, reused level, Bollinger contraction and strongest-level selection.
- [ ] Implement the minimum helper and run focused/full suites GREEN.

### Task 2: Stock LEAN reproduction

**Files:** Create `Yoel First Rebound 20261025/main.py` and `config.json`.

- [ ] Build 09:30-aligned hourly and daily state.
- [ ] Implement immutable signal regimes and stock lifecycle.
- [ ] Smoke test 2025, then run the frozen 2020-2025 period.

### Task 3: Option expressions

**Files:** Modify only the new project and add vehicle-specific lifecycle helpers.

- [ ] Add 21-45 DTE slightly-ITM long option expression.
- [ ] Add same-expiry debit spread expression.
- [ ] Smoke test each vehicle, then run frozen periods without changing signals.

### Task 4: Analysis

**Files:** Create raw results, `analyze_first_rebound.py`, summary JSON and Spanish report.

- [ ] Attribute returns by year, symbol, MA period, direction and exit reason.
- [ ] Compare all vehicles after fees and apply the frozen gate.
- [ ] Verify tests, syntax, completed backtests and artifact consistency.

