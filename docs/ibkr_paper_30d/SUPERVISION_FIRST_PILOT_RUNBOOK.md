# Supervision-First PAPER Pilot Runbook

This runbook advances the approved successor one durable phase at a time. It does
not authorize LIVE access, select an instrument, recommend a trade, or bypass an
authority check. Port `4002` is the only permitted broker API endpoint; port
`4001` must remain absent.

## Required inputs

Set these values from the final Task 10 evidence. Do not infer or substitute any
hash, account, receipt, or path.

```powershell
$Repo = "C:\AI_VAULT_IBKR"
$ApprovedHead = "<FINAL_REVIEWED_HEAD>"
$Config = "<ABSOLUTE_CONFIG_PATH>"
$Evidence = "<ABSOLUTE_FRESH_EVIDENCE_PATH>"
$Authority = "<ABSOLUTE_TRANSITION_AUTHORITY_PATH>"
```

Before any apply, require a clean tracked tree at `$ApprovedHead`, authenticated
PAPER identity, port `4002` only, Read-Only API disabled, zero open orders,
certain executions, exact positions, a fresh lock/process inventory, confirmed
Windows Event Log and external Owner alert delivery, and a complete backup
manifest. A missing, stale, contradictory, or unhashed fact is a `BLOCK`.

## Validate and apply one phase

Validation is always performed first:

```powershell
Set-Location -LiteralPath $Repo

.\INVOKE_IBKR_MULTI_UNIVERSE_MAINTENANCE.ps1 `
  -RepoRoot $Repo `
  -ValidateOnly `
  -PhaseTarget PREPARED `
  -ConfigPath $Config `
  -EvidencePath $Evidence `
  -ApprovedHead $ApprovedHead
```

Only an exact `PASS` for the requested phase permits the corresponding apply:

```powershell
.\INVOKE_IBKR_MULTI_UNIVERSE_MAINTENANCE.ps1 `
  -RepoRoot $Repo `
  -Apply `
  -PhaseTarget PREPARED `
  -ConfigPath $Config `
  -EvidencePath $Evidence `
  -ApprovedHead $ApprovedHead
```

Repeat validate then apply for exactly this order, replacing `PREPARED` above:

1. `PREPARED`
2. `PREDECESSOR_QUIESCED`
3. `PREDECESSOR_RETIRED`
4. `SUCCESSOR_COMMITTED`
5. `SUPERVISION_BOUND`
6. `CANARY_EXCLUSIVE`
7. `CANARY_PASS`
8. `RUNTIME_BOUND`
9. `ACTIVE`

After every apply, rerun validate-only for the committed phase and reconcile
account identity, positions, open orders, executions, transition chain, writer,
execution lock, sleeve ledgers, ownership, and alert delivery. Never batch phases.

## Phase checkpoints

- Through `PREDECESSOR_QUIESCED`, no successor broker write authority exists.
- `PREDECESSOR_RETIRED` requires durable proof that every old launcher is unable
  to reacquire the writer or reach port `4002`.
- `SUCCESSOR_COMMITTED` is the rollback boundary. After it, do not restore an old
  executor or edit receipts/SQLite manually; recover the same successor forward.
- `SUPERVISION_BOUND` requires every inherited position to be owned by
  `REGULAR_SLEEVE`, exact risk-reducing management authority, and both sleeves'
  new-entry authority frozen.
- `CANARY_EXCLUSIVE` permits only the exact Codex-selected, Owner-authorized
  candidate through the sole writer. Ordinary entry authority remains frozen.
- `CANARY_PASS` requires an ordered broker lifecycle, matching receipt chain,
  exact flat-state proof, and reconciled economics. No fill is not a pass.
- `RUNTIME_BOUND` requires the same writer, lock generation, account, successor,
  supervision binding, and authority projection used by every component.
- `ACTIVE` requires fresh DB and broker receipts. Regular entry remains session
  gated; continuous entry remains family-certification and tradability gated.

## Start or validate the service

Validate composition without starting a writer:

```powershell
.\RUN_IBKR_MULTI_UNIVERSE_SERVICE.ps1 `
  -RepoRoot $Repo `
  -ApprovedHead $ApprovedHead `
  -TransitionAuthorityPath $Authority `
  -ValidateOnly
```

Remove `-ValidateOnly` only at the phase where the plan requires the sole
successor writer. The authority file supplies identity; command-line flags do not
grant phase, entry, canary, or management authority.

## Uncertainty and stop conditions

Immediately freeze normal entries and stop phase advancement on any of:

- account, writer, lock, phase, hash, ownership, or reconciliation ambiguity;
- broker disconnect, authentication failure, stale evidence, unknown order state,
  duplicate order, partial-fill uncertainty, or canary cleanup uncertainty;
- predecessor reactivation attempt or any listener/connection involving `4001`;
- missing Event Log or external Owner alert confirmation;
- unexpected broker write count or a process not bound to the approved HEAD.

Persist the event, write Windows Event Log, deliver the external Owner alert, and
preserve exact risk-reducing management of already-owned exposure. Do not delete
locks, edit SQLite, alter receipts, cancel globally, force a canary, or create a
replacement order. Resume only through the documented recovery/reconciliation
path for the same successor.

## Report closure

Generate `SUPERVISION_FIRST_PILOT_REPORT_V1` from exact DB and broker receipts.
The report must include HEAD, transition/event hashes, account, writer/lock,
inherited bindings, sleeve economics, family/canary lifecycle, orders, fills,
positions, accepted model cycles, alert delivery, and broker-write counts. A
`PASS` report is evidence of coherent state; it is not a profitability claim and
does not force Codex to trade.
