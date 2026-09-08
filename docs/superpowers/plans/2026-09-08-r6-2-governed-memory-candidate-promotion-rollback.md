# R6.2 Governed Memory Candidate Promotion and Rollback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add approval-bound, isolated-only promotion and byte-verified rollback behind `MemoryService`, without mutating runtime canonical memory.

**Architecture:** `MemoryService` owns candidate parsing, manual decision binding, and immutable receipts. Snapshot and rollback operate only on a caller-injected temporary root. The legacy promoter delegates to the service and contains no direct JSONL, FAISS, or canonical snapshot effects.

**Tech Stack:** Python 3.11, dataclasses, canonical JSON, SHA-256, pytest, FAISS test doubles.

**Spec:** `docs/superpowers/specs/2026-09-08-r6-2-governed-memory-candidate-promotion-rollback-design.md`

## Global Constraints

- `HUMAN_FINAL_AUTHORITY=true`, `AUTO_MERGE=false`, `CANONICAL_LOCAL_SYNC=false`, `LIVE_TRADING=false`, and `REAL_MONEY=false` are immutable.
- R6.2 is `NO_DEPLOY`: no worker install, no scheduler activation, no real provider call, no repository `memory/` mutation, and no `worker.json` change.
- `MemoryService.promote()` remains a generic-call rejection.
- Only temporary isolated roots may change in tests; a configured semantic root, a `memory/` root, path traversal, and out-of-root paths fail closed.
- Do not reference frozen specimens, Issue/PR numbers, or historical SHA values in production code.

---

## File Structure and Interfaces

| File | Responsibility |
| --- | --- |
| `tmp_agent/brain_v9/core/memory_service.py` | Candidate/decision parsing, receipts, root checks, preparation, isolated execution and rollback APIs. |
| `tmp_agent/brain_v9/core/semantic_memory_faiss.py` | Internal storage primitive only; no public governance decision interface. |
| `tmp_agent/brain_v9/memory/memory_snapshot.py` | Isolated-root, hash-manifest snapshots. |
| `tmp_agent/brain_v9/memory/memory_rollback.py` | Receipt-bound atomic isolated rollback. |
| `tmp_agent/brain_v9/memory/promotion_candidate_promoter.py` | Compatibility facade delegating to `MemoryService`, with no direct storage write. |
| `tests/contract/test_r6_2_governed_memory_candidate_promotion_rollback.py` | R6.2 TDD contract matrix using temporary roots and fake storage. |
| `docs/roadmap/evidence/BRAIN_101_R6_2_GOVERNED_MEMORY_CANDIDATE_PROMOTION_ROLLBACK.json` | Final source-only verification receipt. |

Exact public methods introduced on `MemoryService`:

```python
def validate_governed_candidate(self, candidate: dict[str, object]) -> dict[str, object]: ...
def prepare_governed_promotion(self, candidate: dict[str, object], decision: dict[str, object], staging_root: Path) -> dict[str, object]: ...
def execute_isolated_governed_promotion(self, receipt: dict[str, object], isolated_root: Path) -> dict[str, object]: ...
def rollback_isolated_governed_promotion(self, execution_receipt: dict[str, object], isolated_root: Path) -> dict[str, object]: ...
```

`GovernedPromotionCandidateV1`, `ManualPromotionDecisionV1`, and all receipt schemas have `schema_version == 1`, canonical JSON SHA-256, and unknown-field rejection. `candidate_sha256` is calculated from the candidate canonical JSON after omitting that field itself.

### Task 1: Candidate and Manual Decision Parsing

**Files:**
- Modify: `tmp_agent/brain_v9/core/memory_service.py`
- Create: `tests/contract/test_r6_2_governed_memory_candidate_promotion_rollback.py`

**Produces:** `_parse_governed_candidate_v1`, `_parse_manual_promotion_decision_v1`, and `validate_governed_candidate`.

- [ ] **Step 1: Write failing tests**

```python
def test_exact_candidate_and_manual_decision_bind_by_canonical_hash(tmp_path):
    service = MemoryService(tmp_path / "semantic")
    candidate = governed_candidate(room_id="room_a", text="stable lesson")
    decision = manual_decision(candidate)
    assert service.validate_governed_candidate(candidate)["ok"] is True
    assert service.prepare_governed_promotion(candidate, decision, tmp_path / "staging")["ok"] is True

def test_unknown_fields_or_mismatched_candidate_hash_fail_closed(tmp_path):
    service = MemoryService(tmp_path / "semantic")
    assert service.validate_governed_candidate(governed_candidate(extra={"unknown": 1}))["ok"] is False
    assert service.prepare_governed_promotion(governed_candidate(), manual_decision(governed_candidate(text="other")), tmp_path)["ok"] is False
```

- [ ] **Step 2: Prove RED**

Run: `python -m pytest -q tests/contract/test_r6_2_governed_memory_candidate_promotion_rollback.py -k "exact_candidate or unknown_fields"`

Expected: FAIL because R6.2 parsers and APIs do not exist.

- [ ] **Step 3: Implement minimal parser**

```python
def _canonical_sha256(value: dict[str, object]) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
```

Require candidate schema, ID, source/evidence ID, room ID, retention class, text, and correct `candidate_sha256`, computed over canonical candidate JSON with `candidate_sha256` omitted. Require decision schema, exact `APPROVE_SINGLE_CANDIDATE`, human principal, immutable decision ID, exact candidate ID/hash, and non-expiry. Reject unknown fields, automated actors, unsafe room IDs, live-trading content, and cross-room destinations.

- [ ] **Step 4: Prove GREEN**

Run the Step 2 command. Expected: PASS and no semantic artifact exists under `tmp_path / "semantic"`.

- [ ] **Step 5: Commit**

```bash
git add tmp_agent/brain_v9/core/memory_service.py tests/contract/test_r6_2_governed_memory_candidate_promotion_rollback.py
git commit -m "feat(memory): validate governed promotion candidates"
```

### Task 2: Isolated Snapshot and Receipt-Bound Rollback

**Files:**
- Modify: `tmp_agent/brain_v9/memory/memory_snapshot.py`
- Modify: `tmp_agent/brain_v9/memory/memory_rollback.py`
- Modify: `tests/contract/test_r6_2_governed_memory_candidate_promotion_rollback.py`

**Consumes:** Task 1 receipt SHA.

**Produces:** `create_isolated_memory_snapshot(isolated_root, receipt_sha256)` and `rollback_isolated_snapshot(isolated_root, snapshot, receipt_sha256)`.

- [ ] **Step 1: Write failing tests**

```python
def test_isolated_rollback_restores_each_artifact_byte_for_byte(tmp_path):
    root = isolated_memory_root(tmp_path)
    before = artifact_hashes(root)
    snapshot = create_isolated_memory_snapshot(root, "a" * 64)
    mutate_all_artifacts(root)
    assert rollback_isolated_snapshot(root, snapshot, "a" * 64)["ok"] is True
    assert artifact_hashes(root) == before

def test_canonical_traversal_or_corrupt_manifest_fails_before_copy(tmp_path):
    assert create_isolated_memory_snapshot(Path("memory"), "a" * 64)["ok"] is False
    assert rollback_isolated_snapshot(tmp_path / "safe", {"../escape": {}}, "a" * 64)["ok"] is False
```

- [ ] **Step 2: Prove RED**

Run: `python -m pytest -q tests/contract/test_r6_2_governed_memory_candidate_promotion_rollback.py -k "isolated_rollback or traversal_or_corrupt"`

Expected: FAIL because injected-root snapshot APIs do not exist.

- [ ] **Step 3: Implement the minimal atomic boundary**

`_require_isolated_root()` resolves the supplied path, rejects relative/traversal/canonical paths, and requires an explicit marker directory under the test root. Snapshot manifests use relative names, byte lengths, SHA-256, receipt SHA, and schema version. Rollback copies to a sibling staging directory, verifies all hashes, then replaces only artifacts named in the verified manifest.

- [ ] **Step 4: Prove GREEN**

Run the Step 2 command. Expected: PASS; no repository `memory/` path is created or changed.

- [ ] **Step 5: Commit**

```bash
git add tmp_agent/brain_v9/memory/memory_snapshot.py tmp_agent/brain_v9/memory/memory_rollback.py tests/contract/test_r6_2_governed_memory_candidate_promotion_rollback.py
git commit -m "feat(memory): bind isolated rollback to promotion receipts"
```

### Task 3: Service-Owned Preparation and Isolated Execution

**Files:**
- Modify: `tmp_agent/brain_v9/core/memory_service.py`
- Modify: `tmp_agent/brain_v9/core/semantic_memory_faiss.py`
- Modify: `tests/contract/test_r6_2_governed_memory_candidate_promotion_rollback.py`

**Consumes:** Tasks 1-2 parsers and snapshot APIs.

**Produces:** preparation, execution, and rollback receipts with parent SHA and before/after artifact hashes.

- [ ] **Step 1: Write failing tests**

```python
def test_exact_receipt_executes_once_in_isolated_root_and_can_roll_back(tmp_path, monkeypatch):
    service = MemoryService(tmp_path / "configured-semantic")
    receipt = prepared_receipt(service, tmp_path)
    monkeypatch.setattr(service, "_isolated_storage_write", deterministic_fake_write)
    execution = service.execute_isolated_governed_promotion(receipt, tmp_path / "isolated")
    assert execution["ok"] is True
    assert execution["promotion_receipt_sha256"] == receipt["receipt_sha256"]
    assert service.rollback_isolated_governed_promotion(execution, tmp_path / "isolated")["ok"] is True

def test_execution_rejects_configured_semantic_or_repository_memory_root(tmp_path):
    service = MemoryService(tmp_path / "configured-semantic")
    receipt = prepared_receipt(service, tmp_path)
    assert service.execute_isolated_governed_promotion(receipt, service.semantic_root)["reason"] == "canonical_promotion_not_enabled"
```

- [ ] **Step 2: Prove RED**

Run: `python -m pytest -q tests/contract/test_r6_2_governed_memory_candidate_promotion_rollback.py -k "executes_once or rejects_configured"`

Expected: FAIL because no R6.2 execution API exists.

- [ ] **Step 3: Implement minimal service flow**

`prepare_governed_promotion` validates both payloads and produces a receipt without writing artifacts. `execute_isolated_governed_promotion` verifies receipt/root, snapshots, invokes a private injected writer, verifies exact changed artifacts, and returns execution receipt. On exception it runs verified rollback and returns `isolated_promotion_failed`; it never returns success after rollback. `MemoryService.promote` remains the R6.1 `PermissionError` gate.

- [ ] **Step 4: Prove GREEN**

Run the Step 2 command. Expected: PASS without network, embedding, or real FAISS provider invocation.

- [ ] **Step 5: Commit**

```bash
git add tmp_agent/brain_v9/core/memory_service.py tmp_agent/brain_v9/core/semantic_memory_faiss.py tests/contract/test_r6_2_governed_memory_candidate_promotion_rollback.py
git commit -m "feat(memory): add isolated governed promotion execution"
```

### Task 4: Legacy Promoter Delegation and No-Bypass Contract

**Files:**
- Modify: `tmp_agent/brain_v9/memory/promotion_candidate_promoter.py`
- Modify: `tests/contract/test_r6_2_governed_memory_candidate_promotion_rollback.py`

**Consumes:** Task 3 `MemoryService` APIs.

**Produces:** compatibility rejection or explicit preparation response with `write_performed=False`.

- [ ] **Step 1: Write failing tests**

```python
def test_legacy_promoter_delegates_without_direct_jsonl_or_faiss_mutation(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(promoter, "MemoryService", recording_service(calls))
    result = promoter.promote_candidate("candidate-1", "all", "promotion", "x", "human", "x")
    assert calls == ["prepare_governed_promotion"]
    assert result["write_performed"] is False

def test_legacy_promoter_has_no_direct_storage_primitives():
    source = inspect.getsource(promoter)
    assert "promote_record(" not in source
    assert ".open(\"a\"" not in source
    assert "rollback_from_snapshot(" not in source
```

- [ ] **Step 2: Prove RED**

Run: `python -m pytest -q tests/contract/test_r6_2_governed_memory_candidate_promotion_rollback.py -k "legacy_promoter"`

Expected: FAIL because the legacy module still directly owns storage effects.

- [ ] **Step 3: Implement the facade**

Replace direct imports, FAISS calls, append operations, snapshots, and rollback calls with a compatibility wrapper that accepts only typed candidate/decision input and calls `MemoryService.prepare_governed_promotion`. Old argument forms return `governed_receipt_required`, `promotion_performed=False`, `write_performed=False`.

- [ ] **Step 4: Prove GREEN**

Run the Step 2 command. Expected: PASS and source contains no direct storage primitive.

- [ ] **Step 5: Commit**

```bash
git add tmp_agent/brain_v9/memory/promotion_candidate_promoter.py tests/contract/test_r6_2_governed_memory_candidate_promotion_rollback.py
git commit -m "refactor(memory): route legacy promotion through governance"
```

### Task 5: Full Corruption Matrix, Evidence, and Regression Gate

**Files:**
- Modify: `tests/contract/test_r6_2_governed_memory_candidate_promotion_rollback.py`
- Create: `docs/roadmap/evidence/BRAIN_101_R6_2_GOVERNED_MEMORY_CANDIDATE_PROMOTION_ROLLBACK.json`

**Consumes:** all prior tasks.

**Produces:** final contract evidence, source-only.

- [ ] **Step 1: Write failing crash and invariant tests**

```python
def test_mid_promotion_failure_returns_verified_rollback_not_success(tmp_path, monkeypatch):
    service, receipt, root = prepared_isolated_execution(tmp_path)
    monkeypatch.setattr(service, "_isolated_storage_write", raises_after_first_artifact)
    result = service.execute_isolated_governed_promotion(receipt, root)
    assert result["ok"] is False
    assert result["rollback"]["ok"] is True

def test_runtime_write_and_control_plane_invariants_remain_closed():
    assert MemoryService.promote.__doc__.startswith("Reserve")
    assert no_repository_memory_paths_changed()
    assert no_scheduler_or_trading_paths_changed()
```

- [ ] **Step 2: Prove RED**

Run: `python -m pytest -q tests/contract/test_r6_2_governed_memory_candidate_promotion_rollback.py`

Expected: FAIL until all corruption outcomes and invariant assertions are implemented.

- [ ] **Step 3: Complete tests and evidence**

Write evidence only from fresh command results: source commit, test commands/results, `deployment_mode: "NO_DEPLOY"`, and the five hard-limit values. Do not put candidate bodies, runtime paths, secrets, or memory data in evidence.

- [ ] **Step 4: Run final verification**

```bash
python -m py_compile tmp_agent/brain_v9/core/memory_service.py tmp_agent/brain_v9/core/semantic_memory_faiss.py tmp_agent/brain_v9/memory/memory_snapshot.py tmp_agent/brain_v9/memory/memory_rollback.py tmp_agent/brain_v9/memory/promotion_candidate_promoter.py
python -m pytest -q tests/contract/test_r6_2_governed_memory_candidate_promotion_rollback.py
python -m pytest -q tests/contract/test_r6_1_memory_service_ownership_integrity_baseline.py
git diff --check
git diff --name-only e491be0bc3195fe79285fce5245bfafc4eee02c3...HEAD
```

Expected: all tests pass, no untracked artifacts, and the diff is only the R6.2 JIT allowlist plus approved specification and plan documents.

- [ ] **Step 5: Commit**

```bash
git add tests/contract/test_r6_2_governed_memory_candidate_promotion_rollback.py docs/roadmap/evidence/BRAIN_101_R6_2_GOVERNED_MEMORY_CANDIDATE_PROMOTION_ROLLBACK.json
git commit -m "test(memory): verify governed promotion rollback contracts"
```

## Final Review Gate

Request independent review of the complete branch and run required CI before a Draft PR. Do not install, deploy, enable a task, create runtime candidates, or mutate canonical memory. Merge only through the normal governed merge path after exact-head CI/reviewer success.
