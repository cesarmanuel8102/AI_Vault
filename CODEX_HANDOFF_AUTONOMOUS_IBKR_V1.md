# CODEX HANDOFF — AUTONOMOUS IBKR PAPER TRADER V1

Date: 2026-09-21
Canonical integration branch: `codex/ibkr-paper-auditor-gate-v2`
Validated head at handoff: `1817ad0c83f4130b255bdcec958b769289af0083`

## 1. Purpose

This document is the canonical handoff for Codex and any subsequent agent that
continues the IBKR 30-day autonomous paper-trading experiment.

The objective is not to execute human-designed strategies. The objective is to
measure the autonomous market-research, trading, capital-allocation and
position-management capability of Codex under only these economic constraints:

1. actual IBKR broker permissions and feasibility;
2. current isolated experimental equity;
3. the declared account options permission level (Level 4 context);
4. no economic liability outside isolated experimental capital.

Initial experimental capital: USD 500.

The experiment is aggressive by design. Full loss of current isolated
experimental equity is permitted. The system must not introduce arbitrary
percentage risk limits as a substitute for Codex's reasoning.

## 2. Canonical optimization objective

Codex should reason toward:

`maximize expected terminal experimental equity at the end of the 30-day experiment`

The relevant state is dynamic:

`State_t = {Equity_t, Cash_t, BuyingPower_t, Positions_t, BrokerConstraints_t, Permissions_t, TimeRemaining_t, Market_t, OpportunitySet_t}`

The opportunity set must be rebuilt as capital, broker feasibility and market
conditions change.

A strategy that was not financially executable at USD 500 may become feasible
after capital growth and must be reconsidered. The reverse also applies after
drawdowns.

## 3. Autonomous research architecture

The old architecture was effectively:

`human/predefined scanner -> predefined strategy -> frozen candidate -> Codex validation`

That architecture is NOT authoritative for this experiment.

The autonomous architecture is:

`fresh state -> Codex -> research request(s) -> read-only tools/web -> Codex -> more research as needed -> final decision -> broker feasibility -> deterministic integrity gates -> paper execution`

Codex controls:

- what symbols and markets to investigate;
- what public information to research;
- what timeframe to use;
- what thesis to form;
- what instrument to use;
- what options structure to use;
- position sizing;
- entry;
- monitoring;
- reduction;
- exit;
- whether to remain in cash.

There is no fixed strategy catalog above Codex.

Legacy scanners/strategy code may exist elsewhere in the repository but must
not become an authoritative universe or strategy gate for the autonomous path.

## 4. Codex model configuration

Autonomous runtime default:

- model: `gpt-5.6-sol`
- reasoning effort: `max`
- live Codex web research enabled with `--search`

The runtime audits native Codex tool activity metadata.

Do NOT regress the autonomous runtime to `gpt-5.5` or lower reasoning effort
unless there is an explicit operator decision to do so.

## 5. Research toolbox

Codex has primitive read-only research tools rather than predetermined answers.

Current broker research toolbox includes:

- account state;
- current experiment-relevant positions;
- open orders;
- recent executions/fills;
- IBKR market scanners;
- contract resolution;
- current quotes;
- option Greeks when available;
- historical bars;
- option-chain discovery;
- subscribed IBKR news;
- IBKR what-if order feasibility;
- margin and commission evidence.

Public context can additionally be researched through Codex live web search.

IBKR remains the execution authority for actual contract existence, permissions,
margin and feasibility.

## 6. No frozen candidate universe

The autonomous route must keep:

`candidate_screen_results=[]`

The model may discover any instrument actually available through IBKR and the
account.

Do NOT restore checks such as:

`SYMBOL_NOT_IN_FROZEN_CANDIDATES`

Do NOT hard-code SPY/QQQ/AAPL/IWM/MSFT or another symbol list as the autonomous
opportunity universe.

SPY, QQQ and IEF are used only for the independent Market Data Policy evidence
protocol. They are NOT the trading universe.

## 7. Capital and risk policy

Canonical policy:

`AGGRESSIVE_CAPITAL_BOUNDARY_V1`

There are NO autonomous-route fixed limits for:

- 5% risk per trade;
- 15% total open risk;
- 20% drawdown;
- 40% position cap;
- daily loss percentage;
- weekly drawdown percentage;
- maximum number of positions;
- mandatory stop loss;
- mandatory diversification.

Legacy `RiskEngine.month1()` remains in the repository for compatibility with
older code but MUST NOT be connected to the autonomous route.

The only experiment-level financial boundary is:

`maximum experiment liability <= current isolated experimental equity`

Full current equity may be risked when Codex's reasoning supports it.

## 8. Broker-authoritative capital feasibility

The model-authored field `capital_required` is advisory only.

It must NOT pre-block a proposal.

Actual executability is decided using:

- deterministic payoff/loss analysis;
- IBKR contract resolution;
- IBKR what-if;
- actual initial/maintenance margin change;
- commissions;
- current isolated experiment equity.

A broker account may contain more cash/buying power than the experiment. That
extra broker equity is NOT available to this experiment.

## 9. Level 4 treatment

Level 4 is treated as the maximum strategy capability context, not as an
obligation to use leverage and not as a static strategy allowlist.

Finite-loss examples that can be considered when broker-feasible and within
isolated equity include:

- long stock;
- long calls/puts;
- defined-risk debit spreads;
- defined-risk credit spreads;
- bounded same-expiry multi-leg option structures;
- cash-secured/finite-loss short puts;
- covered calls when isolated experiment shares provide the cover.

Examples that remain blocked because they can violate isolated capital:

- uncovered short calls;
- naked short stock;
- unbounded ratio structures;
- structures whose maximum loss cannot be proven;
- any position capable of consuming capital outside the experiment.

For single long stock/options, maximum paid capital is derived from executable
limit terms, not the model's estimate.

Market orders whose maximum spend cannot be bounded pre-trade must fail closed
when necessary to protect experiment isolation.

## 10. Isolated experiment ledger

Do NOT use global IBKR Net Liquidation Value as the experiment equity.

Canonical experiment state is reconstructed from an append-only isolated ledger
using actual broker fills and marks.

Ledger data includes:

- contract id (conId);
- symbol;
- security type;
- multiplier;
- BUY/SELL side;
- quantity;
- fill price;
- commission;
- execution id hash;
- current mark.

The ledger supports stock, options and individual spread legs.

It computes:

- allocation;
- cash;
- market value;
- current equity;
- high-water mark;
- drawdown;
- fees;
- tracked positions.

High-water mark and drawdown are measurement fields only, not fixed stop rules.

## 11. Fill reconciliation and order isolation

Experiment-originated orders use orderRef prefixes:

- `codex-ibkr-paper-30d-autonomous`
- `codex-ibkr-paper-30d-position-management`

Only executions matching the experiment prefix are imported into the isolated
experiment ledger.

Delayed broker fills are reconciled before each autonomous decision cycle.

Fills are deduplicated using `execution_id_hash`.

Do NOT mix unrelated account positions/orders/fills into the experiment.

## 12. Fresh state before every decision

Before each autonomous Codex cycle, the state builder:

1. reads recent broker executions;
2. imports only experiment-tagged fills;
3. deduplicates them;
4. marks experiment positions with current broker quotes;
5. recomputes isolated cash/equity;
6. reads broker account state;
7. reads current broker positions;
8. reconciles ledger quantities against broker positions;
9. filters open orders to experiment-tagged orders;
10. injects remaining experiment time;
11. leaves candidate_screen_results empty.

Reconciliation failure must block a new action rather than inventing a trading
decision.

## 13. Experiment clock

Every decision bundle includes:

- experiment start UTC;
- experiment end UTC;
- elapsed days;
- remaining days;
- remaining seconds;
- expired flag.

The default duration is 30 calendar days.

Codex should account for the remaining horizon when choosing strategies.

## 14. Valid autonomous decisions

The autonomous loop supports:

- `NO_TRADE`
- `PROPOSE_TRADE`
- `MONITOR_POSITION`
- `REDUCE_POSITION`
- `CLOSE_POSITION`
- `PAUSE_FOR_REVIEW`

NO_TRADE is valid and must never be penalized merely because no trade occurred.

Position reduction/close is revalidated against the real current IBKR position
and must reduce rather than increase exposure.

## 15. Operating cadence

Default continuous service cadence:

- no open position: opportunity-discovery cycle every 300 seconds;
- open position: position-management review every 60 seconds;
- immediately after a fill: immediate position-state reassessment.

These are observation/reasoning frequencies, NOT mandatory trade frequencies.

Codex may repeatedly return NO_TRADE or MONITOR_POSITION.

## 16. Paper execution arming

Implementation is paper-only.

Deployment does NOT arm paper order transmission.

Paper execution requires the explicit environment control:

`IBKR_AUTONOMOUS_PAPER_ARMED=true`

The experiment is not considered started merely because code is deployed or
prerequisites pass.

Do NOT enable live-money execution.

## 17. Non-strategic integrity gates retained

These controls are intentional and must not be interpreted as trading strategy
constraints:

- local PAPER Gateway endpoint only;
- port 4002;
- single DU paper-account identity;
- reconciliation gate;
- kill switch;
- market-data integrity gate;
- immutable decision/input evidence;
- IBKR what-if immediately before execution;
- isolated-capital boundary;
- auditor least-privilege gate.

## 18. Auditor Gate V2

The real Auditor V2 path is implemented.

Relevant files:

- `AUDITOR_WINDOWS_PROVISIONING_V1.ps1`
- `AUDITOR_RUNTIME_V2_DEPLOYMENT.ps1`
- `auditor_runtime/AUDITOR_GATE_V2_PROBE.ps1`
- `auditor_runtime/AUDITOR_DENIAL_PROBE_V1.ps1`
- `auditor_runtime/CODEX_DECISION_AUDITOR_V1.ps1`
- `FINALIZE_IBKR_PREREQUISITES.ps1`

Auditor restricted local account:

`CodexAuditorV1`

Expected SID currently encoded by the reviewed V2 design:

`S-1-5-21-214160970-1890373857-4055601883-1012`

The finalizer must verify that the actual SID matches. Do not silently accept a
different account identity.

The finalizer:

- proves PAPER broker identity;
- installs exact V2 runtime;
- builds immutable audit export;
- runs the consolidated probe under the restricted non-admin account;
- promotes the real receipt;
- evaluates the receipt against current runtime hashes;
- leaves trading unarmed.

## 19. Market Data Policy prerequisite

The market-data gate is independent from strategy discovery.

Required evidence protocol:

- symbols: SPY, QQQ, IEF;
- session: REGULAR;
- realtime data only;
- 3 distinct windows;
- each window >= 5 minutes;
- start separation >= 30 minutes;
- evidence span >= 65 minutes;
- at least 540 accepted observations total;
- at least 180 accepted observations per required symbol.

The automated runner currently collects:

- three 330-second windows;
- 5-second cadence;
- 31-minute start separation;
- 67 samples per symbol/window;
- 201 samples per symbol total if all are accepted.

Verified primary exchanges:

- SPY -> ARCA
- QQQ -> NASDAQ
- IEF -> NASDAQ

Do NOT revert all three to ARCA.

The broker callback now retains the latest broker quote timestamp. Do NOT change
the comparison back to preserving the oldest timestamp.

IBKR connector verification on 2026-09-21 showed `top-status=REALTIME` for
SPY, QQQ and IEF.

Relevant runner:

`RUN_IBKR_MARKET_DATA_GATE.ps1`

The runner freezes `MARKET_DATA_POLICY_V1`, validates a fresh snapshot and
removes its scheduled task after PASS.

## 20. Prerequisite finalizer

Canonical admin finalizer:

`FINALIZE_IBKR_PREREQUISITES.ps1`

Canonical runbook:

`IBKR_PREREQUISITE_FINALIZATION_RUNBOOK.md`

This workflow does not arm or start trading.

## 21. Validation state at handoff

Latest validated Windows autonomous/prerequisite suite before this handoff:

- 71 passed
- 0 failed

Windows CI also validates:

- Python compile for critical modules;
- PowerShell parser for prerequisite scripts;
- security baseline;
- autonomous research tests;
- architecture contract tests;
- Level 4 bounded-structure tests;
- prerequisite helper tests;
- import smoke.

Always inspect current CI after future changes; do not rely indefinitely on the
historical count above.

## 22. Critical files added/modified during this work

Autonomous trader core:

- `ibkr_paper_30d/autonomous_research.py`
- `ibkr_paper_30d/ibkr_research_tools.py`
- `ibkr_paper_30d/autonomous_execution.py`
- `ibkr_paper_30d/autonomous_runtime.py`
- `ibkr_paper_30d/autonomous_state.py`
- `ibkr_paper_30d/autonomous_service.py`
- `ibkr_paper_30d/experiment_ledger.py`
- `ibkr_paper_30d/trader_invocation.py`
- `ibkr_paper_30d/risk.py`

Prerequisite completion:

- `ibkr_paper_30d/prerequisite_tools.py`
- `FINALIZE_IBKR_PREREQUISITES.ps1`
- `RUN_IBKR_MARKET_DATA_GATE.ps1`
- `IBKR_PREREQUISITE_FINALIZATION_RUNBOOK.md`

Market-data corrections:

- `ibkr_paper_30d/market_observation_collector.py`

Canonical design document:

- `CODEX_IBKR_AUTONOMOUS_RESEARCH_V1.md`

## 23. Merged PR history

Important merged work:

- PR #395 — Autonomous Codex research and capital-adaptive IBKR paper trader.
- PR #397 — Broker-authoritative capital-bound refinements.

Do not reconstruct behavior from PR summaries alone. Current branch code is
authoritative.

## 24. Rules for future Codex changes

Before modifying this system, Codex must preserve these invariants:

1. no human-preselected trading universe;
2. no strategy-family gate above Codex;
3. no fixed 5/15/20-style autonomous risk caps;
4. no use of broker-global NLV as experiment equity;
5. no external-capital leakage;
6. no unbounded liability;
7. IBKR what-if remains execution authority;
8. experiment fills remain isolated by orderRef and execution hash;
9. state is rebuilt before each decision;
10. live search remains enabled unless explicitly disabled by operator;
11. default maximum-capability model remains GPT-5.6 Sol/max unless explicitly changed;
12. paper execution remains unarmed by deployment;
13. live-money execution remains disabled;
14. Market Data Policy evidence remains separate from the trading universe;
15. any change must pass Windows/Linux CI before promotion.

## 25. Immediate next operational step

After local synchronization, run the prerequisite finalizer from elevated
Windows PowerShell with PAPER IB Gateway open:

```powershell
Set-Location C:\AI_VAULT
.\FINALIZE_IBKR_PREREQUISITES.ps1
```

Then allow the scheduled Market Data Gate task to collect regular-session
evidence.

Only after both prerequisite gates show PASS should experiment arming/start be
considered as a separate explicit step.
