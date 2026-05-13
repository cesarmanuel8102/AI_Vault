#!/usr/bin/env python3
"""
AI_VAULT AUTONOMY SUPERVISOR
Supervisor del proceso de autoconstrucción
Monitorea, corrige y notifica eventos relevantes
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

class AutonomySupervisor:
    """Supervisor del proceso de autonomía"""
    
    def __init__(self):
        self.current_phase = 0
        self.phase_start_time = None
        self.services = {
            "brain_server": {"port": 8000, "url": "http://127.0.0.1:8000/health"},
            "advisor_server": {"port": 8010, "url": "http://127.0.0.1:8010/health"},
            "chat_interface": {"port": 8030, "url": "http://127.0.0.1:8030/health"},
            "dashboard": {"port": 8040, "url": "http://127.0.0.1:8040/health"},
        }
        self.metrics_history = []
        self.baseline = None
        
    def log(self, message, level="INFO"):
        """Log y notificación"""
        timestamp = datetime.now(timezone.utc).isoformat()
        log_entry = f"[{timestamp}] [{level}] SUPERVISOR: {message}"
        print(log_entry)
        
        # Escribir en bitácora
        with open(BITACORA_PATH, 'a', encoding='utf-8') as f:
            f.write(f"\n## [{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] SUPERVISOR\n")
            f.write(f"- **Nivel:** {level}\n")
            f.write(f"- **Mensaje:** {message}\n")
            f.write(f"- **Fase Actual:** {self.current_phase}\n")
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
    
    def detect_anomalies(self):
        """Detectar anomalías en el comportamiento"""
        if len(self.metrics_history) < 10:
            return []
        
        anomalies = []
        recent = self.metrics_history[-10:]
        
        # Verificar latencias anómalas
        for service in self.services.keys():
            latencies = [m["services"].get(service, {}).get("latency_ms", 0) for m in recent if service in m["services"]]
            if latencies:
                avg_latency = sum(latencies) / len(latencies)
                if avg_latency > 1000:  # Más de 1 segundo
                    anomalies.append(f"{service}: latencia alta ({avg_latency:.0f}ms)")
        
        return anomalies
    
    def establish_baseline(self):
        """Establecer baseline de comportamiento"""
        if len(self.metrics_history) >= 10:
            self.baseline = {
                "established_at": datetime.now(timezone.utc).isoformat(),
                "sample_size": len(self.metrics_history),
                "metrics": self.metrics_history[-10:]
            }
            self.log("Baseline establecido con éxito", "INFO")
            return True
        return False
    
    def run_phase_0(self):
        """Fase 0: INIT - Inicialización"""
        self.log("=== FASE 0: INIT - Inicialización ===", "INFO")
        self.phase_start_time = time.time()
        
        # Verificar servicios
        status, all_running = self.check_all_services()
        
        if all_running:
            self.log("✓ Todos los servicios están corriendo correctamente", "SUCCESS")
            self.log(f"Servicios activos: {list(status.keys())}", "INFO")
            
            # Verificar accesibilidad de endpoints
            for name, config in self.services.items():
                try:
                    response = requests.get(config["url"].replace('/health', ''), timeout=5)
                    self.log(f"✓ {name} accesible en puerto {config['port']}", "SUCCESS")
                except:
                    self.log(f"⚠ {name} no responde en endpoint principal", "WARNING")
            
            return True
        else:
            failed = [name for name, running in status.items() if not running]
            self.log(f"✗ Servicios fallidos: {failed}", "ERROR")
            return False
    
    def run_phase_1(self):
        """Fase 1: MONITOR - Monitoreo Activo"""
        self.log("=== FASE 1: MONITOR - Monitoreo Activo ===", "INFO")
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
                self.log("✓ Sistema estable, estableciendo baseline", "SUCCESS")
                self.establish_baseline()
                return True
            else:
                self.log(f"⚠ Estabilidad insuficiente ({stability*100:.1f}%), continuando monitoreo", "WARNING")
                return False
        else:
            self.log(f"Recolectando métricas... {len(self.metrics_history)}/10", "INFO")
            return False
    
    def run_phase_2(self):
        """Fase 2: SELF-AWARE - Autoconciencia"""
        self.log("=== FASE 2: SELF-AWARE - Autoconciencia ===", "INFO")
        self.phase_start_time = time.time()
        
        # Detectar anomalías
        anomalies = self.detect_anomalies()
        
        if anomalies:
            self.log(f"⚠ Anomalías detectadas: {anomalies}", "WARNING")
        else:
            self.log("✓ No se detectaron anomalías", "SUCCESS")
        
        # Generar diagnóstico
        status, all_running = self.check_all_services()
        
        diagnosis = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "all_services_running": all_running,
            "services_status": status,
            "anomalies": anomalies,
            "metrics_samples": len(self.metrics_history),
            "baseline_established": self.baseline is not None
        }
        
        self.log(f"Diagnóstico completado: {diagnosis}", "INFO")
        
        # Éxito si no hay anomalías y todos los servicios corren
        if not anomalies and all_running:
            self.log("✓ Autoconciencia establecida", "SUCCESS")
            return True
        
        return False
    
    def run_phase_3(self):
        """Fase 3: SELF-HEAL - Auto-sanación"""
        self.log("=== FASE 3: SELF-HEAL - Auto-sanación ===", "INFO")
        self.phase_start_time = time.time()
        
        # Verificar servicios y reiniciar si es necesario
        status, all_running = self.check_all_services()
        
        if not all_running:
            for name, running in status.items():
                if not running:
                    self.log(f"⚠ Intentando recuperar {name}...", "WARNING")
                    # Aquí iría la lógica de reinicio
                    # Por ahora solo notificamos
        
        if all_running:
            self.log("✓ Todos los servicios saludables", "SUCCESS")
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
        """Bucle principal del supervisor"""
        self.log("=== SUPERVISOR DE AUTOCONSTRUCCIÓN INICIADO ===", "INFO")
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
                
                # Fase 2: SELF-AWARE
                elif self.current_phase == 2:
                    if self.run_phase_2():
                        self.advance_phase()
                    time.sleep(30)
                
                # Fase 3: SELF-HEAL
                elif self.current_phase == 3:
                    if self.run_phase_3():
                        self.advance_phase()
                    time.sleep(10)
                
                # Fases 4-6: Requieren implementación adicional
                elif self.current_phase >= 4:
                    self.log(f"Fase {self.current_phase} requiere implementación adicional", "INFO")
                    self.log("Solicitando aprobación humana para continuar...", "WARNING")
                    time.sleep(60)
                
            except Exception as e:
                self.log(f"Error en supervisor: {e}", "ERROR")
                time.sleep(10)

if __name__ == "__main__":
    supervisor = AutonomySupervisor()
    supervisor.run()
