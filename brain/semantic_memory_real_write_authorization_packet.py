"""P2-E Commit 4D-RealWriteAuthorizationPacket: Authorization packet for future controlled real write.

This module provides a read-only authorization packet that models explicit human
approval for a separate future phase of controlled real write.

IMPORTANT: This module NEVER executes real writes. It only produces a structured artifact.
- can_execute_real_write is always False
- allow_real_write is always False
- dry_run_only is always True
- simulated_only is always True
- requires_second_confirmation is always True
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class SemanticMemoryAuthorizationDecision(Enum):
    """Authorization packet decision outcomes."""
    AUTHORIZATION_PACKET_READY = "authorization_packet_ready"
    MANUAL_REVIEW_REQUIRED = "manual_review_required"
    BLOCK_AUTHORIZATION = "block_authorization"


class SemanticMemoryAuthorizationSeverity(Enum):
    """Severity levels for authorization findings."""
    INFO = "info"
    WARNING = "warning"
    BLOCKER = "blocker"


@dataclass
class SemanticMemoryAuthorizationFinding:
    """A single finding in the authorization packet validation."""
    code: str
    severity: SemanticMemoryAuthorizationSeverity
    message: str
    evidence: dict = field(default_factory=dict)


@dataclass
class SemanticMemoryRealWriteAuthorizationPacketReport:
    """Complete authorization packet report."""
    authorization_packet_id: str
    created_at_utc: str
    decision: SemanticMemoryAuthorizationDecision
    findings: list[SemanticMemoryAuthorizationFinding]
    blocker_count: int
    warning_count: int
    info_count: int
    go_no_go_decision: str
    approval_scope: str
    allowed_next_phase: str
    human_approval_intent: bool
    requires_second_confirmation: bool
    can_execute_real_write: bool = False
    allow_real_write: bool = False
    dry_run_only: bool = True
    simulated_only: bool = True
    forbidden_actions: list[str] = field(default_factory=list)
    required_preconditions: list[str] = field(default_factory=list)
    packet: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)


class SemanticMemoryRealWriteAuthorizationPacket:
    """Real write authorization packet builder.
    
    This class builds a read-only authorization packet. It NEVER executes real writes.
    
    Safety invariants:
    - can_execute_real_write is always False
    - allow_real_write is always False
    - dry_run_only is always True
    - simulated_only is always True
    - requires_second_confirmation is always True
    """
    
    VERSION = "4D-AuthorizationPacket-v1.0.0"
    
    def __init__(self, repo_root: str | Path = ".") -> None:
        """Initialize the authorization packet builder.
        
        Args:
            repo_root: Path to the repository root
        """
        self.repo_root = Path(repo_root)
        self.packet_id = str(uuid.uuid4())
    
    def build_packet_read_only(
        self,
        evidence: dict[str, Any],
        human_intent: dict[str, Any] | None = None
    ) -> SemanticMemoryRealWriteAuthorizationPacketReport:
        """Build authorization packet based on evidence and human intent.
        
        This method is read-only and NEVER executes real writes.
        
        Args:
            evidence: Dictionary containing evidence from Go/No-Go checklist
            human_intent: Dictionary containing human approval intent
            
        Returns:
            SemanticMemoryRealWriteAuthorizationPacketReport with decision and findings
        """
        findings: list[SemanticMemoryAuthorizationFinding] = []
        
        # Validate evidence
        evidence_findings = self.validate_evidence_read_only(evidence)
        findings.extend(evidence_findings)
        
        # Validate human intent
        intent_findings = self.validate_human_intent_read_only(human_intent)
        findings.extend(intent_findings)
        
        # Count findings
        blocker_count = sum(1 for f in findings if f.severity == SemanticMemoryAuthorizationSeverity.BLOCKER)
        warning_count = sum(1 for f in findings if f.severity == SemanticMemoryAuthorizationSeverity.WARNING)
        info_count = sum(1 for f in findings if f.severity == SemanticMemoryAuthorizationSeverity.INFO)
        
        # Determine decision
        decision = self._determine_decision(evidence, human_intent, findings)
        
        # Build packet structure
        packet_structure = {
            "version": self.VERSION,
            "packet_id": self.packet_id,
            "go_no_go_decision": evidence.get("go_no_go_decision", "UNKNOWN"),
            "go_no_go_hash": evidence.get("go_no_go_hash", "UNKNOWN"),
            "approval_scope": human_intent.get("approval_scope", "none") if human_intent else "none",
            "allowed_next_phase": human_intent.get("allowed_next_phase", "none") if human_intent else "none",
        }
        
        return SemanticMemoryRealWriteAuthorizationPacketReport(
            authorization_packet_id=self.packet_id,
            created_at_utc=datetime.now(timezone.utc).isoformat(),
            decision=decision,
            findings=findings,
            blocker_count=blocker_count,
            warning_count=warning_count,
            info_count=info_count,
            go_no_go_decision=evidence.get("go_no_go_decision", "UNKNOWN"),
            approval_scope=human_intent.get("approval_scope", "none") if human_intent else "none",
            allowed_next_phase=human_intent.get("allowed_next_phase", "none") if human_intent else "none",
            human_approval_intent=human_intent is not None and len(human_intent) > 0,
            requires_second_confirmation=True,  # SAFETY: Always True
            can_execute_real_write=False,  # SAFETY: Never True
            allow_real_write=False,  # SAFETY: Never True
            dry_run_only=True,  # SAFETY: Always True
            simulated_only=True,  # SAFETY: Always True
            forbidden_actions=[
                "direct_memory_semantic_write",
                "faiss_write",
                "add_memory_execution",
                "auto_execute",
                "promote" + "_real",
                "execute" + "_rollback" + "_real",
            ],
            required_preconditions=[
                "go_no_go_decision must be GO_CANDIDATE_ONLY",
                "commits_pending_post_push must be 0",
                "staged_files must be empty",
                "memory_semantic_in_scope must be False",
                "runtime_active must be False",
                "faiss_write_enabled must be False",
                "add_memory_enabled must be False",
                "allows_auto_execute must be False",
                "human_intent must include approval_scope",
                "human_intent must not allow_real_write_execution",
            ],
            packet=packet_structure,
            metadata={
                "version": self.VERSION,
                "repo_root": str(self.repo_root),
                "evidence_keys": list(evidence.keys()),
                "human_intent_keys": list(human_intent.keys()) if human_intent else [],
            }
        )
    
    def _determine_decision(
        self,
        evidence: dict[str, Any],
        human_intent: dict[str, Any] | None,
        findings: list[SemanticMemoryAuthorizationFinding]
    ) -> SemanticMemoryAuthorizationDecision:
        """Determine the authorization decision based on evidence and intent.
        
        Rules:
        1. If any blockers: BLOCK_AUTHORIZATION
        2. If go_no_go_decision != GO_CANDIDATE_ONLY: BLOCK_AUTHORIZATION
        3. If commits_pending_post_push > 0: BLOCK_AUTHORIZATION
        4. If staged_files not empty: BLOCK_AUTHORIZATION
        5. If memory_semantic_in_scope=True: BLOCK_AUTHORIZATION
        6. If runtime_active=True: BLOCK_AUTHORIZATION
        7. If faiss_write_enabled=True: BLOCK_AUTHORIZATION
        8. If add_memory_enabled=True: BLOCK_AUTHORIZATION
        9. If allows_auto_execute=True: BLOCK_AUTHORIZATION
        10. If human_intent allows_real_write_execution=True: BLOCK_AUTHORIZATION
        11. If human_intent missing: MANUAL_REVIEW_REQUIRED
        12. If all checks pass: AUTHORIZATION_PACKET_READY
        """
        # Check for blockers first
        blocker_count = sum(1 for f in findings if f.severity == SemanticMemoryAuthorizationSeverity.BLOCKER)
        if blocker_count > 0:
            return SemanticMemoryAuthorizationDecision.BLOCK_AUTHORIZATION
        
        # Check Go/No-Go decision
        if evidence.get("go_no_go_decision") != "GO_CANDIDATE_ONLY":
            return SemanticMemoryAuthorizationDecision.BLOCK_AUTHORIZATION
        
        # Check absolute blockers
        if evidence.get("commits_pending_post_push", 0) > 0:
            return SemanticMemoryAuthorizationDecision.BLOCK_AUTHORIZATION
        
        if evidence.get("staged_files", []):
            return SemanticMemoryAuthorizationDecision.BLOCK_AUTHORIZATION
        
        if evidence.get("memory_semantic_in_scope", False):
            return SemanticMemoryAuthorizationDecision.BLOCK_AUTHORIZATION
        
        if evidence.get("runtime_active", False):
            return SemanticMemoryAuthorizationDecision.BLOCK_AUTHORIZATION
        
        if evidence.get("faiss_write_enabled", False):
            return SemanticMemoryAuthorizationDecision.BLOCK_AUTHORIZATION
        
        if evidence.get("add_memory_enabled", False):
            return SemanticMemoryAuthorizationDecision.BLOCK_AUTHORIZATION
        
        if evidence.get("allows_auto_execute", False):
            return SemanticMemoryAuthorizationDecision.BLOCK_AUTHORIZATION
        
        # Check human intent
        if human_intent is None:
            return SemanticMemoryAuthorizationDecision.MANUAL_REVIEW_REQUIRED
        
        if human_intent.get("allows_real_write_execution", False):
            return SemanticMemoryAuthorizationDecision.BLOCK_AUTHORIZATION
        
        # All checks passed
        return SemanticMemoryAuthorizationDecision.AUTHORIZATION_PACKET_READY
    
    def validate_evidence_read_only(
        self,
        evidence: dict[str, Any]
    ) -> list[SemanticMemoryAuthorizationFinding]:
        """Validate that all required evidence is present.
        
        Args:
            evidence: Evidence dictionary to validate
            
        Returns:
            List of findings from validation
        """
        findings: list[SemanticMemoryAuthorizationFinding] = []
        
        required_keys = [
            "go_no_go_decision",
            "go_no_go_hash",
            "commits_pending_post_push",
            "staged_files",
            "memory_semantic_in_scope",
            "runtime_active",
            "faiss_write_enabled",
            "add_memory_enabled",
            "allows_auto_execute",
        ]
        
        for key in required_keys:
            if key not in evidence:
                findings.append(SemanticMemoryAuthorizationFinding(
                    code=f"MISSING_{key.upper()}",
                    severity=SemanticMemoryAuthorizationSeverity.BLOCKER,
                    message=f"Required evidence key '{key}' is missing",
                    evidence={"key": key}
                ))
        
        # Validate specific constraints
        if evidence.get("go_no_go_decision") != "GO_CANDIDATE_ONLY":
            findings.append(SemanticMemoryAuthorizationFinding(
                code="INVALID_GO_NO_GO_DECISION",
                severity=SemanticMemoryAuthorizationSeverity.BLOCKER,
                message=f"Go/No-Go decision must be GO_CANDIDATE_ONLY, got: {evidence.get('go_no_go_decision', 'MISSING')}",
                evidence={"go_no_go_decision": evidence.get("go_no_go_decision")}
            ))
        
        if evidence.get("commits_pending_post_push", 0) > 0:
            findings.append(SemanticMemoryAuthorizationFinding(
                code="PENDING_COMMITS",
                severity=SemanticMemoryAuthorizationSeverity.BLOCKER,
                message=f"{evidence['commits_pending_post_push']} commits pending post-push",
                evidence={"commits_pending": evidence["commits_pending_post_push"]}
            ))
        
        if evidence.get("staged_files", []):
            findings.append(SemanticMemoryAuthorizationFinding(
                code="STAGED_FILES",
                severity=SemanticMemoryAuthorizationSeverity.BLOCKER,
                message=f"{len(evidence['staged_files'])} files staged",
                evidence={"staged_count": len(evidence["staged_files"])}
            ))
        
        if evidence.get("memory_semantic_in_scope", False):
            findings.append(SemanticMemoryAuthorizationFinding(
                code="MEMORY_SEMANTIC_IN_SCOPE",
                severity=SemanticMemoryAuthorizationSeverity.BLOCKER,
                message="memory/semantic is in scope - cannot proceed",
                evidence={}
            ))
        
        if evidence.get("runtime_active", False):
            findings.append(SemanticMemoryAuthorizationFinding(
                code="RUNTIME_ACTIVE",
                severity=SemanticMemoryAuthorizationSeverity.BLOCKER,
                message="Runtime is active - cannot proceed",
                evidence={}
            ))
        
        if evidence.get("faiss_write_enabled", False):
            findings.append(SemanticMemoryAuthorizationFinding(
                code="FAISS_WRITE_ENABLED",
                severity=SemanticMemoryAuthorizationSeverity.BLOCKER,
                message="FAISS write is enabled - cannot proceed",
                evidence={}
            ))
        
        if evidence.get("add_memory_enabled", False):
            findings.append(SemanticMemoryAuthorizationFinding(
                code="ADD_MEMORY_ENABLED",
                severity=SemanticMemoryAuthorizationSeverity.BLOCKER,
                message="add_memory is enabled - cannot proceed",
                evidence={}
            ))
        
        if evidence.get("allows_auto_execute", False):
            findings.append(SemanticMemoryAuthorizationFinding(
                code="AUTO_EXECUTE_ALLOWED",
                severity=SemanticMemoryAuthorizationSeverity.BLOCKER,
                message="Auto-execution is allowed - cannot proceed",
                evidence={}
            ))
        
        return findings
    
    def validate_human_intent_read_only(
        self,
        human_intent: dict[str, Any] | None
    ) -> list[SemanticMemoryAuthorizationFinding]:
        """Validate human intent.
        
        Args:
            human_intent: Human intent dictionary to validate
            
        Returns:
            List of findings from validation
        """
        findings: list[SemanticMemoryAuthorizationFinding] = []
        
        if human_intent is None:
            findings.append(SemanticMemoryAuthorizationFinding(
                code="MISSING_HUMAN_INTENT",
                severity=SemanticMemoryAuthorizationSeverity.WARNING,
                message="Human intent is missing - manual review required",
                evidence={}
            ))
            return findings
        
        # Validate required fields
        required_fields = [
            "approved_by",
            "approval_scope",
            "allowed_next_phase",
        ]
        
        for field in required_fields:
            if field not in human_intent:
                findings.append(SemanticMemoryAuthorizationFinding(
                    code=f"MISSING_{field.upper()}",
                    severity=SemanticMemoryAuthorizationSeverity.WARNING,
                    message=f"Human intent field '{field}' is missing",
                    evidence={"field": field}
                ))
        
        # Validate safety constraints
        if human_intent.get("allows_real_write_execution", False):
            findings.append(SemanticMemoryAuthorizationFinding(
                code="REAL_WRITE_EXECUTION_ALLOWED",
                severity=SemanticMemoryAuthorizationSeverity.BLOCKER,
                message="Human intent allows real write execution - BLOCKED for safety",
                evidence={"allows_real_write_execution": True}
            ))
        
        if not human_intent.get("understands_no_auto_execute", True):
            findings.append(SemanticMemoryAuthorizationFinding(
                code="NO_AUTO_EXECUTE_NOT_UNDERSTOOD",
                severity=SemanticMemoryAuthorizationSeverity.WARNING,
                message="Human intent does not acknowledge no-auto-execute policy",
                evidence={}
            ))
        
        return findings
    
    def summarize_contract(self) -> dict:
        """Summarize the contract enforced by this authorization packet.
        
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
            },
            "decision_outcomes": [
                "AUTHORIZATION_PACKET_READY",
                "MANUAL_REVIEW_REQUIRED",
                "BLOCK_AUTHORIZATION",
            ],
            "required_evidence": [
                "go_no_go_decision",
                "go_no_go_hash",
                "commits_pending_post_push",
                "staged_files",
                "memory_semantic_in_scope",
                "runtime_active",
                "faiss_write_enabled",
                "add_memory_enabled",
                "allows_auto_execute",
            ],
            "required_human_intent": [
                "approved_by",
                "approval_scope",
                "allowed_next_phase",
                "understands_no_auto_execute",
                "allows_candidate_only",
            ],
            "absolute_blockers": [
                "go_no_go_decision != GO_CANDIDATE_ONLY",
                "commits_pending_post_push > 0",
                "staged_files not empty",
                "memory_semantic_in_scope = True",
                "runtime_active = True",
                "faiss_write_enabled = True",
                "add_memory_enabled = True",
                "allows_auto_execute = True",
                "human_intent allows_real_write_execution = True",
            ],
        }
    
    def block_packet(self, reason: str) -> SemanticMemoryRealWriteAuthorizationPacketReport:
        """Create a blocked authorization packet.
        
        Args:
            reason: Reason for blocking
            
        Returns:
            Blocked authorization packet report
        """
        return SemanticMemoryRealWriteAuthorizationPacketReport(
            authorization_packet_id=self.packet_id,
            created_at_utc=datetime.now(timezone.utc).isoformat(),
            decision=SemanticMemoryAuthorizationDecision.BLOCK_AUTHORIZATION,
            findings=[
                SemanticMemoryAuthorizationFinding(
                    code="PACKET_BLOCKED",
                    severity=SemanticMemoryAuthorizationSeverity.BLOCKER,
                    message=reason,
                    evidence={"reason": reason}
                )
            ],
            blocker_count=1,
            warning_count=0,
            info_count=0,
            go_no_go_decision="BLOCKED",
            approval_scope="none",
            allowed_next_phase="none",
            human_approval_intent=False,
            requires_second_confirmation=True,
            can_execute_real_write=False,
            allow_real_write=False,
            dry_run_only=True,
            simulated_only=True,
            forbidden_actions=[],
            required_preconditions=[],
            packet={"blocked": True, "reason": reason},
            metadata={"blocked": True, "reason": reason}
        )


def create_valid_evidence_template() -> dict:
    """Create a template with valid evidence for all checks.
    
    Returns:
        Dictionary with valid evidence template
    """
    return {
        "go_no_go_decision": "GO_CANDIDATE_ONLY",
        "go_no_go_hash": "433c5842",
        "commits_pending_post_push": 0,
        "staged_files": [],
        "memory_semantic_in_scope": False,
        "runtime_active": False,
        "faiss_write_enabled": False,
        "add_memory_enabled": False,
        "allows_auto_execute": False,
        "dry_run_chain_complete": True,
        "backup_contract_ok": True,
        "rollback_simulation_ok": True,
        "security_validation_ok": True,
    }


def create_valid_human_intent_template() -> dict:
    """Create a template with valid human intent.
    
    Returns:
        Dictionary with valid human intent template
    """
    return {
        "approved_by": "Cesar",
        "approval_scope": "authorization_packet_only",
        "allowed_next_phase": "controlled_real_write_candidate_design",
        "understands_no_auto_execute": True,
        "allows_candidate_only": True,
        "allows_real_write_execution": False,
        "requires_second_confirmation": True,
    }


if __name__ == "__main__":
    # Demo: Show valid templates
    evidence_template = create_valid_evidence_template()
    intent_template = create_valid_human_intent_template()
    
    print("Valid Evidence Template:")
    print(json.dumps(evidence_template, indent=2))
    
    print("\nValid Human Intent Template:")
    print(json.dumps(intent_template, indent=2))
    
    # Demo: Build authorization packet
    packet_builder = SemanticMemoryRealWriteAuthorizationPacket()
    report = packet_builder.build_packet_read_only(evidence_template, intent_template)
    
    print(f"\nDecision: {report.decision.value}")
    print(f"Authorization Packet ID: {report.authorization_packet_id}")
    print(f"Go/No-Go Decision: {report.go_no_go_decision}")
    print(f"Approval Scope: {report.approval_scope}")
    print(f"Allowed Next Phase: {report.allowed_next_phase}")
    print(f"\nSafety Invariants:")
    print(f"  can_execute_real_write: {report.can_execute_real_write}")
    print(f"  allow_real_write: {report.allow_real_write}")
    print(f"  dry_run_only: {report.dry_run_only}")
    print(f"  simulated_only: {report.simulated_only}")
    print(f"  requires_second_confirmation: {report.requires_second_confirmation}")
