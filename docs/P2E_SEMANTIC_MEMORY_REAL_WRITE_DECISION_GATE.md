# P2-E Semantic Memory Real Write Decision Gate (Commit 4D-DecisionGate)

## Overview

This document describes the **Semantic Memory Real Write Decision Gate** (P2-E Commit 4D-DecisionGate), which creates a governed decision gate before any real write to memory/semantic.

## Purpose

The 4D-DecisionGate module exists to:

1. **Evaluate Evidence**: Combine evidence from all previous 4A-4D commits
2. **Emit Decisions**: Produce explicit decisions about whether real write is permitted
3. **Require Manual Review**: Ensure no automatic real write without human approval
4. **Block by Default**: Always block real write unless all conditions are met

## Why 4D-DecisionGate Exists After 4D-DependencyMapping

Commit 4D-DependencyMapping mapped dependencies to extra files. This commit evaluates whether it's safe to proceed:
- Are all required artifacts present?
- Is the git state clean?
- Are there high-risk findings?
- Is manual review required?

This decision gate is the final checkpoint before any 4D real write consideration.

## Relationship with Previous Commits

### 4A: MemorySemanticBackupContract
- **Provides**: Backup infrastructure
- **Required by**: Decision gate checks for existence

### 4B: SemanticMemoryRealAdapterSkeleton
- **Provides**: Write infrastructure (blocked)
- **Required by**: Decision gate checks for existence

### 4C: SemanticMemoryRollbackSimulation
- **Provides**: Rollback capability
- **Required by**: Decision gate checks for existence

### 4D-0: RealWriteReadinessGate
- **Provides**: Readiness evaluation
- **Required by**: Decision gate checks for existence

### 4D-Preflight: RealStateAudit
- **Provides**: File listing
- **Required by**: Decision gate checks for existence

### 4D-CleanClassification: ExtraFileClassifier
- **Provides**: File classification
- **Required by**: Decision gate checks for existence

### 4D-DependencyMapping: ExtraFileDependencyMapper
- **Provides**: Dependency mapping
- **Required by**: Decision gate checks for existence

### 4D-DecisionGate: RealWriteDecisionGate
- **Provides**: Governed decision making
- **Output**: Decision report with explicit allow/block

## Design Philosophy

### Read-Only Evaluation
This gate uses ONLY read-only operations:
- Checks if files exist with `Path.exists()`
- Reads file metadata with `Path.stat()`
- NO code execution
- NO module imports
- NO runtime activation

### Safety-First
The gate is designed to be absolutely safe:
- Cannot modify any files
- Cannot execute any code
- Cannot import sensitive modules (faiss, semantic_memory_bridge)
- Cannot start runtime
- `allow_real_write=False` always
- `dry_run_only=True` always
- `can_execute_real_write=False` always

## Decisions

The gate can emit four types of decisions:

### BLOCK_REAL_WRITE
- **When**: Missing required artifacts, staged files, pending commits, high-risk findings
- **Action**: Block any real write operation
- **Next step**: Fix issues and re-evaluate

### CANARY_NOOP_ONLY
- **When**: All artifacts present but warnings exist
- **Action**: Allow only canary/noop tests
- **Next step**: Investigate warnings before proceeding

### MANUAL_REVIEW_REQUIRED
- **When**: High-risk findings that need human assessment
- **Action**: Require human operator review
- **Next step**: Manual review and decision

### ALLOW_MANUAL_REAL_WRITE_CANDIDATE
- **When**: All checks pass, no blockers, no warnings
- **Action**: Candidate for manual real write approval
- **Important**: This does NOT mean automatic write is permitted!
- **Next step**: Human operator must still approve

## Required Artifacts

The gate checks for these required files:

1. `brain/memory_semantic_backup.py`
2. `brain/semantic_memory_adapter_real.py`
3. `brain/semantic_memory_rollback_simulation.py`
4. `brain/semantic_memory_real_write_readiness_gate.py`
5. `brain/semantic_memory_real_state_audit.py`
6. `brain/semantic_memory_extra_file_classifier.py`
7. `brain/semantic_memory_extra_file_dependency_mapper.py`

## Decision Rules

- If any required artifact is missing → **BLOCK_REAL_WRITE**
- If any blocker finding exists → **BLOCK_REAL_WRITE**
- If high-risk extra files exist → **MANUAL_REVIEW_REQUIRED**
- If high-risk dependency hits exist → **MANUAL_REVIEW_REQUIRED**
- If write-like dependency hits exist → **CANARY_NOOP_ONLY**
- If runtime-like dependency hits exist → **CANARY_NOOP_ONLY**
- If no blockers but warnings exist → **CANARY_NOOP_ONLY**
- If all clean → **ALLOW_MANUAL_REAL_WRITE_CANDIDATE**

**Important**: `can_execute_real_write` is ALWAYS `False` regardless of decision.

## Usage

### Basic Usage
```python
from brain.semantic_memory_real_write_decision_gate import (
    SemanticMemoryRealWriteDecisionGate,
    SemanticMemoryDecision,
)

# Create gate
gate = SemanticMemoryRealWriteDecisionGate(repo_root=".")

# Evaluate (read-only)
report = gate.evaluate_read_only()

# Check decision
if report.decision == SemanticDecision.ALLOW_MANUAL_REAL_WRITE_CANDIDATE:
    print("Candidate for manual review")
    print(f"Can execute: {report.can_execute_real_write}")  # Always False
else:
    print(f"Blocked: {report.decision.value}")
    print(f"Blockers: {report.blocker_count}")
    print(f"Warnings: {report.warning_count}")
```

### Block Explicitly
```python
# Explicitly block real write
blocked = gate.block_real_write("Safety precaution")
assert blocked.decision == SemanticMemoryDecision.BLOCK_REAL_WRITE
assert blocked.allow_real_write is False
```

## Report Structure

The gate returns a `SemanticMemoryRealWriteDecisionReport`:

```python
report.decision_id              # Unique identifier
report.created_at_utc          # ISO timestamp
report.repo_root               # Repository root path
report.decision                # Decision enum value
report.findings                # List of SemanticMemoryDecisionFinding
report.blocker_count          # Number of blocker findings
report.warning_count          # Number of warning findings
report.info_count             # Number of info findings
report.allow_real_write       # Always False
report.dry_run_only           # Always True
report.can_execute_real_write # Always False
report.requires_manual_review # True unless ALLOW_MANUAL_REAL_WRITE_CANDIDATE
report.required_artifacts     # Dict of artifact -> exists
report.git_state             # Git state info (read-only)
report.risk_summary          # Risk summary (read-only)
report.warnings              # Warnings list
report.blockers              # Blockers list
report.metadata              # Additional metadata
```

## Finding Structure

Each finding contains:

```python
finding.code        # SemanticMemoryDecisionReasonCode
finding.severity    # INFO, WARNING, or BLOCKER
finding.message     # Human-readable message
finding.evidence    # Dict with additional evidence
```

## Security Contract

The gate provides a security contract:

```python
contract = gate.summarize_contract()
# {
#   "contract_version": "P2-E-Commit-4D-DecisionGate",
#   "contract_type": "RealWriteDecisionGate",
#   "allow_real_write": False,
#   "dry_run_only": True,
#   "can_execute_real_write": False,
#   "decisions": ["BLOCK_REAL_WRITE", "CANARY_NOOP_ONLY",
#                 "MANUAL_REVIEW_REQUIRED", "ALLOW_MANUAL_REAL_WRITE_CANDIDATE"],
#   "limitations": [
#     "NO code execution",
#     "NO module imports (faiss, semantic_memory_bridge)",
#     "NO write operations",
#     "NO subprocess",
#     "NO FAISS import",
#     "Static analysis only",
#     "Manual review required for real write",
#   ],
# }
```

## Testing

### Unit Tests
```bash
pytest tests/unit/test_semantic_memory_real_write_decision_gate.py -v
```

### Smoke Tests
```bash
python tests/smoke/smoke_semantic_memory_real_write_decision_gate.py
```

## Important Safety Notes

### This Commit Does NOT:
- Write to memory/semantic
- Delete files
- Move files
- Copy files
- Touch FAISS
- Execute runtime
- Call real add_memory
- Import semantic_memory_bridge
- Enable real write automatically

### This Commit ONLY:
- Evaluates evidence read-only
- Emits decisions
- Requires manual review
- Blocks by default

### ALLOW_MANUAL_REAL_WRITE_CANDIDATE Means:
- All automatic checks passed
- Still requires human approval
- `can_execute_real_write` remains False
- Real write only after human operator approves

## Integration with Next Steps

This decision gate informs:

1. **Human Operators**: Whether conditions are met for manual review
2. **4D Real Write**: Whether to proceed with governance approval
3. **Governance**: When manual review is required

## Commit Message

```
Add SemanticMemory real write decision gate

- Governed decision gate before any 4D real write
- Evaluates evidence from 4A, 4B, 4C, 4D-0, 4D-Preflight, 4D-CleanClassification, 4D-DependencyMapping
- Emits explicit decisions: BLOCK_REAL_WRITE, CANARY_NOOP_ONLY, MANUAL_REVIEW_REQUIRED, ALLOW_MANUAL_REAL_WRITE_CANDIDATE
- ALLOW_MANUAL_REAL_WRITE_CANDIDATE only means candidate for review, NOT automatic execution
- allow_real_write=False always, dry_run_only=True always, can_execute_real_write=False always
- NO code execution, NO module imports, NO write operations
- Requires manual review by human operator
```

## Compliance

- [x] Read-only evaluation
- [x] No code execution
- [x] No sensitive module imports
- [x] No write operations
- [x] Security contract enforced
- [x] Blockers prevent automatic write
- [x] Manual review required
- [x] All tests passing
- [x] AST security validation OK

---

**P2-E Commit 4D-DecisionGate** | Status: COMPLETE | Safe to Commit: YES | Requires Manual Review: YES


## Fail-Closed Safety

The decision gate is designed with **fail-closed** safety principles:

### Unknown != Safe

- **Unknown git state** is NOT considered safe. The gate cannot verify git state without subprocess, so it assumes the worst and emits a warning.
- **Unknown risk summary** is NOT considered safe. The gate cannot verify risk without prior reports, so it assumes the worst and emits a warning.
- **No evidence** does NOT equal "allow candidate".

### Decision Rules (Fail-Closed)

1. **BLOCK_REAL_WRITE**: If any blocker finding exists
2. **MANUAL_REVIEW_REQUIRED**: If high-risk warning exists (HIGH_RISK_EXTRA_FILES, HIGH_RISK_DEPENDENCY_HITS, MANUAL_REVIEW_REQUIRED)
3. **CANARY_NOOP_ONLY**: If any warning exists (but no high-risk)
4. **ALLOW_MANUAL_REAL_WRITE_CANDIDATE**: Only if no blockers AND no warnings AND git/risk verified

### ALLOW_MANUAL_REAL_WRITE_CANDIDATE Requirements

To reach ALLOW_MANUAL_REAL_WRITE_CANDIDATE, the gate must verify:
- All required artifacts exist
- Git state is verified (no staged files, no pending commits, clean working tree)
- Risk summary is verified (no high-risk findings)
- No warnings of any kind

**Important**: Even ALLOW_MANUAL_REAL_WRITE_CANDIDATE does NOT enable automatic real write. `can_execute_real_write` remains `False` always.

### Git State Verification

The gate uses `check_git_state_read_only()` which:
- Does NOT use subprocess (forbidden)
- Returns `verified=False` by default
- Includes warning: "Git state unknown because subprocess is forbidden (fail-closed)"
- This triggers a WARNING finding, preventing ALLOW_MANUAL_REAL_WRITE_CANDIDATE

### Risk Summary Verification

The gate uses `check_risk_summary_read_only()` which:
- Does NOT execute prior reports (read-only)
- Returns `verified=False` by default
- Returns `None` for risk counts (not 0)
- Includes warning: "Risk summary unknown because prior reports are not loaded (fail-closed)"
- This triggers a WARNING finding, preventing ALLOW_MANUAL_REAL_WRITE_CANDIDATE

### Result in Real Repository

When running in the actual repository (C:/AI_VAULT):
- Decision will be **CANARY_NOOP_ONLY** or **MANUAL_REVIEW_REQUIRED**
- Will NOT be **ALLOW_MANUAL_REAL_WRITE_CANDIDATE**
- Because git/risk cannot be verified without subprocess/prior reports
- This is the **correct, safe behavior**

### Manual Review Required

For the gate to allow manual real write candidate:
1. Human operator must provide git state evidence externally
2. Human operator must provide risk summary evidence externally
3. All blockers must be resolved
4. All warnings must be resolved

Only then can the decision reach ALLOW_MANUAL_REAL_WRITE_CANDIDATE, and even then, human approval is still required.

## Security Guarantees

- `allow_real_write=False` always
- `dry_run_only=True` always  
- `can_execute_real_write=False` always
- Unknown states default to WARNING (not safe)
- No subprocess, no open(), no write operations
- Fail-closed by design
