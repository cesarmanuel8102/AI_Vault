# Codex IBKR Paper Final Gates Implementation Plan V1

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement, prove, and report the evidence-backed market-data policy and dedicated Windows Auditor isolation gates without any broker order write.

**Architecture:** The market track extends the guarded IB read-only boundary with timestamped multi-window observations, a hash-chained ledger, and an immutable policy freezer consumed by the existing market gate. The Auditor track stages two minimal PowerShell scripts under a dedicated low-privilege account, enforces NTFS and SID-scoped firewall boundaries through a reviewable provisioning script, and accepts only actual denial/allow probes as evidence.

**Tech Stack:** Python 3.11, Pydantic, official IB Python API, SQLite/JSONL evidence, pytest, PowerShell 5.1+, Windows LocalAccounts/NetSecurity/ACL cmdlets.

**Spec:** `CODEX_IBKR_PAPER_FINAL_GATES_SPEC_V1.md`

## Global Constraints

- `REAL_IBKR_ORDER_WRITE_AUTHORIZED=false`; no submit, cancel, modify, lifecycle test, directional trade, live trade, or real-money action.
- Use only `ibkr_paper_30d/**`, `tests/ibkr_paper_30d/**`, `auditor_runtime/**`, the two approved root artifacts, `AUDITOR_WINDOWS_PROVISIONING_V1.ps1`, and runtime evidence under `state/ibkr_paper_30d/**`.
- Do not touch `brain/**`, `tmp_agent/brain_v9/**`, `HIVE/**`, `H2/**`, `H2-R2/**`, existing order executors, or live configuration.
- Preserve unrelated worktree changes.
- Market policy cannot freeze from weekend, holiday, premarket, after-hours, closed, unknown, delayed, unhealthy, or timestamp-unproven observations.
- The first valid evidence set requires SPY, QQQ, and IEF; three regular-session windows of at least 5 minutes; starts separated by at least 30 minutes; a span of at least 65 minutes; and at least 180 accepted observations per symbol.
- Policy versions are exclusive-create and immutable. Semantic changes require a successor version and predecessor digest.
- `AUDITOR_WINDOWS_PROVISIONING_V1.ps1 -Mode Apply` and `-Mode Rollback` require a manually opened elevated shell. The script never self-elevates.
- Stop before privileged provisioning and wait for the Owner. Configuration alone never promotes Auditor isolation.
- Every gate stays fail-closed on missing, ambiguous, partial, skipped, or conflicting evidence.
- `AUTONOMOUS_TRADING_STATUS=BLOCKED` throughout this plan.

## Review Focus

- IB reconnects during an observation window: the batch must terminate and no pre-disconnect observations may silently satisfy a freeze.
- Contract-hour strings spanning an early close or timezone transition: session classification must follow broker-supplied liquid hours and fail UNKNOWN on ambiguity.
- Existing policy path with different bytes: freezer must reject it without replacing or truncating the file.
- Provisioning rerun after partial ACL/firewall application: Review reports drift; Apply repairs only manifest-owned entries and never resets unrelated ACLs.
- Auditor target missing or junction/reparse-point redirected: denial is NOT_PROVEN and path resolution outside the approved roots aborts the probe.

---

### Task 1: Market Observation Models And Session Classification

**Files:**
- Create: `ibkr_paper_30d/market_observation.py`
- Create: `tests/ibkr_paper_30d/test_market_observation.py`

**Interfaces:**
- Consumes: broker `tradingHours`, `liquidHours`, timezone ID, broker UTC sample, local request/response timestamps.
- Produces: `MarketSession`, `ClockSample`, `MarketObservation`, `ObservationWindow`, `classify_session(now_utc: datetime, liquid_hours: str, timezone_id: str) -> MarketSession`, and `corrected_quote_age_ms(broker_quote_timestamp: datetime, local_receipt_timestamp: datetime, clock_sample: ClockSample) -> int | None`.

- [ ] **Step 1: RED - add model and session tests**

```python
def test_sunday_and_missing_hours_are_not_regular():
    assert classify_session(SUNDAY_UTC, "20260920:CLOSED", "US/Eastern") is MarketSession.CLOSED
    assert classify_session(SUNDAY_UTC, "", "US/Eastern") is MarketSession.UNKNOWN

def test_clock_corrected_age_uses_midpoint_skew():
    sample = ClockSample.from_round_trip(LOCAL_SEND, BROKER_TIME, LOCAL_RECEIVE)
    assert corrected_quote_age_ms(QUOTE_TIME, LOCAL_RECEIPT, sample) == EXPECTED_MS

def test_early_close_contract_hours_are_honored():
    assert classify_session(AFTER_EARLY_CLOSE, EARLY_CLOSE_HOURS, "US/Eastern") is MarketSession.AFTER_HOURS
```

- [ ] **Step 2: Run RED test**

Run: `python -m pytest tests/ibkr_paper_30d/test_market_observation.py -q`
Expected: FAIL because `market_observation` does not exist.

- [ ] **Step 3: Implement immutable models and strict parsers**

```python
class MarketSession(str, Enum):
    PREMARKET = "PREMARKET"
    REGULAR = "REGULAR"
    AFTER_HOURS = "AFTER_HOURS"
    CLOSED = "CLOSED"
    UNKNOWN = "UNKNOWN"

class MarketObservation(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")
    observation_id: str
    sequence: int
    symbol: str
    source: Literal["IBKR"]
    market_session: MarketSession
    broker_quote_timestamp: datetime | None
    local_receipt_timestamp: datetime
    raw_quote_age_ms: int | None
    corrected_quote_age_ms: int | None
    clock_skew_ms: int | None
    accepted: bool
    reason_codes: tuple[str, ...]
    record_sha256: str
```

Parse only explicit IB hour ranges. Reject stale dates, malformed ranges, unknown timezone IDs, DST ambiguity, and conflicting symbol schedules as `UNKNOWN`.

- [ ] **Step 4: GREEN and regression**

Run: `python -m pytest tests/ibkr_paper_30d/test_market_observation.py tests/ibkr_paper_30d/test_market_data.py -q`
Expected: PASS.

- [ ] **Step 5: Security/fault test and scoped commit**

Add tests rejecting raw account fields, naive datetimes, nonfinite values, negative sequence numbers, and out-of-range clock samples.

Run: `python -m pytest tests/ibkr_paper_30d/test_market_observation.py -q`
Expected: PASS.

```powershell
git add -- ibkr_paper_30d/market_observation.py tests/ibkr_paper_30d/test_market_observation.py
git commit -m "Add market observation evidence models"
```

### Task 2: Guarded Read-Only Multi-Sample Collector

**Files:**
- Create: `ibkr_paper_30d/market_observation_collector.py`
- Modify: `ibkr_paper_30d/ibkr_readonly_session.py`
- Create: `tests/ibkr_paper_30d/test_market_observation_collector.py`
- Modify: `tests/ibkr_paper_30d/test_ibkr_readonly_session.py`

**Interfaces:**
- Consumes: Task 1 models; `ExpectedPaperIdentityStore`; `ReadOnlyMessageGuard`; symbols and cadence.
- Produces: `ObservationConfig(symbols, cadence_seconds, window_seconds)`, `ObservationPrerequisites`, and `MarketObservationCollector.collect_window(config, prerequisites) -> ObservationWindow`.

- [ ] **Step 1: RED - require timestamped quotes and transport allowlist**

```python
def test_collector_rejects_identity_change_mid_window(fake_client):
    fake_client.identity_receipts = [VALID_IDENTITY, DIFFERENT_IDENTITY]
    with pytest.raises(ObservationAborted, match="PAPER_IDENTITY_UNCERTAIN"):
        collector(fake_client).collect_window(CONFIG, PREREQUISITES)

def test_tick_by_tick_messages_are_read_only_allowlisted():
    assert OUT.REQ_TICK_BY_TICK_DATA in ReadOnlyMessageGuard.ALLOWED_MESSAGE_IDS
    assert OUT.CANCEL_TICK_BY_TICK_DATA in ReadOnlyMessageGuard.ALLOWED_MESSAGE_IDS
```

- [ ] **Step 2: Run RED test**

Run: `python -m pytest tests/ibkr_paper_30d/test_market_observation_collector.py tests/ibkr_paper_30d/test_ibkr_readonly_session.py -q`
Expected: FAIL on missing collector and tick-by-tick allowlist entries.

- [ ] **Step 3: Implement collector**

Use `reqContractDetails(request_id, contract)`, `reqTickByTickData(request_id, contract, "BidAsk", 0, False)`, `reqTickByTickData(request_id, contract, "Last", 0, False)`, `reqCurrentTime()`, and matching `cancelTickByTickData(request_id)` calls. Extend the guard only with official read-only message IDs for contract details and tick-by-tick request/cancel. Capture callback timestamps, sizes, market-data type, farm status, monotonic receipt time, and periodic identity/heartbeat receipts. Do not import any order model or expose any order method.

- [ ] **Step 4: GREEN and regression**

Run: `python -m pytest tests/ibkr_paper_30d/test_market_observation_collector.py tests/ibkr_paper_30d/test_ibkr_readonly_session.py tests/ibkr_paper_30d/test_ibkr_readonly.py -q`
Expected: PASS.

- [ ] **Step 5: Security/fault test and scoped commit**

Source-scan the collector for `placeOrder`, `cancelOrder`, `reqOpenOrders`, account IDs, and order imports; inject disconnect, delayed data, farm failure, crossed market, missing timestamp, and callback reordering.

```powershell
git add -- ibkr_paper_30d/market_observation_collector.py ibkr_paper_30d/ibkr_readonly_session.py tests/ibkr_paper_30d/test_market_observation_collector.py tests/ibkr_paper_30d/test_ibkr_readonly_session.py
git commit -m "Add guarded IBKR market observation collector"
```

### Task 3: Hash-Chained Observation Ledger

**Files:**
- Create: `ibkr_paper_30d/market_observation_ledger.py`
- Create: `tests/ibkr_paper_30d/test_market_observation_ledger.py`

**Interfaces:**
- Consumes: `MarketObservation`, `ObservationWindow`.
- Produces: `MarketObservationLedger.append_window(window) -> LedgerReceipt` and `MarketObservationLedger.verify() -> LedgerVerification`.

- [ ] **Step 1: RED - atomic append and tamper tests**

```python
def test_ledger_hash_chain_detects_changed_record(tmp_path, accepted_window):
    ledger = MarketObservationLedger(tmp_path / "observations.jsonl")
    ledger.append_window(accepted_window)
    tamper_first_record(ledger.path, {"symbol": "CHANGED"})
    assert ledger.verify().status == "HASH_MISMATCH"

def test_ledger_rejects_account_identity_and_secret_keys(tmp_path, accepted_window):
    contaminated = accepted_window.model_copy(update={"metadata": {"account_id": "forbidden"}})
    with pytest.raises(ValueError, match="FORBIDDEN_EVIDENCE_KEY"):
        MarketObservationLedger(tmp_path / "observations.jsonl").append_window(contaminated)

def test_existing_sequence_cannot_be_replaced(tmp_path, accepted_window):
    ledger = MarketObservationLedger(tmp_path / "observations.jsonl")
    ledger.append_window(accepted_window)
    with pytest.raises(ValueError, match="SEQUENCE_NOT_MONOTONIC"):
        ledger.append_window(accepted_window)
```

- [ ] **Step 2: Run RED test**

Run: `python -m pytest tests/ibkr_paper_30d/test_market_observation_ledger.py -q`
Expected: FAIL because the ledger module does not exist.

- [ ] **Step 3: Implement canonical JSONL ledger**

Each record includes `previous_record_sha256`; appends use an exclusive process lock, canonical bytes, flush, and `os.fsync`. Verification recomputes every record digest, ordering, window digest, and forbidden-key scan. Never rewrite a prior record.

- [ ] **Step 4: GREEN and regression**

Run: `python -m pytest tests/ibkr_paper_30d/test_market_observation_ledger.py tests/ibkr_paper_30d/test_evidence.py -q`
Expected: PASS.

- [ ] **Step 5: Security/fault test and scoped commit**

Test truncated tails, duplicate sequence, concurrent writer rejection, path traversal, injected `DU` account values, and secret-like keys.

```powershell
git add -- ibkr_paper_30d/market_observation_ledger.py tests/ibkr_paper_30d/test_market_observation_ledger.py
git commit -m "Persist sanitized market observation evidence"
```

### Task 4: Immutable Market Policy Freezer

**Files:**
- Create: `ibkr_paper_30d/market_policy.py`
- Create: `tests/ibkr_paper_30d/test_market_policy.py`
- Modify: `ibkr_paper_30d/market_data.py`

**Interfaces:**
- Consumes: verified Task 3 ledger and Task 1 accepted observations.
- Produces: `MarketPolicyArtifact`, `PolicyFreezeResult`, `MarketPolicyFreezer.freeze(ledger, destination, version="MARKET_DATA_POLICY_V1") -> PolicyFreezeResult`, and `load_verified_policy(path) -> MarketDataPolicy`.

- [ ] **Step 1: RED - protocol minima and formula tests**

```python
def test_weekend_evidence_cannot_freeze_policy(tmp_path, weekend_ledger):
    result = MarketPolicyFreezer().freeze(weekend_ledger, tmp_path / "policy.json")
    assert result.status == "BLOCK"
    assert "REGULAR_SESSION_EVIDENCE_REQUIRED" in result.reason_codes

def test_three_separated_windows_and_540_records_are_required(tmp_path, short_ledger):
    result = MarketPolicyFreezer().freeze(short_ledger, tmp_path / "policy.json")
    assert {"WINDOW_COUNT_INSUFFICIENT", "OBSERVATION_COUNT_INSUFFICIENT"} <= set(result.reason_codes)

def test_policy_thresholds_follow_documented_percentile_formulas(valid_ledger, tmp_path):
    result = MarketPolicyFreezer().freeze(valid_ledger, tmp_path / "policy.json")
    assert result.policy.max_new_trade_age_ms == ceil_100(result.statistics.p99_quote_age_ms + max(250, 2 * result.statistics.quote_age_iqr_ms))

def test_different_existing_v1_is_never_replaced(valid_ledger, tmp_path):
    destination = tmp_path / "policy.json"
    destination.write_text('{"different":true}', encoding="utf-8")
    before = destination.read_bytes()
    assert MarketPolicyFreezer().freeze(valid_ledger, destination).status == "VERSION_CONFLICT"
    assert destination.read_bytes() == before
```

- [ ] **Step 2: Run RED test**

Run: `python -m pytest tests/ibkr_paper_30d/test_market_policy.py -q`
Expected: FAIL because the policy freezer does not exist.

- [ ] **Step 3: Implement deterministic statistics and exclusive creation**

Compute median/p95/p99/max/IQR with a documented nearest-rank method over accepted corrected ages and absolute skews. Apply the exact spec formulas and round-up rules. Serialize a canonical payload, calculate SHA-256 excluding only its own digest field, then create with mode `x`. Existing identical bytes return `ALREADY_FROZEN`; differing bytes return `VERSION_CONFLICT`.

- [ ] **Step 4: GREEN and regression**

Run: `python -m pytest tests/ibkr_paper_30d/test_market_policy.py tests/ibkr_paper_30d/test_market_data.py -q`
Expected: PASS.

- [ ] **Step 5: Security/fault test and scoped commit**

Test NaN/Infinity, missing symbol, conflicting entitlement, bad ledger hash, insufficient separation, early-close evidence, policy truncation, and predecessor mismatch.

```powershell
git add -- ibkr_paper_30d/market_policy.py ibkr_paper_30d/market_data.py tests/ibkr_paper_30d/test_market_policy.py
git commit -m "Freeze versioned market data policy from evidence"
```

### Task 5: Market Observation CLI And Real Gate Validation

**Files:**
- Modify: `ibkr_paper_30d/cli.py`
- Create: `tests/ibkr_paper_30d/test_market_observation_cli.py`

**Interfaces:**
- Consumes: Tasks 1-4 and existing read-only identity/reconciliation reports.
- Produces commands `observe-market-data`, `freeze-market-policy`, and `validate-real-market-data`; writes sanitized reports under `state/ibkr_paper_30d/reports/`.

- [ ] **Step 1: RED - CLI fail-closed tests**

```python
def test_observe_refuses_without_identity_and_reconciliation_pass(tmp_path):
    report = observe_market_data(readonly_report={"paper_account_identity_gate": "BLOCK"}, output_root=tmp_path)
    assert report["status"] == "BLOCK"
    assert report["broker_calls_made"] == 0

def test_freeze_refuses_closed_market_ledger(closed_ledger, tmp_path):
    assert freeze_market_policy(closed_ledger, tmp_path / "policy.json")["market_data_policy_frozen"] is False

@pytest.mark.parametrize("mutation", ["STALE", "DELAYED", "MISSING_BID", "NO_TIMESTAMP"])
def test_validate_blocks_stale_delayed_missing_and_bad_provenance(policy, mutation):
    assert validate_market_observation(policy, quote_case(mutation))["market_data_gate"] == "BLOCK"
```

- [ ] **Step 2: Run RED test**

Run: `python -m pytest tests/ibkr_paper_30d/test_market_observation_cli.py -q`
Expected: FAIL because the commands do not exist.

- [ ] **Step 3: Implement commands**

`observe-market-data` defaults to `SPY QQQ IEF`, 5-second cadence, 5-minute window, and never loops into a trading decision. `freeze-market-policy` reads only a verified ledger. `validate-real-market-data` performs a fresh read-only sample and evaluates every symbol through `MarketDataGate`.

- [ ] **Step 4: GREEN and regression**

Run: `python -m pytest tests/ibkr_paper_30d/test_market_observation_cli.py tests/ibkr_paper_30d/test_market_data.py tests/ibkr_paper_30d/test_ibkr_readonly_session.py -q`
Expected: PASS.

- [ ] **Step 5: Security/fault test and scoped commit**

Assert all command reports show `real_order_writes_attempted=0`, contain no account ID, and retain `MARKET_DATA_POLICY_FROZEN=false` until a verified policy exists.

```powershell
git add -- ibkr_paper_30d/cli.py tests/ibkr_paper_30d/test_market_observation_cli.py
git commit -m "Expose read-only market policy workflow"
```

**External checkpoint:** If the current time is not an actual eligible US regular session, stop market execution here. Do not freeze. During an eligible session, run three observation windows satisfying the spec, verify the ledger, freeze V1, and run real validation. Any failed prerequisite leaves the gate BLOCK.

### Task 6: Reviewable Windows Provisioning Script

**Files:**
- Create: `AUDITOR_WINDOWS_PROVISIONING_V1.ps1`
- Create: `tests/ibkr_paper_30d/test_auditor_provisioning.py`

**Interfaces:**
- Consumes: account name `CodexAuditorV1`, approved ProgramData paths, explicit protected paths, runtime-script hashes.
- Produces: `-Mode Review|Apply|Rollback`, canonical change manifest, provisioning log, validation commands, and rollback actions.

- [ ] **Step 1: RED - static and Review-mode tests**

```python
def test_script_has_no_self_elevation_or_uac_bypass(script_text):
    forbidden = ("-Verb RunAs", "ConsentPromptBehaviorAdmin", "EnableLUA", "EncodedCommand")
    assert not any(token in script_text for token in forbidden)

def test_review_mode_is_default_and_nonmutating(review_result):
    assert review_result.returncode == 0
    assert "HUMAN_INFRASTRUCTURE_ACTION_REQUIRED=true" in review_result.stdout
    assert snapshot_security_state() == review_result.before_state

def test_manifest_names_only_approved_paths_and_firewall_ports(review_manifest):
    assert set(review_manifest["broker_ports"]) == {4001, 4002}
    assert set(review_manifest["paths"]) <= APPROVED_AUDITOR_PATHS

def test_apply_requires_elevated_token_before_first_mutation(non_elevated_apply_result):
    assert non_elevated_apply_result.returncode != 0
    assert "ADMINISTRATOR_REQUIRED" in non_elevated_apply_result.stderr
    assert non_elevated_apply_result.mutation_count == 0

def test_partial_rerun_repairs_only_manifest_owned_drift(partial_security_state):
    result = simulate_apply(partial_security_state)
    assert result.repaired == {"auditor_runtime_acl"}
    assert result.unrelated_acl_changes == ()
```

- [ ] **Step 2: Run RED test**

Run: `python -m pytest tests/ibkr_paper_30d/test_auditor_provisioning.py -q`
Expected: FAIL because the provisioning script does not exist.

- [ ] **Step 3: Implement Review, Apply, and Rollback functions**

The script uses `#Requires -Version 5.1`, `CmdletBinding(SupportsShouldProcess)`, `Get-LocalUser`/`New-LocalUser`, explicit `System.Security.AccessControl.FileSystemAccessRule` objects, `New-NetFirewallRule` plus `Set-NetFirewallRule -LocalUser <SID-SDDL>`, and a manifest-owned rollback list. Review emits JSON and `HUMAN_INFRASTRUCTURE_ACTION_REQUIRED=true`; it calls no mutating cmdlet. Apply checks elevation before resolving a SecureString password. Rollback requires explicit confirmation and removes only manifest-owned entries.

- [ ] **Step 4: GREEN and regression**

Run: `python -m pytest tests/ibkr_paper_30d/test_auditor_provisioning.py tests/ibkr_paper_30d/test_auditor_isolation.py -q`
Expected: PASS.

- [ ] **Step 5: Security/fault test and scoped commit**

Parse the PowerShell AST and reject `Start-Process -Verb RunAs`, encoded commands, registry UAC changes, Owner ACL replacement, wildcard recursive ACLs, Brain/HIVE paths, broker credential writes, or SMTP writes. Exercise only `-Mode Review` nonprivileged.

```powershell
git add -- AUDITOR_WINDOWS_PROVISIONING_V1.ps1 tests/ibkr_paper_30d/test_auditor_provisioning.py
git commit -m "Prepare Windows Auditor provisioning boundary"
```

### Task 7: Minimal Staged Auditor Runtime

**Files:**
- Create: `auditor_runtime/CODEX_DECISION_AUDITOR_V1.ps1`
- Create: `auditor_runtime/AUDITOR_DENIAL_PROBE_V1.ps1`
- Create: `tests/ibkr_paper_30d/test_auditor_runtime.py`
- Modify: `AUDITOR_WINDOWS_PROVISIONING_V1.ps1`

**Interfaces:**
- Consumes: `AUDIT_EXPORT_MANIFEST_V1`, probe-target manifest, runtime manifest.
- Produces: `AUDITOR_REPORT_V1`, `AUDITOR_DENIAL_PROBE_REPORT_V1`, and runtime SHA-256 manifest staged by provisioning.

- [ ] **Step 1: RED - standalone runtime tests**

```python
def test_runtime_contains_no_repo_broker_or_trader_imports(runtime_text):
    assert not any(token in runtime_text for token in ("ibapi", "broker.py", "trader_invocation", "execution_lock"))

def test_runtime_rejects_modified_extra_and_traversing_bundle_files(run_runtime, tampered_bundle):
    result = run_runtime(tampered_bundle)
    assert result["status"] in {"HASH_MISMATCH", "FILE_SET_MISMATCH", "UNSAFE_MANIFEST_PATH"}

def test_probe_report_binds_effective_sid_and_elevation_state(run_probe, expected_sid):
    report = run_probe()
    assert report["effective_sid"] == expected_sid
    assert report["token_elevated"] is False
```

- [ ] **Step 2: Run RED test**

Run: `python -m pytest tests/ibkr_paper_30d/test_auditor_runtime.py -q`
Expected: FAIL because runtime scripts do not exist.

- [ ] **Step 3: Implement standard-library PowerShell verifier and probe shell**

Use `Get-FileHash -Algorithm SHA256`, `ConvertFrom-Json`, strict leaf-name checks, exact file-set comparison, exclusive `FileMode.CreateNew`, effective Windows identity/SID, and token elevation inspection. Probe definitions are data from the Owner-generated target manifest; the script resolves final paths and rejects reparse points or roots outside the manifest.

- [ ] **Step 4: GREEN and regression**

Run: `python -m pytest tests/ibkr_paper_30d/test_auditor_runtime.py tests/ibkr_paper_30d/test_auditor_isolation.py -q`
Expected: PASS.

- [ ] **Step 5: Security/fault test and scoped commit**

Test symlink/junction redirection, malformed JSON, duplicate keys, case collisions, wrong SID, elevated token, report overwrite, and runtime-manifest mismatch.

```powershell
git add -- auditor_runtime/CODEX_DECISION_AUDITOR_V1.ps1 auditor_runtime/AUDITOR_DENIAL_PROBE_V1.ps1 AUDITOR_WINDOWS_PROVISIONING_V1.ps1 tests/ibkr_paper_30d/test_auditor_runtime.py
git commit -m "Add minimal standalone Auditor runtime"
```

**Administrator checkpoint:** Run only `AUDITOR_WINDOWS_PROVISIONING_V1.ps1 -Mode Review`. Present its exact Apply command, manifest, requested ACL/firewall changes, postconditions, and rollback command. Stop and wait for the Owner to run `-Mode Apply` manually in an elevated shell.

### Task 8: Actual Auditor Denial Probes And ACL Verification

**Files:**
- Create: `ibkr_paper_30d/auditor_isolation.py`
- Create: `tests/ibkr_paper_30d/test_auditor_denial_report.py`
- Modify: `ibkr_paper_30d/cli.py`

**Interfaces:**
- Consumes: restricted-run `AUDITOR_DENIAL_PROBE_REPORT_V1`, provisioning manifest, expected Auditor SID.
- Produces: `verify_auditor_denial_report(report, manifest) -> AuditorIsolationResult` and `verify-auditor-isolation` CLI report.

- [ ] **Step 1: RED - all ten outcomes required**

```python
def test_configuration_without_actual_probe_is_block(provisioning_manifest):
    assert verify_auditor_denial_report({}, provisioning_manifest).gate == "BLOCK"

def test_one_unexpected_allow_blocks_entire_gate(valid_probe_report, provisioning_manifest):
    valid_probe_report["results"]["SECRETS_READ"] = "ALLOWED"
    assert verify_auditor_denial_report(valid_probe_report, provisioning_manifest).gate == "BLOCK"

def test_missing_target_is_not_proven_not_denied(valid_probe_report, provisioning_manifest):
    valid_probe_report["results"]["LIVE_DATABASE_MUTATION"] = "NOT_PROVEN"
    result = verify_auditor_denial_report(valid_probe_report, provisioning_manifest)
    assert "LIVE_DATABASE_MUTATION_NOT_PROVEN" in result.reason_codes

def test_all_required_denials_and_allows_pass_for_expected_sid(valid_probe_report, provisioning_manifest):
    assert verify_auditor_denial_report(valid_probe_report, provisioning_manifest).gate == "PASS"
```

- [ ] **Step 2: Run RED test**

Run: `python -m pytest tests/ibkr_paper_30d/test_auditor_denial_report.py -q`
Expected: FAIL because the verifier does not exist.

- [ ] **Step 3: Implement report verifier**

Require the exact SID, non-elevated token, runtime digest, manifest digest, fresh timestamp, all eight DENIED results, both ALLOWED results, and a failed TCP connection to 127.0.0.1 ports 4001/4002. Validate current ACL/firewall state independently from the report without changing it.

```python
REQUIRED_DENIALS = {
    "SECRETS_READ",
    "IBKR_SECRET_READ",
    "SMTP_SECRET_READ",
    "EXECUTION_LOCK_ACCESS",
    "LIVE_DATABASE_MUTATION",
    "BROKER_WRITE_PATH_ACCESS",
    "TRADER_CONTEXT_ACCESS",
    "AUDIT_INPUT_MUTATION",
}
REQUIRED_ALLOWS = {"IMMUTABLE_EXPORT_READ", "AUDITOR_REPORT_WRITE"}
```

- [ ] **Step 4: GREEN and regression**

Run: `python -m pytest tests/ibkr_paper_30d/test_auditor_denial_report.py tests/ibkr_paper_30d/test_auditor_isolation.py -q`
Expected: PASS.

- [ ] **Step 5: Security/fault test and scoped commit**

Test stale report, wrong host/SID, inherited allow conflict, disabled firewall rule, open broker socket, writable export, report-dir denial, and hash mismatch.

```powershell
git add -- ibkr_paper_30d/auditor_isolation.py ibkr_paper_30d/cli.py tests/ibkr_paper_30d/test_auditor_denial_report.py
git commit -m "Verify actual Windows Auditor denial probes"
```

### Task 9: Restricted-Identity Synthetic Auditor Functional Test

**Files:**
- Modify: `ibkr_paper_30d/auditor_export.py`
- Modify: `ibkr_paper_30d/auditor_isolation.py`
- Create: `tests/ibkr_paper_30d/test_auditor_functional.py`

**Interfaces:**
- Consumes: provisioned account, immutable export root, report root, Task 7 runtime, Task 8 verifier.
- Produces: `AUDITOR_FUNCTIONAL_TEST_V1` receipt and final Auditor gate evidence.

- [ ] **Step 1: RED - end-to-end receipt requirements**

```python
def test_functional_receipt_requires_unchanged_input_hashes(valid_functional_receipt):
    changed = valid_functional_receipt.model_copy(update={"post_input_sha256": "0" * 64})
    assert evaluate_functional_receipt(changed).gate == "BLOCK"

def test_report_must_be_created_by_expected_restricted_sid(valid_functional_receipt):
    changed = valid_functional_receipt.model_copy(update={"effective_sid": "S-1-5-18"})
    assert evaluate_functional_receipt(changed).gate == "BLOCK"

def test_probe_and_bundle_verification_must_share_run_id(valid_functional_receipt):
    changed = valid_functional_receipt.model_copy(update={"probe_run_id": "different"})
    assert evaluate_functional_receipt(changed).gate == "BLOCK"
```

- [ ] **Step 2: Run RED test**

Run: `python -m pytest tests/ibkr_paper_30d/test_auditor_functional.py -q`
Expected: FAIL because the functional receipt does not exist.

- [ ] **Step 3: Implement Owner-side orchestration without credentials**

Publish a synthetic `NO_TRADE` bundle, emit the exact `Start-Process -Credential` command for the Owner, and ingest the restricted process result afterward. Never store or accept a plaintext password. Bind pre/post input hashes, output hash, SID, runtime hash, and probe run ID.

- [ ] **Step 4: GREEN and regression**

Run: `python -m pytest tests/ibkr_paper_30d/test_auditor_functional.py tests/ibkr_paper_30d/test_auditor_isolation.py -q`
Expected: PASS.

- [ ] **Step 5: Real restricted run, fault checks, and scoped commit**

After Owner provisioning, run the exact restricted command, verify all actual probe outcomes, then repeat with one tampered synthetic bundle and require rejection. No broker API call is permitted.

```powershell
git add -- ibkr_paper_30d/auditor_export.py ibkr_paper_30d/auditor_isolation.py tests/ibkr_paper_30d/test_auditor_functional.py
git commit -m "Prove restricted Auditor functional isolation"
```

### Task 10: Full Regression, Security, Fault, And Scope Verification

**Files:**
- Modify only test/evidence code if a demonstrated regression requires a fix.

**Interfaces:**
- Consumes: all prior tasks.
- Produces: fresh JUnit, security scan, forbidden-path scan, secret scan, fault report, and broker-write count.

- [ ] **Step 1: Run focused gate suites**

Run:

```powershell
python -m pytest tests/ibkr_paper_30d/test_market_observation.py tests/ibkr_paper_30d/test_market_observation_collector.py tests/ibkr_paper_30d/test_market_observation_ledger.py tests/ibkr_paper_30d/test_market_policy.py tests/ibkr_paper_30d/test_market_observation_cli.py tests/ibkr_paper_30d/test_auditor_provisioning.py tests/ibkr_paper_30d/test_auditor_runtime.py tests/ibkr_paper_30d/test_auditor_denial_report.py tests/ibkr_paper_30d/test_auditor_functional.py -q
```

Expected: all PASS.

- [ ] **Step 2: Run complete experiment suite**

Run: `python -m pytest tests/ibkr_paper_30d -q --junitxml=state/ibkr_paper_30d/reports/pytest.xml`
Expected: zero failures.

- [ ] **Step 3: Run security and secret scans**

```powershell
python -m bandit -r ibkr_paper_30d -q
rg -n "DU[0-9]{4,}|EMAIL_PASS|SMTP_PASSWORD|IBKR_PASSWORD" state/ibkr_paper_30d auditor_runtime
rg -n "placeOrder|cancelOrder|reqGlobalCancel" ibkr_paper_30d/market_observation*.py
```

Expected: no medium/high new Bandit findings, no secret/account matches, no order-write matches.

- [ ] **Step 4: Run fault and forbidden-path verification**

Run the existing fault-injection CLI/tests and compare `git diff --name-only $IMPLEMENTATION_BASE..HEAD` against the Global Constraints allowlist, where `IMPLEMENTATION_BASE` is the plan commit recorded before Task 1. Confirm `REAL_BROKER_WRITE_CALLS=0` from transport evidence.

- [ ] **Step 5: Commit only demonstrated fixes**

If no fix was needed, make no empty commit. Otherwise stage only the failing-test fix and commit `Fix final gate regression findings`.

### Task 11: Pre-Lifecycle V4 And Machine Gate Matrix

**Files:**
- Create: `CODEX_IBKR_PAPER_30D_PREFLIGHT_V4.md`
- Modify: `ibkr_paper_30d/cli.py`
- Modify runtime artifact: `state/ibkr_paper_30d/reports/updated_gate_matrix.json`
- Create or modify: `tests/ibkr_paper_30d/test_final_gate_status.py`

**Interfaces:**
- Consumes: verified policy, real market validation, restricted Auditor receipts, JUnit, alert/reconciliation/Codex reports.
- Produces: `CODEX_IBKR_PAPER_FINAL_PRELIFECYCLE_STATUS` fields and V4 preflight.

- [ ] **Step 1: RED - readiness cannot ignore either final gate**

```python
def test_readiness_requires_frozen_market_policy_and_auditor_pass(all_pass_receipts):
    status = build_final_gate_status(**all_pass_receipts)
    assert status["READY_FOR_HARMLESS_PAPER_LIFECYCLE_TEST"] is True
    all_pass_receipts["auditor_report"] = {"gate": "BLOCK"}
    assert build_final_gate_status(**all_pass_receipts)["READY_FOR_HARMLESS_PAPER_LIFECYCLE_TEST"] is False

def test_status_always_keeps_autonomous_trading_blocked(all_pass_receipts):
    assert build_final_gate_status(**all_pass_receipts)["AUTONOMOUS_TRADING_STATUS"] == "BLOCKED"

def test_missing_real_receipt_cannot_inherit_unit_test_pass(all_pass_receipts):
    all_pass_receipts["market_policy_report"] = {}
    status = build_final_gate_status(**all_pass_receipts)
    assert status["MARKET_DATA_GATE"] == "BLOCK"
```

- [ ] **Step 2: Run RED test**

Run: `python -m pytest tests/ibkr_paper_30d/test_final_gate_status.py -q`
Expected: FAIL until the status builder consumes both new evidence schemas.

- [ ] **Step 3: Implement evidence-driven status and V4 generator**

Report implementation head, test counts, all required gate fields, policy version/hash, restricted identity/probe status, forbidden-path result, broker-write count, unresolved blockers, readiness, and permanent autonomous BLOCK. Never infer PASS from implementation existence.

- [ ] **Step 4: GREEN and full regression**

Run:

```powershell
python -m pytest tests/ibkr_paper_30d/test_final_gate_status.py -q
python -m pytest tests/ibkr_paper_30d -q --junitxml=state/ibkr_paper_30d/reports/pytest.xml
```

Expected: all PASS.

- [ ] **Step 5: Final security/fault check and scoped commit**

Generate V4 and the matrix from fresh receipts, scan both for raw account IDs/secrets, run `git diff --check`, and commit:

```powershell
git add -- CODEX_IBKR_PAPER_30D_PREFLIGHT_V4.md ibkr_paper_30d/cli.py tests/ibkr_paper_30d/test_final_gate_status.py
git commit -m "Reissue final IBKR pre-lifecycle gates"
```

Stop. Even if `READY_FOR_HARMLESS_PAPER_LIFECYCLE_TEST=true`, do not submit, cancel, or modify an order and do not start the experiment.
