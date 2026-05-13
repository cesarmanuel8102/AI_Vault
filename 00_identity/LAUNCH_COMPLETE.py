#!/usr/bin/env python3
"""
AI_VAULT COMPLETE LAUNCHER
Inicia todo el sistema y el Phase Manager con visibilidad
"""

import subprocess
import time
import sys
from pathlib import Path
import threading
import sys

# Redirigir salida para evitar problemas de encoding
sys.stdout = open(sys.stdout.fileno(), mode='w', encoding='utf-8', buffering=1)
sys.stderr = open(sys.stderr.fileno(), mode='w', encoding='utf-8', buffering=1)

def log(msg):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}")

def main():
    base_dir = Path(r"C:\AI_VAULT\00_identity")
    autonomy_dir = base_dir / "autonomy_system"
    
    log("=" * 60)
    log("AI_VAULT COMPLETE SYSTEM LAUNCH")
    log("=" * 60)
    log("")
    log("FASE 0: INIT - Inicializacion")
    log("")
    
    processes = []
    
    # 1. Brain Server
    log("[1/5] Iniciando Brain Server (puerto 8000)...")
    p1 = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "brain_server:app", "--host", "127.0.0.1", "--port", "8000", "--log-level", "warning"],
        cwd=base_dir,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    processes.append(("Brain Server", p1))
    log(f"   Brain Server iniciado (PID: {p1.pid})")
    time.sleep(5)
    
    # 2. Advisor Server
    log("[2/5] Iniciando Advisor Server (puerto 8010)...")
    p2 = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "advisor_server:app", "--host", "127.0.0.1", "--port", "8010", "--log-level", "warning"],
        cwd=base_dir,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    processes.append(("Advisor Server", p2))
    log(f"   Advisor Server iniciado (PID: {p2.pid})")
    time.sleep(5)
    
    # 3. Chat Interface
    log("[3/5] Iniciando Chat Interface (puerto 8030)...")
    p3 = subprocess.Popen(
        [sys.executable, str(autonomy_dir / "chat_interface.py")],
        cwd=autonomy_dir,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    processes.append(("Chat Interface", p3))
    log(f"   Chat Interface iniciado (PID: {p3.pid})")
    time.sleep(3)
    
    # 4. Dashboard
    log("[4/5] Iniciando Dashboard (puerto 8040)...")
    p4 = subprocess.Popen(
        [sys.executable, str(autonomy_dir / "dashboard_simple.py")],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    processes.append(("Dashboard", p4))
    log(f"   Dashboard iniciado (PID: {p4.pid})")
    time.sleep(3)
    
    # 5. Phase Manager (En primer plano, con output visible)
    log("[5/5] Iniciando Phase Manager (autonomia)...")
    log("   El Phase Manager ejecutara las fases 1-6")
    log("   Veras el progreso en tiempo real")
    log("")
    
    try:
        log("=" * 60)
        log("INICIANDO PHASE MANAGER")
        log("=" * 60)
        log("")
        
        # Ejecutar Phase Manager con output visible
        p5 = subprocess.Popen(
            [sys.executable, str(autonomy_dir / "autonomy_phases.py")],
            cwd=autonomy_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8'
        )
        
        # Leer output en tiempo real
        for line in p5.stdout:
            print(line, end='')
            sys.stdout.flush()
        
        p5.wait()
        
    except KeyboardInterrupt:
        log("")
        log("=" * 60)
        log("DETENIENDO SISTEMA")
        log("=" * 60)
        log("")
        
        for name, process in processes:
            log(f"Deteniendo {name} (PID: {process.pid})...")
            try:
                process.terminate()
                process.wait(timeout=5)
            except:
                try:
                    process.kill()
                except:
                    pass
        
        log("")
        log("Sistema detenido.")
        log("")

if __name__ == "__main__":
    main()
