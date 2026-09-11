# HIVE-NEXT V3 Roadmap Reconciliation

## Decision

The canonical repository contains H0 only. The previously discussed H0-H5
shape is retained, with its research lifecycle made explicit and with sleeve
admission placed before selector work and paper eligibility.

H0 remains historical. This proposal does not rewrite it or claim it completed
economic validation.

| Old phase | Proposed phase | Capability | Current reality | Action | Rationale |
| --- | --- | --- | --- | --- | --- |
| H0 inventory and lineage | H0 Current-state forensic inventory and lineage | Static source and evidence boundary | Completed historical source audit; 25 candidates are `RESEARCH_ONLY` | KEEP | H0 is the factual baseline, not a performance assertion. |
| H1 sleeve/candidate economics | H1 Existing sleeve economic audit | Reconstruct evidence and define the baseline economics of existing candidates | Not implemented; datasets, trials, QC and paper lineage are unbound | KEEP, narrow | It must establish what can be tested before new research is added. |
| H2 experiment minimum | H2 QC Strategy Research and Validation Lab | Deterministic QC research trials, IS/OOS and stress receipts | Not implemented | MERGE and expand | A single green backtest is insufficient. |
| H3 adaptive universe and reference portfolio | H3 Sleeve Admission and Portfolio Interaction | Decide whether standalone candidates improve the portfolio after costs | Not implemented | MOVE | Admission must occur before a dynamic selector can choose candidates. |
| H4 selector shadow | H4 Dynamic Universe and Selector SHADOW | Evaluate dynamic preference versus simple baselines | Not implemented | KEEP, constrain | Only H3 survivors may enter shadow selection. |
| H5 paper campaign | H5 Prospective QC PAPER Campaign | Prospective evidence under locked versions and lineage | Not implemented | KEEP, harden | Historical replay and synthetic elapsed time are not prospective paper. |

## V3 phase contract

### H0 - Current-state forensic inventory and lineage

Inputs are source bytes and immutable historical records. Outputs are a bounded
inventory, known unknowns, and no winner. H0 cannot promote an existing
candidate.

### H1 - Existing sleeve economic audit

H1 consumes the H0 inventory and creates a non-promotional baseline for every
existing candidate: candidate identity, source hash, hypothesized family,
minimum data requirements, likely trading frequency, expected cost drivers,
and evidence gaps. It may classify candidates as `EXISTING_REAUDIT`,
`DATA_FEASIBILITY_ONLY`, `DEFERRED`, or `REJECT_EARLY`. It does not run a QC
trial or produce paper eligibility.

### H2 - QC Strategy Research and Validation Lab

H2 turns a selected candidate into a versioned deterministic QC experiment.
It binds the code SHA, data specification, universe, parameter manifest,
locked IS/OOS split, walk-forward protocol, benchmark, execution assumptions,
metrics, and artifact hashes. Its maximum positive output is
`SLEEVE_CANDIDATE`.

### H3 - Sleeve Admission and Portfolio Interaction

H3 compares a valid standalone candidate against the eligible portfolio without
the candidate and with the candidate. It evaluates marginal net return, risk,
drawdown, turnover/cost, tail behavior, capacity and regime correlation. The
only outcomes are `REJECT`, `KEEP_RESEARCH_ONLY`,
`ADD_TO_EXISTING_SLEEVE`, or `CREATE_NEW_SLEEVE_CANDIDATE`.

### H4 - Dynamic Universe and Selector SHADOW

H4 first distinguishes `UNIVERSE`, `STRATEGY`, `SLEEVE`, `SELECTOR`, and
`ALLOCATION`. The selector consumes only H3-admitted candidates, operates in
shadow, and must beat defined simple baselines net of turnover and costs. It
cannot allocate production capital or promote an unvalidated candidate.

### H5 - Prospective QC PAPER Campaign

H5 begins only after H2, H3, and any applicable H4 evidence. It locks strategy,
selector, allocation, universe, data, and execution versions before
`PAPER_START`; records real calendar time and decisions; and measures
degradation against the validation receipt. Historical replay is not paper.

## Non-negotiable transition rules

```text
H0 -> H1: source/evidence baseline only
H1 -> H2: a candidate is specified and its data feasibility is known
H2 -> H3: candidate is VALIDATED_STANDALONE or SLEEVE_CANDIDATE
H3 -> H4: candidate or sleeve is admitted; simple baselines are defined
H3/H4 -> H5: evidence and version locks are complete

GREEN_BACKTEST -> PAPER_ELIGIBLE: FORBIDDEN
H2 -> PAPER_ELIGIBLE: FORBIDDEN
HIVE -> BRAIN runtime integration: DEFERRED
```

## Required conceptual separation

| Concept | Decision it owns | It must not decide |
| --- | --- | --- |
| `UNIVERSE` | Where economically tradable opportunities exist | Whether a signal has edge or how much capital it receives |
| `STRATEGY` | How data becomes a trade/exposure proposal | Portfolio eligibility or portfolio size |
| `SLEEVE` | Grouping of economically related admitted strategies/exposures | Dynamic preference among unrelated sleeves |
| `SELECTOR` | Preference among validated candidates/sleeves in shadow | Universe construction, proof of edge, or final allocation |
| `ALLOCATION` | Joint risk, concentration, capacity and capital distribution | Candidate validation or strategy discovery |

## Reconciliation outcome

```text
RECOMMENDED_HIVE_NEXT_ROADMAP=H0,H1,H2,H3,H4,H5
H0_STATUS=HISTORICAL_STATIC_FORENSIC_BASELINE
NEXT_EXECUTABLE_PHASE=H1_EXISTING_SLEEVE_ECONOMIC_AUDIT
H1_IMPLEMENTATION_AUTHORIZED=false
```
