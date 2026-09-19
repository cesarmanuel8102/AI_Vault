# HIVE-NEXT V3 Quantitative Research Contract

## Purpose

This contract defines the evidence required to move a strategy hypothesis from
research interest to prospective paper eligibility. It prevents research
sprawl, backtest theater, and promotion based on a favorable isolated result.
It defines future work only; it does not implement a strategy, call QC, or
change runtime behavior.

## Candidate lifecycle

```text
StrategyCandidate
  -> preregistered EconomicHypothesis
  -> versioned data specification
  -> deterministic QC implementation
  -> IS diagnostics
  -> locked OOS
  -> walk-forward
  -> stress matrix
  -> ValidationReceipt
  -> REJECT | VALIDATED_STANDALONE | SLEEVE_CANDIDATE
  -> H3 sleeve admission
  -> H4 selector SHADOW where applicable
  -> PAPER_ELIGIBLE
  -> prospective H5 QC PAPER evidence
```

Candidate states are:

```text
RESEARCH_ONLY
REJECTED
VALIDATED_STANDALONE
SLEEVE_CANDIDATE
PAPER_ELIGIBLE
```

H2 may end at `SLEEVE_CANDIDATE`. `PAPER_ELIGIBLE` requires H3 and, when a
selector is involved, H4. A green backtest never changes the state by itself.

## StrategyCandidate and ResearchTrial

A versioned candidate must be canonicalized before QC execution. Its
canonical serialization and SHA-256 bind the economic hypothesis, exact signal,
universe, rebalance/holding definition, allowed parameters, costs, and risk
limits. A `ResearchTrial` binds one candidate version to a predeclared
experiment and contains at least:

```text
candidate_id
strategy_version
candidate_spec_sha256
qc_project_identity
qc_algorithm_identity
code_sha256
data_specification_and_version
universe_specification
parameter_manifest_sha256
is_interval
locked_oos_interval
walk_forward_definition
benchmark_definition
commission_fee_model
slippage_model
fill_assumptions
execution_delay_assumption
rebalance_frequency
turnover_and_capacity_assumptions
trial_identity
artifact_hashes
```

Unknown, mutable, or manually copied fields do not form a trial receipt.

## IS/OOS discipline

IS is used to diagnose the hypothesis and choose only the predeclared model
family. OOS is locked before final evaluation. If a parameter, universe,
execution assumption, or decision rule changes after OOS is observed, the work
becomes a new candidate version with a new untouched validation region or an
equivalent governed protocol.

```text
observe OOS -> tune -> rerun the same OOS -> call it OOS = INVALID
```

## Required validation matrix

Every serious candidate must declare which stresses are economically applicable
and why an inapplicable stress is omitted. Applicable tests include:

```text
base commissions and fees
higher fees and slippage
execution delay
turnover stress
parameter perturbation
sub-period stability
bull and bear regimes
high and low volatility regimes
liquidity deterioration
tail and drawdown periods
walk-forward re-estimation limits
```

The receipt records net return, risk-adjusted return, max drawdown, trade and
decision count, turnover, cost impact, tail behavior, and pass/fail rationale.
No single ratio is sufficient.

## H3 sleeve admission contract

An H2 survivor must demonstrate incremental portfolio value after costs. H3
must compare the same predeclared eligible portfolio or sleeve under both
states:

```text
PORTFOLIO_OR_SLEEVE_WITHOUT_CANDIDATE
vs
PORTFOLIO_OR_SLEEVE_WITH_CANDIDATE
```

The comparison must include, when economically applicable:

```text
marginal net return
delta Sharpe
delta Sortino
delta max drawdown
marginal volatility/risk contribution
correlation
downside correlation
regime interaction
marginal turnover
marginal transaction/slippage cost
capital competition
capacity impact
marginal risk contribution
marginal drawdown contribution
tail behavior
```

Standalone net return, standalone Sharpe, standalone Sortino, standalone CAGR,
and standalone drawdown may describe the candidate, but cannot substitute for
marginal sleeve/portfolio contribution. A candidate may be
`VALIDATED_STANDALONE` and still receive `REJECT` or `KEEP_RESEARCH_ONLY` at
H3 when it does not improve the sleeve or portfolio after costs and risk.

Only these outcomes are permitted:

```text
REJECT
KEEP_RESEARCH_ONLY
ADD_TO_EXISTING_SLEEVE
CREATE_NEW_SLEEVE_CANDIDATE
```

## H4 selector SHADOW contract

H4 consumes only H3-admitted sleeves. It is a shadow decision experiment, not
an allocator or a trade engine. It must compare net outcomes and operational
complexity against explicit baselines:

```text
equal-weight eligible sleeves
static best validated candidate
STATIC_ALLOCATION_BASELINE
simple trend or momentum allocation
inverse-vol allocation where relevant
cash/no-position baseline where relevant
```

`STATIC_ALLOCATION_BASELINE` means a fixed multi-sleeve or multi-strategy allocation of the same eligible opportunities, with weights declared and frozen before the H4 evaluation period and with no dynamic selector switching during evaluation. It answers whether a dynamic selector adds incremental net
value over simply holding a reasonable fixed allocation. It is distinct from a
single static best strategy, equal weight, inverse-vol, and a simple
trend/momentum rule.

The selector is useful only if it delivers incremental, stable, net value over
the simplest applicable baseline and an appropriate
`STATIC_ALLOCATION_BASELINE` after costs. It must bind candidate, data,
evidence and decision versions; it cannot rely on unbound recent PnL or
precomputed regime labels.

## H5 prospective paper contract

`PAPER_START` is a forward-only timestamp. Before it, the following must be
locked and receipted:

```text
strategy version
sleeve version
selector version, if used
allocation version
universe version
data lineage
execution/fill/cost assumptions
degradation-monitoring thresholds
```

Prospective paper requires real calendar duration, a predeclared minimum number
of decisions, execution lineage, fill/cost accounting, and continuous
degradation monitoring. Backfilled simulation, historical replay, and a
synthetic 30-day run are not prospective paper evidence.

## Brain and safety boundary

```text
HIVE: research, validation, evidence, sleeve/selector research and paper evidence
BRAIN: governance, operator authority and future portfolio/risk/compliance authority

HUMAN_FINAL_AUTHORITY=true
AUTO_MERGE=false
CANONICAL_LOCAL_SYNC=false
LIVE_TRADING=false
REAL_MONEY=false
```

No research receipt creates broker authority, real-order authority, or Brain
runtime integration authority.
