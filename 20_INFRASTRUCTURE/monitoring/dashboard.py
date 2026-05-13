"""
AI_VAULT Monitoring Dashboard
Fase 8: Monitoring - Real-time Dashboard
"""

import json
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


@dataclass
class SystemStatus:
    """Estado del sistema"""
    status: str = "unknown"
    uptime_seconds: float = 0
    version: str = "2026.03.19"
    last_check: datetime = field(default_factory=datetime.now)
    components: Dict[str, str] = field(default_factory=dict)


@dataclass
class Alert:
    """Alerta del sistema"""
    id: str
    severity: str  # info, warning, critical
    message: str
    component: str
    timestamp: datetime = field(default_factory=datetime.now)
    acknowledged: bool = False
    resolved: bool = False


class HealthChecker:
    """Verificador de salud de componentes"""
    
    def __init__(self):
        self.checks: Dict[str, callable] = {}
        self.results: Dict[str, Dict] = {}
        self._lock = threading.Lock()
    
    def register_check(self, name: str, check_func: callable):
        """Registra una funcion de verificacion"""
        self.checks[name] = check_func
    
    def run_checks(self) -> Dict[str, Dict]:
        """Ejecuta todas las verificaciones"""
        results = {}
        
        for name, check_func in self.checks.items():
            try:
                start = time.time()
                healthy = check_func()
                duration = time.time() - start
                
                results[name] = {
                    "status": "healthy" if healthy else "unhealthy",
                    "response_time_ms": round(duration * 1000, 2),
                    "last_check": datetime.now().isoformat()
                }
            except Exception as e:
                results[name] = {
                    "status": "error",
                    "error": str(e),
                    "last_check": datetime.now().isoformat()
                }
        
        with self._lock:
            self.results = results
        
        return results


class AlertManager:
    """Gestor de alertas"""
    
    def __init__(self, max_alerts: int = 1000):
        self.max_alerts = max_alerts
        self.alerts: List[Alert] = []
        self._lock = threading.Lock()
        self._alert_handlers: List[callable] = []
    
    def add_handler(self, handler: callable):
        """Agrega un manejador de alertas"""
        self._alert_handlers.append(handler)
    
    def create_alert(self, severity: str, message: str, component: str) -> Alert:
        """Crea una nueva alerta"""
        alert = Alert(
            id=f"ALT-{int(time.time() * 1000)}",
            severity=severity,
            message=message,
            component=component
        )
        
        with self._lock:
            self.alerts.insert(0, alert)
            
            # Limitar cantidad de alertas
            if len(self.alerts) > self.max_alerts:
                self.alerts = self.alerts[:self.max_alerts]
        
        # Notificar handlers
        for handler in self._alert_handlers:
            try:
                handler(alert)
            except Exception as e:
                logger.error(f"Error en alert handler: {e}")
        
        return alert
    
    def acknowledge_alert(self, alert_id: str) -> bool:
        """Marca una alerta como reconocida"""
        with self._lock:
            for alert in self.alerts:
                if alert.id == alert_id:
                    alert.acknowledged = True
                    return True
        return False
    
    def resolve_alert(self, alert_id: str) -> bool:
        """Marca una alerta como resuelta"""
        with self._lock:
            for alert in self.alerts:
                if alert.id == alert_id:
                    alert.resolved = True
                    return True
        return False
    
    def get_active_alerts(self, severity: str = None) -> List[Alert]:
        """Obtiene alertas activas"""
        with self._lock:
            alerts = [a for a in self.alerts if not a.resolved]
            if severity:
                alerts = [a for a in alerts if a.severity == severity]
            return alerts
    
    def get_alert_summary(self) -> Dict:
        """Resumen de alertas"""
        with self._lock:
            total = len(self.alerts)
            active = len([a for a in self.alerts if not a.resolved])
            by_severity = {}
            for alert in self.alerts:
                if not alert.resolved:
                    by_severity[alert.severity] = by_severity.get(alert.severity, 0) + 1
            
            return {
                "total": total,
                "active": active,
                "by_severity": by_severity
            }


class Dashboard:
    """
    Dashboard de monitoreo centralizado
    """
    
    def __init__(self, data_dir: str = None):
        self.data_dir = Path(data_dir) if data_dir else Path("C:/AI_VAULT/20_INFRASTRUCTURE/monitoring/data")
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        self.health_checker = HealthChecker()
        self.alert_manager = AlertManager()
        
        self.system_status = SystemStatus()
        self.start_time = datetime.now()
        
        self._metrics_history: List[Dict] = []
        self._max_history = 10000
        self._lock = threading.Lock()
        
        # Iniciar threads de monitoreo
        self._running = True
        self._health_thread = threading.Thread(target=self._health_check_loop, daemon=True)
        self._health_thread.start()
    
    def _health_check_loop(self):
        """Loop de verificacion de salud"""
        while self._running:
            try:
                # Ejecutar checks
                results = self.health_checker.run_checks()
                
                # Actualizar estado del sistema
                all_healthy = all(r.get("status") == "healthy" for r in results.values())
                self.system_status.status = "healthy" if all_healthy else "degraded"
                self.system_status.uptime_seconds = (datetime.now() - self.start_time).total_seconds()
                self.system_status.components = {name: r["status"] for name, r in results.items()}
                self.system_status.last_check = datetime.now()
                
                # Crear alertas si es necesario
                for name, result in results.items():
                    if result.get("status") != "healthy":
                        self.alert_manager.create_alert(
                            severity="warning" if result.get("status") == "degraded" else "critical",
                            message=f"Component {name} is {result.get('status')}",
                            component=name
                        )
                
                # Guardar snapshot
                self._save_snapshot()
                
            except Exception as e:
                logger.error(f"Error en health check loop: {e}")
            
            time.sleep(30)  # Cada 30 segundos
    
    def _save_snapshot(self):
        """Guarda snapshot del estado actual"""
        snapshot = self.get_full_status()
        
        with self._lock:
            self._metrics_history.append({
                "timestamp": datetime.now().isoformat(),
                "data": snapshot
            })
            
            if len(self._metrics_history) > self._max_history:
                self._metrics_history = self._metrics_history[-self._max_history:]
    
    def get_full_status(self) -> Dict:
        """Obtiene estado completo del sistema"""
        return {
            "system": asdict(self.system_status),
            "health": self.health_checker.results,
            "alerts": self.alert_manager.get_alert_summary(),
            "timestamp": datetime.now().isoformat()
        }
    
    def get_dashboard_data(self) -> Dict:
        """Obtiene datos para el dashboard"""
        return {
            "status": self.system_status.status,
            "uptime": self._format_uptime(self.system_status.uptime_seconds),
            "version": self.system_status.version,
            "components": self.system_status.components,
            "alerts": {
                "summary": self.alert_manager.get_alert_summary(),
                "active": [asdict(a) for a in self.alert_manager.get_active_alerts()[:10]]
            },
            "health": self.health_checker.results,
            "timestamp": datetime.now().isoformat()
        }
    
    def _format_uptime(self, seconds: float) -> str:
        """Formatea tiempo de actividad"""
        td = timedelta(seconds=int(seconds))
        days = td.days
        hours, remainder = divmod(td.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        if days > 0:
            return f"{days}d {hours}h {minutes}m"
        elif hours > 0:
            return f"{hours}h {minutes}m"
        else:
            return f"{minutes}m {seconds}s"
    
    def export_html(self) -> str:
        """Genera HTML del dashboard"""
        data = self.get_dashboard_data()
        
        status_color = {
            "healthy": "#28a745",
            "degraded": "#ffc107",
            "unhealthy": "#dc3545",
            "unknown": "#6c757d"
        }.get(data["status"], "#6c757d")
        
        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>AI_VAULT Dashboard</title>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    margin: 0;
                    padding: 20px;
                    background: #f5f5f5;
                }}
                .header {{
                    background: #1a1a2e;
                    color: white;
                    padding: 20px;
                    border-radius: 8px;
                    margin-bottom: 20px;
                }}
                .status-indicator {{
                    display: inline-block;
                    width: 12px;
                    height: 12px;
                    border-radius: 50%;
                    background: {status_color};
                    margin-right: 10px;
                }}
                .grid {{
                    display: grid;
                    grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                    gap: 20px;
                }}
                .card {{
                    background: white;
                    border-radius: 8px;
                    padding: 20px;
                    box-shadow: 0 2px 4px rgba(0,0,0,0.1);
                }}
                .card h3 {{
                    margin-top: 0;
                    color: #333;
                }}
                .component {{
                    display: flex;
                    justify-content: space-between;
                    padding: 8px 0;
                    border-bottom: 1px solid #eee;
                }}
                .component:last-child {{
                    border-bottom: none;
                }}
                .badge {{
                    padding: 4px 8px;
                    border-radius: 4px;
                    font-size: 12px;
                    font-weight: bold;
                }}
                .badge-healthy {{ background: #d4edda; color: #155724; }}
                .badge-degraded {{ background: #fff3cd; color: #856404; }}
                .badge-unhealthy {{ background: #f8d7da; color: #721c24; }}
                .alert {{
                    padding: 10px;
                    margin: 5px 0;
                    border-radius: 4px;
                    border-left: 4px solid;
                }}
                .alert-warning {{ background: #fff3cd; border-color: #ffc107; }}
                .alert-critical {{ background: #f8d7da; border-color: #dc3545; }}
                .alert-info {{ background: #d1ecf1; border-color: #17a2b8; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1><span class="status-indicator"></span>AI_VAULT Dashboard</h1>
                <p>Status: {data['status'].upper()} | Uptime: {data['uptime']} | Version: {data['version']}</p>
                <p>Last Updated: {data['timestamp']}</p>
            </div>
            
            <div class="grid">
                <div class="card">
                    <h3>Components Health</h3>
                    {''.join(f'''
                    <div class="component">
                        <span>{name}</span>
                        <span class="badge badge-{status}">{status}</span>
                    </div>
                    ''' for name, status in data['components'].items())}
                </div>
                
                <div class="card">
                    <h3>Active Alerts ({data['alerts']['summary']['active']})</h3>
                    {''.join(f'''
                    <div class="alert alert-{alert['severity']}">
                        <strong>[{alert['severity'].upper()}]</strong> {alert['message']}
                        <br><small>{alert['component']} - {alert['timestamp']}</small>
                    </div>
                    ''' for alert in data['alerts']['active']) if data['alerts']['active'] else '<p>No active alerts</p>'}
                </div>
                
                <div class="card">
                    <h3>System Info</h3>
                    <div class="component">
                        <span>Total Alerts</span>
                        <span>{data['alerts']['summary']['total']}</span>
                    </div>
                    <div class="component">
                        <span>Warning</span>
                        <span>{data['alerts']['summary']['by_severity'].get('warning', 0)}</span>
                    </div>
                    <div class="component">
                        <span>Critical</span>
                        <span>{data['alerts']['summary']['by_severity'].get('critical', 0)}</span>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
        return html
    
    def stop(self):
        """Detiene el dashboard"""
        self._running = False


# Instancia global
dashboard = Dashboard()


def get_dashboard() -> Dashboard:
    """Retorna instancia global del dashboard"""
    return dashboard


if __name__ == "__main__":
    # Demo del dashboard
    print("AI_VAULT Dashboard Demo")
    print("=" * 50)
    
    # Registrar checks de ejemplo
    dashboard.health_checker.register_check("brain_server", lambda: True)
    dashboard.health_checker.register_check("database", lambda: True)
    dashboard.health_checker.register_check("cache", lambda: False)
    
    # Ejecutar checks
    dashboard.health_checker.run_checks()
    
    # Crear alertas de ejemplo
    dashboard.alert_manager.create_alert("warning", "High memory usage", "system")
    dashboard.alert_manager.create_alert("critical", "Database connection lost", "database")
    
    # Mostrar datos
    print("\nDashboard Data:")
    import json
    print(json.dumps(dashboard.get_dashboard_data(), indent=2))
    
    # Generar HTML
    html = dashboard.export_html()
    output_path = Path("C:/AI_VAULT/dashboard.html")
    with open(output_path, "w") as f:
        f.write(html)
    print(f"\nDashboard HTML guardado en: {output_path}")
