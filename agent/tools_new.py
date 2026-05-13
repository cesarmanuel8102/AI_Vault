
# ═══════════════════════════════════════════════════════════════════════════════
# FASE 1: SERVICIOS DEL ECOSISTEMA AI_VAULT (8 herramientas)
# ═══════════════════════════════════════════════════════════════════════════════

async def start_brain_v7() -> Dict:
    """Inicia Brain Chat V7/V8 (legacy) en puerto alternativo 8095."""
    import subprocess
    import os
    brain_v7_dir = r"C:\AI_VAULT\00_identity\chat_brain_v7"
    
    # Verificar si ya está corriendo
    check = await check_port(8095)
    if check.get("status") == "en_uso":
        return {
            "success": True,
            "message": "Brain V7 ya está corriendo en http://localhost:8095",
            "status": "already_running"
        }
    
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
            return {
                "success": True,
                "message": "Brain V7 iniciado en http://localhost:8095",
                "status": "started",
                "url": "http://localhost:8095"
            }
        else:
            return {
                "success": False,
                "error": "No se pudo iniciar Brain V7. Verifica los logs.",
                "status": "failed_to_start"
            }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "status": "error"
        }


async def start_dashboard_autonomy() -> Dict:
    """Inicia el Dashboard de Autonomía en puerto 8070."""
    import subprocess
    import os
    dashboard_dir = r"C:\AI_VAULT\00_identity\autonomy_system"
    
    check = await check_port(8070)
    if check.get("status") == "en_uso":
        return {
            "success": True,
            "message": "Dashboard de Autonomía ya está corriendo en http://localhost:8070",
            "status": "already_running"
        }
    
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
            return {
                "success": True,
                "message": "Dashboard de Autonomía iniciado en http://localhost:8070",
                "status": "started",
                "url": "http://localhost:8070"
            }
        else:
            return {
                "success": False,
                "error": "No se pudo iniciar el dashboard.",
                "status": "failed_to_start"
            }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "status": "error"
        }


async def start_brain_server_legacy() -> Dict:
    """Inicia Brain Server legacy en puerto 8000."""
    import subprocess
    import os
    brain_dir = r"C:\AI_VAULT\00_identity"
    
    check = await check_port(8000)
    if check.get("status") == "en_uso":
        return {
            "success": True,
            "message": "Brain Server ya está corriendo en http://localhost:8000",
            "status": "already_running"
        }
    
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
            return {
                "success": True,
                "message": "Brain Server iniciado en http://localhost:8000",
                "status": "started",
                "url": "http://localhost:8000"
            }
        else:
            return {
                "success": False,
                "error": "No se pudo iniciar Brain Server.",
                "status": "failed_to_start"
            }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "status": "error"
        }


async def start_advisor_server() -> Dict:
    """Inicia Advisor Server en puerto 8010."""
    import subprocess
    import os
    advisor_dir = r"C:\AI_VAULT\00_identity"
    
    check = await check_port(8010)
    if check.get("status") == "en_uso":
        return {
            "success": True,
            "message": "Advisor Server ya está corriendo en http://localhost:8010",
            "status": "already_running"
        }
    
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
            return {
                "success": True,
                "message": "Advisor Server iniciado en http://localhost:8010",
                "status": "started",
                "url": "http://localhost:8010"
            }
        else:
            return {
                "success": False,
                "error": "No se pudo iniciar Advisor Server.",
                "status": "failed_to_start"
            }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "status": "error"
        }


async def start_pocketoption_bridge() -> Dict:
    """Inicia el bridge de PocketOption."""
    import subprocess
    import os
    import time
    bridge_dir = r"C:\AI_VAULT\tmp_agent\brain_v9\trading"
    bridge_script = os.path.join(bridge_dir, "pocketoption_bridge_server.py")

    if not os.path.exists(bridge_script):
        return {
            "success": False,
            "error": f"No se encuentra {bridge_script}",
            "status": "file_not_found"
        }

    # Verificar si ya está corriendo por puerto
    check = await check_port(8765)
    if check.get("status") == "en_uso":
        return {
            "success": True,
            "message": "PocketOption Bridge ya está corriendo",
            "status": "already_running"
        }

    try:
        proc = subprocess.Popen(
            ['python', 'pocketoption_bridge_server.py'],
            cwd=bridge_dir,
            stdout=open(os.path.join(bridge_dir, 'bridge.log'), 'a'),
            stderr=subprocess.STDOUT,
            creationflags=subprocess.CREATE_NEW_CONSOLE
        )

        await asyncio.sleep(4)

        verify = await check_port(8765)
        if verify.get("status") == "en_uso":
            return {
                "success": True,
                "message": "PocketOption Bridge iniciado",
                "status": "started",
                "pid": proc.pid
            }
        else:
            return {
                "success": False,
                "error": "El bridge se lanzó pero no escuchó en el puerto 8765",
                "status": "failed_to_start"
            }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "status": "error"
        }


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
        results[svc_id] = {
            "name": svc_info["name"],
            "port": svc_info["port"],
            "status": "running" if check.get("status") == "en_uso" else "stopped",
            "processes": check.get("processes", [])
        }
    
    return {
        "success": True,
        "services_checked": len(results),
        "services": results
    }


async def stop_service(service_name: str) -> Dict:
    """Detiene un servicio del ecosistema por nombre."""
    import subprocess
    
    service_ports = {
        "brain_v9": 8090,
        "brain_v7": 8095,
        "dashboard": 8070,
        "brain_server": 8000,
        "advisor": 8010,
    }
    
    if service_name not in service_ports:
        return {
            "success": False,
            "error": f"Servicio desconocido: {service_name}. Servicios disponibles: {list(service_ports.keys())}",
            "status": "unknown_service"
        }
    
    port = service_ports[service_name]
    
    try:
        # Obtener PID del proceso usando el puerto
        check = await check_port(port)
        if check.get("status") != "en_uso":
            return {
                "success": True,
                "message": f"El servicio {service_name} ya estaba detenido",
                "status": "already_stopped"
            }
        
        # Matar el proceso
        if check.get("processes"):
            for proc in check["processes"]:
                pid = proc.get("pid")
                if pid and pid.isdigit():
                    subprocess.run(f"taskkill /F /PID {pid}", shell=True, capture_output=True)
        
        # Verificar que se detuvo
        await asyncio.sleep(1)
        verify = await check_port(port)
        
        if verify.get("status") == "libre":
            return {
                "success": True,
                "message": f"Servicio {service_name} detenido correctamente",
                "status": "stopped"
            }
        else:
            return {
                "success": False,
                "error": f"No se pudo detener {service_name} completamente",
                "status": "stop_failed"
            }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "status": "error"
        }


async def restart_service(service_name: str) -> Dict:
    """Reinicia un servicio del ecosistema."""
    # Detener
    stop_result = await stop_service(service_name)
    
    # Esperar
    await asyncio.sleep(2)
    
    # Iniciar según el tipo
    start_functions = {
        "brain_v9": start_brain_server,
        "brain_v7": start_brain_v7,
        "dashboard": start_dashboard_autonomy,
        "brain_server": start_brain_server_legacy,
        "advisor": start_advisor_server,
    }
    
    if service_name in start_functions:
        start_result = await start_functions[service_name]()
        return {
            "success": start_result.get("success", False),
            "stop_result": stop_result,
            "start_result": start_result,
            "message": f"Servicio {service_name} reiniciado"
        }
    else:
        return {
            "success": False,
            "error": f"No se encontró función de inicio para {service_name}",
            "stop_result": stop_result
        }


# ═══════════════════════════════════════════════════════════════════════════════
# FASE 2: TRADING Y FINANZAS (5 herramientas)
# ═══════════════════════════════════════════════════════════════════════════════

async def get_trading_status() -> Dict:
    """Obtiene el estado del motor de trading."""
    try:
        # Verificar si existe el motor financiero
        motor_file = Path(r"C:\AI_VAULT\00_identity\financial_motor.py")
        trading_engine = Path(r"C:\AI_VAULT\00_identity\trading_engine.py")
        
        status = {
            "motor_exists": motor_file.exists(),
            "trading_engine_exists": trading_engine.exists(),
        }
        
        # Verificar capital
        capital_file = Path(r"C:\AI_VAULT\60_METRICS\capital_state.json")
        if capital_file.exists():
            try:
                data = json.loads(capital_file.read_text())
                status["capital"] = data
            except:
                status["capital"] = "Error leyendo estado"
        
        return {
            "success": True,
            "trading_available": motor_file.exists() and trading_engine.exists(),
            "status": status
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


async def get_capital_state() -> Dict:
    """Lee el estado actual del capital del sistema."""
    try:
        capital_file = Path(r"C:\AI_VAULT\60_METRICS\capital_state.json")
        if not capital_file.exists():
            return {
                "success": False,
                "error": "Archivo de estado de capital no encontrado",
                "path": str(capital_file)
            }
        
        data = json.loads(capital_file.read_text())
        return {
            "success": True,
            "capital": data,
            "summary": {
                "initial": data.get("initial_capital", "N/A"),
                "cash": data.get("cash", "N/A"),
                "committed": data.get("committed", "N/A"),
                "drawdown": data.get("max_drawdown", "N/A"),
                "status": data.get("status", "N/A")
            }
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


async def get_brain_state() -> Dict:
    """Obtiene el estado actual de Brain."""
    try:
        brain_file = Path(r"C:\AI_VAULT\60_METRICS\brain_state.json")
        if not brain_file.exists():
            return {
                "success": False,
                "error": "Archivo de estado de Brain no encontrado",
                "path": str(brain_file)
            }
        
        data = json.loads(brain_file.read_text())
        return {
            "success": True,
            "brain_state": data
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


async def get_pocketoption_data() -> Dict:
    """Obtiene datos en tiempo real del bridge de PocketOption."""
    try:
        # Intentar leer datos del bridge
        bridge_files = [
            r"C:\AI_VAULT\tmp_agent\state\rooms\brain_binary_paper_pb04_demo_execution\browser_bridge_normalized_feed.json",
            r"C:\AI_VAULT\tmp_agent\pocketoption_data.json",
        ]
        
        for file_path in bridge_files:
            path = Path(file_path)
            if path.exists():
                try:
                    data = json.loads(path.read_text())
                    return {
                        "success": True,
                        "source": str(path),
                        "data": data
                    }
                except:
                    continue
        
        return {
            "success": False,
            "error": "No se encontraron datos del bridge de PocketOption",
            "checked_paths": bridge_files
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


async def execute_trade_paper(symbol: str, direction: str, amount: float = 10.0) -> Dict:
    """Ejecuta una orden de trading en modo paper (simulado)."""
    try:
        # Verificar capital disponible
        capital_file = Path(r"C:\AI_VAULT\60_METRICS\capital_state.json")
        if capital_file.exists():
            capital_data = json.loads(capital_file.read_text())
            available = capital_data.get("cash", 0)
            
            if available < amount:
                return {
                    "success": False,
                    "error": f"Capital insuficiente. Disponible: ${available}, Requerido: ${amount}",
                    "status": "insufficient_funds"
                }
        
        # Simular ejecución de trade
        import random
        result = random.choice(["win", "loss"])
        profit = amount * 0.8 if result == "win" else -amount
        
        return {
            "success": True,
            "trade": {
                "symbol": symbol,
                "direction": direction,
                "amount": amount,
                "result": result,
                "profit": profit,
                "mode": "paper",
                "timestamp": datetime.now().isoformat()
            },
            "message": f"Trade {direction} en {symbol}: {result.upper()} (P&L: ${profit:.2f})"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


# ═══════════════════════════════════════════════════════════════════════════════
# FASE 3: AUTONOMÍA Y ESTADO (3 herramientas)
# ═══════════════════════════════════════════════════════════════════════════════

async def get_autonomy_phase() -> Dict:
    """Obtiene la fase actual del sistema de autonomía."""
    try:
        # Intentar leer estado de autonomía
        autonomy_files = [
            r"C:\AI_VAULT\00_identity\autonomy_system\state\autonomy_state.json",
            r"C:\AI_VAULT\00_identity\autonomy_system\autonomy_roadmap.json",
        ]
        
        for file_path in autonomy_files:
            path = Path(file_path)
            if path.exists():
                try:
                    data = json.loads(path.read_text())
                    return {
                        "success": True,
                        "source": str(path),
                        "phase": data.get("current_phase", "unknown"),
                        "full_state": data
                    }
                except:
                    continue
        
        # Si no encuentra archivos, devolver información básica
        return {
            "success": True,
            "phase": "6.3",
            "description": "EJECUCIÓN_AUTONOMA",
            "note": "Sistema en fase de ejecución autónoma"
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


async def get_rooms_status(limit: int = 10) -> Dict:
    """Obtiene el estado de las rooms de ejecución."""
    try:
        rooms_dir = Path(r"C:\AI_VAULT\tmp_agent\state\rooms")
        if not rooms_dir.exists():
            return {
                "success": False,
                "error": "Directorio de rooms no encontrado",
                "path": str(rooms_dir)
            }
        
        # Listar rooms
        rooms = []
        for room_dir in sorted(rooms_dir.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True)[:limit]:
            if room_dir.is_dir():
                room_info = {
                    "name": room_dir.name,
                    "modified": datetime.fromtimestamp(room_dir.stat().st_mtime).isoformat()
                }
                
                # Buscar archivos de estado dentro de la room
                for state_file in ["plan.json", "status.json", "result.json"]:
                    state_path = room_dir / state_file
                    if state_path.exists():
                        try:
                            room_info[state_file.replace(".json", "")] = json.loads(state_path.read_text())
                        except:
                            room_info[state_file.replace(".json", "")] = "error_reading"
                
                rooms.append(room_info)
        
        return {
            "success": True,
            "total_rooms": len(list(rooms_dir.iterdir())),
            "rooms_shown": len(rooms),
            "rooms": rooms
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e)
        }


async def read_state_json(file_path: str) -> Dict:
    """Lee cualquier archivo JSON de estado del sistema."""
    try:
        # Validar que la ruta esté dentro de AI_VAULT
        full_path = Path(file_path)
        ai_vault_root = Path(r"C:\AI_VAULT")
        
        try:
            full_path.relative_to(ai_vault_root)
        except ValueError:
            return {
                "success": False,
                "error": "Ruta fuera de AI_VAULT no permitida",
                "path": file_path
            }
        
        if not full_path.exists():
            return {
                "success": False,
                "error": "Archivo no encontrado",
                "path": str(full_path)
            }
        
        if not full_path.suffix == ".json":
            return {
                "success": False,
                "error": "Solo se permiten archivos .json",
                "path": str(full_path)
            }
        
        data = json.loads(full_path.read_text(encoding="utf-8"))
        
        return {
            "success": True,
            "path": str(full_path),
            "data": data
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "path": file_path
        }


# ═══════════════════════════════════════════════════════════════════════════════
# FASE 4: DIAGNÓSTICO Y REPARACIÓN (2 herramientas)
# ═══════════════════════════════════════════════════════════════════════════════

async def run_diagnostic() -> Dict:
    """Ejecuta diagnóstico completo del ecosistema AI_VAULT."""
    diagnostic = {
        "timestamp": datetime.now().isoformat(),
        "checks": []
    }
    
    # Check 1: Servicios principales
    services_check = await check_service_status("all")
    diagnostic["checks"].append({
        "name": "Servicios principales",
        "result": services_check
    })
    
    # Check 2: Estado de capital
    capital_check = await get_capital_state()
    diagnostic["checks"].append({
        "name": "Estado de capital",
        "result": capital_check
    })
    
    # Check 3: Estado de Brain
    brain_check = await get_brain_state()
    diagnostic["checks"].append({
        "name": "Estado de Brain",
        "result": brain_check
    })
    
    # Check 4: Fase de autonomía
    autonomy_check = await get_autonomy_phase()
    diagnostic["checks"].append({
        "name": "Fase de autonomía",
        "result": autonomy_check
    })
    
    # Check 5: Trading
    trading_check = await get_trading_status()
    diagnostic["checks"].append({
        "name": "Motor de trading",
        "result": trading_check
    })
    
    # Contar éxitos
    successful = sum(1 for c in diagnostic["checks"] if c["result"].get("success", False))
    
    return {
        "success": True,
        "diagnostic": diagnostic,
        "summary": {
            "total_checks": len(diagnostic["checks"]),
            "successful": successful,
            "failed": len(diagnostic["checks"]) - successful,
            "status": "healthy" if successful == len(diagnostic["checks"]) else "degraded"
        }
    }


async def check_all_services() -> Dict:
    """Verificación completa de todos los servicios del ecosistema."""
    # Servicios a verificar
    services_to_check = [
        {"name": "Brain V9", "port": 8090, "critical": True},
        {"name": "Dashboard Autonomía", "port": 8070, "critical": True},
        {"name": "Brain Server", "port": 8000, "critical": False},
        {"name": "Advisor Server", "port": 8010, "critical": False},
        {"name": "Brain V7", "port": 8095, "critical": False},
    ]
    
    results = []
    critical_down = 0
    
    for svc in services_to_check:
        check = await check_port(svc["port"])
        is_running = check.get("status") == "en_uso"
        
        result = {
            "name": svc["name"],
            "port": svc["port"],
            "running": is_running,
            "critical": svc["critical"],
            "processes": check.get("processes", [])
        }
        
        if svc["critical"] and not is_running:
            critical_down += 1
        
        results.append(result)
    
    return {
        "success": True,
        "overall_status": "critical" if critical_down > 0 else "healthy",
        "critical_services_down": critical_down,
        "services": results,
        "recommendation": "Algunos servicios críticos están detenidos. Considera iniciarlos." if critical_down > 0 else "Todos los servicios críticos están funcionando correctamente."
    }


# Asegurar import de asyncio para las nuevas funciones
import asyncio

