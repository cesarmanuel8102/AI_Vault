#!/usr/bin/env python3
"""
Fase 5: Integracion Brain Lab
Conecta el agente con el ecosistema Brain existente
"""

import json
import urllib.request
import urllib.error
from typing import Dict, List, Optional, Any
from datetime import datetime
from dataclasses import dataclass, field


@dataclass
class BrainLabStatus:
    """Estado del sistema Brain Lab"""
    dashboard_online: bool = False
    api_online: bool = False
    rsi_online: bool = False
    last_update: str = field(default_factory=lambda: datetime.now().isoformat())
    metrics: Dict = field(default_factory=dict)


class BrainLabConnector:
    """Conector con el ecosistema Brain Lab"""
    
    def __init__(self):
        self.endpoints = {
            "dashboard": "http://127.0.0.1:8070",
            "api": "http://127.0.0.1:8000",
            "rsi": "http://127.0.0.1:8090/brain/health",
            "chat": "http://127.0.0.1:8090"
        }
        self.status = BrainLabStatus()
    
    def check_dashboard(self) -> Dict:
        """Verifica estado del dashboard"""
        try:
            req = urllib.request.Request(
                f"{self.endpoints['dashboard']}/health",
                method='GET',
                headers={'Accept': 'application/json'}
            )
            with urllib.request.urlopen(req, timeout=3) as response:
                data = json.loads(response.read().decode())
                self.status.dashboard_online = True
                return {"success": True, "status": data}
        except Exception as e:
            self.status.dashboard_online = False
            return {"success": False, "error": str(e)}
    
    def check_api(self) -> Dict:
        """Verifica estado de la API"""
        try:
            req = urllib.request.Request(
                f"{self.endpoints['api']}/health",
                method='GET'
            )
            with urllib.request.urlopen(req, timeout=3) as response:
                data = json.loads(response.read().decode())
                self.status.api_online = True
                return {"success": True, "status": data}
        except Exception as e:
            self.status.api_online = False
            return {"success": False, "error": str(e)}
    
    def check_rsi(self) -> Dict:
        """Verifica estado del RSI"""
        try:
            req = urllib.request.Request(
                self.endpoints['rsi'],
                method='GET'
            )
            with urllib.request.urlopen(req, timeout=3) as response:
                data = json.loads(response.read().decode())
                self.status.rsi_online = data.get("success", False)
                return {"success": True, "status": data}
        except Exception as e:
            self.status.rsi_online = False
            return {"success": False, "error": str(e)}
    
    def get_full_status(self) -> Dict:
        """Obtiene estado completo del ecosistema"""
        dashboard = self.check_dashboard()
        api = self.check_api()
        rsi = self.check_rsi()
        
        online_count = sum([
            dashboard.get("success", False),
            api.get("success", False),
            rsi.get("success", False)
        ])
        
        self.status.last_update = datetime.now().isoformat()
        
        return {
            "success": True,
            "timestamp": self.status.last_update,
            "summary": {
                "total_services": 3,
                "online": online_count,
                "offline": 3 - online_count,
                "health_percentage": (online_count / 3) * 100
            },
            "services": {
                "dashboard": dashboard,
                "api": api,
                "rsi": rsi
            }
        }
    
    def send_metrics_to_dashboard(self, metrics: Dict) -> bool:
        """Envia metricas al dashboard"""
        try:
            payload = json.dumps({
                "source": "brain_chat_agent",
                "timestamp": datetime.now().isoformat(),
                "metrics": metrics
            }).encode()
            
            req = urllib.request.Request(
                f"{self.endpoints['dashboard']}/api/metrics",
                data=payload,
                headers={'Content-Type': 'application/json'},
                method='POST'
            )
            
            with urllib.request.urlopen(req, timeout=5) as response:
                return response.status == 200
        except:
            return False
    
    def query_rsi_breaches(self) -> List[Dict]:
        """Consulta brechas del RSI"""
        try:
            req = urllib.request.Request(
                f"{self.endpoints['chat']}/brain/health",
                method='GET'
            )
            with urllib.request.urlopen(req, timeout=3) as response:
                data = json.loads(response.read().decode())
                
                # Extraer servicios con problemas
                services = data.get("health_status", {})
                breaches = []
                
                for service_name, status in services.items():
                    if not isinstance(status, dict):
                        continue
                    if not status.get("healthy", True):
                        breaches.append({
                            "service": service_name,
                            "status": "unhealthy",
                            "severity": "high",
                            "timestamp": datetime.now().isoformat()
                        })
                
                return breaches
        except Exception as e:
            return [{"error": str(e)}]


class RSIManager:
    """Gestor de Relacion con el Sistema RSI"""
    
    def __init__(self):
        self.connector = BrainLabConnector()
        self.active_breaches: List[Dict] = []
        self.agent_tasks: List[Dict] = []
    
    def analyze_and_prioritize(self) -> List[Dict]:
        """Analiza brechas y las prioriza"""
        breaches = self.connector.query_rsi_breaches()
        
        # Priorizar por severidad
        priority_map = {
            "critical": 1,
            "high": 2,
            "medium": 3,
            "low": 4
        }
        
        prioritized = []
        for breach in breaches:
            if "error" in breach:
                continue
            
            priority = priority_map.get(breach.get("severity", "medium"), 3)
            breach["priority_score"] = priority
            prioritized.append(breach)
        
        # Ordenar por prioridad
        prioritized.sort(key=lambda x: x["priority_score"])
        self.active_breaches = prioritized
        
        return prioritized
    
    def generate_agent_tasks(self) -> List[Dict]:
        """Genera tareas para el agente basadas en brechas"""
        tasks = []
        
        for breach in self.active_breaches[:3]:  # Top 3 prioridades
            service = breach.get("service", "unknown")
            
            task = {
                "id": f"rsi_task_{datetime.now().timestamp()}",
                "objective": f"Resolver brecha en {service}",
                "source": "RSI",
                "priority": breach.get("severity", "medium"),
                "breach": breach,
                "created_at": datetime.now().isoformat(),
                "status": "pending"
            }
            tasks.append(task)
        
        self.agent_tasks = tasks
        return tasks
    
    def report_task_completion(self, task_id: str, success: bool, 
                               result: Dict) -> bool:
        """Reporta completitud de tarea al RSI"""
        # Actualizar estado local
        for task in self.agent_tasks:
            if task["id"] == task_id:
                task["status"] = "completed" if success else "failed"
                task["completed_at"] = datetime.now().isoformat()
                task["result"] = result
                break
        
        # Enviar al dashboard si esta disponible
        return self.connector.send_metrics_to_dashboard({
            "task_completed": task_id,
            "success": success,
            "result": result
        })
    
    def get_agent_workload(self) -> Dict:
        """Obtiene carga de trabajo actual del agente"""
        pending = len([t for t in self.agent_tasks if t["status"] == "pending"])
        completed = len([t for t in self.agent_tasks if t["status"] == "completed"])
        failed = len([t for t in self.agent_tasks if t["status"] == "failed"])
        
        return {
            "total_tasks": len(self.agent_tasks),
            "pending": pending,
            "completed": completed,
            "failed": failed,
            "active_breaches": len(self.active_breaches)
        }


class DashboardReporter:
    """Reporter de metricas al dashboard"""
    
    def __init__(self):
        self.connector = BrainLabConnector()
        self.metrics_history: List[Dict] = []
    
    def report_agent_activity(self, activity_type: str, details: Dict):
        """Reporta actividad del agente"""
        metric = {
            "type": "agent_activity",
            "activity": activity_type,
            "timestamp": datetime.now().isoformat(),
            "details": details
        }
        
        self.metrics_history.append(metric)
        
        # Enviar al dashboard
        self.connector.send_metrics_to_dashboard(metric)
    
    def report_code_analysis(self, file_path: str, metrics: Dict):
        """Reporta analisis de codigo"""
        self.report_agent_activity("code_analysis", {
            "file": file_path,
            "metrics": metrics
        })
    
    def report_debug_session(self, error: str, resolution: str):
        """Reporta sesion de debug"""
        self.report_agent_activity("debug", {
            "error_type": error,
            "resolution": resolution,
            "timestamp": datetime.now().isoformat()
        })
    
    def report_refactoring(self, original_file: str, changes: List[str]):
        """Reporta refactorizacion"""
        self.report_agent_activity("refactoring", {
            "file": original_file,
            "changes_count": len(changes),
            "changes": changes[:5]  # Top 5
        })
    
    def get_summary(self) -> Dict:
        """Obtiene resumen de actividad"""
        if not self.metrics_history:
            return {"success": False, "error": "No metrics available"}
        
        total = len(self.metrics_history)
        
        # Contar por tipo
        by_type = {}
        for metric in self.metrics_history:
            act_type = metric.get("activity", "unknown")
            by_type[act_type] = by_type.get(act_type, 0) + 1
        
        return {
            "success": True,
            "total_activities": total,
            "by_type": by_type,
            "last_activity": self.metrics_history[-1]["timestamp"] if self.metrics_history else None
        }


# Funciones de conveniencia para uso externo
def get_brain_lab_status() -> Dict:
    """Obtiene estado rapido del ecosistema"""
    connector = BrainLabConnector()
    return connector.get_full_status()


def query_rsi_priorities() -> List[Dict]:
    """Consulta prioridades del RSI"""
    rsi = RSIManager()
    return rsi.analyze_and_prioritize()


def report_to_dashboard(metric_type: str, data: Dict) -> bool:
    """Reporta metrica al dashboard"""
    reporter = DashboardReporter()
    reporter.report_agent_activity(metric_type, data)
    return True


__all__ = [
    'BrainLabConnector',
    'BrainLabStatus',
    'RSIManager',
    'DashboardReporter',
    'get_brain_lab_status',
    'query_rsi_priorities',
    'report_to_dashboard'
]


if __name__ == "__main__":
    # Test
    print("Testing Brain Lab Integration...")
    
    connector = BrainLabConnector()
    status = connector.get_full_status()
    
    print(f"\nBrain Lab Status:")
    print(f"  Dashboard: {'ONLINE' if status['services']['dashboard']['success'] else 'OFFLINE'}")
    print(f"  API: {'ONLINE' if status['services']['api']['success'] else 'OFFLINE'}")
    print(f"  RSI: {'ONLINE' if status['services']['rsi']['success'] else 'OFFLINE'}")
    print(f"  Health: {status['summary']['health_percentage']:.0f}%")
    
    # Test RSI
    rsi = RSIManager()
    breaches = rsi.analyze_and_prioritize()
    print(f"\nBreaches encontradas: {len(breaches)}")
    
    tasks = rsi.generate_agent_tasks()
    print(f"Tareas generadas: {len(tasks)}")
    
    # Test reporter
    reporter = DashboardReporter()
    reporter.report_agent_activity("test", {"message": "Integration test"})
    summary = reporter.get_summary()
    print(f"\nActividades reportadas: {summary.get('total_activities', 0)}")
    
    print("\nTest completado.")
