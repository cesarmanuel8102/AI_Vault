"""
SemanticMemory Final Pre-Execution Gate (P2-E Commit 4D-FinalPreExecutionGate)

This module provides a read-only final gate before any real write execution.
It evaluates evidence chain and final intent to determine if the system is
ready for a future, separately gated real write operation.

IMPORTANT: This module is READ-ONLY. It does NOT:
- Execute any real writes
- Create backups
- Modify memory/semantic
- Touch FAISS
- Import semantic memory bridge
- Call add_memory
- Run any runtime operations
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class SemanticMemoryFinalPreExecutionDecision(str, Enum):
    """Final pre-execution decision states."""
    PRE_EXECUTION_GATE_READY = "PRE_EXECUTION_GATE_READY"
    MANUAL_REVIEW_REQUIRED = "MANUAL_REVIEW_REQUIRED"
    BLOCK_PRE_EXECUTION = "BLOCK_PRE_EXECUTION"


class SemanticMemoryFinalPreExecutionSeverity(str, Enum):
    """Severity levels for pre-execution findings."""
    INFO = "INFO"
    WARNING = "WARNING"
    BLOCKER = "BLOCKER"


@dataclass(frozen=True)
class SemanticMemoryFinalPreExecutionFinding:
    """A finding from the pre-execution gate evaluation."""
    code: str
    severity: SemanticMemoryFinalPreExecutionSeverity
    message: str
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SemanticMemoryFinalPreExecutionGateReport:
    """Report from the final pre-execution gate evaluation."""
    gate_id: str
    created_at_utc: str
    decision: SemanticMemoryFinalPreExecutionDecision
    findings: list[SemanticMemoryFinalPreExecutionFinding]
    blocker_count: int
    warning_count: int
    info_count: int
    candidate_design_hash: str
    authorization_hash: str
    go_no_go_hash: str
    execution_allowed_now: bool
    exact_future_operation: dict[str, Any]
    required_real_backup_plan: dict[str, Any]
    required_real_rollback_plan: dict[str, Any]
    required_runtime_state: dict[str, Any]
    required_git_state: dict[str, Any]
    second_confirmation_contract: dict[str, Any]
    final_blockers: list[str]
    can_execute_real_write: bool = False
    allow_real_write: bool = False
    dry_run_only: bool = True
    simulated_only: bool = True
    requires_second_confirmation: bool = True
    requires_runtime_down: bool = True
    requires_clean_git_gate: bool = True
    requires_real_backup_before_execution: bool = True
    requires_real_rollback_before_execution: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


class SemanticMemoryFinalPreExecutionGate:
    """
    Final pre-execution gate for SemanticMemory real write operations.
    
    This gate is READ-ONLY and evaluates whether the system is ready
    for a future real write execution, without performing any writes.
    """
    
    EXPECTED_CANDIDATE_DESIGN_HASH = "b21c22dd"
    EXPECTED_AUTHORIZATION_HASH = "819be9f2"
    EXPECTED_GO_NO_GO_HASH = "433c5842"
    
    def __init__(self, repo_root: str | Path = ".") -> None:
        """Initialize the gate with a repository root path."""
        self._repo_root = Path(repo_root)
        self._gate_id = self._generate_gate_id()
    
    def _generate_gate_id(self) -> str:
        """Generate a unique gate ID based on timestamp with microsecond precision."""
        now = datetime.now(timezone.utc)
        timestamp = now.strftime("%Y%m%d%H%M%S")
        microsecond = now.microsecond
        # Add microsecond and use object id for additional uniqueness
        random_component = hashlib.sha256(
            timestamp.encode() + str(microsecond).encode() + str(id(self)).encode()
        ).hexdigest()[:8]
        return f"GATE-{timestamp}-{microsecond:06d}-{random_component}"
    
    def _now_utc(self) -> str:
        """Get current UTC timestamp as ISO string."""
        return datetime.now(timezone.utc).isoformat()
    
    def evaluate_pre_execution_gate_read_only(
        self,
        evidence: dict[str, Any],
        final_intent: dict[str, Any] | None = None
    ) -> SemanticMemoryFinalPreExecutionGateReport:
        """
        Evaluate the pre-execution gate in read-only mode.
        
        This method validates evidence chain and final intent to determine
        if the system is ready for a future real write operation.
        
        Args:
            evidence: Evidence dictionary from previous gates
            final_intent: Optional final intent declaration
            
        Returns:
            A read-only report with decision and findings
        """
        findings: list[SemanticMemoryFinalPreExecutionFinding] = []
        
        # Validate chain evidence
        chain_findings = self.validate_chain_evidence_read_only(evidence)
        findings.extend(chain_findings)
        
        # Validate final intent if provided
        if final_intent is not None:
            intent_findings = self.validate_final_intent_read_only(final_intent)
            findings.extend(intent_findings)
        else:
            findings.append(
                SemanticMemoryFinalPreExecutionFinding(
                    code="MISSING_FINAL_INTENT",
                    severity=SemanticMemoryFinalPreExecutionSeverity.WARNING,
                    message="Final intent not provided; manual review required",
                    evidence={}
                )
            )
        
        # Calculate counts
        blocker_count = sum(
            1 for f in findings 
            if f.severity == SemanticMemoryFinalPreExecutionSeverity.BLOCKER
        )
        warning_count = sum(
            1 for f in findings 
            if f.severity == SemanticMemoryFinalPreExecutionSeverity.WARNING
        )
        info_count = sum(
            1 for f in findings 
            if f.severity == SemanticMemoryFinalPreExecutionSeverity.INFO
        )
        
        # Determine decision
        if blocker_count > 0:
            decision = SemanticMemoryFinalPreExecutionDecision.BLOCK_PRE_EXECUTION
        elif final_intent is None:
            decision = SemanticMemoryFinalPreExecutionDecision.MANUAL_REVIEW_REQUIRED
        else:
            decision = SemanticMemoryFinalPreExecutionDecision.PRE_EXECUTION_GATE_READY
        
        # Build final blockers list
        final_blockers = [
            f.message for f in findings 
            if f.severity == SemanticMemoryFinalPreExecutionSeverity.BLOCKER
        ]
        
        # Build the report with all safety invariants
        report = SemanticMemoryFinalPreExecutionGateReport(
            gate_id=self._gate_id,
            created_at_utc=self._now_utc(),
            decision=decision,
            findings=findings,
            blocker_count=blocker_count,
            warning_count=warning_count,
            info_count=info_count,
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
            execution_allowed_now=False,  # NEVER True
            exact_future_operation=self._build_future_operation_plan(),
            required_real_backup_plan=self._build_backup_plan(),
            required_real_rollback_plan=self._build_rollback_plan(),
            required_runtime_state=self._build_required_runtime_state(),
            required_git_state=self._build_required_git_state(),
            second_confirmation_contract=self._build_second_confirmation_contract(),
            final_blockers=final_blockers,
            can_execute_real_write=False,  # NEVER True in this gate
            allow_real_write=False,  # NEVER True in this gate
            dry_run_only=True,  # ALWAYS True
            simulated_only=True,  # ALWAYS True
            requires_second_confirmation=True,  # ALWAYS True
            requires_runtime_down=True,  # ALWAYS True
            requires_clean_git_gate=True,  # ALWAYS True
            requires_real_backup_before_execution=True,  # ALWAYS True
            requires_real_rollback_before_execution=True,  # ALWAYS True
            metadata={
                "evidence_keys": list(evidence.keys()),
                "final_intent_provided": final_intent is not None,
                "validation_timestamp": self._now_utc()
            }
        )
        
        return report
    
    def validate_chain_evidence_read_only(
        self, 
        evidence: dict[str, Any]
    ) -> list[SemanticMemoryFinalPreExecutionFinding]:
        """
        Validate the evidence chain from previous gates.
        
        Args:
            evidence: Evidence dictionary
            
        Returns:
            List of findings from validation
        """
        findings: list[SemanticMemoryFinalPreExecutionFinding] = []
        
        # Check candidate_design_decision
        candidate_design_decision = evidence.get("candidate_design_decision")
        if candidate_design_decision != "CANDIDATE_DESIGN_READY":
            findings.append(
                SemanticMemoryFinalPreExecutionFinding(
                    code="INVALID_CANDIDATE_DESIGN_DECISION",
                    severity=SemanticMemoryFinalPreExecutionSeverity.BLOCKER,
                    message=f"Expected CANDIDATE_DESIGN_READY, got {candidate_design_decision}",
                    evidence={"received": candidate_design_decision}
                )
            )
        
        # Check candidate_design_hash
        candidate_design_hash = evidence.get("candidate_design_hash")
        if candidate_design_hash != self.EXPECTED_CANDIDATE_DESIGN_HASH:
            findings.append(
                SemanticMemoryFinalPreExecutionFinding(
                    code="INVALID_CANDIDATE_DESIGN_HASH",
                    severity=SemanticMemoryFinalPreExecutionSeverity.BLOCKER,
                    message=f"Expected {self.EXPECTED_CANDIDATE_DESIGN_HASH}, got {candidate_design_hash}",
                    evidence={"received": candidate_design_hash}
                )
            )
        
        # Check authorization_hash
        authorization_hash = evidence.get("authorization_hash")
        if authorization_hash != self.EXPECTED_AUTHORIZATION_HASH:
            findings.append(
                SemanticMemoryFinalPreExecutionFinding(
                    code="INVALID_AUTHORIZATION_HASH",
                    severity=SemanticMemoryFinalPreExecutionSeverity.BLOCKER,
                    message=f"Expected {self.EXPECTED_AUTHORIZATION_HASH}, got {authorization_hash}",
                    evidence={"received": authorization_hash}
                )
            )
        
        # Check go_no_go_hash
        go_no_go_hash = evidence.get("go_no_go_hash")
        if go_no_go_hash != self.EXPECTED_GO_NO_GO_HASH:
            findings.append(
                SemanticMemoryFinalPreExecutionFinding(
                    code="INVALID_GO_NO_GO_HASH",
                    severity=SemanticMemoryFinalPreExecutionSeverity.BLOCKER,
                    message=f"Expected {self.EXPECTED_GO_NO_GO_HASH}, got {go_no_go_hash}",
                    evidence={"received": go_no_go_hash}
                )
            )
        
        # Check commits_pending_post_push
        commits_pending = evidence.get("commits_pending_post_push", 0)
        if commits_pending is None:
            commits_pending = 0
        if commits_pending > 0:
            findings.append(
                SemanticMemoryFinalPreExecutionFinding(
                    code="PENDING_COMMITS_DETECTED",
                    severity=SemanticMemoryFinalPreExecutionSeverity.BLOCKER,
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
                SemanticMemoryFinalPreExecutionFinding(
                    code="STAGED_FILES_DETECTED",
                    severity=SemanticMemoryFinalPreExecutionSeverity.BLOCKER,
                    message=f"Expected empty staged files, found {len(staged_files)} files",
                    evidence={"staged_count": len(staged_files)}
                )
            )
        
        # Check memory_semantic_in_scope
        if evidence.get("memory_semantic_in_scope") is True:
            findings.append(
                SemanticMemoryFinalPreExecutionFinding(
                    code="MEMORY_SEMANTIC_IN_SCOPE",
                    severity=SemanticMemoryFinalPreExecutionSeverity.BLOCKER,
                    message="memory/semantic is in scope - this is forbidden for pre-execution",
                    evidence={}
                )
            )
        
        # Check runtime_active
        if evidence.get("runtime_active") is True:
            findings.append(
                SemanticMemoryFinalPreExecutionFinding(
                    code="RUNTIME_ACTIVE",
                    severity=SemanticMemoryFinalPreExecutionSeverity.BLOCKER,
                    message="Runtime is active - must be down before execution",
                    evidence={}
                )
            )
        
        # Check faiss_write_enabled
        if evidence.get("faiss_write_enabled") is True:
            findings.append(
                SemanticMemoryFinalPreExecutionFinding(
                    code="FAISS_WRITE_ENABLED",
                    severity=SemanticMemoryFinalPreExecutionSeverity.BLOCKER,
                    message="FAISS write is enabled - this is forbidden for pre-execution",
                    evidence={}
                )
            )
        
        # Check add_memory_enabled
        if evidence.get("add_memory_enabled") is True:
            findings.append(
                SemanticMemoryFinalPreExecutionFinding(
                    code="ADD_MEMORY_ENABLED",
                    severity=SemanticMemoryFinalPreExecutionSeverity.BLOCKER,
                    message="add_memory is enabled - this is forbidden for pre-execution",
                    evidence={}
                )
            )
        
        # Check allows_auto_execute
        if evidence.get("allows_auto_execute") is True:
            findings.append(
                SemanticMemoryFinalPreExecutionFinding(
                    code="AUTO_EXECUTE_ENABLED",
                    severity=SemanticMemoryFinalPreExecutionSeverity.BLOCKER,
                    message="Auto-execution is enabled - this is forbidden for pre-execution",
                    evidence={}
                )
            )
        
        # Add info finding for successful validation
        if len(findings) == 0:
            findings.append(
                SemanticMemoryFinalPreExecutionFinding(
                    code="EVIDENCE_VALIDATION_PASSED",
                    severity=SemanticMemoryFinalPreExecutionSeverity.INFO,
                    message="All evidence chain validations passed",
                    evidence={
                        "candidate_design_hash": candidate_design_hash,
                        "authorization_hash": authorization_hash,
                        "go_no_go_hash": go_no_go_hash
                    }
                )
            )
        
        return findings
    
    def validate_final_intent_read_only(
        self, 
        final_intent: dict[str, Any]
    ) -> list[SemanticMemoryFinalPreExecutionFinding]:
        """
        Validate the final intent declaration.
        
        Args:
            final_intent: Final intent dictionary
            
        Returns:
            List of findings from validation
        """
        findings: list[SemanticMemoryFinalPreExecutionFinding] = []
        
        # Check requested_by
        requested_by = final_intent.get("requested_by")
        if requested_by != "Cesar":
            findings.append(
                SemanticMemoryFinalPreExecutionFinding(
                    code="INVALID_REQUESTER",
                    severity=SemanticMemoryFinalPreExecutionSeverity.BLOCKER,
                    message=f"Expected 'Cesar', got '{requested_by}'",
                    evidence={"requested_by": requested_by}
                )
            )
        
        # Check intent_scope
        intent_scope = final_intent.get("intent_scope")
        if intent_scope != "pre_execution_gate_only":
            findings.append(
                SemanticMemoryFinalPreExecutionFinding(
                    code="INVALID_INTENT_SCOPE",
                    severity=SemanticMemoryFinalPreExecutionSeverity.BLOCKER,
                    message=f"Expected 'pre_execution_gate_only', got '{intent_scope}'",
                    evidence={"intent_scope": intent_scope}
                )
            )
        
        # Check acknowledges_no_execution_now
        if final_intent.get("acknowledges_no_execution_now") is not True:
            findings.append(
                SemanticMemoryFinalPreExecutionFinding(
                    code="NO_EXECUTION_ACKNOWLEDGMENT_MISSING",
                    severity=SemanticMemoryFinalPreExecutionSeverity.BLOCKER,
                    message="Must acknowledge that no execution happens now",
                    evidence={}
                )
            )
        
        # Check allows_execution_now
        if final_intent.get("allows_execution_now") is True:
            findings.append(
                SemanticMemoryFinalPreExecutionFinding(
                    code="EXECUTION_NOW_BLOCKED",
                    severity=SemanticMemoryFinalPreExecutionSeverity.BLOCKER,
                    message="Execution now is not allowed - this gate is read-only",
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
            if final_intent.get(req) is not True:
                findings.append(
                    SemanticMemoryFinalPreExecutionFinding(
                        code=f"MISSING_{req.upper()}",
                        severity=SemanticMemoryFinalPreExecutionSeverity.WARNING,
                        message=f"Future requirement '{req}' not acknowledged",
                        evidence={"requirement": req}
                    )
                )
        
        # Add info finding for successful validation
        blockers = [f for f in findings if f.severity == SemanticMemoryFinalPreExecutionSeverity.BLOCKER]
        if len(blockers) == 0:
            findings.append(
                SemanticMemoryFinalPreExecutionFinding(
                    code="FINAL_INTENT_VALIDATION_PASSED",
                    severity=SemanticMemoryFinalPreExecutionSeverity.INFO,
                    message="Final intent validation passed",
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
            "gate_type": "FINAL_PRE_EXECUTION_GATE",
            "mode": "READ_ONLY",
            "allow_real_write": False,  # NEVER True
            "can_execute_real_write": False,  # NEVER True
            "execution_allowed_now": False,  # NEVER True
            "dry_run_only": True,  # ALWAYS True
            "simulated_only": True,  # ALWAYS True
            "requires_second_confirmation": True,  # ALWAYS True
            "requires_runtime_down": True,  # ALWAYS True
            "requires_clean_git_gate": True,  # ALWAYS True
            "requires_real_backup_before_execution": True,  # ALWAYS True
            "requires_real_rollback_before_execution": True,  # ALWAYS True
            "expected_hashes": {
                "candidate_design": self.EXPECTED_CANDIDATE_DESIGN_HASH,
                "authorization": self.EXPECTED_AUTHORIZATION_HASH,
                "go_no_go": self.EXPECTED_GO_NO_GO_HASH
            }
        }
    
    def block_gate(self, reason: str) -> SemanticMemoryFinalPreExecutionGateReport:
        """
        Create a blocked gate report with the given reason.
        
        Args:
            reason: Reason for blocking the gate
            
        Returns:
            A blocked gate report
        """
        finding = SemanticMemoryFinalPreExecutionFinding(
            code="MANUAL_BLOCK",
            severity=SemanticMemoryFinalPreExecutionSeverity.BLOCKER,
            message=reason,
            evidence={"blocked_by": "manual_intervention"}
        )
        
        return SemanticMemoryFinalPreExecutionGateReport(
            gate_id=self._gate_id,
            created_at_utc=self._now_utc(),
            decision=SemanticMemoryFinalPreExecutionDecision.BLOCK_PRE_EXECUTION,
            findings=[finding],
            blocker_count=1,
            warning_count=0,
            info_count=0,
            candidate_design_hash=self.EXPECTED_CANDIDATE_DESIGN_HASH,
            authorization_hash=self.EXPECTED_AUTHORIZATION_HASH,
            go_no_go_hash=self.EXPECTED_GO_NO_GO_HASH,
            execution_allowed_now=False,
            exact_future_operation={},
            required_real_backup_plan={},
            required_real_rollback_plan={},
            required_runtime_state={},
            required_git_state={},
            second_confirmation_contract={},
            final_blockers=[reason],
            can_execute_real_write=False,
            allow_real_write=False,
            dry_run_only=True,
            simulated_only=True,
            requires_second_confirmation=True,
            requires_runtime_down=True,
            requires_clean_git_gate=True,
            requires_real_backup_before_execution=True,
            requires_real_rollback_before_execution=True,
            metadata={"blocked": True, "reason": reason}
        )
    
    def _build_future_operation_plan(self) -> dict[str, Any]:
        """Build the exact future operation plan."""
        return {
            "operation": "controlled_real_write",
            "scope": "semantic_memory_promotion",
            "requires_prior": [
                "second_confirmation",
                "runtime_shutdown",
                "clean_git_state",
                "real_backup",
                "real_rollback_plan"
            ],
            "execution_trigger": "separate_future_gate",
            "authorized_by": "Cesar_only"
        }
    
    def _build_backup_plan(self) -> dict[str, Any]:
        """Build the required real backup plan."""
        return {
            "target": "memory/semantic/*",
            "method": "filesystem_copy",
            "location": "backup/semantic_memory/",
            "verification": "hash_check_required",
            "retention": "until_rollback_complete"
        }
    
    def _build_rollback_plan(self) -> dict[str, Any]:
        """Build the required real rollback plan."""
        return {
            "trigger": "failure_during_write",
            "method": "restore_from_backup",
            "verification": "integrity_check_required",
            "authorization": "Cesar_only"
        }
    
    def _build_required_runtime_state(self) -> dict[str, Any]:
        """Build the required runtime state."""
        return {
            "status": "DOWN",
            "verification": "process_check",
            "services_stopped": ["session", "main", "bridge"]
        }
    
    def _build_required_git_state(self) -> dict[str, Any]:
        """Build the required git state."""
        return {
            "clean_working_tree": True,
            "no_pending_commits": True,
            "no_staged_files": True,
            "branch": "codex/own-capital-sustainable-return"
        }
    
    def _build_second_confirmation_contract(self) -> dict[str, Any]:
        """Build the second confirmation contract."""
        return {
            "required": True,
            "authorized_party": "Cesar",
            "method": "explicit_separate_gate",
            "timing": "immediately_before_execution",
            "non_transferable": True
        }


# Factory function for convenience
def create_final_pre_execution_gate(
    repo_root: str | Path = "."
) -> SemanticMemoryFinalPreExecutionGate:
    """Create a new final pre-execution gate instance."""
    return SemanticMemoryFinalPreExecutionGate(repo_root)