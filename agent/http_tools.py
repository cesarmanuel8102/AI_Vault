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
        url: URL completa del servicio (ej: http://127.0.0.1:8070)
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
        port: Puerto a verificar (ej: 8070)
    
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
    Diagnóstico completo del dashboard en puerto 8070.
    Combina check_port + check_http + búsqueda de procesos.
    """
    import os
    
    results = {
        "service": "Dashboard (puerto 8070)",
        "checks": []
    }
    
    # Check 1: Puerto abierto?
    port_check = await check_port_status("127.0.0.1", 8070)
    results["checks"].append({
        "name": "Verificar puerto 8070",
        "result": port_check
    })
    
    if port_check["is_open"]:
        # Check 2: Responde HTTP?
        http_check = await check_http_service("http://127.0.0.1:8070")
        results["checks"].append({
            "name": "Verificar HTTP endpoint",
            "result": http_check
        })
    
    # Verificar si existe el archivo del servidor
    dashboard_file = r"C:\AI_VAULT\tmp_agent\dashboard_professional\dashboard_server.py"
    results["checks"].append({
        "name": "Verificar archivo servidor",
        "result": {
            "exists": os.path.exists(dashboard_file),
            "path": dashboard_file
        }
    })
    
    # Resumen
    port_open = results["checks"][0]["result"]["is_open"]
    file_exists = results["checks"][-1]["result"]["exists"]
    
    if port_open:
        results["summary"] = "✅ Dashboard está corriendo en puerto 8070"
        results["recommendation"] = "El servicio está activo. Si no puedes acceder desde el navegador, verifica el firewall."
    elif file_exists:
        results["summary"] = "⚠️ Dashboard NO está corriendo pero el archivo existe"
        results["recommendation"] = "Inicia el servidor: cd C:\AI_VAULT\tmp_agent\dashboard_professional && python dashboard_server.py"
    else:
        results["summary"] = "❌ Dashboard no existe en la ubicación esperada"
        results["recommendation"] = "El archivo dashboard_server.py no se encuentra. Verifica la instalación."
    
    return results
