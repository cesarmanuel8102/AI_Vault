# Objective Salience Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Codex keep the economic objective and full effective sleeve capital salient, broaden autonomous opportunity search, and justify `NO_TRADE` without adding architecture or prescribing trades.

**Architecture:** Change only the existing prompt mandate in `autonomous_research.py` and its prompt-contract tests. Preserve every execution, risk, broker, accounting, scheduling, and autonomy boundary; regenerate the existing immutable kernel manifest because the prompt source is kernel-covered.

**Tech Stack:** Python 3.11, Pydantic prompt models, pytest, existing immutable-kernel manifest generator.

**Spec:** `docs/superpowers/specs/2026-11-12-objective-salience-design.md`

## Global Constraints

- No new runtime component, database table, service, scheduler, dependency, screener, or QuantConnect requirement.
- No predefined symbol universe, strategy family, timeframe, setup, candidate quota, trade quota, minimum exposure, or forced trade.
- Nominal price must not be treated as opportunity quality or as the effective capital constraint.
- Both sleeves remain economically independent and model-directed.
- Existing PAPER-only, liability, authorization, reconciliation, idempotency, stale-data, and audit controls remain unchanged.

## Review Focus

- A $10,000 sleeve must be described from bundle-derived capital and never as the old $500 constraint.
- Broader-search language must remain advisory to autonomous expected-information-value judgment, not a mandatory scanner or coverage quota.
- `NO_TRADE` must remain valid and must not require fabricated candidates.
- Liquid options and large-cap equities may be considered but must not become required or preferred instruments.
- Existing prompt hardening tests prohibiting mandatory activity and host-selected strategy must remain green.

---

### Task 1: Objective-salience prompt contract

**Files:**
- Modify: `tests/ibkr_paper_30d/test_mandate_hardening.py`
- Modify: `tests/ibkr_paper_30d/test_autonomy_charter.py`
- Modify: `ibkr_paper_30d/autonomous_research.py:1375-1540`
- Regenerate: `IMMUTABLE_EXECUTION_KERNEL_MANIFEST.json`

**Interfaces:**
- Consumes: `CodexAutonomousCLIProvider._prompt_payload(request, bundle, history, toolbox_manifest)` and bundle-derived effective sleeve allocations.
- Produces: the existing `mandate` object with strengthened objective-salience language; no new public runtime interface.

- [ ] **Step 1: Write failing prompt-contract tests**

Add tests asserting that the mandate:

- tells the model to use effective bundle-derived sleeve capital rather than historical nominal-price affordability;
- states that nominal share price is not opportunity quality;
- invites autonomous comparison across liquid large caps, ETFs, catalyst-backed mid-caps, and liquid options when economically appropriate;
- requires the breadth actually examined and best-alternative rejection to be visible for `NO_TRADE` without requiring a candidate count or fabricated candidate;
- directs repeated narrow, low-information searches toward a model-selected methodology change;
- still contains no mandatory scanner, required symbol, minimum candidate count, trade quota, minimum exposure, `must trade`, or `must be aggressive` language.

- [ ] **Step 2: Run the new tests and verify RED**

Run: `python -m pytest tests/ibkr_paper_30d/test_mandate_hardening.py tests/ibkr_paper_30d/test_autonomy_charter.py -q`

Expected: the new objective-salience assertions fail while existing autonomy and no-forced-action tests pass.

- [ ] **Step 3: Implement the minimal mandate-text change**

Modify only `CodexAutonomousCLIProvider._prompt_payload` in `ibkr_paper_30d/autonomous_research.py`. Extend the existing attention policy and instruction with concise bundle-capital, nominal-price-neutral, broad-comparison, `NO_TRADE` accountability, and adaptive-methodology language. Do not add a new schema, model field outside the mandate, runtime component, or hard numeric target.

- [ ] **Step 4: Run focused prompt tests and verify GREEN**

Run: `python -m pytest tests/ibkr_paper_30d/test_mandate_hardening.py tests/ibkr_paper_30d/test_autonomy_charter.py tests/ibkr_paper_30d/test_autonomous_codex_provider.py tests/ibkr_paper_30d/test_autonomous_research.py -q`

Expected: all selected tests pass, including prohibitions on forced trading and mandatory scanning.

- [ ] **Step 5: Regenerate and verify immutable kernel closure**

Run: `python -m ibkr_paper_30d.kernel_manifest --repo-root . --output IMMUTABLE_EXECUTION_KERNEL_MANIFEST.json`

Run: `python -m pytest tests/ibkr_paper_30d/test_kernel_manifest_closure.py -q`

Expected: manifest generation reports `PASS`; kernel closure tests pass.

- [ ] **Step 6: Run the complete IBKR regression suite**

Run: `python -m pytest tests/ibkr_paper_30d -q`

Expected: zero failures.

- [ ] **Step 7: Commit the isolated change**

```powershell
git add ibkr_paper_30d/autonomous_research.py tests/ibkr_paper_30d/test_mandate_hardening.py tests/ibkr_paper_30d/test_autonomy_charter.py IMMUTABLE_EXECUTION_KERNEL_MANIFEST.json docs/superpowers/specs/2026-11-12-objective-salience-design.md docs/superpowers/plans/2026-11-12-objective-salience.md
git commit -m "feat(ibkr): sharpen autonomous economic objective"
```

### Task 2: Controlled promotion and behavioral observation

**Files:**
- Modify only the existing untracked production launch wrapper's approved HEAD binding during promotion.
- Do not modify canonical databases, receipts, positions, orders, or scheduler structure.

**Interfaces:**
- Consumes: the tested Task 1 commit and existing fail-closed runtime-release procedure.
- Produces: canonical runtime at the approved commit plus existing decision records for behavioral comparison.

- [ ] **Step 1: Stop the existing scheduled runtime cleanly and verify no writer remains**

Use the existing scheduled-task stop path. Verify the Day1/autonomous-service process is absent and PAPER broker state is reconciled before promotion.

- [ ] **Step 2: Promote the exact tested commit and rebind the existing launch wrapper**

Cherry-pick the Task 1 commit into canonical production, update only the wrapper's approved HEAD to the resulting canonical commit, and validate PowerShell AST. Do not create a new task or authority mechanism.

- [ ] **Step 3: Relaunch once through the existing scheduled task**

Expected: fresh execution-lock generation, watchdog heartbeat, PAPER reconciliation, and no LIVE connection.

- [ ] **Step 4: Verify initial post-change behavior**

Observe at least one terminal accepted cycle and record: symbols and instrument families examined, effective capital acknowledged, `NO_TRADE` rationale or proposal, orders/fills/positions, and sleeve equity. Confirm the agent retained autonomy and did not fabricate candidates or trade merely to satisfy the prompt.

- [ ] **Step 5: Compare over two to three sessions using existing records**

Compare against the pre-change baseline: breadth and diversity of alternatives examined, repeated low-information loops, accepted/rejected decisions, trade frequency, fees, P&L, and terminal-equity trajectory. Do not add telemetry infrastructure for this comparison.

