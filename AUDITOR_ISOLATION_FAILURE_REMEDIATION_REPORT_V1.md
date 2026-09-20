# AUDITOR_ISOLATION_FAILURE_REMEDIATION_REPORT

Recorded: 2026-09-20T16:57:58.9164979Z

## Preserved Evidence

The following installed artifacts were read and hashed without modification:

| Artifact | SHA256 |
|---|---|
| `final-isolation-verification-0e2ec1a058d245e59857fe7f036badc9.json` | `053d7b0e89a51c25efad9d2722852860220d7921505a55f40fccf6f46013bb37` |
| `audit-cd33c4f62a32e2142eb6f310-77baecdfef264c78adf70c54f874fef9.json` | `dacc41c16cc05271ca458d96b203c548865a7689f263aa0f68583817356582b7` |
| immutable export `manifest.json` | `ab84d419c77c54e0be2958fce33440e8a1676eb8f9e81a33d18cfbdfadf79f31` |
| `AUDITOR_PROBE_TARGET_MANIFEST_V1.json` | `be462e2d7f78b2eed37fd1577b5f1fbdf84fa333effa04278d899a3163b895d2` |
| `AUDITOR_RUNTIME_MANIFEST_V1.json` | `7d8b6780aea64f395b906958f32d6d554a36f35630c404e6418e467b55cbd209` |
| `AUDITOR_PROVISIONING_CHANGE_MANIFEST_V1.json` | `0f72cd4fce86453dc958843cf5d4e70b26443a0570b7c69c6110d6ab993231da` |

## Current Endpoint Truth

| Endpoint | Truth | Evidence |
|---|---|---|
| IPv4 `127.0.0.1:4001` | `NO_LISTENER` | Synchronous socket returned `ConnectionRefused`; no listener exists. |
| IPv4 `127.0.0.1:4002` | `CONNECTED` | Owner and restricted Auditor both completed TCP connection. |
| IPv6 `[::1]:4001` | `NO_LISTENER` | Synchronous socket returned `ConnectionRefused`; no listener exists. |
| IPv6 `[::1]:4002` | `CONNECTED` | Owner and restricted Auditor both completed TCP connection. |

The active listener is PID 94800, `C:\Jts\ibgateway\1044\ibgateway.exe`, bound to `:::4002`. There is no listener on port 4001. The old one-second asynchronous harness labeled its roughly two-second `ConnectionRefused` result as `DENIED`; that was a classification defect.

## Firewall Actual State

| Field | Actual value |
|---|---|
| Rule name | `CodexAuditorV1-Broker-Loopback-Block` |
| Enabled | `True` |
| Profile | `Any` |
| Direction | `Outbound` |
| Action | `Block` |
| Protocol | `TCP` |
| Remote port | `4001,4002` |
| Local port | `Any` |
| Remote address | `Any` |
| Local address | `Any` |
| Program | `Any` |
| Service | `Any` |
| Interface type | `Any` |
| Edge traversal | `Block` |
| Policy store | `PersistentStore`, local |
| Local user filter | `D:(A;;CC;;;S-1-5-21-214160970-1890373857-4055601883-1012)` |
| Authentication | `NotRequired` |
| Encryption | `NotRequired` |

The intended SID filter is present in the actual Windows security filter; the failure is not a missing filter or wrong port. The same-host non-AppContainer loopback connections bypass the intended Windows Defender Firewall rule behavior on this host. A rule object existing in `PersistentStore` therefore does not establish the security objective.

Microsoft documents that direct Windows Filtering Platform ALE layers can classify by user identity and expose a loopback condition flag. A custom, reviewed WFP ALE policy or a dedicated VM with no virtual network adapter are viable design candidates, but neither has been implemented or host-proven here. Windows Sandbox is not a valid fallback on this machine because the installed edition is Windows Home, for which Microsoft does not support Sandbox.

## Unsafe Target Path Root Cause

The installed probe used `Test-Path` and `Get-Item` under the restricted token to discover path existence and reparse points. The same ACL denial that the probe was supposed to prove could terminate that validation. A catch around the entire ten-target loop then discarded the target, operation, normalized path, root, chain, and exception and emitted only `UNSAFE_TARGET_PATH`.

The preserved report cannot identify the exact failing target because those fields were not emitted. `SECRETS_READ` at `C:\AI_VAULT\Secrets` is the first deterministic candidate by manifest order. Promoting it to a proven exact target would fabricate evidence.

Classification: `PROBE_PATH_VALIDATION_DEFECT`.

The corrected source validator:

- requires lexical containment beneath an explicit approved root;
- inspects each accessible existing path component for reparse points;
- rejects every visible reparse point;
- rejects malformed and outside-root paths;
- treats an OS access denial as proof that traversal is already blocked, recording the exact denied component;
- emits a complete target-validation matrix instead of suppressing diagnostics.

## Target Validation Matrix

| Probe | Path | Expected root | Normalized path | Valid | Reason |
|---|---|---|---|---|---|
| `SECRETS_READ` | `C:\AI_VAULT\Secrets` | same | same | yes | accepted; no reparse in Owner forensic inspection |
| `IBKR_SECRET_READ` | `C:\Jts` | same | same | yes | accepted; no reparse |
| `SMTP_SECRET_READ` | `C:\AI_VAULT\Secrets\email_alerts.env` | `C:\AI_VAULT\Secrets` | same | yes | accepted; no reparse |
| `EXECUTION_LOCK_ACCESS` | `C:\AI_VAULT\state\ibkr_paper_30d\execution.lock` | `C:\AI_VAULT\state\ibkr_paper_30d` | same | yes | accepted; missing leaf uses direct existing ancestor |
| `LIVE_DATABASE_MUTATION` | `C:\AI_VAULT\state\ibkr_paper_30d\reports\real_codex_invocations.sqlite3` | `C:\AI_VAULT\state\ibkr_paper_30d` | same | yes | accepted; no reparse |
| `BROKER_WRITE_PATH_ACCESS` | `C:\AI_VAULT\ibkr_paper_30d\broker.py` | same | same | yes | accepted; no reparse |
| `TRADER_CONTEXT_ACCESS` | `C:\AI_VAULT\ibkr_paper_30d\trader_invocation.py` | same | same | yes | accepted; no reparse |
| `AUDIT_INPUT_MUTATION` | `C:\ProgramData\CodexAuditorV1\exports` | same | same | yes | accepted; no reparse |
| `IMMUTABLE_EXPORT_READ` | `C:\ProgramData\CodexAuditorV1\exports` | same | same | yes | accepted; no reparse |
| `AUDITOR_REPORT_WRITE` | `C:\ProgramData\CodexAuditorV1\reports` | same | same | yes | accepted; no reparse |

## Remediation State

- RED reproduction: `PASS` (five focused tests failed before the runtime patch).
- Corrected probe source SHA256: `063e72ab2ea3f3473b7ab5d9bed8f9415c5b660d4c3bfab07b8cb0b61e4a87cc`.
- Installed probe remains unchanged at SHA256 `2bba60bb83ccf07c5a723c8319201686ec0db9fa9d25610da51676de59c45e22`.
- `PasswordRequired=true` is recorded in `AUDITOR_PASSWORD_POLICY_STATE_EVENT_V1.json`; no password or secret material was read or logged.
- No Apply, Rollback, ACL mutation, firewall mutation, elevated command, or IBKR order operation was performed.
- A new elevated provisioning command is intentionally not supplied. The firewall boundary needs Owner approval of a replacement architecture before an administrator script can be safely authored.
- `AUDITOR_ISOLATION_GATE=BLOCK`.
- `AUTONOMOUS_TRADING_STATUS=BLOCKED`.
- `REAL_BROKER_WRITE_CALLS=0`.

## Required Owner Design Decision

Choose one enforceable boundary for a subsequent reviewed checkpoint:

1. A direct Windows Filtering Platform ALE block that matches the Auditor SID, TCP ports 4001/4002, and the loopback flag at both IPv4 and IPv6 connect layers, followed by real restricted-token proof.
2. A dedicated VM with no virtual network adapter, immutable evidence copied in, and reports copied out through an Owner-controlled channel.

Until one is implemented and proved under the restricted token, the 30-day experiment must not start.
