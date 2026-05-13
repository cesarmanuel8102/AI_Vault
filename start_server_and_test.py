#!/usr/bin/env python3
"""
Inicia servidor y verifica que funciona automaticamente
"""
import subprocess
import sys
import time
import urllib.request
import json
from pathlib import Path

# Paso 1: Detener servidores anteriores
print("PASO 1: Deteniendo servidores anteriores...")
subprocess.run(["taskkill", "/F", "/IM", "python.exe"], capture_output=True)
time.sleep(2)

# Paso 2: Iniciar servidor
print("PASO 2: Iniciando servidor chat_simple.py...")
subprocess.Popen(
    [sys.executable, "C:\\AI_VAULT\\00_identity\\chat_brain_v7\\chat_simple.py"],
    creationflags=subprocess.CREATE_NEW_CONSOLE
)

# Esperar a que inicie
print("PASO 3: Esperando servidor...")
time.sleep(3)

# Paso 4: Verificar que responde
print("PASO 4: Verificando servidor...")
try:
    req = urllib.request.Request("http://127.0.0.1:8090/", method="GET")
    with urllib.request.urlopen(req, timeout=5) as response:
        html = response.read().decode()
        if "Brain Chat" in html:
            print("\n✓ SERVIDOR FUNCIONANDO CORRECTAMENTE")
            print("\nURLs DISPONIBLES:")
            print("  - http://127.0.0.1:8090/  (Chat)")
            print("  - http://127.0.0.1:8090/health  (API)")
            print("\nAbre tu navegador en: http://127.0.0.1:8090/")
            print("\nPara detener: Cierra la ventana del servidor o presiona Ctrl+C")
        else:
            print("✗ Error: Respuesta inesperada del servidor")
except Exception as e:
    print(f"✗ Error verificando servidor: {e}")

input("\nPresiona ENTER para salir...")
