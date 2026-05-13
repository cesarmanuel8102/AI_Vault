"""
CHAT_MODO_CONTROL.PY
Interfaz de chat para controlar modos PLAN/BUILD

Comandos disponibles:
- /modo plan          -> Cambiar a modo PLAN
- /modo build         -> Cambiar a modo BUILD  
- /modo estado        -> Ver modo actual
- /ejecutar [n]       -> Ejecutar cambio #n (solo BUILD)
- /rollback [archivo] -> Revertir cambio
- /cambios            -> Listar cambios pendientes
"""

import sys
sys.path.insert(0, 'C:/AI_VAULT')
sys.path.insert(0, 'C:/AI_VAULT/brain')

from modo_operacion_brain import (
    GESTOR_MODO, 
    cambiar_a_build, 
    cambiar_a_plan,
    ModoOperacion
)

class ChatModoControl:
    """Controlador de modos desde el chat"""
    
    def __init__(self):
        self.gestor = GESTOR_MODO
    
    def procesar_comando(self, comando: str, args: list = None) -> dict:
        """Procesa comandos de modo desde el chat"""
        args = args or []
        comando = comando.lower().strip()
        
        if comando == "/modo":
            return self._cmd_modo(args)
        elif comando == "/ejecutar":
            return self._cmd_ejecutar(args)
        elif comando == "/rollback":
            return self._cmd_rollback(args)
        elif comando == "/cambios":
            return self._cmd_cambios()
        elif comando == "/ayuda":
            return self._cmd_ayuda()
        else:
            return {"error": f"Comando desconocido: {comando}. Usa /ayuda para ver comandos."}
    
    def _cmd_modo(self, args: list) -> dict:
        """Comando /modo [plan|build|estado]"""
        if not args:
            # Mostrar estado actual
            estado = self.gestor.get_estado()
            return {
                "tipo": "estado_modo",
                "modo_actual": estado['modo_actual'],
                "puede_modificar": estado['puede_modificar'],
                "cambios_pendientes": estado['cambios_pendientes'],
                "mensaje": self._format_estado(estado)
            }
        
        subcomando = args[0].lower()
        
        if subcomando == "plan":
            resultado = cambiar_a_plan("Solicitado por usuario desde chat")
            return {
                "tipo": "cambio_modo",
                "accion": "cambio_a_plan",
                "resultado": resultado,
                "mensaje": f"✓ Modo cambiado a PLAN\n{resultado.get('mensaje', '')}"
            }
        
        elif subcomando == "build":
            resultado = cambiar_a_build("Solicitado por usuario desde chat")
            return {
                "tipo": "cambio_modo",
                "accion": "cambio_a_build",
                "resultado": resultado,
                "mensaje": f"✓ Modo cambiado a BUILD\n{resultado.get('mensaje', '')}"
            }
        
        elif subcomando == "estado":
            estado = self.gestor.get_estado()
            return {
                "tipo": "estado_detallado",
                "estado": estado,
                "mensaje": self._format_estado_detallado(estado)
            }
        
        else:
            return {"error": f"Subcomando '{subcomando}' no reconocido. Usa: plan, build, o estado"}
    
    def _cmd_ejecutar(self, args: list) -> dict:
        """Comando /ejecutar [indice]"""
        if self.gestor.modo_actual != ModoOperacion.BUILD:
            return {
                "tipo": "error",
                "error": "❌ No se puede ejecutar en modo PLAN",
                "solucion": "Cambia a modo BUILD primero: /modo build"
            }
        
        if not args:
            return {"error": "Uso: /ejecutar [número_cambio]. Usa /cambios para ver lista."}
        
        try:
            indice = int(args[0])
            from modo_operacion_brain import ejecutar_cambio_aprobado
            resultado = ejecutar_cambio_aprobado(indice, "usuario_chat")
            
            if resultado['status'] == 'ok':
                return {
                    "tipo": "ejecucion_exitosa",
                    "cambio": indice,
                    "resultado": resultado,
                    "mensaje": f"✓ Cambio #{indice} ejecutado exitosamente\n{resultado.get('mensaje', '')}"
                }
            else:
                return {
                    "tipo": "ejecucion_fallida",
                    "cambio": indice,
                    "error": resultado.get('error', 'Error desconocido'),
                    "resultado": resultado
                }
        except ValueError:
            return {"error": f"'{args[0]}' no es un número válido"}
        except Exception as e:
            return {"error": f"Error ejecutando cambio: {str(e)}"}
    
    def _cmd_rollback(self, args: list) -> dict:
        """Comando /rollback [archivo]"""
        if not args:
            return {"error": "Uso: /rollback [ruta_archivo]"}
        
        target = " ".join(args)  # Por si la ruta tiene espacios
        resultado = self.gestor.hacer_rollback(target)
        
        return {
            "tipo": "rollback",
            "target": target,
            "resultado": resultado,
            "mensaje": resultado.get('mensaje', resultado.get('error', 'Resultado desconocido'))
        }
    
    def _cmd_cambios(self) -> dict:
        """Comando /cambios - lista cambios pendientes"""
        estado = self.gestor.get_estado()
        cambios = self.gestor.cambios_pendientes
        
        if not cambios:
            return {
                "tipo": "lista_cambios",
                "cantidad": 0,
                "mensaje": "No hay cambios pendientes."
            }
        
        lista = []
        for i, cambio in enumerate(cambios):
            lista.append(f"{i}. {cambio.descripcion} [{cambio.tipo}] - {cambio.riesgo} risk")
        
        return {
            "tipo": "lista_cambios",
            "cantidad": len(cambios),
            "cambios": lista,
            "modo_actual": estado['modo_actual'],
            "mensaje": f"Cambios pendientes ({len(cambios)}):\n" + "\n".join(lista)
        }
    
    def _cmd_ayuda(self) -> dict:
        """Comando /ayuda"""
        ayuda = """COMANDOS DISPONIBLES:

📊 GESTIÓN DE MODOS:
/modo plan              -> Cambiar a modo PLAN (solo lectura)
/modo build             -> Cambiar a modo BUILD (ejecución)
/modo estado            -> Ver estado detallado del modo

⚡ EJECUCIÓN (solo BUILD):
/ejecutar [n]           -> Ejecutar cambio #n aprobado
/cambios                -> Listar cambios pendientes
/rollback [archivo]      -> Revertir cambio usando backup

💡 INFORMACIÓN:
/ayuda                  -> Mostrar esta ayuda

EJEMPLOS:
• /modo build
• /cambios
• /ejecutar 0
• /modo plan

MODO PLAN vs BUILD:
• PLAN: Análisis, diseño, propuestas (sin modificar)
• BUILD: Ejecución real con backup y rollback"""
        
        return {
            "tipo": "ayuda",
            "mensaje": ayuda
        }
    
    def _format_estado(self, estado: dict) -> str:
        """Formatea estado para mostrar"""
        modo = estado['modo_actual']
        if modo == 'build':
            return f"🔧 MODO BUILD (ejecución)\nPuede modificar: {estado['puede_modificar']}"
        else:
            return f"📋 MODO PLAN (análisis)\nPuede modificar: {estado['puede_modificar']}"
    
    def _format_estado_detallado(self, estado: dict) -> str:
        """Formatea estado detallado"""
        lines = [
            f"Modo actual: {estado['modo_actual'].upper()}",
            f"Puede modificar: {'✓ Sí' if estado['puede_modificar'] else '✗ No'}",
            f"Cambios pendientes: {estado['cambios_pendientes']}",
            f"Cambios ejecutados: {estado['cambios_ejecutados']}",
            f"Backups disponibles: {estado['backups_disponibles']}"
        ]
        return "\n".join(lines)


# Instancia global
CHAT_MODO = ChatModoControl()


# Funciones de conveniencia para el endpoint
def procesar_comando_chat(mensaje: str) -> dict:
    """
    Punto de entrada para procesar comandos desde el chat
    
    Args:
        mensaje: Mensaje completo del usuario (ej: "/modo build")
    
    Returns:
        Dict con respuesta procesada
    """
    # Separar comando y argumentos
    partes = mensaje.split()
    if not partes:
        return {"error": "Mensaje vacío"}
    
    comando = partes[0]
    args = partes[1:] if len(partes) > 1 else []
    
    return CHAT_MODO.procesar_comando(comando, args)


if __name__ == "__main__":
    print("="*70)
    print("DEMO: Control de Modos desde Chat")
    print("="*70)
    
    # Demo 1: Ver estado inicial
    print("\n1. USUARIO: /modo estado")
    resultado = procesar_comando_chat("/modo estado")
    print(f"BRAIN:\n{resultado['mensaje']}")
    
    # Demo 2: Cambiar a BUILD
    print("\n2. USUARIO: /modo build")
    resultado = procesar_comando_chat("/modo build")
    print(f"BRAIN:\n{resultado['mensaje']}")
    
    # Demo 3: Ver cambios
    print("\n3. USUARIO: /cambios")
    resultado = procesar_comando_chat("/cambios")
    print(f"BRAIN:\n{resultado['mensaje']}")
    
    # Demo 4: Intentar ejecutar sin cambios
    print("\n4. USUARIO: /ejecutar 0")
    resultado = procesar_comando_chat("/ejecutar 0")
    print(f"BRAIN:\n{resultado.get('mensaje') or resultado.get('error')}")
    
    # Demo 5: Cambiar a PLAN
    print("\n5. USUARIO: /modo plan")
    resultado = procesar_comando_chat("/modo plan")
    print(f"BRAIN:\n{resultado['mensaje']}")
    
    # Demo 6: Intentar ejecutar en PLAN
    print("\n6. USUARIO: /ejecutar 0 (en modo PLAN)")
    resultado = procesar_comando_chat("/ejecutar 0")
    print(f"BRAIN:\n{resultado.get('error', 'Error desconocido')}")
    
    # Demo 7: Mostrar ayuda
    print("\n7. USUARIO: /ayuda")
    resultado = procesar_comando_chat("/ayuda")
    print(f"BRAIN:\n{resultado['mensaje']}")
    
    print("\n" + "="*70)
    print("DEMO COMPLETADO")
    print("="*70)
