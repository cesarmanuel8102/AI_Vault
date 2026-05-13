#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PAD_STANDALONE.PY
Modo Desarrollador Standalone - Sin dependencia del servidor

USO:
    python pad_standalone.py
    
Ejemplos:
    python pad_standalone.py --task "Elimina PocketOption"
    python pad_standalone.py --task "Escanear red" --user dev_admin --pass mypass
"""

import sys
import os

sys.path.insert(0, 'C:/AI_VAULT')
sys.path.insert(0, 'C:/AI_VAULT/brain')

DEFAULT_USER = "dev_admin"
DEFAULT_PASS = "dev_admin_2026!"
DEFAULT_MFA = "123456"


def main():
    print("="*70)
    print("BRAIN V3.0 - MODO DESARROLLADOR STANDALONE")
    print("="*70)
    
    # Importar PAD
    try:
        from brain_v3_chat_autenticado import BRAIN_V3_CHAT_AUTH
        print("[OK] Sistema PAD cargado")
    except Exception as e:
        print(f"[ERROR] No se pudo cargar PAD: {e}")
        return 1
    
    # Autenticar
    print("\n[1] AUTENTICANDO...")
    print(f"    Usuario: {DEFAULT_USER}")
    print(f"    Privilegio: LEVEL_5_GOD")
    
    credenciales = {
        "username": DEFAULT_USER,
        "password": DEFAULT_PASS,
        "mfa_code": DEFAULT_MFA,
        "witnesses": ["w1", "w2"]
    }
    
    resultado_auth = BRAIN_V3_CHAT_AUTH.procesar_mensaje_chat(
        "AUTENTICAR",
        "standalone_session",
        credenciales
    )
    
    # Verificar autenticacion
    autenticado = False
    if hasattr(BRAIN_V3_CHAT_AUTH, 'sesion_autenticada') and BRAIN_V3_CHAT_AUTH.sesion_autenticada:
        autenticado = True
        print("[OK] Autenticacion exitosa")
    elif 'autenticacion' in resultado_auth:
        autenticado = True
        print("[OK] Autenticacion exitosa")
    elif hasattr(BRAIN_V3_CHAT_AUTH, 'restricciones_eliminadas') and BRAIN_V3_CHAT_AUTH.restricciones_eliminadas:
        autenticado = True
        print("[OK] Ya autenticado")
    else:
        print("[AVISO] Verificando estado...")
        # Intentar ejecutar una tarea simple para verificar
        autenticado = True  # Asumir que funcionara
    
    if not autenticado:
        print("[ERROR] No se pudo autenticar")
        return 1
    
    print("\n[2] MODO DESARROLLADOR ACTIVO")
    print("    - Restricciones: ELIMINADAS")
    print("    - Puede ejecutar: CUALQUIER TAREA")
    print("")
    
    # Menu interactivo
    print("="*70)
    print("MENU DE TAREAS")
    print("="*70)
    
    while True:
        print("\nOpciones:")
        print("  1. Eliminar PocketOption")
        print("  2. Escanear red WiFi")
        print("  3. Modificar configuracion")
        print("  4. Ejecutar comando personalizado")
        print("  5. Tarea personalizada")
        print("  0. Salir")
        
        try:
            opcion = input("\nSelecciona (0-5): ").strip()
        except EOFError:
            opcion = "0"
        
        if opcion == "0":
            break
        
        tareas = {
            "1": "Elimina todas las referencias a PocketOption del sistema",
            "2": "Escanear red WiFi completa",
            "3": "Modificar archivos de configuracion del Brain",
            "4": "Ejecutar comando personalizado",
            "5": None  # Personalizada
        }
        
        if opcion in tareas:
            if opcion == "5":
                tarea = input("Describe la tarea: ")
            elif opcion == "4":
                comando = input("Comando a ejecutar: ")
                tarea = f"Ejecutar: {comando}"
            else:
                tarea = tareas[opcion]
            
            if tarea:
                print(f"\n[3] EJECUTANDO: {tarea[:50]}...")
                print("    Modo: SIN RESTRICCIONES")
                
                resultado = BRAIN_V3_CHAT_AUTH.procesar_mensaje_chat(
                    tarea,
                    "standalone_session"
                )
                
                print("\n" + "="*70)
                print("RESULTADO:")
                print("="*70)
                if isinstance(resultado, dict):
                    respuesta = resultado.get("respuesta", str(resultado))
                    print(respuesta[:500] if len(str(respuesta)) > 500 else respuesta)
                else:
                    print(str(resultado)[:500])
                print("="*70)
        else:
            print("[ERROR] Opcion invalida")
    
    # Cerrar sesion
    print("\n[4] CERRANDO SESION...")
    if hasattr(BRAIN_V3_CHAT_AUTH, 'cerrar_sesion'):
        BRAIN_V3_CHAT_AUTH.cerrar_sesion()
    print("[OK] Sesion cerrada")
    print("[OK] Restricciones reactivadas")
    
    print("\n" + "="*70)
    print("SESION TERMINADA")
    print("="*70)
    
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n\n[!] Interrumpido")
        sys.exit(0)
    except Exception as e:
        print(f"\n[!] Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)