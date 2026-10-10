# Supervision-First Continuous Multi-Universe Pilot Design

**Status:** Owner-approved design clarification, pending implementation plan

**Date:** 2026-10-10

**Repository:** `C:\AI_VAULT_IBKR_WHATIF_FIX`

**Base implementation:** `1c2f62ebc7f9b325a6f44969a4846a1e667ceb86`

## 1. Purpose

This addendum defines the operational transition and pilot behavior for the
Continuous Multi-Universe PAPER experiment. It supersedes any requirement in
the 2026-10-09 design that the PAPER account must be flat before the successor
can assume supervision or before the extended-market canary can begin.

The successor must be able to inherit exact Day1 positions, supervise them
while their market is closed, and independently research and trade certified
continuous-market instruments. Existing positions are not liquidated merely
to make deployment convenient.

## 2. Owner Intent

The experiment has one autonomous Codex decision-maker, one authoritative
PAPER writer, and two economically isolated capital sleeves:

- `REGULAR_SLEEVE`: USD 500 for instruments associated with the daytime
  market. New entries are permitted only while the relevant daytime session
  is open.
- `CONTINUOUS_SLEEVE`: USD 500 for certified extended-hours or effectively
  continuous markets. It may open new positions whenever the selected
  instrument is currently tradable, including during the daytime session.

Codex receives one global opportunity set and ranks all currently executable
opportunities. The sleeves are accounting and authority boundaries, not two
agents, two strategies, or two service loops.

When the daytime market is closed, the agent continues running. It can
research and trade through `CONTINUOUS_SLEEVE` while preserving and
supervising daytime obligations. When both markets are available, it may
choose the best opportunity available to either sleeve. A decision to make no
trade remains valid and must never be converted into a forced order.

## 3. Invariants

The pilot must preserve all of the following:

1. PAPER endpoint `127.0.0.1:4002` only; port `4001` is forbidden.
2. Exactly one write-capable broker client and one execution lock.
3. No global cancel and no host-authored economic trade.
4. No capital transfer, margin subsidy, hedge credit, or loss offset between
   sleeves.
5. Orders, fills, fees, financing, cash, positions, and P&L are attributed to
   exactly one sleeve.
6. A contract or derived ownership group belongs to at most one sleeve while
   an order, execution, position, or unresolved lifecycle obligation exists.
7. Existing Day1 positions are inherited by `REGULAR_SLEEVE` with their exact
   quantities, basis, lineage, and historical P&L. They are never rebased.
8. `CONTINUOUS_SLEEVE` begins with USD 500, zero inherited exposure, and zero
   inherited P&L.
9. Position and order management remains available whenever the instrument is
   tradable, regardless of which entry session originally authorized it.
10. A session transition does not force liquidation. Codex decides whether to
    hold, reduce, close, cancel, or modify within verified broker and capital
    authority.

## 4. Unified Opportunity Model

The state bundle presented to Codex contains both sleeves, all owned positions
and orders, certified product families, authenticated session evidence, and a
single globally ranked research workspace.

Market availability filters executable actions; it does not hide positions or
partition the agent's reasoning:

- `REGULAR_SLEEVE` new entries require an authenticated open daytime session.
- `CONTINUOUS_SLEEVE` new entries require an authenticated open session for a
  fully certified continuous-market product family.
- Exits, reductions, cancellations, exact continuity actions, and monitoring
  are evaluated whenever the relevant instrument can be managed.
- Closure of one market must not idle the other sleeve.
- The whole runtime may enter `MARKET_CLOSED_IDLE` only when no certified
  family is available and no order, position, or continuity deadline requires
  action.

Codex chooses the instrument, thesis, timing, order type, price, quantity,
holding period, and management decision. The host supplies verified facts and
enforces authority boundaries but does not manufacture a market opinion.

## 5. Supervision-First Transition

The operational transition is one-way after predecessor retirement:

`PREPARED -> PREDECESSOR_QUIESCED -> PREDECESSOR_RETIRED -> SUCCESSOR_COMMITTED -> SUPERVISION_BOUND -> CANARY_EXCLUSIVE -> CANARY_PASS -> RUNTIME_BOUND -> ACTIVE`

### 5.1 Preparation

Preparation requires exact approved HEAD, Owner authorization, PAPER identity,
broker reconciliation, zero open broker orders, certain execution history,
exact inherited position lineage, a verified rollback snapshot of files and
database state, and proof that no other writer is active.

An account with existing positions is not a blocker when every position is
exactly identified and attributable to `REGULAR_SLEEVE`. An unattributed,
ambiguous, or mismatched position blocks the transition.

### 5.2 Successor Commit and Supervision Binding

After the predecessor is quiesced and permanently retired, the successor is
committed before the canary. The successor acquires the sole execution lock,
reconciles the account again, and binds all inherited positions to
`REGULAR_SLEEVE`.

In `SUPERVISION_BOUND`:

- both sleeves have new-entry authority frozen;
- Codex and the watchdog continue evaluating inherited positions;
- exact model-authored reduce, close, cancel, and continuity actions remain
  available through the authoritative writer;
- closed daytime instruments remain monitored without causing the whole
  runtime to stop; and
- the predecessor can no longer resume or acquire the broker writer identity.

This removes the continuity gap that previously required inherited positions
to be flat or covered by a predecessor-only maintenance plan.

### 5.3 Canary Under the Same Writer

The canary uses the already-bound successor writer. It must never create a
second broker session with write authority.

Codex performs autonomous read-only discovery and selects a candidate
continuous-market product family and exact contract for capability testing.
The maintenance layer may authorize only that exact candidate with a bounded,
non-replenishing PAPER canary reserve. The canary remains technical evidence,
not experimental P&L and not a host-selected strategy.

Full certification still requires contract qualification, market-data
binding, broker feasibility, submit, broker binding, entry fill, visible
position, one production-path management observation, closing fill, flat
state, and exact economics reconciliation. A no-fill terminal attempt proves
transmission only and cannot enable autonomous entries.

### 5.4 Activation

After `CANARY_PASS`, the runtime binds the exact certified family, both sleeve
authorities, ownership projection, risk authorization, writer identity, and
successor clock. `ACTIVE` is reached only after a fresh account reconciliation.

At `ACTIVE`:

- `REGULAR_SLEEVE` receives new-entry authority whenever its authenticated
  daytime session is open;
- `CONTINUOUS_SLEEVE` receives new-entry authority whenever a certified family
  is tradable; and
- both sleeves remain under one global autonomous decision loop.

## 6. Failure Semantics

- Before predecessor retirement, a flat and certain failed transition may
  return to the predecessor using the verified rollback snapshot.
- After predecessor retirement, rollback never revives Day1. The successor
  remains the sole supervisor in `SUPERVISION_BOUND` or a later phase.
- A flat canary failure leaves inherited-position management active while
  keeping all continuous-sleeve entries disabled.
- An uncertain canary freezes all new entries but preserves exact risk-reducing
  or closing actions for inherited and canary exposure.
- A provider outage cannot authorize a new trade. Only an exact, unexpired,
  model-authored continuity action may write.
- Duplicate writer, order ambiguity, unattributed position, reconciliation
  mismatch, or possible LIVE connection fails closed and triggers the critical
  alert path.

## 7. Pilot Scope

The first real pilot may mutate only PAPER state and the canonical experiment
state required for the successor transition. It must not change LIVE settings
or connect to port `4001`.

The pilot sequence is:

1. reconcile PAPER and bind current Day1 positions to `REGULAR_SLEEVE`;
2. retire the predecessor and start successor supervision with all new entries
   frozen;
3. let Codex discover a currently available continuous-market candidate;
4. run one exact bounded canary through the successor writer;
5. enable `CONTINUOUS_SLEEVE` only after full lifecycle certification;
6. observe at least one accepted autonomous decision cycle in the unified
   opportunity model; and
7. if Codex independently finds an acceptable trade, prove submit, broker
   binding, reconciliation, and a later model-authored management decision.

Pilot success does not require Codex to force a trade. It requires that the
runtime is genuinely capable of trading and managing a certified continuous
instrument while preserving exact supervision of the regular sleeve.

## 8. Verification Requirements

Implementation must use RED -> GREEN -> focused regression -> full regression.
Tests must prove at minimum:

- inherited positions no longer block supervision-first activation;
- ambiguous or unattributed positions still block before retirement;
- predecessor retirement is irreversible and old launch paths cannot connect;
- no entry can occur before full family certification;
- the same writer manages inherited positions and canary lifecycle;
- regular-market closure does not idle an available continuous family;
- continuous-market availability during daytime does not disable that sleeve;
- no cross-sleeve capital or ownership transfer occurs;
- canary failure leaves successor supervision alive with entries frozen;
- direct V4 broker writes without final authority remain impossible;
- legacy production remains unchanged until the separately executed pilot
  transition begins; and
- the full test suite, kernel manifest, provenance checks, PowerShell AST, and
  `git diff --check` all pass at the final implementation HEAD.

## 9. Superseded Rules

For this successor, the following earlier rules are superseded:

- the PAPER account need not be flat before successor supervision;
- predecessor continuity plans are not required to span the canary after the
  successor has committed and bound supervision;
- canary completion precedes extended-sleeve entry authority, but it no longer
  precedes successor supervision of inherited positions; and
- temporary market closure is an instrument availability state, not a reason
  to stop the autonomous service.

All other restrictions and fail-closed authority requirements from the
2026-10-09 Continuous Multi-Universe Sleeves design remain in force.
