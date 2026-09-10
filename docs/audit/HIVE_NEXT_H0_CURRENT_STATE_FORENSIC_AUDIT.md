# HIVE-NEXT H0 Current-State Forensic Audit

## Scope and method

This is a static, read-only source audit at the immutable parent snapshot
`8c17580fe0d530b4af3f5a5be26dcc947d0a3d71`. It did not run QC, connect to a
provider or broker, modify strategy code/configuration/datasets, create paper
orders, read mutable paper results, or choose a strategy winner.

```text
QC_EXECUTED=false
PAPER_ORDERS_EXECUTED=false
SELECTOR_MUTATED=false
DATASETS_MUTATED=false
NO_WINNER_DECLARED=true
```

## Source inventory

| Source | SHA-256 | Role observed | Evidence classification |
| --- | --- | --- | --- |
| `tmp_agent/brain_v9/trading/strategy_selector.py` | `e444c6bdfab85406de7ea22d0d5d2e3e187b31adb56be64232637e474a32d1f6` | Deterministic ranking and exploit/explore/probation choice from supplied candidates. | RESEARCH_ONLY |
| `tmp_agent/brain_v9/trading/active_strategy_catalog.py` | `56eb3bf1ef42b23d68f925f6ee581d1d02555b8ce581c2598801aa3a29c19d0f` | Builds venue/lane catalog snapshots from strategies, scorecards, and venue health. | PARTIAL_EVIDENCE |
| `tmp_agent/brain_v9/trading/strategy_archive.py` | `eb0186284a6980d692ab5208d6bb4271d763397de3ea11e7e0b283374a73bba3` | Produces archive snapshots from strategy, scorecard, and hypothesis inputs. | ARCHIVED |
| `tmp_agent/brain_v9/trading/strategy_scorecard.py` | `75d4f219d3d3276bb3c52abc76991319adb63d1f5a48c8154085b6b52e147f0d` | Maintains aggregate, symbol, and context scorecards and freeze/unfreeze states. | PARTIAL_EVIDENCE |
| `tmp_agent/brain_v9/trading/edge_validation.py` | `4fda37ba43ac1b32590e9ff6f9c82f1bec1db95c99980a987a28da90b8d334eb` | Classifies supplied candidate evidence into edge and execution lanes. | PARTIAL_EVIDENCE |
| `tmp_agent/brain_v9/trading/context_edge_validation.py` | `bd43a0cfc629e872f32a806d82fae62dcf8a8f944b2874677bb3a0544b349922` | Classifies supplied current-context evidence and execution impact. | PARTIAL_EVIDENCE |

The canonical source snapshot does not contain a versioned `ResearchTrialRegistry`,
immutable candidate specification ledger, dataset manifest, or source-bound QC
execution receipt set. Individual strategy families and historical artifacts can
therefore be identified only as `UNKNOWN`, `RESEARCH_ONLY`,
`RESULT_WITHOUT_PROVENANCE`, `BACKTEST_ONLY`, `PARTIAL_EVIDENCE`, `REJECTED`,
or `ARCHIVED` until a later H0 evidence collector binds them to code, data, and
run identity.

`HIVE_NEXT_H0_STATIC_STRATEGY_INVENTORY.json` records every 25 tracked
`tmp_agent/strategies/**/main.py` candidates from this snapshot with its exact
source hash. Every candidate is classified `RESEARCH_ONLY`; its parameters,
dataset, IS/OOS claim, stress claim, QC/paper identifiers, execution receipt,
and selector/scorecard history are explicitly `UNKNOWN_UNBOUND`. The inventory
is evidence of source presence, not a performance claim or approval.

## Selector forensic findings

```text
SELECTOR_DETERMINISM: DETERMINISTIC_FOR_IDENTICAL_INPUT
REGIME_DETECTION: PRECOMPUTED_INPUT_ONLY
DOWNSIDE_CORRELATION: NOT_IMPLEMENTED
PAPER_DEGRADATION: NOT_IMPLEMENTED
VALIDATION_LINEAGE: NOT_BOUND_TO_RANKING
```

`strategy_selector.py` ranks supplied candidates using expectancy, win rate,
profit factor, drawdown, sample quality, consistency, venue health,
`regime_alignment_score`, context and symbol expectancy/quality, execution
readiness, signal validity, and governance/freeze state. The source consumes a
precomputed regime-alignment value; it does not implement a versioned regime
detector, feature dataset lineage, locked OOS evaluation, or walk-forward
comparison.

The ranking additionally reads `recent_5_outcomes`, current/context expectancy,
and recovery-oriented fields. That makes recent performance capable of changing
rank, so performance-chasing resistance is not demonstrated. Source inspection
found no portfolio correlation matrix, downside-correlation model, marginal
CVaR calculation, paper-execution degradation measure, `candidate_spec_sha256`,
dataset SHA, trial ID, or OOS receipt bound into the ranking input.

The selector has deterministic sorting and eligibility functions for identical
input lists. `strategy_scorecard.py` can freeze, unfreeze, retire, and force
unfreeze scorecards; this is not a validated allocation-reduction policy and
does not establish safe selector-controlled paper capital.

## Evidence and runtime inventory limits

The following claims remain unverified by H0 because this front neither reads
mutable runtime state nor calls external systems:

| Required H0 evidence | Status |
| --- | --- |
| Candidate versions and parameter sets | UNKNOWN: no immutable registry. |
| Dataset identities, periods, IS/OOS splits | UNKNOWN: no bound dataset manifest. |
| QC project/backtest/paper deployment IDs | UNKNOWN: external state not queried. |
| Actual fills, friction, reconciliation | UNKNOWN: no execution receipts inspected. |
| Selector history and scorecard history | PARTIAL_EVIDENCE: source mechanisms exist; immutable history is not bound. |
| Failed/rejected/invalid trials and duplicates | UNKNOWN: no all-trials registry. |

## H0 conclusion

HIVE has reusable research and scorecard primitives, but the current selector
is a heuristic ranking component rather than a validated research candidate.
No strategy, selector, or portfolio can be labeled `VALIDATED_EVIDENCE_EXISTS`
from this audit. H1 must create immutable candidate, dataset, and all-trial
contracts before H2-H8 may make research or profitability claims.

```text
HIVE_BRAIN_INTEGRATION=DEFERRED
LIVE_TRADING=false
REAL_MONEY=false
```
