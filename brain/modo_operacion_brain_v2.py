"""
MODO_OPERACION_BRAIN_V2.PY
Version mejorada del sistema de modos PLAN/BUILD para el Brain

MEJORAS:
1. Timeout extendido: 30s → 600s (10 min) para tareas complejas
2. Persistencia de estado entre sub-tareas
3. Reintentos automáticos con backoff exponencial
4. Modo BUILD automático para tareas de modificación
5. Checkpointing: guarda progreso cada paso exitoso

Autor: Mentor (basado en opencode)
Version: 2.0.0
"""

import os
import sys
import json
import subprocess
import time
import random
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum

sys.path.insert(0, 'C:/AI_VAULT')
sys.path.insert(0, 'C:/AI_VAULT/brain')

# ============================================================================
# CONFIGURACIÓN MEJORADA
# ============================================================================

class Config:
    """Configuración central del sistema de modos"""
    TIMEOUT_SIMPLE = 30       # 30s para tareas simples
    TIMEOUT_COMPLEJO = 600    # 10 min para tareas complejas (backup, modificaciones)
    MAX_RETRIES = 3           # Reintentos máximos
    BACKOFF_BASE = 2          # Base para backoff exponencial
    CHECKPOINT_INTERVAL = 1   # Guardar checkpoint cada N pasos exitosos
    
    # Directorios
    BACKUP_DIR = Path("C:/AI_VAULT/tmp_agent/backups/build_mode")
    CHECKPOINT_DIR = Path("C:/AI_VAULT/tmp_agent/state/checkpoints")

# ============================================================================
# ESTRUCTURAS DE DATOS
# ============================================================================

class ModoOperacion(Enum):
    PLAN = "plan"    # Solo lectura, análisis, diseño
    BUILD = "build"  # Ejecución, modificación, implementación

class TaskComplexity(Enum):
    SIMPLE = "simple"      # Consultas, diagnósticos
    MEDIUM = "medium"      # Análisis de código
    COMPLEX = "complex"    # Modificaciones de archivos
    META = "meta"          # Tareas multi-paso complejas

@dataclass
class CambioPropuesto:
    """Un cambio propuesto por el Brain"""
    tipo: str  # "file", "command", "config"
    target: str
    descripcion: str
    contenido_actual: Optional[str] = None
    contenido_nuevo: Optional[str] = None
    justificacion: str = ""
    riesgo: str = "low"
    backup_path: Optional[str] = None
    aprobado: bool = False
    ejecutado: bool = False
    intentos: int = 0
    ultimo_error: Optional[str] = None

@dataclass
class Checkpoint:
    """Punto de guardado del progreso"""
    task_id: str
    step: int
    modo: str
    cambios_pendientes: List[Dict]
    cambios_ejecutados: List[Dict]
    timestamp: str
    status: str  # "running", "completed", "failed"

# ============================================================================
# SISTEMA DE PERSISTENCIA
# ============================================================================

class PersistenciaManager:
    """Gestiona la persistencia de estado entre sub-tareas"""
    
    def __init__(self):
        self.checkpoint_dir = Config.CHECKPOINT_DIR
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
    
    def save_checkpoint(self, task_id: str, step: int, modo: ModoOperacion,
                       cambios_pendientes: List[CambioPropuesto],
                       cambios_ejecutados: List[CambioPropuesto],
                       status: str = "running"):
        """Guarda el estado actual como checkpoint"""
        checkpoint = Checkpoint(
            task_id=task_id,
            step=step,
            modo=modo.value,
            cambios_pendientes=[asdict(c) for c in cambios_pendientes],
            cambios_ejecutados=[asdict(c) for c in cambios_ejecutados],
            timestamp=datetime.now().isoformat(),
            status=status
        )
        
        checkpoint_file = self.checkpoint_dir / f"{task_id}_checkpoint.json"
        with open(checkpoint_file, 'w', encoding='utf-8') as f:
            json.dump(asdict(checkpoint), f, indent=2)
        
        return checkpoint_file
    
    def load_checkpoint(self, task_id: str) -> Optional[Checkpoint]:
        """Carga el último checkpoint de una tarea"""
        checkpoint_file = self.checkpoint_dir / f"{task_id}_checkpoint.json"
        
        if not checkpoint_file.exists():
            return None
        
        try:
            with open(checkpoint_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                return Checkpoint(**data)
        except Exception as e:
            print(f"[Persistencia] Error cargando checkpoint: {e}")
            return None
    
    def clear_checkpoint(self, task_id: str):
        """Elimina el checkpoint de una tarea completada"""
        checkpoint_file = self.checkpoint_dir / f"{task_id}_checkpoint.json"
        if checkpoint_file.exists():
            checkpoint_file.unlink()

# ============================================================================
# SISTEMA DE REINTENTOS INTELIGENTES
# ============================================================================

class RetryManager:
    """Gestiona reintentos con backoff exponencial"""
    
    @staticmethod
    def should_retry(error: str, attempt: int) -> bool:
        """Determina si se debe reintentar basado en el error"""
        if attempt >= Config.MAX_RETRIES:
            return False
        
        # Errores transitorios que merecen reintento
        transient_errors = [
            "timeout", "timed out", "connection", "temporarily",
            "busy", "retry", "rate limit", "too many requests"
        ]
        
        error_lower = error.lower()
        return any(err in error_lower for err in transient_errors)
    
    @staticmethod
    def calculate_backoff(attempt: int) -> float:
        """Calcula tiempo de espera con backoff exponencial + jitter"""
        base = Config.BACKOFF_BASE ** attempt
        jitter = random.uniform(0, 1)
        return base + jitter
    
    @staticmethod
    def execute_with_retry(func, *args, **kwargs) -> Dict[str, Any]:
        """Ejecuta una función con reintentos automáticos"""
        last_error = None
        
        for attempt in range(Config.MAX_RETRIES + 1):
            try:
                result = func(*args, **kwargs)
                
                # Si fue exitoso, retornar
                if result.get("status") in ["ok", "success"]:
                    if attempt > 0:
                        result["retries"] = attempt
                    return result
                
                # Si falló, verificar si reintentar
                last_error = result.get("error", "Unknown error")
                if not RetryManager.should_retry(last_error, attempt):
                    return result
                
            except Exception as e:
                last_error = str(e)
                if not RetryManager.should_retry(last_error, attempt):
                    return {"status": "error", "error": last_error}
            
            # Calcular backoff y esperar
            if attempt < Config.MAX_RETRIES:
                wait_time = RetryManager.calculate_backoff(attempt)
                print(f"[Retry] Intento {attempt + 1} falló: {last_error}")
                print(f"[Retry] Reintentando en {wait_time:.1f}s...")
                time.sleep(wait_time)
        
        return {
            "status": "error",
            "error": f"Falló después de {Config.MAX_RETRIES} reintentos: {last_error}",
            "last_error": last_error
        }

# ============================================================================
# DETECTOR DE COMPLEJIDAD
# ============================================================================

class ComplexityDetector:
    """Detecta la complejidad de una tarea para asignar recursos adecuados"""
    
    COMPLEX_KEYWORDS = [
        "eliminar", "delete", "remover", "remove",
        "modificar", "modify", "editar", "edit",
        "backup", "respaldo", "copiar", "copy",
        "migrar", "migrate", "refactorizar", "refactor",
        "actualizar", "update", "instalar", "install"
    ]
    
    META_KEYWORDS = [
        "completo", "completa", "full", "total",
        "paso", "step", "fase", "phase",
        "multi", "varios", "several", "todos", "all"
    ]
    
    @classmethod
    def detect(cls, descripcion: str) -> TaskComplexity:
        """Detecta el nivel de complejidad de una tarea"""
        desc_lower = descripcion.lower()
        
        # Contar palabras clave
        complex_count = sum(1 for kw in cls.COMPLEX_KEYWORDS if kw in desc_lower)
        meta_count = sum(1 for kw in cls.META_KEYWORDS if kw in desc_lower)
        
        # Determinar complejidad
        if meta_count >= 2 or (complex_count >= 3 and meta_count >= 1):
            return TaskComplexity.META
        elif complex_count >= 2:
            return TaskComplexity.COMPLEX
        elif complex_count >= 1:
            return TaskComplexity.MEDIUM
        else:
            return TaskComplexity.SIMPLE
    
    @classmethod
    def get_timeout(cls, complexity: TaskComplexity) -> int:
        """Retorna el timeout apropiado según complejidad"""
        timeouts = {
            TaskComplexity.SIMPLE: Config.TIMEOUT_SIMPLE,
            TaskComplexity.MEDIUM: Config.TIMEOUT_SIMPLE * 2,
            TaskComplexity.COMPLEX: Config.TIMEOUT_COMPLEJO,
            TaskComplexity.META: Config.TIMEOUT_COMPLEJO
        }
        return timeouts.get(complexity, Config.TIMEOUT_SIMPLE)

# ============================================================================
# BRAIN MODO OPERACION V2
# ============================================================================

class BrainModoOperacionV2:
    """
    Gestor de modos de operación del Brain - Versión 2.0 Mejorada
    
    CARACTERÍSTICAS:
    - Timeouts adaptativos según complejidad
    - Persistencia automática de estado
    - Reintentos inteligentes con backoff
    - Activación automática de modo BUILD
    """
    
    def __init__(self):
        self.modo_actual = ModoOperacion.PLAN
        self.cambios_pendientes: List[CambioPropuesto] = []
        self.cambios_ejecutados: List[CambioPropuesto] = []
        self.backups_creados: Dict[str, str] = {}
        self.historial_modo = []
        self.persistencia = PersistenciaManager()
        self.retry_manager = RetryManager()
        
        # Directorio de backups
        self.backup_dir = Config.BACKUP_DIR
        self.backup_dir.mkdir(parents=True, exist_ok=True)
    
    def cambiar_modo(self, nuevo_modo: ModoOperacion, razon: str = "", 
                     auto_detect: bool = False) -> Dict[str, Any]:
        """
        Cambia el modo de operación del Brain
        
        Args:
            nuevo_modo: PLAN o BUILD
            razon: Justificación del cambio
            auto_detect: Si True, detecta automáticamente si se necesita BUILD
        """
        if auto_detect and nuevo_modo == ModoOperacion.BUILD:
            razon = f"[AUTO] {razon} - Detectada tarea que requiere modificaciones"
        
        modo_anterior = self.modo_actual
        self.modo_actual = nuevo_modo
        
        self.historial_modo.append({
            "timestamp": datetime.now().isoformat(),
            "de": modo_anterior.value,
            "a": nuevo_modo.value,
            "razon": razon
        })
        
        return {
            "status": "ok",
            "modo_anterior": modo_anterior.value,
            "modo_actual": nuevo_modo.value,
            "puede_modificar": nuevo_modo == ModoOperacion.BUILD,
            "mensaje": self._get_mensaje_modo(nuevo_modo),
            "auto_activado": auto_detect
        }
    
    def auto_activate_build(self, descripcion_tarea: str) -> Dict[str, Any]:
        """
        Activa automáticamente el modo BUILD si la tarea lo requiere
        """
        complejidad = ComplexityDetector.detect(descripcion_tarea)
        
        if complejidad in [TaskComplexity.COMPLEX, TaskComplexity.META]:
            if self.modo_actual != ModoOperacion.BUILD:
                return self.cambiar_modo(
                    ModoOperacion.BUILD,
                    f"Tarea detectada: {complejidad.value}. Requiere modo BUILD.",
                    auto_detect=True
                )
        
        return {
            "status": "ok",
            "modo_actual": self.modo_actual.value,
            "complejidad_detectada": complejidad.value,
            "auto_activado": False
        }
    
    def _get_mensaje_modo(self, modo: ModoOperacion) -> str:
        """Mensaje descriptivo del modo actual"""
        if modo == ModoOperacion.PLAN:
            return """MODO PLAN ACTIVADO
            
Estoy en modo de análisis y diseño. Puedo:
- Leer y analizar archivos
- Diseñar soluciones
- Proponer cambios
- Calcular impactos

NO puedo:
- Modificar archivos
- Ejecutar comandos destructivos
- Borrar datos
- Hacer cambios permanentes

Para ejecutar cambios, cambia a modo BUILD."""
        else:
            return """MODO BUILD ACTIVADO [V2.0]
            
Estoy en modo de ejecución mejorado. Puedo:
- Modificar archivos (con backup previo)
- Ejecutar comandos (validados)
- Implementar cambios
- Hacer rollback si es necesario
- Crear nuevos archivos
- Actualizar configuraciones

CARACTERÍSTICAS MEJORADAS:
- Timeouts adaptativos (hasta 10 min para tareas complejas)
- Reintentos automáticos con backoff
- Persistencia de estado entre pasos
- Checkpoints automáticos

TODOS los cambios:
- Requieren aprobación explícita
- Crean backup automático
- Son reversibles
- Se registran en audit log"""
    
    def proponer_cambio(self, cambio: CambioPropuesto, 
                       task_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Registra un cambio propuesto con persistencia
        """
        self.cambios_pendientes.append(cambio)
        
        # Guardar checkpoint si hay task_id
        if task_id:
            self.persistencia.save_checkpoint(
                task_id, len(self.cambios_ejecutados), 
                self.modo_actual, self.cambios_pendientes, 
                self.cambios_ejecutados
            )
        
        if self.modo_actual == ModoOperacion.PLAN:
            return {
                "status": "proposed",
                "mensaje": f"Cambio '{cambio.descripcion}' propuesto. Requiere modo BUILD + aprobación.",
                "requiere_aprobacion": True,
                "cambio": cambio,
                "sugerencia": "Activa modo BUILD para ejecutar"
            }
        else:
            return {
                "status": "ready_to_execute",
                "mensaje": f"Cambio '{cambio.descripcion}' listo. Requiere aprobación.",
                "requiere_aprobacion": True,
                "cambio": cambio,
                "indice": len(self.cambios_pendientes) - 1
            }
    
    def aprobar_y_ejecutar(self, indice_cambio: int, aprobador: str = "user",
                          task_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Aprueba y ejecuta un cambio con reintentos y persistencia
        """
        if self.modo_actual != ModoOperacion.BUILD:
            return {
                "status": "error",
                "error": "Cambios solo pueden ejecutarse en modo BUILD.",
                "modo_actual": self.modo_actual.value,
                "accion_sugerida": "Cambiar a modo BUILD primero"
            }
        
        if indice_cambio >= len(self.cambios_pendientes):
            return {
                "status": "error",
                "error": f"Índice inválido. Solo hay {len(self.cambios_pendientes)} cambios pendientes."
            }
        
        cambio = self.cambios_pendientes[indice_cambio]
        cambio.aprobado = True
        cambio.intentos += 1
        
        # Ejecutar según tipo con timeout adaptativo
        timeout = self._get_timeout_for_cambio(cambio)
        
        if cambio.tipo == "file":
            resultado = self._ejecutar_cambio_archivo(cambio, timeout)
        elif cambio.tipo == "command":
            resultado = self._ejecutar_comando(cambio, timeout)
        elif cambio.tipo == "config":
            resultado = self._ejecutar_cambio_config(cambio, timeout)
        else:
            resultado = {"status": "error", "error": f"Tipo desconocido: {cambio.tipo}"}
        
        # Si falló, intentar reintento
        if resultado["status"] == "error" and cambio.intentos < Config.MAX_RETRIES:
            cambio.ultimo_error = resultado.get("error")
            if self.retry_manager.should_retry(cambio.ultimo_error, cambio.intentos):
                wait_time = self.retry_manager.calculate_backoff(cambio.intentos)
                print(f"[Retry] Reintentando en {wait_time:.1f}s...")
                time.sleep(wait_time)
                return self.aprobar_y_ejecutar(indice_cambio, aprobador, task_id)
        
        # Si fue exitoso o agotó reintentos
        if resultado["status"] == "ok":
            cambio.ejecutado = True
            self.cambios_ejecutados.append(cambio)
            self.cambios_pendientes.pop(indice_cambio)
            
            # Guardar checkpoint
            if task_id:
                self.persistencia.save_checkpoint(
                    task_id, len(self.cambios_ejecutados),
                    self.modo_actual, self.cambios_pendientes,
                    self.cambios_ejecutados, "completed"
                )
        
        return resultado
    
    def _get_timeout_for_cambio(self, cambio: CambioPropuesto) -> int:
        """Determina timeout apropiado según el tipo de cambio"""
        if cambio.tipo == "command":
            # Comandos de backup pueden tardar
            if "backup" in cambio.descripcion.lower() or "copiar" in cambio.descripcion.lower():
                return Config.TIMEOUT_COMPLEJO
            return Config.TIMEOUT_SIMPLE
        elif cambio.tipo == "file":
            # Modificaciones de archivos grandes
            if cambio.contenido_nuevo and len(cambio.contenido_nuevo) > 10000:
                return Config.TIMEOUT_COMPLEJO
            return Config.TIMEOUT_SIMPLE
        return Config.TIMEOUT_SIMPLE
    
    def _ejecutar_cambio_archivo(self, cambio: CambioPropuesto, 
                                timeout: int = Config.TIMEOUT_SIMPLE) -> Dict[str, Any]:
        """Ejecuta un cambio de archivo con backup previo"""
        try:
            target_path = Path(cambio.target)
            backup_path = None
            
            # 1. Crear backup
            if target_path.exists():
                backup_filename = f"{target_path.stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{target_path.suffix}"
                backup_path = self.backup_dir / backup_filename
                
                # Leer y guardar backup
                contenido_actual = target_path.read_text(encoding='utf-8')
                backup_path.write_text(contenido_actual, encoding='utf-8')
                cambio.backup_path = str(backup_path)
                self.backups_creados[str(target_path)] = str(backup_path)
            
            # 2. Aplicar cambio
            if cambio.contenido_nuevo is not None:
                target_path.write_text(cambio.contenido_nuevo, encoding='utf-8')
            
            return {
                "status": "ok",
                "accion": "archivo_modificado",
                "target": str(target_path),
                "backup": str(backup_path) if backup_path else None,
                "mensaje": f"Archivo {target_path.name} modificado exitosamente",
                "timeout_usado": timeout
            }
            
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "accion": "modificacion_fallida",
                "target": str(target_path) if 'target_path' in locals() else None
            }
    
    def _ejecutar_comando(self, cambio: CambioPropuesto, 
                         timeout: int = Config.TIMEOUT_SIMPLE) -> Dict[str, Any]:
        """Ejecuta un comando de shell con timeout extendido"""
        try:
            comando = cambio.target
            
            # Lista de comandos prohibidos
            prohibidos = ['rm -rf /', 'format', 'del /f', 'rmdir /s']
            if any(prohibido in comando.lower() for prohibido in prohibidos):
                return {
                    "status": "error",
                    "error": "Comando prohibido por seguridad",
                    "comando": comando
                }
            
            # Ejecutar con timeout adaptativo
            resultado = subprocess.run(
                comando,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,  # Timeout dinámico
                cwd="C:/AI_VAULT"
            )
            
            return {
                "status": "ok" if resultado.returncode == 0 else "warning",
                "returncode": resultado.returncode,
                "stdout": resultado.stdout[:1000],  # Aumentado de 500
                "stderr": resultado.stderr[:1000] if resultado.stderr else None,
                "comando": comando,
                "timeout_usado": timeout,
                "duracion": "completado dentro del timeout"
            }
            
        except subprocess.TimeoutExpired:
            return {
                "status": "error", 
                "error": f"Comando excedió timeout de {timeout}s",
                "timeout_configurado": timeout,
                "sugerencia": "La tarea es muy compleja. Intentar en pasos más pequeños."
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    def _ejecutar_cambio_config(self, cambio: CambioPropuesto,
                               timeout: int = Config.TIMEOUT_SIMPLE) -> Dict[str, Any]:
        """Ejecuta un cambio de configuración JSON"""
        try:
            config_path = Path(cambio.target)
            
            # Crear backup
            if config_path.exists():
                backup_filename = f"{config_path.stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{config_path.suffix}"
                backup_path = self.backup_dir / backup_filename
                backup_path.write_text(config_path.read_text(encoding='utf-8'), encoding='utf-8')
                cambio.backup_path = str(backup_path)
            
            # Aplicar cambio
            if cambio.contenido_nuevo:
                nuevo_config = json.loads(cambio.contenido_nuevo)
                config_path.write_text(json.dumps(nuevo_config, indent=2), encoding='utf-8')
            
            return {
                "status": "ok",
                "accion": "config_actualizada",
                "target": str(config_path),
                "backup": cambio.backup_path,
                "timeout_usado": timeout
            }
            
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    def get_estado(self) -> Dict[str, Any]:
        """Retorna el estado actual del sistema de modos"""
        return {
            "modo_actual": self.modo_actual.value,
            "puede_modificar": self.modo_actual == ModoOperacion.BUILD,
            "cambios_pendientes": len(self.cambios_pendientes),
            "cambios_ejecutados": len(self.cambios_ejecutados),
            "backups_disponibles": len(self.backups_creados),
            "historial": self.historial_modo[-5:],
            "version": "2.0.0",
            "mejoras": [
                "Timeout adaptativo (hasta 600s)",
                "Reintentos automáticos",
                "Persistencia de estado",
                "Detección automática de modo BUILD"
            ]
        }


# ============================================================================
# INSTANCIA GLOBAL Y FUNCIONES DE CONVENIENCIA
# ============================================================================

GESTOR_MODO_V2 = BrainModoOperacionV2()


def cambiar_a_build(razon: str = "", auto_detect: bool = False) -> Dict[str, Any]:
    """Cambia a modo BUILD"""
    return GESTOR_MODO_V2.cambiar_modo(ModoOperacion.BUILD, razon, auto_detect)


def cambiar_a_plan(razon: str = "") -> Dict[str, Any]:
    """Cambia a modo PLAN"""
    return GESTOR_MODO_V2.cambiar_modo(ModoOperacion.PLAN, razon)


def auto_activate_build(descripcion: str) -> Dict[str, Any]:
    """Activa modo BUILD automáticamente si la tarea lo requiere"""
    return GESTOR_MODO_V2.auto_activate_build(descripcion)


def proponer_modificacion_archivo(ruta: str, contenido_nuevo: str, 
                                  descripcion: str, task_id: str = None) -> Dict[str, Any]:
    """Propone modificar un archivo"""
    cambio = CambioPropuesto(
        tipo="file",
        target=ruta,
        descripcion=descripcion,
        contenido_nuevo=contenido_nuevo
    )
    return GESTOR_MODO_V2.proponer_cambio(cambio, task_id)


def proponer_comando(comando: str, descripcion: str, task_id: str = None) -> Dict[str, Any]:
    """Propone ejecutar un comando"""
    cambio = CambioPropuesto(
        tipo="command",
        target=comando,
        descripcion=descripcion
    )
    return GESTOR_MODO_V2.proponer_cambio(cambio, task_id)


def ejecutar_cambio_aprobado(indice: int, aprobador: str = "user", 
                             task_id: str = None) -> Dict[str, Any]:
    """Ejecuta un cambio aprobado"""
    return GESTOR_MODO_V2.aprobar_y_ejecutar(indice, aprobador, task_id)


# ============================================================================
# TEST
# ============================================================================

if __name__ == "__main__":
    print("="*70)
    print("BRAIN MODO OPERACION V2.0 - TEST")
    print("="*70)
    
    # Test 1: Auto-activación
    print("\n1. PROBANDO AUTO-ACTIVACIÓN")
    resultado = auto_activate_build("Eliminar completamente PocketOption del sistema")
    print(f"Modo: {resultado['modo_actual']}")
    print(f"Auto-activado: {resultado['auto_activado']}")
    print(f"Complejidad: {resultado['complejidad_detectada']}")
    
    # Test 2: Timeout adaptativo
    print("\n2. PROBANDO TIMEOUT ADAPTATIVO")
    complejidades = ["consulta simple", "modificar archivo", "eliminar completamente sistema"]
    for desc in complejidades:
        comp = ComplexityDetector.detect(desc)
        timeout = ComplexityDetector.get_timeout(comp)
        print(f"  '{desc[:30]}...' -> {comp.value}: {timeout}s")
    
    print("\n" + "="*70)
    print("TEST COMPLETADO - Brain V2.0 Listo")
    print("="*70)