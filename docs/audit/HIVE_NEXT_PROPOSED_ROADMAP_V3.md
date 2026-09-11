# HIVE-NEXT Proposed Roadmap V3

## Roadmap

| Phase | Objective | Required output | Promotion boundary |
| --- | --- | --- | --- |
| H0 | Forensic source inventory and lineage | Immutable static inventory and unknowns | Completed historically; no strategy promotion |
| H1 | Existing sleeve economic audit | Candidate/evidence/data-gap baseline for existing sources | Candidate specification only; no QC trial or paper eligibility |
| H2 | QC Strategy Research and Validation Lab | Deterministic trial receipts with locked OOS and stress evidence | At most `SLEEVE_CANDIDATE` |
| H3 | Sleeve Admission and Portfolio Interaction | Marginal portfolio comparison and sleeve decision | Admitted sleeve candidate only |
| H4 | Dynamic Universe and Selector SHADOW | Versioned shadow decision versus simple baselines | Evidence for selector value; no trade authority |
| H5 | Prospective QC PAPER Campaign | Forward-only paper receipt with locked versions and degradation evidence | Research conclusion only; no live-trading authority |

## Proposed H1 scope

H1 begins with the H0 static inventory, not with another strategy build. It
creates the contracts required to answer the following for each existing source:

```text
What is the exact candidate?
Which economic family does it claim?
What data, parameters and execution assumptions are missing?
Does a source hash identify a deterministic hypothesis?
Is it a candidate for re-audit, data feasibility, deferment, or early rejection?
```

H1 ends with a bounded queue for H2 and no performance claim.

## H2 execution order after H1 authorization

1. `TSMOM_ENSEMBLE_V1`
2. `DONCHIAN_ATR_V1`
3. `ORB_RELATIVE_VOLUME_REPLICATION_V1`
4. `RSI2_CONTROL_V1`
5. `PEAD_DATA_FEASIBILITY_V1`

The order is conditional. If the H1 data contract invalidates a candidate, it
is rejected or deferred rather than silently substituted with an easier test.
Trend/carry, cross-sectional momentum, bounded VRP and relative-value baskets
remain queued based on their data/cost feasibility and H1 information gain.

## H3 and H4 decision hierarchy

```text
candidate evidence -> H2 standalone validation
validated candidate -> H3 portfolio/sleeve admission
admitted sleeve -> H4 selector shadow comparison
selector or static baseline -> H5 prospective paper
```

The universe is a separate input to every stage. Allocation remains separate
from both the selector and strategy code.

## H5 success and failure definitions

H5 cannot begin until the required evidence is complete. It is successful only
as a prospective observation campaign with version-locked inputs, real elapsed
time, decision count, cost/fill accounting and degradation monitoring. It may
conclude `REJECT`, `RESEARCH_ONLY`, or support a later paper-readiness decision;
it cannot authorize live trading or real money.

## Governance invariants

```text
H1_IMPLEMENTATION_AUTHORIZED=false
HIVE_BRAIN_INTEGRATION=DEFERRED
PERSISTENT_AGENT_LOOP=DEFERRED
SCHEDULERS=DISABLED
HUMAN_FINAL_AUTHORITY=true
AUTO_MERGE=false
CANONICAL_LOCAL_SYNC=false
LIVE_TRADING=false
REAL_MONEY=false
```

## Owner decision requested

```text
RECOMMENDED_HIVE_NEXT_ROADMAP=H0,H1,H2,H3,H4,H5
H0_STATUS=HISTORICAL_STATIC_FORENSIC_BASELINE
NEXT_EXECUTABLE_PHASE=H1_EXISTING_SLEEVE_ECONOMIC_AUDIT
FIRST_RESEARCH_COHORT=TSMOM,DONCHIAN,ORB,RSI2,PEAD_DATA_FEASIBILITY

H1_IMPLEMENTATION_AUTHORIZED=false
```

The next action is Owner review of this proposal. No H1 implementation,
QuantConnect experiment, selector work, paper trading, or Brain integration is
authorized by this roadmap.
