#!/usr/bin/env python3
"""
AI_VAULT Services Monitor - Versión Silenciosa
Mantiene Brain V9 y Dashboard corriendo, reinicia si fallan
Sin ventanas de consola - usa pythonw.exe
"""

import subprocess
import time
import json
import urllib.request
import urllib.error
import os
import sys
from datetime import datetime
from pathlib import Path

# Evitar ventana de consola en Windows
if os.name == 'nt':
    import ctypes
    ctypes.windll.kernel32.FreeConsole()

# Configuración
SERVICES = {
    "BrainV9": {
        "name": "Brain V9",
        "port": 8090,
        "endpoint": "/health",
        "command": ["pythonw", "-m", "brain_v9.main"],
        "cwd": "C:\\AI_VAULT\\tmp_agent",
        "log": "C:\\AI_VAULT\\tmp_agent\\logs\\monitor.log"
    },
    "Dashboard": {
        "name": "Dashboard",
        "port": 8070,
        "endpoint": "/api/health",
        "command": ["pythonw", "dashboard_server.py"],
        "cwd": "C:\\AI_VAULT\\00_identity\\autonomy_system",
        "log": "C:\\AI_VAULT\\00_identity\\autonomy_system\\monitor.log"
    }
}

LOG_FILE = "C:\\AI_VAULT\\tmp_agent\\service_monitor.log"

def log_message(message, level="INFO"):
    """Escribe mensaje en log (sin print a consola)"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"[{timestamp}] [{level}] {message}\n"
    try:
        with open(LOG_FILE, "a") as f:
            f.write(log_line)
    except:
        pass

def check_service(port, endpoint, timeout=5):
    """Verifica si un servicio está respondiendo"""
    try:
        url = f"http://127.0.0.1:{port}{endpoint}"
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
            return data.get('status') == 'healthy' or data.get('ok') == True
    except:
        return False

def kill_existing_processes(command):
    """Mata procesos existentes del servicio"""
    try:
        subprocess.run(
            ['taskkill', '/F', '/IM', 'python.exe', '/FI', f'WINDOWTITLE eq *{command[1]}*'],
            capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW
        )
        subprocess.run(
            ['taskkill', '/F', '/IM', 'pythonw.exe', '/FI', f'WINDOWTITLE eq *{command[1]}*'],
            capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW
        )
    except:
        pass

def start_service(service_key, service_config):
    """Inicia un servicio sin ventana"""
    log_message(f"Iniciando {service_config['name']}...")
    
    # Limpiar procesos previos
    kill_existing_processes(service_config['command'])
    time.sleep(2)
    
    try:
        # Usar subprocess.Popen sin ventana
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        
        process = subprocess.Popen(
            service_config['command'],
            cwd=service_config['cwd'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            startupinfo=startupinfo,
            creationflags=subprocess.CREATE_NO_WINDOW
        )
        
        log_message(f"{service_config['name']} iniciado (PID: {process.pid})", "SUCCESS")
        time.sleep(5)
        return True
        
    except Exception as e:
        log_message(f"Error iniciando {service_config['name']}: {e}", "ERROR")
        return False

def monitor_services():
    """Loop principal de monitoreo - Silencioso"""
    log_message("Monitor silencioso iniciado")
    
    try:
        while True:
            for service_key, service_config in SERVICES.items():
                is_healthy = check_service(
                    service_config['port'], 
                    service_config['endpoint']
                )
                
                if not is_healthy:
                    log_message(f"{service_config['name']} no responde, reiniciando...", "WARN")
                    if start_service(service_key, service_config):
                        log_message(f"{service_config['name']} reiniciado", "SUCCESS")
                    else:
                        log_message(f"Falló reiniciar {service_config['name']}", "ERROR")
                else:
                    log_message(f"{service_config['name']} OK")
            
            time.sleep(30)
            
    except KeyboardInterrupt:
        log_message("Monitor detenido", "INFO")
        sys.exit(0)
    except Exception as e:
        log_message(f"Error en monitor: {e}", "ERROR")
        time.sleep(10)
        monitor_services()

if __name__ == "__main__":
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    monitor_services()
