"""
Project State Provider — Fuente canónica de verdad para estado P2.

Expone API local y determinística para consultar estado de P2 sin depender de LLM.
No importa session.py, main.py, FAISS ni SemanticMemoryBridge.
"""

import os
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


def _resolve_repo_root(repo_root: Optional[Path] = None) -> Path:
    """
    Resolver raíz del repositorio de forma canónica.
    
    Orden de prioridad:
    1. repo_root explícito
    2. env AI_VAULT_ROOT
    3. Derivado de __file__ (project_state_provider.py está en C:\AI_VAULT\brain\)
    4. Path.cwd() como fallback
    
    Args:
        repo_root: Raíz explícita (opcional)
        
    Returns:
        Path canónico del repo
    """
    if repo_root is not None:
        return Path(repo_root).resolve()
    
    # Intentar desde variable de entorno
    env_root = os.environ.get("AI_VAULT_ROOT")
    if env_root:
        return Path(env_root).resolve()
    
    # Derivar desde ubicación de este archivo: ...\brain\project_state_provider.py
    # El repo root es parents[1]: ...\AI_VAULT\
    try:
        return Path(__file__).resolve().parents[1]
    except Exception:
        pass
    
    # Fallback final
    return Path.cwd().resolve()


@dataclass
class P2State:
    """Estado completo del pipeline P2."""
    p2_a_completed: bool = False
    p2_b_completed: bool = False
    p2_c_completed: bool = False
    p2_d_completed: bool = False
    
    # Detección de archivos
    adapter_file_exists: bool = False
    adapter_test_exists: bool = False
    adapter_doc_exists: bool = False
    adapter_smoke_exists: bool = False
    
    # Detección de commits (opcional)
    p2_c_commit_exists: bool = False
    p2_d_commit_exists: bool = False
    p2_c_commit_hash: Optional[str] = None
    p2_d_commit_hash: Optional[str] = None
    
    # Rutas
    repo_root: Path = field(default_factory=lambda: Path.cwd())
    
    def to_dict(self) -> Dict:
        return {
            "P2-A": {"completed": self.p2_a_completed, "description": "InformationCurator contract"},
            "P2-B": {"completed": self.p2_b_completed, "description": "InformationCurator-LearningValidator contract"},
            "P2-C": {"completed": self.p2_c_completed, "description": "CurationValidationAdapter implementation"},
            "P2-D": {"completed": self.p2_d_completed, "description": "Documentation and smoke tests"},
            "files": {
                "adapter": self.adapter_file_exists,
                "adapter_test": self.adapter_test_exists,
                "adapter_doc": self.adapter_doc_exists,
                "adapter_smoke": self.adapter_smoke_exists,
            },
            "commits": {
                "p2_c": self.p2_c_commit_exists,
                "p2_d": self.p2_d_commit_exists,
            }
        }


class ProjectStateProvider:
    """
    Proveedor de estado del proyecto P2.
    
    Responsabilidades:
    - Detectar existencia de archivos canónicos
    - Opcional: consultar git log para commits
    - NO ejecuta tests
    - NO importa session/main/FAISS/SemanticMemoryBridge
    - NO afirma runtime/chat integration
    - NO afirma autoaprendizaje
    """
    
    P2_C_COMMIT_KEYWORDS = ["P2-C", "curation_validation_adapter"]
    P2_D_COMMIT_KEYWORDS = ["P2-D", "smoke", "CurationRecord validation adapter"]
    
    def __init__(self, repo_root: Optional[Path] = None):
        """
        Inicializar provider.
        
        Args:
            repo_root: Raíz del repositorio. Si es None, se resuelve canónicamente.
        """
        self.repo_root = _resolve_repo_root(repo_root)
        self._state: Optional[P2State] = None
    
    def _detect_files(self, state: P2State) -> None:
        """Detectar existencia de archivos canónicos."""
        # P2-C files
        adapter_path = self.repo_root / "brain" / "curation_validation_adapter.py"
        adapter_test_path = self.repo_root / "tests" / "unit" / "test_curation_validation_adapter.py"
        
        # P2-D files
        adapter_doc_path = self.repo_root / "docs" / "P2D_CURATION_VALIDATION_ADAPTER_USAGE.md"
        adapter_smoke_path = self.repo_root / "tests" / "smoke" / "smoke_curation_validation_adapter.py"
        
        # P2-A/B files (para completitud)
        p2a_test_path = self.repo_root / "tests" / "unit" / "test_information_curator_contract.py"
        p2b_test_path = self.repo_root / "tests" / "unit" / "test_information_curator_learning_validator_contract.py"
        
        state.adapter_file_exists = adapter_path.exists()
        state.adapter_test_exists = adapter_test_path.exists()
        state.adapter_doc_exists = adapter_doc_path.exists()
        state.adapter_smoke_exists = adapter_smoke_path.exists()
        
        # P2 completado si existen archivos
        state.p2_a_completed = p2a_test_path.exists()
        state.p2_b_completed = p2b_test_path.exists()
        state.p2_c_completed = state.adapter_file_exists and state.adapter_test_exists
        state.p2_d_completed = state.adapter_doc_exists and state.adapter_smoke_exists
    
    def _detect_commits(self, state: P2State) -> None:
        """Opcional: detectar commits P2 en git log. No falla si git no disponible."""
        try:
            result = subprocess.run(
                ["git", "log", "--oneline", "-50"],
                cwd=self.repo_root,
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode != 0:
                return
            
            log = result.stdout
            
            # Buscar P2-C
            for line in log.split("\n"):
                if "P2-C" in line or "curation_validation_adapter" in line.lower():
                    state.p2_c_commit_exists = True
                    # Extraer hash (primeros 8 chars)
                    parts = line.split()
                    if parts:
                        state.p2_c_commit_hash = parts[0]
                    break
            
            # Buscar P2-D
            for line in log.split("\n"):
                if "P2-D" in line or "smoke" in line.lower():
                    state.p2_d_commit_exists = True
                    parts = line.split()
                    if parts:
                        state.p2_d_commit_hash = parts[0]
                    break
                    
        except Exception:
            # Silenciosamente ignorar si git no disponible
            pass
    
    def get_p2_state(self, force_refresh: bool = False) -> P2State:
        """
        Obtener estado P2 actual.
        
        Args:
            force_refresh: Forzar recálculo aunque exista cache.
            
        Returns:
            P2State con estado detectado.
        """
        if self._state is None or force_refresh:
            state = P2State(repo_root=self.repo_root)
            self._detect_files(state)
            self._detect_commits(state)
            self._state = state
        return self._state
    
    def summarize_p2_state(self) -> str:
        """
        Resumen ejecutivo del estado P2.
        NO afirma runtime/chat integration.
        NO afirma FAISS/SemanticMemoryBridge.
        """
        state = self.get_p2_state()
        
        lines = [
            "Estado Pipeline P2 (fuente: archivos locales):",
            "",
        ]
        
        if state.p2_a_completed:
            lines.append("P2-A: Completado (InformationCurator contract)")
        else:
            lines.append("P2-A: No detectado")
            
        if state.p2_b_completed:
            lines.append("P2-B: Completado (InformationCurator-LearningValidator contract)")
        else:
            lines.append("P2-B: No detectado")
        
        if state.p2_c_completed:
            lines.append("P2-C: Completado (CurationValidationAdapter implementado)")
            if state.p2_c_commit_hash:
                lines.append(f"       Commit: {state.p2_c_commit_hash}")
            lines.append(f"       Archivos: adapter.py + test unitario")
        else:
            lines.append("P2-C: No detectado (faltan archivos)")
        
        if state.p2_d_completed:
            lines.append("P2-D: Completado (documentación + smoke tests)")
            if state.p2_d_commit_hash:
                lines.append(f"       Commit: {state.p2_d_commit_hash}")
            lines.append(f"       Archivos: docs/P2D_*.md + tests/smoke/*.py")
        else:
            lines.append("P2-D: No detectado (faltan archivos)")
        
        lines.append("")
        lines.append("Notas de arquitectura:")
        lines.append("- P2-C/P2-D son adapters/documentación, no conexión a runtime/chat.")
        lines.append("- El adapter NO escribe en SemanticMemoryBridge ni FAISS.")
        lines.append("- El adapter NO activa autoaprendizaje.")
        
        return "\n".join(lines)
    
    def explain_curation_adapter(self) -> str:
        """
        Explicar qué hace el CurationValidationAdapter.
        NO afirma que escriba en FAISS/memoria semántica.
        """
        state = self.get_p2_state()
        
        if not state.p2_c_completed:
            return (
                "No puedo confirmar estado P2-C desde fuente canónica local en este turno. "
                "No debo inventarlo."
            )
        
        return (
            "El CurationValidationAdapter conecta CuratedRecord (InformationCurator) con "
            "LearningValidator mediante una interfaz explícita.\n\n"
            "Responsabilidades:\n"
            "- Convierte CuratedRecord -> llamada a LearningValidator.validate()\n"
            "- Preserva trazabilidad: record_id, source, content_hash, topic\n"
            "- Retorna CurationValidationResult con estado VALIDATED/REJECTED/UNVALIDATED/ERROR\n\n"
            "Qué NO hace:\n"
            "- NO valida automáticamente al ingresar (requiere llamada explícita)\n"
            "- NO modifica record.validated_at (sigue None después de validar)\n"
            "- NO escribe en SemanticMemoryBridge\n"
            "- NO escribe en FAISS\n"
            "- NO conecta runtime/chat\n"
            "- NO activa autoaprendizaje\n\n"
            "Flujo esperado:\n"
            "1. curator.ingest_text() -> crea CuratedRecord\n"
            "2. adapter.validate_record(record) -> valida explícitamente\n"
            "3. Revisar result.status -> decidir manualmente promover o no"
        )
    
    def explain_smoke_command(self) -> str:
        """
        Explicar cómo ejecutar smoke test P2-D.
        """
        state = self.get_p2_state()
        
        if not state.p2_d_completed:
            return (
                "No puedo confirmar estado P2-D desde fuente canónica local en este turno. "
                "No debo inventarlo."
            )
        
        return (
            "Para probar localmente el smoke de P2-D:\n\n"
            "python tests/smoke/smoke_curation_validation_adapter.py\n\n"
            "Este script:\n"
            "- Crea un CuratedRecord mediante ingest_text()\n"
            "- Usa un FakeLearningValidator determinístico\n"
            "- Llama adapter.validate_record()\n"
            "- Verifica preservación de trazabilidad\n"
            "- Confirma validated_at sigue None\n"
            "- Verifica NO imports prohibidos\n\n"
            "Resultado esperado: SMOKE_CURATION_VALIDATION_ADAPTER_OK"
        )
    
    def explain_auto_learning_status(self) -> str:
        """
        Explicar estado de autoaprendizaje.
        SIEMPRE niega autoaprendizaje automático.
        """
        state = self.get_p2_state()
        
        lines = [
            "Estado de autoaprendizaje:",
            "",
            "NO hay autoaprendizaje automático implementado ni activado.",
            "",
            "Razones:",
            "- P2-C/P2-D son adapters/documentación, no conectores automáticos.",
            "- El adapter NO escribe en SemanticMemoryBridge ni FAISS.",
            "- No hay pipeline de promoción automática de registros validados.",
            "",
        ]
        
        if state.p2_c_completed and state.p2_d_completed:
            lines.append(
                "Para promover un registro curado validado a memoria semántica, "
                "se requiere decisión manual explícita (fuera de alcance P2)."
            )
        else:
            lines.append(
                "No puedo confirmar estado P2 desde fuente canónica local. "
                "No afirmaré que hay autoaprendizaje disponible."
            )
        
        lines.append("")
        lines.append(
            "Verificación: P2-E/P3 requieren diseño y autorización explícita "
            "antes de conectar a SemanticMemoryBridge/FAISS."
        )
        
        return "\n".join(lines)

    def answer_project_state_query(self, message: str) -> Optional[str]:
        """
        Router de estado del proyecto. Responde queries P2/adapter/FAISS/smoke/etc.
        
        Args:
            message: Mensaje del usuario
            
        Returns:
            Respuesta si es query conocida, None si no aplica
        """
        import re

        msg = (message or "").lower().strip()

        def any_match(patterns):
            return any(re.search(p, msg, re.IGNORECASE) for p in patterns)

        smoke_patterns = [
            r"smoke_curation_validation_adapter\.py",
            r"\bsmoke\b",
            r"como\s+pruebo",
            r"c[oó]mo\s+pruebo",
            r"probar\s+localmente",
            r"prueba\s+local",
            r"p2-d.*smoke",
            r"smoke.*p2-d",
        ]
        if any_match(smoke_patterns):
            return self.explain_smoke_command()

        auto_learning_patterns = [
            r"aprender\s+automaticamente",
            r"aprender\s+autom[aá]ticamente",
            r"autoaprendizaje",
            r"fuentes\s+curadas",
            r"meter.*memoria\s+semantica",
            r"meter.*memoria\s+sem[aá]ntica",
            r"promover\s+automaticamente",
            r"promoci[oó]n\s+autom[aá]tica",
        ]
        if any_match(auto_learning_patterns):
            return self.explain_auto_learning_status()

        faiss_patterns = [
            r"semanticmemorybridge",
            r"\bfaiss\b",
            r"memoria\s+semantica",
            r"memoria\s+sem[aá]ntica",
            r"escribe.*memoria",
            r"escribe.*faiss",
            r"escribe.*semanticmemorybridge",
        ]
        if any_match(faiss_patterns):
            return (
                "No. El adapter NO escribe en SemanticMemoryBridge ni FAISS. "
                "No hay promoción automática de registros validados a memoria semántica. "
                "P2-C/P2-D son adapter, documentación y smoke local; no son conectores automáticos a runtime."
            )

        ingest_patterns = [
            r"ingest_text",
            r"ingiere\s+contenido",
            r"ingerir\s+contenido",
            r"valida\s+automaticamente",
            r"valida\s+autom[aá]ticamente",
            r"auto.?valida",
        ]
        if any_match(ingest_patterns):
            return (
                "No. InformationCurator.ingest_text NO valida automáticamente. "
                "La validación requiere una llamada explícita a adapter.validate_record(record). "
                "El CuratedRecord mantiene validated_at=None; no se promueve automáticamente."
            )

        adapter_patterns = [
            r"que\s+hace\s+el\s+adapter",
            r"qu[eé]\s+hace\s+el\s+adapter",
            r"adapter.*curatedrecord",
            r"curatedrecord.*learningvalidator",
            r"adapter.*learningvalidator",
            r"adapter\s+curatedrecord",
        ]
        if any_match(adapter_patterns):
            return self.explain_curation_adapter()

        p2_status_patterns = [
            r"\bp2-a\b",
            r"\bp2-b\b",
            r"\bp2-c\b",
            r"\bp2-d\b",
            r"estado\s+actual.*p2",
            r"estado.*p2",
            r"resume.*p2",
            r"pipeline\s+p2",
            r"informationcurator.*learningvalidator",
            r"learningvalidator.*informationcurator",
        ]
        if any_match(p2_status_patterns):
            return self.summarize_p2_state()

        return None


# Factory function para uso simple
def create_project_state_provider(repo_root: Optional[Path] = None) -> ProjectStateProvider:
    """Crear provider con repo_root opcional."""
    return ProjectStateProvider(repo_root=repo_root)
