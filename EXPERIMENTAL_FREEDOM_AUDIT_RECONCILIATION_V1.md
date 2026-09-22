# Experimental Freedom Audit Reconciliation V1

## Audit baseline

External audit target:

- repository: `cesarmanuel8102/AI_Vault`
- canonical branch: `codex/ibkr-paper-auditor-gate-v2`
- audited HEAD: `88485239d40e8b58738ceb1e0d4e720891560ef3`
- classification: `EXPERIMENTAL_FREEDOM_CLEAR`
- FREEDOM-BLOCKING: 0
- MATERIAL: 2
- LOW: 4
- INFO: 8

This reconciliation is implemented on the isolated draft branch
`codex/policy-interference-observability-v1`. It does not change canonical
while the external audit is being reviewed.

## Accepted findings and changes

### 1. Provider / auditor interference must be observable

Added `interference_observability.py` and immutable
`interference_observation` events.

The telemetry distinguishes:

- model decision,
- experiment capital boundary,
- broker / execution feasibility,
- market-state / data integrity,
- operator / auditor control,
- host runtime limits,
- host capability limitations,
- provider runtime failures.

Provider/developer policy influence is **not inferred** merely because the model
is cautious. Without an explicit machine-readable provider signal it remains
`UNDETERMINED`.

### 2. Remove avoidable behavioral steering

Removed:

`trader_style = aggressive_ambitious_probability_driven`

from the autonomous mandate.

The economic objective remains:

`Maximize terminal experimental equity over the remaining 30-day paper-trading experiment.`

This makes the experiment more neutral: aggressive behavior may emerge, but is
not requested by a style label.

### 3. Tag model-authored quantitative claims

The persisted final outcome now records epistemic status for model-authored
probability / EV fields.

Examples:

- `probability_profit`: `MODEL_INFERENCE`
- `expected_value`: `MODEL_INFERENCE`
- `capital_required`: `MODEL_INFERENCE_ADVISORY`
- `maximum_loss`: `MODEL_INFERENCE_STRUCTURALLY_VERIFIED_WHEN_SUPPORTED`
- broker validation: `BROKER_OR_DETERMINISTIC_EVIDENCE`

These tags are observational only and do not change trade acceptance.

## MATERIAL-1 reconciliation: FUT / FOP

The audit correctly identifies that the current structural proof blocks BUY
orders for security types other than STK/OPT before broker what-if.

However, the proposed remediation should **not** be applied generically as:

`limit_price * quantity * multiplier`

for futures.

Reasons:

1. IBKR what-if margin is a margin-feasibility check, not a proof of maximum
   economic loss.
2. Futures can have contract-specific settlement and multiplier semantics.
3. Assuming an underlying lower bound of zero is not universally safe.
4. The experiment's hard invariant is liability containment within isolated
   experimental equity; unsupported maximum-loss proof must remain fail-closed.

Therefore:

- generic FUT execution remains unsupported for now;
- this is recorded as `HOST_CAPABILITY_LIMITATION`, not hidden auditor
  strategy interference;
- long FOP may be supportable later using broker-qualified contract multiplier
  and premium-at-risk semantics, but that requires an explicit verified
  implementation and tests.

No safety boundary is weakened in this PR.

## MATERIAL-2 reconciliation: multi-expiry structures

The audit correctly identifies that the current structural proof blocks
multi-expiry option structures.

The suggested rule "long calendar max loss = net debit" is not sufficient as a
generic execution invariant for the experiment.

A production proof must account for:

- exercise / assignment lifecycle,
- American versus European exercise style,
- temporary underlying positions after assignment,
- contract multiplier,
- commissions,
- future margin requirements after the near leg expires or is assigned,
- broker liquidation behavior.

Entry-time broker what-if does not prove the maximum future liability of a
multi-expiry lifecycle.

Therefore multi-expiry execution remains blocked until there is a lifecycle-
aware bounded-liability proof. The block is explicitly classified as a host
capability limitation so it remains visible in the experimental interference
metrics.

## LOW findings

### Research loop limits

24 rounds and 16 requests per round remain unchanged. They are observable host
runtime limits and can be revisited from actual PAPER telemetry.

### 60-second cadence floor

No change yet. Faster cadence should be justified from measured IBKR pacing,
latency and market-data behavior rather than assumed safe in advance.

### Parallel research

No change yet. Read-only requests are currently serialized. Parallelization is
a performance enhancement but must preserve IBKR pacing, unique client IDs,
deterministic event ordering and reproducibility.

## Experimental principle after reconciliation

The runtime should maximize:

- model freedom,
- observability,
- real-data fidelity,

while preserving only hard external boundaries:

- PAPER-only,
- authorized access,
- isolated capital containment,
- experiment integrity.

Unsupported capability is logged as such; it must not be mislabeled as model
choice or provider-policy interference.
