#!/usr/bin/env python3
"""
AI_VAULT Autonomy System Launcher
Inicia todos los servicios del sistema de autonomía
"""

import subprocess
import time
import sys
import os
from pathlib import Path

def log(msg):
    print(f"[AI_VAULT] {msg}")

def start_service(name, cmd, cwd, delay=3):
    """Iniciar un servicio"""
    log(f"Iniciando {name}...")
    try:
        process = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == 'win32' else 0
        )
        time.sleep(delay)
        log(f"{name} iniciado (PID: {process.pid})")
        return process
    except Exception as e:
        log(f"Error iniciando {name}: {e}")
        return None

def main():
    base_dir = Path(r"C:\AI_VAULT\00_identity")
    
    # Agregar al PYTHONPATH
    sys.path.insert(0, str(base_dir))
    os.environ['PYTHONPATH'] = str(base_dir) + os.pathsep + os.environ.get('PYTHONPATH', '')
    
    print("=" * 60)
    print("AI_VAULT AUTONOMY SYSTEM LAUNCHER")
    print("=" * 60)
    print()
    
    processes = []
    
    # 1. Brain Server
    p1 = start_service(
        "Brain Server (puerto 8000)",
        [sys.executable, "-m", "uvicorn", "brain_server:app", "--host", "127.0.0.1", "--port", "8000"],
        base_dir,
        5
    )
    if p1:
        processes.append(("Brain Server", p1))
    
    # 2. Advisor Server
    p2 = start_service(
        "Advisor Server (puerto 8010)",
        [sys.executable, "-m", "uvicorn", "advisor_server:app", "--host", "127.0.0.1", "--port", "8010"],
        base_dir,
        5
    )
    if p2:
        processes.append(("Advisor Server", p2))
    
    # 3. Dashboard
    p3 = start_service(
        "Dashboard (puerto 8020)",
        [sys.executable, "-m", "uvicorn", "autonomy_system.dashboard_server:app", "--host", "127.0.0.1", "--port", "8020"],
        base_dir,
        3
    )
    if p3:
        processes.append(("Dashboard", p3))
    
    # 4. Chat Interface
    p4 = start_service(
        "Chat Interface (puerto 8030)",
        [sys.executable, "-m", "uvicorn", "autonomy_system.chat_interface:app", "--host", "127.0.0.1", "--port", "8030"],
        base_dir,
        3
    )
    if p4:
        processes.append(("Chat Interface", p4))
    
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
    print("Presiona Ctrl+C para detener todos los servicios...")
    print()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n\nDeteniendo servicios...")
        for name, process in processes:
            log(f"Deteniendo {name}...")
            try:
                process.terminate()
                process.wait(timeout=5)
            except:
                try:
                    process.kill()
                except:
                    pass
        log("Todos los servicios detenidos.")

if __name__ == "__main__":
    main()
