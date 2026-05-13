#!/usr/bin/env python3
"""
Fase 6: Sistema de Caché y Optimización
Cache para LLM queries, embeddings, y resultados frecuentes
"""

import json
import hashlib
import time
from typing import Dict, Any, Optional
from pathlib import Path
from datetime import datetime, timedelta


class LLMCache:
    """Cache para queries de LLM"""
    
    def __init__(self, cache_dir: str = None):
        if cache_dir is None:
            cache_dir = "C:/AI_VAULT/tmp_agent/cache/llm"
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.memory_cache: Dict[str, Any] = {}
        self.hit_count = 0
        self.miss_count = 0
        
    def _get_cache_key(self, prompt: str, model: str) -> str:
        """Genera clave de cache"""
        key_data = f"{model}:{prompt}"
        return hashlib.md5(key_data.encode()).hexdigest()
    
    def get(self, prompt: str, model: str, max_age_hours: int = 24) -> Optional[str]:
        """Obtiene respuesta cacheada"""
        key = self._get_cache_key(prompt, model)
        
        # Primero buscar en memoria
        if key in self.memory_cache:
            entry = self.memory_cache[key]
            if datetime.now() - entry['timestamp'] < timedelta(hours=max_age_hours):
                self.hit_count += 1
                return entry['response']
        
        # Buscar en disco
        cache_file = self.cache_dir / f"{key}.json"
        if cache_file.exists():
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    entry = json.load(f)
                
                timestamp = datetime.fromisoformat(entry['timestamp'])
                if datetime.now() - timestamp < timedelta(hours=max_age_hours):
                    # Cargar a memoria
                    self.memory_cache[key] = entry
                    self.hit_count += 1
                    return entry['response']
            except:
                pass
        
        self.miss_count += 1
        return None
    
    def set(self, prompt: str, model: str, response: str):
        """Guarda respuesta en cache"""
        key = self._get_cache_key(prompt, model)
        entry = {
            'prompt': prompt[:200],  # Truncar para no guardar todo
            'model': model,
            'response': response,
            'timestamp': datetime.now().isoformat()
        }
        
        # Guardar en memoria
        self.memory_cache[key] = entry
        
        # Guardar en disco
        cache_file = self.cache_dir / f"{key}.json"
        try:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(entry, f)
        except Exception as e:
            print(f"[WARNING] No se pudo guardar cache: {e}")
    
    def get_stats(self) -> Dict:
        """Estadísticas de cache"""
        total = self.hit_count + self.miss_count
        hit_rate = (self.hit_count / total * 100) if total > 0 else 0
        
        return {
            'hits': self.hit_count,
            'misses': self.miss_count,
            'hit_rate': f"{hit_rate:.1f}%",
            'memory_entries': len(self.memory_cache),
            'disk_entries': len(list(self.cache_dir.glob('*.json')))
        }
    
    def clear(self):
        """Limpia cache"""
        self.memory_cache.clear()
        for f in self.cache_dir.glob('*.json'):
            f.unlink()
        self.hit_count = 0
        self.miss_count = 0


class ResultCache:
    """Cache para resultados de herramientas"""
    
    def __init__(self, ttl_seconds: int = 300):
        self.cache: Dict[str, Any] = {}
        self.timestamps: Dict[str, float] = {}
        self.ttl = ttl_seconds
    
    def get(self, key: str) -> Optional[Any]:
        """Obtiene resultado cacheado"""
        if key in self.cache:
            if time.time() - self.timestamps[key] < self.ttl:
                return self.cache[key]
            else:
                # Expirado
                del self.cache[key]
                del self.timestamps[key]
        return None
    
    def set(self, key: str, value: Any):
        """Guarda resultado"""
        self.cache[key] = value
        self.timestamps[key] = time.time()
    
    def invalidate(self, pattern: str = None):
        """Invalida entradas"""
        if pattern is None:
            self.cache.clear()
            self.timestamps.clear()
        else:
            keys_to_remove = [k for k in self.cache.keys() if pattern in k]
            for k in keys_to_remove:
                del self.cache[k]
                del self.timestamps[k]


class PerformanceMonitor:
    """Monitoreo de performance"""
    
    def __init__(self):
        self.metrics: Dict[str, list] = {}
        
    def start_timer(self, operation: str):
        """Inicia timer"""
        if operation not in self.metrics:
            self.metrics[operation] = []
        return time.time()
    
    def end_timer(self, operation: str, start_time: float):
        """Termina timer y registra"""
        elapsed = time.time() - start_time
        self.metrics[operation].append(elapsed)
        return elapsed
    
    def get_stats(self, operation: str = None) -> Dict:
        """Estadísticas de performance"""
        if operation:
            if operation in self.metrics and self.metrics[operation]:
                times = self.metrics[operation]
                return {
                    'operation': operation,
                    'count': len(times),
                    'avg': sum(times) / len(times),
                    'min': min(times),
                    'max': max(times),
                    'total': sum(times)
                }
            return {'error': 'No data'}
        
        # Todas las operaciones
        return {op: self.get_stats(op) for op in self.metrics.keys()}


# Instancias globales
llm_cache = LLMCache()
result_cache = ResultCache()
performance_monitor = PerformanceMonitor()


if __name__ == "__main__":
    print("Testing cache system...")
    
    # Test LLM cache
    cache = LLMCache()
    
    # Primera llamada (miss)
    result = cache.get("test prompt", "qwen2.5:14b")
    print(f"First get (should be None): {result}")
    
    # Guardar
    cache.set("test prompt", "qwen2.5:14b", "test response")
    
    # Segunda llamada (hit)
    result = cache.get("test prompt", "qwen2.5:14b")
    print(f"Second get (should be 'test response'): {result}")
    
    # Stats
    print(f"Cache stats: {cache.get_stats()}")
    
    # Test result cache
    result_cache.set("file_analysis_agent_core", {"lines": 500})
    cached = result_cache.get("file_analysis_agent_core")
    print(f"Cached result: {cached}")
    
    print("\nCache system OK")
