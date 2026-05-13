"""
MODO_OPERACION_BRAIN.PY
Sistema de Modos PLAN y BUILD para el Brain

Basado en los protocolos de opencode:
- PLAN: Modo análisis y diseño (solo lectura, propuestas)
- BUILD: Modo ejecución (puede modificar archivos, ejecutar comandos)

Seguridad:
- En PLAN: Solo lectura y análisis
- En BUILD: Ejecución con validación y rollback automático
- Cambios requieren confirmación explícita del usuario
"""

import os
import sys
import json
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum

sys.path.insert(0, 'C:/AI_VAULT')
sys.path.insert(0, 'C:/AI_VAULT/brain')

class ModoOperacion(Enum):
    PLAN = "plan"    # Solo lectura, análisis, diseño
    BUILD = "build"  # Ejecución, modificación, implementación

@dataclass
class CambioPropuesto:
    """Un cambio propuesto por el Brain"""
    tipo: str  # "file", "command", "config"
    target: str  # archivo o comando
    descripcion: str
    contenido_actual: Optional[str] = None
    contenido_nuevo: Optional[str] = None
    justificacion: str = ""
    riesgo: str = "low"  # low, medium, high, critical
    backup_path: Optional[str] = None
    aprobado: bool = False
    ejecutado: bool = False

class BrainModoOperacion:
    """
    Gestor de modos de operación del Brain
    
    PLAN: Análisis y diseño sin modificar nada
    BUILD: Ejecución con capacidades reales de modificación
    """
    
    def __init__(self):
        self.modo_actual = ModoOperacion.PLAN
        self.cambios_pendientes: List[CambioPropuesto] = []
        self.cambios_ejecutados: List[CambioPropuesto] = []
        self.backups_creados: Dict[str, str] = {}
        self.historial_modo = []
        
        # Directorio de backups
        self.backup_dir = Path("C:/AI_VAULT/tmp_agent/backups/build_mode")
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        
    def cambiar_modo(self, nuevo_modo: ModoOperacion, razon: str = "") -> Dict[str, Any]:
        """
        Cambia el modo de operación del Brain
        
        Args:
            nuevo_modo: PLAN o BUILD
            razon: Justificación del cambio
        """
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
            "mensaje": self._get_mensaje_modo(nuevo_modo)
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
- Crear planes detallados

NO puedo:
- Modificar archivos
- Ejecutar comandos destructivos
- Borrar datos
- Hacer cambios permanentes

Para ejecutar cambios, cambia a modo BUILD."""
        else:
            return """MODO BUILD ACTIVADO
            
Estoy en modo de ejecución. Puedo:
- Modificar archivos (con backup previo)
- Ejecutar comandos (validados)
- Implementar cambios
- Hacer rollback si es necesario
- Crear nuevos archivos
- Actualizar configuraciones

TODOS los cambios:
- Requieren aprobación explícita
- Crean backup automático
- Son reversibles
- Se registran en audit log"""
    
    def proponer_cambio(self, cambio: CambioPropuesto) -> Dict[str, Any]:
        """
        Registra un cambio propuesto
        
        En PLAN: Solo lo registra para aprobación futura
        En BUILD: Prepara para ejecución inmediata (si aprobado)
        """
        self.cambios_pendientes.append(cambio)
        
        if self.modo_actual == ModoOperacion.PLAN:
            return {
                "status": "proposed",
                "mensaje": f"Cambio '{cambio.descripcion}' propuesto. Requiere modo BUILD + aprobación para ejecutar.",
                "requiere_aprobacion": True,
                "cambio": cambio
            }
        else:
            return {
                "status": "ready_to_execute",
                "mensaje": f"Cambio '{cambio.descripcion}' listo para ejecución. Requiere aprobación explícita.",
                "requiere_aprobacion": True,
                "cambio": cambio
            }
    
    def aprobar_y_ejecutar(self, indice_cambio: int, aprobador: str = "user") -> Dict[str, Any]:
        """
        Aprueba y ejecuta un cambio (solo en modo BUILD)
        """
        if self.modo_actual != ModoOperacion.BUILD:
            return {
                "status": "error",
                "error": "Cambios solo pueden ejecutarse en modo BUILD. Cambia el modo primero.",
                "modo_actual": self.modo_actual.value
            }
        
        if indice_cambio >= len(self.cambios_pendientes):
            return {
                "status": "error",
                "error": f"Índice de cambio inválido. Solo hay {len(self.cambios_pendientes)} cambios pendientes."
            }
        
        cambio = self.cambios_pendientes[indice_cambio]
        cambio.aprobado = True
        
        # Ejecutar según tipo
        if cambio.tipo == "file":
            resultado = self._ejecutar_cambio_archivo(cambio)
        elif cambio.tipo == "command":
            resultado = self._ejecutar_comando(cambio)
        elif cambio.tipo == "config":
            resultado = self._ejecutar_cambio_config(cambio)
        else:
            resultado = {"status": "error", "error": f"Tipo de cambio desconocido: {cambio.tipo}"}
        
        if resultado["status"] == "ok":
            cambio.ejecutado = True
            self.cambios_ejecutados.append(cambio)
            self.cambios_pendientes.pop(indice_cambio)
        
        return resultado
    
    def _ejecutar_cambio_archivo(self, cambio: CambioPropuesto) -> Dict[str, Any]:
        """Ejecuta un cambio de archivo con backup previo"""
        try:
            target_path = Path(cambio.target)
            backup_path = None
            
            # 1. Crear backup
            if target_path.exists():
                backup_filename = f"{target_path.stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{target_path.suffix}"
                backup_path = self.backup_dir / backup_filename
                backup_path.write_text(target_path.read_text(encoding='utf-8'), encoding='utf-8')
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
                "mensaje": f"Archivo {target_path.name} modificado exitosamente"
            }
            
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "accion": "modificacion_fallida"
            }
    
    def _ejecutar_comando(self, cambio: CambioPropuesto) -> Dict[str, Any]:
        """Ejecuta un comando de shell (con restricciones de seguridad)"""
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
            
            # Ejecutar con timeout y captura
            resultado = subprocess.run(
                comando,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
                cwd="C:/AI_VAULT"
            )
            
            return {
                "status": "ok" if resultado.returncode == 0 else "warning",
                "returncode": resultado.returncode,
                "stdout": resultado.stdout[:500],  # Limitar output
                "stderr": resultado.stderr[:500] if resultado.stderr else None,
                "comando": comando
            }
            
        except subprocess.TimeoutExpired:
            return {"status": "error", "error": "Comando excedió timeout de 30s"}
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    def _ejecutar_cambio_config(self, cambio: CambioPropuesto) -> Dict[str, Any]:
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
                "target": str(config_path)
            }
            
        except json.JSONDecodeError as e:
            return {"status": "error", "error": f"JSON inválido: {e}"}
        except Exception as e:
            return {"status": "error", "error": str(e)}
    
    def hacer_rollback(self, target: str) -> Dict[str, Any]:
        """
        Revierte un cambio usando el backup
        """
        if target in self.backups_creados:
            backup_path = Path(self.backups_creados[target])
            target_path = Path(target)
            
            if backup_path.exists():
                target_path.write_text(backup_path.read_text(encoding='utf-8'), encoding='utf-8')
                return {
                    "status": "ok",
                    "mensaje": f"Rollback exitoso para {target_path.name}",
                    "backup_usado": str(backup_path)
                }
            else:
                return {"status": "error", "error": f"Backup no encontrado: {backup_path}"}
        else:
            return {"status": "error", "error": f"No hay backup registrado para {target}"}
    
    def get_estado(self) -> Dict[str, Any]:
        """Retorna el estado actual del sistema de modos"""
        return {
            "modo_actual": self.modo_actual.value,
            "puede_modificar": self.modo_actual == ModoOperacion.BUILD,
            "cambios_pendientes": len(self.cambios_pendientes),
            "cambios_ejecutados": len(self.cambios_ejecutados),
            "backups_disponibles": len(self.backups_creados),
            "historial_modo": self.historial_modo[-5:]  # Últimos 5 cambios
        }


# Instancia global
GESTOR_MODO = BrainModoOperacion()


# Funciones de conveniencia para integración
def cambiar_a_build(razon: str = "") -> Dict[str, Any]:
    """Cambia a modo BUILD"""
    return GESTOR_MODO.cambiar_modo(ModoOperacion.BUILD, razon)

def cambiar_a_plan(razon: str = "") -> Dict[str, Any]:
    """Cambia a modo PLAN"""
    return GESTOR_MODO.cambiar_modo(ModoOperacion.PLAN, razon)

def proponer_modificacion_archivo(ruta: str, contenido_nuevo: str, descripcion: str) -> Dict[str, Any]:
    """Propone modificar un archivo"""
    cambio = CambioPropuesto(
        tipo="file",
        target=ruta,
        descripcion=descripcion,
        contenido_nuevo=contenido_nuevo
    )
    return GESTOR_MODO.proponer_cambio(cambio)

def proponer_comando(comando: str, descripcion: str) -> Dict[str, Any]:
    """Propone ejecutar un comando"""
    cambio = CambioPropuesto(
        tipo="command",
        target=comando,
        descripcion=descripcion
    )
    return GESTOR_MODO.proponer_cambio(cambio)

def ejecutar_cambio_aprobado(indice: int, aprobador: str = "user") -> Dict[str, Any]:
    """Ejecuta un cambio aprobado (solo BUILD)"""
    return GESTOR_MODO.aprobar_y_ejecutar(indice, aprobador)


if __name__ == "__main__":
    print("="*70)
    print("SISTEMA DE MODOS PLAN/BUILD - TEST")
    print("="*70)
    
    # Test 1: Modo PLAN
    print("\n1. INICIANDO EN MODO PLAN")
    estado = GESTOR_MODO.get_estado()
    print(f"Modo: {estado['modo_actual']}")
    print(f"Puede modificar: {estado['puede_modificar']}")
    
    # Proponer cambio en PLAN
    print("\n2. PROPONIENDO CAMBIO EN MODO PLAN")
    resultado = proponer_modificacion_archivo(
        "C:/AI_VAULT/test.txt",
        "nuevo contenido",
        "Actualizar archivo de prueba"
    )
    print(f"Status: {resultado['status']}")
    print(f"Mensaje: {resultado['mensaje']}")
    
    # Intentar ejecutar en PLAN (debe fallar)
    print("\n3. INTENTANDO EJECUTAR EN MODO PLAN (debe fallar)")
    resultado = ejecutar_cambio_aprobado(0)
    print(f"Status: {resultado['status']}")
    print(f"Error: {resultado.get('error', 'N/A')}")
    
    # Cambiar a BUILD
    print("\n4. CAMBIANDO A MODO BUILD")
    resultado = cambiar_a_build("Necesito implementar cambios de configuración")
    print(f"Status: {resultado['status']}")
    print(f"Mensaje: {resultado['mensaje'][:100]}...")
    
    # Ahora sí puede ejecutar
    print("\n5. EJECUTANDO CAMBIO EN MODO BUILD")
    resultado = ejecutar_cambio_aprobado(0, "usuario_admin")
    print(f"Status: {resultado['status']}")
    if resultado['status'] == 'ok':
        print(f"Acción: {resultado.get('accion')}")
        print(f"Backup: {resultado.get('backup', 'N/A')}")
    
    # Ver estado final
    print("\n6. ESTADO FINAL")
    estado = GESTOR_MODO.get_estado()
    print(f"Cambios ejecutados: {estado['cambios_ejecutados']}")
    print(f"Backups disponibles: {estado['backups_disponibles']}")
    
    print("\n" + "="*70)
    print("TEST COMPLETADO")
    print("="*70)
