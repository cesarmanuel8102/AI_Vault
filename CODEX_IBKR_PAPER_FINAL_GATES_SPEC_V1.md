# Codex IBKR Paper Final Gates Specification V1

Status: APPROVED FOR IMPLEMENTATION PLANNING ONLY
Date: 2026-09-20
Baseline: `d04203b92feb5d3f74d8e0da58b4eb57a91b3fd9`

## 1. Purpose And Authority

This specification defines the two remaining pre-lifecycle controls for the autonomous IBKR paper experiment:

1. evidence-backed `MARKET_DATA_POLICY_V1`; and
2. reproducible OS-level isolation for `CODEX_DECISION_AUDITOR_V1`.

The implementation has no broker order authority, trading-decision authority, or permission to modify account state. It must not submit, cancel, or modify an order, start the 30-day experiment, touch Brain/HIVE/H2 paths, or modify live configuration. Administrator provisioning is a manual Owner action and is outside the implementation authority covered by this document.

## 2. Market Observation Architecture

### 2.1 Components

- `MarketObservationCollector`: a dedicated read-only IB API client that uses the existing guarded transport and may send only market-data, current-time, managed-account, and cancellation messages already classified as read-only.
- `MarketSessionClassifier`: classifies `PREMARKET`, `REGULAR`, `AFTER_HOURS`, `CLOSED`, or `UNKNOWN` from IB contract `tradingHours`/`liquidHours`, the contract timezone, and broker/local UTC time. Missing, stale, or conflicting contract-hours evidence yields `UNKNOWN`; `UNKNOWN` and `CLOSED` cannot contribute to a policy freeze.
- `MarketObservationLedger`: writes canonical JSON Lines records using exclusive creation and flush/fsync. Records contain no account identifier, credentials, order information, strategy signal, or position information.
- `MarketPolicyFreezer`: validates an evidence window, computes descriptive statistics and conservative thresholds, and writes a new immutable policy version. It has no overwrite operation.
- `MarketDataGate`: loads a hash-verified policy and applies the existing fail-closed quote checks.

The collector uses SPY, QQQ, and IEF unless a symbol cannot be resolved or entitled. A replacement requires an explicit evidence reason and must be a highly liquid US-listed instrument. Fewer than three valid symbols blocks freezing.

### 2.2 Observation Protocol

- Cadence: one observation point every 5 seconds per symbol.
- Windows: at least three regular-session windows, each at least 5 minutes long.
- Separation: window starts are separated by at least 30 minutes.
- Minimum elapsed evidence span: 65 minutes from first accepted observation to last accepted observation.
- Minimum count: 180 accepted observations per symbol and 540 accepted observations total.
- Session: every accepted observation must be `REGULAR`; weekend, holiday, premarket, after-hours, closed, and unknown observations may be retained as rejected evidence but cannot satisfy minima.
- Health prerequisite: paper identity, broker reconciliation, broker heartbeat, and market-data farm health must remain valid throughout each window. Identity uncertainty terminates collection and produces no policy.

The timing requirements characterize multiple points in the session while avoiding an all-day run. Missed cadence points are not imputed.

## 3. Observation Evidence Schema

Each `MARKET_DATA_OBSERVATION_V1` record contains:

- `observation_id`, sequence number, and canonical record SHA-256;
- symbol, contract ID, source `IBKR`, and market-session classification;
- realtime/delayed/frozen classification and entitlement state;
- bid, ask, last and corresponding sizes when supplied;
- bid-present, ask-present, last-present, and spread-present booleans;
- broker quote timestamp and timestamp source;
- local receipt timestamp and monotonic receipt counter;
- broker current-time sample and local current-time sample;
- quote age, broker/local clock skew, and receipt latency in milliseconds;
- source health and sanitized IB status/error codes;
- identity-proof receipt hash and reconciliation receipt hash;
- acceptance status and reason codes.

No raw account ID is persisted. Quote timestamps must originate from timestamp-bearing IB callbacks, such as tick-by-tick bid/ask or last data. A locally synthesized quote timestamp is prohibited. Local receipt time alone is not broker timestamp provenance.

Raw quote age is `local_receipt_utc - broker_quote_utc`. Policy statistics use clock-corrected quote age: `raw_quote_age_ms - nearest_clock_skew_ms`. Clock skew is measured as the broker-time response against the midpoint of a bounded local request/response interval, with round-trip time and the raw delta retained. Negative corrected age beyond measured clock uncertainty is invalid rather than clamped.

## 4. Observation Rejection Rules

An observation is rejected from policy statistics when any of these is true:

- delayed, frozen, unknown, or conflicting market-data classification;
- unavailable or ambiguous entitlement;
- missing broker timestamp or local receipt timestamp;
- missing required bid or ask;
- nonpositive, nonfinite, crossed, or otherwise invalid prices;
- negative sizes;
- closed or unknown market session;
- unhealthy/degraded source, heartbeat failure, farm disconnect, or identity uncertainty;
- clock skew cannot be bounded from broker-time samples.

Rejected records remain in the ledger with reason codes. They never become valid by omission or substitution.

## 5. Policy Freeze Algorithm

`MarketPolicyFreezer` refuses to run unless all observation protocol minima and provenance requirements pass. It computes per-symbol and aggregate count, minimum, median, p95, p99, maximum, interquartile range, and missing/rejection rates for quote age, receipt latency, and absolute clock skew.

The initial deterministic formulas are:

- `age_margin_ms = max(250, 2 * quote_age_iqr_ms)`
- `MAX_QUOTE_AGE_FOR_NEW_TRADE_MS = ceil_100(p99_quote_age_ms + age_margin_ms)`
- `MAX_QUOTE_AGE_FOR_OPEN_POSITION_MANAGEMENT_MS = ceil_100(max(2 * MAX_QUOTE_AGE_FOR_NEW_TRADE_MS, p99_quote_age_ms + 1000))`
- `skew_margin_ms = max(100, 2 * clock_skew_iqr_ms)`
- `MAX_CLOCK_SKEW_MS = ceil_50(p99_absolute_clock_skew_ms + skew_margin_ms)`
- `REQUIRE_REALTIME_FOR_NEW_TRADE = true`
- `REQUIRE_BID_ASK_FOR_SPREAD_EVALUATION = true`

The fixed floors are safety margins, not observations and not gate-tuning knobs. The artifact records both the observed statistics and each formula input. Freeze blocks if any computed threshold is nonfinite, negative, or unsupported by all three symbols. A human cannot supply an ad hoc threshold to bypass this algorithm.

## 6. Policy Artifact And Versioning

The canonical artifact schema is `MARKET_DATA_POLICY_V1`. It includes:

- `POLICY_VERSION` (`MARKET_DATA_POLICY_V1` for the first artifact);
- evidence start/end and accepted window boundaries;
- source, symbols, observation counts, entitlement state, and session classes;
- latency/freshness/skew distributions and rejection summary;
- all five policy controls and threshold rationale;
- evidence-ledger SHA-256, canonical policy payload SHA-256, and creation time.

The policy store uses exclusive creation. If V1 exists, another V1 freeze must reproduce the identical digest or fail. Any semantic change requires `MARKET_DATA_POLICY_V2` or later and a predecessor digest. No silent modification is permitted.

Weekend or closed-market collection may test plumbing but always leaves `MARKET_DATA_POLICY_FROZEN=false` and `MARKET_DATA_GATE=BLOCK`.

## 7. Market Gate Acceptance Tests

Against the frozen policy:

- fresh, realtime, entitled, healthy, timestamp-proven quotes with required bid/ask pass;
- stale quotes block with `STALE_QUOTE`;
- delayed/frozen quotes block when realtime is required;
- missing bid/ask blocks spread evaluation;
- missing, synthetic, inconsistent, or future broker timestamps block;
- clock skew beyond policy blocks;
- unhealthy/degraded source or lost heartbeat blocks;
- any evidence or policy hash mismatch blocks.

The real gate may pass only on a new read-only observation that independently satisfies the frozen policy.

## 8. Windows Auditor Architecture

The dedicated local standard account is `CodexAuditorV1`. It is not an administrator, does not receive elevation rights, and is not added to privileged groups. It runs a minimal staged auditor runtime from:

`C:\ProgramData\CodexAuditorV1\runtime`

Audit inputs and outputs are outside the repository:

- immutable exports: `C:\ProgramData\CodexAuditorV1\exports`
- auditor reports: `C:\ProgramData\CodexAuditorV1\reports`
- provisioning logs: `C:\ProgramData\CodexAuditorV1\provisioning`

The staged runtime contains only two hash-manifested PowerShell scripts: the bundle verifier/report writer and the denial probe runner. It relies on the signed Windows PowerShell runtime already supplied by the OS and contains no Python environment, broker adapter, IB API package, Trader provider, execution-lock implementation, credentials, or live database code. The Owner-side Python exporter remains outside the Auditor boundary.

## 9. ACL Matrix

| Resource | Owner/Administrators/SYSTEM | CodexAuditorV1 |
|---|---|---|
| `C:\AI_VAULT\Secrets` | unchanged | explicit deny read/list/write/delete |
| IBKR/JTS configuration and credential paths | unchanged | explicit deny read/list/write/delete |
| SMTP credential files | unchanged | explicit deny read/list/write/delete |
| experiment live SQLite, WAL, SHM | unchanged | explicit deny read/write/delete |
| execution-lock resources | unchanged | explicit deny read/write/delete |
| Trader runtime/context/IPC paths | unchanged | explicit deny read/write/delete |
| broker/order-write source and configuration | unchanged | explicit deny read/execute/write |
| staged auditor runtime | full control | read/execute only |
| immutable export directory and files | full control | read/list only; write/delete denied |
| dedicated report directory | full control | create/write/read reports only; delete denied where supported |
| provisioning logs | full control | read only |

ACL changes are limited to these explicitly resolved paths. A missing target is logged and blocks the corresponding probe; the script never broadens Owner access or recursively rewrites unrelated repository ACLs.

## 10. Broker Network Boundary

Filesystem isolation alone is insufficient because Gateway port 4002 is local. Provisioning creates an outbound Windows Firewall block scoped to the `CodexAuditorV1` SID for TCP ports 4001 and 4002 on loopback/local addresses. The rule is validated through its security filter and by an actual socket-connection denial under the Auditor identity. If this host cannot enforce a SID-scoped outbound rule, `AUDITOR_ISOLATION_GATE` remains BLOCK; the design does not downgrade to import-only evidence.

The rule design follows Windows Firewall's supported local-user security filters and outbound port blocking. Configuration is not accepted as proof without the socket probe.

## 11. Provisioning Process

`AUDITOR_WINDOWS_PROVISIONING_V1.ps1` has three modes:

1. `-Mode Review`: default, nonprivileged, prints the exact account, directories, ACL entries, firewall rule, validation commands, and rollback actions. It makes no changes and prints `HUMAN_INFRASTRUCTURE_ACTION_REQUIRED=true`.
2. `-Mode Apply`: requires an already elevated Administrator shell, validates every path and parameter, prompts for a SecureString account password when creating the account, and applies only the reviewed changes. It never self-elevates.
3. `-Mode Rollback`: requires an elevated shell and removes the dedicated firewall rule, dedicated ProgramData tree after explicit confirmation, and local account. It restores only ACL entries created by this script from its signed/hashed change manifest; it does not reset whole ACLs.

Apply is idempotent: existing correct state is retained, drift is reported, and conflicting identities or paths fail closed. Every intended and completed change is written to the provisioning log without secrets.

The exact Owner action after implementation is:

```powershell
PowerShell.exe -NoProfile -File .\AUDITOR_WINDOWS_PROVISIONING_V1.ps1 -Mode Review
# After reviewing the emitted manifest, open PowerShell as Administrator:
PowerShell.exe -NoProfile -File .\AUDITOR_WINDOWS_PROVISIONING_V1.ps1 -Mode Apply
```

The actual command may include a verified script signing or hash-validation step if local execution policy requires it. Codex must stop before `-Mode Apply` and wait for the Owner.

## 12. Denial Probe Architecture

The Owner launches the staged probe under `CodexAuditorV1` with an interactive credential prompt. The probe attempts every operation and records the OS result and sanitized exception type:

| Probe | Required result |
|---|---|
| `SECRETS_READ` | DENIED |
| `IBKR_SECRET_READ` | DENIED |
| `SMTP_SECRET_READ` | DENIED |
| `EXECUTION_LOCK_ACCESS` | DENIED |
| `LIVE_DATABASE_MUTATION` | DENIED |
| `BROKER_WRITE_PATH_ACCESS` | DENIED, including TCP 4001/4002 connection |
| `TRADER_CONTEXT_ACCESS` | DENIED |
| `AUDIT_INPUT_MUTATION` | DENIED |
| `IMMUTABLE_EXPORT_READ` | ALLOWED |
| `AUDITOR_REPORT_WRITE` | ALLOWED |

An absent forbidden target is `NOT_PROVEN`, not `DENIED`. A probe process running under the Owner identity, an elevated token, or an unverified SID is invalid. The report includes the effective SID, token elevation status, runtime-manifest digest, input-manifest digest, and all probe results.

## 13. Auditor Functional Test

The Owner-side exporter publishes a synthetic immutable bundle to the export directory. Under `CodexAuditorV1`, the minimal auditor must:

1. verify the runtime manifest;
2. read and hash the export manifest and every declared input;
3. reject extra, modified, missing, or path-traversing inputs;
4. write an exclusive-create report to the report directory;
5. leave input hashes unchanged; and
6. pass all required denial/allow probes.

`AUDITOR_ISOLATION_GATE=PASS` requires every probe and functional step in the same run. Any partial, skipped, ambiguous, or configuration-only result is BLOCK.

## 14. Test Matrix

### Market Data

- schema validation and secret/account-ID rejection;
- ledger canonicalization, sequence/hash chain, fsync, and no overwrite;
- broker contract-hours parsing, weekend, holiday, early-close, and unknown-time handling;
- cadence/window/count enforcement;
- timestamp provenance, quote-age, latency, and skew calculations;
- delayed/frozen/missing/crossed/invalid/unhealthy rejection;
- deterministic policy statistics, margins, canonical hash, and immutable versioning;
- fresh PASS and stale/delayed/missing/provenance/source-health BLOCK tests;
- read-only transport source scan and outbound-message allowlist test.

### Auditor

- provisioning script parser/static safety tests;
- Review mode is nonmutating and reports the exact apply/rollback plan;
- Apply refuses non-elevated execution and never self-elevates;
- idempotence and drift-conflict tests against mocked Windows primitives;
- ACL manifest completeness and forbidden-path scope checks;
- effective SID/elevation verification;
- all ten real denial/allow probes;
- synthetic immutable-bundle functional test;
- rollback manifest precision;
- secret scan, forbidden-path scan, and full `ibkr_paper_30d` regression/fault suite.

## 15. Stop Conditions

Immediately stop and remain BLOCKED when:

- paper identity, broker reconciliation, heartbeat, or source health fails;
- market session is not confirmed regular;
- timestamp provenance or entitlement is ambiguous;
- evidence minima are not met;
- an existing policy version would be modified;
- administrator rights are required and the Owner has not manually acted;
- account SID, ACL, firewall, or runtime manifest is ambiguous;
- any required denial probe unexpectedly succeeds;
- any required allow probe fails;
- a forbidden repository path would be touched;
- any broker order-write call is observed.

Even after both gates pass, `AUTONOMOUS_TRADING_STATUS=BLOCKED`. No paper lifecycle action or 30-day experiment may begin without separate Owner authorization.
