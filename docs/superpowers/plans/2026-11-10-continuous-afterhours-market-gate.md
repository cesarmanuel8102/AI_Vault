# Continuous After-Hours Market Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the V4 model-visible market gate reflect sleeve-specific eligibility without weakening regular-session or order-level controls.

**Architecture:** Derive an effective snapshot after `_multi_sleeve_context` computes authoritative entry and management eligibility. Preserve the original regular gate as nested evidence and keep existing proposal validation unchanged.

**Tech Stack:** Python, Pydantic, pytest, SQLite-backed runtime state.

**Spec:** `docs/superpowers/specs/2026-11-10-continuous-afterhours-market-gate-design.md`

## Global Constraints

- PAPER only; never connect to LIVE `4001` or submit a forced order.
- Regular sleeve must remain blocked outside its authenticated session.
- Continuous pass requires an existing V4 `PASS` eligibility route.
- Original regular gate evidence must remain available.

## Review Focus

- Continuous eligible while regular is closed: effective gate passes and regular remains blocked.
- No eligible V4 route: original block remains unchanged.
- Regular quote gate failure during regular hours: must not be hidden unless another independently eligible V4 route exists.
- Management-only eligibility: research context remains available without opening new entries.
- Proposal binding: a regular proposal cannot use a continuous family or eligibility pass.

---

### Task 1: Derive and publish the effective V4 market gate

**Files:**
- Modify: `ibkr_paper_30d/autonomous_state.py`
- Test: `tests/ibkr_paper_30d/test_autonomous_state.py`
- Test: `tests/ibkr_paper_30d/test_autonomous_research.py`

**Interfaces:**
- Consumes: frozen `market_gate` plus `multi_sleeve_portfolio.entry_eligibility` and `management_eligibility`.
- Produces: `_effective_market_data_snapshot(market_gate, multi_sleeve_portfolio)`.

- [ ] Write failing tests proving continuous after-hours eligibility yields an effective pass, no eligibility retains block, and regular proposals remain blocked.
- [ ] Run focused tests and confirm the expected failure.
- [ ] Implement the smallest pure projection helper and use it in `AutonomousStateBuilder.build`.
- [ ] Run focused tests and the relevant state/research/service suites.
- [ ] Run the complete suite, kernel/provenance checks, and `git diff --check`.
- [ ] Commit, deploy at the approved head, relaunch once, and verify accepted cycles expose the corrected gate without orders or alerts.
