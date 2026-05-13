# PLAN DE FORTALECIMIENTO SISTÉMICO AI_VAULT
## Versión 1.0 | Fecha: 2026-03-19
## Fase: Fortalecimiento Post-Depuración

---

## 1. VISIÓN GENERAL

**Objetivo:** Transformar AI_VAULT de un sistema operativo con deuda técnica a una plataforma robusta, escalable y de alto rendimiento.

**Filosofía:** 
- **Consolidación:** Unificar componentes dispersos
- **Robustez:** Implementar manejo de errores y recuperación
- **Escalabilidad:** Preparar para crecimiento sin deuda técnica
- **Calidad:** Testing automatizado y estándares estrictos

---

## 2. FASE 1: CONSOLIDACIÓN DE ARQUITECTURA (Semanas 1-2)

### 2.1 Estructura de Directorios Canonical

```
AI_VAULT/
├── 00_CORE/                          # Núcleo del sistema
│   ├── brain/                        # Brain principal
│   │   ├── server.py                  # (ex brain_server.py)
│   │   ├── router.py                  # (ex brain_router.py)
│   │   ├── agent_loop.py             # (ex agent_loop.py)
│   │   └── chat/                     # Sistema de chat
│   │       ├── ui_server.py          # (ex brain_chat_ui_server.py)
│   │       └── interface.html        # (ex chat_interface.html)
│   ├── advisor/                      # Sistema advisor
│   │   └── server.py                 # (ex advisor_server.py)
│   └── autonomy/                     # Sistema de autonomía
│       ├── system.py                 # (ex autonomy_system/)
│       └── dashboard/
│           └── unified.html          # Dashboard unificado
│
├── 10_FINANCIAL/                     # Motor financiero
│   ├── core/                         # Núcleo financiero
│   │   ├── engine.py                 # (ex trading_engine.py)
│   │   ├── risk.py                   # (ex risk_manager.py)
│   │   └── capital.py                # (ex capital_manager.py)
│   ├── strategies/                   # Generador de estrategias
│   │   ├── generator.py              # (ex strategy_generator.py)
│   │   └── backtest.py               # (ex backtest_engine.py)
│   ├── data/                         # Integración de datos
│   │   ├── integrator.py             # (ex data_integrator.py)
│   │   └── sources/                  # Fuentes de datos
│   │       ├── quantconnect.py
│   │       └── tiingo.py
│   └── trading/                      # Trading real
│       └── pocketoption/             # (ex pocketoption_integrator.py)
│           ├── integrator.py
│           └── bridge/
│
├── 20_INFRASTRUCTURE/                # Infraestructura
│   ├── monitoring/                   # Monitoreo
│   │   ├── brain_monitor.py
│   │   └── dashboard/
│   ├── logging/                      # Sistema de logs
│   │   └── rotation.py
│   ├── state/                        # Gestión de estado
│   │   └── rooms/                    # Rooms del sistema
│   └── security/                     # Seguridad
│       └── policy/
│
├── 30_SERVICES/                      # Servicios externos
│   ├── scoring/                      # (ex 70_SCORING_ENGINE/)
│   ├── capital/                      # (ex 80_CAPITAL_ENGINE/)
│   └── experiments/                  # (ex 40_EXPERIMENTS/)
│
├── 90_SHARED/                        # Recursos compartidos
│   ├── config/                       # Configuraciones
│   ├── docs/                         # Documentación
│   └── utils/                        # Utilidades
│
└── tests/                            # Testing
    ├── unit/
    ├── integration/
    └── e2e/
```

### 2.2 Script de Migración

```python
#!/usr/bin/env python3
"""
migrate_to_canonical.py
Migra archivos a estructura canonical
"""

import shutil
import os
from pathlib import Path

MIGRATION_MAP = {
    # Core Brain
    "00_identity/brain_server.py": "00_CORE/brain/server.py",
    "00_identity/brain_router.py": "00_CORE/brain/router.py",
    "00_identity/agent_loop.py": "00_CORE/brain/agent_loop.py",
    "00_identity/brain_chat_ui_server.py": "00_CORE/brain/chat/ui_server.py",
    "00_identity/chat_interface.html": "00_CORE/brain/chat/interface.html",
    
    # Advisor
    "00_identity/advisor_server.py": "00_CORE/advisor/server.py",
    
    # Financial
    "00_identity/trading_engine.py": "10_FINANCIAL/core/engine.py",
    "00_identity/risk_manager.py": "10_FINANCIAL/core/risk.py",
    "00_identity/capital_manager.py": "10_FINANCIAL/core/capital.py",
    "00_identity/strategy_generator.py": "10_FINANCIAL/strategies/generator.py",
    "00_identity/backtest_engine.py": "10_FINANCIAL/strategies/backtest.py",
    "00_identity/data_integrator.py": "10_FINANCIAL/data/integrator.py",
    "00_identity/pocketoption_integrator.py": "10_FINANCIAL/trading/pocketoption/integrator.py",
    
    # Autonomy
    "00_identity/autonomy_system/unified_dashboard_live.html": "00_CORE/autonomy/dashboard/unified.html",
    "00_identity/phase_promotion_system.py": "00_CORE/autonomy/promotion.py",
}

def migrate_files():
    for old_path, new_path in MIGRATION_MAP.items():
        if Path(old_path).exists():
            Path(new_path).parent.mkdir(parents=True, exist_ok=True)
            shutil.move(old_path, new_path)
            print(f"✓ Migrado: {old_path} → {new_path}")

if __name__ == "__main__":
    migrate_files()
```

---

## 3. FASE 2: IMPLEMENTACIÓN DE TESTING AUTOMATIZADO (Semanas 3-4)

### 3.1 Framework de Testing

```python
# tests/conftest.py
import pytest
import asyncio
from pathlib import Path

# Fixtures globales
@pytest.fixture
def test_data_dir():
    return Path("tests/data")

@pytest.fixture
def mock_brain_state():
    return {
        "phase": "6.3",
        "status": "active",
        "roadmap": "ROADMAP_V2_AUTONOMY"
    }

@pytest.fixture(scope="session")
def event_loop():
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()
```

### 3.2 Tests Unitarios - Brain Server

```python
# tests/unit/test_brain_server.py
import pytest
from fastapi.testclient import TestClient

from 00_CORE.brain.server import app

client = TestClient(app)

class TestBrainServer:
    """Tests para el servidor Brain"""
    
    def test_health_endpoint(self):
        """Test del endpoint de salud"""
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
    
    def test_chat_endpoint(self):
        """Test del endpoint de chat"""
        response = client.post("/api/chat", json={
            "message": "test",
            "room_id": "test_room"
        })
        assert response.status_code == 200
        assert "reply" in response.json()
    
    def test_phase_status(self):
        """Test del estado de fases"""
        response = client.get("/api/status")
        assert response.status_code == 200
        data = response.json()
        assert "phases" in data
        assert "6.1" in data["phases"]

class TestErrorHandling:
    """Tests de manejo de errores"""
    
    def test_invalid_endpoint(self):
        """Test de endpoint inválido"""
        response = client.get("/invalid")
        assert response.status_code == 404
    
    def test_malformed_json(self):
        """Test de JSON malformado"""
        response = client.post("/api/chat", data="invalid json")
        assert response.status_code == 422
```

### 3.3 Tests de Integración - Financial

```python
# tests/integration/test_financial_integration.py
import pytest
from 10_FINANCIAL.core.engine import TradingEngine
from 10_FINANCIAL.core.risk import RiskManager

class TestFinancialIntegration:
    """Tests de integración del sistema financiero"""
    
    @pytest.fixture
    def trading_setup(self):
        risk_manager = RiskManager()
        engine = TradingEngine(risk_manager=risk_manager)
        return engine, risk_manager
    
    def test_trade_with_risk_management(self, trading_setup):
        """Test de trade con gestión de riesgo"""
        engine, risk_manager = trading_setup
        
        # Simular trade
        result = engine.simulate_trade(
            symbol="EURUSD",
            direction="CALL",
            amount=100,
            payout_pct=85
        )
        
        assert result is not None
        assert "risk_approved" in result
        assert result["risk_approved"] == True
    
    def test_capital_allocation(self, trading_setup):
        """Test de asignación de capital"""
        engine, _ = trading_setup
        
        allocation = engine.allocate_capital(
            total_capital=10000,
            risk_level="medium"
        )
        
        assert allocation["core"] > 0
        assert allocation["satellite"] >= 0
        assert allocation["explorer"] >= 0
```

### 3.4 Tests E2E - Complete Flow

```python
# tests/e2e/test_complete_flow.py
import pytest
import requests
import time

class TestEndToEnd:
    """Tests End-to-End completos"""
    
    BASE_URL = "http://127.0.0.1:8010"
    
    @pytest.fixture(scope="class")
    def server_running(self):
        """Verificar que el servidor está corriendo"""
        max_retries = 10
        for i in range(max_retries):
            try:
                response = requests.get(f"{self.BASE_URL}/health")
                if response.status_code == 200:
                    return True
            except:
                pass
            time.sleep(1)
        pytest.skip("Server not running")
    
    def test_full_chat_flow(self, server_running):
        """Test completo de flujo de chat"""
        # 1. Enviar mensaje
        response = requests.post(
            f"{self.BASE_URL}/api/chat",
            json={"message": "Hola Brain, ¿en qué fase estamos?", "room_id": "e2e_test"}
        )
        assert response.status_code == 200
        
        # 2. Verificar respuesta
        data = response.json()
        assert "reply" in data
        assert len(data["reply"]) > 0
        
        # 3. Verificar persistencia
        history_response = requests.get(f"{self.BASE_URL}/api/chat/history/e2e_test")
        assert history_response.status_code == 200
```

### 3.5 Suite de Testing Completa

```yaml
# tests/run_tests.yml
name: AI_VAULT Test Suite

stages:
  - name: Unit Tests
    command: pytest tests/unit/ -v --cov=00_CORE --cov-report=html
    coverage_threshold: 80
    
  - name: Integration Tests
    command: pytest tests/integration/ -v --tb=short
    
  - name: E2E Tests
    command: pytest tests/e2e/ -v
    
  - name: Performance Tests
    command: python tests/performance/locustfile.py
    rps_threshold: 100
    
  - name: Security Tests
    command: bandit -r 00_CORE/ -f json -o security_report.json
    severity: HIGH
```

---

## 4. FASE 3: MEJORAS DE SEGURIDAD (Semanas 5-6)

### 4.1 Gestión de Secretos

```python
# 20_INFRASTRUCTURE/security/secrets_manager.py
import os
from pathlib import Path
from cryptography.fernet import Fernet

class SecretsManager:
    """Gestor de secretos centralizado"""
    
    def __init__(self, secrets_file: str = ".secrets/encrypted.json"):
        self.secrets_file = Path(secrets_file)
        self.key = self._load_or_create_key()
        self.cipher = Fernet(self.key)
        self._secrets = self._load_secrets()
    
    def _load_or_create_key(self) -> bytes:
        """Cargar o crear clave de cifrado"""
        key_file = Path(".secrets/.key")
        if key_file.exists():
            return key_file.read_bytes()
        
        key = Fernet.generate_key()
        key_file.parent.mkdir(parents=True, exist_ok=True)
        key_file.write_bytes(key)
        os.chmod(key_file, 0o600)  # Solo lectura para owner
        return key
    
    def get_secret(self, name: str) -> str:
        """Obtener secreto desencriptado"""
        encrypted = self._secrets.get(name)
        if encrypted:
            return self.cipher.decrypt(encrypted.encode()).decode()
        return os.getenv(name.upper())  # Fallback a env var
    
    def set_secret(self, name: str, value: str):
        """Guardar secreto encriptado"""
        encrypted = self.cipher.encrypt(value.encode()).decode()
        self._secrets[name] = encrypted
        self._save_secrets()

# Uso
secrets = SecretsManager()
openai_key = secrets.get_secret("openai_api_key")
```

### 4.2 Validación de Entradas

```python
# 20_INFRASTRUCTURE/security/validation.py
from pydantic import BaseModel, validator, Field
from typing import Optional
import re

class ChatRequest(BaseModel):
    """Modelo validado para requests de chat"""
    
    message: str = Field(..., min_length=1, max_length=5000)
    room_id: str = Field(..., regex=r"^[a-zA-Z0-9_-]+$")
    auto_apply: bool = Field(default=False)
    
    @validator('message')
    def sanitize_message(cls, v):
        """Sanitizar mensaje de entrada"""
        # Eliminar caracteres potencialmente peligrosos
        v = re.sub(r'[ -]', '', v)
        return v.strip()
    
    @validator('room_id')
    def validate_room_id(cls, v):
        """Validar formato de room_id"""
        if len(v) < 3 or len(v) > 50:
            raise ValueError("room_id debe tener entre 3 y 50 caracteres")
        return v

class TradeRequest(BaseModel):
    """Modelo validado para requests de trading"""
    
    symbol: str = Field(..., regex=r"^[A-Z]{6}$")  # EURUSD, etc
    direction: str = Field(..., regex=r"^(CALL|PUT)$")
    amount: float = Field(..., gt=0, le=10000)
    payout_pct: float = Field(..., ge=0, le=100)
    
    @validator('amount')
    def validate_amount(cls, v):
        """Validar monto de trade"""
        if v < 1:
            raise ValueError("Monto mínimo: 1 unidad")
        return v
```

### 4.3 Rate Limiting

```python
# 20_INFRASTRUCTURE/security/rate_limiter.py
from fastapi import HTTPException, Request
from functools import wraps
import time
from collections import defaultdict

class RateLimiter:
    """Rate limiter por IP y endpoint"""
    
    def __init__(self):
        self.requests = defaultdict(list)
        self.limits = {
            "default": {"requests": 100, "window": 60},  # 100 req/min
            "chat": {"requests": 30, "window": 60},      # 30 req/min
            "trade": {"requests": 10, "window": 60},    # 10 req/min
        }
    
    def is_allowed(self, key: str, endpoint_type: str = "default") -> bool:
        """Verificar si la request está permitida"""
        now = time.time()
        window = self.limits[endpoint_type]["window"]
        max_requests = self.limits[endpoint_type]["requests"]
        
        # Limpiar requests antiguas
        self.requests[key] = [t for t in self.requests[key] if now - t < window]
        
        if len(self.requests[key]) >= max_requests:
            return False
        
        self.requests[key].append(now)
        return True
    
    def limit(self, endpoint_type: str = "default"):
        """Decorator para rate limiting"""
        def decorator(func):
            @wraps(func)
            async def wrapper(request: Request, *args, **kwargs):
                client_ip = request.client.host
                if not self.is_allowed(client_ip, endpoint_type):
                    raise HTTPException(
                        status_code=429, 
                        detail="Rate limit exceeded. Please try again later."
                    )
                return await func(request, *args, **kwargs)
            return wrapper
        return decorator

rate_limiter = RateLimiter()

# Uso en endpoints
@app.post("/api/chat")
@rate_limiter.limit("chat")
async def chat_endpoint(request: Request, body: ChatRequest):
    # ...
```

---

## 5. FASE 4: OPTIMIZACIÓN DE RENDIMIENTO (Semanas 7-8)

### 5.1 Caching Inteligente

```python
# 20_INFRASTRUCTURE/caching/cache_manager.py
from functools import wraps
from typing import Any, Optional
import json
import hashlib
import time
from pathlib import Path

class CacheManager:
    """Sistema de cache con TTL y persistencia"""
    
    def __init__(self, cache_dir: str = "cache", default_ttl: int = 300):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.default_ttl = default_ttl
        self._memory_cache = {}
    
    def _get_key(self, *args, **kwargs) -> str:
        """Generar clave de cache"""
        key_data = json.dumps({"args": args, "kwargs": kwargs}, sort_keys=True)
        return hashlib.md5(key_data.encode()).hexdigest()
    
    def get(self, key: str) -> Optional[Any]:
        """Obtener valor del cache"""
        # Verificar memoria primero
        if key in self._memory_cache:
            value, expiry = self._memory_cache[key]
            if time.time() < expiry:
                return value
            del self._memory_cache[key]
        
        # Verificar disco
        cache_file = self.cache_dir / f"{key}.json"
        if cache_file.exists():
            data = json.loads(cache_file.read_text())
            if time.time() < data["expiry"]:
                return data["value"]
            cache_file.unlink()  # Limpiar expirado
        
        return None
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None):
        """Guardar valor en cache"""
        ttl = ttl or self.default_ttl
        expiry = time.time() + ttl
        
        # Guardar en memoria
        self._memory_cache[key] = (value, expiry)
        
        # Persistir en disco
        cache_file = self.cache_dir / f"{key}.json"
        cache_file.write_text(json.dumps({
            "value": value,
            "expiry": expiry
        }))
    
    def cached(self, ttl: Optional[int] = None):
        """Decorator para cachear funciones"""
        def decorator(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                key = self._get_key(func.__name__, *args, **kwargs)
                
                # Intentar obtener del cache
                cached_value = self.get(key)
                if cached_value is not None:
                    return cached_value
                
                # Ejecutar función
                result = func(*args, **kwargs)
                
                # Guardar en cache
                self.set(key, result, ttl)
                
                return result
            return wrapper
        return decorator

cache = CacheManager()

# Uso
@cache.cached(ttl=600)  # Cachear por 10 minutos
def get_roadmap_status():
    """Obtener estado del roadmap (cacheado)"""
    # ... operación costosa
    return status
```

### 5.2 Optimización de Base de Datos (JSON)

```python
# 20_INFRASTRUCTURE/storage/optimized_json.py
import json
from pathlib import Path
from typing import Any, Dict, List
import threading

class OptimizedJSONStorage:
    """Almacenamiento JSON optimizado con indexing"""
    
    def __init__(self, data_dir: str = "data"):
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(exist_ok=True)
        self._cache = {}
        self._lock = threading.RLock()
        self._index = {}
    
    def _load_with_cache(self, file_path: Path) -> Dict:
        """Cargar archivo con cache"""
        str_path = str(file_path)
        
        with self._lock:
            if str_path not in self._cache:
                if file_path.exists():
                    self._cache[str_path] = json.loads(file_path.read_text())
                else:
                    self._cache[str_path] = {}
        
        return self._cache[str_path]
    
    def get(self, collection: str, doc_id: str) -> Optional[Dict]:
        """Obtener documento por ID"""
        file_path = self.data_dir / collection / f"{doc_id}.json"
        data = self._load_with_cache(file_path)
        return data.get(doc_id)
    
    def set(self, collection: str, doc_id: str, data: Dict):
        """Guardar documento"""
        file_path = self.data_dir / collection / f"{doc_id}.json"
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        with self._lock:
            self._cache[str(file_path)] = {doc_id: data}
            file_path.write_text(json.dumps({doc_id: data}, indent=2))
        
        # Actualizar índice
        self._update_index(collection, doc_id, data)
    
    def query(self, collection: str, **filters) -> List[Dict]:
        """Query con filtros (usa índice si disponible)"""
        collection_dir = self.data_dir / collection
        results = []
        
        for file_path in collection_dir.glob("*.json"):
            data = self._load_with_cache(file_path)
            for doc_id, doc in data.items():
                if all(doc.get(k) == v for k, v in filters.items()):
                    results.append(doc)
        
        return results
    
    def _update_index(self, collection: str, doc_id: str, data: Dict):
        """Actualizar índices"""
        if collection not in self._index:
            self._index[collection] = {}
        
        self._index[collection][doc_id] = {
            k: v for k, v in data.items() 
            if isinstance(v, (str, int, float, bool))
        }
```

### 5.3 Async/Await en Operaciones I/O

```python
# 00_CORE/brain/async_operations.py
import asyncio
import aiohttp
from typing import List, Dict, Any

class AsyncBrainOperations:
    """Operaciones asíncronas del Brain"""
    
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
    
    async def fetch_multiple_roadmaps(self, roadmap_ids: List[str]) -> Dict[str, Any]:
        """Obtener múltiples roadmaps en paralelo"""
        tasks = [self._fetch_roadmap(rid) for rid in roadmap_ids]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        return {
            rid: result if not isinstance(result, Exception) else None
            for rid, result in zip(roadmap_ids, results)
        }
    
    async def _fetch_roadmap(self, roadmap_id: str) -> Dict:
        """Obtener un roadmap"""
        # Simular operación asíncrona
        await asyncio.sleep(0.1)  # I/O
        return {"id": roadmap_id, "status": "loaded"}
    
    async def process_batch_candidates(self, candidates: List[Dict]) -> List[Dict]:
        """Procesar candidatos en batch asíncrono"""
        semaphore = asyncio.Semaphore(10)  # Limitar concurrencia
        
        async def process_with_limit(candidate):
            async with semaphore:
                return await self._process_candidate(candidate)
        
        tasks = [process_with_limit(c) for c in candidates]
        return await asyncio.gather(*tasks)
    
    async def _process_candidate(self, candidate: Dict) -> Dict:
        """Procesar un candidato"""
        # Operación I/O simulada
        await asyncio.sleep(0.05)
        return {**candidate, "processed": True}

# Uso
async def main():
    async with AsyncBrainOperations() as ops:
        roadmaps = await ops.fetch_multiple_roadmaps(["V2", "BL"])
        print(roadmaps)

# En FastAPI
@app.get("/api/roadmaps/batch")
async def get_batch_roadmaps():
    async with AsyncBrainOperations() as ops:
        return await ops.fetch_multiple_roadmaps(["V2", "BL"])
```

---

## 6. FASE 5: MONITOREO Y OBSERVABILIDAD (Semana 9)

### 6.1 Sistema de Métricas

```python
# 20_INFRASTRUCTURE/monitoring/metrics.py
from prometheus_client import Counter, Histogram, Gauge, start_http_server
import time

# Métricas del Brain
brain_requests_total = Counter(
    'brain_requests_total',
    'Total requests to brain',
    ['endpoint', 'status']
)

brain_request_duration = Histogram(
    'brain_request_duration_seconds',
    'Request duration',
    ['endpoint']
)

brain_active_rooms = Gauge(
    'brain_active_rooms',
    'Number of active rooms'
)

brain_phase_status = Gauge(
    'brain_phase_status',
    'Current phase status',
    ['phase']
)

# Métricas Financieras
financial_trades_total = Counter(
    'financial_trades_total',
    'Total trades executed',
    ['symbol', 'direction', 'outcome']
)

financial_pnl = Gauge(
    'financial_pnl',
    'Current P&L'
)

# Decorator para métricas
def track_metrics(endpoint: str):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = await func(*args, **kwargs)
                brain_requests_total.labels(
                    endpoint=endpoint, 
                    status="success"
                ).inc()
                return result
            except Exception as e:
                brain_requests_total.labels(
                    endpoint=endpoint, 
                    status="error"
                ).inc()
                raise
            finally:
                brain_request_duration.labels(
                    endpoint=endpoint
                ).observe(time.time() - start)
        return wrapper
    return decorator

# Iniciar servidor de métricas
start_http_server(9090)  # Prometheus scrape endpoint
```

### 6.2 Dashboard de Monitoreo

```python
# 20_INFRASTRUCTURE/monitoring/dashboard.py
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
import psutil

monitoring_app = FastAPI(title="AI_VAULT Monitoring")

@monitoring_app.get("/metrics")
async def get_metrics():
    """Endpoint para Prometheus"""
    # ... retornar métricas

@monitoring_app.get("/health/system")
async def system_health():
    """Estado de salud del sistema"""
    return {
        "cpu_percent": psutil.cpu_percent(),
        "memory_percent": psutil.virtual_memory().percent,
        "disk_usage": psutil.disk_usage('/').percent,
        "active_rooms": get_active_rooms_count(),
        "current_phase": get_current_phase()
    }

@monitoring_app.get("/health/dashboard", response_class=HTMLResponse)
async def monitoring_dashboard():
    """Dashboard visual de monitoreo"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>AI_VAULT Monitoring</title>
        <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    </head>
    <body>
        <h1>AI_VAULT System Monitor</h1>
        
        <div id="metrics">
            <canvas id="cpuChart"></canvas>
            <canvas id="memoryChart"></canvas>
        </div>
        
        <script>
            // Actualizar métricas cada 5 segundos
            setInterval(async () => {
                const response = await fetch('/health/system');
                const data = await response.json();
                updateCharts(data);
            }, 5000);
        </script>
    </body>
    </html>
    """
```

---

## 7. FASE 6: DOCUMENTACIÓN COMPLETA (Semana 10)

### 7.1 Generación Automática de Docs

```python
# scripts/generate_docs.py
"""
Generador automático de documentación
"""

import ast
from pathlib import Path
import json

def extract_docstrings(file_path: Path) -> dict:
    """Extraer docstrings de un archivo Python"""
    content = file_path.read_text()
    tree = ast.parse(content)
    
    docs = {
        "module": ast.get_docstring(tree),
        "classes": [],
        "functions": []
    }
    
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            docs["classes"].append({
                "name": node.name,
                "docstring": ast.get_docstring(node)
            })
        elif isinstance(node, ast.FunctionDef):
            docs["functions"].append({
                "name": node.name,
                "docstring": ast.get_docstring(node)
            })
    
    return docs

def generate_api_docs():
    """Generar documentación de API"""
    docs = {}
    
    for py_file in Path("00_CORE").rglob("*.py"):
        module_name = str(py_file.relative_to("00_CORE")).replace("/", ".")
        docs[module_name] = extract_docstrings(py_file)
    
    # Guardar documentación
    Path("docs/api").mkdir(parents=True, exist_ok=True)
    Path("docs/api/core_modules.json").write_text(
        json.dumps(docs, indent=2)
    )
    
    # Generar markdown
    with open("docs/api/README.md", "w") as f:
        f.write("# AI_VAULT API Documentation\n\n")
        for module, info in docs.items():
            f.write(f"## {module}\n\n")
            if info["module"]:
                f.write(f"{info['module']}\n\n")
            
            if info["classes"]:
                f.write("### Classes\n\n")
                for cls in info["classes"]:
                    f.write(f"#### {cls['name']}\n\n")
                    if cls["docstring"]:
                        f.write(f"{cls['docstring']}\n\n")

if __name__ == "__main__":
    generate_api_docs()
```

---

## 8. MÉTRICAS DE ÉXITO DEL FORTALECIMIENTO

### 8.1 Indicadores Clave

| Métrica | Antes | Objetivo | Después |
|---------|-------|----------|---------|
| **Cobertura de Tests** | ~20% | >80% | ? |
| **Tiempo de Inicio** | ~15s | <5s | ? |
| **Requests/segundo** | ~50 | >200 | ? |
| **Errores 500** | ~5% | <0.1% | ? |
| **Latencia p95** | ~500ms | <100ms | ? |
| **Deuda Técnica** | Media-Alta | Baja | ? |
| **Documentación** | Parcial | Completa | ? |

### 8.2 Validación de Calidad

```python
# tests/quality_checks.py
"""
Validación de calidad del sistema fortalecido
"""

import subprocess
import json

def check_code_quality():
    """Verificar calidad del código"""
    checks = {
        "linting": run_linter(),
        "type_checking": run_type_checker(),
        "security": run_security_scan(),
        "coverage": run_coverage_check(),
        "documentation": check_documentation()
    }
    
    return checks

def run_linter():
    """Ejecutar linter (flake8/pylint)"""
    result = subprocess.run(
        ["flake8", "00_CORE/", "--max-line-length=100"],
        capture_output=True,
        text=True
    )
    return {
        "passed": result.returncode == 0,
        "errors": result.stdout if result.stdout else "No issues"
    }

def run_coverage_check():
    """Verificar cobertura de tests"""
    result = subprocess.run(
        ["pytest", "--cov=00_CORE", "--cov-report=json"],
        capture_output=True
    )
    
    with open("coverage.json") as f:
        coverage = json.load(f)
    
    return {
        "coverage_percent": coverage["totals"]["percent_covered"],
        "passed": coverage["totals"]["percent_covered"] >= 80
    }

# Ejecutar validación
if __name__ == "__main__":
    quality_report = check_code_quality()
    print(json.dumps(quality_report, indent=2))
```

---

## 9. BITÁCORA DE FORTALECIMIENTO

| Fase | Semana | Acción | Estado | Responsable | Notas |
|------|--------|--------|--------|-------------|-------|
| 1 | 1-2 | Consolidación de Arquitectura | ⏳ PENDIENTE | - | - |
| 2 | 3-4 | Testing Automatizado | ⏳ PENDIENTE | - | - |
| 3 | 5-6 | Seguridad | ⏳ PENDIENTE | - | - |
| 4 | 7-8 | Optimización | ⏳ PENDIENTE | - | - |
| 5 | 9 | Monitoreo | ⏳ PENDIENTE | - | - |
| 6 | 10 | Documentación | ⏳ PENDIENTE | - | - |

---

## 10. CONSIDERACIONES FINALES

### 10.1 Orden de Ejecución
1. **NO** iniciar fortalecimiento sin completar la depuración
2. Ejecutar fases en orden secuencial
3. Cada fase debe pasar tests antes de la siguiente
4. Mantener sistema operativo durante transición

### 10.2 Rollback Plan
```bash
# Si algo falla, restaurar desde backup
cp -r BACKUP/00_identity/* 00_identity/
cp -r BACKUP/tmp_agent/* tmp_agent/
# Reiniciar servicios
```

### 10.3 Comunicación
- Actualizar FULL_ADN_INTEGRAL.json después de cada fase
- Documentar decisiones técnicas en docs/decisions/
- Registrar aprendizajes en bitácora

---

**Documento creado:** 2026-03-19  
**Versión:** 1.0  
**Próxima revisión:** Post-Depuración

**NOTA IMPORTANTE:** Este plan debe ejecutarse DESPUÉS de completar el PLAN_DEPURACION.md. No ejecutar ambos simultáneamente.
