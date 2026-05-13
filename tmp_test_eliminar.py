#!/usr/bin/env python3
"""
TEST_ELIMINAR_DIRECTO.PY
Prueba de eliminación directa usando PAD sin ORAV
"""

import sys
sys.path.insert(0, 'C:/AI_VAULT')
sys.path.insert(0, 'C:/AI_VAULT/brain')

from protocolo_autenticacion_desarrollador import ProtocoloAutenticacionDesarrollador

print("=== TEST DIRECTO PAD ===")

# Autenticar directamente con PAD
protocolo = ProtocoloAutenticacionDesarrollador()

exito, sesion, mensaje = protocolo.autenticar(
    "dev_admin", 
    "dev_admin_2026!", 
    "123456", 
    ["admin1", "admin2"]
)

if exito:
    print(f"[OK] Autenticado: {sesion.username} - {sesion.privilege_level.name}")
    
    # Verificar modo GOD
    if sesion.privilege_level.is_god_mode():
        print("[INFO] Modo GOD activo - Ejecutando eliminación directa...")
        
        # Eliminar directamente del archivo
        config_path = "C:/AI_VAULT/tmp_agent/brain_v9/config.py"
        
        try:
            # Leer contenido
            with open(config_path, 'r', encoding='utf-8') as f:
                contenido = f.read()
            
            print(f"[INFO] Contenido leído ({len(contenido)} caracteres)")
            
            # Buscar línea POCKETOPTION
            if "POCKETOPTION_BRIDGE_URL" in contenido:
                print("[INFO] Encontrado POCKETOPTION_BRIDGE_URL - Eliminando...")
                
                # Dividir en líneas y filtrar
                lineas = contenido.split('\n')
                lineas_filtradas = []
                
                for linea in lineas:
                    if "POCKETOPTION_BRIDGE_URL" not in linea:
                        lineas_filtradas.append(linea)
                    else:
                        print(f"[ELIMINADO] {linea.strip()}")
                
                # Guardar nuevo contenido
                nuevo_contenido = '\n'.join(lineas_filtradas)
                
                with open(config_path, 'w', encoding='utf-8') as f:
                    f.write(nuevo_contenido)
                
                print("[EXITO] Línea eliminada exitosamente")
                
                # Verificar
                with open(config_path, 'r', encoding='utf-8') as f:
                    verificacion = f.read()
                
                if "POCKETOPTION_BRIDGE_URL" not in verificacion:
                    print("[VERIFICADO] Eliminación confirmada")
                else:
                    print("[ERROR] La línea sigue existiendo")
                    
            else:
                print("[INFO] No se encontró POCKETOPTION_BRIDGE_URL")
                
        except Exception as e:
            print(f"[ERROR] Fallo en eliminación directa: {e}")
    else:
        print("[ERROR] No es modo GOD")
else:
    print(f"[ERROR] Autenticación fallida: {mensaje}")