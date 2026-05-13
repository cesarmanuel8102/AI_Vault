#!/usr/bin/env python3
"""
AI_VAULT CONSCIOUS SUPERVISOR
Supervisor consciente de las Premisas Canónicas que guía el proceso de autoconstrucción
"""

import subprocess
import time
import json
import requests
import sys
from datetime import datetime, timezone
from pathlib import Path

# Configuración
BASE_DIR = Path(r"C:\AI_VAULT\00_identity")
AUTONOMY_DIR = BASE_DIR / "autonomy_system"
LOGS_DIR = AUTONOMY_DIR / "logs"
BITACORA_PATH = Path(r"C:\AI_VAULT\bitacora_ejecucion.md")
ROADMAP_PATH = AUTONOMY_DIR / "autonomy_roadmap.json"
CONSTITUTION_PATH = AUTONOMY_DIR / "system_constitution.json"

class ConsciousSupervisor:
    """Supervisor consciente de las premisas canónicas"""
    
    def __init__(self):
        self.current_phase = 0
        self.phase_start_time = None
        self.constitution = self._load_constitution()
        self.services = {
            "brain_server": {"port": 8000, "url": "http://127.0.0.1:8000/health"},
            "advisor_server": {"port": 8010, "url": "http://127.0.0.1:8010/health"},
            "chat_interface": {"port": 8030, "url": "http://127.0.0.1:8030/health"},
            "dashboard": {"port": 8040, "url": "http://127.0.0.1:8040/health"},
        }
        self.metrics_history = []
        self.baseline = None
        
    def _load_constitution(self):
        """Cargar constitución inyectada"""
        try:
            with open(CONSTITUTION_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            return {
                "primary_objective": "Hacer crecer el capital de forma sostenida",
                "core_principles": ["Supervivencia > retorno nominal", "Robustez > velocidad"]
            }
    
    def log(self, message, level="INFO"):
        """Log y notificación consciente"""
        timestamp = datetime.now(timezone.utc).isoformat()
        log_entry = f"[{timestamp}] [{level}] CONSCIOUS_SUPERVISOR: {message}"
        print(log_entry)
        
        # Escribir en bitácora
        with open(BITACORA_PATH, 'a', encoding='utf-8') as f:
            f.write(f"\n## [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] CONSCIOUS_SUPERVISOR\n")
            f.write(f"- **Nivel:** {level}\n")
            f.write(f"- **Mensaje:** {message}\n")
            f.write(f"- **Fase Actual:** {self.current_phase}\n")
            f.write(f"- **Conciencia:** Sistema consciente de objetivo financiero\n")
            f.write(f"- **Estado:** {'OK' if level != 'ERROR' else 'ALERTA'}\n")
    
    def check_service(self, name, config):
        """Verificar estado de un servicio"""
        try:
            response = requests.get(config["url"], timeout=5)
            return response.status_code == 200
        except:
            return False
    
    def check_all_services(self):
        """Verificar todos los servicios"""
        status = {}
        all_running = True
        
        for name, config in self.services.items():
            is_running = self.check_service(name, config)
            status[name] = is_running
            if not is_running:
                all_running = False
                self.log(f"Servicio {name} NO RESPONDE", "WARNING")
        
        return status, all_running
    
    def collect_metrics(self):
        """Recolectar métricas del sistema"""
        metrics = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "phase": self.current_phase,
            "services": {}
        }
        
        for name, config in self.services.items():
            try:
                start = time.time()
                response = requests.get(config["url"], timeout=5)
                latency = time.time() - start
                metrics["services"][name] = {
                    "status": "running" if response.status_code == 200 else "error",
                    "latency_ms": round(latency * 1000, 2),
                    "status_code": response.status_code
                }
            except Exception as e:
                metrics["services"][name] = {
                    "status": "error",
                    "error": str(e)
                }
        
        self.metrics_history.append(metrics)
        
        # Mantener solo últimas 100 métricas
        if len(self.metrics_history) > 100:
            self.metrics_history = self.metrics_history[-100:]
        
        return metrics
    
    def run_phase_0(self):
        """Fase 0: INIT - Inicialización consciente"""
        self.log("=== FASE 0: INIT - Inicialización ===", "INFO")
        self.log(f"OBJETIVO PRIMARIO: {self.constitution.get('primary_objective', 'No definido')}", "INFO")
        self.log("PRINCIPIOS RECTORES:", "INFO")
        for principle in self.constitution.get('core_principles', []):
            self.log(f"  - {principle}", "INFO")
        
        self.phase_start_time = time.time()
        
        # Verificar servicios
        status, all_running = self.check_all_services()
        
        if all_running:
            self.log("[OK] Todos los servicios están corriendo correctamente", "SUCCESS")
            self.log(f"Servicios activos: {list(status.keys())}", "INFO")
            
            # Verificar accesibilidad de endpoints
            for name, config in self.services.items():
                try:
                    response = requests.get(config["url"].replace('/health', ''), timeout=5)
                    self.log(f"[OK] {name} accesible en puerto {config['port']}", "SUCCESS")
                except:
                    self.log(f"[WARN] {name} no responde en endpoint principal", "WARNING")
            
            return True
        else:
            failed = [name for name, running in status.items() if not running]
            self.log(f"[FAIL] Servicios fallidos: {failed}", "ERROR")
            return False
    
    def run_phase_1(self):
        """Fase 1: MONITOR - Monitoreo Activo consciente"""
        self.log("=== FASE 1: MONITOR - Monitoreo Activo ===", "INFO")
        self.log("Recuerda: Robustez > velocidad", "INFO")
        self.phase_start_time = time.time()
        
        # Recolectar métricas
        metrics = self.collect_metrics()
        self.log(f"Métricas recolectadas: {len(self.metrics_history)} muestras", "INFO")
        
        # Verificar estabilidad
        if len(self.metrics_history) >= 10:
            # Calcular estabilidad
            running_count = sum(1 for m in self.metrics_history[-10:] 
                              for s in m["services"].values() if s.get("status") == "running")
            total_services = len(self.services) * 10
            stability = running_count / total_services
            
            self.log(f"Estabilidad del sistema: {stability*100:.1f}%", "INFO")
            
            if stability >= 0.95:  # 95% de uptime
                self.log("[OK] Sistema estable, estableciendo baseline", "SUCCESS")
                self.establish_baseline()
                return True
            else:
                self.log(f"[WARN] Estabilidad insuficiente ({stability*100:.1f}%), continuando monitoreo", "WARNING")
                return False
        else:
            self.log(f"Recolectando métricas... {len(self.metrics_history)}/10", "INFO")
            return False
    
    def establish_baseline(self):
        """Establecer baseline de comportamiento"""
        if len(self.metrics_history) >= 10:
            self.baseline = {
                "established_at": datetime.now(timezone.utc).isoformat(),
                "sample_size": len(self.metrics_history),
                "metrics": self.metrics_history[-10:]
            }
            self.log("[OK] Baseline establecido con éxito", "SUCCESS")
            return True
        return False
    
    def advance_phase(self):
        """Avanzar a la siguiente fase"""
        self.current_phase += 1
        self.log(f"=== AVANZANDO A FASE {self.current_phase} ===", "SUCCESS")
        
        # Actualizar roadmap
        try:
            with open(ROADMAP_PATH, 'r', encoding='utf-8') as f:
                roadmap = json.load(f)
            
            roadmap["current_phase"] = self.current_phase
            for phase in roadmap["phases"]:
                if phase["number"] == self.current_phase - 1:
                    phase["status"] = "completed"
                elif phase["number"] == self.current_phase:
                    phase["status"] = "active"
            
            with open(ROADMAP_PATH, 'w', encoding='utf-8') as f:
                json.dump(roadmap, f, indent=2)
            
            self.log(f"Roadmap actualizado a fase {self.current_phase}", "SUCCESS")
        except Exception as e:
            self.log(f"Error actualizando roadmap: {e}", "ERROR")
    
    def run(self):
        """Bucle principal del supervisor consciente"""
        self.log("=== SUPERVISOR CONSCIENTE INICIADO ===", "INFO")
        self.log("Sistema autónomo con CONCIENCIA DE PROPÓSITO FINANCIERO", "INFO")
        self.log(f"Objetivo: {self.constitution.get('primary_objective', 'No definido')}", "INFO")
        self.log("Iniciando proceso de autonomía progresiva...", "INFO")
        
        while True:
            try:
                # Fase 0: INIT
                if self.current_phase == 0:
                    if self.run_phase_0():
                        self.advance_phase()
                    else:
                        self.log("Fase 0 incompleta, reintentando en 10s...", "WARNING")
                        time.sleep(10)
                        continue
                
                # Fase 1: MONITOR
                elif self.current_phase == 1:
                    if self.run_phase_1():
                        # Verificar si hemos estado 5 minutos en esta fase
                        if self.phase_start_time and (time.time() - self.phase_start_time) >= 300:
                            self.advance_phase()
                    time.sleep(10)
                
                # Fases 2+: Requieren implementación adicional
                elif self.current_phase >= 2:
                    self.log(f"Fase {self.current_phase} requiere implementación adicional", "INFO")
                    self.log("Solicitando aprobación humana para continuar...", "WARNING")
                    time.sleep(60)
                
            except Exception as e:
                self.log(f"Error en supervisor: {e}", "ERROR")
                time.sleep(10)

if __name__ == "__main__":
    supervisor = ConsciousSupervisor()
    supervisor.run()
