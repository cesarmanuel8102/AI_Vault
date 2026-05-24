"""
SemanticMemory Controlled Real Write Execution Package (P2-E Commit 4D)

This module provides the final execution package before any real write execution.
It builds the complete execution plan, preflight, required backup, required rollback,
future command, future payload, checklist and second confirmation contract.

IMPORTANT: This module is READ-ONLY. It does NOT:
- Execute any real writes
- Create real backups
- Restore real backups
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


class SemanticMemoryExecutionPackageDecision(str, Enum):
    """Execution package decision states."""
    EXECUTION_PACKAGE_READY = "EXECUTION_PACKAGE_READY"
    MANUAL_REVIEW_REQUIRED = "MANUAL_REVIEW_REQUIRED"
    BLOCK_EXECUTION_PACKAGE = "BLOCK_EXECUTION_PACKAGE"


class SemanticMemoryExecutionPackageSeverity(str, Enum):
    """Severity levels for execution package findings."""
    INFO = "INFO"
    WARNING = "WARNING"
    BLOCKER = "BLOCKER"


@dataclass(frozen=True)
class SemanticMemoryExecutionPackageFinding:
    """A finding from the execution package evaluation."""
    code: str
    severity: SemanticMemoryExecutionPackageSeverity
    message: str
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class SemanticMemoryControlledRealWriteExecutionPackageReport:
    """Report from the execution package builder."""
    package_id: str
    created_at_utc: str
    decision: SemanticMemoryExecutionPackageDecision
    findings: list[SemanticMemoryExecutionPackageFinding]
    blocker_count: int
    warning_count: int
    info_count: int
    final_pre_execution_gate_hash: str
    candidate_design_hash: str
    authorization_hash: str
    go_no_go_hash: str
    future_execution_command: dict[str, Any]
    future_payload: dict[str, Any]
    required_backup_manifest: dict[str, Any]
    required_rollback_manifest: dict[str, Any]
    required_runtime_preflight: dict[str, Any]
    required_git_preflight: dict[str, Any]
    second_confirmation_contract: dict[str, Any]
    execution_allowed_now: bool = False
    can_execute_real_write: bool = False
    allow_real_write: bool = False
    dry_run_only: bool = True
    simulated_only: bool = True
    package_only: bool = True
    requires_second_confirmation: bool = True
    requires_runtime_down: bool = True
    requires_clean_git_gate: bool = True
    requires_real_backup_before_execution: bool = True
    requires_real_rollback_before_execution: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


class SemanticMemoryControlledRealWriteExecutionPackage:
    """
    Controlled real write execution package for SemanticMemory.
    
    This package is READ-ONLY and builds the complete execution plan
    for a future, separately gated real write operation.
    """
    
    EXPECTED_FINAL_PRE_EXECUTION_GATE_HASH = "dcf2b72e"
    EXPECTED_CANDIDATE_DESIGN_HASH = "b21c22dd"
    EXPECTED_AUTHORIZATION_HASH = "819be9f2"
    EXPECTED_GO_NO_GO_HASH = "433c5842"
    
    def __init__(self, repo_root: str | Path = ".") -> None:
        """Initialize the execution package with a repository root path."""
        self._repo_root = Path(repo_root)
        self._package_id = self._generate_package_id()
    
    def _generate_package_id(self) -> str:
        """Generate a unique package ID based on timestamp."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        random_component = hashlib.sha256(
            timestamp.encode() + str(datetime.now(timezone.utc).timestamp()).encode()
        ).hexdigest()[:8]
        return f"EXEC-PKG-{timestamp}-{random_component}"
    
    def _now_utc(self) -> str:
        """Get current UTC timestamp as ISO string."""
        return datetime.now(timezone.utc).isoformat()
    
    def build_execution_package_read_only(
        self,
        evidence: dict[str, Any],
        execution_intent: dict[str, Any] | None = None
    ) -> SemanticMemoryControlledRealWriteExecutionPackageReport:
        """
        Build the execution package in read-only mode.
        
        This method validates evidence chain and execution intent to determine
        if the system is ready for a future real write operation.
        
        Args:
            evidence: Evidence dictionary from previous gates
            execution_intent: Optional execution intent declaration
            
        Returns:
            A read-only report with decision and findings
        """
        findings: list[SemanticMemoryExecutionPackageFinding] = []
        
        # Validate chain evidence
        chain_findings = self.validate_chain_evidence_read_only(evidence)
        findings.extend(chain_findings)
        
        # Validate execution intent if provided
        if execution_intent is not None:
            intent_findings = self.validate_execution_intent_read_only(execution_intent)
            findings.extend(intent_findings)
        else:
            findings.append(
                SemanticMemoryExecutionPackageFinding(
                    code="MISSING_EXECUTION_INTENT",
                    severity=SemanticMemoryExecutionPackageSeverity.WARNING,
                    message="Execution intent not provided; manual review required",
                    evidence={}
                )
            )
        
        # Calculate counts
        blocker_count = sum(
            1 for f in findings 
            if f.severity == SemanticMemoryExecutionPackageSeverity.BLOCKER
        )
        warning_count = sum(
            1 for f in findings 
            if f.severity == SemanticMemoryExecutionPackageSeverity.WARNING
        )
        info_count = sum(
            1 for f in findings 
            if f.severity == SemanticMemoryExecutionPackageSeverity.INFO
        )
        
        # Determine decision
        if blocker_count > 0:
            decision = SemanticMemoryExecutionPackageDecision.BLOCK_EXECUTION_PACKAGE
        elif execution_intent is None:
            decision = SemanticMemoryExecutionPackageDecision.MANUAL_REVIEW_REQUIRED
        else:
            decision = SemanticMemoryExecutionPackageDecision.EXECUTION_PACKAGE_READY
        
        # Build the report with all safety invariants
        report = SemanticMemoryControlledRealWriteExecutionPackageReport(
            package_id=self._package_id,
            created_at_utc=self._now_utc(),
            decision=decision,
            findings=findings,
            blocker_count=blocker_count,
            warning_count=warning_count,
            info_count=info_count,
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
            future_execution_command=self._build_future_execution_command(evidence),
            future_payload=self._build_future_payload(evidence, execution_intent),
            required_backup_manifest=self._build_backup_manifest(),
            required_rollback_manifest=self._build_rollback_manifest(),
            required_runtime_preflight=self._build_runtime_preflight(),
            required_git_preflight=self._build_git_preflight(),
            second_confirmation_contract=self._build_second_confirmation_contract(),
            execution_allowed_now=False,  # NEVER True
            can_execute_real_write=False,  # NEVER True
            allow_real_write=False,  # NEVER True
            dry_run_only=True,  # ALWAYS True
            simulated_only=True,  # ALWAYS True
            package_only=True,  # ALWAYS True
            requires_second_confirmation=True,  # ALWAYS True
            requires_runtime_down=True,  # ALWAYS True
            requires_clean_git_gate=True,  # ALWAYS True
            requires_real_backup_before_execution=True,  # ALWAYS True
            requires_real_rollback_before_execution=True,  # ALWAYS True
            metadata={
                "evidence_keys": list(evidence.keys()),
                "execution_intent_provided": execution_intent is not None,
                "package_timestamp": self._now_utc()
            }
        )
        
        return report
    
    def validate_chain_evidence_read_only(
        self,
        evidence: dict[str, Any]
    ) -> list[SemanticMemoryExecutionPackageFinding]:
        """
        Validate the evidence chain from previous gates.
        
        Args:
            evidence: Evidence dictionary
            
        Returns:
            List of findings from validation
        """
        findings: list[SemanticMemoryExecutionPackageFinding] = []
        
        # Check final_pre_execution_decision
        final_pre_execution_decision = evidence.get("final_pre_execution_decision")
        if final_pre_execution_decision != "PRE_EXECUTION_GATE_READY":
            findings.append(
                SemanticMemoryExecutionPackageFinding(
                    code="INVALID_FINAL_PRE_EXECUTION_DECISION",
                    severity=SemanticMemoryExecutionPackageSeverity.BLOCKER,
                    message=f"Expected PRE_EXECUTION_GATE_READY, got {final_pre_execution_decision}",
                    evidence={"received": final_pre_execution_decision}
                )
            )
        
        # Check final_pre_execution_gate_hash
        final_pre_execution_gate_hash = evidence.get("final_pre_execution_gate_hash")
        if final_pre_execution_gate_hash != self.EXPECTED_FINAL_PRE_EXECUTION_GATE_HASH:
            findings.append(
                SemanticMemoryExecutionPackageFinding(
                    code="INVALID_FINAL_PRE_EXECUTION_GATE_HASH",
                    severity=SemanticMemoryExecutionPackageSeverity.BLOCKER,
                    message=f"Expected {self.EXPECTED_FINAL_PRE_EXECUTION_GATE_HASH}, got {final_pre_execution_gate_hash}",
                    evidence={"received": final_pre_execution_gate_hash}
                )
            )
        
        # Check candidate_design_hash
        candidate_design_hash = evidence.get("candidate_design_hash")
        if candidate_design_hash != self.EXPECTED_CANDIDATE_DESIGN_HASH:
            findings.append(
                SemanticMemoryExecutionPackageFinding(
                    code="INVALID_CANDIDATE_DESIGN_HASH",
                    severity=SemanticMemoryExecutionPackageSeverity.BLOCKER,
                    message=f"Expected {self.EXPECTED_CANDIDATE_DESIGN_HASH}, got {candidate_design_hash}",
                    evidence={"received": candidate_design_hash}
                )
            )
        
        # Check authorization_hash
        authorization_hash = evidence.get("authorization_hash")
        if authorization_hash != self.EXPECTED_AUTHORIZATION_HASH:
            findings.append(
                SemanticMemoryExecutionPackageFinding(
                    code="INVALID_AUTHORIZATION_HASH",
                    severity=SemanticMemoryExecutionPackageSeverity.BLOCKER,
                    message=f"Expected {self.EXPECTED_AUTHORIZATION_HASH}, got {authorization_hash}",
                    evidence={"received": authorization_hash}
                )
            )
        
        # Check go_no_go_hash
        go_no_go_hash = evidence.get("go_no_go_hash")
        if go_no_go_hash != self.EXPECTED_GO_NO_GO_HASH:
            findings.append(
                SemanticMemoryExecutionPackageFinding(
                    code="INVALID_GO_NO_GO_HASH",
                    severity=SemanticMemoryExecutionPackageSeverity.BLOCKER,
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
                SemanticMemoryExecutionPackageFinding(
                    code="PENDING_COMMITS_DETECTED",
                    severity=SemanticMemoryExecutionPackageSeverity.BLOCKER,
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
                SemanticMemoryExecutionPackageFinding(
                    code="STAGED_FILES_DETECTED",
                    severity=SemanticMemoryExecutionPackageSeverity.BLOCKER,
                    message=f"Expected empty staged files, found {len(staged_files)} files",
                    evidence={"staged_count": len(staged_files)}
                )
            )
        
        # Check memory_semantic_in_scope
        if evidence.get("memory_semantic_in_scope") is True:
            findings.append(
                SemanticMemoryExecutionPackageFinding(
                    code="MEMORY_SEMANTIC_IN_SCOPE",
                    severity=SemanticMemoryExecutionPackageSeverity.BLOCKER,
                    message="memory/semantic is in scope - this is forbidden for execution package",
                    evidence={}
                )
            )
        
        # Check runtime_active
        if evidence.get("runtime_active") is True:
            findings.append(
                SemanticMemoryExecutionPackageFinding(
                    code="RUNTIME_ACTIVE",
                    severity=SemanticMemoryExecutionPackageSeverity.BLOCKER,
                    message="Runtime is active - must be down before execution",
                    evidence={}
                )
            )
        
        # Check faiss_write_enabled
        if evidence.get("faiss_write_enabled") is True:
            findings.append(
                SemanticMemoryExecutionPackageFinding(
                    code="FAISS_WRITE_ENABLED",
                    severity=SemanticMemoryExecutionPackageSeverity.BLOCKER,
                    message="FAISS write is enabled - this is forbidden for execution package",
                    evidence={}
                )
            )
        
        # Check add_memory_enabled
        if evidence.get("add_memory_enabled") is True:
            findings.append(
                SemanticMemoryExecutionPackageFinding(
                    code="ADD_MEMORY_ENABLED",
                    severity=SemanticMemoryExecutionPackageSeverity.BLOCKER,
                    message="add_memory is enabled - this is forbidden for execution package",
                    evidence={}
                )
            )
        
        # Check allows_auto_execute
        if evidence.get("allows_auto_execute") is True:
            findings.append(
                SemanticMemoryExecutionPackageFinding(
                    code="AUTO_EXECUTE_ENABLED",
                    severity=SemanticMemoryExecutionPackageSeverity.BLOCKER,
                    message="Auto-execution is enabled - this is forbidden for execution package",
                    evidence={}
                )
            )
        
        # Add info finding for successful validation
        if len(findings) == 0:
            findings.append(
                SemanticMemoryExecutionPackageFinding(
                    code="EVIDENCE_VALIDATION_PASSED",
                    severity=SemanticMemoryExecutionPackageSeverity.INFO,
                    message="All evidence chain validations passed",
                    evidence={
                        "final_pre_execution_gate_hash": final_pre_execution_gate_hash,
                        "candidate_design_hash": candidate_design_hash,
                        "authorization_hash": authorization_hash,
                        "go_no_go_hash": go_no_go_hash
                    }
                )
            )
        
        return findings
    
    def validate_execution_intent_read_only(
        self,
        execution_intent: dict[str, Any]
    ) -> list[SemanticMemoryExecutionPackageFinding]:
        """
        Validate the execution intent declaration.
        
        Args:
            execution_intent: Execution intent dictionary
            
        Returns:
            List of findings from validation
        """
        findings: list[SemanticMemoryExecutionPackageFinding] = []
        
        # Check requested_by
        requested_by = execution_intent.get("requested_by")
        if requested_by != "Cesar":
            findings.append(
                SemanticMemoryExecutionPackageFinding(
                    code="INVALID_REQUESTER",
                    severity=SemanticMemoryExecutionPackageSeverity.BLOCKER,
                    message=f"Expected 'Cesar', got '{requested_by}'",
                    evidence={"requested_by": requested_by}
                )
            )
        
        # Check intent_scope
        intent_scope = execution_intent.get("intent_scope")
        if intent_scope != "execution_package_only":
            findings.append(
                SemanticMemoryExecutionPackageFinding(
                    code="INVALID_INTENT_SCOPE",
                    severity=SemanticMemoryExecutionPackageSeverity.BLOCKER,
                    message=f"Expected 'execution_package_only', got '{intent_scope}'",
                    evidence={"intent_scope": intent_scope}
                )
            )
        
        # Check target_operation
        target_operation = execution_intent.get("target_operation")
        if target_operation != "single_curated_fact_probe":
            findings.append(
                SemanticMemoryExecutionPackageFinding(
                    code="INVALID_TARGET_OPERATION",
                    severity=SemanticMemoryExecutionPackageSeverity.WARNING,
                    message=f"Expected 'single_curated_fact_probe', got '{target_operation}'",
                    evidence={"target_operation": target_operation}
                )
            )
        
        # Check acknowledges_no_execution_now
        if execution_intent.get("acknowledges_no_execution_now") is not True:
            findings.append(
                SemanticMemoryExecutionPackageFinding(
                    code="NO_EXECUTION_ACKNOWLEDGMENT_MISSING",
                    severity=SemanticMemoryExecutionPackageSeverity.BLOCKER,
                    message="Must acknowledge that no execution happens now",
                    evidence={}
                )
            )
        
        # Check allows_execution_now
        if execution_intent.get("allows_execution_now") is True:
            findings.append(
                SemanticMemoryExecutionPackageFinding(
                    code="EXECUTION_NOW_BLOCKED",
                    severity=SemanticMemoryExecutionPackageSeverity.BLOCKER,
                    message="Execution now is not allowed - this package is read-only",
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
            if execution_intent.get(req) is not True:
                findings.append(
                    SemanticMemoryExecutionPackageFinding(
                        code=f"MISSING_{req.upper()}",
                        severity=SemanticMemoryExecutionPackageSeverity.WARNING,
                        message=f"Future requirement '{req}' not acknowledged",
                        evidence={"requirement": req}
                    )
                )
        
        # Add info finding for successful validation
        blockers = [f for f in findings if f.severity == SemanticMemoryExecutionPackageSeverity.BLOCKER]
        if len(blockers) == 0:
            findings.append(
                SemanticMemoryExecutionPackageFinding(
                    code="EXECUTION_INTENT_VALIDATION_PASSED",
                    severity=SemanticMemoryExecutionPackageSeverity.INFO,
                    message="Execution intent validation passed",
                    evidence={"requested_by": requested_by, "target_operation": target_operation}
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
            "package_type": "EXECUTION_PACKAGE",
            "mode": "READ_ONLY",
            "allow_real_write": False,  # NEVER True
            "can_execute_real_write": False,  # NEVER True
            "execution_allowed_now": False,  # NEVER True
            "dry_run_only": True,  # ALWAYS True
            "simulated_only": True,  # ALWAYS True
            "package_only": True,  # ALWAYS True
            "requires_second_confirmation": True,  # ALWAYS True
            "requires_runtime_down": True,  # ALWAYS True
            "requires_clean_git_gate": True,  # ALWAYS True
            "requires_real_backup_before_execution": True,  # ALWAYS True
            "requires_real_rollback_before_execution": True,  # ALWAYS True
            "expected_hashes": {
                "final_pre_execution_gate": self.EXPECTED_FINAL_PRE_EXECUTION_GATE_HASH,
                "candidate_design": self.EXPECTED_CANDIDATE_DESIGN_HASH,
                "authorization": self.EXPECTED_AUTHORIZATION_HASH,
                "go_no_go": self.EXPECTED_GO_NO_GO_HASH
            }
        }
    
    def block_package(self, reason: str) -> SemanticMemoryControlledRealWriteExecutionPackageReport:
        """
        Create a blocked package report with the given reason.
        
        Args:
            reason: Reason for blocking the package
            
        Returns:
            A blocked package report
        """
        finding = SemanticMemoryExecutionPackageFinding(
            code="MANUAL_BLOCK",
            severity=SemanticMemoryExecutionPackageSeverity.BLOCKER,
            message=reason,
            evidence={"blocked_by": "manual_intervention"}
        )
        
        return SemanticMemoryControlledRealWriteExecutionPackageReport(
            package_id=self._package_id,
            created_at_utc=self._now_utc(),
            decision=SemanticMemoryExecutionPackageDecision.BLOCK_EXECUTION_PACKAGE,
            findings=[finding],
            blocker_count=1,
            warning_count=0,
            info_count=0,
            final_pre_execution_gate_hash=self.EXPECTED_FINAL_PRE_EXECUTION_GATE_HASH,
            candidate_design_hash=self.EXPECTED_CANDIDATE_DESIGN_HASH,
            authorization_hash=self.EXPECTED_AUTHORIZATION_HASH,
            go_no_go_hash=self.EXPECTED_GO_NO_GO_HASH,
            future_execution_command={},
            future_payload={},
            required_backup_manifest={},
            required_rollback_manifest={},
            required_runtime_preflight={},
            required_git_preflight={},
            second_confirmation_contract={},
            execution_allowed_now=False,
            can_execute_real_write=False,
            allow_real_write=False,
            dry_run_only=True,
            simulated_only=True,
            package_only=True,
            requires_second_confirmation=True,
            requires_runtime_down=True,
            requires_clean_git_gate=True,
            requires_real_backup_before_execution=True,
            requires_real_rollback_before_execution=True,
            metadata={"blocked": True, "reason": reason}
        )
    
    def _build_future_execution_command(self, evidence: dict[str, Any]) -> dict[str, Any]:
        """Build the future execution command."""
        return {
            "command": "controlled_real_write",
            "scope": "semantic_memory_promotion",
            "target_operation": "single_curated_fact_probe",
            "target_room": "migration_p2e_probe",
            "requires_prior": [
                "second_confirmation",
                "runtime_shutdown",
                "clean_git_state",
                "real_backup",
                "real_rollback_plan"
            ],
            "execution_trigger": "separate_future_gate_with_cesar_approval",
            "authorized_by": "Cesar_only",
            "method": "curated_fact_promotion_via_bridge",
            "rollback_on_failure": True
        }
    
    def _build_future_payload(self, evidence: dict[str, Any], execution_intent: dict[str, Any] | None) -> dict[str, Any]:
        """Build the future payload."""
        if execution_intent:
            return {
                "fact_key": execution_intent.get("candidate_fact_key", "p2e_real_write_probe"),
                "fact_value": execution_intent.get("candidate_fact_value", "controlled execution package only; not executed"),
                "target_room": execution_intent.get("target_room", "migration_p2e_probe"),
                "metadata": {
                    "package_id": self._package_id,
                    "final_pre_execution_gate_hash": evidence.get("final_pre_execution_gate_hash"),
                    "candidate_design_hash": evidence.get("candidate_design_hash"),
                    "authorization_hash": evidence.get("authorization_hash")
                }
            }
        return {
            "fact_key": "p2e_real_write_probe",
            "fact_value": "controlled execution package only; not executed",
            "target_room": "migration_p2e_probe",
            "metadata": {"package_id": self._package_id}
        }
    
    def _build_backup_manifest(self) -> dict[str, Any]:
        """Build the required backup manifest."""
        return {
            "manifest_type": "BACKUP_REQUIRED",
            "target": "memory/semantic/*",
            "method": "filesystem_copy",
            "location": "backup/semantic_memory/",
            "verification": "hash_check_required",
            "retention": "until_rollback_complete",
            "rollback_plan": "restore_from_backup_on_failure",
            "verification_steps": [
                "verify_backup_exists",
                "verify_backup_integrity",
                "verify_backup_accessible"
            ]
        }
    
    def _build_rollback_manifest(self) -> dict[str, Any]:
        """Build the required rollback manifest."""
        return {
            "manifest_type": "ROLLBACK_REQUIRED",
            "trigger": "failure_during_write",
            "method": "restore_from_backup",
            "verification": "integrity_check_required",
            "authorization": "Cesar_only",
            "steps": [
                "detect_failure",
                "stop_runtime",
                "restore_from_backup",
                "verify_integrity",
                "resume_runtime_if_safe"
            ],
            "max_retries": 3
        }
    
    def _build_runtime_preflight(self) -> dict[str, Any]:
        """Build the required runtime preflight."""
        return {
            "status": "DOWN",
            "verification": "process_check",
            "services_stopped": ["session", "main", "bridge"],
            "preflight_checks": [
                "verify_no_runtime_processes",
                "verify_no_open_connections",
                "verify_clean_shutdown"
            ]
        }
    
    def _build_git_preflight(self) -> dict[str, Any]:
        """Build the required git preflight."""
        return {
            "clean_working_tree": True,
            "no_pending_commits": True,
            "no_staged_files": True,
            "branch": "codex/own-capital-sustainable-return",
            "preflight_checks": [
                "verify_clean_working_tree",
                "verify_no_uncommitted_changes",
                "verify_correct_branch"
            ]
        }
    
    def _build_second_confirmation_contract(self) -> dict[str, Any]:
        """Build the second confirmation contract."""
        return {
            "required": True,
            "authorized_party": "Cesar",
            "method": "explicit_separate_gate_with_package_id",
            "timing": "immediately_before_execution",
            "non_transferable": True,
            "verification": "manual_hash_confirmation",
            "confirmation_data_required": [
                "package_id",
                "final_pre_execution_gate_hash",
                "candidate_design_hash",
                "authorization_hash"
            ]
        }


# Factory function for convenience
def create_execution_package(
    repo_root: str | Path = "."
) -> SemanticMemoryControlledRealWriteExecutionPackage:
    """Create a new execution package instance."""
    return SemanticMemoryControlledRealWriteExecutionPackage(repo_root)