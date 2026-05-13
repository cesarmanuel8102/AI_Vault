#!/usr/bin/env python3
"""
AI_VAULT Autonomy System - Simple Launcher
Inicia todos los servicios en ventanas separadas
"""

import subprocess
import time
import sys
from pathlib import Path

def main():
    base_dir = Path(r"C:\AI_VAULT\00_identity")
    
    print("=" * 60)
    print("AI_VAULT AUTONOMY SYSTEM")
    print("=" * 60)
    print()
    
    # Iniciar Brain Server
    print("[1/4] Iniciando Brain Server (puerto 8000)...")
    subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "brain_server:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd=base_dir,
        creationflags=subprocess.CREATE_NEW_CONSOLE
    )
    time.sleep(5)
    
    # Iniciar Advisor Server
    print("[2/4] Iniciando Advisor Server (puerto 8010)...")
    subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "advisor_server:app", "--host", "127.0.0.1", "--port", "8010"],
        cwd=base_dir,
        creationflags=subprocess.CREATE_NEW_CONSOLE
    )
    time.sleep(5)
    
    # Iniciar Dashboard (desde autonomy_system)
    print("[3/4] Iniciando Dashboard (puerto 8020)...")
    dashboard_script = base_dir / "autonomy_system" / "dashboard_server.py"
    subprocess.Popen(
        [sys.executable, str(dashboard_script)],
        cwd=base_dir / "autonomy_system",
        creationflags=subprocess.CREATE_NEW_CONSOLE
    )
    time.sleep(3)
    
    # Iniciar Chat Interface (desde autonomy_system)
    print("[4/4] Iniciando Chat Interface (puerto 8030)...")
    chat_script = base_dir / "autonomy_system" / "chat_interface.py"
    subprocess.Popen(
        [sys.executable, str(chat_script)],
        cwd=base_dir / "autonomy_system",
        creationflags=subprocess.CREATE_NEW_CONSOLE
    )
    time.sleep(3)
    
    print()
    print("=" * 60)
    print("SISTEMA INICIADO")
    print("=" * 60)
    print()
    print("URLs de acceso:")
    print("  Dashboard:      http://127.0.0.1:8020")
    print("  Chat:           http://127.0.0.1:8030")
    print("  Brain API:      http://127.0.0.1:8000/docs")
    print("  Advisor API:    http://127.0.0.1:8010/docs")
    print()
    print("Cada servicio está corriendo en su propia ventana.")
    print("Cierra las ventanas individuales para detener cada servicio.")
    print()
    input("Presiona Enter para salir...")

if __name__ == "__main__":
    main()
