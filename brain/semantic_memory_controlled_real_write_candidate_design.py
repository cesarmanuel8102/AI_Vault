"""P2-E Commit 4D-ControlledRealWriteCandidateDesign: Read-only design of exact candidate for future controlled real write.

This module provides a read-only design of the exact candidate for a future controlled real write operation.
It specifies the candidate, scope, preconditions, expected backup/rollback, dry-run checklist, and second confirmation criteria.

IMPORTANT: This module NEVER executes real writes. It only produces a candidate design.
- can_execute_real_write is always False
- allow_real_write is always False
- dry_run_only is always True
- simulated_only is always True
- requires_second_confirmation is always True
- requires_runtime_down is always True
- requires_clean_git_gate is always True
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class SemanticMemoryCandidateDesignDecision(Enum):
    """Candidate design decision outcomes."""
    CANDIDATE_DESIGN_READY = "candidate_design_ready"
    MANUAL_REVIEW_REQUIRED = "manual_review_required"
    BLOCK_CANDIDATE_DESIGN = "block_candidate_design"


class SemanticMemoryCandidateDesignSeverity(Enum):
    """Severity levels for candidate design findings."""
    INFO = "info"
    WARNING = "warning"
    BLOCKER = "blocker"


@dataclass
class SemanticMemoryCandidateDesignFinding:
    """A single finding in the candidate design validation."""
    code: str
    severity: SemanticMemoryCandidateDesignSeverity
    message: str
    evidence: dict = field(default_factory=dict)


@dataclass
class SemanticMemoryControlledRealWriteCandidateDesignReport:
    """Complete controlled real write candidate design report."""
    candidate_id: str
    created_at_utc: str
    decision: SemanticMemoryCandidateDesignDecision
    findings: list[SemanticMemoryCandidateDesignFinding]
    blocker_count: int
    warning_count: int
    info_count: int
    authorization_hash: str
    target_operation_type: str
    scope: dict
    candidate_payload: dict
    expected_diff: dict
    backup_plan: dict
    rollback_plan: dict
    preflight_checklist: dict
    dry_run_verification: dict
    second_confirmation: dict
    hard_blockers: list[str]
    can_execute_real_write: bool = False
    allow_real_write: bool = False
    dry_run_only: bool = True
    simulated_only: bool = True
    requires_second_confirmation: bool = True
    requires_runtime_down: bool = True
    requires_clean_git_gate: bool = True
    metadata: dict = field(default_factory=dict)


class SemanticMemoryControlledRealWriteCandidateDesign:
    """Controlled real write candidate design builder.
    
    This class builds a read-only candidate design. It NEVER executes real writes.
    
    Safety invariants:
    - can_execute_real_write is always False
    - allow_real_write is always False
    - dry_run_only is always True
    - simulated_only is always True
    - requires_second_confirmation is always True
    - requires_runtime_down is always True
    - requires_clean_git_gate is always True
    """
    
    VERSION = "4D-CandidateDesign-v1.0.0"
    EXPECTED_AUTHORIZATION_HASH = "819be9f2"
    
    def __init__(self, repo_root: str | Path = ".") -> None:
        """Initialize the candidate design builder.
        
        Args:
            repo_root: Path to the repository root
        """
        self.repo_root = Path(repo_root)
        self.candidate_id = str(uuid.uuid4())
    
    def build_candidate_design_read_only(
        self,
        evidence: dict[str, Any],
        candidate_request: dict[str, Any] | None = None
    ) -> SemanticMemoryControlledRealWriteCandidateDesignReport:
        """Build candidate design based on evidence and candidate request.
        
        This method is read-only and NEVER executes real writes.
        
        Args:
            evidence: Dictionary containing evidence from authorization packet
            candidate_request: Dictionary containing candidate request
            
        Returns:
            SemanticMemoryControlledRealWriteCandidateDesignReport with decision and findings
        """
        findings: list[SemanticMemoryCandidateDesignFinding] = []
        
        # Validate authorization evidence
        auth_findings = self.validate_authorization_evidence_read_only(evidence)
        findings.extend(auth_findings)
        
        # Validate candidate request
        request_findings = self.validate_candidate_request_read_only(candidate_request)
        findings.extend(request_findings)
        
        # Count findings
        blocker_count = sum(1 for f in findings if f.severity == SemanticMemoryCandidateDesignSeverity.BLOCKER)
        warning_count = sum(1 for f in findings if f.severity == SemanticMemoryCandidateDesignSeverity.WARNING)
        info_count = sum(1 for f in findings if f.severity == SemanticMemoryCandidateDesignSeverity.INFO)
        
        # Determine decision
        decision = self._determine_decision(evidence, candidate_request, findings)
        
        # Build candidate design structure
        if candidate_request:
            scope = {
                "candidate_scope": candidate_request.get("candidate_scope", "unknown"),
                "target_room": candidate_request.get("target_room", "unknown"),
            }
            candidate_payload = {
                "fact_key": candidate_request.get("candidate_fact_key", "unknown"),
                "fact_value": candidate_request.get("candidate_fact_value", "unknown"),
            }
        else:
            scope = {"candidate_scope": "unknown", "target_room": "unknown"}
            candidate_payload = {"fact_key": "unknown", "fact_value": "unknown"}
        
        return SemanticMemoryControlledRealWriteCandidateDesignReport(
            candidate_id=self.candidate_id,
            created_at_utc=datetime.now(timezone.utc).isoformat(),
            decision=decision,
            findings=findings,
            blocker_count=blocker_count,
            warning_count=warning_count,
            info_count=info_count,
            authorization_hash=evidence.get("authorization_hash", "UNKNOWN"),
            target_operation_type="controlled_semantic_memory_write_candidate",
            scope=scope,
            candidate_payload=candidate_payload,
            expected_diff={
                "operation": "design_only",
                "description": "No actual diff - this is a candidate design",
                "simulated_changes": ["fact_probe_entry"],
            },
            backup_plan={
                "required": True,
                "description": "Full semantic memory backup required before any real write",
                "backup_targets": ["memory/semantic/"],
                "validation_required": True,
            },
            rollback_plan={
                "required": True,
                "description": "Automated rollback on failure required",
                "rollback_targets": ["memory/semantic/", "FAISS index"],
                "validation_required": True,
            },
            preflight_checklist={
                "runtime_down": "Required",
                "git_clean": "Required",
                "backup_validated": "Required",
                "security_validation": "Required",
            },
            dry_run_verification={
                "simulated": True,
                "writes_blocked": True,
                "reads_allowed": True,
                "validation_complete": True,
            },
            second_confirmation={
                "required": True,
                "approver": "Cesar",
                "timestamp_required": True,
            },
            hard_blockers=[
                "runtime_active",
                "git_unclean",
                "backup_not_validated",
                "no_second_confirmation",
            ],
            can_execute_real_write=False,  # SAFETY: Never True
            allow_real_write=False,  # SAFETY: Never True
            dry_run_only=True,  # SAFETY: Always True
            simulated_only=True,  # SAFETY: Always True
            requires_second_confirmation=True,  # SAFETY: Always True
            requires_runtime_down=True,  # SAFETY: Always True
            requires_clean_git_gate=True,  # SAFETY: Always True
            metadata={
                "version": self.VERSION,
                "repo_root": str(self.repo_root),
                "evidence_keys": list(evidence.keys()),
                "request_keys": list(candidate_request.keys()) if candidate_request else [],
            }
        )
    
    def _determine_decision(
        self,
        evidence: dict[str, Any],
        candidate_request: dict[str, Any] | None,
        findings: list[SemanticMemoryCandidateDesignFinding]
    ) -> SemanticMemoryCandidateDesignDecision:
        """Determine the candidate design decision based on evidence and request.
        
        Rules:
        1. If any blockers: BLOCK_CANDIDATE_DESIGN
        2. If authorization_decision != AUTHORIZATION_PACKET_READY: BLOCK
        3. If authorization_hash != 819be9f2: BLOCK
        4. If commits_pending_post_push > 0: BLOCK
        5. If staged_files not empty: BLOCK
        6. If memory_semantic_in_scope=True: BLOCK
        7. If runtime_active=True: BLOCK
        8. If faiss_write_enabled=True: BLOCK
        9. If add_memory_enabled=True: BLOCK
        10. If allows_auto_execute=True: BLOCK
        11. If operation_mode != design_only: BLOCK
        12. If expects_no_write != True: BLOCK
        13. If candidate_request missing: MANUAL_REVIEW_REQUIRED
        14. If all checks pass: CANDIDATE_DESIGN_READY
        """
        # Check for blockers first
        blocker_count = sum(1 for f in findings if f.severity == SemanticMemoryCandidateDesignSeverity.BLOCKER)
        if blocker_count > 0:
            return SemanticMemoryCandidateDesignDecision.BLOCK_CANDIDATE_DESIGN
        
        # Check authorization decision
        if evidence.get("authorization_decision") != "AUTHORIZATION_PACKET_READY":
            return SemanticMemoryCandidateDesignDecision.BLOCK_CANDIDATE_DESIGN
        
        # Check authorization hash
        if evidence.get("authorization_hash") != self.EXPECTED_AUTHORIZATION_HASH:
            return SemanticMemoryCandidateDesignDecision.BLOCK_CANDIDATE_DESIGN
        
        # Check absolute blockers
        if evidence.get("commits_pending_post_push", 0) > 0:
            return SemanticMemoryCandidateDesignDecision.BLOCK_CANDIDATE_DESIGN
        
        if evidence.get("staged_files", []):
            return SemanticMemoryCandidateDesignDecision.BLOCK_CANDIDATE_DESIGN
        
        if evidence.get("memory_semantic_in_scope", False):
            return SemanticMemoryCandidateDesignDecision.BLOCK_CANDIDATE_DESIGN
        
        if evidence.get("runtime_active", False):
            return SemanticMemoryCandidateDesignDecision.BLOCK_CANDIDATE_DESIGN
        
        if evidence.get("faiss_write_enabled", False):
            return SemanticMemoryCandidateDesignDecision.BLOCK_CANDIDATE_DESIGN
        
        if evidence.get("add_memory_enabled", False):
            return SemanticMemoryCandidateDesignDecision.BLOCK_CANDIDATE_DESIGN
        
        if evidence.get("allows_auto_execute", False):
            return SemanticMemoryCandidateDesignDecision.BLOCK_CANDIDATE_DESIGN
        
        # Check candidate request
        if candidate_request is None:
            return SemanticMemoryCandidateDesignDecision.MANUAL_REVIEW_REQUIRED
        
        if candidate_request.get("operation_mode") != "design_only":
            return SemanticMemoryCandidateDesignDecision.BLOCK_CANDIDATE_DESIGN
        
        if candidate_request.get("expects_no_write") is not True:
            return SemanticMemoryCandidateDesignDecision.BLOCK_CANDIDATE_DESIGN
        
        # All checks passed
        return SemanticMemoryCandidateDesignDecision.CANDIDATE_DESIGN_READY
    
    def validate_authorization_evidence_read_only(
        self,
        evidence: dict[str, Any]
    ) -> list[SemanticMemoryCandidateDesignFinding]:
        """Validate authorization evidence.
        
        Args:
            evidence: Evidence dictionary to validate
            
        Returns:
            List of findings from validation
        """
        findings: list[SemanticMemoryCandidateDesignFinding] = []
        
        # Check authorization decision
        if evidence.get("authorization_decision") != "AUTHORIZATION_PACKET_READY":
            findings.append(SemanticMemoryCandidateDesignFinding(
                code="INVALID_AUTHORIZATION_DECISION",
                severity=SemanticMemoryCandidateDesignSeverity.BLOCKER,
                message=f"Authorization decision must be AUTHORIZATION_PACKET_READY, got: {evidence.get('authorization_decision', 'MISSING')}",
                evidence={"authorization_decision": evidence.get("authorization_decision")}
            ))
        
        # Check authorization hash
        if evidence.get("authorization_hash") != self.EXPECTED_AUTHORIZATION_HASH:
            findings.append(SemanticMemoryCandidateDesignFinding(
                code="INVALID_AUTHORIZATION_HASH",
                severity=SemanticMemoryCandidateDesignSeverity.BLOCKER,
                message=f"Authorization hash must be {self.EXPECTED_AUTHORIZATION_HASH}, got: {evidence.get('authorization_hash', 'MISSING')}",
                evidence={"expected": self.EXPECTED_AUTHORIZATION_HASH, "got": evidence.get("authorization_hash")}
            ))
        
        # Check absolute blockers
        if evidence.get("commits_pending_post_push", 0) > 0:
            findings.append(SemanticMemoryCandidateDesignFinding(
                code="PENDING_COMMITS",
                severity=SemanticMemoryCandidateDesignSeverity.BLOCKER,
                message=f"{evidence['commits_pending_post_push']} commits pending post-push",
                evidence={"commits_pending": evidence["commits_pending_post_push"]}
            ))
        
        if evidence.get("staged_files", []):
            findings.append(SemanticMemoryCandidateDesignFinding(
                code="STAGED_FILES",
                severity=SemanticMemoryCandidateDesignSeverity.BLOCKER,
                message=f"{len(evidence['staged_files'])} files staged",
                evidence={"staged_count": len(evidence["staged_files"])}
            ))
        
        if evidence.get("memory_semantic_in_scope", False):
            findings.append(SemanticMemoryCandidateDesignFinding(
                code="MEMORY_SEMANTIC_IN_SCOPE",
                severity=SemanticMemoryCandidateDesignSeverity.BLOCKER,
                message="memory/semantic is in scope - cannot proceed",
                evidence={}
            ))
        
        if evidence.get("runtime_active", False):
            findings.append(SemanticMemoryCandidateDesignFinding(
                code="RUNTIME_ACTIVE",
                severity=SemanticMemoryCandidateDesignSeverity.BLOCKER,
                message="Runtime is active - cannot proceed",
                evidence={}
            ))
        
        if evidence.get("faiss_write_enabled", False):
            findings.append(SemanticMemoryCandidateDesignFinding(
                code="FAISS_WRITE_ENABLED",
                severity=SemanticMemoryCandidateDesignSeverity.BLOCKER,
                message="FAISS write is enabled - cannot proceed",
                evidence={}
            ))
        
        if evidence.get("add_memory_enabled", False):
            findings.append(SemanticMemoryCandidateDesignFinding(
                code="ADD_MEMORY_ENABLED",
                severity=SemanticMemoryCandidateDesignSeverity.BLOCKER,
                message="add_memory is enabled - cannot proceed",
                evidence={}
            ))
        
        if evidence.get("allows_auto_execute", False):
            findings.append(SemanticMemoryCandidateDesignFinding(
                code="AUTO_EXECUTE_ALLOWED",
                severity=SemanticMemoryCandidateDesignSeverity.BLOCKER,
                message="Auto-execution is allowed - cannot proceed",
                evidence={}
            ))
        
        return findings
    
    def validate_candidate_request_read_only(
        self,
        candidate_request: dict[str, Any] | None
    ) -> list[SemanticMemoryCandidateDesignFinding]:
        """Validate candidate request.
        
        Args:
            candidate_request: Candidate request dictionary to validate
            
        Returns:
            List of findings from validation
        """
        findings: list[SemanticMemoryCandidateDesignFinding] = []
        
        if candidate_request is None:
            findings.append(SemanticMemoryCandidateDesignFinding(
                code="MISSING_CANDIDATE_REQUEST",
                severity=SemanticMemoryCandidateDesignSeverity.WARNING,
                message="Candidate request is missing - manual review required",
                evidence={}
            ))
            return findings
        
        # Validate operation_mode
        if candidate_request.get("operation_mode") != "design_only":
            findings.append(SemanticMemoryCandidateDesignFinding(
                code="INVALID_OPERATION_MODE",
                severity=SemanticMemoryCandidateDesignSeverity.BLOCKER,
                message=f"Operation mode must be 'design_only', got: {candidate_request.get('operation_mode', 'MISSING')}",
                evidence={"operation_mode": candidate_request.get("operation_mode")}
            ))
        
        # Validate expects_no_write
        if candidate_request.get("expects_no_write") is not True:
            findings.append(SemanticMemoryCandidateDesignFinding(
                code="EXPECTS_WRITE_TRUE",
                severity=SemanticMemoryCandidateDesignSeverity.BLOCKER,
                message="Candidate request expects write - BLOCKED for safety",
                evidence={"expects_no_write": candidate_request.get("expects_no_write")}
            ))
        
        return findings
    
    def summarize_contract(self) -> dict:
        """Summarize the contract enforced by this candidate design.
        
        Returns:
            Dictionary summarizing the safety contract
        """
        return {
            "version": self.VERSION,
            "safety_invariants": {
                "can_execute_real_write": False,
                "allow_real_write": False,
                "dry_run_only": True,
                "simulated_only": True,
                "requires_second_confirmation": True,
                "requires_runtime_down": True,
                "requires_clean_git_gate": True,
            },
            "decision_outcomes": [
                "CANDIDATE_DESIGN_READY",
                "MANUAL_REVIEW_REQUIRED",
                "BLOCK_CANDIDATE_DESIGN",
            ],
            "required_evidence": [
                "authorization_decision",
                "authorization_hash",
                "commits_pending_post_push",
                "staged_files",
                "memory_semantic_in_scope",
                "runtime_active",
                "faiss_write_enabled",
                "add_memory_enabled",
                "allows_auto_execute",
            ],
            "required_candidate_request": [
                "requested_by",
                "candidate_scope",
                "target_room",
                "operation_mode",
                "expects_no_write",
            ],
            "absolute_blockers": [
                "authorization_decision != AUTHORIZATION_PACKET_READY",
                "authorization_hash != 819be9f2",
                "commits_pending_post_push > 0",
                "staged_files not empty",
                "memory_semantic_in_scope = True",
                "runtime_active = True",
                "faiss_write_enabled = True",
                "add_memory_enabled = True",
                "allows_auto_execute = True",
                "operation_mode != design_only",
                "expects_no_write != True",
            ],
        }
    
    def block_design(self, reason: str) -> SemanticMemoryControlledRealWriteCandidateDesignReport:
        """Create a blocked candidate design.
        
        Args:
            reason: Reason for blocking
            
        Returns:
            Blocked candidate design report
        """
        return SemanticMemoryControlledRealWriteCandidateDesignReport(
            candidate_id=self.candidate_id,
            created_at_utc=datetime.now(timezone.utc).isoformat(),
            decision=SemanticMemoryCandidateDesignDecision.BLOCK_CANDIDATE_DESIGN,
            findings=[
                SemanticMemoryCandidateDesignFinding(
                    code="DESIGN_BLOCKED",
                    severity=SemanticMemoryCandidateDesignSeverity.BLOCKER,
                    message=reason,
                    evidence={"reason": reason}
                )
            ],
            blocker_count=1,
            warning_count=0,
            info_count=0,
            authorization_hash="BLOCKED",
            target_operation_type="none",
            scope={},
            candidate_payload={},
            expected_diff={},
            backup_plan={},
            rollback_plan={},
            preflight_checklist={},
            dry_run_verification={},
            second_confirmation={},
            hard_blockers=[],
            can_execute_real_write=False,
            allow_real_write=False,
            dry_run_only=True,
            simulated_only=True,
            requires_second_confirmation=True,
            requires_runtime_down=True,
            requires_clean_git_gate=True,
            metadata={"blocked": True, "reason": reason}
        )


def create_valid_evidence_template() -> dict:
    """Create a template with valid evidence for all checks.
    
    Returns:
        Dictionary with valid evidence template
    """
    return {
        "authorization_decision": "AUTHORIZATION_PACKET_READY",
        "authorization_hash": "819be9f2",
        "go_no_go_hash": "433c5842",
        "commits_pending_post_push": 0,
        "staged_files": [],
        "memory_semantic_in_scope": False,
        "runtime_active": False,
        "faiss_write_enabled": False,
        "add_memory_enabled": False,
        "allows_auto_execute": False,
        "can_execute_real_write": False,
        "allow_real_write": False,
        "dry_run_only": True,
        "simulated_only": True,
        "requires_second_confirmation": True,
        "security_validation_ok": True,
    }


def create_valid_candidate_request_template() -> dict:
    """Create a template with valid candidate request.
    
    Returns:
        Dictionary with valid candidate request template
    """
    return {
        "requested_by": "Cesar",
        "candidate_scope": "single_curated_fact_probe",
        "target_room": "migration_p2e_probe",
        "candidate_fact_key": "p2e_real_write_probe",
        "candidate_fact_value": "controlled candidate design only; not executed",
        "operation_mode": "design_only",
        "expects_no_runtime": True,
        "expects_no_write": True,
        "expects_second_confirmation": True,
    }


if __name__ == "__main__":
    # Demo: Show valid templates
    evidence_template = create_valid_evidence_template()
    request_template = create_valid_candidate_request_template()
    
    print("Valid Evidence Template:")
    print(json.dumps(evidence_template, indent=2))
    
    print("\nValid Candidate Request Template:")
    print(json.dumps(request_template, indent=2))
    
    # Demo: Build candidate design
    design_builder = SemanticMemoryControlledRealWriteCandidateDesign()
    report = design_builder.build_candidate_design_read_only(evidence_template, request_template)
    
    print(f"\nDecision: {report.decision.value}")
    print(f"Candidate ID: {report.candidate_id}")
    print(f"Authorization Hash: {report.authorization_hash}")
    print(f"Target Operation: {report.target_operation_type}")
    print(f"\nSafety Invariants:")
    print(f"  can_execute_real_write: {report.can_execute_real_write}")
    print(f"  allow_real_write: {report.allow_real_write}")
    print(f"  dry_run_only: {report.dry_run_only}")
    print(f"  simulated_only: {report.simulated_only}")
    print(f"  requires_second_confirmation: {report.requires_second_confirmation}")
    print(f"  requires_runtime_down: {report.requires_runtime_down}")
    print(f"  requires_clean_git_gate: {report.requires_clean_git_gate}")
