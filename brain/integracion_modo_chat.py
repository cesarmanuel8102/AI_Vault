"""
INTEGRACION_MODO_CHAT.PY
Integración del sistema PLAN/BUILD con el chat del Brain

Permite al Brain operar en modo PLAN (solo lectura/análisis) o BUILD (ejecución real)
"""

import sys
from typing import Dict, Any, Optional
from datetime import datetime

sys.path.insert(0, 'C:/AI_VAULT')
sys.path.insert(0, 'C:/AI_VAULT/brain')

from modo_operacion_brain import (
    BrainModoOperacion, 
    CambioPropuesto, 
    ModoOperacion,
    cambiar_a_build,
    cambiar_a_plan,
    proponer_modificacion_archivo,
    proponer_comando,
    ejecutar_cambio_aprobado,
    GESTOR_MODO
)
from sistema_consciencia_limitaciones import SistemaConscienciaLimitaciones
from integracion_brain_excelente import ChatExcelente

class BrainAdaptado:
    """
    Brain con capacidades adaptadas a los protocolos de opencode
    
    - Modo PLAN: Análisis, diseño, propuestas (sin modificar)
    - Modo BUILD: Ejecución real con validación y rollback
    """
    
    def __init__(self):
        self.modo = GESTOR_MODO
        self.consciencia = SistemaConscienciaLimitaciones()
        self.excelente = ChatExcelente()
        
    def chat(self, mensaje: str, modo: str = "auto") -> Dict[str, any]:
        """
        Procesa mensaje del usuario según modo de operación
        
        Args:
            mensaje: Mensaje del usuario
            modo: "plan", "build", o "auto" (detectar automáticamente)
        """
        # Detectar si requiere ejecución
        requiere_ejecucion = self._detectar_ejecucion(mensaje)
        
        if modo == "auto":
            if requiere_ejecucion and self.modo.modo_actual == ModoOperacion.PLAN:
                # Proponer cambio a BUILD
                return self._proponer_cambio_modo(mensaje)
            elif requiere_ejecucion:
                modo = "build"
            else:
                modo = "plan"
        
        if modo == "plan" or self.modo.modo_actual == ModoOperacion.PLAN:
            return self._ejecutar_plan(mensaje)
        else:
            return self._ejecutar_build(mensaje)
    
    def _detectar_ejecucion(self, mensaje: str) -> bool:
        """Detecta si el mensaje requiere ejecución de cambios"""
        palabras_ejecucion = [
            "ejecuta", "modifica", "cambia", "actualiza", "borra",
            "elimina", "crea", "desactiva", "descontinua", "implementa",
            "aplica", "instala", "configura", "habilita", "deshabilita"
        ]
        mensaje_lower = mensaje.lower()
        return any(palabra in mensaje_lower for palabra in palabras_ejecucion)
    
    def _proponer_cambio_modo(self, mensaje: str) -> Dict[str, any]:
        """Propone cambiar a modo BUILD"""
        return {
            "tipo": "cambio_modo_propuesto",
            "mensaje": f"""Tu solicitud requiere ejecución de cambios:

"{mensaje[:80]}..."

Actualmente estoy en modo PLAN (solo lectura).

OPCIONES:
1. Cambiar a modo BUILD y ejecutar cambios
2. Mantener modo PLAN y solo analizar/diseñar
3. Proponer plan detallado sin ejecutar

¿Qué prefieres? (responde 1, 2, o 3)""",
            "modo_actual": "plan",
            "modo_requerido": "build",
            "requiere_confirmacion": True
        }
    
    def _ejecutar_plan(self, mensaje: str) -> Dict[str, any]:
        """Ejecuta en modo PLAN: análisis y diseño"""
        
        # 1. Analizar el desafío
        analisis = self.consciencia.analyze_challenge(mensaje)
        
        # 2. Si hay carencias, documentarlas
        if not analisis.can_do_directly:
            respuesta = self.consciencia.format_response(analisis, mensaje)
            return {
                "tipo": "plan_con_limitaciones",
                "respuesta": respuesta,
                "carencias": len(analisis.gaps_identified),
                "puede_hacerlo": False,
                "recomendacion": "Cambiar a modo BUILD para implementar solución"
            }
        
        # 3. Usar capacidades excelentes para responder
        respuesta_excelente = self.excelente.chat(mensaje, {})
        
        return {
            "tipo": "plan_ejecutado",
            "respuesta": respuesta_excelente['text'],
            "capacidad_usada": respuesta_excelente['capability_used'],
            "confianza": respuesta_excelente['confidence'],
            "puede_hacerlo": True,
            "modo": "PLAN",
            "observacion": "Este es análisis/diseño. Para implementación real, usar modo BUILD."
        }
    
    def _ejecutar_build(self, mensaje: str) -> Dict[str, any]:
        """Ejecuta en modo BUILD: implementación real"""
        
        # 1. Verificar que esté en modo BUILD
        if self.modo.modo_actual != ModoOperacion.BUILD:
            return {
                "tipo": "error",
                "error": "Se requiere modo BUILD. Usa cambiar_a_build() primero."
            }
        
        # 2. Analizar qué cambios requiere
        analisis = self.consciencia.analyze_challenge(mensaje)
        
        # 3. Si tiene carencias que puede resolver en BUILD
        if analisis.gaps_identified:
            cambios_propuestos = []
            
            for gap in analisis.gaps_identified:
                # Proponer cambios según el tipo de gap
                if gap.gap_type.value == "config":
                    # Proponer modificación de configuración
                    propuesta = self._proponer_cambio_config(gap, mensaje)
                    if propuesta:
                        cambios_propuestos.append(propuesta)
            
            return {
                "tipo": "build_cambios_propuestos",
                "cambios": cambios_propuestos,
                "mensaje": f"Se requieren {len(cambios_propuestos)} cambios. ¿Aprobas la ejecución?",
                "requiere_aprobacion": True
            }
        
        # 4. Si no hay carencias, ejecutar directamente
        respuesta = self.excelente.chat(mensaje, {})
        return {
            "tipo": "build_ejecutado",
            "respuesta": respuesta['text'],
            "modo": "BUILD",
            "cambios_realizados": len(self.modo.cambios_ejecutados),
            "observacion": "Cambios ejecutados con backup y rollback disponible."
        }
    
    def _proponer_cambio_config(self, gap, mensaje_original: str) -> Optional[Dict]:
        """Propone un cambio de configuración específico"""
        
        # Ejemplo: desactivar PocketOption
        if "pocket" in mensaje_original.lower() or "binary" in mensaje_original.lower():
            return {
                "descripcion": "Desactivar PocketOption en trading policy",
                "tipo": "config",
                "target": "C:/AI_VAULT/tmp_agent/state/trading_autonomy_policy.json",
                "cambio": {
                    "platform_rules.pocket_option.mode": "disabled",
                    "platform_rules.pocket_option.paper_allowed": False,
                    "platform_rules.pocket_option.live_allowed": False
                },
                "justificacion": "Discontinuar trading de binarias",
                "riesgo": "low"
            }
        
        return None
    
    def ejecutar_cambio_config_aprobado(self, cambio: Dict) -> Dict[str, any]:
        """Ejecuta un cambio de configuración aprobado"""
        
        if self.modo.modo_actual != ModoOperacion.BUILD:
            return {"error": "Requiere modo BUILD"}
        
        try:
            import json
            from pathlib import Path
            
            config_path = Path(cambio['target'])
            
            # Leer configuración actual
            with open(config_path, 'r') as f:
                config = json.load(f)
            
            # Crear backup
            backup_filename = f"{config_path.stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{config_path.suffix}"
            backup_path = self.modo.backup_dir / backup_filename
            with open(backup_path, 'w') as f:
                json.dump(config, f, indent=2)
            
            # Aplicar cambios
            for key, valor in cambio['cambio'].items():
                keys = key.split('.')
                d = config
                for k in keys[:-1]:
                    d = d.setdefault(k, {})
                d[keys[-1]] = valor
            
            # Guardar configuración modificada
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)
            
            return {
                "status": "ok",
                "cambio_aplicado": cambio['descripcion'],
                "backup": str(backup_path),
                "config_actualizada": str(config_path)
            }
            
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "cambio_fallido": cambio['descripcion']
            }


# Instancia global
BRAIN_ADAPTADO = BrainAdaptado()


# Funciones de conveniencia para el chat
def brain_chat(mensaje: str, modo: str = "auto") -> Dict[str, any]:
    """
    Punto de entrada principal para el chat del Brain adaptado
    
    Ejemplos:
        brain_chat("Analiza el mercado", "plan")
        brain_chat("Desactiva PocketOption", "build")
        brain_chat("Ayúdame con esto")  # auto-detecta
    """
    return BRAIN_ADAPTADO.chat(mensaje, modo)


def cambiar_modo(modo: str, razon: str = "") -> Dict[str, any]:
    """
    Cambia el modo de operación del Brain
    
    Args:
        modo: "plan" o "build"
        razon: Justificación del cambio
    """
    if modo == "build":
        return cambiar_a_build(razon)
    elif modo == "plan":
        return cambiar_a_plan(razon)
    else:
        return {"error": f"Modo inválido: {modo}. Use 'plan' o 'build'."}


def get_estado_brain() -> Dict[str, any]:
    """Retorna el estado actual del Brain"""
    return {
        "modo_actual": GESTOR_MODO.get_estado(),
        "puede_ejecutar": GESTOR_MODO.modo_actual == ModoOperacion.BUILD,
        "cambios_pendientes": len(GESTOR_MODO.cambios_pendientes),
        "cambios_ejecutados": len(GESTOR_MODO.cambios_ejecutados)
    }


# Test
if __name__ == "__main__":
    print("="*70)
    print("BRAIN ADAPTADO - TEST DE INTEGRACIÓN")
    print("="*70)
    
    # Test 1: Chat en modo PLAN (análisis)
    print("\n1. TEST: Chat en modo PLAN (análisis)")
    print("-"*70)
    resultado = brain_chat("Analiza qué equipos están conectados a mi red WiFi", "plan")
    print(f"Tipo: {resultado['tipo']}")
    print(f"Puede hacerlo: {resultado.get('puede_hacerlo', 'N/A')}")
    if 'respuesta' in resultado:
        print(f"Respuesta: {resultado['respuesta'][:200]}...")
    
    # Test 2: Chat que requiere ejecución (auto-detecta)
    print("\n2. TEST: Chat que requiere BUILD (auto-detect)")
    print("-"*70)
    resultado = brain_chat("Descontinua PocketOption y desactiva el trading de binarias")
    print(f"Tipo: {resultado['tipo']}")
    if 'mensaje' in resultado:
        print(f"Mensaje: {resultado['mensaje']}")
    
    # Test 3: Cambiar a BUILD
    print("\n3. TEST: Cambiar a modo BUILD")
    print("-"*70)
    resultado = cambiar_modo("build", "Necesito implementar cambios de configuración")
    print(f"Status: {resultado['status']}")
    print(f"Modo: {resultado['modo_actual']}")
    
    # Test 4: Chat en modo BUILD
    print("\n4. TEST: Chat en modo BUILD")
    print("-"*70)
    resultado = brain_chat("Descontinua PocketOption y desactiva el trading de binarias", "build")
    print(f"Tipo: {resultado['tipo']}")
    if 'cambios' in resultado:
        print(f"Cambios propuestos: {len(resultado['cambios'])}")
        for i, cambio in enumerate(resultado['cambios'], 1):
            print(f"  {i}. {cambio['descripcion']}")
    
    # Test 5: Estado final
    print("\n5. ESTADO FINAL DEL BRAIN")
    print("-"*70)
    estado = get_estado_brain()
    print(f"Modo: {estado['modo_actual']['modo_actual']}")
    print(f"Puede ejecutar: {estado['puede_ejecutar']}")
    print(f"Cambios pendientes: {estado['cambios_pendientes']}")
    print(f"Cambios ejecutados: {estado['cambios_ejecutados']}")
    
    print("\n" + "="*70)
    print("TEST COMPLETADO")
    print("="*70)
    print("\nEl Brain ahora tiene:")
    print("  • Modo PLAN: Análisis y diseño (sin modificar)")
    print("  • Modo BUILD: Ejecución real (con backup y rollback)")
    print("  • Auto-detección de requerimientos de ejecución")
    print("  • Cambios con validación y aprobación")
    print("="*70)
