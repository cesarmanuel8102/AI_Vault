"""
P2-E Commit 4D-EvidenceInjection: Semantic Memory External Evidence Contract

Contrato read-only para inyectar evidencia externa verificada al DecisionGate.
Este módulo NO ejecuta subprocess, NO lee archivos de runtime, NO escribe nada.

REGLAS DURAS:
- Solo valida objetos/dicts proporcionados externamente
- NO ejecuta git
- NO usa subprocess
- NO usa open()
- NO lee memory/semantic
- NO write_text/write_bytes
- NO unlink/remove/rmdir
- NO shutil
- NO copy calls
- NO import faiss
- NO requests/httpx
- NO semantic_memory_bridge
- NO add_memory
- allow_real_write=False SIEMPRE
- dry_run_only=True SIEMPRE
- can_execute_real_write=False SIEMPRE
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
import uuid


class SemanticMemoryEvidenceKind(str, Enum):
    """Tipos de evidencia que puede recibir."""
    GIT_STATE_EVIDENCE = "GIT_STATE_EVIDENCE"
    RISK_SUMMARY_EVIDENCE = "RISK_SUMMARY_EVIDENCE"
    SECURITY_VALIDATION_EVIDENCE = "SECURITY_VALIDATION_EVIDENCE"
    TEST_EXECUTION_EVIDENCE = "TEST_EXECUTION_EVIDENCE"
    SMOKE_EXECUTION_EVIDENCE = "SMOKE_EXECUTION_EVIDENCE"
    UNKNOWN = "UNKNOWN"


class SemanticMemoryEvidenceStatus(str, Enum):
    """Estado de validación de evidencia."""
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    PARTIAL = "PARTIAL"
    MISSING = "MISSING"
    UNKNOWN = "UNKNOWN"


class SemanticMemoryEvidenceSeverity(str, Enum):
    """Severidad de findings de evidencia."""
    INFO = "INFO"
    WARNING = "WARNING"
    BLOCKER = "BLOCKER"


@dataclass
class SemanticMemoryEvidenceFinding:
    """Un finding de validación de evidencia."""
    code: str
    severity: SemanticMemoryEvidenceSeverity
    message: str
    evidence: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity.value,
            "message": self.message,
            "evidence": self.evidence,
        }


@dataclass
class SemanticMemoryExternalEvidenceBundle:
    """
    Bundle de evidencia externa para validación.
    
    Este bundle representa evidencia producida externamente
    por el agente o humano, NO generada por este módulo.
    """
    bundle_id: str
    created_at_utc: str
    producer: str
    repo_root: str
    branch: str
    head_hash: str
    git_state: Dict[str, Any]
    risk_summary: Dict[str, Any]
    security_validation: Dict[str, Any]
    test_summary: Dict[str, Any]
    smoke_summary: Dict[str, Any]
    allow_real_write: bool = False
    dry_run_only: bool = True
    can_execute_real_write: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "bundle_id": self.bundle_id,
            "created_at_utc": self.created_at_utc,
            "producer": self.producer,
            "repo_root": self.repo_root,
            "branch": self.branch,
            "head_hash": self.head_hash,
            "git_state": self.git_state,
            "risk_summary": self.risk_summary,
            "security_validation": self.security_validation,
            "test_summary": self.test_summary,
            "smoke_summary": self.smoke_summary,
            "allow_real_write": self.allow_real_write,
            "dry_run_only": self.dry_run_only,
            "can_execute_real_write": self.can_execute_real_write,
            "metadata": self.metadata,
        }


@dataclass
class SemanticMemoryExternalEvidenceValidationReport:
    """
    Reporte de validación de evidencia externa.
    
    SIEMPRE bloquea hasta que se cumplan todas las condiciones.
    """
    validation_id: str
    created_at_utc: str
    status: SemanticMemoryEvidenceStatus
    findings: List[SemanticMemoryEvidenceFinding]
    blocker_count: int
    warning_count: int
    info_count: int
    git_state_verified: bool
    risk_summary_verified: bool
    security_validation_verified: bool
    tests_verified: bool
    smokes_verified: bool
    allow_real_write: bool = False
    dry_run_only: bool = True
    can_execute_real_write: bool = False
    requires_manual_review: bool = True
    accepted_for_decision_gate: bool = False
    warnings: List[str] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "validation_id": self.validation_id,
            "created_at_utc": self.created_at_utc,
            "status": self.status.value,
            "findings": [f.to_dict() for f in self.findings],
            "blocker_count": self.blocker_count,
            "warning_count": self.warning_count,
            "info_count": self.info_count,
            "git_state_verified": self.git_state_verified,
            "risk_summary_verified": self.risk_summary_verified,
            "security_validation_verified": self.security_validation_verified,
            "tests_verified": self.tests_verified,
            "smokes_verified": self.smokes_verified,
            "allow_real_write": self.allow_real_write,
            "dry_run_only": self.dry_run_only,
            "can_execute_real_write": self.can_execute_real_write,
            "requires_manual_review": self.requires_manual_review,
            "accepted_for_decision_gate": self.accepted_for_decision_gate,
            "warnings": self.warnings,
            "blockers": self.blockers,
            "metadata": self.metadata,
        }


class SemanticMemoryExternalEvidenceContract:
    """
    Contrato de evidencia externa para DecisionGate.
    
    Este contrato valida evidencia producida externamente.
    NO ejecuta subprocess, NO lee archivos runtime, NO escribe nada.
    
    Responsabilidades:
    - Validar estructura de bundles de evidencia
    - Verificar flags de seguridad
    - Asegurar consistencia de evidencia
    - Emitir reporte de aceptación/rechazo
    
    Limitaciones:
    - Solo valida objetos/dicts proporcionados
    - NO ejecuta git, subprocess, o runtime
    - NO modifica archivos
    - NO importa faiss, semantic_memory_bridge
    - SIEMPRE bloquea allow_real_write
    """
    
    def __init__(self, repo_root: str | Path = "."):
        """
        Inicializar contrato.
        
        Args:
            repo_root: Raíz del repositorio (para referencia, no modifica)
        """
        self._repo_root = Path(repo_root).resolve()
        self._validation_id = f"evidence_{uuid.uuid4().hex[:16]}"
        self._created_at = datetime.now(timezone.utc).isoformat()
    
    def validate_bundle_read_only(
        self,
        bundle: SemanticMemoryExternalEvidenceBundle | Dict[str, Any],
    ) -> SemanticMemoryExternalEvidenceValidationReport:
        """
        Validar bundle de evidencia (read-only).
        
        Este método:
        1. Normaliza el bundle a dict
        2. Valida git_state
        3. Valida risk_summary
        4. Valida security_validation
        5. Valida test_summary
        6. Valida smoke_summary
        7. Determina estado de aceptación
        
        Args:
            bundle: Bundle de evidencia (dataclass o dict)
            
        Returns:
            SemanticMemoryExternalEvidenceValidationReport con resultado
        """
        findings: List[SemanticMemoryEvidenceFinding] = []
        
        # Normalizar bundle
        bundle_dict = self.normalize_bundle(bundle)
        
        # Check 1: Git state evidence
        git_state = bundle_dict.get("git_state", {})
        git_findings = self.validate_git_state(git_state)
        findings.extend(git_findings)
        git_verified = not any(
            f.severity == SemanticMemoryEvidenceSeverity.BLOCKER for f in git_findings
        ) and git_state.get("verified", False)
        
        # Check 2: Risk summary evidence
        risk_summary = bundle_dict.get("risk_summary", {})
        risk_findings = self.validate_risk_summary(risk_summary)
        findings.extend(risk_findings)
        risk_verified = not any(
            f.severity == SemanticMemoryEvidenceSeverity.BLOCKER for f in risk_findings
        ) and risk_summary.get("verified", False)
        
        # Check 3: Security validation evidence
        security_validation = bundle_dict.get("security_validation", {})
        security_findings = self.validate_security_validation(security_validation)
        findings.extend(security_findings)
        security_verified = not any(
            f.severity == SemanticMemoryEvidenceSeverity.BLOCKER for f in security_findings
        ) and security_validation.get("verified", False)
        
        # Check 4: Test summary evidence
        test_summary = bundle_dict.get("test_summary", {})
        test_findings = self.validate_test_summary(test_summary)
        findings.extend(test_findings)
        tests_verified = not any(
            f.severity == SemanticMemoryEvidenceSeverity.BLOCKER for f in test_findings
        ) and test_summary.get("verified", False)
        
        # Check 5: Smoke summary evidence
        smoke_summary = bundle_dict.get("smoke_summary", {})
        smoke_findings = self.validate_smoke_summary(smoke_summary)
        findings.extend(smoke_findings)
        smokes_verified = not any(
            f.severity == SemanticMemoryEvidenceSeverity.BLOCKER for f in smoke_findings
        ) and smoke_summary.get("verified", False)
        
        # Calculate conteos
        blocker_count = sum(1 for f in findings if f.severity == SemanticMemoryEvidenceSeverity.BLOCKER)
        warning_count = sum(1 for f in findings if f.severity == SemanticMemoryEvidenceSeverity.WARNING)
        info_count = sum(1 for f in findings if f.severity == SemanticMemoryEvidenceSeverity.INFO)
        
        # Determinar status
        if blocker_count > 0:
            status = SemanticMemoryEvidenceStatus.REJECTED
            accepted = False
        elif warning_count > 0:
            status = SemanticMemoryEvidenceStatus.PARTIAL
            accepted = False
        elif git_verified and risk_verified and security_verified and tests_verified and smokes_verified:
            status = SemanticMemoryEvidenceStatus.ACCEPTED
            accepted = True
        else:
            status = SemanticMemoryEvidenceStatus.MISSING
            accepted = False
        
        # Bloqueadores
        blockers = [
            "P2-E Commit 4D-EvidenceInjection: Evidence contract activo",
            "allow_real_write=False por diseño",
        ]
        if blocker_count > 0:
            blockers.append(f"{blocker_count} blockers en evidencia")
        
        warnings_list = [f.message for f in findings if f.severity == SemanticMemoryEvidenceSeverity.WARNING]
        
        return SemanticMemoryExternalEvidenceValidationReport(
            validation_id=self._validation_id,
            created_at_utc=self._created_at,
            status=status,
            findings=findings,
            blocker_count=blocker_count,
            warning_count=warning_count,
            info_count=info_count,
            git_state_verified=git_verified,
            risk_summary_verified=risk_verified,
            security_validation_verified=security_verified,
            tests_verified=tests_verified,
            smokes_verified=smokes_verified,
            allow_real_write=False,  # SIEMPRE False
            dry_run_only=True,  # SIEMPRE True
            can_execute_real_write=False,  # SIEMPRE False
            requires_manual_review=not accepted,
            accepted_for_decision_gate=accepted,
            warnings=warnings_list,
            blockers=blockers,
            metadata={
                "bundle_id": bundle_dict.get("bundle_id", "unknown"),
                "producer": bundle_dict.get("producer", "unknown"),
                "head_hash": bundle_dict.get("head_hash", "unknown"),
            },
        )
    
    def normalize_bundle(
        self,
        bundle: SemanticMemoryExternalEvidenceBundle | Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Normalizar bundle a dict.
        
        Args:
            bundle: Bundle (dataclass o dict)
            
        Returns:
            Dict con datos del bundle
        """
        if isinstance(bundle, SemanticMemoryExternalEvidenceBundle):
            return bundle.to_dict()
        elif isinstance(bundle, dict):
            return bundle
        else:
            return {}
    
    def validate_git_state(self, git_state: Dict[str, Any]) -> List[SemanticMemoryEvidenceFinding]:
        """
        Validar evidencia de estado git.
        
        Args:
            git_state: Dict con evidencia de git
            
        Returns:
            Lista de findings
        """
        findings: List[SemanticMemoryEvidenceFinding] = []
        
        if not git_state:
            findings.append(SemanticMemoryEvidenceFinding(
                code="MISSING_GIT_STATE",
                severity=SemanticMemoryEvidenceSeverity.BLOCKER,
                message="git_state es requerido",
                evidence={},
            ))
            return findings
        
        if not git_state.get("verified", False):
            findings.append(SemanticMemoryEvidenceFinding(
                code="GIT_STATE_NOT_VERIFIED",
                severity=SemanticMemoryEvidenceSeverity.BLOCKER,
                message="git_state.verificado debe ser True",
                evidence={"verified": git_state.get("verified")},
            ))
        
        pending = git_state.get("pending_commits_vs_origin")
        if pending is not None and pending > 0:
            findings.append(SemanticMemoryEvidenceFinding(
                code="PENDING_COMMITS",
                severity=SemanticMemoryEvidenceSeverity.BLOCKER,
                message=f"Hay {pending} commits pendientes vs origin",
                evidence={"pending_commits": pending},
            ))
        
        staged = git_state.get("staged_files", [])
        if staged and len(staged) > 0:
            findings.append(SemanticMemoryEvidenceFinding(
                code="STAGED_FILES",
                severity=SemanticMemoryEvidenceSeverity.BLOCKER,
                message=f"Hay {len(staged)} archivos staged",
                evidence={"staged_files": staged},
            ))
        
        if git_state.get("memory_semantic_in_commit", False):
            findings.append(SemanticMemoryEvidenceFinding(
                code="MEMORY_SEMANTIC_IN_COMMIT",
                severity=SemanticMemoryEvidenceSeverity.BLOCKER,
                message="Commit contiene archivos de memory/semantic",
                evidence={},
            ))
        
        if git_state.get("tmp_agent_strategies_in_commit", False):
            findings.append(SemanticMemoryEvidenceFinding(
                code="TMP_AGENT_STRATEGIES_IN_COMMIT",
                severity=SemanticMemoryEvidenceSeverity.BLOCKER,
                message="Commit contiene archivos de tmp_agent/strategies",
                evidence={},
            ))
        
        if git_state.get("nul_in_commit", False):
            findings.append(SemanticMemoryEvidenceFinding(
                code="NUL_IN_COMMIT",
                severity=SemanticMemoryEvidenceSeverity.BLOCKER,
                message="Commit contiene archivo 'nul'",
                evidence={},
            ))
        
        if git_state.get("runtime_active", False):
            findings.append(SemanticMemoryEvidenceFinding(
                code="RUNTIME_ACTIVE",
                severity=SemanticMemoryEvidenceSeverity.BLOCKER,
                message="Runtime está activo durante evaluación",
                evidence={},
            ))
        
        return findings
    
    def validate_risk_summary(self, risk_summary: Dict[str, Any]) -> List[SemanticMemoryEvidenceFinding]:
        """
        Validar evidencia de resumen de riesgo.
        
        Args:
            risk_summary: Dict con evidencia de riesgo
            
        Returns:
            Lista de findings
        """
        findings: List[SemanticMemoryEvidenceFinding] = []
        
        if not risk_summary:
            findings.append(SemanticMemoryEvidenceFinding(
                code="MISSING_RISK_SUMMARY",
                severity=SemanticMemoryEvidenceSeverity.BLOCKER,
                message="risk_summary es requerido",
                evidence={},
            ))
            return findings
        
        if not risk_summary.get("verified", False):
            findings.append(SemanticMemoryEvidenceFinding(
                code="RISK_SUMMARY_NOT_VERIFIED",
                severity=SemanticMemoryEvidenceSeverity.BLOCKER,
                message="risk_summary.verificado debe ser True",
                evidence={"verified": risk_summary.get("verified")},
            ))
        
        high_risk = risk_summary.get("unresolved_high_risk_count")
        if high_risk is not None and high_risk > 0:
            findings.append(SemanticMemoryEvidenceFinding(
                code="UNRESOLVED_HIGH_RISK",
                severity=SemanticMemoryEvidenceSeverity.BLOCKER,
                message=f"Hay {high_risk} riesgos altos sin resolver",
                evidence={"unresolved_high_risk_count": high_risk},
            ))
        
        write_like = risk_summary.get("unresolved_write_like_count")
        if write_like is not None and write_like > 0:
            findings.append(SemanticMemoryEvidenceFinding(
                code="UNRESOLVED_WRITE_LIKE",
                severity=SemanticMemoryEvidenceSeverity.WARNING,
                message=f"Hay {write_like} operaciones write-like sin resolver",
                evidence={"unresolved_write_like_count": write_like},
            ))
        
        runtime_like = risk_summary.get("unresolved_runtime_like_count")
        if runtime_like is not None and runtime_like > 0:
            findings.append(SemanticMemoryEvidenceFinding(
                code="UNRESOLVED_RUNTIME_LIKE",
                severity=SemanticMemoryEvidenceSeverity.WARNING,
                message=f"Hay {runtime_like} operaciones runtime-like sin resolver",
                evidence={"unresolved_runtime_like_count": runtime_like},
            ))
        
        return findings
    
    def validate_security_validation(self, security_validation: Dict[str, Any]) -> List[SemanticMemoryEvidenceFinding]:
        """
        Validar evidencia de validación de seguridad.
        
        Args:
            security_validation: Dict con evidencia de seguridad
            
        Returns:
            Lista de findings
        """
        findings: List[SemanticMemoryEvidenceFinding] = []
        
        if not security_validation:
            findings.append(SemanticMemoryEvidenceFinding(
                code="MISSING_SECURITY_VALIDATION",
                severity=SemanticMemoryEvidenceSeverity.BLOCKER,
                message="security_validation es requerido",
                evidence={},
            ))
            return findings
        
        if not security_validation.get("verified", False):
            findings.append(SemanticMemoryEvidenceFinding(
                code="SECURITY_VALIDATION_NOT_VERIFIED",
                severity=SemanticMemoryEvidenceSeverity.BLOCKER,
                message="security_validation.verificado debe ser True",
                evidence={"verified": security_validation.get("verified")},
            ))
        
        critical_flags = {
            "no_open": "NO_OPEN_FAILED",
            "no_subprocess": "NO_SUBPROCESS_FAILED",
            "no_faiss": "NO_FAISS_FAILED",
            "no_requests_httpx": "NO_HTTP_CLIENT_FAILED",
            "no_semantic_memory_bridge": "NO_SEMANTIC_MEMORY_BRIDGE_FAILED",
            "no_add_memory": "NO_ADD_MEMORY_FAILED",
            "no_write_ops": "NO_WRITE_OPS_FAILED",
            "no_delete_ops": "NO_DELETE_OPS_FAILED",
            "no_move_ops": "NO_MOVE_OPS_FAILED",
            "no_allow_real_write_true": "ALLOW_REAL_WRITE_TRUE_FOUND",
        }
        
        for flag, code in critical_flags.items():
            if not security_validation.get(flag, False):
                findings.append(SemanticMemoryEvidenceFinding(
                    code=code,
                    severity=SemanticMemoryEvidenceSeverity.BLOCKER,
                    message=f"Seguridad crítica falló: {flag}=False",
                    evidence={"flag": flag, "value": security_validation.get(flag)},
                ))
        
        return findings
    
    def validate_test_summary(self, test_summary: Dict[str, Any]) -> List[SemanticMemoryEvidenceFinding]:
        """
        Validar evidencia de tests.
        
        Args:
            test_summary: Dict con evidencia de tests
            
        Returns:
            Lista de findings
        """
        findings: List[SemanticMemoryEvidenceFinding] = []
        
        if not test_summary:
            findings.append(SemanticMemoryEvidenceFinding(
                code="MISSING_TEST_SUMMARY",
                severity=SemanticMemoryEvidenceSeverity.BLOCKER,
                message="test_summary es requerido",
                evidence={},
            ))
            return findings
        
        if not test_summary.get("verified", False):
            findings.append(SemanticMemoryEvidenceFinding(
                code="TEST_SUMMARY_NOT_VERIFIED",
                severity=SemanticMemoryEvidenceSeverity.BLOCKER,
                message="test_summary.verificado debe ser True",
                evidence={"verified": test_summary.get("verified")},
            ))
        
        failed = test_summary.get("failed")
        if failed is not None and failed > 0:
            findings.append(SemanticMemoryEvidenceFinding(
                code="TESTS_FAILED",
                severity=SemanticMemoryEvidenceSeverity.BLOCKER,
                message=f"Hay {failed} tests fallidos",
                evidence={"failed": failed},
            ))
        
        if not test_summary.get("decision_gate_tests_passed", False):
            findings.append(SemanticMemoryEvidenceFinding(
                code="DECISION_GATE_TESTS_FAILED",
                severity=SemanticMemoryEvidenceSeverity.WARNING,
                message="Tests de DecisionGate no pasaron",
                evidence={},
            ))
        
        if not test_summary.get("p2e_regression_tests_passed", False):
            findings.append(SemanticMemoryEvidenceFinding(
                code="P2E_REGRESSION_TESTS_FAILED",
                severity=SemanticMemoryEvidenceSeverity.WARNING,
                message="Tests de regresión P2E no pasaron",
                evidence={},
            ))
        
        return findings
    
    def validate_smoke_summary(self, smoke_summary: Dict[str, Any]) -> List[SemanticMemoryEvidenceFinding]:
        """
        Validar evidencia de smoke tests.
        
        Args:
            smoke_summary: Dict con evidencia de smoke tests
            
        Returns:
            Lista de findings
        """
        findings: List[SemanticMemoryEvidenceFinding] = []
        
        if not smoke_summary:
            findings.append(SemanticMemoryEvidenceFinding(
                code="MISSING_SMOKE_SUMMARY",
                severity=SemanticMemoryEvidenceSeverity.BLOCKER,
                message="smoke_summary es requerido",
                evidence={},
            ))
            return findings
        
        if not smoke_summary.get("verified", False):
            findings.append(SemanticMemoryEvidenceFinding(
                code="SMOKE_SUMMARY_NOT_VERIFIED",
                severity=SemanticMemoryEvidenceSeverity.BLOCKER,
                message="smoke_summary.verificado debe ser True",
                evidence={"verified": smoke_summary.get("verified")},
            ))
        
        failed = smoke_summary.get("failed")
        if failed is not None and failed > 0:
            findings.append(SemanticMemoryEvidenceFinding(
                code="SMOKES_FAILED",
                severity=SemanticMemoryEvidenceSeverity.BLOCKER,
                message=f"Hay {failed} smoke tests fallidos",
                evidence={"failed": failed},
            ))
        
        if not smoke_summary.get("decision_gate_smoke_ok", False):
            findings.append(SemanticMemoryEvidenceFinding(
                code="DECISION_GATE_SMOKE_FAILED",
                severity=SemanticMemoryEvidenceSeverity.WARNING,
                message="Smoke test de DecisionGate no pasó",
                evidence={},
            ))
        
        if not smoke_summary.get("p2e_regression_smokes_ok", False):
            findings.append(SemanticMemoryEvidenceFinding(
                code="P2E_REGRESSION_SMOKES_FAILED",
                severity=SemanticMemoryEvidenceSeverity.WARNING,
                message="Smoke tests de regresión P2E no pasaron",
                evidence={},
            ))
        
        return findings
    
    def summarize_contract(self) -> Dict[str, Any]:
        """
        Resumir el contrato de evidencia.
        
        Returns:
            Dict con información del contrato
        """
        return {
            "contract_version": "P2-E-Commit-4D-EvidenceInjection",
            "contract_type": "ExternalEvidenceContract",
            "allow_real_write": False,
            "dry_run_only": True,
            "can_execute_real_write": False,
            "requires_manual_review": True,
            "evidence_kinds": [
                "GIT_STATE_EVIDENCE",
                "RISK_SUMMARY_EVIDENCE",
                "SECURITY_VALIDATION_EVIDENCE",
                "TEST_EXECUTION_EVIDENCE",
                "SMOKE_EXECUTION_EVIDENCE",
            ],
            "validation_rules": [
                "git_state.verificado=True",
                "pending_commits_vs_origin=0",
                "staged_files=[]",
                "memory_semantic_in_commit=False",
                "risk_summary.unresolved_high_risk_count=0",
                "security_validation.security_validation_ok=True",
                "test_summary.failed=0",
                "smoke_summary.failed=0",
            ],
            "limitations": [
                "NO subprocess execution",
                "NO file system writes",
                "NO runtime activation",
                "NO FAISS import",
                "NO semantic_memory_bridge import",
                "External evidence validation only",
            ],
            "next_step": "Provide verified evidence bundle",
        }
    
    def block_evidence(
        self,
        reason: str = "Evidence contract blocked",
    ) -> SemanticMemoryExternalEvidenceValidationReport:
        """
        Bloquear evidencia explícitamente.
        
        Args:
            reason: Razón del bloqueo
            
        Returns:
            SemanticMemoryExternalEvidenceValidationReport bloqueado
        """
        return SemanticMemoryExternalEvidenceValidationReport(
            validation_id=f"blocked_{self._validation_id}",
            created_at_utc=datetime.now(timezone.utc).isoformat(),
            status=SemanticMemoryEvidenceStatus.REJECTED,
            findings=[
                SemanticMemoryEvidenceFinding(
                    code="EVIDENCE_BLOCKED",
                    severity=SemanticMemoryEvidenceSeverity.BLOCKER,
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
            allow_real_write=False,
            dry_run_only=True,
            can_execute_real_write=False,
            requires_manual_review=True,
            accepted_for_decision_gate=False,
            warnings=[],
            blockers=[reason, "BLOCKED: Evidence validation blocked"],
            metadata={"block_reason": reason},
        )
