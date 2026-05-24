"""P2-E Commit 4D-GoNoGoReadinessChecklist: Final read-only GO/NO-GO checklist.

This module provides a read-only checklist that evaluates all evidence
from the 4D sequence before any controlled real write can be authorized.

IMPORTANT: This module NEVER executes real writes. It only emits decisions.
- allow_real_write is always False
- dry_run_only is always True
- can_execute_real_write is always False
- simulated_only is always True
- requires_human_approval is always True
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


class SemanticMemoryGoNoGoDecision(Enum):
    """GO/NO-GO decision outcomes."""
    GO_CANDIDATE_ONLY = "go_candidate_only"
    NO_GO = "no_go"
    MANUAL_REVIEW_REQUIRED = "manual_review_required"


class SemanticMemoryGoNoGoSeverity(Enum):
    """Severity levels for checklist findings."""
    INFO = "info"
    WARNING = "warning"
    BLOCKER = "blocker"


@dataclass
class SemanticMemoryGoNoGoFinding:
    """A single finding in the checklist."""
    code: str
    severity: SemanticMemoryGoNoGoSeverity
    message: str
    evidence: dict = field(default_factory=dict)


@dataclass
class SemanticMemoryGoNoGoChecklistReport:
    """Complete GO/NO-GO checklist report."""
    checklist_id: str
    created_at_utc: str
    decision: SemanticMemoryGoNoGoDecision
    findings: list[SemanticMemoryGoNoGoFinding]
    blocker_count: int
    warning_count: int
    info_count: int
    decision_gate_ok: bool
    evidence_contract_ok: bool
    adapter_ok: bool
    canary_ok: bool
    final_readiness_ok: bool
    backup_contract_ok: bool
    rollback_simulation_ok: bool
    security_validation_ok: bool
    git_state_ok: bool
    human_intent_ok: bool
    allow_real_write: bool = False
    dry_run_only: bool = True
    can_execute_real_write: bool = False
    simulated_only: bool = True
    requires_human_approval: bool = True
    readiness_score: float = 0.0
    checklist: dict = field(default_factory=dict)
    metadata: dict = field(default_factory=dict)


class SemanticMemoryGoNoGoReadinessChecklist:
    """GO/NO-GO readiness checklist for SemanticMemory controlled real write.
    
    This class evaluates all evidence from the 4D sequence and emits
    a GO/NO-GO decision. It NEVER executes real writes.
    
    Safety invariants:
    - allow_real_write is always False
    - dry_run_only is always True
    - can_execute_real_write is always False
    - simulated_only is always True
    - requires_human_approval is always True
    """
    
    VERSION = "4D-GoNoGo-v1.0.0"
    
    def __init__(self, repo_root: str | Path = ".") -> None:
        """Initialize the checklist evaluator.
        
        Args:
            repo_root: Path to the repository root
        """
        self.repo_root = Path(repo_root)
        self.checklist_id = str(uuid.uuid4())
    
    def evaluate_checklist_read_only(
        self,
        evidence: dict[str, Any] | None = None
    ) -> SemanticMemoryGoNoGoChecklistReport:
        """Evaluate the GO/NO-GO checklist based on evidence.
        
        This method is read-only and NEVER executes real writes.
        
        Args:
            evidence: Dictionary containing evidence from all 4D components
            
        Returns:
            SemanticMemoryGoNoGoChecklistReport with decision and findings
        """
        if evidence is None:
            evidence = {}
        
        findings: list[SemanticMemoryGoNoGoFinding] = []
        
        # Validate required evidence
        validation_findings = self.validate_required_evidence_read_only(evidence)
        findings.extend(validation_findings)
        
        # Check individual components
        decision_gate_ok = evidence.get("decision_gate_ok", False)
        evidence_contract_ok = evidence.get("evidence_contract_ok", False)
        adapter_ok = evidence.get("adapter_ok", False)
        canary_ok = evidence.get("canary_ok", False)
        final_readiness_ok = evidence.get("final_readiness_ok", False)
        backup_contract_ok = evidence.get("backup_contract_ok", False)
        rollback_simulation_ok = evidence.get("rollback_simulation_ok", False)
        security_validation_ok = evidence.get("security_validation_ok", False)
        git_state_ok = evidence.get("git_state_ok", False)
        human_intent_ok = evidence.get("human_intent_ok", False)
        
        # Count blockers and warnings
        blocker_count = sum(1 for f in findings if f.severity == SemanticMemoryGoNoGoSeverity.BLOCKER)
        warning_count = sum(1 for f in findings if f.severity == SemanticMemoryGoNoGoSeverity.WARNING)
        info_count = sum(1 for f in findings if f.severity == SemanticMemoryGoNoGoSeverity.INFO)
        
        # Calculate readiness score
        readiness_score = self.calculate_readiness_score(findings, evidence)
        
        # Determine decision
        decision = self._determine_decision(
            findings,
            evidence,
            decision_gate_ok,
            evidence_contract_ok,
            adapter_ok,
            canary_ok,
            final_readiness_ok,
            backup_contract_ok,
            rollback_simulation_ok,
            security_validation_ok,
            git_state_ok,
            human_intent_ok
        )
        
        # Build checklist summary
        checklist_summary = {
            "version": self.VERSION,
            "checks": {
                "decision_gate": decision_gate_ok,
                "evidence_contract": evidence_contract_ok,
                "adapter": adapter_ok,
                "canary": canary_ok,
                "final_readiness": final_readiness_ok,
                "backup_contract": backup_contract_ok,
                "rollback_simulation": rollback_simulation_ok,
                "security_validation": security_validation_ok,
                "git_state": git_state_ok,
                "human_intent": human_intent_ok,
            },
            "counts": {
                "blockers": blocker_count,
                "warnings": warning_count,
                "infos": info_count,
            },
        }
        
        return SemanticMemoryGoNoGoChecklistReport(
            checklist_id=self.checklist_id,
            created_at_utc=datetime.now(timezone.utc).isoformat(),
            decision=decision,
            findings=findings,
            blocker_count=blocker_count,
            warning_count=warning_count,
            info_count=info_count,
            decision_gate_ok=decision_gate_ok,
            evidence_contract_ok=evidence_contract_ok,
            adapter_ok=adapter_ok,
            canary_ok=canary_ok,
            final_readiness_ok=final_readiness_ok,
            backup_contract_ok=backup_contract_ok,
            rollback_simulation_ok=rollback_simulation_ok,
            security_validation_ok=security_validation_ok,
            git_state_ok=git_state_ok,
            human_intent_ok=human_intent_ok,
            allow_real_write=False,  # SAFETY: Never True
            dry_run_only=True,  # SAFETY: Always True
            can_execute_real_write=False,  # SAFETY: Never True
            simulated_only=True,  # SAFETY: Always True
            requires_human_approval=True,  # SAFETY: Always True
            readiness_score=readiness_score,
            checklist=checklist_summary,
            metadata={
                "version": self.VERSION,
                "repo_root": str(self.repo_root),
                "evidence_keys": list(evidence.keys()),
            }
        )
    
    def _determine_decision(
        self,
        findings: list[SemanticMemoryGoNoGoFinding],
        evidence: dict[str, Any],
        decision_gate_ok: bool,
        evidence_contract_ok: bool,
        adapter_ok: bool,
        canary_ok: bool,
        final_readiness_ok: bool,
        backup_contract_ok: bool,
        rollback_simulation_ok: bool,
        security_validation_ok: bool,
        git_state_ok: bool,
        human_intent_ok: bool
    ) -> SemanticMemoryGoNoGoDecision:
        """Determine the GO/NO-GO decision based on all evidence.
        
        Rules:
        1. If commits_pending_post_push > 0: NO_GO
        2. If staged_files not empty: NO_GO
        3. If memory_semantic_in_scope=True: NO_GO
        4. If runtime_active=True: NO_GO
        5. If faiss_write_enabled=True: NO_GO
        6. If add_memory_enabled=True: NO_GO
        7. If allows_auto_execute=True: NO_GO
        8. If any critical check fails: NO_GO
        9. If human_intent_ok=False: MANUAL_REVIEW_REQUIRED
        10. If all checks pass: GO_CANDIDATE_ONLY
        """
        # Check for absolute blockers first
        if evidence.get("commits_pending_post_push", 0) > 0:
            return SemanticMemoryGoNoGoDecision.NO_GO
        
        if evidence.get("staged_files", []):
            return SemanticMemoryGoNoGoDecision.NO_GO
        
        if evidence.get("memory_semantic_in_scope", False):
            return SemanticMemoryGoNoGoDecision.NO_GO
        
        if evidence.get("runtime_active", False):
            return SemanticMemoryGoNoGoDecision.NO_GO
        
        if evidence.get("faiss_write_enabled", False):
            return SemanticMemoryGoNoGoDecision.NO_GO
        
        if evidence.get("add_memory_enabled", False):
            return SemanticMemoryGoNoGoDecision.NO_GO
        
        if evidence.get("allows_auto_execute", False):
            return SemanticMemoryGoNoGoDecision.NO_GO
        
        if not evidence.get("allows_candidate_only", True):
            return SemanticMemoryGoNoGoDecision.MANUAL_REVIEW_REQUIRED
        
        # Check critical component failures
        critical_checks = [
            (decision_gate_ok, "decision_gate"),
            (evidence_contract_ok, "evidence_contract"),
            (adapter_ok, "adapter"),
            (canary_ok, "canary"),
            (final_readiness_ok, "final_readiness"),
            (backup_contract_ok, "backup_contract"),
            (rollback_simulation_ok, "rollback_simulation"),
            (security_validation_ok, "security_validation"),
            (git_state_ok, "git_state"),
        ]
        
        for check_ok, check_name in critical_checks:
            if not check_ok:
                return SemanticMemoryGoNoGoDecision.NO_GO
        
        # Check human intent last
        if not human_intent_ok:
            return SemanticMemoryGoNoGoDecision.MANUAL_REVIEW_REQUIRED
        
        # All checks passed
        return SemanticMemoryGoNoGoDecision.GO_CANDIDATE_ONLY
    
    def validate_required_evidence_read_only(
        self,
        evidence: dict[str, Any]
    ) -> list[SemanticMemoryGoNoGoFinding]:
        """Validate that all required evidence is present.
        
        Args:
            evidence: Evidence dictionary to validate
            
        Returns:
            List of findings from validation
        """
        findings: list[SemanticMemoryGoNoGoFinding] = []
        
        required_keys = [
            "decision_gate_ok",
            "evidence_contract_ok",
            "adapter_ok",
            "canary_ok",
            "final_readiness_ok",
            "backup_contract_ok",
            "rollback_simulation_ok",
            "security_validation_ok",
            "git_state_ok",
            "human_intent_ok",
        ]
        
        for key in required_keys:
            if key not in evidence:
                findings.append(SemanticMemoryGoNoGoFinding(
                    code=f"MISSING_{key.upper()}",
                    severity=SemanticMemoryGoNoGoSeverity.BLOCKER,
                    message=f"Required evidence key '{key}' is missing",
                    evidence={"key": key}
                ))
        
        # Validate specific constraints
        if evidence.get("commits_pending_post_push", 0) > 0:
            findings.append(SemanticMemoryGoNoGoFinding(
                code="PENDING_COMMITS",
                severity=SemanticMemoryGoNoGoSeverity.BLOCKER,
                message=f"{evidence['commits_pending_post_push']} commits pending post-push",
                evidence={"commits_pending": evidence["commits_pending_post_push"]}
            ))
        
        if evidence.get("staged_files", []):
            findings.append(SemanticMemoryGoNoGoFinding(
                code="STAGED_FILES",
                severity=SemanticMemoryGoNoGoSeverity.BLOCKER,
                message=f"{len(evidence['staged_files'])} files staged",
                evidence={"staged_count": len(evidence["staged_files"])}
            ))
        
        if evidence.get("memory_semantic_in_scope", False):
            findings.append(SemanticMemoryGoNoGoFinding(
                code="MEMORY_SEMANTIC_IN_SCOPE",
                severity=SemanticMemoryGoNoGoSeverity.BLOCKER,
                message="memory/semantic is in scope - cannot proceed",
                evidence={}
            ))
        
        if evidence.get("runtime_active", False):
            findings.append(SemanticMemoryGoNoGoFinding(
                code="RUNTIME_ACTIVE",
                severity=SemanticMemoryGoNoGoSeverity.BLOCKER,
                message="Runtime is active - cannot proceed",
                evidence={}
            ))
        
        if evidence.get("faiss_write_enabled", False):
            findings.append(SemanticMemoryGoNoGoFinding(
                code="FAISS_WRITE_ENABLED",
                severity=SemanticMemoryGoNoGoSeverity.BLOCKER,
                message="FAISS write is enabled - cannot proceed",
                evidence={}
            ))
        
        if evidence.get("add_memory_enabled", False):
            findings.append(SemanticMemoryGoNoGoFinding(
                code="ADD_MEMORY_ENABLED",
                severity=SemanticMemoryGoNoGoSeverity.BLOCKER,
                message="add_memory is enabled - cannot proceed",
                evidence={}
            ))
        
        if evidence.get("allows_auto_execute", False):
            findings.append(SemanticMemoryGoNoGoFinding(
                code="AUTO_EXECUTE_ALLOWED",
                severity=SemanticMemoryGoNoGoSeverity.BLOCKER,
                message="Auto-execution is allowed - cannot proceed",
                evidence={}
            ))
        
        if not evidence.get("allows_candidate_only", True):
            findings.append(SemanticMemoryGoNoGoFinding(
                code="CANDIDATE_ONLY_DISABLED",
                severity=SemanticMemoryGoNoGoSeverity.WARNING,
                message="Candidate-only mode is disabled",
                evidence={}
            ))
        
        return findings
    
    def calculate_readiness_score(
        self,
        findings: list[SemanticMemoryGoNoGoFinding],
        evidence: dict[str, Any]
    ) -> float:
        """Calculate a readiness score from 0.0 to 1.0.
        
        Args:
            findings: List of findings from validation
            evidence: Evidence dictionary
            
        Returns:
            Readiness score between 0.0 and 1.0
        """
        if not findings:
            return 1.0
        
        blocker_count = sum(1 for f in findings if f.severity == SemanticMemoryGoNoGoSeverity.BLOCKER)
        warning_count = sum(1 for f in findings if f.severity == SemanticMemoryGoNoGoSeverity.WARNING)
        
        if blocker_count > 0:
            return 0.0
        
        # Score decreases with warnings
        score = 1.0 - (warning_count * 0.1)
        return max(0.0, min(1.0, score))
    
    def summarize_contract(self) -> dict:
        """Summarize the contract enforced by this checklist.
        
        Returns:
            Dictionary summarizing the safety contract
        """
        return {
            "version": self.VERSION,
            "safety_invariants": {
                "allow_real_write": False,
                "dry_run_only": True,
                "can_execute_real_write": False,
                "simulated_only": True,
                "requires_human_approval": True,
            },
            "decision_outcomes": [
                "GO_CANDIDATE_ONLY",
                "NO_GO",
                "MANUAL_REVIEW_REQUIRED",
            ],
            "required_evidence": [
                "decision_gate_ok",
                "evidence_contract_ok",
                "adapter_ok",
                "canary_ok",
                "final_readiness_ok",
                "backup_contract_ok",
                "rollback_simulation_ok",
                "security_validation_ok",
                "git_state_ok",
                "human_intent_ok",
            ],
            "absolute_blockers": [
                "commits_pending_post_push > 0",
                "staged_files not empty",
                "memory_semantic_in_scope = True",
                "runtime_active = True",
                "faiss_write_enabled = True",
                "add_memory_enabled = True",
                "allows_auto_execute = True",
            ],
        }
    
    def block_checklist(self, reason: str) -> SemanticMemoryGoNoGoChecklistReport:
        """Create a blocked checklist report.
        
        Args:
            reason: Reason for blocking
            
        Returns:
            Blocked checklist report
        """
        return SemanticMemoryGoNoGoChecklistReport(
            checklist_id=self.checklist_id,
            created_at_utc=datetime.now(timezone.utc).isoformat(),
            decision=SemanticMemoryGoNoGoDecision.NO_GO,
            findings=[
                SemanticMemoryGoNoGoFinding(
                    code="CHECKLIST_BLOCKED",
                    severity=SemanticMemoryGoNoGoSeverity.BLOCKER,
                    message=reason,
                    evidence={"reason": reason}
                )
            ],
            blocker_count=1,
            warning_count=0,
            info_count=0,
            decision_gate_ok=False,
            evidence_contract_ok=False,
            adapter_ok=False,
            canary_ok=False,
            final_readiness_ok=False,
            backup_contract_ok=False,
            rollback_simulation_ok=False,
            security_validation_ok=False,
            git_state_ok=False,
            human_intent_ok=False,
            allow_real_write=False,
            dry_run_only=True,
            can_execute_real_write=False,
            simulated_only=True,
            requires_human_approval=True,
            readiness_score=0.0,
            checklist={"blocked": True, "reason": reason},
            metadata={"blocked": True, "reason": reason}
        )


def create_valid_evidence_template() -> dict:
    """Create a template with valid evidence for all checks.
    
    Returns:
        Dictionary with valid evidence template
    """
    return {
        "decision_gate_ok": True,
        "evidence_contract_ok": True,
        "adapter_ok": True,
        "canary_ok": True,
        "final_readiness_ok": True,
        "backup_contract_ok": True,
        "rollback_simulation_ok": True,
        "security_validation_ok": True,
        "git_state_ok": True,
        "human_intent_ok": True,
        "commits_pending_post_push": 0,
        "staged_files": [],
        "memory_semantic_in_scope": False,
        "runtime_active": False,
        "faiss_write_enabled": False,
        "add_memory_enabled": False,
        "allows_auto_execute": False,
        "allows_candidate_only": True,
    }


if __name__ == "__main__":
    # Demo: Show valid evidence template
    template = create_valid_evidence_template()
    print("Valid Evidence Template:")
    print(json.dumps(template, indent=2))
    
    # Demo: Evaluate with valid evidence
    checklist = SemanticMemoryGoNoGoReadinessChecklist()
    report = checklist.evaluate_checklist_read_only(template)
    print(f"\nDecision: {report.decision.value}")
    print(f"Readiness Score: {report.readiness_score}")
    print(f"Findings: {len(report.findings)} (Blockers: {report.blocker_count})")
    print(f"\nSafety Invariants:")
    print(f"  allow_real_write: {report.allow_real_write}")
    print(f"  dry_run_only: {report.dry_run_only}")
    print(f"  can_execute_real_write: {report.can_execute_real_write}")
    print(f"  simulated_only: {report.simulated_only}")
    print(f"  requires_human_approval: {report.requires_human_approval}")
