"""
AI_VAULT Prometheus Metrics
Fase 8: Monitoring - Prometheus Metrics Collection
"""

import time
import threading
from typing import Dict, List, Optional, Callable
from datetime import datetime
from dataclasses import dataclass, field
from collections import defaultdict
import json
import logging

logger = logging.getLogger(__name__)


@dataclass
class MetricValue:
    """Valor de metrica con timestamp"""
    value: float
    timestamp: datetime = field(default_factory=datetime.now)
    labels: Dict[str, str] = field(default_factory=dict)


class Counter:
    """Contador monotonicamente creciente"""
    
    def __init__(self, name: str, description: str = "", labels: List[str] = None):
        self.name = name
        self.description = description
        self.label_names = labels or []
        self._values: Dict[tuple, float] = defaultdict(float)
        self._lock = threading.Lock()
    
    def inc(self, amount: float = 1, **labels):
        """Incrementa el contador"""
        with self._lock:
            label_key = tuple(labels.get(k, "") for k in self.label_names)
            self._values[label_key] += amount
    
    def get(self, **labels) -> float:
        """Obtiene valor actual"""
        label_key = tuple(labels.get(k, "") for k in self.label_names)
        return self._values.get(label_key, 0)
    
    def collect(self) -> List[Dict]:
        """Recolecta todas las series"""
        with self._lock:
            return [
                {
                    "labels": dict(zip(self.label_names, label_key)),
                    "value": value
                }
                for label_key, value in self._values.items()
            ]


class Gauge:
    """Metrica que puede subir o bajar"""
    
    def __init__(self, name: str, description: str = "", labels: List[str] = None):
        self.name = name
        self.description = description
        self.label_names = labels or []
        self._values: Dict[tuple, float] = defaultdict(float)
        self._lock = threading.Lock()
    
    def set(self, value: float, **labels):
        """Establece valor"""
        with self._lock:
            label_key = tuple(labels.get(k, "") for k in self.label_names)
            self._values[label_key] = value
    
    def inc(self, amount: float = 1, **labels):
        """Incrementa valor"""
        with self._lock:
            label_key = tuple(labels.get(k, "") for k in self.label_names)
            self._values[label_key] += amount
    
    def dec(self, amount: float = 1, **labels):
        """Decrementa valor"""
        self.inc(-amount, **labels)
    
    def get(self, **labels) -> float:
        """Obtiene valor actual"""
        label_key = tuple(labels.get(k, "") for k in self.label_names)
        return self._values.get(label_key, 0)
    
    def collect(self) -> List[Dict]:
        """Recolecta todas las series"""
        with self._lock:
            return [
                {
                    "labels": dict(zip(self.label_names, label_key)),
                    "value": value
                }
                for label_key, value in self._values.items()
            ]


class Histogram:
    """Histograma para distribucion de valores"""
    
    DEFAULT_BUCKETS = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10]
    
    def __init__(self, name: str, description: str = "", 
                 labels: List[str] = None, buckets: List[float] = None):
        self.name = name
        self.description = description
        self.label_names = labels or []
        self.buckets = sorted(buckets or self.DEFAULT_BUCKETS)
        self._counts: Dict[tuple, List[int]] = defaultdict(lambda: [0] * (len(self.buckets) + 1))
        self._sums: Dict[tuple, float] = defaultdict(float)
        self._lock = threading.Lock()
    
    def observe(self, value: float, **labels):
        """Registra una observacion"""
        with self._lock:
            label_key = tuple(labels.get(k, "") for k in self.label_names)
            
            # Encontrar bucket
            bucket_idx = len(self.buckets)
            for i, bucket in enumerate(self.buckets):
                if value <= bucket:
                    bucket_idx = i
                    break
            
            self._counts[label_key][bucket_idx] += 1
            self._sums[label_key] += value
    
    def collect(self) -> Dict:
        """Recolecta datos del histograma"""
        with self._lock:
            result = {}
            for label_key, counts in self._counts.items():
                labels = dict(zip(self.label_names, label_key))
                result[tuple(label_key)] = {
                    "labels": labels,
                    "buckets": [
                        {"le": float("inf") if i >= len(self.buckets) else self.buckets[i], 
                         "count": sum(counts[:i+1])}
                        for i in range(len(counts))
                    ],
                    "sum": self._sums[label_key],
                    "count": sum(counts)
                }
            return result


class Summary:
    """Resumen con percentiles calculados"""
    
    def __init__(self, name: str, description: str = "", 
                 labels: List[str] = None, quantiles: List[float] = None):
        self.name = name
        self.description = description
        self.label_names = labels or []
        self.quantiles = quantiles or [0.5, 0.9, 0.99]
        self._values: Dict[tuple, List[float]] = defaultdict(list)
        self._lock = threading.Lock()
    
    def observe(self, value: float, **labels):
        """Registra una observacion"""
        with self._lock:
            label_key = tuple(labels.get(k, "") for k in self.label_names)
            self._values[label_key].append(value)
            
            # Limitar tamaño para evitar memory leak
            if len(self._values[label_key]) > 10000:
                self._values[label_key] = self._values[label_key][-5000:]
    
    def collect(self) -> Dict:
        """Calcula percentiles"""
        with self._lock:
            result = {}
            for label_key, values in self._values.items():
                if not values:
                    continue
                
                sorted_values = sorted(values)
                n = len(sorted_values)
                
                quantile_values = {}
                for q in self.quantiles:
                    idx = int(q * n)
                    quantile_values[f"quantile_{int(q*100)}"] = sorted_values[min(idx, n-1)]
                
                labels = dict(zip(self.label_names, label_key))
                result[tuple(label_key)] = {
                    "labels": labels,
                    "quantiles": quantile_values,
                    "count": n,
                    "sum": sum(values)
                }
            return result


class MetricsCollector:
    """
    Colector central de metricas
    """
    
    def __init__(self):
        self._counters: Dict[str, Counter] = {}
        self._gauges: Dict[str, Gauge] = {}
        self._histograms: Dict[str, Histogram] = {}
        self._summaries: Dict[str, Summary] = {}
        self._lock = threading.Lock()
    
    def create_counter(self, name: str, description: str = "", 
                       labels: List[str] = None) -> Counter:
        """Crea o obtiene un contador"""
        with self._lock:
            if name not in self._counters:
                self._counters[name] = Counter(name, description, labels)
            return self._counters[name]
    
    def create_gauge(self, name: str, description: str = "", 
                     labels: List[str] = None) -> Gauge:
        """Crea o obtiene un gauge"""
        with self._lock:
            if name not in self._gauges:
                self._gauges[name] = Gauge(name, description, labels)
            return self._gauges[name]
    
    def create_histogram(self, name: str, description: str = "", 
                         labels: List[str] = None, buckets: List[float] = None) -> Histogram:
        """Crea o obtiene un histograma"""
        with self._lock:
            if name not in self._histograms:
                self._histograms[name] = Histogram(name, description, labels, buckets)
            return self._histograms[name]
    
    def create_summary(self, name: str, description: str = "", 
                       labels: List[str] = None, quantiles: List[float] = None) -> Summary:
        """Crea o obtiene un summary"""
        with self._lock:
            if name not in self._summaries:
                self._summaries[name] = Summary(name, description, labels, quantiles)
            return self._summaries[name]
    
    def collect_all(self) -> Dict:
        """Recolecta todas las metricas"""
        metrics = {
            "counters": {},
            "gauges": {},
            "histograms": {},
            "summaries": {},
            "timestamp": datetime.now().isoformat()
        }
        
        for name, counter in self._counters.items():
            metrics["counters"][name] = {
                "description": counter.description,
                "values": counter.collect()
            }
        
        for name, gauge in self._gauges.items():
            metrics["gauges"][name] = {
                "description": gauge.description,
                "values": gauge.collect()
            }
        
        for name, hist in self._histograms.items():
            metrics["histograms"][name] = {
                "description": hist.description,
                "values": hist.collect()
            }
        
        for name, summary in self._summaries.items():
            metrics["summaries"][name] = {
                "description": summary.description,
                "values": summary.collect()
            }
        
        return metrics
    
    def export_prometheus(self) -> str:
        """Exporta metricas en formato Prometheus"""
        lines = []
        
        # Counters
        for name, counter in self._counters.items():
            lines.append(f"# HELP {name} {counter.description}")
            lines.append(f"# TYPE {name} counter")
            for series in counter.collect():
                labels = ",".join(f'{k}="{v}"' for k, v in series["labels"].items())
                label_str = "{" + labels + "}" if labels else ""
                lines.append(f"{name}{label_str} {series['value']}")
        
        # Gauges
        for name, gauge in self._gauges.items():
            lines.append(f"# HELP {name} {gauge.description}")
            lines.append(f"# TYPE {name} gauge")
            for series in gauge.collect():
                labels = ",".join(f'{k}="{v}"' for k, v in series["labels"].items())
                label_str = "{" + labels + "}" if labels else ""
                lines.append(f"{name}{label_str} {series['value']}")
        
        return "\n".join(lines)


class Timer:
    """Context manager para medir duracion"""
    
    def __init__(self, histogram: Histogram, **labels):
        self.histogram = histogram
        self.labels = labels
        self.start_time = None
    
    def __enter__(self):
        self.start_time = time.time()
        return self
    
    def __exit__(self, *args):
        duration = time.time() - self.start_time
        self.histogram.observe(duration, **self.labels)


# Metricas predefinidas para AI_VAULT
collector = MetricsCollector()

# HTTP metrics
http_requests_total = collector.create_counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"]
)

http_request_duration = collector.create_histogram(
    "http_request_duration_seconds",
    "HTTP request duration",
    ["method", "endpoint"]
)

# System metrics
active_connections = collector.create_gauge(
    "active_connections",
    "Number of active connections"
)

memory_usage_bytes = collector.create_gauge(
    "memory_usage_bytes",
    "Memory usage in bytes",
    ["type"]
)

# Business metrics
trades_total = collector.create_counter(
    "trades_total",
    "Total number of trades",
    ["symbol", "side", "status"]
)

ai_requests_total = collector.create_counter(
    "ai_requests_total",
    "Total AI API requests",
    ["model", "status"]
)

ai_request_duration = collector.create_histogram(
    "ai_request_duration_seconds",
    "AI API request duration",
    ["model"]
)


def time_function(histogram: Histogram):
    """Decorador para medir tiempo de funcion"""
    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start
                histogram.observe(duration)
        return wrapper
    return decorator


if __name__ == "__main__":
    # Demo de metricas
    print("AI_VAULT Metrics Demo")
    print("=" * 50)
    
    # Simular requests
    for i in range(100):
        http_requests_total.inc(method="GET", endpoint="/api/data", status="200")
        http_request_duration.observe(0.05 + i * 0.001, method="GET", endpoint="/api/data")
    
    # Simular trades
    trades_total.inc(symbol="BTC", side="buy", status="filled")
    trades_total.inc(symbol="BTC", side="sell", status="filled")
    trades_total.inc(symbol="ETH", side="buy", status="filled")
    
    # Actualizar gauges
    active_connections.set(42)
    memory_usage_bytes.set(1024 * 1024 * 512, type="heap")
    
    # Mostrar metricas
    print("\nMetricas recolectadas:")
    metrics = collector.collect_all()
    print(json.dumps(metrics, indent=2))
    
    print("\n\nFormato Prometheus:")
    print(collector.export_prometheus())
