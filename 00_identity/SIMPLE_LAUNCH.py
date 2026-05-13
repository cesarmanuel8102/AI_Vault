#!/usr/bin/env python3
"""
AI_VAULT SIMPLE LAUNCHER
Inicia todos los servicios en secuencia con verificación
"""

import subprocess
import time
import sys
import os
from pathlib import Path

def log(msg):
    print(f"[LAUNCHER] {msg}")

def start_service(name, cmd, cwd, wait_time=5):
    """Iniciar un servicio y esperar"""
    log(f"Iniciando {name}...")
    try:
        # Iniciar en nueva consola para ver errores
        process = subprocess.Popen(
            cmd,
            cwd=cwd,
            creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == 'win32' else 0
        )
        log(f"  {name} iniciado (PID: {process.pid})")
        time.sleep(wait_time)
        return process
    except Exception as e:
        log(f"  ERROR iniciando {name}: {e}")
        return None

def main():
    base_dir = Path(r"C:\AI_VAULT\00_identity")
    autonomy_dir = base_dir / "autonomy_system"
    
    log("=" * 60)
    log("AI_VAULT SIMPLE LAUNCHER")
    log("=" * 60)
    log("")
    
    processes = []
    
    # 1. Brain Server
    p1 = start_service(
        "Brain Server (puerto 8000)",
        [sys.executable, "-m", "uvicorn", "brain_server:app", 
         "--host", "127.0.0.1", "--port", "8000"],
        base_dir,
        5
    )
    if p1:
        processes.append(("Brain", p1))
    
    # 2. Advisor Server
    p2 = start_service(
        "Advisor Server (puerto 8010)",
        [sys.executable, "-m", "uvicorn", "advisor_server:app",
         "--host", "127.0.0.1", "--port", "8010"],
        base_dir,
        5
    )
    if p2:
        processes.append(("Advisor", p2))
    
    # 3. Chat Profesional
    p3 = start_service(
        "Chat Profesional (puerto 8030)",
        [sys.executable, str(autonomy_dir / "chat_professional.py")],
        autonomy_dir,
        3
    )
    if p3:
        processes.append(("Chat", p3))
    
    # 4. Dashboard Profesional
    p4 = start_service(
        "Dashboard Profesional (puerto 8040)",
        [sys.executable, str(autonomy_dir / "dashboard_professional.py")],
        autonomy_dir,
        3
    )
    if p4:
        processes.append(("Dashboard", p4))
    
    log("")
    log("=" * 60)
    log("SISTEMA INICIADO")
    log("=" * 60)
    log("")
    log("Servicios activos:")
    for name, p in processes:
        log(f"  - {name}: PID {p.pid}")
    log("")
    log("URLs de acceso:")
    log("  Dashboard: http://127.0.0.1:8040")
    log("  Chat:      http://127.0.0.1:8030")
    log("  Brain API: http://127.0.0.1:8000/docs")
    log("  Advisor:   http://127.0.0.1:8010/docs")
    log("")
    log("Presiona Enter para detener todos los servicios...")
    input()
    
    log("")
    log("Deteniendo servicios...")
    for name, p in processes:
        log(f"  Deteniendo {name}...")
        try:
            p.terminate()
            p.wait(timeout=5)
        except:
            p.kill()
    log("Servicios detenidos.")

if __name__ == "__main__":
    main()
