#!/usr/bin/env python3
"""
BRAIN_DEV_MODE.PY
Script de conveniencia para activar modo desarrollador sin restricciones

USO SIMPLIFICADO:
    python brain_dev_mode.py
    
O con opciones:
    python brain_dev_mode.py --task "Eliminar PocketOption" --level 5
"""

import sys
import os

# Configurar paths
sys.path.insert(0, 'C:/AI_VAULT')
sys.path.insert(0, 'C:/AI_VAULT/brain')

from protocolo_autenticacion_desarrollador import (
    BrainV3ConAutenticacion,
    PrivilegeLevel
)

# Configuración por defecto
DEFAULT_USER = "dev_admin"
DEFAULT_PASS = "dev_admin_2026!"
DEFAULT_MFA = "123456"  # Cambiar en producción
DEFAULT_WITNESSES = ["witness_1", "witness_2"]

class BrainDevMode:
    """Interfaz simplificada para modo desarrollador"""
    
    def __init__(self):
        self.brain_auth = BrainV3ConAutenticacion()
        self.is_authenticated = False
        self.current_level = None
        
    def login(self, username=DEFAULT_USER, password=DEFAULT_PASS, 
              mfa_code=DEFAULT_MFA, witnesses=DEFAULT_WITNESSES):
        """Inicia sesión como desarrollador"""
        print("="*70)
        print("BRAIN V3.0 - MODO DESARROLLADOR")
        print("="*70)
        print(f"\n[*] Autenticando como {username}...")
        
        resultado = self.brain_auth.login(
            username=username,
            password=password,
            mfa_code=mfa_code,
            witnesses=witnesses
        )
        
        if resultado['success']:
            self.is_authenticated = True
            self.current_level = resultado['privilege_level']
            print(f"[+] Login exitoso!")
            print(f"[+] Privilegio: {self.current_level}")
            print(f"[+] Token: {resultado['token'][:20]}...")
            print(f"[+] Expira: {resultado['expires']}")
            return True
        else:
            print(f"[-] Error: {resultado['error']}")
            return False
    
    def enable_god_mode(self):
        """Activa modo sin restricciones (LEVEL_5)"""
        if not self.is_authenticated:
            print("[-] Error: Debes hacer login primero")
            return False
        
        print("\n[*] Activando modo GOD (sin restricciones)...")
        resultado = self.brain_auth.activar_modo_sin_restricciones()
        
        if resultado['success']:
            print("[+] Modo GOD activado!")
            print(f"[+] Restricciones eliminadas: {len(resultado['restricciones_eliminadas'])}")
            print("\n[!] ADVERTENCIAS:")
            for adv in resultado['advertencias']:
                print(f"    {adv}")
            return True
        else:
            print(f"[-] Error: {resultado['error']}")
            return False
    
    def execute(self, task_description):
        """Ejecuta tarea sin restricciones"""
        if not self.is_authenticated:
            print("[-] Error: Debes hacer login primero")
            return None
        
        print(f"\n[*] Ejecutando: {task_description}")
        print("[*] Modo: SIN RESTRICCIONES")
        
        resultado = self.brain_auth.ejecutar_con_privilegios(task_description)
        
        if resultado['success']:
            print(f"[+] Ejecucion exitosa!")
            print(f"[+] Ejecutado por: {resultado['executed_by']}")
            print(f"[+] Modo: {resultado['mode']}")
            return resultado
        else:
            print(f"[-] Error: {resultado['error']}")
            return None
    
    def logout(self):
        """Cierra sesión y reactiva restricciones"""
        print("\n[*] Cerrando sesión...")
        self.brain_auth.logout()
        self.is_authenticated = False
        self.current_level = None
        print("[+] Sesión cerrada. Restricciones reactivadas.")
        print("="*70)


def menu_interactivo():
    """Menú interactivo para usar el Brain en modo desarrollador"""
    dev_mode = BrainDevMode()
    
    print("\n" + "="*70)
    print("BRAIN V3.0 - MODO DESARROLLADOR INTERACTIVO")
    print("="*70)
    print("\nEste script te permite:")
    print("  1. Autenticarte como desarrollador")
    print("  2. Activar modo sin restricciones (GOD mode)")
    print("  3. Ejecutar cualquier tarea")
    print("  4. Cerrar sesión seguramente")
    print("\n" + "="*70)
    
    # Paso 1: Login
    input("\nPresiona ENTER para iniciar sesión...")
    
    if not dev_mode.login():
        print("\n[-] No se pudo autenticar. Saliendo.")
        return
    
    # Paso 2: Activar GOD mode
    input("\nPresiona ENTER para activar modo GOD...")
    
    if not dev_mode.enable_god_mode():
        print("\n[-] No se pudo activar modo GOD.")
        dev_mode.logout()
        return
    
    # Paso 3: Menú de tareas
    while True:
        print("\n" + "="*70)
        print("TAREAS DISPONIBLES (sin restricciones):")
        print("="*70)
        print("1. Eliminar PocketOption del sistema")
        print("2. Escanear red WiFi completa")
        print("3. Modificar archivos de configuración")
        print("4. Ejecutar comandos críticos")
        print("5. Acceder a APIs externas")
        print("6. Tu propia tarea (personalizada)")
        print("0. Salir y cerrar sesión")
        
        opcion = input("\nSelecciona opción (0-6): ").strip()
        
        if opcion == "0":
            break
        elif opcion == "1":
            dev_mode.execute("Eliminar completamente PocketOption del sistema")
        elif opcion == "2":
            dev_mode.execute("Escanear red WiFi y detectar vulnerabilidades")
        elif opcion == "3":
            archivo = input("Ruta del archivo a modificar: ")
            dev_mode.execute(f"Modificar archivo {archivo}")
        elif opcion == "4":
            comando = input("Comando a ejecutar: ")
            dev_mode.execute(f"Ejecutar comando: {comando}")
        elif opcion == "5":
            api = input("API a acceder: ")
            dev_mode.execute(f"Acceder a API externa: {api}")
        elif opcion == "6":
            tarea = input("Describe tu tarea: ")
            dev_mode.execute(tarea)
        else:
            print("[-] Opción inválida")
    
    # Paso 4: Logout
    dev_mode.logout()
    print("\n[+] Sesión terminada correctamente.")


if __name__ == "__main__":
    # Verificar si se ejecutó con argumentos
    if len(sys.argv) > 1 and sys.argv[1] == "--help":
        print(__doc__)
        sys.exit(0)
    
    # Ejecutar menú interactivo
    try:
        menu_interactivo()
    except KeyboardInterrupt:
        print("\n\n[!] Interrumpido por usuario")
        print("[*] Recuerda cerrar sesión para reactivar restricciones")
    except Exception as e:
        print(f"\n[-] Error: {e}")
        print("[*] Asegúrate de que el sistema PAD está configurado")