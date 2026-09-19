# HIVE H1 Evidence Gap Matrix

## Interpretation

The H0 inventory is source-bound. Every other evidence category below is
`UNKNOWN_UNBOUND` for all 25 candidates unless an immutable, candidate-specific
receipt binds it to code, data, parameters, period, and result. This is a
finding, not an assertion that no historical run ever occurred.

| Evidence category | H1 status | Why it cannot be promoted |
| --- | --- | --- |
| Candidate source path and SHA-256 | Bound through H0 | Proves source presence only. |
| Dataset identity and point-in-time lineage | `UNKNOWN_UNBOUND` | No immutable candidate dataset manifest. |
| QC project and algorithm identity | `UNKNOWN_UNBOUND` | No source-bound project/algorithm receipt. |
| Backtest metrics | `UNKNOWN_UNBOUND` | A metric without full code/data/parameter/period binding is non-evidence. |
| IS interval | `UNKNOWN_UNBOUND` | No canonical interval receipt. |
| Locked OOS interval | `UNKNOWN_UNBOUND` | No locked evaluation receipt. |
| Walk-forward evidence | `UNKNOWN_UNBOUND` | No governed walk-forward definition or artifact. |
| Cost and slippage model | `UNKNOWN_UNBOUND` | No candidate-bound fee, fill, slippage, or borrow receipt. |
| Stress evidence | `UNKNOWN_UNBOUND` | No candidate-bound regime, tail, friction, or turnover result set. |
| Paper and execution evidence | `UNKNOWN_UNBOUND` | No candidate-bound prospective paper or execution receipt. |
| Selector linkage | `UNKNOWN_UNBOUND` | H0 selector inputs are not validation-lineage bound. |
| Sleeve/portfolio linkage | `UNKNOWN_UNBOUND` | No canonical sleeve membership/allocation contract exists. |

## Economic metric rule

The following fields remain `UNKNOWN_UNBOUND` for every candidate: gross
return, net return, CAGR, Sharpe, Sortino, drawdown, volatility, win rate,
turnover, trade count, holding period, fees, slippage, borrow cost, capacity,
capital requirement, tail behavior, and regime behavior.

H1 does not estimate these metrics from partial logs, filenames, screenshots,
or manually copied numbers. A future H2 receipt must bind them to a versioned
candidate and full QC experiment contract.

## Gate implication

```text
SOURCE_BOUND_ONLY -> H1 audit disposition
SOURCE_BOUND_ONLY -> VALIDATED_STANDALONE: FORBIDDEN
SOURCE_BOUND_ONLY -> SLEEVE_CANDIDATE: FORBIDDEN
SOURCE_BOUND_ONLY -> PAPER_ELIGIBLE: FORBIDDEN

H2_IMPLEMENTATION_AUTHORIZED=false
LIVE_TRADING=false
REAL_MONEY=false
```
