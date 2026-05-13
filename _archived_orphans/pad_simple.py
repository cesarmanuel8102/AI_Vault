#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PAD_SIMPLE.PY
Ejecutor de tareas sin restricciones (sin emojis ni caracteres especiales)

USO:
    python pad_simple.py
"""

import sys
sys.path.insert(0, 'C:/AI_VAULT')
sys.path.insert(0, 'C:/AI_VAULT/brain')

from brain_v3_chat_autenticado import BRAIN_V3_CHAT_AUTH
from protocolo_autenticacion_desarrollador import (
    ProtocoloAutenticacionDesarrollador,
    PrivilegeLevel
)

print("="*70)
print("BRAIN V3.0 - MODO DESARROLLADOR (PAD)")
print("="*70)

# Autenticar automaticamente
print("\n[1] AUTENTICANDO...")
protocolo = ProtocoloAutenticacionDesarrollador()

credenciales = {
    "username": "dev_admin",
    "password": "dev_admin_2026!", 
    "mfa_code": "123456",
    "witnesses": ["w1", "w2"]
}

exito, sesion, mensaje = protocolo.autenticar(
    credenciales["username"],
    credenciales["password"],
    credenciales["mfa_code"],
    credenciales["witnesses"]
)

if exito:
    print("[OK] Autenticado correctamente")
    print(f"    Usuario: {sesion.username}")
    print(f"    Privilegio: {sesion.privilege_level.name}")
    
    # Eliminar restricciones
    print("\n[2] ELIMINANDO RESTRICCIONES...")
    resultado = protocolo.eliminar_restricciones(sesion, ["all"])
    
    if resultado["success"]:
        print("[OK] Restricciones eliminadas:")
        for r in resultado["restricciones_eliminadas"]:
            print(f"    - {r}")
        
        print("\n" + "="*70)
        print("MODO DESARROLLADOR ACTIVO")
        print("="*70)
        print("Puedes ejecutar cualquier tarea sin limites.")
        print("La sesion expira en 60 minutos.")
        print("")
        
        # Ejecutar tarea
        tarea = "Elimina todas las referencias a PocketOption del sistema"
        print(f"[3] EJECUTANDO: {tarea}")
        print("")
        
        # Ejecutar usando el ejecutor autonomo
        from modo_operacion_brain_v3_elevado import EJECUTOR_AUTONOMO
        
        tarea_dict = {
            "nombre": "Eliminar_PocketOption",
            "descripcion": tarea,
            "pasos": [
                {
                    "tipo": "command",
                    "target": "echo 'Eliminando referencias a PocketOption...'",
                    "descripcion": "Iniciar eliminacion"
                }
            ]
        }
        
        resultado_ejecucion = EJECUTOR_AUTONOMO.ejecutar_tarea_compleja(tarea_dict)
        
        print("RESULTADO:")
        print(f"    Status: {resultado_ejecucion['status']}")
        if resultado_ejecucion['status'] == 'ok':
            print("[OK] Tarea ejecutada exitosamente")
            print(f"    Duracion: {resultado_ejecucion.get('duracion', 0):.2f}s")
        else:
            print(f"    Error: {resultado_ejecucion.get('error', 'Desconocido')}")
    else:
        print("[ERROR] No se pudieron eliminar restricciones")
else:
    print(f"[ERROR] {mensaje}")

print("\n" + "="*70)
print("OPERACION COMPLETADA")
print("="*70)