"""
Brain Chat V9 — Tool para diagnosticar servicios HTTP (dashboard, APIs, etc.)
Añadir a brain_v9/agent/tools.py
"""
import logging
from typing import Dict, Optional
from aiohttp import ClientSession, ClientTimeout

log = logging.getLogger("agent.tools.http")

async def check_http_service(url: str, timeout: int = 5) -> Dict:
    """
    Verifica si un servicio HTTP está respondiendo.
    Útil para diagnosticar dashboards, APIs, bridges, etc.
    
    Args:
        url: URL completa del servicio (ej: http://127.0.0.1:8090)
        timeout: Timeout en segundos (default: 5)
    
    Returns:
        Dict con status, código HTTP, tiempo de respuesta, y error si aplica
    """
    import time
    
    try:
        t0 = time.time()
        async with ClientSession(timeout=ClientTimeout(total=timeout)) as session:
            async with session.get(url) as response:
                elapsed_ms = (time.time() - t0) * 1000
                
                return {
                    "success": True,
                    "url": url,
                    "status_code": response.status,
                    "is_healthy": response.status < 400,
                    "response_time_ms": round(elapsed_ms, 2),
                    "headers": dict(response.headers),
                    "error": None
                }
    except Exception as e:
        return {
            "success": False,
            "url": url,
            "status_code": None,
            "is_healthy": False,
            "response_time_ms": None,
            "headers": {},
            "error": str(e),
            "error_type": type(e).__name__
        }


async def check_port_status(host: str, port: int) -> Dict:
    """
    Verifica si un puerto está abierto y escuchando conexiones.
    Útil para diagnosticar si un servicio está corriendo.
    
    Args:
        host: Hostname o IP (ej: 127.0.0.1)
        port: Puerto a verificar (ej: 8090)
    
    Returns:
        Dict con estado del puerto y diagnóstico
    """
    import socket
    import time
    
    try:
        t0 = time.time()
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(3)
        result = sock.connect_ex((host, port))
        sock.close()
        elapsed_ms = (time.time() - t0) * 1000
        
        if result == 0:
            return {
                "success": True,
                "host": host,
                "port": port,
                "is_open": True,
                "response_time_ms": round(elapsed_ms, 2),
                "diagnosis": f"El puerto {port} está abierto y aceptando conexiones en {host}",
                "error": None
            }
        else:
            return {
                "success": True,
                "host": host,
                "port": port,
                "is_open": False,
                "response_time_ms": None,
                "diagnosis": f"El puerto {port} está cerrado en {host}. El servicio no está corriendo o está bloqueado.",
                "error": f"Código de error socket: {result}"
            }
    except Exception as e:
        return {
            "success": False,
            "host": host,
            "port": port,
            "is_open": False,
            "response_time_ms": None,
            "diagnosis": f"Error al verificar puerto {port}: {str(e)}",
            "error": str(e),
            "error_type": type(e).__name__
        }


async def diagnose_dashboard() -> Dict:
    """
    Diagnostico del dashboard — ahora integrado en Brain V9 en :8090/ui.
    Port 8070 is retired. dashboard_professional/ was removed in P5-11.
    """
    results = {
        "service": "Dashboard (integrado en Brain V9 :8090/ui)",
        "checks": []
    }

    # Check Brain V9 on port 8090
    port_check = await check_port_status("127.0.0.1", 8090)
    results["checks"].append({
        "name": "Verificar puerto 8090 (Brain V9)",
        "result": port_check
    })

    if port_check["is_open"]:
        http_check = await check_http_service("http://127.0.0.1:8090/health")
        results["checks"].append({
            "name": "Verificar HTTP /health",
            "result": http_check
        })
        results["summary"] = "Dashboard integrado en Brain V9 :8090/ui"
        results["recommendation"] = "Acceder a http://localhost:8090/ui"
    else:
        results["summary"] = "Brain V9 no esta corriendo en puerto 8090"
        results["recommendation"] = "Ejecutar emergency_start.ps1 para iniciar Brain V9"

    return results
