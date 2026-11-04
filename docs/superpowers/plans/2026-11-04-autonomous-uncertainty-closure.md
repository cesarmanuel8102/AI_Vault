# Autonomous Uncertainty Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Require Codex to close or abandon repeated unresolved uncertainty without prescribing trading judgment.

**Architecture:** Extend the existing mandate text and economic-accountability contract only. Pin the autonomy-preserving behavior with a focused contract test, then run the relevant research and charter regressions before deployment.

**Tech Stack:** Python, Pydantic, pytest.

**Spec:** `docs/superpowers/specs/2026-11-04-autonomous-uncertainty-closure-design.md`

## Global Constraints

- Preserve unconditional validity of NO_TRADE.
- Do not prescribe instruments, strategies, evidence types, thresholds, cadence, or risk.
- Do not modify execution or safety boundaries.

## Review Focus

- The new language must not imply mandatory trading.
- The model must retain authority to choose how to resolve uncertainty.
- Continuing an investigation must remain possible when information value is positive.
- A methodology change must not be required merely because one cycle ends NO_TRADE.
- The existing strict output schema must remain unchanged.

---

### Task 1: Add the uncertainty-closure contract

**Files:**
- Modify: `tests/ibkr_paper_30d/test_autonomy_charter.py`
- Modify: `ibkr_paper_30d/autonomous_research.py`

**Interfaces:**
- Consumes: `CodexAutonomousCLIProvider._prompt_payload(...)`
- Produces: mandate field `autonomous_uncertainty_closure` and matching instruction text.

- [ ] **Step 1: Write the failing contract test**

Assert that repeated material evidence gaps without new information require an autonomous choice among resolving the gap, changing method, or redirecting attention; assert that no host-selected method or mandatory trade language appears.

- [ ] **Step 2: Run the focused test and verify RED**

Run: `python -m pytest tests/ibkr_paper_30d/test_autonomy_charter.py::test_repeated_uncertainty_requires_autonomous_closure_without_prescribing_method -q`

- [ ] **Step 3: Add the minimal mandate field and instruction paragraph**

Keep all choices model-selected and preserve NO_TRADE.

- [ ] **Step 4: Run focused and relevant regression suites**

Run the charter test, autonomous-research tests, and mandate-hardening tests.

- [ ] **Step 5: Commit the isolated change**

Commit only the specification, plan, test, and mandate change.
