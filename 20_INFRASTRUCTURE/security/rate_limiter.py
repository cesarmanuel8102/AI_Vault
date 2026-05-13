"""
AI_VAULT Rate Limiter
Fase 6: Security Enhancements - Rate Limiting Middleware
"""

import time
import json
import hashlib
from typing import Dict, Optional, Callable, Any
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from collections import defaultdict
import threading
import logging
from functools import wraps

logger = logging.getLogger(__name__)


@dataclass
class RateLimitConfig:
    """Configuracion de rate limiting"""
    requests_per_minute: int = 60
    requests_per_hour: int = 1000
    burst_size: int = 10
    window_seconds: int = 60
    block_duration_minutes: int = 30


class TokenBucket:
    """
    Implementacion de Token Bucket para rate limiting
    """
    
    def __init__(self, capacity: int, refill_rate: float):
        self.capacity = capacity
        self.tokens = capacity
        self.refill_rate = refill_rate  # tokens por segundo
        self.last_refill = time.time()
        self._lock = threading.Lock()
    
    def consume(self, tokens: int = 1) -> bool:
        """
        Intenta consumir tokens del bucket
        
        Returns:
            True si hay suficientes tokens, False si se excede el limite
        """
        with self._lock:
            self._refill()
            
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False
    
    def _refill(self):
        """Recarga tokens basado en el tiempo transcurrido"""
        now = time.time()
        elapsed = now - self.last_refill
        tokens_to_add = elapsed * self.refill_rate
        
        self.tokens = min(self.capacity, self.tokens + tokens_to_add)
        self.last_refill = now
    
    def get_remaining(self) -> float:
        """Retorna tokens restantes"""
        with self._lock:
            self._refill()
            return self.tokens


class RateLimiter:
    """
    Rate Limiter centralizado con multiples estrategias
    """
    
    def __init__(self, config: RateLimitConfig = None):
        self.config = config or RateLimitConfig()
        self._buckets: Dict[str, TokenBucket] = {}
        self._request_counts: Dict[str, Dict[int, int]] = defaultdict(lambda: defaultdict(int))
        self._blocked: Dict[str, datetime] = {}
        self._lock = threading.RLock()
        
        # Iniciar thread de limpieza
        self._cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._cleanup_thread.start()
    
    def _get_key(self, identifier: str, granularity: str = "ip") -> str:
        """Genera clave unica para rate limiting"""
        return f"{granularity}:{identifier}"
    
    def is_blocked(self, identifier: str) -> bool:
        """Verifica si un identificador esta bloqueado"""
        with self._lock:
            if identifier in self._blocked:
                if datetime.now() < self._blocked[identifier]:
                    return True
                else:
                    del self._blocked[identifier]
            return False
    
    def block(self, identifier: str, duration_minutes: int = None):
        """Bloquea un identificador temporalmente"""
        duration = duration_minutes or self.config.block_duration_minutes
        with self._lock:
            self._blocked[identifier] = datetime.now() + timedelta(minutes=duration)
            logger.warning(f"Identificador bloqueado: {identifier} por {duration} minutos")
    
    def check_rate_limit(self, identifier: str, cost: int = 1) -> tuple:
        """
        Verifica si una solicitud esta dentro del rate limit
        
        Returns:
            Tuple (allowed: bool, remaining: int, reset_time: int)
        """
        with self._lock:
            if self.is_blocked(identifier):
                return False, 0, int(self._blocked[identifier].timestamp())
            
            key = self._get_key(identifier)
            
            # Obtener o crear bucket
            if key not in self._buckets:
                self._buckets[key] = TokenBucket(
                    capacity=self.config.burst_size,
                    refill_rate=self.config.requests_per_minute / 60.0
                )
            
            bucket = self._buckets[key]
            allowed = bucket.consume(cost)
            
            if not allowed:
                # Bloquear temporalmente si se excede
                self.block(identifier, 1)
                return False, 0, int(time.time()) + 60
            
            remaining = int(bucket.get_remaining())
            reset_time = int(time.time()) + self.config.window_seconds
            
            return True, remaining, reset_time
    
    def check_sliding_window(self, identifier: str) -> tuple:
        """
        Verifica rate limit usando ventana deslizante
        
        Returns:
            Tuple (allowed: bool, current_count: int, limit: int)
        """
        with self._lock:
            if self.is_blocked(identifier):
                return False, 0, self.config.requests_per_minute
            
            current_minute = int(time.time()) // 60
            counts = self._request_counts[identifier]
            
            # Contar requests en la ultima hora
            total = sum(counts[m] for m in list(counts.keys()) if current_minute - m < 60)
            
            if total >= self.config.requests_per_hour:
                self.block(identifier)
                return False, total, self.config.requests_per_hour
            
            # Incrementar contador
            counts[current_minute] += 1
            
            return True, total + 1, self.config.requests_per_hour
    
    def _cleanup_loop(self):
        """Limpia datos antiguos periodicamente"""
        while True:
            time.sleep(300)  # Cada 5 minutos
            self._cleanup()
    
    def _cleanup(self):
        """Limpia contadores y bloqueos expirados"""
        with self._lock:
            current_minute = int(time.time()) // 60
            
            # Limpiar contadores antiguos
            for identifier in list(self._request_counts.keys()):
                counts = self._request_counts[identifier]
                for minute in list(counts.keys()):
                    if current_minute - minute > 60:
                        del counts[minute]
                if not counts:
                    del self._request_counts[identifier]
            
            # Limpiar bloqueos expirados
            for identifier in list(self._blocked.keys()):
                if datetime.now() > self._blocked[identifier]:
                    del self._blocked[identifier]
    
    def get_stats(self, identifier: str = None) -> Dict:
        """Retorna estadisticas de rate limiting"""
        with self._lock:
            if identifier:
                key = self._get_key(identifier)
                bucket = self._buckets.get(key)
                return {
                    "identifier": identifier,
                    "remaining_tokens": bucket.get_remaining() if bucket else 0,
                    "is_blocked": self.is_blocked(identifier)
                }
            
            return {
                "total_buckets": len(self._buckets),
                "total_blocked": len(self._blocked),
                "config": asdict(self.config)
            }


class RateLimitMiddleware:
    """
    Middleware de rate limiting para FastAPI/Flask
    """
    
    def __init__(self, limiter: RateLimiter = None, 
                 key_func: Callable = None,
                 exempt_routes: list = None):
        self.limiter = limiter or RateLimiter()
        self.key_func = key_func or self._default_key_func
        self.exempt_routes = exempt_routes or ["/health", "/metrics"]
    
    def _default_key_func(self, request) -> str:
        """Funcion por defecto para extraer identificador"""
        # Intentar obtener de header X-Forwarded-For
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        
        # Fallback a IP directa
        return request.client.host if hasattr(request, "client") else "unknown"
    
    def is_exempt(self, path: str) -> bool:
        """Verifica si una ruta esta exenta de rate limiting"""
        return any(path.startswith(route) for route in self.exempt_routes)
    
    async def __call__(self, request, call_next):
        """Middleware para ASGI (FastAPI)"""
        if self.is_exempt(request.url.path):
            return await call_next(request)
        
        identifier = self.key_func(request)
        allowed, remaining, reset_time = self.limiter.check_rate_limit(identifier)
        
        if not allowed:
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Rate limit exceeded",
                    "retry_after": reset_time - int(time.time())
                },
                headers={
                    "X-RateLimit-Limit": str(self.limiter.config.requests_per_minute),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset_time),
                    "Retry-After": str(reset_time - int(time.time()))
                }
            )
        
        response = await call_next(request)
        
        # Agregar headers de rate limit
        response.headers["X-RateLimit-Limit"] = str(self.limiter.config.requests_per_minute)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset_time)
        
        return response


# Decorador para rate limiting
def rate_limit(requests_per_minute: int = 60, 
               key_func: Callable = None):
    """
    Decorador para aplicar rate limiting a funciones
    
    Args:
        requests_per_minute: Limite de requests por minuto
        key_func: Funcion para extraer identificador de request
    """
    limiter = RateLimiter(RateLimitConfig(requests_per_minute=requests_per_minute))
    
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Extraer request de args
            request = args[0] if args else None
            identifier = key_func(request) if key_func else "default"
            
            allowed, remaining, reset_time = limiter.check_rate_limit(identifier)
            
            if not allowed:
                raise RateLimitExceeded("Rate limit exceeded")
            
            return func(*args, **kwargs)
        return wrapper
    return decorator


class RateLimitExceeded(Exception):
    """Excepcion para rate limit excedido"""
    pass


# Instancia global
_rate_limiter = None

def get_rate_limiter() -> RateLimiter:
    """Retorna instancia singleton del RateLimiter"""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter


if __name__ == "__main__":
    # Demo de rate limiting
    print("AI_VAULT Rate Limiter Demo")
    print("=" * 50)
    
    limiter = RateLimiter(RateLimitConfig(
        requests_per_minute=10,
        burst_size=5
    ))
    
    # Simular requests
    client_id = "client_123"
    
    print(f"\nSimulando 15 requests rapidos...")
    for i in range(15):
        allowed, remaining, reset = limiter.check_rate_limit(client_id)
        status = "✓ ALLOWED" if allowed else "✗ BLOCKED"
        print(f"Request {i+1}: {status} (remaining: {remaining})")
        time.sleep(0.1)
    
    print(f"\nEstadisticas: {limiter.get_stats(client_id)}")
