# Codex IBKR Paper 30-Day Preflight V3

Generated: 2026-09-20

`PAPER_ONLY=true`
`LIVE_ALLOWED=false`
`REAL_MONEY_ALLOWED=false`
`REAL_PAPER_ORDER_WRITE_AUTHORIZED=false`
`TEST_ORDER_AUTHORIZED=false`
`DIRECTIONAL_TRADING_AUTHORIZED=false`
`AUTONOMOUS_TRADING_STATUS=BLOCKED`

## Verification Summary

| Gate | Status | Evidence |
|---|---|---|
| PAPER_ACCOUNT_IDENTITY_GATE | PASS | Local Gateway configuration is consistently paper; one DU managed identity matched account summary and the protected expected hash. |
| REAL_IBKR_READ_ONLY_IDENTITY_GATE | PASS | Authenticated local API session on port 4002 with seven-factor identity proof. |
| BROKER_RECONCILIATION_GATE | PASS | Account summary, cash, dated settled cash, buying power, positions, open orders, executions, broker time, and heartbeat were read successfully. |
| MARKET_DATA_GATE | BLOCK | SPY and QQQ snapshots reported realtime type but returned no bid, ask, last, or quote timestamp on Sunday. No thresholds were guessed. |
| TRADER_INVOCATION_REAL_CODEX_GATE | PASS | Real `codex exec` invocation used `gpt-5.5` at medium effort and returned schema-valid `NO_TRADE`; no tool, broker, lock, or secret access occurred. |
| AUDITOR_ISOLATION_GATE | BLOCK | Dedicated low-privilege account provisioning was denied without administrator rights; current-process probes retained forbidden capabilities. |
| OWNER_ALERT_GATE | PASS | SMTP and Windows Event Log delivery were confirmed for 2FA reauth, kill switch, and broker heartbeat timeout simulations. |
| RECOVERY_GATE | PASS | Fail-closed recovery transitions and reconciliation prerequisites are covered by the verified local suite. |
| EXECUTION_LOCK_GATE | PASS | Local deterministic suite. |
| RISK_ENGINE_GATE | PASS | Local deterministic suite. |
| SUBLEDGER_GATE | PASS | Local deterministic suite. |
| PRETRADE_FREEZE_GATE | PASS | Local deterministic suite. |
| FAULT_INJECTION_GATE | PASS | Local deterministic suite. |

## Paper Identity

The exact account identity is bound in `Secrets/expected_paper_account_identity_v1.json`. The file contains only a SHA-256 digest and a short fingerprint; it contains no raw account ID. ACL inheritance is removed and access is restricted to the Owner account and SYSTEM.

The real read-only report is `state/ibkr_paper_30d/reports/read_only_real_paper_reconciliation.json`. All outbound IB API messages were checked against the explicit read-only transport allowlist. No order submit, cancel, or modify message was attempted.

The Codex IBKR connector was unavailable in this execution environment, so connector comparison is recorded as `UNAVAILABLE`. The local-session identity and account-summary identity were consistent.

## Market Data

Observed behavior is `UNAVAILABLE` for policy calibration. Although IB returned market-data type 1, both representative snapshots lacked prices and quote timestamps. Therefore no defensible values have been frozen for:

- `MAX_QUOTE_AGE_FOR_NEW_TRADE_MS`
- `MAX_QUOTE_AGE_FOR_OPEN_POSITION_MANAGEMENT_MS`
- `MAX_CLOCK_SKEW_MS`
- `REQUIRE_REALTIME_FOR_NEW_TRADE`

`MARKET_DATA_POLICY_FROZEN=false`

## Auditor Isolation

An actual attempt to provision the dedicated `CodexAuditorV1` local account failed with access denied because the current Windows session is not elevated. The current-process denial probe confirmed access to Secrets, broker/lock imports, and live SQLite mutation, so it cannot represent an isolated Auditor.

`AUDITOR_ISOLATION_GATE=BLOCK`

## 2FA And Recovery

The state model now includes the exact `BROKER_RECONNECTING` state. Tests verify disconnect, reconnect, 2FA-required, authentication failure, reconciliation-required, and ready behavior. The 2FA critical alert was externally delivered with `OWNER_ACTION_REQUIRED=true`; the system remains paused after authentication until reconciliation and execution-lock recovery prerequisites pass.

No actual 2FA challenge was instrumented during this run. The authenticated Gateway was followed by a full read-only reconciliation before the broker evidence was accepted.

## Test Evidence

`TEST_COUNT=222`
`PASS=222`
`FAIL=0`

Machine-readable evidence is in `state/ibkr_paper_30d/reports/updated_gate_matrix.json`.

## Unresolved Blockers

1. Prove OS-level Auditor denials under a restricted token or dedicated low-privilege account.
2. Collect actual timestamped market quotes during an eligible market-data session and freeze policy values from measured evidence.

`READY_FOR_HARMLESS_PAPER_LIFECYCLE_TEST=false`
`AUTONOMOUS_TRADING_STATUS=BLOCKED`

No paper order was submitted, cancelled, or modified. The 30-day experiment was not started.
