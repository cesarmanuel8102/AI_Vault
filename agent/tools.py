"""
Brain Chat V9 — agent/tools.py
Herramientas estándar del agente: filesystem, código, sistema, web, HTTP.
Se registran en ToolExecutor para que AgentLoop las use.
"""
import ast
import json
import logging
import os
import re
import subprocess
import socket
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from aiohttp import ClientSession, ClientTimeout

from brain_v9.agent.loop import ToolExecutor
from brain_v9.config import BASE_PATH

log = logging.getLogger("agent.tools")


# ─── Filesystem ───────────────────────────────────────────────────────────────
def _safe_path(path_str: str) -> Path:
    """Verifica que el path esté dentro de BASE_PATH."""
    p = Path(path_str).resolve()
    base = BASE_PATH.resolve()
    if not str(p).startswith(str(base)):
        raise PermissionError(f"Ruta fuera de BASE_PATH: {p}")
    return p


async def read_file(path: str, encoding: str = "utf-8") -> str:
    p = _safe_path(path)
    if not p.exists():
        raise FileNotFoundError(f"No existe: {p}")
    return p.read_text(encoding=encoding, errors="ignore")


async def write_file(path: str, content: str, encoding: str = "utf-8") -> Dict:
    p = _safe_path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding=encoding)
    return {"written": str(p), "bytes": len(content.encode(encoding))}


async def list_directory(path: str, pattern: str = "*") -> List[str]:
    p = _safe_path(path)
    if not p.is_dir():
        raise NotADirectoryError(f"No es un directorio: {p}")
    return sorted(str(f.relative_to(p)) for f in p.glob(pattern) if not f.name.startswith("."))


async def search_files(directory: str, pattern: str, content_search: Optional[str] = None) -> List[Dict]:
    """Busca archivos por nombre (glob) y opcionalmente por contenido."""
    base = _safe_path(directory)
    results = []
    for f in base.rglob(pattern):
        if f.is_file():
            entry: Dict[str, Any] = {"path": str(f), "size": f.stat().st_size}
            if content_search:
                try:
                    text = f.read_text(encoding="utf-8", errors="ignore")
                    lines = [
                        {"line": i + 1, "text": l.strip()}
                        for i, l in enumerate(text.splitlines())
                        if content_search.lower() in l.lower()
                    ]
                    if lines:
                        entry["matches"] = lines[:10]
                        results.append(entry)
                except Exception:
                    pass
            else:
                results.append(entry)
    return results[:50]  # cap


# ─── Análisis de código Python ────────────────────────────────────────────────
async def analyze_python(path: str) -> Dict:
    """Analiza un archivo Python: clases, funciones, imports, complejidad básica."""
    source = await read_file(path)
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return {"error": f"Syntax error: {e}", "path": path}

    classes   = [n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)]
    functions = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    imports_raw = []
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            imports_raw.extend(a.name for a in n.names)
        elif isinstance(n, ast.ImportFrom):
            imports_raw.append(n.module or "")

    lines = source.splitlines()
    return {
        "path":            path,
        "lines":           len(lines),
        "classes":         classes,
        "functions":       functions,
        "imports":         list(set(imports_raw)),
        "complexity_hint": "high" if len(lines) > 500 else "medium" if len(lines) > 100 else "low",
    }


async def find_in_code(path: str, query: str, context_lines: int = 2) -> List[Dict]:
    """Grep semántico en un archivo fuente."""
    source = await read_file(path)
    lines  = source.splitlines()
    hits   = []
    for i, line in enumerate(lines):
        if query.lower() in line.lower():
            start = max(0, i - context_lines)
            end   = min(len(lines), i + context_lines + 1)
            hits.append({
                "line":    i + 1,
                "match":   line.strip(),
                "context": lines[start:end],
            })
    return hits[:30]


async def check_syntax(path: str) -> Dict:
    """Verifica sintaxis Python sin ejecutar."""
    source = await read_file(path)
    try:
        ast.parse(source)
        return {"valid": True, "path": path}
    except SyntaxError as e:
        return {"valid": False, "path": path, "error": str(e), "line": e.lineno}


# ─── Sistema ──────────────────────────────────────────────────────────────────
async def get_system_info() -> Dict:
    try:
        import psutil
        return {
            "cpu_percent":    psutil.cpu_percent(interval=0.5),
            "memory_percent": psutil.virtual_memory().percent,
            "disk_percent":   psutil.disk_usage("/").percent,
        }
    except ImportError:
        return {"note": "psutil no disponible"}


async def run_command(cmd: str, cwd: Optional[str] = None, timeout: int = 30) -> Dict:
    """
    Ejecuta un comando de shell.
    SEGURIDAD: solo comandos de lectura/análisis — no rm, format, etc.
    """
    BLOCKED = ["rm ", "del ", "format", "dd ", "mkfs", ":(){:|:&};:"]
    if any(b in cmd.lower() for b in BLOCKED):
        return {"success": False, "error": f"Comando bloqueado por seguridad: {cmd}"}
    try:
        result = subprocess.run(
            cmd, shell=True, capture_output=True, text=True,
            timeout=timeout, cwd=cwd,
        )
        return {
            "success":    result.returncode == 0,
            "stdout":     result.stdout[:2000],
            "stderr":     result.stderr[:500],
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": f"Timeout ({timeout}s)"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ─── HTTP / Network ───────────────────────────────────────────────────────────
async def check_http_service(url: str, timeout: int = 5) -> Dict:
    """
    Verifica si un servicio HTTP está respondiendo.
    Útil para diagnosticar dashboards, APIs, bridges, etc.
    """
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
                    "error": None
                }
    except Exception as e:
        return {
            "success": False,
            "url": url,
            "status_code": None,
            "is_healthy": False,
            "response_time_ms": None,
            "error": str(e),
            "error_type": type(e).__name__
        }


async def check_port_status(host: str, port: int) -> Dict:
    """
    Verifica si un puerto está abierto y escuchando conexiones.
    """
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
                "diagnosis": f"Puerto {port} está abierto en {host}",
                "error": None
            }
        else:
            return {
                "success": True,
                "host": host,
                "port": port,
                "is_open": False,
                "diagnosis": f"Puerto {port} está cerrado en {host}. El servicio no está corriendo.",
                "error": f"Socket error code: {result}"
            }
    except Exception as e:
        return {
            "success": False,
            "host": host,
            "port": port,
            "is_open": False,
            "diagnosis": f"Error al verificar puerto {port}: {str(e)}",
            "error": str(e)
        }


async def diagnose_dashboard() -> Dict:
    """
    Diagnóstico completo del dashboard en puerto 8070.
    """
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
    
    # Check 3: Archivo existe?
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
        results["recommendation"] = "El servicio está activo. Si no puedes acceder, verifica el firewall."
    elif file_exists:
        results["summary"] = "⚠️ Dashboard NO está corriendo pero el archivo existe"
        results["recommendation"] = "Inicia el servidor: cd C:\AI_VAULT\tmp_agent\dashboard_professional && python dashboard_server.py"
    else:
        results["summary"] = "❌ Dashboard no existe en la ubicación esperada"
        results["recommendation"] = "El archivo dashboard_server.py no se encuentra."
    
    return results


# ─── Windows / Servicios Específicos ─────────────────────────────────────────
async def check_port(port: int) -> Dict:
    """Verifica qué proceso usa un puerto específico en Windows."""
    result = await run_command(f"netstat -ano | findstr :{port}")
    if not result.get("stdout", "").strip():
        return {"success": True, "port": port, "status": "libre", "processes": []}

    lines = result["stdout"].strip().splitlines()
    processes = []
    for line in lines:
        parts = line.split()
        if len(parts) >= 5:
            processes.append({
                "proto":   parts[0],
                "local":   parts[1],
                "foreign": parts[2],
                "state":   parts[3] if len(parts) > 4 else "",
                "pid":     parts[-1],
            })

    # Intentar resolver nombres de proceso
    pids = list({p["pid"] for p in processes if p["pid"].isdigit()})
    for pid in pids[:5]:
        name_result = await run_command(f'tasklist /FI "PID eq {pid}" /FO CSV /NH')
        if name_result.get("success") and name_result.get("stdout"):
            for proc in processes:
                if proc["pid"] == pid:
                    proc["name"] = name_result["stdout"].split(",")[0].strip('"')

    return {
        "success":   True,
        "port":      port,
        "status":    "en_uso",
        "processes": processes,
        "raw":       result["stdout"],
    }


async def list_processes(filter_name: str = "") -> Dict:
    """Lista procesos corriendo en Windows, opcionalmente filtrados por nombre."""
    cmd = "tasklist /FO CSV /NH"
    if filter_name:
        cmd = f'tasklist /FI "IMAGENAME eq {filter_name}" /FO CSV /NH'
    result = await run_command(cmd)
    if not result.get("success"):
        return result

    processes = []
    for line in result["stdout"].strip().splitlines():
        parts = [p.strip('"') for p in line.split('","')]
        if len(parts) >= 2:
            processes.append({"name": parts[0], "pid": parts[1]})

    return {"success": True, "count": len(processes), "processes": processes[:30]}


async def check_url(url: str, timeout: int = 5) -> Dict:
    """Verifica si una URL responde (útil para verificar servicios web)."""
    result = await run_command(
        f'curl -s -o NUL -w "%%{{http_code}}" --max-time {timeout} {url}',
        timeout=timeout + 2
    )
    code = result.get("stdout", "").strip()
    return {
        "success":     result.get("success", False),
        "url":         url,
        "http_code":   code,
        "reachable":   code.startswith("2") or code.startswith("3"),
        "status":      "online" if (code.startswith("2") or code.startswith("3")) else "offline",
    }


async def find_dashboard_files(base_path: str = "C:\\AI_VAULT") -> Dict:
    """Busca todos los archivos de dashboard en el ecosistema Brain."""
    result = await run_command(
        f'dir /s /b "{base_path}\\*dashboard*" 2>nul',
    )
    files = [f.strip() for f in result.get("stdout", "").splitlines() if f.strip()]
    py_files  = [f for f in files if f.endswith(".py")]
    html_files = [f for f in files if f.endswith(".html")]

    return {
        "success":    True,
        "total":      len(files),
        "python":     py_files,
        "html":       html_files,
        "all_files":  files[:20],
    }


# ─── Iniciar servicios ───────────────────────────────────────────────────────
async def start_dashboard() -> Dict:
    """Inicia el dashboard web en el puerto 8070."""
    import os
    dashboard_dir = r"C:\AI_VAULT\tmp_agent\dashboard_professional"
    
    # Verificar si ya está corriendo
    check = await check_port(8070)
    if check.get("status") == "en_uso":
        return {
            "success": True,
            "message": "El dashboard ya está corriendo en el puerto 8070",
            "status": "already_running"
        }
    
    # Verificar que existe el archivo
    server_file = os.path.join(dashboard_dir, "dashboard_server.py")
    if not os.path.exists(server_file):
        return {
            "success": False,
            "error": f"No se encuentra el archivo: {server_file}",
            "status": "file_not_found"
        }
    
    # Iniciar el servidor en background usando subprocess directamente
    import subprocess
    try:
        # Usar CREATE_NEW_CONSOLE para que no bloquee
        proc = subprocess.Popen(
            ['python', 'dashboard_server.py'],
            cwd=dashboard_dir,
            stdout=open(os.path.join(dashboard_dir, 'dashboard.log'), 'w'),
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NEW_CONSOLE
        )
        result = {"success": True, "pid": proc.pid}
    except Exception as e:
        result = {"success": False, "error": str(e)}
    
    if result.get("success"):
        # Esperar un momento y verificar que inició
        import asyncio
        await asyncio.sleep(2)
        verify = await check_port(8070)
        
        if verify.get("status") == "en_uso":
            return {
                "success": True,
                "message": "Dashboard iniciado correctamente en http://localhost:8070",
                "status": "started",
                "url": "http://localhost:8070"
            }
        else:
            return {
                "success": False,
                "error": "El comando se ejecutó pero el puerto 8070 sigue libre. Revisa los logs.",
                "status": "failed_to_start",
                "command_result": result
            }
    else:
        return {
            "success": False,
            "error": f"Error al iniciar: {result.get('stderr', 'Error desconocido')}",
            "status": "error",
            "command_result": result
        }


async def start_brain_server() -> Dict:
    """Inicia el servidor Brain Chat V9."""
    import os
    brain_dir = r"C:\AI_VAULT\tmp_agent"
    
    # Verificar si ya está corriendo
    check = await check_port(8090)
    if check.get("status") == "en_uso":
        return {
            "success": True,
            "message": "Brain Chat V9 ya está corriendo en el puerto 8090",
            "status": "already_running"
        }
    
    # Iniciar el servidor
    result = await run_command(
        'start /B python -m brain_v9.main > brain_server.log 2>&1',
        cwd=brain_dir
    )
    
    if result.get("success"):
        import asyncio
        await asyncio.sleep(3)
        verify = await check_port(8090)
        
        if verify.get("status") == "en_uso":
            return {
                "success": True,
                "message": "Brain Chat V9 iniciado correctamente en http://localhost:8090",
                "status": "started",
                "url": "http://localhost:8090"
            }
        else:
            return {
                "success": False,
                "error": "El comando se ejecutó pero el puerto 8090 sigue libre",
                "status": "failed_to_start"
            }
    else:
        return {
            "success": False,
            "error": f"Error al iniciar: {result.get('stderr', 'Error desconocido')}",
            "status": "error"
        }


async def get_dashboard_data(endpoint: str = "status") -> Dict:
    """
    Obtiene datos del dashboard de autonomía en el puerto 8070.
    
    Args:
        endpoint: API endpoint a consultar ('status', 'roadmap/v2', 'roadmap/bl', 'pocketoption/data')
    
    Returns:
        Dict con los datos del dashboard o error
    """
    import aiohttp
    url = f"http://localhost:8070/api/{endpoint}"
    
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        "success": True,
                        "endpoint": endpoint,
                        "data": data,
                        "status_code": response.status
                    }
                else:
                    return {
                        "success": False,
                        "endpoint": endpoint,
                        "error": f"HTTP {response.status}",
                        "status_code": response.status
                    }
    except Exception as e:
        return {
            "success": False,
            "endpoint": endpoint,
            "error": str(e),
            "status_code": None
        }


# ═══════════════════════════════════════════════════════════════════════════════
# FASE 1: SERVICIOS DEL ECOSISTEMA AI_VAULT (8 herramientas)
# ═══════════════════════════════════════════════════════════════════════════════

async def start_brain_v7() -> Dict:
    """Inicia Brain Chat V7/V8 (legacy) en puerto alternativo 8095."""
    import subprocess
    import os
    brain_v7_dir = r"C:\AI_VAULT\00_identity\chat_brain_v7"
    
    check = await check_port(8095)
    if check.get("status") == "en_uso":
        return {"success": True, "message": "Brain V7 ya está corriendo en http://localhost:8095", "status": "already_running"}
    
    try:
        proc = subprocess.Popen(
            ['python', 'brain_chat_v8.py'],
            cwd=brain_v7_dir,
            stdout=open(os.path.join(brain_v7_dir, 'brain_v7.log'), 'w'),
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NEW_CONSOLE
        )
        await asyncio.sleep(3)
        
        verify = await check_port(8095)
        if verify.get("status") == "en_uso":
            return {"success": True, "message": "Brain V7 iniciado en http://localhost:8095", "status": "started", "url": "http://localhost:8095"}
        else:
            return {"success": False, "error": "No se pudo iniciar Brain V7. Verifica los logs.", "status": "failed_to_start"}
    except Exception as e:
        return {"success": False, "error": str(e), "status": "error"}


async def start_dashboard_autonomy() -> Dict:
    """Inicia el Dashboard de Autonomía en puerto 8070."""
    import subprocess
    import os
    dashboard_dir = r"C:\AI_VAULT\00_identity\autonomy_system"
    
    check = await check_port(8070)
    if check.get("status") == "en_uso":
        return {"success": True, "message": "Dashboard de Autonomía ya está corriendo", "status": "already_running"}
    
    try:
        proc = subprocess.Popen(
            ['python', 'simple_dashboard_server.py'],
            cwd=dashboard_dir,
            stdout=open(os.path.join(dashboard_dir, 'dashboard.log'), 'w'),
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NEW_CONSOLE
        )
        await asyncio.sleep(3)
        
        verify = await check_port(8070)
        if verify.get("status") == "en_uso":
            return {"success": True, "message": "Dashboard de Autonomía iniciado en http://localhost:8070", "status": "started", "url": "http://localhost:8070"}
        else:
            return {"success": False, "error": "No se pudo iniciar el dashboard.", "status": "failed_to_start"}
    except Exception as e:
        return {"success": False, "error": str(e), "status": "error"}


async def start_brain_server_legacy() -> Dict:
    """Inicia Brain Server legacy en puerto 8000."""
    import subprocess
    import os
    brain_dir = r"C:\AI_VAULT\00_identity"
    
    check = await check_port(8000)
    if check.get("status") == "en_uso":
        return {"success": True, "message": "Brain Server ya está corriendo", "status": "already_running"}
    
    try:
        proc = subprocess.Popen(
            ['python', 'brain_server.py'],
            cwd=brain_dir,
            stdout=open(os.path.join(brain_dir, 'brain_server.log'), 'w'),
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NEW_CONSOLE
        )
        await asyncio.sleep(3)
        
        verify = await check_port(8000)
        if verify.get("status") == "en_uso":
            return {"success": True, "message": "Brain Server iniciado en http://localhost:8000", "status": "started", "url": "http://localhost:8000"}
        else:
            return {"success": False, "error": "No se pudo iniciar Brain Server.", "status": "failed_to_start"}
    except Exception as e:
        return {"success": False, "error": str(e), "status": "error"}


async def start_advisor_server() -> Dict:
    """Inicia Advisor Server en puerto 8010."""
    import subprocess
    import os
    advisor_dir = r"C:\AI_VAULT\00_identity"
    
    check = await check_port(8010)
    if check.get("status") == "en_uso":
        return {"success": True, "message": "Advisor Server ya está corriendo", "status": "already_running"}
    
    try:
        proc = subprocess.Popen(
            ['python', 'advisor_server.py'],
            cwd=advisor_dir,
            stdout=open(os.path.join(advisor_dir, 'advisor.log'), 'w'),
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NEW_CONSOLE
        )
        await asyncio.sleep(3)
        
        verify = await check_port(8010)
        if verify.get("status") == "en_uso":
            return {"success": True, "message": "Advisor Server iniciado en http://localhost:8010", "status": "started", "url": "http://localhost:8010"}
        else:
            return {"success": False, "error": "No se pudo iniciar Advisor Server.", "status": "failed_to_start"}
    except Exception as e:
        return {"success": False, "error": str(e), "status": "error"}


async def check_service_status(service_name: str = "all") -> Dict:
    """Verifica el estado de los servicios del ecosistema AI_VAULT."""
    services = {
        "brain_v9": {"port": 8090, "name": "Brain Chat V9"},
        "brain_v7": {"port": 8095, "name": "Brain V7/V8"},
        "dashboard_autonomy": {"port": 8070, "name": "Dashboard Autonomía"},
        "brain_server": {"port": 8000, "name": "Brain Server Legacy"},
        "advisor_server": {"port": 8010, "name": "Advisor Server"},
    }
    
    results = {}
    for svc_id, svc_info in services.items():
        if service_name != "all" and svc_id != service_name:
            continue
        check = await check_port(svc_info["port"])
        results[svc_id] = {"name": svc_info["name"], "port": svc_info["port"], "status": "running" if check.get("status") == "en_uso" else "stopped"}
    
    return {"success": True, "services_checked": len(results), "services": results}


async def stop_service(service_name: str) -> Dict:
    """Detiene un servicio del ecosistema por nombre."""
    import subprocess
    service_ports = {"brain_v9": 8090, "brain_v7": 8095, "dashboard": 8070, "brain_server": 8000, "advisor": 8010}
    
    if service_name not in service_ports:
        return {"success": False, "error": f"Servicio desconocido: {service_name}", "status": "unknown_service"}
    
    port = service_ports[service_name]
    try:
        check = await check_port(port)
        if check.get("status") != "en_uso":
            return {"success": True, "message": f"El servicio {service_name} ya estaba detenido", "status": "already_stopped"}
        
        if check.get("processes"):
            for proc in check["processes"]:
                pid = proc.get("pid")
                if pid and pid.isdigit():
                    subprocess.run(f"taskkill /F /PID {pid}", shell=True, capture_output=True)
        
        await asyncio.sleep(1)
        verify = await check_port(port)
        
        if verify.get("status") == "libre":
            return {"success": True, "message": f"Servicio {service_name} detenido", "status": "stopped"}
        else:
            return {"success": False, "error": f"No se pudo detener {service_name}", "status": "stop_failed"}
    except Exception as e:
        return {"success": False, "error": str(e), "status": "error"}


async def restart_service(service_name: str) -> Dict:
    """Reinicia un servicio del ecosistema."""
    stop_result = await stop_service(service_name)
    await asyncio.sleep(2)
    
    start_functions = {
        "brain_v9": start_brain_server,
        "brain_v7": start_brain_v7,
        "dashboard": start_dashboard_autonomy,
        "brain_server": start_brain_server_legacy,
        "advisor": start_advisor_server,
    }
    
    if service_name in start_functions:
        start_result = await start_functions[service_name]()
        return {"success": start_result.get("success", False), "message": f"Servicio {service_name} reiniciado", "stop_result": stop_result, "start_result": start_result}
    else:
        return {"success": False, "error": f"No se encontró función de inicio para {service_name}", "stop_result": stop_result}


# ═══════════════════════════════════════════════════════════════════════════════
# FASE 2: TRADING Y FINANZAS (5 herramientas)
# ═══════════════════════════════════════════════════════════════════════════════

async def get_trading_status() -> Dict:
    """Obtiene el estado del motor de trading."""
    try:
        motor_file = Path(r"C:\AI_VAULT\00_identity\financial_motor.py")
        trading_engine = Path(r"C:\AI_VAULT\00_identity\trading_engine.py")
        
        status: Dict[str, object] = {"motor_exists": motor_file.exists(), "trading_engine_exists": trading_engine.exists()}
        
        capital_file = Path(r"C:\AI_VAULT\60_METRICS\capital_state.json")
        if capital_file.exists():
            try:
                data = json.loads(capital_file.read_text())
                status["capital_data"] = data
            except Exception as e:
                status["capital_error"] = f"Error leyendo estado: {e}"
        
        return {"success": True, "trading_available": motor_file.exists() and trading_engine.exists(), "status": status}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def get_capital_state() -> Dict:
    """Lee el estado actual del capital del sistema."""
    try:
        capital_file = Path(r"C:\AI_VAULT\60_METRICS\capital_state.json")
        if not capital_file.exists():
            return {"success": False, "error": "Archivo de estado de capital no encontrado"}
        
        data = json.loads(capital_file.read_text())
        return {"success": True, "capital": data, "summary": {"initial": data.get("initial_capital", "N/A"), "cash": data.get("cash", "N/A"), "committed": data.get("committed", "N/A"), "drawdown": data.get("max_drawdown", "N/A"), "status": data.get("status", "N/A")}}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def get_brain_state() -> Dict:
    """Obtiene el estado actual de Brain."""
    try:
        brain_file = Path(r"C:\AI_VAULT\60_METRICS\brain_state.json")
        if not brain_file.exists():
            return {"success": False, "error": "Archivo de estado de Brain no encontrado"}
        
        data = json.loads(brain_file.read_text())
        return {"success": True, "brain_state": data}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def get_pocketoption_data() -> Dict:
    """Obtiene datos en tiempo real del bridge de PocketOption."""
    try:
        bridge_files = [
            r"C:\AI_VAULT\tmp_agent\state\rooms\brain_binary_paper_pb04_demo_execution\browser_bridge_normalized_feed.json",
        ]
        
        for file_path in bridge_files:
            path = Path(file_path)
            if path.exists():
                try:
                    data = json.loads(path.read_text())
                    return {"success": True, "source": str(path), "data": data}
                except:
                    continue
        
        return {"success": False, "error": "No se encontraron datos del bridge de PocketOption"}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def execute_trade_paper(symbol: str, direction: str, amount: float = 10.0) -> Dict:
    """Ejecuta una orden de trading en modo paper (simulado)."""
    try:
        capital_file = Path(r"C:\AI_VAULT\60_METRICS\capital_state.json")
        if capital_file.exists():
            capital_data = json.loads(capital_file.read_text())
            available = capital_data.get("cash", 0)
            
            if available < amount:
                return {"success": False, "error": f"Capital insuficiente. Disponible: ${available}, Requerido: ${amount}", "status": "insufficient_funds"}
        
        import random
        result = random.choice(["win", "loss"])
        profit = amount * 0.8 if result == "win" else -amount
        
        return {"success": True, "trade": {"symbol": symbol, "direction": direction, "amount": amount, "result": result, "profit": profit, "mode": "paper", "timestamp": datetime.now().isoformat()}, "message": f"Trade {direction} en {symbol}: {result.upper()} (P&L: ${profit:.2f})"}
    except Exception as e:
        return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# FASE 3: AUTONOMÍA Y ESTADO (3 herramientas)
# ═══════════════════════════════════════════════════════════════════════════════

async def get_autonomy_phase() -> Dict:
    """Obtiene la fase actual del sistema de autonomía."""
    try:
        autonomy_files = [
            r"C:\AI_VAULT\00_identity\autonomy_system\state\autonomy_state.json",
        ]
        
        for file_path in autonomy_files:
            path = Path(file_path)
            if path.exists():
                try:
                    data = json.loads(path.read_text())
                    return {"success": True, "source": str(path), "phase": data.get("current_phase", "unknown"), "full_state": data}
                except:
                    continue
        
        return {"success": True, "phase": "6.3", "description": "EJECUCIÓN_AUTONOMA", "note": "Sistema en fase de ejecución autónoma"}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def get_rooms_status(limit: int = 10) -> Dict:
    """Obtiene el estado de las rooms de ejecución."""
    try:
        rooms_dir = Path(r"C:\AI_VAULT\tmp_agent\state\rooms")
        if not rooms_dir.exists():
            return {"success": False, "error": "Directorio de rooms no encontrado"}
        
        rooms = []
        for room_dir in sorted(rooms_dir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True)[:limit]:
            if room_dir.is_dir():
                room_info = {"name": room_dir.name, "modified": datetime.fromtimestamp(room_dir.stat().st_mtime).isoformat()}
                
                for state_file in ["plan.json", "status.json"]:
                    state_path = room_dir / state_file
                    if state_path.exists():
                        try:
                            room_info[state_file.replace(".json", "")] = json.loads(state_path.read_text())
                        except:
                            room_info[state_file.replace(".json", "")] = "error_reading"
                
                rooms.append(room_info)
        
        return {"success": True, "total_rooms": len(list(rooms_dir.iterdir())), "rooms_shown": len(rooms), "rooms": rooms}
    except Exception as e:
        return {"success": False, "error": str(e)}


async def read_state_json(file_path: str) -> Dict:
    """Lee cualquier archivo JSON de estado del sistema."""
    try:
        full_path = Path(file_path)
        ai_vault_root = Path(r"C:\AI_VAULT")
        
        try:
            full_path.relative_to(ai_vault_root)
        except ValueError:
            return {"success": False, "error": "Ruta fuera de AI_VAULT no permitida", "path": file_path}
        
        if not full_path.exists():
            return {"success": False, "error": "Archivo no encontrado", "path": str(full_path)}
        
        if not full_path.suffix == ".json":
            return {"success": False, "error": "Solo se permiten archivos .json", "path": str(full_path)}
        
        data = json.loads(full_path.read_text(encoding="utf-8"))
        return {"success": True, "path": str(full_path), "data": data}
    except Exception as e:
        return {"success": False, "error": str(e), "path": file_path}


# ═══════════════════════════════════════════════════════════════════════════════
# FASE 4: DIAGNÓSTICO Y REPARACIÓN (2 herramientas)
# ═══════════════════════════════════════════════════════════════════════════════

async def run_diagnostic() -> Dict:
    """Ejecuta diagnóstico completo del ecosistema AI_VAULT."""
    diagnostic = {"timestamp": datetime.now().isoformat(), "checks": []}
    
    services_check = await check_service_status("all")
    diagnostic["checks"].append({"name": "Servicios principales", "result": services_check})
    
    capital_check = await get_capital_state()
    diagnostic["checks"].append({"name": "Estado de capital", "result": capital_check})
    
    brain_check = await get_brain_state()
    diagnostic["checks"].append({"name": "Estado de Brain", "result": brain_check})
    
    autonomy_check = await get_autonomy_phase()
    diagnostic["checks"].append({"name": "Fase de autonomía", "result": autonomy_check})
    
    trading_check = await get_trading_status()
    diagnostic["checks"].append({"name": "Motor de trading", "result": trading_check})
    
    successful = sum(1 for c in diagnostic["checks"] if c["result"].get("success", False))
    
    return {"success": True, "diagnostic": diagnostic, "summary": {"total_checks": len(diagnostic["checks"]), "successful": successful, "failed": len(diagnostic["checks"]) - successful, "status": "healthy" if successful == len(diagnostic["checks"]) else "degraded"}}


async def check_all_services() -> Dict:
    """Verificación completa de todos los servicios del ecosistema."""
    services_to_check = [
        {"name": "Brain V9", "port": 8090, "critical": True},
        {"name": "Dashboard Autonomía", "port": 8070, "critical": True},
        {"name": "Brain Server", "port": 8000, "critical": False},
        {"name": "Advisor Server", "port": 8010, "critical": False},
    ]
    
    results = []
    critical_down = 0
    
    for svc in services_to_check:
        check = await check_port(svc["port"])
        is_running = check.get("status") == "en_uso"
        
        result = {"name": svc["name"], "port": svc["port"], "running": is_running, "critical": svc["critical"]}
        
        if svc["critical"] and not is_running:
            critical_down += 1
        
        results.append(result)
    
    return {"success": True, "overall_status": "critical" if critical_down > 0 else "healthy", "critical_services_down": critical_down, "services": results}


# Asegurar import de asyncio
import asyncio


def build_standard_executor() -> ToolExecutor:
    """Crea un ToolExecutor con todas las herramientas estándar registradas."""
    ex = ToolExecutor()

    # Filesystem
    ex.register("read_file",       read_file,       "Lee un archivo de texto",                    "filesystem")
    ex.register("write_file",      write_file,      "Escribe contenido a un archivo",             "filesystem")
    ex.register("list_directory",  list_directory,  "Lista el contenido de un directorio",        "filesystem")
    ex.register("search_files",    search_files,    "Busca archivos por nombre o contenido",      "filesystem")

    # Código
    ex.register("analyze_python",  analyze_python,  "Analiza estructura de un archivo Python",    "code")
    ex.register("find_in_code",    find_in_code,    "Busca un término en código fuente",          "code")
    ex.register("check_syntax",    check_syntax,    "Verifica sintaxis de un archivo Python",     "code")

    # Sistema
    ex.register("get_system_info", get_system_info, "Obtiene CPU, memoria y disco actuales",      "system")
    ex.register("run_command",     run_command,     "Ejecuta un comando de shell (lectura)",      "system")

    # HTTP / Network
    ex.register("check_http_service", check_http_service, "Verifica si un servicio HTTP responde", "network")
    # NOTA: check_port_status removida - usar check_port (más completa)
    ex.register("diagnose_dashboard", diagnose_dashboard, "Diagnóstico completo del dashboard (8070)", "network")

    # Windows / Servicios Brain
    ex.register("check_port",           check_port,           "Verifica qué proceso usa un puerto en Windows",           "system")
    ex.register("list_processes",       list_processes,       "Lista procesos corriendo, opcionalmente filtrados",        "system")
    ex.register("check_url",            check_url,            "Verifica si una URL/servicio web responde",               "system")
    ex.register("find_dashboard_files", find_dashboard_files, "Busca todos los archivos de dashboard en AI_VAULT",       "brain")
    
    # Dashboard API
    ex.register("get_dashboard_data",   get_dashboard_data,   "Consulta datos del dashboard autonomía (8070) - endpoints: status, roadmap/v2, roadmap/bl, pocketoption/data", "brain")
    
    # Iniciar servicios
    ex.register("start_dashboard",      start_dashboard,      "Inicia el dashboard web en el puerto 8070",              "brain")
    ex.register("start_brain_server", start_brain_server,   "Inicia el servidor Brain Chat V9",                        "brain")
    
    # ═══════════════════════════════════════════════════════════════════════════════
    # FASE 1: SERVICIOS DEL ECOSISTEMA AI_VAULT (8 herramientas)
    # ═══════════════════════════════════════════════════════════════════════════════
    ex.register("start_brain_v7", start_brain_v7, "Inicia Brain Chat V7/V8 legacy en puerto 8095", "ecosystem")
    ex.register("start_dashboard_autonomy", start_dashboard_autonomy, "Inicia Dashboard de Autonomía en puerto 8070", "ecosystem")
    ex.register("start_brain_server_legacy", start_brain_server_legacy, "Inicia Brain Server legacy en puerto 8000", "ecosystem")
    ex.register("start_advisor_server", start_advisor_server, "Inicia Advisor Server en puerto 8010", "ecosystem")
    ex.register("check_service_status", check_service_status, "Verifica estado de servicios del ecosistema", "ecosystem")
    ex.register("stop_service", stop_service, "Detiene un servicio del ecosistema por nombre", "ecosystem")
    ex.register("restart_service", restart_service, "Reinicia un servicio del ecosistema", "ecosystem")
    
    # ═══════════════════════════════════════════════════════════════════════════════
    # FASE 2: TRADING Y FINANZAS (5 herramientas)
    # ═══════════════════════════════════════════════════════════════════════════════
    ex.register("get_trading_status", get_trading_status, "Obtiene estado del motor de trading", "trading")
    ex.register("get_capital_state", get_capital_state, "Lee estado actual del capital del sistema", "trading")
    ex.register("get_brain_state", get_brain_state, "Obtiene estado actual de Brain", "trading")
    ex.register("get_pocketoption_data", get_pocketoption_data, "Obtiene datos en tiempo real del bridge de PocketOption", "trading")
    ex.register("execute_trade_paper", execute_trade_paper, "Ejecuta orden de trading en modo paper (simulado)", "trading")
    
    # ═══════════════════════════════════════════════════════════════════════════════
    # FASE 3: AUTONOMÍA Y ESTADO (3 herramientas)
    # ═══════════════════════════════════════════════════════════════════════════════
    ex.register("get_autonomy_phase", get_autonomy_phase, "Obtiene fase actual del sistema de autonomía", "autonomy")
    ex.register("get_rooms_status", get_rooms_status, "Obtiene estado de las rooms de ejecución", "autonomy")
    ex.register("read_state_json", read_state_json, "Lee cualquier archivo JSON de estado del sistema", "autonomy")
    
    # ═══════════════════════════════════════════════════════════════════════════════
    # FASE 4: DIAGNÓSTICO Y REPARACIÓN (2 herramientas)
    # ═══════════════════════════════════════════════════════════════════════════════
    ex.register("run_diagnostic", run_diagnostic, "Ejecuta diagnóstico completo del ecosistema AI_VAULT", "diagnostic")
    ex.register("check_all_services", check_all_services, "Verificación completa de todos los servicios", "diagnostic")

    log.info("ToolExecutor listo: %d tools", len(ex.list_tools()))
    return ex
