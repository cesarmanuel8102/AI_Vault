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
must compare a predeclared eligible portfolio without and with the candidate,
including:

```text
standalone net return
standalone Sharpe and Sortino
maximum drawdown and tail behavior
turnover and marginal costs
capacity and capital competition
linear and downside correlation
regime correlation
marginal return contribution
marginal risk contribution
marginal drawdown contribution
```

Only these outcomes are permitted:

```text
REJECT
KEEP_RESEARCH_ONLY
ADD_TO_EXISTING_SLEEVE
CREATE_NEW_SLEEVE_CANDIDATE
```

A standalone Sharpe cannot substitute for this comparison.

## H4 selector SHADOW contract

H4 consumes only H3-admitted sleeves. It is a shadow decision experiment, not
an allocator or a trade engine. It must compare net outcomes and operational
complexity against explicit baselines:

```text
equal-weight eligible sleeves
static best validated candidate
simple trend or momentum allocation
inverse-vol allocation where relevant
cash/no-position baseline where relevant
```

The selector is useful only if it delivers incremental, stable, net value over
the simplest applicable baseline. It must bind candidate, data, evidence and
decision versions; it cannot rely on unbound recent PnL or precomputed regime
labels.

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
