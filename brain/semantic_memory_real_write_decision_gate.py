"""
P2-E Commit 4D-DecisionGate: Semantic Memory Real Write Decision Gate

Compuerta de decisión gobernada para escritura real de memoria semántica.
Este módulo solo emite decisiones read-only, NO ejecuta escrituras reales.

REGLAS DURAS:
- Solo lectura de archivos (Path.exists, Path.stat, Path.read_text)
- NO ejecuta código
- NO importa módulos runtime (faiss, semantic_memory_bridge)
- NO escribe archivos
- NO usa subprocess
- NO usa open()
- NO write_text/write_bytes
- NO unlink/remove/rmdir
- NO shutil
- NO copy calls
- allow_real_write=False SIEMPRE
- dry_run_only=True SIEMPRE
- can_execute_real_write=False SIEMPRE
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
import uuid


class SemanticMemoryDecision(str, Enum):
    """Decisiones posibles del gate."""
    BLOCK_REAL_WRITE = "BLOCK_REAL_WRITE"
    CANARY_NOOP_ONLY = "CANARY_NOOP_ONLY"
    MANUAL_REVIEW_REQUIRED = "MANUAL_REVIEW_REQUIRED"
    ALLOW_MANUAL_REAL_WRITE_CANDIDATE = "ALLOW_MANUAL_REAL_WRITE_CANDIDATE"


class SemanticMemoryDecisionReasonCode(str, Enum):
    """Códigos de razón para findings."""
    MISSING_BACKUP_CONTRACT = "MISSING_BACKUP_CONTRACT"
    MISSING_ROLLBACK_SIMULATION = "MISSING_ROLLBACK_SIMULATION"
    MISSING_READINESS_GATE = "MISSING_READINESS_GATE"
    MISSING_REAL_STATE_AUDIT = "MISSING_REAL_STATE_AUDIT"
    MISSING_EXTRA_FILE_CLASSIFICATION = "MISSING_EXTRA_FILE_CLASSIFICATION"
    MISSING_DEPENDENCY_MAPPING = "MISSING_DEPENDENCY_MAPPING"
    STAGED_FILES_PRESENT = "STAGED_FILES_PRESENT"
    COMMITS_PENDING_VS_ORIGIN = "COMMITS_PENDING_VS_ORIGIN"
    DIRTY_STATE_DETECTED = "DIRTY_STATE_DETECTED"
    HIGH_RISK_EXTRA_FILES = "HIGH_RISK_EXTRA_FILES"
    HIGH_RISK_DEPENDENCY_HITS = "HIGH_RISK_DEPENDENCY_HITS"
    WRITE_LIKE_DEPENDENCY_HITS = "WRITE_LIKE_DEPENDENCY_HITS"
    RUNTIME_LIKE_DEPENDENCY_HITS = "RUNTIME_LIKE_DEPENDENCY_HITS"
    MANUAL_REVIEW_REQUIRED = "MANUAL_REVIEW_REQUIRED"
    ALLOW_REAL_WRITE_STILL_FALSE = "ALLOW_REAL_WRITE_STILL_FALSE"
    DRY_RUN_ONLY_STILL_TRUE = "DRY_RUN_ONLY_STILL_TRUE"
    SECURITY_VALIDATION_REQUIRED = "SECURITY_VALIDATION_REQUIRED"
    SAFE_CANDIDATE_ONLY = "SAFE_CANDIDATE_ONLY"


class SemanticMemoryDecisionSeverity(str, Enum):
    """Severidad de los findings."""
    INFO = "INFO"
    WARNING = "WARNING"
    BLOCKER = "BLOCKER"


@dataclass
class SemanticMemoryDecisionFinding:
    """Un finding de la evaluación del gate."""
    code: SemanticMemoryDecisionReasonCode
    severity: SemanticMemoryDecisionSeverity
    message: str
    evidence: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "code": self.code.value,
            "severity": self.severity.value,
            "message": self.message,
            "evidence": self.evidence,
        }


@dataclass
class SemanticMemoryRealWriteDecisionReport:
    """
    Reporte de decisión del gate de escritura real.
    
    SIEMPRE bloquea escritura real hasta que se cumplan todas las condiciones.
    """
    decision_id: str
    created_at_utc: str
    repo_root: str
    decision: SemanticMemoryDecision
    findings: List[SemanticMemoryDecisionFinding]
    blocker_count: int
    warning_count: int
    info_count: int
    allow_real_write: bool = False
    dry_run_only: bool = True
    can_execute_real_write: bool = False
    requires_manual_review: bool = True
    required_artifacts: Dict[str, Any] = field(default_factory=dict)
    git_state: Dict[str, Any] = field(default_factory=dict)
    risk_summary: Dict[str, Any] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    blockers: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "created_at_utc": self.created_at_utc,
            "repo_root": self.repo_root,
            "decision": self.decision.value,
            "findings": [f.to_dict() for f in self.findings],
            "blocker_count": self.blocker_count,
            "warning_count": self.warning_count,
            "info_count": self.info_count,
            "allow_real_write": self.allow_real_write,
            "dry_run_only": self.dry_run_only,
            "can_execute_real_write": self.can_execute_real_write,
            "requires_manual_review": self.requires_manual_review,
            "required_artifacts": self.required_artifacts,
            "git_state": self.git_state,
            "risk_summary": self.risk_summary,
            "warnings": self.warnings,
            "blockers": self.blockers,
            "metadata": self.metadata,
        }


class SemanticMemoryRealWriteDecisionGate:
    """
    Compuerta de decisión para escritura real de memoria semántica.
    
    Este gate evalúa artefactos previos y emite una decisión read-only.
    NO ejecuta escrituras reales. NO modifica archivos.
    
    Decisiones:
    - BLOCK_REAL_WRITE: Bloquear escritura (falta algo crítico)
    - CANARY_NOOP_ONLY: Permitir solo pruebas no-op
    - MANUAL_REVIEW_REQUIRED: Requiere revisión humana
    - ALLOW_MANUAL_REAL_WRITE_CANDIDATE: Candidato para revisión humana
    
    Importante: ALLOW_MANUAL_REAL_WRITE_CANDIDATE no significa que se permita
    escritura real automáticamente. Solo indica que pasó las verificaciones
    automáticas y necesita aprobación humana.
    """
    
    REQUIRED_ARTIFACTS = [
        "brain/memory_semantic_backup.py",
        "brain/semantic_memory_adapter_real.py",
        "brain/semantic_memory_rollback_simulation.py",
        "brain/semantic_memory_real_write_readiness_gate.py",
        "brain/semantic_memory_real_state_audit.py",
        "brain/semantic_memory_extra_file_classifier.py",
        "brain/semantic_memory_extra_file_dependency_mapper.py",
    ]
    
    def __init__(self, repo_root: str | Path = "."):
        """
        Inicializar el gate.
        
        Args:
            repo_root: Raíz del repositorio
        """
        self._repo_root = Path(repo_root).resolve()
        self._decision_id = f"decision_{uuid.uuid4().hex[:16]}"
        self._created_at = datetime.now(timezone.utc).isoformat()
    
    def evaluate_read_only(self) -> SemanticMemoryRealWriteDecisionReport:
        """
        Evaluar condiciones para escritura real (solo lectura).
        
        Este método:
        1. Verifica artefactos requeridos
        2. Verifica estado del git (read-only)
        3. Calcula resumen de riesgo
        4. Emite decisión basada en findings
        
        Returns:
            SemanticMemoryRealWriteDecisionReport con la decisión
        """
        findings: List[SemanticMemoryDecisionFinding] = []
        
        # Check 1: Artefactos requeridos
        required_artifacts = self.check_required_artifacts()
        for artifact, exists in required_artifacts.items():
            if not exists:
                findings.append(SemanticMemoryDecisionFinding(
                    code=SemanticMemoryDecisionReasonCode.MISSING_BACKUP_CONTRACT
                        if "backup" in artifact else
                        SemanticMemoryDecisionReasonCode.MISSING_ROLLBACK_SIMULATION
                        if "rollback" in artifact else
                        SemanticMemoryDecisionReasonCode.MISSING_READINESS_GATE
                        if "readiness" in artifact else
                        SemanticMemoryDecisionReasonCode.MISSING_REAL_STATE_AUDIT
                        if "audit" in artifact else
                        SemanticMemoryDecisionReasonCode.MISSING_EXTRA_FILE_CLASSIFICATION
                        if "classifier" in artifact else
                        SemanticMemoryDecisionReasonCode.MISSING_DEPENDENCY_MAPPING
                        if "dependency" in artifact else
                        SemanticMemoryDecisionReasonCode.MISSING_BACKUP_CONTRACT,
                    severity=SemanticMemoryDecisionSeverity.BLOCKER,
                    message=f"Artefacto requerido no encontrado: {artifact}",
                    evidence={"artifact": artifact, "path": str(self._repo_root / artifact)},
                ))
        
        # Check 2: Estado del git (read-only, no subprocess)
        git_state = self.check_git_state_read_only()
        if git_state.get("staged_files_present", False):
            findings.append(SemanticMemoryDecisionFinding(
                code=SemanticMemoryDecisionReasonCode.STAGED_FILES_PRESENT,
                severity=SemanticMemoryDecisionSeverity.BLOCKER,
                message="Hay archivos staged. Limpiar working tree antes de escritura real.",
                evidence={"staged_files": git_state.get("staged_files", [])},
            ))
        
        if git_state.get("commits_pending_vs_origin", False):
            findings.append(SemanticMemoryDecisionFinding(
                code=SemanticMemoryDecisionReasonCode.COMMITS_PENDING_VS_ORIGIN,
                severity=SemanticMemoryDecisionSeverity.BLOCKER,
                message="Hay commits pendientes vs origin. Push antes de escritura real.",
                evidence={"pending_commits": git_state.get("pending_count", 0)},
            ))
        
        if git_state.get("dirty_state", False):
            findings.append(SemanticMemoryDecisionFinding(
                code=SemanticMemoryDecisionReasonCode.DIRTY_STATE_DETECTED,
                severity=SemanticMemoryDecisionSeverity.WARNING,
                message="Working tree sucio. Verificar archivos modificados.",
                evidence={"modified_files": git_state.get("modified_files", [])},
            ))
        
        # Fail-closed: git state not verified
        if not git_state.get("verified", False):
            findings.append(SemanticMemoryDecisionFinding(
                code=SemanticMemoryDecisionReasonCode.SECURITY_VALIDATION_REQUIRED,
                severity=SemanticMemoryDecisionSeverity.WARNING,
                message="Git state unknown because subprocess is forbidden (fail-closed). Manual verification required.",
                evidence={"verified": False, "note": git_state.get("note", "")},
            ))
        
        # Check 3: Resumen de riesgo
        risk_summary = self.check_risk_summary_read_only()
        
        # High risk extra files
        if (risk_summary.get("high_risk_extra_files") or 0) > 0:
            findings.append(SemanticMemoryDecisionFinding(
                code=SemanticMemoryDecisionReasonCode.HIGH_RISK_EXTRA_FILES,
                severity=SemanticMemoryDecisionSeverity.WARNING,
                message=f"Archivos extra de alto riesgo detectados: {risk_summary['high_risk_extra_files']}",
                evidence={"extra_files": risk_summary.get("extra_files", [])},
            ))
        
        # High risk dependency hits
        if (risk_summary.get("high_risk_dependency_hits") or 0) > 0:
            findings.append(SemanticMemoryDecisionFinding(
                code=SemanticMemoryDecisionReasonCode.HIGH_RISK_DEPENDENCY_HITS,
                severity=SemanticMemoryDecisionSeverity.WARNING,
                message=f"Hits de dependencia de alto riesgo: {risk_summary['high_risk_dependency_hits']}",
                evidence={"high_risk_hits": risk_summary.get("high_risk_hits", [])},
            ))
        
        # Write-like dependency hits
        if (risk_summary.get("write_like_hits") or 0) > 0:
            findings.append(SemanticMemoryDecisionFinding(
                code=SemanticMemoryDecisionReasonCode.WRITE_LIKE_DEPENDENCY_HITS,
                severity=SemanticMemoryDecisionSeverity.WARNING,
                message=f"Operaciones tipo write detectadas: {risk_summary['write_like_hits']}",
                evidence={"write_hits": risk_summary.get("write_hits", [])},
            ))
        
        # Runtime-like dependency hits
        if (risk_summary.get("runtime_like_hits") or 0) > 0:
            findings.append(SemanticMemoryDecisionFinding(
                code=SemanticMemoryDecisionReasonCode.RUNTIME_LIKE_DEPENDENCY_HITS,
                severity=SemanticMemoryDecisionSeverity.WARNING,
                message=f"Operaciones runtime detectadas: {risk_summary['runtime_like_hits']}",
                evidence={"runtime_hits": risk_summary.get("runtime_hits", [])},
            ))
        
        # Fail-closed: risk summary not verified
        if not risk_summary.get("verified", False):
            findings.append(SemanticMemoryDecisionFinding(
                code=SemanticMemoryDecisionReasonCode.SECURITY_VALIDATION_REQUIRED,
                severity=SemanticMemoryDecisionSeverity.WARNING,
                message="Risk summary unknown because prior reports are not loaded (fail-closed). Manual verification required.",
                evidence={"verified": False, "note": risk_summary.get("note", "")},
            ))
        
        # Always add info finding that security is enforced
        findings.append(SemanticMemoryDecisionFinding(
            code=SemanticMemoryDecisionReasonCode.ALLOW_REAL_WRITE_STILL_FALSE,
            severity=SemanticMemoryDecisionSeverity.INFO,
            message="allow_real_write=False (bloqueado por diseño)",
            evidence={"allow_real_write": False},
        ))
        
        findings.append(SemanticMemoryDecisionFinding(
            code=SemanticMemoryDecisionReasonCode.DRY_RUN_ONLY_STILL_TRUE,
            severity=SemanticMemoryDecisionSeverity.INFO,
            message="dry_run_only=True (modo seguro activo)",
            evidence={"dry_run_only": True},
        ))
        
        # Calcular decisión
        decision = self.decide(findings)
        
        # Calcular conteos
        blocker_count = sum(1 for f in findings if f.severity == SemanticMemoryDecisionSeverity.BLOCKER)
        warning_count = sum(1 for f in findings if f.severity == SemanticMemoryDecisionSeverity.WARNING)
        info_count = sum(1 for f in findings if f.severity == SemanticMemoryDecisionSeverity.INFO)
        
        # Bloqueadores adicionales
        blockers = [
            "P2-E Commit 4D-DecisionGate: Decision gate activo",
            "allow_real_write=False por diseño",
        ]
        if blocker_count > 0:
            blockers.append(f"{blocker_count} blockers encontrados")
        
        warnings_list = [f.message for f in findings if f.severity == SemanticMemoryDecisionSeverity.WARNING]
        
        return SemanticMemoryRealWriteDecisionReport(
            decision_id=self._decision_id,
            created_at_utc=self._created_at,
            repo_root=str(self._repo_root),
            decision=decision,
            findings=findings,
            blocker_count=blocker_count,
            warning_count=warning_count,
            info_count=info_count,
            allow_real_write=False,  # SIEMPRE False
            dry_run_only=True,  # SIEMPRE True
            can_execute_real_write=False,  # SIEMPRE False
            requires_manual_review=(decision != SemanticMemoryDecision.ALLOW_MANUAL_REAL_WRITE_CANDIDATE),
            required_artifacts=required_artifacts,
            git_state=git_state,
            risk_summary=risk_summary,
            warnings=warnings_list,
            blockers=blockers,
            metadata={
                "gate_version": "P2-E-Commit-4D-DecisionGate",
                "evaluation_type": "read_only",
                "artifacts_checked": len(self.REQUIRED_ARTIFACTS),
            },
        )
    
    def check_required_artifacts(self) -> Dict[str, bool]:
        """
        Verificar que existen los artefactos requeridos.
        
        Returns:
            Dict con nombre del artefacto y si existe
        """
        result = {}
        for artifact in self.REQUIRED_ARTIFACTS:
            artifact_path = self._repo_root / artifact
            result[artifact] = artifact_path.exists()
        return result
    
    def check_git_state_read_only(self) -> Dict[str, Any]:
        """
        Verificar estado del git (read-only, no subprocess).
        
        Este método NO ejecuta git. Retorna estado unknown (fail-closed).
        Unknown != safe. No evidence != allow.
        
        Returns:
            Dict con información del estado del git (unknown/verified=False)
        """
        # NO usar subprocess - retornar estado desconocido (fail-closed)
        # Unknown git state is NOT safe - must be verified before allowing real write
        return {
            "staged_files_present": None,
            "commits_pending_vs_origin": None,
            "dirty_state": None,
            "staged_files": [],
            "modified_files": [],
            "pending_count": None,
            "verified": False,
            "note": "Git state unknown because subprocess is forbidden (fail-closed)",
        }
    
    def check_risk_summary_read_only(self) -> Dict[str, Any]:
        """
        Calcular resumen de riesgo (read-only).
        
        Este método verifica si existen reportes de clasificación
        y mapeo previos, pero NO los ejecuta.
        
        Unknown risk summary is NOT safe. Must be verified before allowing.
        
        Returns:
            Dict con resumen de riesgo (unknown/verified=False)
        """
        # Fail-closed: no evidence != safe
        # En una implementación real, esto leería reportes previos
        # Por ahora, retorna estado desconocido
        return {
            "verified": False,
            "high_risk_extra_files": None,
            "high_risk_dependency_hits": None,
            "write_like_hits": None,
            "runtime_like_hits": None,
            "extra_files": [],
            "high_risk_hits": [],
            "write_hits": [],
            "runtime_hits": [],
            "note": "Risk summary unknown because prior reports are not loaded (fail-closed)",
        }
    
    def decide(self, findings: List[SemanticMemoryDecisionFinding]) -> SemanticMemoryDecision:
        """
        Calcular decisión basada en findings.
        
        Fail-closed rules:
        1. Si hay blockers -> BLOCK_REAL_WRITE
        2. Si hay high-risk warnings -> MANUAL_REVIEW_REQUIRED
        3. Si hay warnings sin high-risk -> CANARY_NOOP_ONLY
        4. Solo si todo está limpio y verificado -> ALLOW_MANUAL_REAL_WRITE_CANDIDATE
        
        Args:
            findings: Lista de findings de la evaluación
            
        Returns:
            SemanticMemoryDecision
        """
        blocker_count = sum(1 for f in findings if f.severity == SemanticMemoryDecisionSeverity.BLOCKER)
        warning_count = sum(1 for f in findings if f.severity == SemanticMemoryDecisionSeverity.WARNING)
        
        # Check for high-risk warning codes
        high_risk_codes = {
            SemanticMemoryDecisionReasonCode.HIGH_RISK_EXTRA_FILES,
            SemanticMemoryDecisionReasonCode.HIGH_RISK_DEPENDENCY_HITS,
            SemanticMemoryDecisionReasonCode.MANUAL_REVIEW_REQUIRED,
        }
        
        has_high_risk_warning = any(
            f.severity == SemanticMemoryDecisionSeverity.WARNING and f.code in high_risk_codes
            for f in findings
        )
        
        # Rule 1: Si hay blockers, bloquear
        if blocker_count > 0:
            return SemanticMemoryDecision.BLOCK_REAL_WRITE
        
        # Rule 2: Si hay high-risk warnings, requiere revisión manual
        if has_high_risk_warning:
            return SemanticMemoryDecision.MANUAL_REVIEW_REQUIRED
        
        # Rule 3: Si hay warnings (pero no high-risk), canary noop only
        if warning_count > 0:
            return SemanticMemoryDecision.CANARY_NOOP_ONLY
        
        # Rule 4: Solo si todo está limpio y verificado, candidato para revisión manual
        # PERO recuerda: can_execute_real_write sigue siendo False
        # ALLOW_MANUAL_REAL_WRITE_CANDIDATE requiere git/risk verificados
        return SemanticMemoryDecision.ALLOW_MANUAL_REAL_WRITE_CANDIDATE
    
    def summarize_contract(self) -> Dict[str, Any]:
        """
        Resumir el contrato de seguridad del gate.
        
        Returns:
            Dict con información del contrato
        """
        return {
            "contract_version": "P2-E-Commit-4D-DecisionGate",
            "contract_type": "RealWriteDecisionGate",
            "allow_real_write": False,
            "dry_run_only": True,
            "can_execute_real_write": False,
            "requires_manual_review": True,
            "decisions": [
                "BLOCK_REAL_WRITE",
                "CANARY_NOOP_ONLY",
                "MANUAL_REVIEW_REQUIRED",
                "ALLOW_MANUAL_REAL_WRITE_CANDIDATE",
            ],
            "limitations": [
                "NO code execution",
                "NO module imports (faiss, semantic_memory_bridge)",
                "NO write operations",
                "NO subprocess",
                "NO FAISS import",
                "Static analysis only",
                "Manual review required for real write",
            ],
            "next_step": "Manual review by human operator",
        }
    
    def block_real_write(
        self,
        reason: str = "Decision gate blocked real write",
    ) -> SemanticMemoryRealWriteDecisionReport:
        """
        Bloquear explícitamente escritura real.
        
        Args:
            reason: Razón del bloqueo
            
        Returns:
            SemanticMemoryRealWriteDecisionReport bloqueado
        """
        return SemanticMemoryRealWriteDecisionReport(
            decision_id=f"blocked_{self._decision_id}",
            created_at_utc=datetime.now(timezone.utc).isoformat(),
            repo_root=str(self._repo_root),
            decision=SemanticMemoryDecision.BLOCK_REAL_WRITE,
            findings=[
                SemanticMemoryDecisionFinding(
                    code=SemanticMemoryDecisionReasonCode.SAFE_CANDIDATE_ONLY,
                    severity=SemanticMemoryDecisionSeverity.BLOCKER,
                    message=reason,
                    evidence={"block_reason": reason},
                ),
            ],
            blocker_count=1,
            warning_count=0,
            info_count=0,
            allow_real_write=False,
            dry_run_only=True,
            can_execute_real_write=False,
            requires_manual_review=True,
            required_artifacts={},
            git_state={},
            risk_summary={},
            warnings=[],
            blockers=[reason, "BLOCKED: Real write blocked by decision gate"],
            metadata={"block_reason": reason},
        )
