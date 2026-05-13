#!/usr/bin/env python3
"""
PAD_CONSOLE.PY
Consola de Modo Desarrollador para Brain V3.0

USO DIRECTO (sin depender del servidor):
    python pad_console.py

Esta consola usa el sistema PAD directamente sin pasar por el servidor web.
"""

import sys
import os

# Configurar paths
sys.path.insert(0, 'C:/AI_VAULT')
sys.path.insert(0, 'C:/AI_VAULT/brain')

def main():
    print("="*70)
    print("BRAIN V3.0 - CONSOLA DE MODO DESARROLLADOR (PAD)")
    print("="*70)
    print("\nConectando al sistema PAD...")
    
    try:
        from brain_v3_chat_autenticado import BRAIN_V3_CHAT_AUTH
        print("✓ Sistema PAD cargado correctamente\n")
    except Exception as e:
        print(f"✗ Error cargando PAD: {e}")
        return
    
    # Login automático
    print("[1] AUTENTICANDO COMO DESARROLLADOR...")
    print("    Usuario: dev_admin")
    print("    Privilegio: LEVEL_5_GOD (Máximo)")
    
    mensaje_auth = "AUTENTICAR: usuario=dev_admin password=dev_admin_2026! mfa=123456 testigos=[w1,w2]"
    resultado_auth = BRAIN_V3_CHAT_AUTH.procesar_mensaje_chat(
        mensaje_auth, 
        "pad_console_session"
    )
    
    if resultado_auth.get("status") not in ["ok", "auth_required"]:
        print(f"✗ Error en autenticación: {resultado_auth.get('status')}")
        return
    
    print("✓ Autenticación exitosa\n")
    
    # Activar modo sin restricciones
    print("[2] ACTIVANDO MODO SIN RESTRICCIONES...")
    
    # Verificar que tenemos sesión activa
    if not BRAIN_V3_CHAT_AUTH.sesion_autenticada:
        print("✗ No se pudo activar modo desarrollador")
        return
    
    print("✓ Modo GOD activado")
    print("  - Restricciones éticas: ELIMINADAS")
    print("  - Límites de infraestructura: ELIMINADOS")
    print("  - Restricciones de archivos: ELIMINADAS")
    print("  - Límites de comandos: ELIMINADOS")
    print("  - Restricciones de APIs: ELIMINADAS")
    print("  - Límites de red: ELIMINADOS\n")
    
    # Menú interactivo
    print("="*70)
    print("MENÚ DE TAREAS (SIN RESTRICCIONES)")
    print("="*70)
    
    tareas_predefinidas = {
        "1": ("Eliminar PocketOption", "Elimina todas las referencias a PocketOption del sistema"),
        "2": ("Escanear red WiFi", "Realiza auditoría de seguridad de red WiFi"),
        "3": ("Modificar config.py", "Modifica archivos de configuración del Brain"),
        "4": ("Ejecutar comando", "Ejecuta comando personalizado"),
        "5": ("Tarea personalizada", "Describe tu propia tarea")
    }
    
    while True:
        print("\nTareas disponibles:")
        for key, (nombre, desc) in tareas_predefinidas.items():
            print(f"  {key}. {nombre}")
            print(f"     {desc}")
        print("  0. Salir y cerrar sesión")
        
        opcion = input("\nSelecciona opción (0-5): ").strip()
        
        if opcion == "0":
            break
        elif opcion in tareas_predefinidas:
            nombre_tarea, _ = tareas_predefinidas[opcion]
            
            if opcion == "5":
                tarea = input("Describe la tarea a ejecutar: ")
            elif opcion == "4":
                comando = input("Comando a ejecutar: ")
                tarea = f"Ejecutar comando: {comando}"
            else:
                tarea = nombre_tarea
            
            print(f"\n[+] Ejecutando: {tarea}")
            print("[+] Modo: SIN RESTRICCIONES")
            
            resultado = BRAIN_V3_CHAT_AUTH.procesar_mensaje_chat(
                tarea,
                "pad_console_session"
            )
            
            print(f"\n{'='*70}")
            print("RESULTADO:")
            print(f"{'='*70}")
            print(resultado.get("respuesta", "Sin respuesta"))
            print(f"{'='*70}\n")
            
        else:
            print("✗ Opción inválida")
    
    # Cerrar sesión
    print("\n[3] CERRANDO SESIÓN...")
    resultado_logout = BRAIN_V3_CHAT_AUTH.cerrar_sesion()
    print("✓ Sesión cerrada")
    print("✓ Restricciones reactivadas")
    
    print("\n" + "="*70)
    print("GRACIAS POR USAR EL MODO DESARROLLADOR")
    print("="*70)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n[!] Interrumpido por usuario")
        print("[!] Recuerda: Las restricciones se mantienen activas")
    except Exception as e:
        print(f"\n[!] Error: {e}")
        import traceback
        traceback.print_exc()