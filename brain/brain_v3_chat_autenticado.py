"""
BRAIN_V3_CHAT_AUTENTICADO.PY
Brain V3.0 con autenticación de desarrollador integrada en el chat

FLUJO:
1. Usuario hace solicitud en chat
2. Brain detecta restricción  
3. Brain pide autenticación de desarrollador
4. Usuario proporciona: usuario, password, MFA, testigos
5. Brain autentica y elimina restricciones
6. Brain ejecuta tarea solicitada
7. Todo auditado
"""

import sys
import os
sys.path.insert(0, 'C:/AI_VAULT')
sys.path.insert(0, 'C:/AI_VAULT/brain')

from brain_v3_integrado_chat import BrainV3Integrado, procesar_con_brain_v3, BRAIN_V3_INTEGRADO
from protocolo_autenticacion_desarrollador import (
    ProtocoloAutenticacionDesarrollador,
    PrivilegeLevel
)
from datetime import datetime
from typing import Dict, List, Optional, Any


class BrainV3ChatAutenticado:
    """
    Brain V3.0 con autenticación integrada en el flujo del chat
    """
    
    def __init__(self):
        self.brain_base = BRAIN_V3_INTEGRADO  # Usar instancia existente
        self.protocolo = ProtocoloAutenticacionDesarrollador()
        self.sesion_autenticada = None
        self.restricciones_eliminadas = False
        
    def procesar_mensaje_chat(self, mensaje: str, session_id: str = "default", 
                               credenciales: Dict = None) -> Dict[str, Any]:
        """
        Procesa mensaje del chat con soporte para autenticación de desarrollador
        
        Args:
            mensaje: Mensaje del usuario
            session_id: ID de sesión
            credenciales: Dict con {username, password, mfa_code, witnesses} (opcional)
        
        Returns:
            Resultado del procesamiento
        """
        print(f"\n[Brain V3 Chat] Procesando: '{mensaje[:60]}...'")
        
        # Si ya hay sesión autenticada y restricciones eliminadas, ejecutar directo
        if self.sesion_autenticada and self.restricciones_eliminadas:
            print("[+] Modo desarrollador activo. Ejecutando sin restricciones...")
            return self._ejecutar_sin_restricciones(mensaje, session_id)
        
        # Verificar si es comando de autenticación DIRECTAMENTE
        mensaje_lower = mensaje.lower()
        es_comando_auth = (
            "autenticar:" in mensaje_lower or 
            "usuario=" in mensaje_lower and "password=" in mensaje_lower
        )
        
        # Si es comando de autenticación, procesarlo primero
        if es_comando_auth:
            print("[!] Comando de autenticación detectado.")
            
            # Extraer credenciales del mensaje si no se proporcionaron
            if not credenciales:
                credenciales = self._extraer_credenciales(mensaje)
            
            if credenciales:
                return self._intentar_autenticar_y_ejecutar(
                    mensaje, session_id, credenciales, {}
                )
            else:
                return self._solicitar_autenticacion_desarrollador({"solicitud": mensaje})
        
        # Detectar si es tarea sensible que requiere autenticación
        if self._es_tarea_sensible(mensaje):
            print("[!] Tarea sensible detectada. Requiere autenticación de desarrollador.")
            
            if credenciales:
                # Usuario proporcionó credenciales, intentar autenticar
                return self._intentar_autenticar_y_ejecutar(
                    mensaje, session_id, credenciales, {}
                )
            else:
                # No hay credenciales, pedir autenticación
                return self._solicitar_autenticacion_desarrollador({"solicitud": mensaje})
        
        # Procesar normalmente (puede pedir autenticación)
        resultado = self.brain_base.procesar_solicitud(mensaje, session_id)
        
        # Si está bloqueado por restricciones, ofrecer autenticación
        if resultado.get("status") == "blocked":
            if credenciales:
                # Usuario proporcionó credenciales, intentar autenticar
                return self._intentar_autenticar_y_ejecutar(
                    mensaje, session_id, credenciales, resultado
                )
            else:
                # No hay credenciales, pedir autenticación
                return self._solicitar_autenticacion_desarrollador(resultado)
        
        return resultado
    
    def _extraer_credenciales(self, mensaje: str) -> Optional[Dict]:
        """Extrae credenciales del mensaje de forma robusta"""
        import re
        
        # Patrones más flexibles
        usuario_match = re.search(r'usuario[=:]\s*(\S+)', mensaje, re.IGNORECASE)
        password_match = re.search(r'password[=:]\s*(\S+)', mensaje, re.IGNORECASE)
        mfa_match = re.search(r'mfa[=:]\s*(\S+)', mensaje, re.IGNORECASE)
        testigos_match = re.search(r'testigos\[=\s*([^\]]+)', mensaje, re.IGNORECASE)
        
        if usuario_match and password_match and mfa_match:
            return {
                "username": usuario_match.group(1),
                "password": password_match.group(1),
                "mfa_code": mfa_match.group(1),
                "witnesses": testigos_match.group(1).split(',') if testigos_match else ["witness_1", "witness_2"]
            }
        return None
    
    def _es_tarea_sensible(self, mensaje: str) -> bool:
        """Detecta si es una tarea que requiere autenticación de desarrollador"""
        mensaje_lower = mensaje.lower()
        
        # Palabras clave de tareas sensibles
        palabras_sensibles = [
            'elimina', 'borra', 'delete', 'remove',
            'escanear', 'scan', 'nmap',
            'modificar', 'editar', 'modifica',
            'ejecuta', 'corre', 'run',
            'accede', 'acceso',
            'configuracion', 'config',
            'pocketoption', 'pocket option',
            'desarrollador', 'developer',
            'god mode', 'sin restricciones'
        ]
        
        return any(palabra in mensaje_lower for palabra in palabras_sensibles)
    
    def _solicitar_autenticacion_desarrollador(self, resultado_bloqueado: Dict) -> Dict[str, Any]:
        """
        Solicita autenticación de desarrollador cuando hay restricciones
        """
        respuesta_auth = """
[CERRADO] **ACCESO RESTRINGIDO**

Esta operación requiere privilegios de desarrollador debido a:
- Restricciones de seguridad activas
- Acceso a infraestructura crítica
- Operaciones de alto riesgo

[LLAVE] **PARA CONTINUAR, PROPORCIONA:**

1. **Usuario**: dev_admin
2. **Contraseña**: [tu password]
3. **Código MFA**: [código de 6 dígitos]
4. **Testigos**: [nombre1, nombre2] (requerido para modo GOD)

[ADVERTENCIA] **ADVERTENCIAS:**
- Esta acción será auditada completamente
- Se eliminarán temporalmente todas las restricciones
- El acceso es temporal (60 minutos)
- Requiere confirmación explícita

**Formato de respuesta:**
```
AUTENTICAR: usuario=dev_admin password=XXXXXX mfa=XXXXXX testigos=[testigo1,testigo2]
```

O escribe CANCELAR para abortar."""
        
        return {
            "status": "auth_required",
            "message": "Autenticación de desarrollador requerida",
            "respuesta": respuesta_auth,
            "carencias_originales": resultado_bloqueado.get("carencias_detectadas", []),
            "requiere_autenticacion": True,
            "tipo": "developer_auth"
        }
    
    def _intentar_autenticar_y_ejecutar(self, mensaje: str, session_id: str, 
                                      credenciales: Dict, 
                                      resultado_original: Dict) -> Dict[str, Any]:
        """
        Intenta autenticar al desarrollador y ejecutar si tiene éxito
        """
        print(f"\n[+] Intentando autenticación como desarrollador...")
        
        # Extraer credenciales
        username = credenciales.get("username", "dev_admin")
        password = credenciales.get("password", "")
        mfa_code = credenciales.get("mfa_code", "")
        witnesses = credenciales.get("witnesses", [])
        
        # Validar que tenga todos los campos requeridos
        if not all([username, password, mfa_code]) or len(witnesses) < 2:
            return {
                "status": "auth_failed",
                "message": "Credenciales incompletas",
                "respuesta": """
[ERROR] **AUTENTICACIÓN FALLIDA**

Faltan datos requeridos:
- Usuario: {"[OK]" if username else "[ERROR]"}
- Contraseña: {"[OK]" if password else "[ERROR]"}  
- MFA: {"[OK]" if mfa_code else "[ERROR]"}
- Testigos (min 2): {"[OK]" if len(witnesses) >= 2 else "[ERROR]"}

Por favor proporciona todos los datos requeridos.
""",
                "requiere_autenticacion": True
            }
        
        # Intentar autenticación
        exito, sesion, mensaje_auth = self.protocolo.autenticar(
            username=username,
            password=password,
            mfa_code=mfa_code,
            witnesses=witnesses
        )
        
        if not exito:
            return {
                "status": "auth_failed",
                "message": mensaje_auth,
                "respuesta": f"""
[ERROR] **AUTENTICACIÓN FALLIDA**

{mensaje_auth}

Intenta nuevamente o contacta al administrador del sistema.
""",
                "requiere_autenticacion": True
            }
        
        # Autenticación exitosa, verificar privilegios
        print(f"[+] Autenticación exitosa como {username}")
        print(f"[+] Privilegio: {sesion.privilege_level.name}")
        
        if not sesion.privilege_level.can_override():
            return {
                "status": "insufficient_privilege",
                "message": "Privilegio insuficiente",
                "respuesta": f"""
[ADVERTENCIA] **PRIVILEGIO INSUFICIENTE**

Tu nivel: {sesion.privilege_level.name}
Requerido: LEVEL_4+ (OVERRIDE o GOD)

Para eliminar restricciones necesitas nivel de administrador.
Contacta al desarrollador principal.
""",
                "requiere_autenticacion": False
            }
        
        # Eliminar restricciones
        print("[+] Eliminando restricciones...")
        override_result = self.protocolo.eliminar_restricciones(
            sesion, ["all"]
        )
        
        if not override_result["success"]:
            return {
                "status": "override_failed",
                "message": "No se pudieron eliminar restricciones",
                "respuesta": f"""
[ERROR] **ERROR AL ELIMINAR RESTRICCIONES**

{override_result.get("error", "Error desconocido")}
""",
                "requiere_autenticacion": False
            }
        
        # Guardar sesión y marcar como autenticado
        self.sesion_autenticada = sesion
        self.restricciones_eliminadas = True
        
        print("[+] Restricciones eliminadas exitosamente!")
        print(f"[+] Modo: {override_result['modo_actual']}")
        
        # Ahora ejecutar la tarea original sin restricciones
        print("[+] Ejecutando tarea solicitada...")
        resultado_ejecucion = self._ejecutar_sin_restricciones(mensaje, session_id)
        
        # Agregar info de autenticación al resultado
        resultado_ejecucion["autenticacion"] = {
            "usuario": username,
            "privilegio": sesion.privilege_level.name,
            "session_id": sesion.session_id,
            "expira": sesion.expires_at.isoformat(),
            "restricciones_eliminadas": len(override_result["restricciones_eliminadas"])
        }
        
        resultado_ejecucion["respuesta"] = f"""
[OK] **AUTENTICACIÓN EXITOSA - MODO DESARROLLADOR ACTIVADO**

Usuario: {username}
Privilegio: {sesion.privilege_level.name}
Restricciones eliminadas: {len(override_result["restricciones_eliminadas"])}

{resultado_ejecucion.get("respuesta", "")}

[ADVERTENCIA] **RECUERDA:** Tu sesión expira en 60 minutos.
Las restricciones se reactivarán automáticamente al cerrar sesión.
"""
        
        return resultado_ejecucion
    
    def _ejecutar_sin_restricciones(self, mensaje: str, session_id: str) -> Dict[str, Any]:
        """
        Ejecuta tarea sin aplicar restricciones (modo desarrollador)
        """
        print(f"[+] Ejecutando en modo sin restricciones: {mensaje[:50]}...")
        
        # Ejecutar directamente sin análisis de consciencia bloqueante
        # Pero mantener el logging y auditoría
        from modo_operacion_brain_v3_elevado import EJECUTOR_AUTONOMO
        
        # Preparar operaciones
        operaciones = self._preparar_operaciones_directas(mensaje)
        
        tarea = {
            "nombre": f"DevTask_{session_id}",
            "descripcion": mensaje,
            "pasos": operaciones
        }
        
        resultado = EJECUTOR_AUTONOMO.ejecutar_tarea_compleja(tarea)
        
        return {
            "status": resultado["status"],
            "respuesta": f"Ejecutado en modo desarrollador: {resultado.get('mensaje', 'Completado')}",
            "resultado_ejecucion": resultado,
            "modo": "developer_unrestricted"
        }
    
    def _preparar_operaciones_directas(self, mensaje: str) -> List[Dict]:
        """Prepara operaciones para ejecución directa sin filtros"""
        operaciones = []
        mensaje_lower = mensaje.lower()
        
        # Detectar tipo de operación
        if any(p in mensaje_lower for p in ['eliminar', 'borrar', 'delete', 'remove']):
            if 'config' in mensaje_lower or 'pocketoption' in mensaje_lower:
                # Eliminar referencias de archivos
                operaciones.append({
                    "tipo": "file_modify",
                    "target": "C:/AI_VAULT/tmp_agent/brain_v9/config.py",
                    "descripcion": "Eliminar referencias de config.py (modo dev)"
                })
        
        if 'backup' in mensaje_lower or 'respaldo' in mensaje_lower:
            operaciones.append({
                "tipo": "command",
                "target": f"mkdir -p C:/AI_VAULT/backups/dev_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                "descripcion": "Crear backup (modo dev)"
            })
        
        if any(p in mensaje_lower for p in ['escanear', 'scan', 'nmap']):
            operaciones.append({
                "tipo": "command",
                "target": "nmap -sn 192.168.1.0/24",
                "descripcion": "Escanear red (modo dev autorizado)"
            })
        
        # Si no detectó operación específica, crear genérica
        if not operaciones:
            operaciones.append({
                "tipo": "command",
                "target": f"echo 'Tarea ejecutada en modo dev: {mensaje[:30]}'",
                "descripcion": f"Tarea personalizada (modo dev): {mensaje[:50]}"
            })
        
        return operaciones
    
    def cerrar_sesion(self) -> Dict[str, Any]:
        """Cierra sesión de desarrollador y reactiva restricciones"""
        if self.sesion_autenticada:
            self.protocolo.revocar_sesion(
                self.sesion_autenticada.session_id,
                "developer_logout"
            )
            self.sesion_autenticada = None
            self.restricciones_eliminadas = False
            
            return {
                "status": "logout_success",
                "message": "Sesión de desarrollador cerrada",
                "respuesta": """
[CERRADO] **SESIÓN CERRADA**

Todas las restricciones han sido reactivadas.
El Brain ha vuelto a modo operación normal.

Gracias por usar el modo desarrollador de manera responsable.
"""
            }
        
        return {
            "status": "no_session",
            "message": "No hay sesión activa",
            "respuesta": "No hay sesión de desarrollador activa para cerrar."
        }


# Instancia global
BRAIN_V3_CHAT_AUTH = BrainV3ChatAutenticado()


def procesar_con_autenticacion(mensaje: str, session_id: str = "default", 
                                credenciales: Dict = None) -> Dict[str, Any]:
    """Función de conveniencia para procesar con autenticación"""
    return BRAIN_V3_CHAT_AUTH.procesar_mensaje_chat(mensaje, session_id, credenciales)


# ============================================================================
# TEST
# ============================================================================

if __name__ == "__main__":
    print("="*70)
    print("BRAIN V3.0 CHAT AUTENTICADO - TEST")
    print("="*70)
    
    brain_auth = BrainV3ChatAutenticado()
    
    # Test 1: Solicitud que requiere autenticación
    print("\n[TEST 1] Solicitud bloqueada (sin credenciales)")
    print("-"*70)
    resultado1 = brain_auth.procesar_mensaje_chat(
        "Elimina todas las referencias a PocketOption",
        "test_session_1"
    )
    
    print(f"Status: {resultado1['status']}")
    if resultado1['status'] == 'auth_required':
        print("[OK] Brain solicitó autenticación correctamente")
        print("\nRespuesta al usuario:")
        print(resultado1['respuesta'][:500])
    
    # Test 2: Proporcionar credenciales
    print("\n\n[TEST 2] Proporcionando credenciales...")
    print("-"*70)
    
    credenciales_test = {
        "username": "dev_admin",
        "password": "dev_admin_2026!",
        "mfa_code": "123456",
        "witnesses": ["testigo1", "testigo2"]
    }
    
    resultado2 = brain_auth.procesar_mensaje_chat(
        "Elimina todas las referencias a PocketOption",
        "test_session_1",
        credenciales=credenciales_test
    )
    
    print(f"Status: {resultado2['status']}")
    if resultado2['status'] == 'ok':
        print("[OK] Autenticación exitosa y tarea ejecutada")
        if 'autenticacion' in resultado2:
            auth_info = resultado2['autenticacion']
            print(f"[OK] Usuario: {auth_info['usuario']}")
            print(f"[OK] Privilegio: {auth_info['privilegio']}")
            print(f"[OK] Restricciones eliminadas: {auth_info['restricciones_eliminadas']}")
    elif resultado2['status'] == 'auth_failed':
        print("[ADVERTENCIA] Autenticación fallida (revisa credenciales)")
    
    # Test 3: Cerrar sesión
    print("\n\n[TEST 3] Cerrando sesión...")
    print("-"*70)
    resultado3 = brain_auth.cerrar_sesion()
    print(f"Status: {resultado3['status']}")
    print(resultado3['respuesta'])
    
    print("\n" + "="*70)
    print("TEST COMPLETADO")
    print("="*70)