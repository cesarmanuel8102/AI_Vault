"""
P2-E Commit 4D-DecisionGateEvidenceAdapter: Read-only adapter to integrate DecisionGate with ExternalEvidence

This module creates a bridge between SemanticMemoryExternalEvidenceContract and 
SemanticMemoryRealWriteDecisionGate, allowing the decision gate to consume validated
external evidence bundles.

REGLAS DURAS:
- Only validates provided objects/dicts
- NO subprocess execution
- NO file system writes
- NO runtime activation
- NO FAISS import
- NO semantic_memory_bridge import
- NO add_memory calls
- allow_real_write=False ALWAYS
- dry_run_only=True ALWAYS
- can_execute_real_write=False ALWAYS
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid

# Import required modules
from brain.semantic_memory_external_evidence_contract import (
    SemanticMemoryExternalEvidenceContract,
    SemanticMemoryEvidenceStatus,
    SemanticMemoryEvidenceSeverity,
    SemanticMemoryEvidenceFinding,
)
from brain.semantic_memory_real_write_decision_gate import (
    SemanticMemoryDecision,
    SemanticMemoryDecisionReasonCode,
    SemanticMemoryDecisionSeverity,
)


class SemanticMemoryEvidenceAdapterStatus(str, Enum):
    """Estados posibles del adaptador."""
    ACCEPTED_FOR_GATE = "ACCEPTED_FOR_GATE"
    REJECTED_BY_EVIDENCE = "REJECTED_BY_EVIDENCE"
    PARTIAL_EVIDENCE = "PARTIAL_EVIDENCE"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"


@dataclass
class SemanticMemoryEvidenceAdapterFinding:
    """Un finding del adaptador."""
    code: str
    severity: str
    message: str
    evidence: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SemanticMemoryDecisionGateEvidenceAdapterReport:
    """
    Reporte del adaptador de evidencia para DecisionGate.
    """
    adapter_id: str
    created_at_utc: str
    status: SemanticMemoryEvidenceAdapterStatus
    evidence_status: str
    decision: str
    findings: List[SemanticMemoryEvidenceAdapterFinding]
    blocker_count: int
    warning_count: int
    info_count: int
    git_state_verified: bool
    risk_summary_verified: bool
    security_validation_verified: bool
    tests_verified: bool
    smokes_verified: bool
    accepted_for_decision_gate: bool
    allow_real_write: bool = False
    dry_run_only: bool = True
    can_execute_real_write: bool = False
    requires_manual_review: bool = True
    warnings: List[str] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "adapter_id": self.adapter_id,
            "created_at_utc": self.created_at_utc,
            "status": self.status.value,
            "evidence_status": self.evidence_status,
            "decision": self.decision,
            "findings": [f.__dict__ for f in self.findings],
            "blocker_count": self.blocker_count,
            "warning_count": self.warning_count,
            "info_count": self.info_count,
            "git_state_verified": self.git_state_verified,
            "risk_summary_verified": self.risk_summary_verified,
            "security_validation_verified": self.security_validation_verified,
            "tests_verified": self.tests_verified,
            "smokes_verified": self.smokes_verified,
            "accepted_for_decision_gate": self.accepted_for_decision_gate,
            "allow_real_write": self.allow_real_write,
            "dry_run_only": self.dry_run_only,
            "can_execute_real_write": self.can_execute_real_write,
            "requires_manual_review": self.requires_manual_review,
            "warnings": self.warnings,
            "blockers": self.blockers,
            "metadata": self.metadata,
        }


class SemanticMemoryDecisionGateEvidenceAdapter:
    """
    Adaptador read-only para integrar EvidenceContract con DecisionGate.
    
    Este adaptador:
    1. Recibe bundles de evidencia externa
    2. Los valida usando SemanticMemoryExternalEvidenceContract
    3. Traduce evidencia aceptada a decisiones del gate
    4. Mantiene siempre allow_real_write=False
    """
    
    def __init__(self, repo_root: str | Path = "."):
        """
        Inicializar adaptador.
        
        Args:
            repo_root: Raíz del repositorio
        """
        self._repo_root = Path(repo_root).resolve()
        self._adapter_id = f"adapter_{uuid.uuid4().hex[:16]}"
        self._created_at = datetime.now(timezone.utc).isoformat()
        
        # Initialize evidence contract
        self._evidence_contract = SemanticMemoryExternalEvidenceContract(
            repo_root=self._repo_root
        )
    
    def evaluate_with_evidence_read_only(
        self,
        bundle: Dict[str, Any],
    ) -> SemanticMemoryDecisionGateEvidenceAdapterReport:
        """
        Evaluar bundle de evidencia y producir decisión.
        
        Args:
            bundle: Bundle de evidencia externa
            
        Returns:
            SemanticMemoryDecisionGateEvidenceAdapterReport
        """
        findings: List[SemanticMemoryEvidenceAdapterFinding] = []
        
        # Step 1: Validate evidence using contract
        evidence_report = self._evidence_contract.validate_bundle_read_only(bundle)
        
        # Step 2: Map evidence status to adapter status and decision
        adapter_status, decision = self._map_evidence_to_adapter(
            evidence_report.status
        )
        
        # Step 3: Convert evidence findings to adapter findings
        for ef in evidence_report.findings:
            findings.append(SemanticMemoryEvidenceAdapterFinding(
                code=ef.code,
                severity=ef.severity.value,
                message=ef.message,
                evidence=ef.evidence,
            ))
        
        # Step 4: Add adapter-specific findings
        if evidence_report.status == SemanticMemoryEvidenceStatus.ACCEPTED:
            findings.append(SemanticMemoryEvidenceAdapterFinding(
                code="EVIDENCE_ACCEPTED_FOR_GATE",
                severity=SemanticMemoryEvidenceSeverity.INFO.value,
                message="External evidence accepted for decision gate",
                evidence={"evidence_status": evidence_report.status.value},
            ))
        elif evidence_report.status == SemanticMemoryEvidenceStatus.PARTIAL:
            findings.append(SemanticMemoryEvidenceAdapterFinding(
                code="EVIDENCE_PARTIAL",
                severity=SemanticMemoryEvidenceSeverity.WARNING.value,
                message="External evidence is partial, manual review required",
                evidence={"evidence_status": evidence_report.status.value},
            ))
        else:
            findings.append(SemanticMemoryEvidenceAdapterFinding(
                code="EVIDENCE_REJECTED_OR_BLOCKED",
                severity=SemanticMemoryEvidenceSeverity.BLOCKER.value,
                message="External evidence rejected or blocked",
                evidence={"evidence_status": evidence_report.status.value},
            ))
        
        # Step 5: Calculate counts
        blocker_count = sum(1 for f in findings if f.severity == SemanticMemoryEvidenceSeverity.BLOCKER.value)
        warning_count = sum(1 for f in findings if f.severity == SemanticMemoryEvidenceSeverity.WARNING.value)
        info_count = sum(1 for f in findings if f.severity == SemanticMemoryEvidenceSeverity.INFO.value)
        
        # Step 6: Determine if accepted for decision gate
        accepted = (
            evidence_report.status == SemanticMemoryEvidenceStatus.ACCEPTED
            and adapter_status == SemanticMemoryEvidenceAdapterStatus.ACCEPTED_FOR_GATE
            and decision == SemanticMemoryDecision.ALLOW_MANUAL_REAL_WRITE_CANDIDATE.value
        )
        
        # Step 7: Build blockers and warnings
        blockers = [
            "P2-E Commit 4D-DecisionGateEvidenceAdapter: Adapter activo",
            "allow_real_write=False por diseño",
        ]
        if blocker_count > 0:
            blockers.append(f"{blocker_count} blockers encontrados")
        
        warnings_list = [f.message for f in findings if f.severity == SemanticMemoryEvidenceSeverity.WARNING.value]
        
        return SemanticMemoryDecisionGateEvidenceAdapterReport(
            adapter_id=self._adapter_id,
            created_at_utc=self._created_at,
            status=adapter_status,
            evidence_status=evidence_report.status.value,
            decision=decision,
            findings=findings,
            blocker_count=blocker_count,
            warning_count=warning_count,
            info_count=info_count,
            git_state_verified=evidence_report.git_state_verified,
            risk_summary_verified=evidence_report.risk_summary_verified,
            security_validation_verified=evidence_report.security_validation_verified,
            tests_verified=evidence_report.tests_verified,
            smokes_verified=evidence_report.smokes_verified,
            accepted_for_decision_gate=accepted,
            allow_real_write=False,  # SIEMPRE False
            dry_run_only=True,  # SIEMPRE True
            can_execute_real_write=False,  # SIEMPRE False
            requires_manual_review=not accepted,
            warnings=warnings_list,
            blockers=blockers,
            metadata={
                "adapter_version": "P2-E-Commit-4D-DecisionGateEvidenceAdapter",
                "bundle_id": bundle.get("bundle_id", "unknown"),
                "producer": bundle.get("producer", "unknown"),
            },
        )
    
    def _map_evidence_to_adapter(
        self,
        evidence_status: SemanticMemoryEvidenceStatus,
    ) -> tuple[SemanticMemoryEvidenceAdapterStatus, str]:
        """
        Mapear estado de evidencia a estado del adaptador y decisión.
        
        Args:
            evidence_status: Estado de la evidencia
            
        Returns:
            Tupla (adapter_status, decision)
        """
        mapping = {
            SemanticMemoryEvidenceStatus.ACCEPTED: (
                SemanticMemoryEvidenceAdapterStatus.ACCEPTED_FOR_GATE,
                SemanticMemoryDecision.ALLOW_MANUAL_REAL_WRITE_CANDIDATE.value,
            ),
            SemanticMemoryEvidenceStatus.PARTIAL: (
                SemanticMemoryEvidenceAdapterStatus.PARTIAL_EVIDENCE,
                SemanticMemoryDecision.CANARY_NOOP_ONLY.value,
            ),
            SemanticMemoryEvidenceStatus.REJECTED: (
                SemanticMemoryEvidenceAdapterStatus.REJECTED_BY_EVIDENCE,
                SemanticMemoryDecision.BLOCK_REAL_WRITE.value,
            ),
            SemanticMemoryEvidenceStatus.MISSING: (
                SemanticMemoryEvidenceAdapterStatus.BLOCKED,
                SemanticMemoryDecision.BLOCK_REAL_WRITE.value,
            ),
            SemanticMemoryEvidenceStatus.UNKNOWN: (
                SemanticMemoryEvidenceAdapterStatus.UNKNOWN,
                SemanticMemoryDecision.BLOCK_REAL_WRITE.value,
            ),
        }
        
        return mapping.get(
            evidence_status,
            (SemanticMemoryEvidenceAdapterStatus.BLOCKED, SemanticMemoryDecision.BLOCK_REAL_WRITE.value)
        )
    
    def summarize_contract(self) -> Dict[str, Any]:
        """
        Resumir el contrato del adaptador.
        
        Returns:
            Dict con información del contrato
        """
        return {
            "contract_version": "P2-E-Commit-4D-DecisionGateEvidenceAdapter",
            "contract_type": "DecisionGateEvidenceAdapter",
            "allow_real_write": False,
            "dry_run_only": True,
            "can_execute_real_write": False,
            "requires_manual_review": True,
            "decision_mapping": {
                "ACCEPTED": "ALLOW_MANUAL_REAL_WRITE_CANDIDATE",
                "PARTIAL": "CANARY_NOOP_ONLY",
                "REJECTED": "BLOCK_REAL_WRITE",
                "MISSING": "BLOCK_REAL_WRITE",
                "UNKNOWN": "BLOCK_REAL_WRITE",
            },
            "limitations": [
                "NO subprocess execution",
                "NO file system writes",
                "NO runtime activation",
                "NO FAISS import",
                "NO semantic_memory_bridge import",
                "Evidence-to-decision mapping only",
            ],
            "next_step": "Provide validated evidence bundle",
        }
    
    def block_adapter(
        self,
        reason: str = "Adapter blocked",
    ) -> SemanticMemoryDecisionGateEvidenceAdapterReport:
        """
        Bloquear adaptador explícitamente.
        
        Args:
            reason: Razón del bloqueo
            
        Returns:
            SemanticMemoryDecisionGateEvidenceAdapterReport bloqueado
        """
        return SemanticMemoryDecisionGateEvidenceAdapterReport(
            adapter_id=f"blocked_{self._adapter_id}",
            created_at_utc=datetime.now(timezone.utc).isoformat(),
            status=SemanticMemoryEvidenceAdapterStatus.BLOCKED,
            evidence_status=SemanticMemoryEvidenceStatus.REJECTED.value,
            decision=SemanticMemoryDecision.BLOCK_REAL_WRITE.value,
            findings=[
                SemanticMemoryEvidenceAdapterFinding(
                    code="ADAPTER_BLOCKED",
                    severity=SemanticMemoryEvidenceSeverity.BLOCKER.value,
                    message=reason,
                    evidence={"block_reason": reason},
                ),
            ],
            blocker_count=1,
            warning_count=0,
            info_count=0,
            git_state_verified=False,
            risk_summary_verified=False,
            security_validation_verified=False,
            tests_verified=False,
            smokes_verified=False,
            accepted_for_decision_gate=False,
            allow_real_write=False,
            dry_run_only=True,
            can_execute_real_write=False,
            requires_manual_review=True,
            warnings=[],
            blockers=[reason, "BLOCKED: Evidence adapter blocked"],
            metadata={"block_reason": reason},
        )
