"""
P2-E Commit 3F: SemanticMemory Read-Only Probe

Probe read-only/dry-run para inspeccionar la infraestructura de SemanticMemory/FAISS
SIN escribir en memoria semántica, SIN modificar índices, SIN importar faiss.

Este módulo responde:
1. ¿Existe módulo/clase de SemanticMemory?
2. ¿Qué métodos públicos expone?
3. ¿Existe ruta memory/semantic?
4. ¿Existen archivos de índice/datos?
5. ¿Qué método parecería apto para futura escritura?
6. ¿Qué método parecería apto para futura lectura?
7. ¿Qué riesgos hay antes de integrar promote_real?
8. ¿Qué contrato mínimo debe cumplir el adapter futuro?

REGLAS DURAS:
- Solo lectura de archivos (Path.read_text).
- NO usar open(..., "w") ni open(..., "a").
- NO usar write_text, append_text.
- NO usar unlink, remove, rmdir.
- NO importar faiss.
- NO importar requests/httpx.
- NO construir índices.
- NO llamar endpoints.
- NO escribir en memory/semantic.
- allow_real_write=False siempre.
- dry_run_only=True siempre.
- read_only=True siempre.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import ast
import uuid


@dataclass
class SemanticMemoryProbeResult:
    """
    Resultado del probe read-only de SemanticMemory.
    
    Este dataclass contiene toda la información descubierta
    sobre la infraestructura de SemanticMemory sin modificar nada.
    """
    # Identificación
    probe_id: str
    created_at_utc: str
    repo_root: str
    
    # Paths descubiertos
    semantic_paths_found: List[str] = field(default_factory=list)
    faiss_paths_found: List[str] = field(default_factory=list)
    
    # Candidatos para integración
    candidate_modules: List[str] = field(default_factory=list)
    candidate_classes: List[str] = field(default_factory=list)
    candidate_methods: List[str] = field(default_factory=list)
    
    # Estado de memory/semantic
    memory_semantic_exists: bool = False
    memory_semantic_files: List[str] = field(default_factory=list)
    
    # Controles de seguridad - SIEMPRE True/False en este commit
    read_only: bool = True
    dry_run_only: bool = True
    allow_real_write: bool = False
    
    # Análisis de riesgos
    risks: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convertir a diccionario serializable."""
        return {
            "probe_id": self.probe_id,
            "created_at_utc": self.created_at_utc,
            "repo_root": self.repo_root,
            "semantic_paths_found": self.semantic_paths_found,
            "faiss_paths_found": self.faiss_paths_found,
            "candidate_modules": self.candidate_modules,
            "candidate_classes": self.candidate_classes,
            "candidate_methods": self.candidate_methods,
            "memory_semantic_exists": self.memory_semantic_exists,
            "memory_semantic_files": self.memory_semantic_files,
            "read_only": self.read_only,
            "dry_run_only": self.dry_run_only,
            "allow_real_write": self.allow_real_write,
            "risks": self.risks,
            "recommendations": self.recommendations,
        }


class SemanticMemoryProbe:
    """
    Probe read-only para inspeccionar infraestructura SemanticMemory.
    
    Responsabilidades:
    - Descubrir módulos y clases relacionados con SemanticMemory
    - Inspeccionar métodos públicos sin ejecutarlos
    - Verificar existencia de paths y archivos
    - Identificar riesgos antes de integración
    - Proponer contrato mínimo para adapter futuro
    
    Limitaciones (P2-E Commit 3F):
    - Solo lectura de archivos (no escribe)
    - Solo análisis estático (no importa ni ejecuta)
    - Solo inspección de paths (no modifica)
    - SIEMPRE read_only=True
    """
    
    def __init__(self, repo_root: Optional[str] = None):
        """
        Inicializar probe.
        
        Args:
            repo_root: Raíz del repositorio (default: C:\\AI_VAULT)
        """
        self._repo_root = Path(repo_root) if repo_root else Path(r"C:\AI_VAULT")
        self._probe_id = f"probe_{uuid.uuid4().hex[:16]}"
    
    def run_probe(self) -> SemanticMemoryProbeResult:
        """
        Ejecutar probe completo de inspección.
        
        Returns:
            SemanticMemoryProbeResult con toda la información descubierta
        """
        result = SemanticMemoryProbeResult(
            probe_id=self._probe_id,
            created_at_utc=datetime.now(timezone.utc).isoformat(),
            repo_root=str(self._repo_root),
            read_only=True,
            dry_run_only=True,
            allow_real_write=False,
        )
        
        # 1. Inspeccionar archivos Python
        python_inspection = self.inspect_python_files()
        result.candidate_modules = python_inspection.get("modules", [])
        result.candidate_classes = python_inspection.get("classes", [])
        result.candidate_methods = python_inspection.get("methods", [])
        
        # 2. Inspeccionar path memory/semantic
        semantic_inspection = self.inspect_memory_semantic_path()
        result.memory_semantic_exists = semantic_inspection.get("exists", False)
        result.memory_semantic_files = semantic_inspection.get("files", [])
        
        # 3. Buscar paths relacionados
        result.semantic_paths_found = self._find_semantic_paths()
        result.faiss_paths_found = self._find_faiss_paths()
        
        # 4. Analizar riesgos
        result.risks = self._analyze_risks(result)
        result.recommendations = self._generate_recommendations(result)
        
        return result
    
    def inspect_python_files(self) -> Dict[str, List[str]]:
        """
        Inspeccionar archivos Python para encontrar candidatos SemanticMemory.
        
        Returns:
            Dict con modules, classes y methods encontrados
        """
        result = {"modules": [], "classes": [], "methods": []}
        
        # Buscar archivos relevantes
        patterns = ["*semantic*.py", "*faiss*.py", "*memory*.py"]
        seen_files = set()
        
        for pattern in patterns:
            for filepath in self._repo_root.rglob(pattern):
                str_path = str(filepath)
                # Excluir .venv y archivos no relevantes
                if ".venv" in str_path or "__pycache__" in str_path:
                    continue
                if str_path not in seen_files:
                    seen_files.add(str_path)
                    
                    # Extraer nombre de módulo
                    relative = filepath.relative_to(self._repo_root)
                    module_name = str(relative.with_suffix("")).replace("\\", ".").replace("/", ".")
                    result["modules"].append(module_name)
                    
                    # Analizar AST para clases y métodos
                    try:
                        content = filepath.read_text(encoding="utf-8", errors="ignore")
                        tree = ast.parse(content)
                        
                        for node in ast.walk(tree):
                            if isinstance(node, ast.ClassDef):
                                class_name = node.name
                                result["classes"].append(f"{module_name}.{class_name}")
                                
                                # Buscar métodos públicos
                                for item in node.body:
                                    if isinstance(item, ast.FunctionDef):
                                        method_name = item.name
                                        if not method_name.startswith("_"):
                                            full_method = f"{module_name}.{class_name}.{method_name}"
                                            result["methods"].append(full_method)
                    except Exception:
                        continue
        
        return result
    
    def inspect_memory_semantic_path(self) -> Dict[str, Any]:
        """
        Inspeccionar el path memory/semantic sin modificarlo.
        
        Returns:
            Dict con exists y files encontrados
        """
        semantic_path = self._repo_root / "memory" / "semantic"
        
        result = {"exists": False, "files": []}
        
        if semantic_path.exists():
            result["exists"] = True
            
            # Solo listar archivos (no leer contenido)
            try:
                for item in semantic_path.iterdir():
                    if item.is_file():
                        result["files"].append(item.name)
            except Exception:
                pass
        
        return result
    
    def _find_semantic_paths(self) -> List[str]:
        """Encontrar paths relacionados con semantic."""
        paths = []
        
        for filepath in self._repo_root.rglob("*semantic*"):
            str_path = str(filepath)
            if ".venv" not in str_path and "__pycache__" not in str_path:
                paths.append(str_path)
        
        return paths[:20]  # Limitar a 20
    
    def _find_faiss_paths(self) -> List[str]:
        """Encontrar paths relacionados con faiss."""
        paths = []
        
        for filepath in self._repo_root.rglob("*faiss*"):
            str_path = str(filepath)
            if ".venv" not in str_path and "__pycache__" not in str_path:
                paths.append(str_path)
        
        return paths[:20]  # Limitar a 20
    
    def _analyze_risks(self, result: SemanticMemoryProbeResult) -> List[str]:
        """
        Analizar riesgos basados en la inspección.
        
        Args:
            result: Resultado del probe
            
        Returns:
            Lista de riesgos identificados
        """
        risks = []
        
        # Riesgo 1: No existe infraestructura
        if not result.memory_semantic_exists:
            risks.append("R1: No existe el directorio memory/semantic")
        
        # Riesgo 2: No hay módulos candidatos
        if not result.candidate_modules:
            risks.append("R2: No se encontraron módulos candidatos para SemanticMemory")
        
        # Riesgo 3: FAISS no disponible
        if not result.faiss_paths_found:
            risks.append("R3: No se encontraron archivos relacionados con FAISS")
        
        # Riesgo 4: Múltiples implementaciones
        if len(result.candidate_modules) > 3:
            risks.append("R4: Múltiples implementaciones candidatas - riesgo de inconsistencia")
        
        return risks
    
    def _generate_recommendations(self, result: SemanticMemoryProbeResult) -> List[str]:
        """
        Generar recomendaciones para integración futura.
        
        Args:
            result: Resultado del probe
            
        Returns:
            Lista de recomendaciones
        """
        recommendations = []
        
        recommendations.append("REC1: Validar contrato de SemanticMemory antes de escritura real")
        recommendations.append("REC2: Crear adapter dry-run que valide payloads antes de FAISS")
        recommendations.append("REC3: Implementar rollback capability antes de escritura real")
        recommendations.append("REC4: Agregar observability de operaciones SemanticMemory")
        recommendations.append("REC5: Pruebas de integración controladas con dataset pequeño")
        
        if result.candidate_modules:
            recommendations.append(f"REC6: Revisar módulos candidatos: {', '.join(result.candidate_modules[:3])}")
        
        return recommendations
    
    def validate_probe_result(self, result: SemanticMemoryProbeResult) -> bool:
        """
        Validar que el resultado del probe está bien formado.
        
        Args:
            result: Resultado a validar
            
        Returns:
            True si el resultado es válido
        """
        # Verificar probe_id
        if not result.probe_id or len(result.probe_id) == 0:
            return False
        
        # Verificar created_at_utc
        if not result.created_at_utc:
            return False
        
        # Bloquear allow_real_write=True
        if result.allow_real_write:
            return False
        
        # Verificar read_only=True
        if not result.read_only:
            return False
        
        # Verificar dry_run_only=True
        if not result.dry_run_only:
            return False
        
        return True
    
    def summarize_contract(self, result: SemanticMemoryProbeResult) -> Dict[str, Any]:
        """
        Generar resumen del contrato mínimo necesario para adapter.
        
        Args:
            result: Resultado del probe
            
        Returns:
            Dict con contrato propuesto
        """
        return {
            "required_methods": ["add_memory", "search", "get_by_id"],
            "optional_methods": ["update", "delete", "backup"],
            "input_contract": {
                "text": "str",
                "metadata": "Dict[str, Any]",
                "source": "str",
            },
            "output_contract": {
                "memory_id": "str",
                "embedding": "List[float]",
                "similarity_score": "float",
            },
            "error_handling": ["FAISS_UNAVAILABLE", "EMBEDDING_FAILED", "IO_ERROR"],
            "risks": result.risks,
            "recommendations": result.recommendations,
        }


def create_semantic_memory_probe(repo_root: Optional[str] = None) -> SemanticMemoryProbe:
    """
    Factory para crear instancia del probe.
    
    Args:
        repo_root: Raíz del repositorio (opcional)
        
    Returns:
        SemanticMemoryProbe configurado
    """
    return SemanticMemoryProbe(repo_root=repo_root)


# Ejemplo de uso (solo si se ejecuta directamente)
if __name__ == "__main__":
    probe = create_semantic_memory_probe()
    result = probe.run_probe()
    print(f"Probe ID: {result.probe_id}")
    print(f"Semantic paths found: {len(result.semantic_paths_found)}")
    print(f"FAISS paths found: {len(result.faiss_paths_found)}")
    print(f"Candidate modules: {result.candidate_modules}")
    print(f"Risks: {result.risks}")
    print(f"Recommendations: {result.recommendations}")
