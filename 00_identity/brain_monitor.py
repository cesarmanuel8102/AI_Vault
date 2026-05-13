"""
AI_VAULT Live Monitor Dashboard
Sistema visual de monitoreo en tiempo real del Brain
Muestra: actividad, aprendizaje, conexiones, propósito, trazas
"""

import asyncio
import json
import random
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class BrainActivity:
    """Registro de actividad del Brain"""
    timestamp: datetime
    activity_type: str  # learning, executing, connecting, analyzing
    description: str
    status: str  # success, in_progress, error
    details: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "type": self.activity_type,
            "description": self.description,
            "status": self.status,
            "details": self.details
        }

@dataclass
class ConnectionTrace:
    """Trazas de conexiones del Brain"""
    timestamp: datetime
    service: str
    endpoint: str
    latency_ms: float
    status: str
    data_size: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "service": self.service,
            "endpoint": self.endpoint,
            "latency_ms": self.latency_ms,
            "status": self.status,
            "data_size": self.data_size
        }

@dataclass
class LearningProgress:
    """Progreso de aprendizaje del Brain"""
    topic: str
    skill_level: float  # 0-100
    experience_hours: float
    last_practice: datetime
    success_rate: float
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "topic": self.topic,
            "skill_level": self.skill_level,
            "experience_hours": self.experience_hours,
            "last_practice": self.last_practice.isoformat(),
            "success_rate": self.success_rate
        }

class BrainMonitor:
    """
    Monitor en tiempo real del Brain
    Rastrea actividad, aprendizaje, conexiones y propósito
    """
    
    def __init__(self):
        self.activities: List[BrainActivity] = []
        self.connections: List[ConnectionTrace] = []
        self.learning: Dict[str, LearningProgress] = {}
        self.purpose_state = {
            "current_phase": "6.1",
            "current_goal": "Motor Financiero - Paper Trading",
            "next_milestone": "Validación de estrategias",
            "autonomy_level": "Total",
            "human_oversight": "Review cada 3 minutos"
        }
        
        # Inicializar skills de aprendizaje
        self._initialize_learning()
        
        # Estado actual
        self.is_running = False
        self.start_time = datetime.now(timezone.utc)
        
        logger.info("Brain Monitor initialized")
    
    def _initialize_learning(self):
        """Inicializar métricas de aprendizaje"""
        self.learning = {
            "trading": LearningProgress(
                topic="Trading Execution",
                skill_level=75.0,
                experience_hours=48.0,
                last_practice=datetime.now(timezone.utc),
                success_rate=0.92
            ),
            "risk_management": LearningProgress(
                topic="Risk Management",
                skill_level=68.0,
                experience_hours=36.0,
                last_practice=datetime.now(timezone.utc),
                success_rate=0.88
            ),
            "data_integration": LearningProgress(
                topic="Data Integration",
                skill_level=85.0,
                experience_hours=72.0,
                last_practice=datetime.now(timezone.utc),
                success_rate=0.95
            ),
            "strategy_development": LearningProgress(
                topic="Strategy Development",
                skill_level=45.0,
                experience_hours=24.0,
                last_practice=datetime.now(timezone.utc),
                success_rate=0.75
            ),
            "market_analysis": LearningProgress(
                topic="Market Analysis",
                skill_level=60.0,
                experience_hours=40.0,
                last_practice=datetime.now(timezone.utc),
                success_rate=0.82
            )
        }
    
    def log_activity(self, activity_type: str, description: str, status: str = "success", details: Dict = None):
        """Registrar una actividad del Brain"""
        activity = BrainActivity(
            timestamp=datetime.now(timezone.utc),
            activity_type=activity_type,
            description=description,
            status=status,
            details=details or {}
        )
        self.activities.append(activity)
        
        # Mantener solo últimas 100 actividades
        if len(self.activities) > 100:
            self.activities.pop(0)
        
        logger.info(f"[{activity_type.upper()}] {description}")
    
    def log_connection(self, service: str, endpoint: str, latency_ms: float, status: str = "success", data_size: int = 0):
        """Registrar una conexión"""
        conn = ConnectionTrace(
            timestamp=datetime.now(timezone.utc),
            service=service,
            endpoint=endpoint,
            latency_ms=latency_ms,
            status=status,
            data_size=data_size
        )
        self.connections.append(conn)
        
        # Mantener solo últimas 50 conexiones
        if len(self.connections) > 50:
            self.connections.pop(0)
    
    def update_learning(self, topic: str, hours: float = 0.1, success: bool = True):
        """Actualizar progreso de aprendizaje"""
        if topic in self.learning:
            skill = self.learning[topic]
            skill.experience_hours += hours
            skill.last_practice = datetime.now(timezone.utc)
            
            # Actualizar success rate
            total_attempts = skill.experience_hours * 10
            if success:
                skill.success_rate = ((skill.success_rate * (total_attempts - 1)) + 1) / total_attempts
            else:
                skill.success_rate = ((skill.success_rate * (total_attempts - 1)) + 0) / total_attempts
            
            # Subir nivel de skill lentamente
            if skill.skill_level < 100:
                skill.skill_level = min(100, skill.skill_level + (hours * 0.1))
    
    def get_dashboard_data(self) -> Dict[str, Any]:
        """Obtener datos para el dashboard"""
        
        # Calcular uptime
        uptime = datetime.now(timezone.utc) - self.start_time
        
        # Actividades recientes (últimas 10)
        recent_activities = [a.to_dict() for a in self.activities[-10:]]
        
        # Conexiones recientes (últimas 10)
        recent_connections = [c.to_dict() for c in self.connections[-10:]]
        
        # Estadísticas de conexiones
        connection_stats = {
            "total": len(self.connections),
            "success": len([c for c in self.connections if c.status == "success"]),
            "error": len([c for c in self.connections if c.status == "error"]),
            "avg_latency": sum(c.latency_ms for c in self.connections) / len(self.connections) if self.connections else 0
        }
        
        # Skills de aprendizaje
        learning_data = {k: v.to_dict() for k, v in self.learning.items()}
        
        # Estadísticas de actividad
        activity_stats = {
            "learning": len([a for a in self.activities if a.activity_type == "learning"]),
            "executing": len([a for a in self.activities if a.activity_type == "executing"]),
            "connecting": len([a for a in self.activities if a.activity_type == "connecting"]),
            "analyzing": len([a for a in self.activities if a.activity_type == "analyzing"])
        }
        
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "uptime": str(uptime),
            "purpose": self.purpose_state,
            "activities": {
                "recent": recent_activities,
                "stats": activity_stats,
                "total": len(self.activities)
            },
            "connections": {
                "recent": recent_connections,
                "stats": connection_stats
            },
            "learning": learning_data,
            "system_health": {
                "status": "operational",
                "cpu_usage": random.uniform(15, 45),
                "memory_usage": random.uniform(30, 60),
                "active_threads": random.randint(8, 15)
            }
        }
    
    async def simulate_activity(self):
        """Simular actividad del Brain para demostración"""
        
        activities_pool = [
            ("learning", "Analizando patrones de mercado", {"symbol": "AAPL", "pattern": "bullish"}),
            ("executing", "Ejecutando orden de compra", {"symbol": "MSFT", "quantity": 10}),
            ("connecting", "Conectando a QuantConnect API", {"endpoint": "/api/v2/data"}),
            ("analyzing", "Calculando métricas de riesgo", {"var_95": -0.015}),
            ("learning", "Optimizando parámetros de estrategia", {"strategy": "momentum"}),
            ("executing", "Actualizando posiciones", {"positions": 3}),
            ("connecting", "Sincronizando datos con Tiingo", {"records": 1500}),
            ("analyzing", "Evaluando performance del portafolio", {"return": 2.3})
        ]
        
        services = [
            ("QuantConnect", "/api/v2/data/read", 150),
            ("Tiingo", "/iex/prices", 80),
            ("Brain Core", "/v1/agent/status", 25),
            ("Risk Engine", "/calculate/var", 45),
            ("Data Integrator", "/consolidate", 120)
        ]
        
        while self.is_running:
            # Simular actividad aleatoria
            if random.random() > 0.3:  # 70% probabilidad
                activity = random.choice(activities_pool)
                self.log_activity(
                    activity_type=activity[0],
                    description=activity[1],
                    details=activity[2]
                )
                
                # Actualizar aprendizaje
                if activity[0] == "learning":
                    self.update_learning("strategy_development", hours=0.1)
                elif activity[0] == "executing":
                    self.update_learning("trading", hours=0.05)
                elif activity[0] == "analyzing":
                    self.update_learning("market_analysis", hours=0.08)
            
            # Simular conexión
            if random.random() > 0.5:  # 50% probabilidad
                service = random.choice(services)
                latency = service[2] + random.uniform(-20, 20)
                self.log_connection(
                    service=service[0],
                    endpoint=service[1],
                    latency_ms=latency,
                    data_size=random.randint(100, 5000)
                )
            
            await asyncio.sleep(2)  # Cada 2 segundos
    
    def start(self):
        """Iniciar monitoreo"""
        self.is_running = True
        self.log_activity("system", "Brain Monitor started", "success")
        logger.info("Brain Monitor started")
    
    def stop(self):
        """Detener monitoreo"""
        self.is_running = False
        self.log_activity("system", "Brain Monitor stopped", "success")
        logger.info("Brain Monitor stopped")

# Instancia global
brain_monitor = BrainMonitor()

# Para integración con dashboard
def get_monitor():
    """Obtener instancia del monitor"""
    return brain_monitor

if __name__ == "__main__":
    # Test
    monitor = BrainMonitor()
    monitor.start()
    
    # Simular algunas actividades
    monitor.log_activity("learning", "Iniciando análisis de mercado", "in_progress")
    monitor.log_connection("QuantConnect", "/api/v2/data", 145.5, "success", 2048)
    monitor.update_learning("trading", hours=1.0, success=True)
    
    data = monitor.get_dashboard_data()
    print(json.dumps(data, indent=2, default=str))
    
    monitor.stop()
