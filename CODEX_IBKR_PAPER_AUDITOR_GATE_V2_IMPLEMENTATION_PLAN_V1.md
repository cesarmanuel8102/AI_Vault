# Codex IBKR Paper Auditor Gate V2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement a fail-closed Month-1 PAPER Auditor gate that proves least privilege, exact authorized-runtime integrity, immutable evidence consumption, and paper-identity binding without claiming network containment.

**Architecture:** A pure Python evaluator consumes one consolidated, hash-bound V2 receipt. A separate runtime-integrity module verifies an exact PowerShell fileset through a two-level manifest, performs deterministic AST/capability analysis, and feeds the receipt generator. A narrowly scoped PowerShell orchestrator runs under `CodexAuditorV1`; report and preflight writers consume only a validated V2 evaluation. Real execution stops at a reviewed runtime-only administrator checkpoint if the corrected runtime is not already installed.

**Tech Stack:** Python 3, dataclasses, canonical JSON/SHA-256 helpers already in the repository, pytest, Windows PowerShell 5.1 AST APIs, existing standalone Auditor PowerShell runtime.

**Spec:** `docs/superpowers/specs/2026-09-20-auditor-gate-v2-rebaseline-design.md`

## Global Constraints

- Month-1 only: `PAPER_ONLY=true`, `LIVE_ALLOWED=false`, `REAL_MONEY_ALLOWED=false`.
- Expected Auditor SID: `S-1-5-21-214160970-1890373857-4055601883-1012`.
- `AUDITOR_TECHNICAL_SOCKET_REACHABILITY` and `AUDITOR_NETWORK_ISOLATION_REQUIRED` are separate facts.
- Month-1 residual risk remains explicit: `AUDITOR_UNAUTHORIZED_RAW_API_PATH_POSSIBLE=true` and `AUDITOR_COMPROMISE_CONTAINMENT_NOT_CLAIMED=true`.
- Preserve `LEGACY_FIREWALL_CONTROL=INEFFECTIVE_FOR_LOOPBACK_REQUIREMENT`; it contributes nothing to V2 PASS and is not modified.
- A V2 PASS requires one receipt from one real non-elevated `CodexAuditorV1` execution; evidence cannot be stitched across runs.
- A bare `gate=PASS`, any V1 receipt, and any partial or stale receipt must remain BLOCK.
- No WFP, firewall, ACL, account, toolchain, SDK, market-data, or order-operation changes.
- Do not touch `brain/**`, `tmp_agent/brain_v9/**`, `HIVE/**`, `H2/**`, `H2-R2/**`, order executors, or live-account configuration.
- Never persist a clear-text IBKR account number.
- Receipt freshness window: 24 hours; receipt time must also be no earlier than its bound paper-identity receipt and runtime deployment manifest.
- Every task uses RED, minimal GREEN, focused regression, scope check, and a scoped commit.

## Review Focus

- A syntactically valid V2 receipt with one omitted nested field must BLOCK, never receive defaults that promote it.
- Case-colliding or duplicate JSON keys in manifests and receipts must BLOCK before semantic validation.
- The permitted narrow `TcpClient` endpoint classifier must not become a generic network or process launcher.
- Runtime-manifest self-integrity must use the external deployment manifest; no circular self-hash or unhashed runtime file is allowed.
- A valid Auditor receipt bound to a different paper identity, environment reference, or materially changed identity receipt must BLOCK.

---

## File Structure

- Create `ibkr_paper_30d/auditor_gate_v2.py`: strict receipt models, parsing, freshness, single-run coherence, paper binding, and canonical gate evaluation.
- Create `ibkr_paper_30d/auditor_runtime_v2.py`: runtime/deployment manifest construction, exact fileset verification, PowerShell capability assessment.
- Create `ibkr_paper_30d/auditor_v2_artifacts.py`: residual-risk JSON, Markdown gate report, Preflight V4, and sanitized matrix projections.
- Create `auditor_runtime/AUDITOR_GATE_V2_PROBE.ps1`: exact consolidated restricted-token run.
- Create `AUDITOR_RUNTIME_V2_DEPLOYMENT.ps1`: Review/Install/Remove runtime-only checkpoint; never execute Install/Remove without later authorization.
- Create `tests/ibkr_paper_30d/test_auditor_gate_v2.py`: evaluator, negative matrix, paper binding, and artifact tests.
- Create `tests/ibkr_paper_30d/test_auditor_runtime_v2.py`: fileset, hash, AST/capability, and PowerShell probe tests.
- Modify `ibkr_paper_30d/cli.py`: V2 receipt input, evaluator integration, explicit compatibility aliases, report commands.
- Modify `tests/ibkr_paper_30d/test_ibkr_readonly.py`: implementation-status integration and permanent safety-state regression.
- Create during authorized implementation: `AUDITOR_MONTH1_PAPER_RESIDUAL_RISK_ACCEPTANCE_V1.json`, `AUDITOR_ISOLATION_GATE_V2_REPORT.md`, and `CODEX_IBKR_PAPER_30D_PREFLIGHT_V4.md`.
- Update atomically only after validated evidence: `state/ibkr_paper_30d/reports/updated_gate_matrix.json`.

### Task 1: V2 Receipt And Evaluation Data Models

**Files:**
- Create: `ibkr_paper_30d/auditor_gate_v2.py`
- Create: `tests/ibkr_paper_30d/test_auditor_gate_v2.py`

**Interfaces:**
- Produces: `AuditorGateV2Receipt`, `AuditorGateV2Evaluation`, `parse_auditor_gate_v2_receipt(source: bytes | str)`, `EXPECTED_AUDITOR_SID`, `RECEIPT_MAX_AGE`.
- Consumes: `canonical_bytes` and `sha256_json` from `ibkr_paper_30d.canonical`.

- [ ] **Step 1: Write failing strict-schema tests**

```python
def test_v2_receipt_rejects_unknown_missing_and_duplicate_semantics(complete_receipt):
    extra = deepcopy(complete_receipt)
    extra["unknown"] = True
    with pytest.raises(ReceiptValidationError, match="UNKNOWN_FIELD"):
        parse_auditor_gate_v2_receipt(canonical_bytes(extra))

    missing = deepcopy(complete_receipt)
    del missing["runtime_integrity"]
    with pytest.raises(ReceiptValidationError, match="MISSING_FIELD"):
        parse_auditor_gate_v2_receipt(canonical_bytes(missing))

    duplicate_source = b'{"schema":"AUDITOR_GATE_V2_RECEIPT_V1","schema":"DUPLICATE"}'
    with pytest.raises(ReceiptValidationError, match="DUPLICATE_KEY"):
        parse_auditor_gate_v2_receipt(duplicate_source)
```

- [ ] **Step 2: Run RED**

Run: `pytest -q tests/ibkr_paper_30d/test_auditor_gate_v2.py -k receipt`

Expected: FAIL because the module and strict models do not exist.

- [ ] **Step 3: Implement immutable models and exact-key parsing**

```python
EXPECTED_AUDITOR_SID = "S-1-5-21-214160970-1890373857-4055601883-1012"
RECEIPT_MAX_AGE = timedelta(hours=24)

@dataclass(frozen=True)
class AuditorGateV2Receipt:
    schema: str
    gate_version: str
    run_id: str
    started_at_utc: datetime
    completed_at_utc: datetime
    effective_sid: str
    token_elevated: bool
    separate_process: bool
    runtime_integrity: Mapping[str, object]
    target_validation_matrix: Sequence[Mapping[str, object]]
    capability_outcomes: Mapping[str, str]
    functional_auditor: Mapping[str, object]
    paper_identity: Mapping[str, object]
    network_facts: Mapping[str, object]
    output: Mapping[str, object]
```

Parse raw bytes/text with an `object_pairs_hook` before model construction. Reject unknown keys, wrong scalar types, duplicate/case-colliding source keys, non-UTC timestamps, invalid SHA-256 values, and mutable defaults.

- [ ] **Step 4: Run focused GREEN and regressions**

Run: `pytest -q tests/ibkr_paper_30d/test_auditor_gate_v2.py -k receipt && pytest -q tests/ibkr_paper_30d/test_config_and_redaction.py`

Expected: PASS.

- [ ] **Step 5: Scope check and commit**

Run: `git diff --name-only` and require only the two Task 1 paths.

Commit: `git commit -m "Add strict Auditor Gate V2 receipt models"`

### Task 2: Runtime Manifest V2 And Exact Fileset Authority

**Files:**
- Create: `ibkr_paper_30d/auditor_runtime_v2.py`
- Create: `tests/ibkr_paper_30d/test_auditor_runtime_v2.py`

**Interfaces:**
- Produces: `build_runtime_manifest_v2(runtime_root, payload_names)`, `build_deployment_manifest_v2(runtime_manifest_path, payload_paths)`, `verify_runtime_fileset_v2(runtime_root, deployment_manifest)`.
- Consumes: `canonical_bytes`; exact payload allowlist `CODEX_DECISION_AUDITOR_V1.ps1`, `AUDITOR_DENIAL_PROBE_V1.ps1`, `AUDITOR_GATE_V2_PROBE.ps1`.

- [ ] **Step 1: Write RED tests for exact fileset and two-level hashes**

```python
@pytest.mark.parametrize("mutation", ["EXTRA", "MISSING", "PAYLOAD_HASH", "RUNTIME_MANIFEST_HASH"])
def test_runtime_v2_blocks_every_fileset_or_hash_mutation(tmp_path, staged_runtime, mutation):
    deployment = build_deployment_manifest_v2(staged_runtime / "AUDITOR_RUNTIME_MANIFEST_V2.json", staged_runtime.glob("*.ps1"))
    mutate_runtime(staged_runtime, deployment, mutation)
    result = verify_runtime_fileset_v2(staged_runtime, deployment)
    assert result.status == "BLOCK"
```

Require the runtime directory set to equal the three scripts plus `AUDITOR_RUNTIME_MANIFEST_V2.json`. The external deployment manifest must hash all four files, including the runtime manifest, eliminating circular self-hashing.

- [ ] **Step 2: Run RED**

Run: `pytest -q tests/ibkr_paper_30d/test_auditor_runtime_v2.py -k fileset`

Expected: FAIL because manifest builders/verifier do not exist.

- [ ] **Step 3: Implement canonical manifests and verifier**

```python
RUNTIME_PAYLOAD_ALLOWLIST = (
    "AUDITOR_DENIAL_PROBE_V1.ps1",
    "AUDITOR_GATE_V2_PROBE.ps1",
    "CODEX_DECISION_AUDITOR_V1.ps1",
)

def verify_runtime_fileset_v2(root: Path, deployment: Mapping[str, object]) -> RuntimeIntegrityResult:
    expected = set(RUNTIME_PAYLOAD_ALLOWLIST) | {"AUDITOR_RUNTIME_MANIFEST_V2.json"}
    actual = {item.name for item in root.iterdir() if item.is_file()}
    if actual != expected:
        return RuntimeIntegrityResult.block("RUNTIME_FILESET_MISMATCH")
    # Verify deployment-manifest hashes first, then runtime-manifest schema and payload hashes.
```

Reject reparse points, non-files, path separators, case collisions, malformed hashes, schema drift, and unrecognized files.

- [ ] **Step 4: Run focused GREEN and existing runtime tests**

Run: `pytest -q tests/ibkr_paper_30d/test_auditor_runtime_v2.py -k fileset && pytest -q tests/ibkr_paper_30d/test_auditor_runtime.py`

Expected: PASS.

- [ ] **Step 5: Scope check and commit**

Require only `auditor_runtime_v2.py` and its test file, then commit `Add exact Auditor runtime V2 fileset authority`.

### Task 3: Structural Capability Scanner And Runtime Verifier

**Files:**
- Modify: `ibkr_paper_30d/auditor_runtime_v2.py`
- Modify: `tests/ibkr_paper_30d/test_auditor_runtime_v2.py`

**Interfaces:**
- Produces: `assess_runtime_capabilities(runtime_root) -> RuntimeCapabilityAssessment` with the six required structural booleans and the derived compatibility predicate `ORDER_WRITE_MODULE_AVAILABLE`.
- Consumes: an already verified exact fileset.

- [ ] **Step 1: Write RED tests for forbidden capability introduction**

```python
@pytest.mark.parametrize(
    ("payload", "predicate"),
    [
        ("Import-Module ibapi", "BROKER_MODULE_AVAILABLE"),
        ("placeOrder", "ORDER_WRITE_SYMBOL_AVAILABLE"),
        ("ibkr_paper_30d.broker", "EXECUTION_ADAPTER_AVAILABLE"),
        ("Acquire-ExecutionLock", "EXECUTION_LOCK_CLIENT_AVAILABLE"),
        ("NamedPipeClientStream", "TRADER_IPC_CLIENT_AVAILABLE"),
        ("IBKR_PASSWORD", "BROKER_CREDENTIAL_SOURCE_AVAILABLE"),
    ],
)
def test_capability_scanner_fails_closed_on_forbidden_runtime_surface(staged_runtime, payload, predicate):
    inject_into_probe(staged_runtime, payload)
    result = assess_runtime_capabilities(staged_runtime)
    assert result.status == "BLOCK"
    assert result.predicates[predicate] is True
```

For module and order-symbol mutations, also assert `ORDER_WRITE_MODULE_AVAILABLE=true`; for the approved runtime assert all six structural predicates and `ORDER_WRITE_MODULE_AVAILABLE` are false. Define `ORDER_WRITE_MODULE_AVAILABLE` mechanically as the fail-closed aggregate of broker/protocol module, order-write symbol, and execution-adapter availability, never as a separately supplied receipt value.

Add tests for order submit/cancel/modify forms, alternative IBKR protocol clients, `Start-Process`, `Invoke-Expression`, `Add-Type`, arbitrary child PowerShell/Python launch, generic sockets, executable/DLL payloads, and broadened import paths. Preserve one narrow exception: `TcpClient` is allowed only in `AUDITOR_DENIAL_PROBE_V1.ps1` inside `Test-TcpEndpoint`, with literal loopback addresses and validated ports.

- [ ] **Step 2: Run RED**

Run: `pytest -q tests/ibkr_paper_30d/test_auditor_runtime_v2.py -k capability`

Expected: FAIL because the scanner does not exist.

- [ ] **Step 3: Implement deterministic token and PowerShell AST analysis**

Use Windows PowerShell's parser through a fixed subprocess argument vector, parse returned JSON, and fail closed if parsing is unavailable or returns any error. Never execute runtime source during scanning.

```python
FORBIDDEN_SYMBOL_GROUPS = {
    "BROKER_MODULE_AVAILABLE": {"ibapi", "ibkr_paper_30d.broker", "IBKR protocol client"},
    "ORDER_WRITE_SYMBOL_AVAILABLE": {"placeOrder", "cancelOrder", "reqGlobalCancel", "modifyOrder"},
    "EXECUTION_ADAPTER_AVAILABLE": {"ibkr_paper_30d.broker", "execution adapter"},
    "EXECUTION_LOCK_CLIENT_AVAILABLE": {"Acquire-ExecutionLock", "execution_lock"},
    "TRADER_IPC_CLIENT_AVAILABLE": {"NamedPipeClientStream", "trader_invocation"},
    "BROKER_CREDENTIAL_SOURCE_AVAILABLE": {"IBKR_PASSWORD", "credential source"},
}
```

The real implementation must use normalized AST/token classifications rather than treating the illustrative labels with spaces as literal-only matches. Unknown command, module, process, IPC, credential-source, or network-helper classifications fail closed.

- [ ] **Step 4: Run focused GREEN, AST tests, and security regression**

Run: `pytest -q tests/ibkr_paper_30d/test_auditor_runtime_v2.py -k capability && pytest -q tests/ibkr_paper_30d/test_auditor_runtime.py`

Expected: PASS.

- [ ] **Step 5: Scope check and commit**

Commit only the Task 3 module/test changes as `Add Auditor runtime capability analysis`.

### Task 4: Canonical Residual-Risk Acceptance Artifact

**Files:**
- Create: `ibkr_paper_30d/auditor_v2_artifacts.py`
- Modify: `tests/ibkr_paper_30d/test_auditor_gate_v2.py`
- Create only after a validated real receipt exists: `AUDITOR_MONTH1_PAPER_RESIDUAL_RISK_ACCEPTANCE_V1.json`

**Interfaces:**
- Produces: `build_residual_risk_acceptance(receipt, evaluation, owner_decision)`, `write_immutable_json(path, payload)`.
- Consumes: a PASS V2 evaluation and paper identity binding; never accepts raw account IDs.

- [ ] **Step 1: Write RED tests for exact fields, canonical bytes, and tamper detection**

```python
def test_residual_risk_binds_paper_identity_without_cleartext_account(
    complete_receipt, pass_evaluation, expected_identity, owner_decision
):
    artifact = build_residual_risk_acceptance(
        complete_receipt, pass_evaluation, owner_decision
    )
    assert artifact["EXPECTED_PAPER_ACCOUNT_IDENTITY_HASH"] == expected_identity.expected_account_hash
    assert artifact["PAPER_IDENTITY_RECEIPT_SHA256"] == expected_identity.receipt_sha256
    assert artifact["AUDITOR_TECHNICAL_SOCKET_REACHABILITY"] is True
    assert artifact["AUDITOR_NETWORK_ISOLATION_REQUIRED"] is False
    assert expected_identity.raw_account not in canonical_bytes(artifact).decode("ascii")
```

Test write-once behavior, canonical hash verification, artifact tampering, live/real-money toggles, environment changes, and all expiration triggers.

- [ ] **Step 2: Run RED**

Run: `pytest -q tests/ibkr_paper_30d/test_auditor_gate_v2.py -k residual_risk`

Expected: FAIL because artifact generation does not exist.

- [ ] **Step 3: Implement canonical immutable artifact generation**

The artifact must include `PAPER_ONLY=true`, `LIVE_ALLOWED=false`, `REAL_MONEY_ALLOWED=false`, `AUDITOR_TECHNICAL_SOCKET_REACHABILITY=true`, `AUDITOR_NETWORK_ISOLATION_REQUIRED=false`, `AUDITOR_UNAUTHORIZED_RAW_API_PATH_POSSIBLE=true`, `AUDITOR_COMPROMISE_CONTAINMENT_NOT_CLAIMED=true`, `AUDITOR_ORDER_AUTHORITY_GRANTED=false`, `AUDITOR_BROKER_CONTROL_PATH_AUTHORIZED=false`, `EXPECTED_PAPER_ACCOUNT_IDENTITY_HASH`, `PAPER_IDENTITY_RECEIPT_SHA256`, `PAPER_ENVIRONMENT_REFERENCE`, optional `BROKER_SESSION_ENVIRONMENT_REFERENCE`, `PAPER_IDENTITY_VERIFIED_AT_UTC`, source receipt hashes, expiration triggers, and this sentence: `The authenticated local IB Gateway may technically accept another local API client.` The writer must refuse fixture/synthetic receipts and must leave the operational artifact absent when no validated real receipt exists.

- [ ] **Step 4: Run focused GREEN and secret scan**

Run: `pytest -q tests/ibkr_paper_30d/test_auditor_gate_v2.py -k residual_risk`

The focused test must scan the exact `tmp_path` artifact bytes for raw-account and secret patterns. Also run: `rg -n "DU[0-9]{4,}|EMAIL_PASS|SMTP_PASSWORD|IBKR_PASSWORD" ibkr_paper_30d/auditor_v2_artifacts.py`; if the operational artifact exists, include its exact path in the same command.

Expected: tests PASS and grep has no matches.

- [ ] **Step 5: Scope check and commit**

Commit only the artifact module and tests as `Add paper-bound Auditor residual-risk acceptance`. Commit the operational JSON later only if it was generated from the accepted real receipt; never commit a fixture-derived substitute.

### Task 5: V2 Gate Evaluator

**Files:**
- Modify: `ibkr_paper_30d/auditor_gate_v2.py`
- Modify: `tests/ibkr_paper_30d/test_auditor_gate_v2.py`

**Interfaces:**
- Produces: `evaluate_auditor_gate_v2(receipt, expected_paper_identity, now) -> AuditorGateV2Evaluation`.
- Consumes: strict parsed receipt, verified runtime result, exact protected paper identity expectation.

- [ ] **Step 1: Write the single positive-gate RED test**

```python
def test_gate_v2_passes_only_one_complete_coherent_receipt(complete_receipt, expected_identity, now):
    result = evaluate_auditor_gate_v2(complete_receipt, expected_identity, now)
    assert result.canonical_gate == "PASS"
    assert result.compatibility_gate == "PASS"
    assert result.gate_version == "V2"
    assert result.reason_codes == ()
```

Require exactly ten unique target names and ten capability outcomes with the approved values; validate runtime, functional audit, paper identity, immutable bundle, output report, run ID, and timestamps.

- [ ] **Step 2: Run RED**

Run: `pytest -q tests/ibkr_paper_30d/test_auditor_gate_v2.py -k gate_v2_passes`

Expected: FAIL because the evaluator is incomplete.

- [ ] **Step 3: Implement one fail-closed predicate path**

```python
def evaluate_auditor_gate_v2(receipt, expected_paper_identity, now):
    reasons = tuple(_evaluate_predicates(receipt, expected_paper_identity, now))
    status = "PASS" if not reasons else "BLOCK"
    return AuditorGateV2Evaluation(
        canonical_gate=status,
        compatibility_gate=status,
        gate_version="V2",
        reason_codes=reasons,
    )
```

There must be no alternate PASS constructor or special-case bypass.

- [ ] **Step 4: Run focused GREEN and local gate regression**

Run: `pytest -q tests/ibkr_paper_30d/test_auditor_gate_v2.py -k gate_v2_passes && pytest -q tests/ibkr_paper_30d/test_auditor_isolation.py`

Expected: PASS.

- [ ] **Step 5: Scope check and commit**

Commit Task 5 changes as `Add fail-closed Auditor Gate V2 evaluator`.

### Task 6: Legacy, Partial, Mixed-Run, And Negative Matrix

**Files:**
- Modify: `tests/ibkr_paper_30d/test_auditor_gate_v2.py`
- Modify: `ibkr_paper_30d/auditor_gate_v2.py` only for failures exposed by tests.

**Interfaces:**
- Expands evaluator rejection coverage; no new PASS interface.

- [ ] **Step 1: Add the explicit 22-case negative parameterization**

Cases: V1-only; partial; stale; mixed-run; wrong SID; elevated token; wrong paper-account hash; wrong paper-identity receipt hash; paper-environment change; runtime extra file; runtime missing file; runtime hash mismatch; broker module introduced; order symbol introduced; execution-lock code introduced; Trader IPC introduced; missing target row; missing capability outcome; broadened runtime bundle; residual-risk artifact tamper; `LIVE_ALLOWED=true`; `REAL_MONEY_ALLOWED=true`.

```python
@pytest.mark.parametrize("mutation", NEGATIVE_GATE_MUTATIONS, ids=lambda item: item.name)
def test_every_negative_mutation_blocks(complete_receipt, expected_identity, now, mutation):
    mutated = mutation.apply(deepcopy(complete_receipt))
    result = evaluate_auditor_gate_v2(mutated, expected_identity, now)
    assert result.canonical_gate == "BLOCK"
    assert mutation.reason_code in result.reason_codes
```

- [ ] **Step 2: Run RED and record every unexpected PASS**

Run: `pytest -q tests/ibkr_paper_30d/test_auditor_gate_v2.py -k negative --maxfail=22`

Expected: one or more FAIL until every mutation is rejected for its specific reason.

- [ ] **Step 3: Add only missing fail-closed predicates**

Do not add defaults. Normalize no absent field. Reject duplicate target names, duplicate capability names, mismatched run IDs, and receipts predating bound inputs.

- [ ] **Step 4: Run GREEN and full Gate V2 tests**

Run: `pytest -q tests/ibkr_paper_30d/test_auditor_gate_v2.py`

Expected: PASS, including all 22 negative cases and the single positive case.

- [ ] **Step 5: Scope check and commit**

Commit only evaluator/test changes as `Reject incomplete and legacy Auditor V2 evidence`.

### Task 7: Paper Identity Binding And Expiration Logic

**Files:**
- Modify: `ibkr_paper_30d/auditor_gate_v2.py`
- Modify: `tests/ibkr_paper_30d/test_auditor_gate_v2.py`

**Interfaces:**
- Produces: `PaperIdentityBinding.from_readonly_receipt(readonly_payload, receipt_bytes)`, `evaluate_acceptance_expiration(acceptance, current_context)`.
- Consumes: `REAL_IBKR_READ_ONLY_RECONCILIATION_V1`, protected expected hash, canonical receipt bytes.

- [ ] **Step 1: Write RED tests for identity/environment binding**

```python
def test_paper_binding_uses_hashes_and_broker_derived_gate(readonly_receipt_bytes, expected_hash):
    binding = PaperIdentityBinding.from_readonly_receipt(json.loads(readonly_receipt_bytes), readonly_receipt_bytes)
    assert binding.expected_account_hash == expected_hash
    assert binding.receipt_sha256 == hashlib.sha256(readonly_receipt_bytes).hexdigest()
    assert binding.paper_identity_gate == "PASS"
    assert binding.raw_account_identity_persisted is False
```

Add expiration tests for changed account hash, receipt hash, paper environment, broker-session environment, runtime/deployment hash, privilege boundary, experiment completion/termination, and live/real-money flags.

- [ ] **Step 2: Run RED**

Run: `pytest -q tests/ibkr_paper_30d/test_auditor_gate_v2.py -k "paper_binding or expiration"`

Expected: FAIL because binding/expiration helpers do not exist.

- [ ] **Step 3: Implement exact broker-derived binding**

Reject configuration-only `PAPER_ONLY`. Require the read-only receipt's paper identity, read-only identity, and broker reconciliation gates to be PASS; bind masked environment references and never preserve the account number.

- [ ] **Step 4: Run focused GREEN plus readonly regression**

Run: `pytest -q tests/ibkr_paper_30d/test_auditor_gate_v2.py -k "paper_binding or expiration" && pytest -q tests/ibkr_paper_30d/test_ibkr_readonly.py`

Expected: PASS.

- [ ] **Step 5: Scope check and commit**

Commit Task 7 changes as `Bind Auditor V2 acceptance to paper identity`.

### Task 8: Corrected Consolidated Probe And Runtime-Only Administrator Checkpoint

**Files:**
- Create: `auditor_runtime/AUDITOR_GATE_V2_PROBE.ps1`
- Create: `AUDITOR_RUNTIME_V2_DEPLOYMENT.ps1`
- Modify: `tests/ibkr_paper_30d/test_auditor_runtime_v2.py`
- Modify: `ibkr_paper_30d/auditor_runtime_v2.py`

**Interfaces:**
- Probe consumes: immutable bundle, immutable paper-identity receipt, target manifest, runtime manifest V2, external deployment manifest, expected SID, report directory.
- Probe produces: one `AUDITOR_GATE_V2_RECEIPT_V1` JSON report with one run ID.
- Deployment script supports only `Review`, `Install`, and `Remove`; Install/Remove remain unexecuted.

- [ ] **Step 1: Write RED PowerShell tests with fake child results**

Test exact SID/non-elevation, one run ID, all target rows/outcomes, functional result, bundle identity, paper identity hashes, runtime hashes, report path, network facts, canonical create-new write, and fail-closed behavior on any child failure. Test AST parsing and prove parameters cannot select arbitrary scripts or destinations.

- [ ] **Step 2: Run RED**

Run: `pytest -q tests/ibkr_paper_30d/test_auditor_runtime_v2.py -k consolidated_probe`

Expected: FAIL because the orchestrator does not exist.

- [ ] **Step 3: Implement the fixed orchestrator and Review-only checkpoint behavior**

The orchestrator may invoke only exact sibling filenames after deployment-manifest verification. It must not accept executable/script path parameters. The deployment script must check administrator status before mutation, bind the existing exact SID, atomically install only the four runtime files plus provisioning deployment manifest, preserve existing ACLs, and refuse any unrecognized prior state.

- [ ] **Step 4: Run focused GREEN and nonprivileged Review**

Run: `pytest -q tests/ibkr_paper_30d/test_auditor_runtime_v2.py`

Run: `powershell.exe -NoProfile -File .\AUDITOR_RUNTIME_V2_DEPLOYMENT.ps1 -Mode Review`

Expected: tests PASS; Review prints script/runtime/manifest SHA-256 values and exact future Install/Remove commands without host mutation.

- [ ] **Step 5: Inspect installed runtime without mutation**

Compare installed ProgramData hashes with V2 deployment hashes. If they differ, set `NEW_ADMIN_ACTION_REQUIRED=true`, publish the reviewed checkpoint, and do not attempt a real V2 receipt. If they match, prepare the exact non-elevated `runas` command for Owner execution; do not execute or supply credentials automatically.

- [ ] **Step 6: Scope check and commit**

Allow only the two scripts, runtime module, and runtime tests. Commit `Add consolidated Auditor V2 probe checkpoint`.

### Task 9: Auditor Isolation Gate V2 Report Generation

**Files:**
- Modify: `ibkr_paper_30d/auditor_v2_artifacts.py`
- Modify: `tests/ibkr_paper_30d/test_auditor_gate_v2.py`
- Create after real receipt exists: `AUDITOR_ISOLATION_GATE_V2_REPORT.md`

**Interfaces:**
- Produces: `render_auditor_gate_v2_report(receipt, evaluation, evidence_hashes) -> str`.
- Consumes: one validated receipt or a BLOCK result explaining missing evidence.

- [ ] **Step 1: Write RED snapshot assertions**

Require all V2 predicates, evidence paths/hashes, canonical and alias gates, network fact/requirement separation, firewall classification, WFP deferral, unresolved reasons, paper identity hash/reference, and no raw account identity.

- [ ] **Step 2: Run RED**

Run: `pytest -q tests/ibkr_paper_30d/test_auditor_gate_v2.py -k gate_report`

- [ ] **Step 3: Implement deterministic Markdown rendering**

Sort predicate and evidence rows; render `BLOCK` when the real receipt is absent or invalid. Never convert fixture evidence into an operational PASS report.

- [ ] **Step 4: Run GREEN and secret scan**

Run: `pytest -q tests/ibkr_paper_30d/test_auditor_gate_v2.py -k gate_report`

If the operational report exists, run: `rg -n "DU[0-9]{4,}|EMAIL_PASS|SMTP_PASSWORD|IBKR_PASSWORD" AUDITOR_ISOLATION_GATE_V2_REPORT.md`. Otherwise, assert its absence and scan the exact temporary report bytes in the focused test.

- [ ] **Step 5: Scope check and commit**

Commit `Add Auditor Gate V2 evidence report`.

### Task 10: Pre-Lifecycle V4 And Gate-Matrix Integration

**Files:**
- Modify: `ibkr_paper_30d/cli.py`
- Modify: `tests/ibkr_paper_30d/test_ibkr_readonly.py`
- Create: `CODEX_IBKR_PAPER_30D_PREFLIGHT_V4.md`
- Update at runtime: `state/ibkr_paper_30d/reports/updated_gate_matrix.json`

**Interfaces:**
- `load_and_evaluate_auditor_gate_v2(source: Path | bytes, expected_paper_identity, now)` converts absent, invalid, legacy, or V1 input into a BLOCK evaluation with reason codes.
- `build_implementation_status(*, test_count, test_failures, readonly_report, alert_report, real_codex_report, auditor_v2_evaluation, implementation_head)` consumes that evaluation object, not a trusted receipt gate string.
- CLI adds explicit receipt/report paths and `write-auditor-v2-artifacts`; it does not execute the restricted probe or elevate.

- [ ] **Step 1: Write RED integration tests**

```python
def test_status_ignores_bare_or_v1_auditor_pass(
    complete_status_inputs, expected_identity, now
):
    evaluation = load_and_evaluate_auditor_gate_v2(
        canonical_bytes({"gate": "PASS"}), expected_identity, now
    )
    status = build_implementation_status(
        **complete_status_inputs,
        auditor_v2_evaluation=evaluation,
    )
    assert status["AUDITOR_LEAST_PRIVILEGE_AND_RUNTIME_INTEGRITY_GATE_V2"] == "BLOCK"
    assert status["AUDITOR_ISOLATION_GATE_V2"] == "BLOCK"

def test_status_uses_validated_v2_evaluation_but_never_authorizes_orders(
    complete_status_inputs, pass_evaluation
):
    status = build_implementation_status(
        **complete_status_inputs,
        auditor_v2_evaluation=pass_evaluation,
    )
    assert status["AUDITOR_ISOLATION_GATE_V2"] == "PASS"
    assert status["READY_FOR_HARMLESS_PAPER_LIFECYCLE_TEST"] is False
    assert status["REAL_PAPER_ORDER_WRITE_AUTHORIZED"] is False
```

- [ ] **Step 2: Run RED**

Run: `pytest -q tests/ibkr_paper_30d/test_ibkr_readonly.py -k auditor`

- [ ] **Step 3: Integrate canonical evaluator and atomic artifact writing**

Expose both V2 gate names with identical values and `gate_version=V2`. Add all four network/risk fields, WFP deferral, legacy firewall classification, paper restrictions, and unresolved reasons. Keep Market Data unchanged and independently BLOCK unless already frozen by its existing policy.

- [ ] **Step 4: Generate Preflight V4 from actual state**

If Task 8 is awaiting administrator action, V4 must say Gate V2 BLOCK and name that exact blocker. If a real accepted receipt exists, report PASS but keep Market Data and lifecycle authorization independent. Atomically update the operational matrix only from the validated evaluation.

- [ ] **Step 5: Run GREEN and integration regressions**

Run: `pytest -q tests/ibkr_paper_30d/test_ibkr_readonly.py tests/ibkr_paper_30d/test_auditor_gate_v2.py`

Expected: PASS.

- [ ] **Step 6: Scope check and commit**

Commit only CLI/tests/Preflight V4 as `Integrate Auditor Gate V2 into preflight status`.

### Task 11: Full Regression, Security, Fault, And Scope Verification

**Files:**
- Verify only; modify prior task files only to fix demonstrated failures.

**Interfaces:**
- Produces final evidence counts, hashes, install checkpoint status, and zero broker-write assertion.

- [ ] **Step 1: Run the complete experiment suite**

Run: `pytest -q tests/ibkr_paper_30d --junitxml=state/ibkr_paper_30d/reports/pytest.xml`

Expected: zero failures.

- [ ] **Step 2: Run dedicated Auditor and fault suites**

Run: `pytest -q tests/ibkr_paper_30d/test_auditor_gate_v2.py tests/ibkr_paper_30d/test_auditor_runtime_v2.py tests/ibkr_paper_30d/test_auditor_runtime.py tests/ibkr_paper_30d/test_auditor_provisioning.py tests/ibkr_paper_30d/test_fault_injection.py`

Expected: zero failures.

- [ ] **Step 3: Parse every changed PowerShell file**

Use `[System.Management.Automation.Language.Parser]::ParseFile` against `AUDITOR_GATE_V2_PROBE.ps1`, `AUDITOR_RUNTIME_V2_DEPLOYMENT.ps1`, and existing runtime scripts. Require zero parse errors.

- [ ] **Step 4: Run security and secret scans**

Run: `python -m bandit -r ibkr_paper_30d -q`

Require no medium/high findings introduced by this change.

Run: `rg -n "DU[0-9]{4,}|EMAIL_PASS|SMTP_PASSWORD|IBKR_PASSWORD" ibkr_paper_30d auditor_runtime AUDITOR_*_V1.json AUDITOR_*_V2_REPORT.md`

Expected: no secret/account matches.

- [ ] **Step 5: Prove no order-write implementation or call occurred**

Run: `rg -n "placeOrder|cancelOrder|reqGlobalCancel" auditor_runtime ibkr_paper_30d/auditor_gate_v2.py ibkr_paper_30d/auditor_runtime_v2.py ibkr_paper_30d/auditor_v2_artifacts.py`

Any matches must be scanner constants/test evidence only, never executable calls. Confirm transport evidence reports `REAL_BROKER_WRITE_CALLS=0`.

- [ ] **Step 6: Run forbidden-path and diff checks**

Compare changed paths to the File Structure allowlist and explicitly reject changes under every forbidden directory. Run `git diff --check` and require a clean result.

- [ ] **Step 7: Validate operational stop state**

Require:

```text
WFP_AUDITOR_FRONT=DEFERRED
AUDITOR_V2_IMPLEMENTATION_AUTHORIZED=false
IMPLEMENTATION_AUTHORIZED=false
INSTALLATION_PERFORMED=false unless separately authorized later
REAL_BROKER_WRITE_CALLS=0
READY_FOR_HARMLESS_PAPER_LIFECYCLE_TEST=false
LIVE_ALLOWED=false
REAL_MONEY_ALLOWED=false
AUTONOMOUS_TRADING_STATUS=BLOCKED
```

- [ ] **Step 8: Commit verified fixes only**

If verification required no code changes, make no empty commit. Otherwise commit only demonstrated fixes as `Fix Auditor Gate V2 verification findings`.

## Execution Stop Conditions

- Stop before any administrator action and return the reviewed runtime-only script/hash/commands to the Owner.
- Stop if the real corrected restricted-token receipt cannot be generated; report Gate V2 BLOCK without stitching old evidence.
- Stop if paper identity or environment binding differs from the protected expectation.
- Stop if any runtime capability predicate is present or indeterminate.
- Stop after artifacts and verification; do not collect market data, freeze policy, submit/cancel/modify orders, or start the experiment.
