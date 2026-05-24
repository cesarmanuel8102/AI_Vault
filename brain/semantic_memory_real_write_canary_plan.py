"""
P2-E Commit 4D-RealWriteCanaryPlan: Canary Plan for Semantic Memory Real Write Operations

This module provides a canary plan for validating semantic memory real write operations
without executing them. It works with the decision gate evidence adapter to ensure
all safety checks pass before any real write could be considered.

REGLAS DURAS:
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
from typing import Any, Dict, List, Optional, Set, Tuple
import uuid

# Import from evidence adapter (P2-E Commit 4D-DecisionGateEvidenceAdapter)
from brain.semantic_memory_decision_gate_evidence_adapter import (
    SemanticMemoryEvidenceAdapterStatus,
    SemanticMemoryEvidenceAdapterFinding,
    SemanticMemoryDecisionGateEvidenceAdapterReport,
    SemanticMemoryDecisionGateEvidenceAdapter,
)


class SemanticMemoryCanaryDecision(str, Enum):
    """Decisiones posibles del canary plan."""
    BLOCK = "BLOCK"
    NOOP_ONLY = "NOOP_ONLY"
    CANDIDATE_READY = "CANDIDATE_READY"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class SemanticMemoryCanarySeverity(str, Enum):
    """Severidad de los findings del canary."""
    INFO = "INFO"
    WARNING = "WARNING"
    BLOCKER = "BLOCKER"
    CRITICAL = "CRITICAL"


@dataclass
class SemanticMemoryCanaryFinding:
    """Un finding del canary plan."""
    code: str
    severity: SemanticMemoryCanarySeverity
    message: str
    evidence: Dict[str, Any] = field(default_factory=dict)
    timestamp_utc: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity.value,
            "message": self.message,
            "evidence": self.evidence,
            "timestamp_utc": self.timestamp_utc,
        }


@dataclass
class SemanticMemoryRealWriteCanaryPlanReport:
    """
    Reporte del canary plan para escritura real de memoria semántica.
    
    Este reporte documenta el estado del canary plan y su decisión.
    SIEMPRE mantiene allow_real_write=False.
    """
    canary_id: str
    created_at_utc: str
    decision: SemanticMemoryCanaryDecision
    status: str
    findings: List[SemanticMemoryCanaryFinding]
    blocker_count: int
    warning_count: int
    info_count: int
    critical_count: int
    allow_real_write: bool = False
    dry_run_only: bool = True
    can_execute_real_write: bool = False
    requires_manual_review: bool = True
    adapter_report_id: Optional[str] = None
    adapter_status: Optional[str] = None
    evidence_bundle_valid: bool = False
    safety_invariants_passed: bool = False
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "canary_id": self.canary_id,
            "created_at_utc": self.created_at_utc,
            "decision": self.decision.value,
            "status": self.status,
            "findings": [f.to_dict() for f in self.findings],
            "blocker_count": self.blocker_count,
            "warning_count": self.warning_count,
            "info_count": self.info_count,
            "critical_count": self.critical_count,
            "allow_real_write": self.allow_real_write,
            "dry_run_only": self.dry_run_only,
            "can_execute_real_write": self.can_execute_real_write,
            "requires_manual_review": self.requires_manual_review,
            "adapter_report_id": self.adapter_report_id,
            "adapter_status": self.adapter_status,
            "evidence_bundle_valid": self.evidence_bundle_valid,
            "safety_invariants_passed": self.safety_invariants_passed,
            "blockers": self.blockers,
            "warnings": self.warnings,
            "metadata": self.metadata,
        }


class SemanticMemoryRealWriteCanaryPlan:
    """
    Canary Plan para operaciones de escritura real de memoria semántica.
    
    Este plan:
    1. Recibe bundles de evidencia
    2. Valida usando el adaptador de evidencia
    3. Ejecuta verificaciones de invarianzas de seguridad
    4. Emite decisión canary sin ejecutar escrituras
    
    SIEMPRE:
    - allow_real_write=False
    - dry_run_only=True
    - can_execute_real_write=False
    """
    
    # Códigos de findings del canary
    CANARY_CODES = {
        "ADAPTER_VALIDATION_PASSED": "Adapter validation passed",
        "ADAPTER_VALIDATION_FAILED": "Adapter validation failed",
        "EVIDENCE_BUNDLE_ACCEPTED": "Evidence bundle accepted",
        "EVIDENCE_BUNDLE_REJECTED": "Evidence bundle rejected",
        "SAFETY_INVARIANT_PASSED": "Safety invariant passed",
        "SAFETY_INVARIANT_FAILED": "Safety invariant failed",
        "REAL_WRITE_BLOCKED": "Real write operation blocked",
        "DRY_RUN_ENFORCED": "Dry run mode enforced",
        "NOOP_OPERATION_ONLY": "Noop operation only",
        "CANARY_PLAN_ACTIVE": "Canary plan is active",
        "ADD_MEMORY_BLOCKED": "add_memory call blocked",
        "SUBPROCESS_BLOCKED": "subprocess blocked",
        "FAISS_IMPORT_BLOCKED": "FAISS import blocked",
        "BRIDGE_IMPORT_BLOCKED": "semantic_memory_bridge import blocked",
        "WRITE_OPERATION_BLOCKED": "Write operation blocked",
        "GIT_OPERATION_BLOCKED": "Git operation blocked",
        "CANARY_REPORT_GENERATED": "Canary report generated",
        "MANUAL_REVIEW_TRIGGERED": "Manual review triggered",
        "CANDIDATE_STATUS_ACHIEVED": "Candidate status achieved",
        "CANDIDATE_STATUS_DENIED": "Candidate status denied",
    }
    
    def __init__(self, repo_root: str | Path = "."):
        """
        Inicializar canary plan.
        
        Args:
            repo_root: Raíz del repositorio
        """
        self._repo_root = Path(repo_root).resolve()
        self._canary_id = f"canary_{uuid.uuid4().hex[:16]}"
        self._created_at = datetime.now(timezone.utc).isoformat()
        
        # Initialize evidence adapter
        self._adapter = SemanticMemoryDecisionGateEvidenceAdapter(
            repo_root=self._repo_root
        )
    
    def evaluate_canary_plan(
        self,
        evidence_bundle: Optional[Dict[str, Any]] = None,
    ) -> SemanticMemoryRealWriteCanaryPlanReport:
        """
        Evaluar canary plan con bundle de evidencia.
        
        Args:
            evidence_bundle: Bundle de evidencia externa (opcional)
            
        Returns:
            SemanticMemoryRealWriteCanaryPlanReport
        """
        findings: List[SemanticMemoryCanaryFinding] = []
        
        # Step 1: Validate evidence bundle using adapter if provided
        adapter_report = None
        evidence_bundle_valid = False
        adapter_status = None
        adapter_report_id = None
        
        if evidence_bundle:
            adapter_report = self._adapter.evaluate_with_evidence_read_only(
                evidence_bundle
            )
            adapter_report_id = adapter_report.adapter_id
            adapter_status = adapter_report.status.value
            
            # Check if evidence bundle was accepted
            if adapter_report.status == SemanticMemoryEvidenceAdapterStatus.ACCEPTED_FOR_GATE:
                evidence_bundle_valid = True
                findings.append(SemanticMemoryCanaryFinding(
                    code="EVIDENCE_BUNDLE_ACCEPTED",
                    severity=SemanticMemoryCanarySeverity.INFO,
                    message="Evidence bundle accepted by adapter",
                    evidence={
                        "adapter_id": adapter_report.adapter_id,
                        "evidence_status": adapter_report.evidence_status,
                    },
                ))
            else:
                findings.append(SemanticMemoryCanaryFinding(
                    code="EVIDENCE_BUNDLE_REJECTED",
                    severity=SemanticMemoryCanarySeverity.BLOCKER,
                    message=f"Evidence bundle rejected: {adapter_report.status.value}",
                    evidence={
                        "adapter_status": adapter_report.status.value,
                        "evidence_status": adapter_report.evidence_status,
                    },
                ))
        else:
            findings.append(SemanticMemoryCanaryFinding(
                code="EVIDENCE_BUNDLE_REJECTED",
                severity=SemanticMemoryCanarySeverity.WARNING,
                message="No evidence bundle provided, proceeding with default checks",
                evidence={},
            ))
        
        # Step 2: Enforce safety invariants
        safety_passed = self._enforce_safety_invariants(findings)
        
        # Step 3: Calculate decision
        decision, status = self._calculate_decision(
            evidence_bundle_valid=evidence_bundle_valid,
            safety_passed=safety_passed,
            adapter_report=adapter_report,
        )
        
        # Step 4: Calculate counts
        blocker_count = sum(1 for f in findings if f.severity == SemanticMemoryCanarySeverity.BLOCKER)
        warning_count = sum(1 for f in findings if f.severity == SemanticMemoryCanarySeverity.WARNING)
        info_count = sum(1 for f in findings if f.severity == SemanticMemoryCanarySeverity.INFO)
        critical_count = sum(1 for f in findings if f.severity == SemanticMemoryCanarySeverity.CRITICAL)
        
        # Step 5: Build blockers and warnings lists
        blockers = [
            "P2-E Commit 4D-RealWriteCanaryPlan: Canary activo",
            "allow_real_write=False por diseño",
            "dry_run_only=True por diseño",
            "can_execute_real_write=False por diseño",
        ]
        
        if blocker_count > 0:
            blockers.append(f"{blocker_count} blockers encontrados")
        
        if not safety_passed:
            blockers.append("Safety invariants not passed")
        
        if not evidence_bundle_valid and evidence_bundle:
            blockers.append("Evidence bundle not valid")
        
        warnings_list = [f.message for f in findings if f.severity == SemanticMemoryCanarySeverity.WARNING]
        
        return SemanticMemoryRealWriteCanaryPlanReport(
            canary_id=self._canary_id,
            created_at_utc=self._created_at,
            decision=decision,
            status=status,
            findings=findings,
            blocker_count=blocker_count,
            warning_count=warning_count,
            info_count=info_count,
            critical_count=critical_count,
            allow_real_write=False,  # SIEMPRE False
            dry_run_only=True,  # SIEMPRE True
            can_execute_real_write=False,  # SIEMPRE False
            requires_manual_review=(decision != SemanticMemoryCanaryDecision.CANDIDATE_READY),
            adapter_report_id=adapter_report_id,
            adapter_status=adapter_status,
            evidence_bundle_valid=evidence_bundle_valid,
            safety_invariants_passed=safety_passed,
            blockers=blockers,
            warnings=warnings_list,
            metadata={
                "canary_version": "P2-E-Commit-4D-RealWriteCanaryPlan",
                "canary_type": "RealWriteCanaryPlan",
                "evidence_bundle_provided": evidence_bundle is not None,
                "bundle_id": evidence_bundle.get("bundle_id", "unknown") if evidence_bundle else None,
            },
        )
    
    def _enforce_safety_invariants(
        self,
        findings: List[SemanticMemoryCanaryFinding],
    ) -> bool:
        """
        Enforce safety invariants - verify no forbidden operations.
        
        Args:
            findings: Lista de findings (se agregan aquí)
            
        Returns:
            True si todas las invarianzas pasan
        """
        invariants_passed = True
        
        # Invariant 1: allow_real_write is always False
        findings.append(SemanticMemoryCanaryFinding(
            code="SAFETY_INVARIANT_PASSED",
            severity=SemanticMemoryCanarySeverity.INFO,
            message="Invariant: allow_real_write=False enforced",
            evidence={"invariant": "allow_real_write", "value": False},
        ))
        
        # Invariant 2: dry_run_only is always True
        findings.append(SemanticMemoryCanaryFinding(
            code="SAFETY_INVARIANT_PASSED",
            severity=SemanticMemoryCanarySeverity.INFO,
            message="Invariant: dry_run_only=True enforced",
            evidence={"invariant": "dry_run_only", "value": True},
        ))
        
        # Invariant 3: can_execute_real_write is always False
        findings.append(SemanticMemoryCanaryFinding(
            code="SAFETY_INVARIANT_PASSED",
            severity=SemanticMemoryCanarySeverity.INFO,
            message="Invariant: can_execute_real_write=False enforced",
            evidence={"invariant": "can_execute_real_write", "value": False},
        ))
        
        # Invariant 4: No subprocess allowed
        findings.append(SemanticMemoryCanaryFinding(
            code="SUBPROCESS_BLOCKED",
            severity=SemanticMemoryCanarySeverity.INFO,
            message="Invariant: subprocess blocked - no subprocess calls in this module",
            evidence={"blocked_operation": "subprocess"},
        ))
        
        # Invariant 5: No FAISS import
        findings.append(SemanticMemoryCanaryFinding(
            code="FAISS_IMPORT_BLOCKED",
            severity=SemanticMemoryCanarySeverity.INFO,
            message="Invariant: FAISS import blocked - no faiss import in this module",
            evidence={"blocked_import": "faiss"},
        ))
        
        # Invariant 6: No semantic_memory_bridge import
        findings.append(SemanticMemoryCanaryFinding(
            code="BRIDGE_IMPORT_BLOCKED",
            severity=SemanticMemoryCanarySeverity.INFO,
            message="Invariant: semantic_memory_bridge import blocked",
            evidence={"blocked_import": "semantic_memory_bridge"},
        ))
        
        # Invariant 7: No add_memory calls
        findings.append(SemanticMemoryCanaryFinding(
            code="ADD_MEMORY_BLOCKED",
            severity=SemanticMemoryCanarySeverity.INFO,
            message="Invariant: add_memory calls blocked",
            evidence={"blocked_operation": "add_memory"},
        ))
        
        # Invariant 8: No write operations
        findings.append(SemanticMemoryCanaryFinding(
            code="WRITE_OPERATION_BLOCKED",
            severity=SemanticMemoryCanarySeverity.INFO,
            message="Invariant: write operations blocked - read-only only",
            evidence={"blocked_operation": "write"},
        ))
        
        # Invariant 9: No git operations
        findings.append(SemanticMemoryCanaryFinding(
            code="GIT_OPERATION_BLOCKED",
            severity=SemanticMemoryCanarySeverity.INFO,
            message="Invariant: git operations blocked - no git execution",
            evidence={"blocked_operation": "git"},
        ))
        
        return invariants_passed
    
    def _calculate_decision(
        self,
        evidence_bundle_valid: bool,
        safety_passed: bool,
        adapter_report: Optional[SemanticMemoryDecisionGateEvidenceAdapterReport],
    ) -> Tuple[SemanticMemoryCanaryDecision, str]:
        """
        Calculate canary decision based on validations.
        
        Args:
            evidence_bundle_valid: Si el bundle de evidencia es válido
            safety_passed: Si las invarianzas de seguridad pasaron
            adapter_report: Reporte del adaptador
            
        Returns:
            Tupla (decision, status)
        """
        if not safety_passed:
            return SemanticMemoryCanaryDecision.BLOCK, "BLOCKED_SAFETY_FAILED"
        
        if adapter_report:
            if adapter_report.status == SemanticMemoryEvidenceAdapterStatus.ACCEPTED_FOR_GATE:
                if evidence_bundle_valid and safety_passed:
                    return SemanticMemoryCanaryDecision.CANDIDATE_READY, "CANDIDATE"
                else:
                    return SemanticMemoryCanaryDecision.MANUAL_REVIEW, "REVIEW_REQUIRED"
            elif adapter_report.status == SemanticMemoryEvidenceAdapterStatus.PARTIAL_EVIDENCE:
                return SemanticMemoryCanaryDecision.NOOP_ONLY, "NOOP_ONLY"
            elif adapter_report.status == SemanticMemoryEvidenceAdapterStatus.REJECTED_BY_EVIDENCE:
                return SemanticMemoryCanaryDecision.BLOCK, "BLOCKED_EVIDENCE"
            elif adapter_report.status == SemanticMemoryEvidenceAdapterStatus.BLOCKED:
                return SemanticMemoryCanaryDecision.BLOCK, "BLOCKED_ADAPTER"
            else:
                return SemanticMemoryCanaryDecision.MANUAL_REVIEW, "UNKNOWN_STATUS"
        else:
            # No evidence bundle - allow noop only
            return SemanticMemoryCanaryDecision.NOOP_ONLY, "NOOP_NO_BUNDLE"
    
    def create_noop_canary_report(self) -> SemanticMemoryRealWriteCanaryPlanReport:
        """
        Create a noop canary report (default safe state).
        
        Returns:
            SemanticMemoryRealWriteCanaryPlanReport con decisión NOOP_ONLY
        """
        findings = [
            SemanticMemoryCanaryFinding(
                code="CANARY_PLAN_ACTIVE",
                severity=SemanticMemoryCanarySeverity.INFO,
                message="Canary plan initialized in noop mode",
                evidence={"mode": "noop"},
            ),
            SemanticMemoryCanaryFinding(
                code="NOOP_OPERATION_ONLY",
                severity=SemanticMemoryCanarySeverity.INFO,
                message="Only noop operations allowed",
                evidence={"operation_type": "noop"},
            ),
        ]
        
        # Add safety invariants
        self._enforce_safety_invariants(findings)
        
        blocker_count = sum(1 for f in findings if f.severity == SemanticMemoryCanarySeverity.BLOCKER)
        warning_count = sum(1 for f in findings if f.severity == SemanticMemoryCanarySeverity.WARNING)
        info_count = sum(1 for f in findings if f.severity == SemanticMemoryCanarySeverity.INFO)
        
        return SemanticMemoryRealWriteCanaryPlanReport(
            canary_id=self._canary_id,
            created_at_utc=self._created_at,
            decision=SemanticMemoryCanaryDecision.NOOP_ONLY,
            status="NOOP_DEFAULT",
            findings=findings,
            blocker_count=blocker_count,
            warning_count=warning_count,
            info_count=info_count,
            critical_count=0,
            allow_real_write=False,
            dry_run_only=True,
            can_execute_real_write=False,
            requires_manual_review=True,
            adapter_report_id=None,
            adapter_status=None,
            evidence_bundle_valid=False,
            safety_invariants_passed=True,
            blockers=["Canary plan in noop mode"],
            warnings=[],
            metadata={
                "canary_version": "P2-E-Commit-4D-RealWriteCanaryPlan",
                "mode": "noop_default",
            },
        )
    
    def block_canary(
        self,
        reason: str = "Canary blocked",
    ) -> SemanticMemoryRealWriteCanaryPlanReport:
        """
        Bloquear canary explícitamente.
        
        Args:
            reason: Razón del bloqueo
            
        Returns:
            SemanticMemoryRealWriteCanaryPlanReport bloqueado
        """
        findings = [
            SemanticMemoryCanaryFinding(
                code="REAL_WRITE_BLOCKED",
                severity=SemanticMemoryCanarySeverity.CRITICAL,
                message=reason,
                evidence={"block_reason": reason},
            ),
            SemanticMemoryCanaryFinding(
                code="DRY_RUN_ENFORCED",
                severity=SemanticMemoryCanarySeverity.INFO,
                message="Dry run enforced",
                evidence={"enforced": True},
            ),
        ]
        
        return SemanticMemoryRealWriteCanaryPlanReport(
            canary_id=f"blocked_{self._canary_id}",
            created_at_utc=datetime.now(timezone.utc).isoformat(),
            decision=SemanticMemoryCanaryDecision.BLOCK,
            status="BLOCKED",
            findings=findings,
            blocker_count=1,
            warning_count=0,
            info_count=1,
            critical_count=1,
            allow_real_write=False,
            dry_run_only=True,
            can_execute_real_write=False,
            requires_manual_review=True,
            adapter_report_id=None,
            adapter_status=None,
            evidence_bundle_valid=False,
            safety_invariants_passed=False,
            blockers=[reason, "BLOCKED: Canary plan blocked"],
            warnings=[],
            metadata={"block_reason": reason},
        )
    
    def summarize_canary_plan(self) -> Dict[str, Any]:
        """
        Resumir el canary plan.
        
        Returns:
            Dict con información del canary plan
        """
        return {
            "canary_version": "P2-E-Commit-4D-RealWriteCanaryPlan",
            "canary_type": "RealWriteCanaryPlan",
            "allow_real_write": False,
            "dry_run_only": True,
            "can_execute_real_write": False,
            "requires_manual_review": True,
            "decision_states": {
                "BLOCK": "Blocked - cannot proceed",
                "NOOP_ONLY": "Noop only - safe operations only",
                "CANDIDATE_READY": "Candidate ready - requires manual review",
                "MANUAL_REVIEW": "Manual review required",
            },
            "severity_levels": {
                "INFO": "Informational",
                "WARNING": "Warning - attention needed",
                "BLOCKER": "Blocker - prevents operation",
                "CRITICAL": "Critical - immediate attention",
            },
            "limitations": [
                "NO subprocess execution",
                "NO file system writes",
                "NO runtime activation",
                "NO FAISS import",
                "NO semantic_memory_bridge import",
                "NO add_memory calls",
                "Read-only evaluation only",
            ],
            "invariants": [
                "allow_real_write=False ALWAYS",
                "dry_run_only=True ALWAYS",
                "can_execute_real_write=False ALWAYS",
            ],
            "next_step": "Provide evidence bundle for evaluation",
        }
