# IBKR Prerequisite Finalization

This procedure completes the two remaining operational prerequisites for the
Codex 30-day autonomous IBKR paper experiment without arming or starting
trading.

## Preconditions

- Windows PowerShell 5.1.
- Repository available at `C:\AI_VAULT`.
- Local IB Gateway logged into the intended PAPER account and listening on
  `127.0.0.1:4002`.
- Run the finalizer from an elevated PowerShell window.
- The dedicated local auditor identity is expected to be
  `CodexAuditorV1` with SID
  `S-1-5-21-214160970-1890373857-4055601883-1012`.

## Run

```powershell
cd C:\AI_VAULT
git fetch origin
git switch codex/ibkr-paper-auditor-gate-v2
git pull --ff-only
PowerShell.exe -NoProfile -ExecutionPolicy Bypass -File .\FINALIZE_IBKR_PREREQUISITES.ps1
```

The finalizer:

1. performs real read-only PAPER identity/reconciliation against local IBKR;
2. reuses existing auditor provisioning when present;
3. installs and verifies the exact Auditor Runtime V2 fileset;
4. creates a read-only audit export and byte-identical PAPER identity receipt;
5. runs the consolidated V2 probe under the restricted `CodexAuditorV1` token;
6. promotes and evaluates the real V2 receipt;
7. materializes the immutable residual-risk acceptance only when absent;
8. leaves paper order execution unarmed;
9. if Market Data Gate is not already PASS, registers scheduled task
   `CodexIBKRMarketDataGate`.

## Market Data Gate

The scheduled task runs at 09:35 local Eastern time on weekdays while the user
is logged in. IB Gateway must remain logged into PAPER and port 4002 available.

The task performs a clean protocol using SPY, QQQ and IEF:

- three real-time observation windows;
- 315 seconds per window at 5-second cadence;
- 31-minute start-to-start separation;
- regular-session evidence only;
- policy freeze;
- independent real-market-data validation.

Any failed attempt archives its evidence and the next scheduled run starts
clean. On PASS the task unregisters itself.

The evidence protocol intentionally exceeds the minimum freezer requirements of
three >=5-minute windows, >=30-minute start separation, >=65-minute total span,
>=540 accepted observations, and >=180 observations per required symbol.

## Important

Neither script sets `IBKR_AUTONOMOUS_PAPER_ARMED=true`.

Neither script starts `AutonomousExperimentService`.

No live-money path is enabled.

## Evidence

Canonical local reports are written under:

`C:\AI_VAULT\state\ibkr_paper_30d\reports`

Key artifacts:

- `read_only_real_paper_reconciliation.json`
- `auditor_gate_v2_receipt.json`
- `market_observations.jsonl`
- `market_data_policy_v1.json`
- `market_data_validation.json`

Auditor runtime/report evidence is also retained under:

`C:\ProgramData\CodexAuditorV1`

## Check

After the market-data task has completed:

```powershell
cd C:\AI_VAULT
python -m ibkr_paper_30d.prerequisite_tools readiness
Get-ScheduledTask -TaskName CodexIBKRMarketDataGate -ErrorAction SilentlyContinue
```

A completed Market Data Gate has `market_data_gate = PASS`; the scheduled task
should no longer exist.
