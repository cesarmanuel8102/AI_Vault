# HIVE H1 H2 Research Priority

## Decision rule

H1 ranks only the information value of reconciling existing source families to
future H2 candidate specifications. It does not validate, backtest, tune, or
promote them. The V3 cohort remains the canonical starting order because H1
found no bound performance evidence that would justify a reorder.

## Top H2 research priorities

| Rank | H2 candidate | H1 relationship to existing source inventory | H1 rationale |
| ---: | --- | --- | --- |
| 1 | `TSMOM_ENSEMBLE_V1` | Reconcile `cta_trend_following`, `multi_asset_tf`, `trend_following`, and `tsm_forex` only as historical source inputs | Strong economic prior; source code is not a validation receipt. |
| 2 | `DONCHIAN_ATR_V1` | Compare only with trend-family source labels | A simple benchmark can falsify whether historical trend implementations add complexity value. |
| 3 | `ORB_RELATIVE_VOLUME_REPLICATION_V1` | Reconcile `intraday_momentum` and `london_breakout` without claiming equivalence | Tests a precise external hypothesis before adapting legacy intraday code. |
| 4 | `RSI2_CONTROL_V1` | Use mean-reversion sources as provenance context only | Cheap control to quantify parameter and friction fragility. |
| 5 | `PEAD_DATA_FEASIBILITY_V1` | No H0 candidate is a bound PEAD receipt | Point-in-time data feasibility is a prerequisite, not a performance trial. |

## Existing source dispositions that constrain H2

| H1 group | Required H2 behavior if later authorized |
| --- | --- |
| Trend and momentum source files | Start from a new versioned candidate specification; do not reuse source parameters as validated defaults. |
| Carry and options files | Resolve data, financing, curve, option-surface, borrow, cost, and capacity feasibility before a trial. |
| Intraday/breakout files | Build an exact replication baseline before adapting any legacy implementation. |
| Mean-reversion and stat-arb files | Treat as controls or re-audit candidates; require modern OOS and realistic costs. |
| CFD data probe | Do not promote; it is not a strategy candidate. |
| Deferred source files | Require a precise economic hypothesis before consuming H2 capacity. |

## Boundary

```text
H1_IMPLEMENTATION_AUTHORIZED=true
H2_IMPLEMENTATION_AUTHORIZED=false
VALIDATED_STANDALONE=false
SLEEVE_CANDIDATE=false
PAPER_ELIGIBLE=false
LIVE_TRADING=false
REAL_MONEY=false
```

H1 must not produce VALIDATED_STANDALONE, SLEEVE_CANDIDATE, or PAPER_ELIGIBLE.
