#!/usr/bin/env python3
"""
AI_VAULT Services Monitor
Mantiene Brain V9 y Dashboard corriendo, reinicia si fallan
"""

import subprocess
import time
import json
import urllib.request
import urllib.error
import os
import sys
from datetime import datetime

# Configuración
SERVICES = {
    "BrainV9": {
        "name": "Brain V9",
        "port": 8090,
        "endpoint": "/health",
        "command": ["python", "-m", "brain_v9.main"],
        "cwd": "C:\\AI_VAULT\\tmp_agent",
        "log": "C:\\AI_VAULT\\tmp_agent\\logs\\brain_v9_monitor.log"
    },
    "Dashboard": {
        "name": "Dashboard",
        "port": 8070,
        "endpoint": "/api/health",
        "command": ["python", "dashboard_server.py"],
        "cwd": "C:\\AI_VAULT\\00_identity\\autonomy_system",
        "log": "C:\\AI_VAULT\\00_identity\\autonomy_system\\dashboard_monitor.log"
    }
}

LOG_FILE = "C:\\AI_VAULT\\tmp_agent\\monitor_service.log"

def log_message(message, level="INFO"):
    """Escribe mensaje en log y consola"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_line = f"[{timestamp}] [{level}] {message}"
    print(log_line)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(log_line + "\n")
    except:
        pass

def check_service(port, endpoint, timeout=5):
    """Verifica si un servicio está respondiendo"""
    try:
        url = f"http://127.0.0.1:{port}{endpoint}"
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            data = json.loads(resp.read().decode())
            return data.get('status') == 'healthy' or data.get('ok') == True
    except Exception as e:
        return False

def kill_existing_processes(command):
    """Mata procesos existentes del servicio por puerto específico."""
    # Find the port for this service by matching the command
    target_port = None
    for svc in SERVICES.values():
        cmd_key = svc['command'][1] if len(svc['command']) > 1 else svc['command'][0]
        if cmd_key == command:
            target_port = svc['port']
            break

    if target_port is None:
        return

    try:
        result = subprocess.run(
            ['netstat', '-ano'],
            capture_output=True,
            text=True,
            timeout=10
        )
        for line in result.stdout.split('\n'):
            if f':{target_port}' in line and 'LISTENING' in line:
                parts = line.split()
                if len(parts) >= 5:
                    try:
                        pid = int(parts[-1])
                        if pid > 0:
                            subprocess.run(['taskkill', '/F', '/PID', str(pid)],
                                         capture_output=True, timeout=10)
                            log_message(f"  Killed PID {pid} on port {target_port}")
                    except (ValueError, subprocess.TimeoutExpired):
                        pass
    except Exception:
        pass

def start_service(service_key, service_config):
    """Inicia un servicio"""
    log_message(f"Iniciando {service_config['name']}...")
    
    # Limpiar procesos previos
    kill_existing_processes(service_config['command'][1] if len(service_config['command']) > 1 else service_config['command'][0])
    time.sleep(2)
    
    try:
        # Iniciar proceso
        process = subprocess.Popen(
            service_config['command'],
            cwd=service_config['cwd'],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NEW_CONSOLE
        )
        
        # Log del servicio
        with open(service_config['log'], 'a') as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Servicio iniciado (PID: {process.pid})\n")
        
        log_message(f"{service_config['name']} iniciado (PID: {process.pid})", "SUCCESS")
        time.sleep(5)  # Esperar a que inicie
        return True
        
    except Exception as e:
        log_message(f"Error iniciando {service_config['name']}: {e}", "ERROR")
        return False

def monitor_services():
    """Loop principal de monitoreo"""
    log_message("🚀 AI_VAULT Monitor iniciado")
    log_message("Verificando cada 30 segundos. Presiona Ctrl+C para detener.\n")
    
    try:
        while True:
            for service_key, service_config in SERVICES.items():
                is_healthy = check_service(
                    service_config['port'], 
                    service_config['endpoint']
                )
                
                if not is_healthy:
                    log_message(f"⚠️ {service_config['name']} no responde en puerto {service_config['port']}", "WARN")
                    if start_service(service_key, service_config):
                        log_message(f"✓ {service_config['name']} reiniciado", "SUCCESS")
                    else:
                        log_message(f"✗ Falló reiniciar {service_config['name']}", "ERROR")
                else:
                    log_message(f"✓ {service_config['name']} saludable en puerto {service_config['port']}")
            
            log_message("")
            time.sleep(30)
            
    except KeyboardInterrupt:
        log_message("\n👋 Monitor detenido por usuario", "INFO")
        sys.exit(0)
    except Exception as e:
        log_message(f"Error en monitor: {e}", "ERROR")
        time.sleep(10)
        monitor_services()  # Reintentar

if __name__ == "__main__":
    # Asegurar directorio de logs existe
    os.makedirs(os.path.dirname(LOG_FILE), exist_ok=True)
    
    # Iniciar monitoreo
    monitor_services()
