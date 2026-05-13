"""
AI_VAULT Cache Manager
Fase 7: Performance Optimization - Smart Caching with TTL
"""

import json
import hashlib
import pickle
import threading
from typing import Any, Optional, Dict, List, Callable, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from collections import OrderedDict
import time
import logging

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    """Entrada de cache con metadatos"""
    value: Any
    created_at: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None
    access_count: int = 0
    last_accessed: datetime = field(default_factory=datetime.now)
    size_bytes: int = 0
    
    def is_expired(self) -> bool:
        """Verifica si la entrada expiro"""
        if self.expires_at is None:
            return False
        return datetime.now() > self.expires_at
    
    def touch(self):
        """Actualiza metadatos de acceso"""
        self.access_count += 1
        self.last_accessed = datetime.now()


class CacheManager:
    """
    Gestor de cache inteligente con TTL y estrategias de eviction
    """
    
    def __init__(self, 
                 max_size: int = 1000,
                 default_ttl: int = 300,
                 eviction_policy: str = "lru"):
        """
        Inicializa el cache manager
        
        Args:
            max_size: Numero maximo de entradas
            default_ttl: TTL por defecto en segundos
            eviction_policy: lru, lfu, fifo
        """
        self.max_size = max_size
        self.default_ttl = default_ttl
        self.eviction_policy = eviction_policy
        
        self._cache: Dict[str, CacheEntry] = {}
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0
        
        # Estadisticas
        self._stats = {
            "hits": 0,
            "misses": 0,
            "evictions": 0,
            "expirations": 0
        }
        
        # Iniciar thread de limpieza
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._cleanup_thread.start()
    
    def _generate_key(self, *args, **kwargs) -> str:
        """Genera clave de cache desde argumentos"""
        key_data = json.dumps({"args": args, "kwargs": kwargs}, sort_keys=True, default=str)
        return hashlib.md5(key_data.encode()).hexdigest()
    
    def get(self, key: str, default: Any = None) -> Any:
        """
        Obtiene valor del cache
        
        Args:
            key: Clave del cache
            default: Valor por defecto si no existe
            
        Returns:
            Valor cacheado o default
        """
        with self._lock:
            entry = self._cache.get(key)
            
            if entry is None:
                self._misses += 1
                self._stats["misses"] += 1
                return default
            
            if entry.is_expired():
                del self._cache[key]
                self._stats["expirations"] += 1
                self._misses += 1
                self._stats["misses"] += 1
                return default
            
            entry.touch()
            self._hits += 1
            self._stats["hits"] += 1
            return entry.value
    
    def set(self, 
            key: str, 
            value: Any, 
            ttl: int = None,
            tags: List[str] = None) -> bool:
        """
        Almacena valor en cache
        
        Args:
            key: Clave del cache
            value: Valor a almacenar
            ttl: Tiempo de vida en segundos (None = sin expiracion)
            tags: Tags para invalidacion por grupo
            
        Returns:
            True si se almaceno exitosamente
        """
        with self._lock:
            # Verificar si necesitamos hacer espacio
            if len(self._cache) >= self.max_size and key not in self._cache:
                self._evict()
            
            # Calcular expiracion
            expires_at = None
            if ttl is not None:
                expires_at = datetime.now() + timedelta(seconds=ttl)
            elif self.default_ttl > 0:
                expires_at = datetime.now() + timedelta(seconds=self.default_ttl)
            
            # Calcular tamaño aproximado
            try:
                size = len(pickle.dumps(value))
            except:
                size = len(str(value))
            
            entry = CacheEntry(
                value=value,
                expires_at=expires_at,
                size_bytes=size
            )
            
            self._cache[key] = entry
            return True
    
    def delete(self, key: str) -> bool:
        """Elimina entrada del cache"""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False
    
    def clear(self):
        """Limpia todo el cache"""
        with self._lock:
            self._cache.clear()
            logger.info("Cache limpiado completamente")
    
    def _evict(self):
        """Evicta entradas segun la politica configurada"""
        if not self._cache:
            return
        
        if self.eviction_policy == "lru":
            # Least Recently Used
            oldest = min(self._cache.items(), key=lambda x: x[1].last_accessed)
            del self._cache[oldest[0]]
        
        elif self.eviction_policy == "lfu":
            # Least Frequently Used
            least_used = min(self._cache.items(), key=lambda x: x[1].access_count)
            del self._cache[least_used[0]]
        
        elif self.eviction_policy == "fifo":
            # First In First Out
            oldest = min(self._cache.items(), key=lambda x: x[1].created_at)
            del self._cache[oldest[0]]
        
        self._stats["evictions"] += 1
    
    def _cleanup_loop(self):
        """Loop de limpieza de entradas expiradas"""
        while True:
            time.sleep(60)  # Cada minuto
            self._cleanup_expired()
    
    def _cleanup_expired(self):
        """Elimina entradas expiradas"""
        with self._lock:
            expired = [
                key for key, entry in self._cache.items() 
                if entry.is_expired()
            ]
            for key in expired:
                del self._cache[key]
            
            if expired:
                self._stats["expirations"] += len(expired)
                logger.debug(f"Eliminadas {len(expired)} entradas expiradas")
    
    def get_stats(self) -> Dict:
        """Retorna estadisticas del cache"""
        with self._lock:
            total_size = sum(entry.size_bytes for entry in self._cache.values())
            hit_rate = self._hits / (self._hits + self._misses) if (self._hits + self._misses) > 0 else 0
            
            return {
                "size": len(self._cache),
                "max_size": self.max_size,
                "total_size_bytes": total_size,
                "hit_rate": round(hit_rate * 100, 2),
                "hits": self._stats["hits"],
                "misses": self._stats["misses"],
                "evictions": self._stats["evictions"],
                "expirations": self._stats["expirations"]
            }
    
    def cached(self, ttl: int = None, key_prefix: str = ""):
        """
        Decorador para cachear resultados de funciones
        
        Args:
            ttl: Tiempo de vida en segundos
            key_prefix: Prefijo para las claves de cache
        """
        def decorator(func: Callable) -> Callable:
            def wrapper(*args, **kwargs):
                # Generar clave
                key = f"{key_prefix}:{self._generate_key(func.__name__, args, kwargs)}"
                
                # Intentar obtener del cache
                cached_value = self.get(key)
                if cached_value is not None:
                    return cached_value
                
                # Ejecutar funcion y cachear resultado
                result = func(*args, **kwargs)
                self.set(key, result, ttl=ttl)
                return result
            
            # Agregar metodos al wrapper
            wrapper.cache_clear = lambda: self.delete(f"{key_prefix}:{func.__name__}")
            wrapper.cache_info = lambda: self.get_stats()
            
            return wrapper
        return decorator
    
    def invalidate_by_tag(self, tag: str):
        """Invalida entradas por tag (placeholder para implementacion futura)"""
        # TODO: Implementar indexacion por tags
        pass


class MultiLevelCache:
    """
    Cache de multiples niveles (L1: memoria, L2: disco)
    """
    
    def __init__(self, 
                 l1_size: int = 100,
                 l2_path: str = None,
                 l2_size: int = 1000):
        self.l1 = CacheManager(max_size=l1_size, eviction_policy="lru")
        self.l2_path = l2_path or "C:/AI_VAULT/20_INFRASTRUCTURE/caching/.l2_cache"
        self.l2_size = l2_size
        self._l2_cache: Dict[str, CacheEntry] = {}
        self._load_l2()
    
    def _load_l2(self):
        """Carga cache L2 desde disco"""
        import os
        if os.path.exists(self.l2_path):
            try:
                with open(self.l2_path, "rb") as f:
                    self._l2_cache = pickle.load(f)
            except Exception as e:
                logger.error(f"Error cargando L2 cache: {e}")
    
    def _save_l2(self):
        """Guarda cache L2 a disco"""
        try:
            import os
            os.makedirs(os.path.dirname(self.l2_path), exist_ok=True)
            with open(self.l2_path, "wb") as f:
                pickle.dump(self._l2_cache, f)
        except Exception as e:
            logger.error(f"Error guardando L2 cache: {e}")
    
    def get(self, key: str) -> Any:
        """Obtiene valor de L1 o L2"""
        # Intentar L1 primero
        value = self.l1.get(key)
        if value is not None:
            return value
        
        # Intentar L2
        entry = self._l2_cache.get(key)
        if entry and not entry.is_expired():
            # Promover a L1
            self.l1.set(key, entry.value)
            return entry.value
        
        return None
    
    def set(self, key: str, value: Any, ttl: int = None):
        """Almacena en ambos niveles"""
        self.l1.set(key, value, ttl=ttl)
        
        # Guardar en L2
        entry = CacheEntry(value=value)
        if ttl:
            entry.expires_at = datetime.now() + timedelta(seconds=ttl)
        
        self._l2_cache[key] = entry
        
        # Limitar tamaño de L2
        if len(self._l2_cache) > self.l2_size:
            oldest = min(self._l2_cache.keys(), key=lambda k: self._l2_cache[k].created_at)
            del self._l2_cache[oldest]


# Instancia global
cache_manager = CacheManager()


def cached(ttl: int = 300, key_prefix: str = ""):
    """Decorador usando cache global"""
    return cache_manager.cached(ttl=ttl, key_prefix=key_prefix)


def get_cache() -> CacheManager:
    """Retorna instancia global del cache"""
    return cache_manager


if __name__ == "__main__":
    # Demo de cache
    print("AI_VAULT Cache Manager Demo")
    print("=" * 50)
    
    cache = CacheManager(max_size=5, default_ttl=2)
    
    # Almacenar valores
    for i in range(5):
        cache.set(f"key_{i}", f"value_{i}")
    
    print(f"Cache size: {len(cache._cache)}")
    print(f"Stats: {cache.get_stats()}")
    
    # Acceder a valores
    print(f"\nAccediendo a key_0: {cache.get('key_0')}")
    print(f"Accediendo a key_1: {cache.get('key_1')}")
    
    # Agregar mas valores (deberia evictar)
    cache.set("key_5", "value_5")
    cache.set("key_6", "value_6")
    
    print(f"\nDespues de evictions:")
    print(f"Stats: {cache.get_stats()}")
    
    # Esperar expiracion
    print(f"\nEsperando expiracion...")
    time.sleep(3)
    print(f"key_0 despues de TTL: {cache.get('key_0')}")
