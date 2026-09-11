# HIVE-NEXT Strategy Catalog V3

## Reading this catalog

This catalog is a research queue, not a list of approved systems. `Evidence
prior` estimates whether the economic hypothesis merits falsification work; it
is not a validation result. Every candidate begins `RESEARCH_ONLY` until H2
and H3 produce versioned evidence.

```text
GREEN_HIGH_PRIOR: strong independent economic motivation, still unvalidated here
YELLOW_MEDIUM_PRIOR: plausible, but execution, decay, or specificity is material
RED_LOW_OR_MIXED_PRIOR: weak, mixed, or fragile prior; test only if cheap/informative
RED_PARAMETERIZABLE: rules can be formalized but lack independent evidence
RED_NOT_FORMALIZED: a claim or narrative without sufficient deterministic rules
```

## Existing candidates requiring re-audit

All listed candidates are sourced from the H0 static inventory and remain
`RESEARCH_ONLY`. Family and action below are classification proposals, not
claims about the source implementation.

| Candidate IDs | Inferred family | V3 classification | Evidence prior | H1 action |
| --- | --- | --- | --- | --- |
| `trend_following`, `cta_trend_following`, `multi_asset_tf`, `mtf_trend`, `trend_pullback`, `tsm_forex` | Trend / time-series momentum | `EXISTING_REAUDIT` | `GREEN_HIGH_PRIOR` | Map overlap, instruments, rules and data feasibility before retaining more than one benchmark. |
| `carry_trade`, `momentum_carry` | Carry / momentum-carry | `DATA_FEASIBILITY_ONLY` | `GREEN_HIGH_PRIOR` | Prove point-in-time curve, roll and financing data before a performance trial. |
| `intraday_momentum`, `london_breakout` | Intraday momentum / breakout | `EXISTING_REAUDIT` | `YELLOW_MEDIUM_PRIOR` | Determine whether either is an exact, reproducible ORB or a distinct hypothesis. |
| `mean_reversion_eq`, `mean_reversion_fut`, `multi_asset_mr`, `commodity_mr`, `vol_regime_mr`, `session_cont_rev` | Mean reversion | `EXISTING_REAUDIT` | `YELLOW_MEDIUM_PRIOR` | Use as controls; identify all tuning and execution assumptions. |
| `stat_arb_pairs` | Relative value / pairs | `EXISTING_REAUDIT` | `YELLOW_MEDIUM_PRIOR` | Require cointegration, formation/holding separation and borrow/cost feasibility. |
| `tactical_momentum`, `mtf_pullback` | Tactical momentum / pullback | `EXISTING_REAUDIT` | `YELLOW_MEDIUM_PRIOR` | Define exact signal and distinguish from trend benchmarks. |
| `forex_v1`, `fusion_v1`, `ibkr_10k_growth`, `test_cfd_v2` | Mixed or venue-specific | `DEFERRED` | `RED_LOW_OR_MIXED_PRIOR` | Do not consume research capacity until a falsifiable economic specification exists. |
| `yoel_options`, `yoel_sai` | Options / mentor-derived | `DATA_FEASIBILITY_ONLY` | `RED_PARAMETERIZABLE` | Require deterministic rules, bounded risk and realistic option data before a trial. |

## New research candidates

| Candidate ID | Family | Economic hypothesis | Status | Evidence prior | Key blocker |
| --- | --- | --- | --- | --- |
| `TSMOM_ENSEMBLE_V1` | Time-series momentum | Diversified, volatility-aware trend can earn premia over liquid instruments | `NEW_CANDIDATE` | `GREEN_HIGH_PRIOR` | Universe, continuous-price and volatility-targeting specification |
| `DONCHIAN_ATR_V1` | Trend breakout | Simple breakout rules offer a robust trend benchmark | `NEW_CANDIDATE` | `GREEN_HIGH_PRIOR` | Avoiding parameter-search and defining roll/transaction assumptions |
| `TREND_CARRY_ENSEMBLE_V1` | Trend plus carry | Complementary trend and carry exposures improve portfolio robustness | `DATA_FEASIBILITY_ONLY` | `GREEN_HIGH_PRIOR` | Point-in-time curves, rolls, financing and carry definitions |
| `ORB_RELATIVE_VOLUME_REPLICATION_V1` | Intraday momentum | Stocks-in-play filters may make a published ORB hypothesis viable after costs | `NEW_CANDIDATE` | `YELLOW_MEDIUM_PRIOR` | Point-in-time relative volume, spreads/slippage, shortability and locked post-publication OOS |
| `RSI2_CONTROL_V1` | Short-horizon mean reversion | A simple rule is useful as a falsification control, not a core alpha claim | `NEW_CANDIDATE` | `YELLOW_MEDIUM_PRIOR` | Neighboring-parameter robustness and recent OOS |
| `PEAD_DATA_FEASIBILITY_V1` | Event alpha | Conditional earnings drift could exist only with correct point-in-time fundamentals and costs | `DATA_FEASIBILITY_ONLY` | `YELLOW_MEDIUM_PRIOR` | Point-in-time surprise/consensus data and post-publication decay |
| `CROSS_SECTIONAL_MOMENTUM_V1` | Cross-sectional momentum | Low-turnover relative strength may complement time-series trend | `NEW_CANDIDATE` | `GREEN_HIGH_PRIOR` | Universe survivorship controls, borrow assumptions and turnover |
| `BOUNDED_VRP_BENCHMARK_V1` | Volatility risk premium | Bounded-risk premium harvesting may survive costs while containing tail exposure | `DATA_FEASIBILITY_ONLY` | `YELLOW_MEDIUM_PRIOR` | Option surface, realistic fills, tail scenarios and capital/capacity |
| `RELATIVE_VALUE_BASKETS_V1` | Relative value | Diversified baskets may be more robust than naive pairs | `DEFERRED` | `YELLOW_MEDIUM_PRIOR` | Basket construction, borrow, cointegration stability and execution |
| `CARDONA_EXACT_V1`, `CARDONA_NORMALIZED_V1` | Rule-based discretionary claim | Exact and normalized versions are distinct falsifiable hypotheses | `EXISTING_REAUDIT` | `RED_PARAMETERIZABLE` | Independent rule source, non-stationary thresholds and OOS |

## Early rejection and deferment

| Class | Treatment | Rationale |
| --- | --- | --- |
| Naked short strangles and unbounded premium selling | `REJECT_EARLY` | Tail risk is incompatible with the proposed bounded-risk research priority. |
| Raw PEAD on fixed ticker lists | `REJECT_EARLY` | Lacks point-in-time data and a defensible universe. |
| Naive correlation pairs | `REJECT_EARLY` | Correlation alone is not a stable relative-value thesis. |
| Marketing-only or unformalized mentor claims | `DEFERRED` or `RED_NOT_FORMALIZED` | Narrative cannot receive a validation budget. |
| CFD/synthetic-index transfers | `DEFERRED` | Market microstructure and execution do not transfer without separate evidence. |

## First proposed research cohort

H1 must first establish data feasibility and exact candidate specifications.
Conditional on that gate, the first H2 cohort is intentionally five items:

| Order | Candidate | Why now | Cheapest disproving test | Data ready now | Expected information gain | Stop condition |
| --- | --- | --- | --- | --- | --- |
| R01 | `TSMOM_ENSEMBLE_V1` | Strong prior and a liquid, slow reference family | Fixed 3/6/9/12-month ensemble versus simple benchmark with costs | `UNVERIFIED` | High: determines whether current trend sources merit consolidation | No robust OOS contribution after modest cost/parameter perturbations |
| R02 | `DONCHIAN_ATR_V1` | Independent, interpretable trend baseline | Pre-registered 20/55-channel family with volatility scaling | `UNVERIFIED` | High: separates generic trend exposure from overfit source code | Only a narrow parameter wins or OOS fails |
| R03 | `ORB_RELATIVE_VOLUME_REPLICATION_V1` | High potential but fragile/expensive claim | Exact published-style replication before any adaptation | `UNVERIFIED` | High: resolves whether intraday work deserves further spend | Post-publication OOS or execution stress removes net edge |
| R04 | `RSI2_CONTROL_V1` | Cheap negative/control experiment | Neighboring threshold and friction test on liquid ETFs | `UNVERIFIED` | Medium: calibrates the lab against a common weak prior | Edge vanishes outside a narrow threshold or after modest friction |
| R05 | `PEAD_DATA_FEASIBILITY_V1` | Avoids wasting work on an untestable event thesis | Verify point-in-time SUE, calendar and liquidity availability | `UNKNOWN_UNBOUND` | High: immediate go/no-go for expensive event research | Required point-in-time lineage is unavailable or materially incomplete |

`TREND_CARRY_ENSEMBLE_V1`, `CROSS_SECTIONAL_MOMENTUM_V1`, and
`BOUNDED_VRP_BENCHMARK_V1` are queued after the first cohort because their
economic priors are good but their data/cost contracts need explicit proof.

## Candidate contract fields

Every candidate entering H1 or H2 must provide:

```text
candidate_id
family
economic_hypothesis
signal_definition_status
data_requirements
point_in_time_requirement
expected_holding_period
expected_turnover
primary_cost_risks
capacity_concerns
known_failure_modes
regime_dependency
portfolio_role
evidence_prior
implementation_complexity
data_feasibility
falsification_cost
research_priority
```

Absent fields fail closed to `RESEARCH_ONLY`; they do not inherit presumed
values from a source file, a historical report, or an external paper.
