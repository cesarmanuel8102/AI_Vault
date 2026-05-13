#!/usr/bin/env python3
"""
AI_VAULT Autonomy System - Launcher Robusto
Inicia todos los servicios con manejo correcto de paths
"""

import subprocess
import time
import sys
import os
from pathlib import Path

def log(msg):
    print(f"[AI_VAULT] {msg}")

def main():
    base_dir = Path(r"C:\AI_VAULT\00_identity")
    autonomy_dir = base_dir / "autonomy_system"
    
    # Configurar PYTHONPATH
    env = os.environ.copy()
    pythonpath = env.get('PYTHONPATH', '')
    env['PYTHONPATH'] = f"{base_dir};{autonomy_dir};{pythonpath}"
    
    print("=" * 60)
    print("AI_VAULT AUTONOMY SYSTEM - LAUNCHER")
    print("=" * 60)
    print()
    
    processes = []
    
    # 1. Brain Server
    log("Iniciando Brain Server (puerto 8000)...")
    p1 = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "brain_server:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd=base_dir,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    processes.append(("Brain Server", p1))
    time.sleep(5)
    
    # 2. Advisor Server
    log("Iniciando Advisor Server (puerto 8010)...")
    p2 = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "advisor_server:app", "--host", "127.0.0.1", "--port", "8010"],
        cwd=base_dir,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    processes.append(("Advisor Server", p2))
    time.sleep(5)
    
    # 3. Dashboard - ejecutar directamente el archivo
    log("Iniciando Dashboard (puerto 8020)...")
    dashboard_code = '''
import sys
sys.path.insert(0, r"C:\\AI_VAULT\\00_identity")
sys.path.insert(0, r"C:\\AI_VAULT\\00_identity\\autonomy_system")
from dashboard_server import app
import uvicorn
uvicorn.run(app, host="127.0.0.1", port=8020)
'''
    p3 = subprocess.Popen(
        [sys.executable, "-c", dashboard_code],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    processes.append(("Dashboard", p3))
    time.sleep(3)
    
    # 4. Chat Interface
    log("Iniciando Chat Interface (puerto 8030)...")
    chat_code = '''
import sys
sys.path.insert(0, r"C:\\AI_VAULT\\00_identity")
sys.path.insert(0, r"C:\\AI_VAULT\\00_identity\\autonomy_system")
from chat_interface import app
import uvicorn
uvicorn.run(app, host="127.0.0.1", port=8030)
'''
    p4 = subprocess.Popen(
        [sys.executable, "-c", chat_code],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    processes.append(("Chat Interface", p4))
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
