# Day 1 Persistent PAPER Launch Design

Date: 2026-09-23
Status: OWNER-REVIEW REVISIONS INCORPORATED; PENDING FINAL OWNER APPROVAL
Repository: `C:\AI_VAULT_IBKR`

## Purpose

Start the authorized 30-day, USD 500 IBKR PAPER experiment as soon as every
material gate can pass, then keep the authoritative autonomous service running
without depending on the current Codex or terminal session. The design must
never connect to LIVE, invent a gate result, force a trade, or create two
execution authorities.

The immutable scheduled experiment start remains
`2026-09-23T13:30:00Z`. If prerequisites delay execution, evidence records the
actual service start and delay without rewriting the clock.

## Current State

- IBKR Gateway PAPER listens on `127.0.0.1:4002`.
- The expected account identity is bound by SHA-256 and resolves to exactly one
  `DU` namespace account.
- Fresh read-only broker reconciliation is PASS with no positions, open orders,
  executions, or broker writes.
- Auditor Gate V2 is PASS against the current PAPER identity receipt.
- `CodexIBKRMarketDataGate` is registered at highest privilege for
  2026-09-24 09:35 America/New_York.
- Its currently installed three-hour execution limit is sufficient for market
  collection but not for the 30-day service. The implementation changes the
  registration to a 31-day limit with bounded restart settings, and the Owner
  must rerun the elevated finalizer once after implementation to apply those
  task settings.
- Market policy is not frozen, the experiment database does not exist, PAPER is
  unarmed, and Day 1 has not started.
- Integer-second IBKR timestamps now carry explicit 1000 ms resolution through
  observation evidence. Quote ages outside resolution plus measured half-RTT
  still fail closed.

## Architecture

The existing `CodexIBKRMarketDataGate` task remains the only Windows scheduled
launch authority. Its existing action continues to call
`RUN_IBKR_MARKET_DATA_GATE.ps1 -Scheduled`; no second task or detached process
is introduced.

In scheduled mode the script performs these stages in order:

1. Collect the three regular-session windows and freeze/validate
   `MARKET_DATA_POLICY_V1` using the existing evidence-backed implementation.
2. Generate a unique launch-attempt UUID and run
   `FINALIZE_IBKR_PREREQUISITES.ps1 -SkipTaskRegistration -LaunchAttemptId`
   in the same elevated task token. This validates the pre-existing explicit
   Owner authorization, creates a fresh read-only identity receipt and matching
   fresh Auditor V2 receipt, then binds both hashes to that attempt UUID.
3. Invoke `python -m ibkr_paper_30d.day1_launch --launch-attempt-id` with the
   same UUID in the foreground.
4. Keep the scheduled task alive for the lifetime of the authoritative Python
   service. The task must not unregister itself before a terminal experiment
   state.

Task Scheduler supplies persistence, `IgnoreNew` multiple-instance behavior,
start-when-available behavior, a weekday 09:35 trigger plus Owner-logon
recovery trigger on the same task, a 31-day execution limit, and bounded
restart attempts separated by five minutes. The Python launch boundary supplies a
second database-backed single-instance guard so direct or accidental duplicate
invocations fail closed. The task uses the interactive Owner token because
IBKR Gateway and Codex credentials live in that session; after logout or reboot,
start-when-available resumes only after the Owner session and Gateway return.

## Launch Boundary

`ibkr_paper_30d.day1_launch` owns orchestration but no strategy or broker-write
methods. It imports the existing authoritative components and performs:

1. Validate the approved repository root and ensure system UTC is not before
   `2026-09-23T13:30:00Z`.
2. Validate the caller's launch-attempt UUID against the fresh reconciliation
   and Auditor V2 receipt hashes. Load the read-only receipt and require host
   `127.0.0.1`, port `4002`, PAPER mode, observed managed-account count one,
   sanitized `DU` namespace evidence, heartbeat PASS, complete
   positions/executions/open-orders visibility, and reconciliation PASS.
3. Export only the receipt's expected account hash to the child process as
   `IBKR_PAPER_ACCOUNT_SHA256`.
4. Evaluate fresh Runtime Auditor V2 and Runtime Market Data gates. New-trade
   evaluation must be PASS; delayed/frozen data remains forbidden.
5. Open the canonical SQLite database, require `PRAGMA integrity_check=ok`,
   validate the current schema, and require a valid experiment ledger.
6. Load and validate the immutable clock with start `2026-09-23T13:30:00Z`,
   end `2026-10-23T13:30:00Z`, 30 days, and USD 500. Delayed launch consumes
   clock time; the launcher never initializes or rewrites the clock.
7. Consume and validate the exact Owner authorization phrase
   `AUTHORIZE 30-DAY PAPER EXPERIMENT`, created only during an explicit
   elevated Owner finalizer invocation and bound to that clock hash. The
   scheduled finalizer and launcher never create authorization.
8. Require monotonic kill-switch history: exactly the initial explicit CLEAR
   and no TRIGGERED event anywhere later. A TRIGGERED event is permanent for
   this experiment even if a later CLEAR row exists.
9. Set `IBKR_AUTONOMOUS_PAPER_ARMED=true` only in the service process
   environment and instantiate `AutonomousExperimentService` with
   `execute_paper=True`, `gpt-5.6-sol`, reasoning effort `max`, five-minute scan
   cadence, and one-minute position cadence.
10. Run the service in the foreground and persist launch, first-cycle, delay,
    PID, gate, and terminal/failure evidence.

Both the environment arm and `--execute-paper` semantics remain mandatory.
The existing executor remains the only code allowed to place, cancel, modify,
reduce, or close PAPER orders, using stable execution client `19761`.

## State And Evidence

The canonical database remains
`state/ibkr_paper_30d/autonomous.sqlite3`. Launcher evidence is written under
`state/ibkr_paper_30d/launch/` using canonical JSON, SHA-256, atomic replace,
and append-only JSON Lines where history is required.

Evidence includes:

- scheduled and actual start UTC plus delay seconds;
- repository HEAD and runtime file hashes;
- identity, reconciliation, auditor, market-policy, and market-validation
  receipt hashes;
- clock and owner-authorization event hashes;
- kill-switch state;
- requested model and reasoning effort;
- process ID, task identity, startup time, first-cycle identifier, and latest
  heartbeat;
- sanitized reason codes and corrective-action history.
- launch-attempt UUID plus fresh reconciliation and Auditor V2 receipt hashes.

Raw account IDs, credentials, tokens, and prompts are forbidden from launch
evidence.

## Recovery And Restart

Transient Gateway, market-data, or Codex-provider failures use bounded
exponential backoff with sanitized logging. The service already handles
recoverable runtime failures internally.

If the authoritative process exits unexpectedly, a retry must first reacquire
the single-instance guard and rerun identity, reconciliation, auditor, market,
database, and ledger gates. Existing clock and authorization must match. A
triggered kill switch, ambiguous order ownership, uncertain broker write,
database corruption, identity mismatch, login/2FA requirement, or LIVE route
is terminal `OWNER_ACTION_REQUIRED`; no automatic restart or kill-switch clear
is allowed.

## Idempotence

Repeated scheduled or manual invocation must produce one of three outcomes:

- attach to/report the one valid running authority without launching another;
- safely resume after fresh reconciliation when the previous authority is
  proven absent and controls remain CLEAR; or
- remain fail-closed with explicit reason codes.

Clock, authorization, policy, and append-only ledger artifacts are never
silently replaced.

Native autonomous discovery remains active throughout the experiment. No fixed
symbol, asset-class, strategy, expiration, strike, market, or session whitelist
is introduced. Capability-discovery and candidate-screen results are advisory;
actual IBKR permissions, contract qualification, what-if, market data, and
execution gates remain authoritative.

## Testing

Implementation follows TDD and covers:

- integer-second timestamp resolution and out-of-bound future timestamps;
- pre-start refusal and immutable clock mismatch;
- PAPER endpoint/identity and LIVE-route refusal;
- missing or blocked auditor, reconciliation, market-data, ledger, and model
  gates;
- explicit elevated Owner-boundary clock, authorization, and initial kill-switch creation;
- explicit elevated Owner authorization with no launcher synthesis;
- per-attempt freshness binding across reconciliation and Auditor V2;
- refusal to auto-clear a later kill switch;
- refusal to rehabilitate any historical triggered kill switch;
- double-start exclusion and stale PID handling;
- scheduled PowerShell chaining, exit codes, and persistent foreground service;
- recovery requiring reconciliation before restart;
- zero broker-write calls in every launcher/preflight test;
- executor and IB transport write tripwires wired into integration tests;
- empty-candidate Native discovery and fail-closed unknown cycle statuses;
- unchanged auditor runtime and trust-anchor hashes.

Verification includes the complete `tests/ibkr_paper_30d` suite, PowerShell AST
parsing, a dry-run launch against fakes, `git diff --check`, and live read-only
PAPER checks. No paper order is submitted as a launch test.

After verification, the Owner reruns `FINALIZE_IBKR_PREREQUISITES.ps1` once in
an elevated PowerShell. That idempotent run refreshes Auditor V2 and replaces
the already registered task with the reviewed long-running settings. No broker
write occurs during installation.

## Success Criteria

Success is `AUTONOMOUS_PAPER_EXPERIMENT_RUNNING` with fresh PASS evidence,
immutable clock and owner authorization, CLEAR kill switch, one armed PAPER
service, a persisted first autonomous cycle, growing logs, valid database and
ledger, and no LIVE-capable route. `NO_TRADE` is a valid first-cycle decision.
