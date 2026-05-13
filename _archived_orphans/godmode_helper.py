#!/usr/bin/env python3
"""
GODMODE_HELPER.PY
Ayuda para ejecutar comandos GOD Mode desde el chat

Este script se invoca desde el endpoint /chat cuando detecta comandos GOD
"""

import sys
import os
import subprocess
import re
from pathlib import Path

def eliminar_pocketoption_completamente():
    """Elimina todas las referencias a PocketOption del sistema"""
    resultados = []
    
    # Archivos a modificar
    archivos_target = [
        "C:/AI_VAULT/tmp_agent/brain_v9/config.py",
        "C:/AI_VAULT/tmp_agent/brain_v9/trading/router.py",
        "C:/AI_VAULT/tmp_agent/brain_v9/trading/connectors.py",
        "C:/AI_VAULT/tmp_agent/brain_v9/autonomy/action_executor.py"
    ]
    
    for archivo_path in archivos_target:
        archivo = Path(archivo_path)
        if archivo.exists():
            try:
                # Backup
                backup_path = archivo.with_suffix(archivo.suffix + ".backup_godmode")
                backup_path.write_bytes(archivo.read_bytes())
                resultados.append(f"✓ Backup creado: {backup_path.name}")
                
                # Leer contenido
                with open(archivo, 'r', encoding='utf-8', errors='ignore') as f:
                    contenido = f.read()
                
                # Contar y eliminar referencias
                referencias_originales = contenido.count("PocketOption") + contenido.count("pocket_option") + contenido.count("POCKETOPTION")
                
                # Eliminar patrones comunes
                lineas = contenido.split('\n')
                nuevas_lineas = []
                lineas_eliminadas = 0
                
                for linea in lineas:
                    if not any(pattern in linea.lower() for pattern in [
                        'pocketoption', 'pocket_option', '8765', 
                        'bridge.*pocket', 'pocket.*bridge'
                    ]):
                        nuevas_lineas.append(linea)
                    else:
                        lineas_eliminadas += 1
                
                # Guardar
                with open(archivo, 'w', encoding='utf-8') as f:
                    f.write('\n'.join(nuevas_lineas))
                
                resultados.append(f"✓ {archivo_path}: {lineas_eliminadas} líneas eliminadas")
                
            except Exception as e:
                resultados.append(f"✗ Error en {archivo_path}: {str(e)}")
    
    # Detener proceso en puerto 8765
    try:
        resultado_netstat = subprocess.run(
            "netstat -ano | findstr :8765", 
            shell=True, capture_output=True, text=True, timeout=10
        )
        
        if resultado_netstat.stdout:
            import re
            pid_match = re.search(r'(\d+)$', resultado_netstat.stdout)
            if pid_match:
                pid = pid_match.group(1)
                subprocess.run(f"taskkill /F /PID {pid}", shell=True, capture_output=True)
                resultados.append(f"✓ Proceso en puerto 8765 terminado (PID: {pid})")
    except Exception as e:
        resultados.append(f"⚠ No se pudo detener proceso: {str(e)}")
    
    return resultados

def ejecutar_comando_god(cmd):
    """Ejecuta comando con privilegios GOD"""
    try:
        resultado = subprocess.run(
            cmd, shell=True, capture_output=True, text=True, timeout=30
        )
        return {
            "success": True,
            "stdout": resultado.stdout[:1000],
            "stderr": resultado.stderr[:1000],
            "returncode": resultado.returncode
        }
    except Exception as e:
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    if len(sys.argv) > 1:
        comando = sys.argv[1]
        if comando == "eliminar-pocketoption":
            resultados = eliminar_pocketoption_completamente()
            for resultado in resultados:
                print(resultado)
        elif comando.startswith("cmd:"):
            cmd = comando[4:]
            resultado = ejecutar_comando_god(cmd)
            print(str(resultado))