"""
SemanticMemory Controlled Real Write Preflight Snapshot (P2-E Commit 4D)

This module provides a read-only preflight snapshot before any real write execution.
It confirms if the system is ready for a future real execution by checking
current repository state, git status, and runtime readiness.

IMPORTANT: This module is READ-ONLY. It does NOT:
- Execute any real writes
- Create real backups
- Restore real backups
- Modify memory/semantic
- Touch FAISS
- Import semantic memory bridge
- Call add_memory
- Run any runtime operations
- Open files
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class SemanticMemoryPreflightSnapshotDecision(str, Enum):
    """Preflight snapshot decision states."""
    PREFLIGHT_SNAPSHOT_READY = "PREFLIGHT_SNAPSHOT_READY"
    MANUAL_REVIEW_REQUIRED = "MANUAL_REVIEW_REQUIRED"
    BLOCK_PREFLIGHT_SNAPSHOT = "BLOCK_PREFLIGHT_SNAPSHOT"


class SemanticMemoryPreflightSnapshotSeverity(str, Enum):
    """Severity levels for preflight snapshot findings."""
    INFO = "INFO"
    WARNING = "WARNING"
    BLOCKER = "BLOCKER"


@dataclass(frozen=True)
class SemanticMemoryPreflightSnapshotFinding:
    """A finding from the preflight snapshot evaluation."""
    code: str
    severity: SemanticMemoryPreflightSnapshotSeverity
    message: str
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SemanticMemoryControlledRealWritePreflightSnapshotReport:
    """Report from the preflight snapshot builder."""
    snapshot_id: str
    created_at_utc: str
    decision: SemanticMemoryPreflightSnapshotDecision
    findings: list[SemanticMemoryPreflightSnapshotFinding]
    blocker_count: int
    warning_count: int
    info_count: int
    execution_package_hash: str
    final_pre_execution_gate_hash: str
    candidate_design_hash: str
    authorization_hash: str
    go_no_go_hash: str
    repo_root: str
    branch: str
    head_hash: str
    origin_head_hash: str
    commits_pending: int
    staged_files: list[str]
    dirty_files: list[str]
    runtime_expected_down: bool
    backup_required: bool
    rollback_required: bool
    second_confirmation_required: bool
    memory_semantic_write_allowed_now: bool = False
    execution_allowed_now: bool = False
    can_execute_real_write: bool = False
    allow_real_write: bool = False
    dry_run_only: bool = True
    simulated_only: bool = True
    snapshot_only: bool = True
    requires_second_confirmation: bool = True
    requires_runtime_down: bool = True
    requires_clean_git_gate: bool = True
    requires_real_backup_before_execution: bool = True
    requires_real_rollback_before_execution: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


class SemanticMemoryControlledRealWritePreflightSnapshot:
    """
    Controlled real write preflight snapshot for SemanticMemory.
    
    This snapshot is READ-ONLY and validates system readiness
    for a future, separately gated real write operation.
    """
    
    EXPECTED_EXECUTION_PACKAGE_HASH = "5c41ba4b"
    EXPECTED_FINAL_PRE_EXECUTION_GATE_HASH = "dcf2b72e"
    EXPECTED_CANDIDATE_DESIGN_HASH = "b21c22dd"
    EXPECTED_AUTHORIZATION_HASH = "819be9f2"
    EXPECTED_GO_NO_GO_HASH = "433c5842"
    EXPECTED_HEAD_HASH = "5c41ba4b"
    EXPECTED_ORIGIN_HEAD_HASH = "5c41ba4b"
    EXPECTED_BRANCH = "codex/own-capital-sustainable-return"
    
    def __init__(self, repo_root: str | Path = ".") -> None:
        """Initialize the preflight snapshot with a repository root path."""
        self._repo_root = Path(repo_root)
        self._snapshot_id = self._generate_snapshot_id()
    
    def _generate_snapshot_id(self) -> str:
        """Generate a unique snapshot ID based on timestamp."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        random_component = hashlib.sha256(
            timestamp.encode() + str(datetime.now(timezone.utc).timestamp()).encode()
        ).hexdigest()[:8]
        return f"PREFLIGHT-SNAP-{timestamp}-{random_component}"
    
    def _now_utc(self) -> str:
        """Get current UTC timestamp as ISO string."""
        return datetime.now(timezone.utc).isoformat()
    
    def build_snapshot_read_only(
        self,
        evidence: dict[str, Any],
        operator_intent: dict[str, Any] | None = None
    ) -> SemanticMemoryControlledRealWritePreflightSnapshotReport:
        """
        Build the preflight snapshot in read-only mode.
        
        This method validates evidence and operator intent to determine
        if the system is ready for a future real write operation.
        
        Args:
            evidence: Evidence dictionary from previous gates
            operator_intent: Optional operator intent declaration
            
        Returns:
            A read-only report with decision and findings
        """
        findings: list[SemanticMemoryPreflightSnapshotFinding] = []
        
        # Validate chain evidence
        evidence_findings = self.validate_evidence_read_only(evidence)
        findings.extend(evidence_findings)
        
        # Validate operator intent if provided
        if operator_intent is not None:
            intent_findings = self.validate_operator_intent_read_only(operator_intent)
            findings.extend(intent_findings)
        else:
            findings.append(
                SemanticMemoryPreflightSnapshotFinding(
                    code="MISSING_OPERATOR_INTENT",
                    severity=SemanticMemoryPreflightSnapshotSeverity.WARNING,
                    message="Operator intent not provided; manual review required",
                    evidence={}
                )
            )
        
        # Calculate counts
        blocker_count = sum(
            1 for f in findings 
            if f.severity == SemanticMemoryPreflightSnapshotSeverity.BLOCKER
        )
        warning_count = sum(
            1 for f in findings 
            if f.severity == SemanticMemoryPreflightSnapshotSeverity.WARNING
        )
        info_count = sum(
            1 for f in findings 
            if f.severity == SemanticMemoryPreflightSnapshotSeverity.INFO
        )
        
        # Determine decision
        if blocker_count > 0:
            decision = SemanticMemoryPreflightSnapshotDecision.BLOCK_PREFLIGHT_SNAPSHOT
        elif operator_intent is None:
            decision = SemanticMemoryPreflightSnapshotDecision.MANUAL_REVIEW_REQUIRED
        else:
            decision = SemanticMemoryPreflightSnapshotDecision.PREFLIGHT_SNAPSHOT_READY
        
        # Get repository state
        repo_root = str(self._repo_root)
        branch = evidence.get("branch", self.EXPECTED_BRANCH)
        head_hash = evidence.get("head_hash", self.EXPECTED_HEAD_HASH)
        origin_head_hash = evidence.get("origin_head_hash", self.EXPECTED_ORIGIN_HEAD_HASH)
        commits_pending = evidence.get("commits_pending", 0)
        staged_files = evidence.get("staged_files", [])
        dirty_files = evidence.get("dirty_files", [])
        
        # Build the report with all safety invariants
        report = SemanticMemoryControlledRealWritePreflightSnapshotReport(
            snapshot_id=self._snapshot_id,
            created_at_utc=self._now_utc(),
            decision=decision,
            findings=findings,
            blocker_count=blocker_count,
            warning_count=warning_count,
            info_count=info_count,
            execution_package_hash=evidence.get(
                "execution_package_hash",
                self.EXPECTED_EXECUTION_PACKAGE_HASH
            ),
            final_pre_execution_gate_hash=evidence.get(
                "final_pre_execution_gate_hash",
                self.EXPECTED_FINAL_PRE_EXECUTION_GATE_HASH
            ),
            candidate_design_hash=evidence.get(
                "candidate_design_hash",
                self.EXPECTED_CANDIDATE_DESIGN_HASH
            ),
            authorization_hash=evidence.get(
                "authorization_hash",
                self.EXPECTED_AUTHORIZATION_HASH
            ),
            go_no_go_hash=evidence.get(
                "go_no_go_hash",
                self.EXPECTED_GO_NO_GO_HASH
            ),
            repo_root=repo_root,
            branch=branch,
            head_hash=head_hash,
            origin_head_hash=origin_head_hash,
            commits_pending=commits_pending if commits_pending is not None else 0,
            staged_files=staged_files if staged_files is not None else [],
            dirty_files=dirty_files if dirty_files is not None else [],
            runtime_expected_down=not evidence.get("runtime_active", True),
            backup_required=True,
            rollback_required=True,
            second_confirmation_required=True,
            memory_semantic_write_allowed_now=False,  # NEVER True
            execution_allowed_now=False,  # NEVER True
            can_execute_real_write=False,  # NEVER True
            allow_real_write=False,  # NEVER True
            dry_run_only=True,  # ALWAYS True
            simulated_only=True,  # ALWAYS True
            snapshot_only=True,  # ALWAYS True
            requires_second_confirmation=True,  # ALWAYS True
            requires_runtime_down=True,  # ALWAYS True
            requires_clean_git_gate=True,  # ALWAYS True
            requires_real_backup_before_execution=True,  # ALWAYS True
            requires_real_rollback_before_execution=True,  # ALWAYS True
            metadata={
                "evidence_keys": list(evidence.keys()),
                "operator_intent_provided": operator_intent is not None,
                "snapshot_timestamp": self._now_utc()
            }
        )
        
        return report
    
    def validate_evidence_read_only(
        self,
        evidence: dict[str, Any]
    ) -> list[SemanticMemoryPreflightSnapshotFinding]:
        """
        Validate the evidence from previous gates.
        
        Args:
            evidence: Evidence dictionary
            
        Returns:
            List of findings from validation
        """
        findings: list[SemanticMemoryPreflightSnapshotFinding] = []
        
        # Check execution_package_decision
        execution_package_decision = evidence.get("execution_package_decision")
        if execution_package_decision != "EXECUTION_PACKAGE_READY":
            findings.append(
                SemanticMemoryPreflightSnapshotFinding(
                    code="INVALID_EXECUTION_PACKAGE_DECISION",
                    severity=SemanticMemoryPreflightSnapshotSeverity.BLOCKER,
                    message=f"Expected EXECUTION_PACKAGE_READY, got {execution_package_decision}",
                    evidence={"received": execution_package_decision}
                )
            )
        
        # Check execution_package_hash
        execution_package_hash = evidence.get("execution_package_hash")
        if execution_package_hash != self.EXPECTED_EXECUTION_PACKAGE_HASH:
            findings.append(
                SemanticMemoryPreflightSnapshotFinding(
                    code="INVALID_EXECUTION_PACKAGE_HASH",
                    severity=SemanticMemoryPreflightSnapshotSeverity.BLOCKER,
                    message=f"Expected {self.EXPECTED_EXECUTION_PACKAGE_HASH}, got {execution_package_hash}",
                    evidence={"received": execution_package_hash}
                )
            )
        
        # Check final_pre_execution_gate_hash
        final_pre_execution_gate_hash = evidence.get("final_pre_execution_gate_hash")
        if final_pre_execution_gate_hash != self.EXPECTED_FINAL_PRE_EXECUTION_GATE_HASH:
            findings.append(
                SemanticMemoryPreflightSnapshotFinding(
                    code="INVALID_FINAL_PRE_EXECUTION_GATE_HASH",
                    severity=SemanticMemoryPreflightSnapshotSeverity.BLOCKER,
                    message=f"Expected {self.EXPECTED_FINAL_PRE_EXECUTION_GATE_HASH}, got {final_pre_execution_gate_hash}",
                    evidence={"received": final_pre_execution_gate_hash}
                )
            )
        
        # Check candidate_design_hash
        candidate_design_hash = evidence.get("candidate_design_hash")
        if candidate_design_hash != self.EXPECTED_CANDIDATE_DESIGN_HASH:
            findings.append(
                SemanticMemoryPreflightSnapshotFinding(
                    code="INVALID_CANDIDATE_DESIGN_HASH",
                    severity=SemanticMemoryPreflightSnapshotSeverity.BLOCKER,
                    message=f"Expected {self.EXPECTED_CANDIDATE_DESIGN_HASH}, got {candidate_design_hash}",
                    evidence={"received": candidate_design_hash}
                )
            )
        
        # Check authorization_hash
        authorization_hash = evidence.get("authorization_hash")
        if authorization_hash != self.EXPECTED_AUTHORIZATION_HASH:
            findings.append(
                SemanticMemoryPreflightSnapshotFinding(
                    code="INVALID_AUTHORIZATION_HASH",
                    severity=SemanticMemoryPreflightSnapshotSeverity.BLOCKER,
                    message=f"Expected {self.EXPECTED_AUTHORIZATION_HASH}, got {authorization_hash}",
                    evidence={"received": authorization_hash}
                )
            )
        
        # Check go_no_go_hash
        go_no_go_hash = evidence.get("go_no_go_hash")
        if go_no_go_hash != self.EXPECTED_GO_NO_GO_HASH:
            findings.append(
                SemanticMemoryPreflightSnapshotFinding(
                    code="INVALID_GO_NO_GO_HASH",
                    severity=SemanticMemoryPreflightSnapshotSeverity.BLOCKER,
                    message=f"Expected {self.EXPECTED_GO_NO_GO_HASH}, got {go_no_go_hash}",
                    evidence={"received": go_no_go_hash}
                )
            )
        
        # Check head_hash
        head_hash = evidence.get("head_hash")
        if head_hash != self.EXPECTED_HEAD_HASH:
            findings.append(
                SemanticMemoryPreflightSnapshotFinding(
                    code="INVALID_HEAD_HASH",
                    severity=SemanticMemoryPreflightSnapshotSeverity.BLOCKER,
                    message=f"Expected {self.EXPECTED_HEAD_HASH}, got {head_hash}",
                    evidence={"received": head_hash}
                )
            )
        
        # Check origin_head_hash
        origin_head_hash = evidence.get("origin_head_hash")
        if origin_head_hash != self.EXPECTED_ORIGIN_HEAD_HASH:
            findings.append(
                SemanticMemoryPreflightSnapshotFinding(
                    code="INVALID_ORIGIN_HEAD_HASH",
                    severity=SemanticMemoryPreflightSnapshotSeverity.BLOCKER,
                    message=f"Expected {self.EXPECTED_ORIGIN_HEAD_HASH}, got {origin_head_hash}",
                    evidence={"received": origin_head_hash}
                )
            )
        
        # Check branch
        branch = evidence.get("branch")
        if branch != self.EXPECTED_BRANCH:
            findings.append(
                SemanticMemoryPreflightSnapshotFinding(
                    code="INVALID_BRANCH",
                    severity=SemanticMemoryPreflightSnapshotSeverity.BLOCKER,
                    message=f"Expected {self.EXPECTED_BRANCH}, got {branch}",
                    evidence={"received": branch}
                )
            )
        
        # Check commits_pending
        commits_pending = evidence.get("commits_pending", 0)
        if commits_pending is None:
            commits_pending = 0
        if commits_pending > 0:
            findings.append(
                SemanticMemoryPreflightSnapshotFinding(
                    code="PENDING_COMMITS_DETECTED",
                    severity=SemanticMemoryPreflightSnapshotSeverity.BLOCKER,
                    message=f"Expected 0 pending commits, found {commits_pending}",
                    evidence={"commits_pending": commits_pending}
                )
            )
        
        # Check staged_files
        staged_files = evidence.get("staged_files", [])
        if staged_files is None:
            staged_files = []
        if len(staged_files) > 0:
            findings.append(
                SemanticMemoryPreflightSnapshotFinding(
                    code="STAGED_FILES_DETECTED",
                    severity=SemanticMemoryPreflightSnapshotSeverity.BLOCKER,
                    message=f"Expected empty staged files, found {len(staged_files)} files",
                    evidence={"staged_count": len(staged_files)}
                )
            )
        
        # Check runtime_active
        if evidence.get("runtime_active") is True:
            findings.append(
                SemanticMemoryPreflightSnapshotFinding(
                    code="RUNTIME_ACTIVE",
                    severity=SemanticMemoryPreflightSnapshotSeverity.BLOCKER,
                    message="Runtime is active - must be down before execution",
                    evidence={}
                )
            )
        
        # Check allows_auto_execute
        if evidence.get("allows_auto_execute") is True:
            findings.append(
                SemanticMemoryPreflightSnapshotFinding(
                    code="AUTO_EXECUTE_ENABLED",
                    severity=SemanticMemoryPreflightSnapshotSeverity.BLOCKER,
                    message="Auto-execution is enabled - this is forbidden",
                    evidence={}
                )
            )
        
        # Check execution_allowed_now
        if evidence.get("execution_allowed_now") is True:
            findings.append(
                SemanticMemoryPreflightSnapshotFinding(
                    code="EXECUTION_ALLOWED_NOW_BLOCKED",
                    severity=SemanticMemoryPreflightSnapshotSeverity.BLOCKER,
                    message="Execution now is not allowed - this snapshot is read-only",
                    evidence={}
                )
            )
        
        # Check can_execute_real_write
        if evidence.get("can_execute_real_write") is True:
            findings.append(
                SemanticMemoryPreflightSnapshotFinding(
                    code="CAN_EXECUTE_REAL_WRITE_BLOCKED",
                    severity=SemanticMemoryPreflightSnapshotSeverity.BLOCKER,
                    message="Real write execution flag must be False",
                    evidence={}
                )
            )
        
        # Check allow_real_write
        if evidence.get("allow_real_write") is True:
            findings.append(
                SemanticMemoryPreflightSnapshotFinding(
                    code="ALLOW_REAL_WRITE_BLOCKED",
                    severity=SemanticMemoryPreflightSnapshotSeverity.BLOCKER,
                    message="Real write allow flag must be False",
                    evidence={}
                )
            )
        
        # Check memory_semantic_write_allowed_now
        if evidence.get("memory_semantic_write_allowed_now") is True:
            findings.append(
                SemanticMemoryPreflightSnapshotFinding(
                    code="MEMORY_SEMANTIC_WRITE_ALLOWED_NOW_BLOCKED",
                    severity=SemanticMemoryPreflightSnapshotSeverity.BLOCKER,
                    message="Memory semantic write now is not allowed - this snapshot is read-only",
                    evidence={}
                )
            )
        
        # Add info finding for successful validation
        if len(findings) == 0:
            findings.append(
                SemanticMemoryPreflightSnapshotFinding(
                    code="EVIDENCE_VALIDATION_PASSED",
                    severity=SemanticMemoryPreflightSnapshotSeverity.INFO,
                    message="All evidence validations passed",
                    evidence={
                        "execution_package_hash": execution_package_hash,
                        "final_pre_execution_gate_hash": final_pre_execution_gate_hash,
                        "candidate_design_hash": candidate_design_hash,
                        "authorization_hash": authorization_hash,
                        "go_no_go_hash": go_no_go_hash,
                        "head_hash": head_hash,
                        "origin_head_hash": origin_head_hash,
                        "branch": branch
                    }
                )
            )
        
        return findings
    
    def validate_operator_intent_read_only(
        self,
        operator_intent: dict[str, Any]
    ) -> list[SemanticMemoryPreflightSnapshotFinding]:
        """
        Validate the operator intent declaration.
        
        Args:
            operator_intent: Operator intent dictionary
            
        Returns:
            List of findings from validation
        """
        findings: list[SemanticMemoryPreflightSnapshotFinding] = []
        
        # Check requested_by
        requested_by = operator_intent.get("requested_by")
        if requested_by != "Cesar":
            findings.append(
                SemanticMemoryPreflightSnapshotFinding(
                    code="INVALID_REQUESTER",
                    severity=SemanticMemoryPreflightSnapshotSeverity.BLOCKER,
                    message=f"Expected 'Cesar', got '{requested_by}'",
                    evidence={"requested_by": requested_by}
                )
            )
        
        # Check intent_scope
        intent_scope = operator_intent.get("intent_scope")
        if intent_scope != "preflight_snapshot_only":
            findings.append(
                SemanticMemoryPreflightSnapshotFinding(
                    code="INVALID_INTENT_SCOPE",
                    severity=SemanticMemoryPreflightSnapshotSeverity.BLOCKER,
                    message=f"Expected 'preflight_snapshot_only', got '{intent_scope}'",
                    evidence={"intent_scope": intent_scope}
                )
            )
        
        # Check acknowledges_no_execution_now
        if operator_intent.get("acknowledges_no_execution_now") is not True:
            findings.append(
                SemanticMemoryPreflightSnapshotFinding(
                    code="NO_EXECUTION_ACKNOWLEDGMENT_MISSING",
                    severity=SemanticMemoryPreflightSnapshotSeverity.BLOCKER,
                    message="Must acknowledge that no execution happens now",
                    evidence={}
                )
            )
        
        # Check allows_execution_now
        if operator_intent.get("allows_execution_now") is True:
            findings.append(
                SemanticMemoryPreflightSnapshotFinding(
                    code="EXECUTION_NOW_BLOCKED",
                    severity=SemanticMemoryPreflightSnapshotSeverity.BLOCKER,
                    message="Execution now is not allowed - this snapshot is read-only",
                    evidence={}
                )
            )
        
        # Check allows_memory_semantic_write_now
        if operator_intent.get("allows_memory_semantic_write_now") is True:
            findings.append(
                SemanticMemoryPreflightSnapshotFinding(
                    code="MEMORY_SEMANTIC_WRITE_NOW_BLOCKED",
                    severity=SemanticMemoryPreflightSnapshotSeverity.BLOCKER,
                    message="Memory semantic write now is not allowed - this snapshot is read-only",
                    evidence={}
                )
            )
        
        # Check future requirements
        future_requirements = [
            "requires_future_second_confirmation",
            "requires_future_runtime_down",
            "requires_future_clean_git",
            "requires_future_real_backup",
            "requires_future_real_rollback"
        ]
        
        for req in future_requirements:
            if operator_intent.get(req) is not True:
                findings.append(
                    SemanticMemoryPreflightSnapshotFinding(
                        code=f"MISSING_{req.upper()}",
                        severity=SemanticMemoryPreflightSnapshotSeverity.WARNING,
                        message=f"Future requirement '{req}' not acknowledged",
                        evidence={"requirement": req}
                    )
                )
        
        # Add info finding for successful validation
        blockers = [f for f in findings if f.severity == SemanticMemoryPreflightSnapshotSeverity.BLOCKER]
        if len(blockers) == 0:
            findings.append(
                SemanticMemoryPreflightSnapshotFinding(
                    code="OPERATOR_INTENT_VALIDATION_PASSED",
                    severity=SemanticMemoryPreflightSnapshotSeverity.INFO,
                    message="Operator intent validation passed",
                    evidence={"requested_by": requested_by}
                )
            )
        
        return findings
    
    def summarize_contract(self) -> dict[str, Any]:
        """
        Summarize the contract and safety invariants.
        
        Returns:
            Dictionary with contract summary
        """
        return {
            "snapshot_type": "PREFLIGHT_SNAPSHOT",
            "mode": "READ_ONLY",
            "allow_real_write": False,  # NEVER True
            "can_execute_real_write": False,  # NEVER True
            "execution_allowed_now": False,  # NEVER True
            "memory_semantic_write_allowed_now": False,  # NEVER True
            "dry_run_only": True,  # ALWAYS True
            "simulated_only": True,  # ALWAYS True
            "snapshot_only": True,  # ALWAYS True
            "requires_second_confirmation": True,  # ALWAYS True
            "requires_runtime_down": True,  # ALWAYS True
            "requires_clean_git_gate": True,  # ALWAYS True
            "requires_real_backup_before_execution": True,  # ALWAYS True
            "requires_real_rollback_before_execution": True,  # ALWAYS True
            "expected_hashes": {
                "execution_package": self.EXPECTED_EXECUTION_PACKAGE_HASH,
                "final_pre_execution_gate": self.EXPECTED_FINAL_PRE_EXECUTION_GATE_HASH,
                "candidate_design": self.EXPECTED_CANDIDATE_DESIGN_HASH,
                "authorization": self.EXPECTED_AUTHORIZATION_HASH,
                "go_no_go": self.EXPECTED_GO_NO_GO_HASH,
                "head": self.EXPECTED_HEAD_HASH,
                "origin_head": self.EXPECTED_ORIGIN_HEAD_HASH,
                "branch": self.EXPECTED_BRANCH
            }
        }
    
    def block_snapshot(self, reason: str) -> SemanticMemoryControlledRealWritePreflightSnapshotReport:
        """
        Create a blocked snapshot report with the given reason.
        
        Args:
            reason: Reason for blocking the snapshot
            
        Returns:
            A blocked snapshot report
        """
        finding = SemanticMemoryPreflightSnapshotFinding(
            code="MANUAL_BLOCK",
            severity=SemanticMemoryPreflightSnapshotSeverity.BLOCKER,
            message=reason,
            evidence={"blocked_by": "manual_intervention"}
        )
        
        return SemanticMemoryControlledRealWritePreflightSnapshotReport(
            snapshot_id=self._snapshot_id,
            created_at_utc=self._now_utc(),
            decision=SemanticMemoryPreflightSnapshotDecision.BLOCK_PREFLIGHT_SNAPSHOT,
            findings=[finding],
            blocker_count=1,
            warning_count=0,
            info_count=0,
            execution_package_hash=self.EXPECTED_EXECUTION_PACKAGE_HASH,
            final_pre_execution_gate_hash=self.EXPECTED_FINAL_PRE_EXECUTION_GATE_HASH,
            candidate_design_hash=self.EXPECTED_CANDIDATE_DESIGN_HASH,
            authorization_hash=self.EXPECTED_AUTHORIZATION_HASH,
            go_no_go_hash=self.EXPECTED_GO_NO_GO_HASH,
            repo_root=str(self._repo_root),
            branch=self.EXPECTED_BRANCH,
            head_hash=self.EXPECTED_HEAD_HASH,
            origin_head_hash=self.EXPECTED_ORIGIN_HEAD_HASH,
            commits_pending=0,
            staged_files=[],
            dirty_files=[],
            runtime_expected_down=True,
            backup_required=True,
            rollback_required=True,
            second_confirmation_required=True,
            memory_semantic_write_allowed_now=False,
            execution_allowed_now=False,
            can_execute_real_write=False,
            allow_real_write=False,
            dry_run_only=True,
            simulated_only=True,
            snapshot_only=True,
            requires_second_confirmation=True,
            requires_runtime_down=True,
            requires_clean_git_gate=True,
            requires_real_backup_before_execution=True,
            requires_real_rollback_before_execution=True,
            metadata={"blocked": True, "reason": reason}
        )


# Factory function for convenience
def create_preflight_snapshot(
    repo_root: str | Path = "."
) -> SemanticMemoryControlledRealWritePreflightSnapshot:
    """Create a new preflight snapshot instance."""
    return SemanticMemoryControlledRealWritePreflightSnapshot(repo_root)