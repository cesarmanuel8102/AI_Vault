# 0DTE Loss Precursor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans. Steps use checkbox syntax.

**Goal:** Instrument the TP5 control, derive one causal loss-precursor rule from 2023-2024, and confirm it on 2025-2026.

**Architecture:** Optional trace mode emits compact derived checkpoint records to QuantConnect logs without altering lifecycle decisions. A local parser joins traces to closed trades and freezes one combined rule before confirmation runs.

**Tech Stack:** Python, pytest, QuantConnect Cloud API.

**Spec:** `docs/superpowers/specs/2026-10-25-0dte-loss-precursor-design.md`

## Tasks

### Task 1: Trace instrumentation
- [x] RED tests for optional trace mode, entry context and checkpoints.
- [x] Add trace state and derived records without changing decisions.
- [x] Verify focused and full suites.

### Task 2: Log retrieval and parsing
- [x] RED tests for authenticated filtered-log pagination and TRACE parsing.
- [x] Implement retrieval and trade/checkpoint join.
- [x] Verify parser on synthetic records.

### Task 3: Discovery runs and rule freeze
- [x] Run TP5 trace controls for 2023 and 2024.
- [x] Analyze pre-entry economics and checkpoint separation.
- [x] Freeze one combined rule without threshold grid search.

### Task 4: Confirmation and report
- [x] Implement the frozen counterfactual evaluator test-first.
- [x] Run 2025 and 2026 trace controls and evaluate the unchanged rule.
- [x] Report retention, expectancy, PF and costs; issue GO/NO-GO.

The rule was not added to live strategy behavior because it failed the
pre-registered profitability and profit-factor gates in discovery and
confirmation.
