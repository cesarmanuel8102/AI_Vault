"""
AI_VAULT AUTONOMY ORCHESTRATOR
Controlador maestro para el sistema de autonomía progresiva
"""

import os
import sys
import json
import time
import subprocess
import threading
import requests
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict

# Configuración
BASE_DIR = Path(r"C:\AI_VAULT\00_identity")
AUTONOMY_DIR = BASE_DIR / "autonomy_system"
STATE_DIR = AUTONOMY_DIR / "state"
LOGS_DIR = AUTONOMY_DIR / "logs"
ROADMAP_PATH = AUTONOMY_DIR / "autonomy_roadmap.json"

# Asegurar directorios
for d in [AUTONOMY_DIR, STATE_DIR, LOGS_DIR]:
    d.mkdir(parents=True, exist_ok=True)


@dataclass
class ServiceStatus:
    name: str
    port: int
    pid: Optional[int]
    status: str  # "running", "stopped", "error"
    last_check: str
    health: Optional[Dict] = None


@dataclass
class AutonomyState:
    phase: int
    phase_name: str
    current_goal: str
    services: Dict[str, dict]
    last_update: str
    metrics: Dict[str, Any]


class AutonomyOrchestrator:
    """Orquestador del sistema de autonomía"""
    
    SERVICES = {
        "brain_server": {"port": 8000, "script": "brain_server.py", "module": "brain_server:app"},
        "advisor_server": {"port": 8010, "script": "advisor_server.py", "module": "advisor_server:app"},
    }
    
    def __init__(self):
        self.state = self._load_state()
        self.processes: Dict[str, subprocess.Popen] = {}
        self.monitoring = False
        self.monitor_thread = None
        
    def _load_state(self) -> AutonomyState:
        """Cargar estado de autonomía"""
        state_file = STATE_DIR / "autonomy_state.json"
        if state_file.exists():
            with open(state_file, 'r') as f:
                data = json.load(f)
                return AutonomyState(**data)
        
        # Estado inicial
        return AutonomyState(
            phase=0,
            phase_name="INIT",
            current_goal="Inicializar sistema de autonomía",
            services={},
            last_update=datetime.now(timezone.utc).isoformat(),
            metrics={}
        )
    
    def _save_state(self):
        """Guardar estado de autonomía"""
        state_file = STATE_DIR / "autonomy_state.json"
        with open(state_file, 'w') as f:
            json.dump(asdict(self.state), f, indent=2, default=str)
    
    def _log(self, message: str, level: str = "INFO"):
        """Log de eventos"""
        timestamp = datetime.now(timezone.utc).isoformat()
        log_entry = f"[{timestamp}] [{level}] {message}"
        print(log_entry)
        
        # Guardar en archivo
        log_file = LOGS_DIR / f"orchestrator_{datetime.now().strftime('%Y%m%d')}.log"
        with open(log_file, 'a') as f:
            f.write(log_entry + "\n")
    
    def check_service(self, name: str) -> ServiceStatus:
        """Verificar estado de un servicio"""
        config = self.SERVICES[name]
        port = config["port"]
        
        # Verificar si el puerto está en uso
        try:
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(2)
            result = sock.connect_ex(('127.0.0.1', port))
            sock.close()
            
            if result == 0:
                # Puerto en uso, verificar health
                try:
                    response = requests.get(f"http://127.0.0.1:{port}/health", timeout=3)
                    health = response.json() if response.status_code == 200 else None
                    return ServiceStatus(
                        name=name,
                        port=port,
                        pid=None,  # TODO: obtener PID
                        status="running",
                        last_check=datetime.now(timezone.utc).isoformat(),
                        health=health
                    )
                except:
                    return ServiceStatus(
                        name=name,
                        port=port,
                        pid=None,
                        status="running",
                        last_check=datetime.now(timezone.utc).isoformat()
                    )
            else:
                return ServiceStatus(
                    name=name,
                    port=port,
                    pid=None,
                    status="stopped",
                    last_check=datetime.now(timezone.utc).isoformat()
                )
        except Exception as e:
            return ServiceStatus(
                name=name,
                port=port,
                pid=None,
                status="error",
                last_check=datetime.now(timezone.utc).isoformat(),
                health={"error": str(e)}
            )
    
    def start_service(self, name: str) -> bool:
        """Iniciar un servicio"""
        config = self.SERVICES[name]
        module = config["module"]
        port = config["port"]
        
        self._log(f"Iniciando servicio: {name} en puerto {port}")
        
        try:
            # Verificar si ya está corriendo
            status = self.check_service(name)
            if status.status == "running":
                self._log(f"Servicio {name} ya está corriendo")
                return True
            
            # Iniciar proceso
            if name in ["dashboard", "chat_interface"]:
                # Para servicios en autonomy_system, ejecutar directamente
                script_path = AUTONOMY_DIR / f"{name}.py"
                cmd = [sys.executable, str(script_path)]
                work_dir = str(AUTONOMY_DIR)
            else:
                # Para servicios en 00_identity, usar uvicorn
                cmd = [
                    sys.executable, "-m", "uvicorn",
                    module,
                    "--host", "127.0.0.1",
                    "--port", str(port)
                ]
                work_dir = str(BASE_DIR)
            
            # Crear archivos de log
            out_log = LOGS_DIR / f"{name}_out.log"
            err_log = LOGS_DIR / f"{name}_err.log"
            
            with open(out_log, 'w') as out, open(err_log, 'w') as err:
                process = subprocess.Popen(
                    cmd,
                    cwd=work_dir,
                    stdout=out,
                    stderr=err,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
                )
            
            self.processes[name] = process
            
            # Esperar a que inicie
            time.sleep(3)
            
            # Verificar
            status = self.check_service(name)
            if status.status == "running":
                self._log(f"Servicio {name} iniciado correctamente")
                self.state.services[name] = asdict(status)
                self._save_state()
                return True
            else:
                self._log(f"Error iniciando {name}", "ERROR")
                return False
                
        except Exception as e:
            self._log(f"Error iniciando {name}: {e}", "ERROR")
            return False
    
    def stop_service(self, name: str) -> bool:
        """Detener un servicio"""
        self._log(f"Deteniendo servicio: {name}")
        
        try:
            if name in self.processes:
                process = self.processes[name]
                process.terminate()
                process.wait(timeout=5)
                del self.processes[name]
            
            # Actualizar estado
            if name in self.state.services:
                self.state.services[name]["status"] = "stopped"
                self._save_state()
            
            return True
        except Exception as e:
            self._log(f"Error deteniendo {name}: {e}", "ERROR")
            return False
    
    def start_all_services(self) -> Dict[str, bool]:
        """Iniciar todos los servicios"""
        self._log("Iniciando todos los servicios...")
        results = {}
        
        for name in self.SERVICES:
            results[name] = self.start_service(name)
            time.sleep(2)  # Esperar entre servicios
        
        return results
    
    def stop_all_services(self):
        """Detener todos los servicios"""
        self._log("Deteniendo todos los servicios...")
        for name in list(self.processes.keys()):
            self.stop_service(name)
    
    def get_system_status(self) -> Dict:
        """Obtener estado completo del sistema"""
        status = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "phase": self.state.phase,
            "phase_name": self.state.phase_name,
            "current_goal": self.state.current_goal,
            "services": {}
        }
        
        for name in self.SERVICES:
            service_status = self.check_service(name)
            status["services"][name] = asdict(service_status)
        
        return status
    
    def advance_phase(self, new_phase: int, new_goal: str):
        """Avanzar a la siguiente fase de autonomía"""
        self._log(f"Avanzando a fase {new_phase}: {new_goal}")
        self.state.phase = new_phase
        self.state.phase_name = f"PHASE_{new_phase}"
        self.state.current_goal = new_goal
        self.state.last_update = datetime.now(timezone.utc).isoformat()
        self._save_state()
    
    def monitor_loop(self):
        """Bucle de monitoreo continuo"""
        self._log("Iniciando monitoreo de servicios...")
        self.monitoring = True
        
        while self.monitoring:
            try:
                # Verificar cada servicio
                for name in self.SERVICES:
                    status = self.check_service(name)
                    self.state.services[name] = asdict(status)
                    
                    # Si un servicio crítico se detuvo, intentar reiniciar
                    if status.status == "stopped" and name in ["brain_server", "advisor_server"]:
                        self._log(f"Servicio {name} detenido, reiniciando...", "WARN")
                        self.start_service(name)
                
                self._save_state()
                time.sleep(10)  # Verificar cada 10 segundos
                
            except Exception as e:
                self._log(f"Error en monitoreo: {e}", "ERROR")
                time.sleep(5)
    
    def start_monitoring(self):
        """Iniciar monitoreo en segundo plano"""
        self.monitor_thread = threading.Thread(target=self.monitor_loop, daemon=True)
        self.monitor_thread.start()
    
    def stop_monitoring(self):
        """Detener monitoreo"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2)


def main():
    """Función principal"""
    print("=" * 60)
    print("AI_VAULT AUTONOMY ORCHESTRATOR")
    print("=" * 60)
    print()
    
    orchestrator = AutonomyOrchestrator()
    
    # Mostrar estado actual
    status = orchestrator.get_system_status()
    print(f"Fase actual: {status['phase']} - {status['phase_name']}")
    print(f"Meta actual: {status['current_goal']}")
    print()
    print("Estado de servicios:")
    for name, svc in status['services'].items():
        print(f"  {name}: {svc['status']} (puerto {svc['port']})")
    print()
    
    # Iniciar servicios
    print("Iniciando servicios...")
    results = orchestrator.start_all_services()
    
    if all(results.values()):
        print("\n[OK] Todos los servicios iniciados correctamente")
        print("\nURLs de acceso:")
        print("  Dashboard: http://127.0.0.1:8020")
        print("  Chat:      http://127.0.0.1:8030")
        print("  Brain API: http://127.0.0.1:8000/docs")
        print("  Advisor:   http://127.0.0.1:8010/docs")
        
        # Iniciar monitoreo
        orchestrator.start_monitoring()
        
        print("\nPresiona Ctrl+C para detener...")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\n\nDeteniendo servicios...")
            orchestrator.stop_monitoring()
            orchestrator.stop_all_services()
            print("Servicios detenidos.")
    else:
        print("\n[ERROR] Algunos servicios no pudieron iniciarse")
        for name, success in results.items():
            status = "[OK]" if success else "[FAIL]"
            print(f"  {status} {name}")


if __name__ == "__main__":
    main()
