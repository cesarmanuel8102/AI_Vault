# Contract-Scoped Quarantine Design

## Intent

Prevent the uncertain SOL/PAXOS order `964` from blocking autonomous work on unrelated contracts while preserving fail-closed handling for that exact order and position.

## Goals

- Quarantine only SOL contract `conId=766137558` and order identity `orderId=964`, `permId=1166274319`, `clientId=19761`, `orderRef=codex-ibkr-paper-30d-p-6ea0925b6b3a`.
- Permit independent sleeves and contracts to research, decide, and execute whenever their own session, certification, reconciliation, capital, and safety gates pass.
- Continue read-only reconciliation of SOL until IBKR reports a terminal order state.
- Reduce closed-session SOL reconciliation to a bounded cadence without consuming model invocations.

## Non-Goals

- Do not bypass broker session evidence or permit writes to a closed venue.
- Do not submit, replace, modify, or cancel order `964` again.
- Do not permit another SOL order while order `964` is non-terminal.
- Do not modify PBR, SLB, sleeve capital, `AUTONOMY_EPOCH_2`, or the 30-day clock.

## Approach

Use contract-scoped eligibility. The quarantine contributes a block only when an action targets the quarantined contract or exact open-order identity. It must not become a global market-data or reconciliation failure. A closed or uncertain SOL session produces a monitor-only result for SOL while the ordinary eligibility calculation continues for every other certified family and owned contract.

Alternative approaches were rejected: disabling the market gate would permit writes against broker-declared closed sessions; clearing the order locally would hide real broker exposure; treating the quarantine as sleeve-wide would unnecessarily suppress unrelated opportunities.

## Verification

- Quarantined SOL action is blocked with an explicit contract-quarantine reason.
- Duplicate/replacement SOL orders remain impossible.
- An unrelated eligible regular or continuous contract reaches research and execution admission.
- Closed SOL monitoring does not call the model and does not emit repeated critical alerts.
- PBR and SLB management eligibility is unchanged.
- Full regression, kernel-manifest verification, and read-only broker reconciliation pass before deployment.
