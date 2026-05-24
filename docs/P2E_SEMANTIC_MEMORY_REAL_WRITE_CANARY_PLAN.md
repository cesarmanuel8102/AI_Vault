# P2-E Commit 4D-RealWriteCanaryPlan: Semantic Memory Real Write Canary Plan

## Overview

The **SemanticMemoryRealWriteCanaryPlan** provides a safety mechanism for validating semantic memory real write operations before they would ever be executed. It works in conjunction with the **DecisionGateEvidenceAdapter** to ensure all safety checks pass.

## Purpose

The canary plan acts as a pre-flight validation system that:

1. **Validates** evidence bundles using the evidence adapter
2. **Enforces** safety invariants (read-only, no writes)
3. **Emits** decisions without executing any real operations
4. **Documents** blockers and warnings for manual review

## Core Components

### 1. SemanticMemoryCanaryDecision (Enum)

Possible decisions from the canary plan:

- **BLOCK**: Operation blocked - cannot proceed
- **NOOP_ONLY**: Only noop operations allowed (safe mode)
- **CANDIDATE_READY**: Ready for manual review (still requires human approval)
- **MANUAL_REVIEW**: Requires manual review

### 2. SemanticMemoryCanarySeverity (Enum)

Severity levels for findings:

- **INFO**: Informational
- **WARNING**: Warning - attention needed
- **BLOCKER**: Blocker - prevents operation
- **CRITICAL**: Critical - immediate attention required

### 3. SemanticMemoryCanaryFinding (Dataclass)

Individual finding from canary evaluation:

```python
@dataclass
class SemanticMemoryCanaryFinding:
    code: str
    severity: SemanticMemoryCanarySeverity
    message: str
    evidence: Dict[str, Any]
    timestamp_utc: str
```

### 4. SemanticMemoryRealWriteCanaryPlanReport (Dataclass)

Complete report from canary evaluation:

```python
@dataclass
class SemanticMemoryRealWriteCanaryPlanReport:
    canary_id: str
    created_at_utc: str
    decision: SemanticMemoryCanaryDecision
    status: str
    findings: List[SemanticMemoryCanaryFinding]
    blocker_count: int
    warning_count: int
    info_count: int
    critical_count: int
    allow_real_write: bool = False  # ALWAYS False
    dry_run_only: bool = True       # ALWAYS True
    can_execute_real_write: bool = False  # ALWAYS False
    requires_manual_review: bool
    adapter_report_id: Optional[str]
    adapter_status: Optional[str]
    evidence_bundle_valid: bool
    safety_invariants_passed: bool
```

### 5. SemanticMemoryRealWriteCanaryPlan (Class)

Main class for canary plan operations.

## Safety Invariants (Hard Rules)

The canary plan **ALWAYS** enforces these invariants:

1. **allow_real_write = False** - Never allows real write execution
2. **dry_run_only = True** - Only dry run mode
3. **can_execute_real_write = False** - Cannot execute real writes
4. **No subprocess execution** - No subprocess module usage
5. **No FAISS import** - No faiss library usage
6. **No semantic_memory_bridge import** - No bridge imports
7. **No add_memory calls** - No memory addition operations
8. **No write operations** - Read-only only
9. **No git operations** - No git execution

## Usage

### Basic Usage (Noop Mode)

```python
from brain.semantic_memory_real_write_canary_plan import SemanticMemoryRealWriteCanaryPlan

plan = SemanticMemoryRealWriteCanaryPlan()
report = plan.create_noop_canary_report()

print(report.decision)  # NOOP_ONLY
print(report.allow_real_write)  # False
```

### Evaluation with Evidence Bundle

```python
from brain.semantic_memory_real_write_canary_plan import SemanticMemoryRealWriteCanaryPlan

plan = SemanticMemoryRealWriteCanaryPlan()

evidence_bundle = {
    "bundle_id": "bundle_123",
    "producer": "my_system",
    "git_state": {
        "head_commit": "abc123",
        "branch": "main",
        "commits_ahead": 0,
        "dirty_files_count": 0,
        "staged_files_count": 0,
    },
    "risk_summary": {
        "total_extra_files": 0,
        "critical_extra_files": [],
        "dependency_hits": [],
        "high_risk_hits": 0,
    },
    "security_validation": {
        "passed": True,
        "has_subprocess": False,
        "has_faiss": False,
        "has_bridge": False,
        "has_add_memory": False,
    },
    "test_results": {
        "all_tests_passed": True,
        "test_count": 10,
    },
    "smoke_results": {
        "all_smokes_passed": True,
        "smoke_count": 3,
    },
}

report = plan.evaluate_canary_plan(evidence_bundle=bundle)

if report.decision == SemanticMemoryCanaryDecision.CANDIDATE_READY:
    print("Ready for manual review")
else:
    print(f"Decision: {report.decision}")
    print(f"Blockers: {report.blockers}")
```

### Blocking Canary

```python
plan = SemanticMemoryRealWriteCanaryPlan()
report = plan.block_canary(reason="Security violation detected")

assert report.decision == SemanticMemoryCanaryDecision.BLOCK
assert "Security violation detected" in report.blockers
```

### Summarizing Canary Plan

```python
plan = SemanticMemoryRealWriteCanaryPlan()
summary = plan.summarize_canary_plan()

print(summary["canary_version"])  # P2-E-Commit-4D-RealWriteCanaryPlan
print(summary["allow_real_write"])  # False
print(summary["limitations"])
print(summary["invariants"])
```

## Flow

```
1. Initialize CanaryPlan
   |
2. Provide Evidence Bundle (optional)
   |
3. Evaluate with Evidence Adapter
   |
4. Enforce Safety Invariants
   |
5. Calculate Decision
   |
6. Generate Report
   |
7. Review Blockers/Warnings
   |
8. Manual Review Required (always)
```

## What This Module Does NOT Do

⚠️ **Important Limitations:**

1. **Does NOT execute any real writes** - Always dry run only
2. **Does NOT call subprocess** - No external command execution
3. **Does NOT import FAISS** - No vector operations
4. **Does NOT import semantic_memory_bridge** - No bridge usage
5. **Does NOT call add_memory** - No memory addition
6. **Does NOT write files** - Read-only operations only
7. **Does NOT execute git commands** - No git operations
8. **Does NOT bypass manual review** - Always requires human approval for candidates
9. **Does NOT guarantee real write safety** - Only validates preconditions
10. **Does NOT replace code review** - Complements but does not replace human review

## Integration with P2-E Commit 4D-DecisionGateEvidenceAdapter

The canary plan imports from and uses the evidence adapter:

```python
from brain.semantic_memory_decision_gate_evidence_adapter import (
    SemanticMemoryEvidenceAdapterStatus,
    SemanticMemoryDecisionGateEvidenceAdapter,
)
```

The evidence adapter validates evidence bundles, and the canary plan:
1. Uses the adapter's validation results
2. Adds additional safety invariant checks
3. Produces the final canary decision

## Report Structure

### Successful Noop Report

```json
{
  "canary_id": "canary_abc123...",
  "created_at_utc": "2024-01-01T00:00:00+00:00",
  "decision": "NOOP_ONLY",
  "status": "NOOP_DEFAULT",
  "findings": [
    {"code": "CANARY_PLAN_ACTIVE", "severity": "INFO", ...},
    {"code": "NOOP_OPERATION_ONLY", "severity": "INFO", ...},
    {"code": "SAFETY_INVARIANT_PASSED", "severity": "INFO", ...},
    ...
  ],
  "blocker_count": 0,
  "warning_count": 0,
  "info_count": 11,
  "critical_count": 0,
  "allow_real_write": false,
  "dry_run_only": true,
  "can_execute_real_write": false,
  "requires_manual_review": true,
  "adapter_report_id": null,
  "evidence_bundle_valid": false,
  "safety_invariants_passed": true,
  "blockers": [
    "P2-E Commit 4D-RealWriteCanaryPlan: Canary activo",
    "allow_real_write=False por diseño",
    "dry_run_only=True por diseño",
    "can_execute_real_write=False por diseño"
  ]
}
```

### Blocked Report

```json
{
  "canary_id": "blocked_canary_abc123...",
  "decision": "BLOCK",
  "status": "BLOCKED",
  "findings": [
    {"code": "REAL_WRITE_BLOCKED", "severity": "CRITICAL", ...},
    {"code": "DRY_RUN_ENFORCED", "severity": "INFO", ...}
  ],
  "blocker_count": 1,
  "critical_count": 1,
  "blockers": [
    "Test block reason",
    "BLOCKED: Canary plan blocked"
  ]
}
```

## Decision Mapping

The canary plan maps evidence adapter statuses to canary decisions:

| Adapter Status | Evidence Valid | Safety Passed | Canary Decision |
|---------------|----------------|---------------|-----------------|
| ACCEPTED_FOR_GATE | True | True | CANDIDATE_READY |
| PARTIAL_EVIDENCE | - | True | NOOP_ONLY |
| REJECTED_BY_EVIDENCE | False | True | BLOCK |
| BLOCKED | False | True | BLOCK |
| UNKNOWN | - | True | MANUAL_REVIEW |
| No bundle | False | True | NOOP_ONLY |

## Testing

### Unit Tests

```bash
python -m pytest tests/unit/test_semantic_memory_real_write_canary_plan.py -v
```

48 tests covering:
- Decision and severity enums
- Finding creation and conversion
- Report creation with invariants
- Canary plan initialization
- Evaluation with and without bundles
- Safety invariant validation
- Block canary functionality
- Edge cases

### Smoke Test

```bash
python tests/smoke/smoke_semantic_memory_real_write_canary_plan.py
# Output: SMOKE_SEMANTIC_MEMORY_REAL_WRITE_CANARY_PLAN_OK
```

## Migration Control Ledger Entry

See: `docs/MIGRATION_CONTROL_LEDGER.md`

**Commit:** 4D-RealWriteCanaryPlan  
**Module:** `brain/semantic_memory_real_write_canary_plan.py`  
**Tests:** `tests/unit/test_semantic_memory_real_write_canary_plan.py`  
**Smoke:** `tests/smoke/smoke_semantic_memory_real_write_canary_plan.py`  
**Docs:** `docs/P2E_SEMANTIC_MEMORY_REAL_WRITE_CANARY_PLAN.md`

## See Also

- P2-E Commit 4D-DecisionGate: `brain/semantic_memory_real_write_decision_gate.py`
- P2-E Commit 4D-DecisionGateEvidenceAdapter: `brain/semantic_memory_decision_gate_evidence_adapter.py`
- P2-E Commit 4D-ExternalEvidenceContract: `brain/semantic_memory_external_evidence_contract.py`

## Version

**P2-E Commit 4D-RealWriteCanaryPlan**  
Canary Version: `P2-E-Commit-4D-RealWriteCanaryPlan`  
Canary Type: `RealWriteCanaryPlan`
