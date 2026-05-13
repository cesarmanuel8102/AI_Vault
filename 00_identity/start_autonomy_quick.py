#!/usr/bin/env python3
"""
AI_VAULT Autonomy System - Quick Start
Inicia todos los servicios de forma simple
"""

import subprocess
import time
import sys
from pathlib import Path

def log(msg):
    print(f"[AI_VAULT] {msg}")

def main():
    base_dir = Path(r"C:\AI_VAULT\00_identity")
    autonomy_dir = base_dir / "autonomy_system"
    
    print("=" * 60)
    print("AI_VAULT AUTONOMY SYSTEM")
    print("=" * 60)
    print()
    
    # Iniciar Brain Server
    log("Iniciando Brain Server (puerto 8000)...")
    subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "brain_server:app", "--host", "127.0.0.1", "--port", "8000", "--log-level", "warning"],
        cwd=base_dir,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    time.sleep(5)
    
    # Iniciar Advisor Server
    log("Iniciando Advisor Server (puerto 8010)...")
    subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "advisor_server:app", "--host", "127.0.0.1", "--port", "8010", "--log-level", "warning"],
        cwd=base_dir,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    time.sleep(5)
    
    # Iniciar Dashboard (version simple)
    log("Iniciando Dashboard (puerto 8040)...")
    subprocess.Popen(
        [sys.executable, str(autonomy_dir / "dashboard_simple.py")],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    time.sleep(3)
    
    # Iniciar Chat Interface
    log("Iniciando Chat Interface (puerto 8030)...")
    subprocess.Popen(
        [sys.executable, str(autonomy_dir / "chat_interface.py")],
        cwd=autonomy_dir,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    time.sleep(3)
    
    print()
    print("=" * 60)
    print("SISTEMA INICIADO")
    print("=" * 60)
    print()
    print("URLs de acceso:")
    print("  Dashboard:      http://127.0.0.1:8040")
    print("  Chat:           http://127.0.0.1:8030")
    print("  Brain API:      http://127.0.0.1:8000/docs")
    print("  Advisor API:    http://127.0.0.1:8010/docs")
    print()
    print("El sistema esta corriendo en segundo plano.")
    print("Presiona Ctrl+C para detener...")
    print()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\nDeteniendo servicios...")
        import os
        os.system("taskkill /F /IM python.exe 2>nul")
        log("Servicios detenidos.")

if __name__ == "__main__":
    main()
