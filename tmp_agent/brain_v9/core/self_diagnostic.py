"""
Brain Chat V9 — Sistema de Autodiagnóstico y Autocorrección
Ejecuta verificaciones periódicas y toma acciones automáticas
"""
import asyncio
import json
import logging
import shutil
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

import aiohttp

from brain_v9.config import BASE_PATH, LOG_ACCUMULATION_DIRS, LOG_RETENTION_DAYS


class SelfDiagnostic:
    """
    Sistema de autodiagnóstico para Brain V9.
    Ejecuta verificaciones automáticas y toma acciones correctivas.
    """

    CHECK_INTERVAL_SECONDS = 300  # 5 minutos
    DISK_WARNING_PERCENT = 85
    DISK_CRITICAL_PERCENT = 95
    MEMORY_WARNING_PERCENT = 80
    GPU_IDLE_THRESHOLD = 5  # % de uso GPU que indica no está trabajando

    def __init__(self):
        self.logger = logging.getLogger("SelfDiagnostic")
        self.checks_history: List[Dict] = []
        self.is_running = False
        self.last_alert_time = 0
        self.alert_cooldown_seconds = 3600  # 1 hora entre alertas iguales

    async def start(self):
        """Inicia el loop de autodiagnóstico en background."""
        self.is_running = True
        self.logger.info("SelfDiagnostic iniciado - intervalo: %ds", self.CHECK_INTERVAL_SECONDS)
        
        while self.is_running:
            try:
                await self.run_diagnostic_cycle()
                await asyncio.sleep(self.CHECK_INTERVAL_SECONDS)
            except Exception as e:
                self.logger.error("Error en ciclo de diagnóstico: %s", e)
                await asyncio.sleep(60)  # Esperar 1 minuto antes de reintentar

    def stop(self):
        """Detiene el autodiagnóstico."""
        self.is_running = False
        self.logger.info("SelfDiagnostic detenido")

    async def run_diagnostic_cycle(self) -> Dict:
        """Ejecuta un ciclo completo de diagnóstico."""
        self.logger.debug("Iniciando ciclo de diagnóstico...")
        
        checks = {
            "timestamp": datetime.now().isoformat(),
            "brain_health": await self._check_brain_health(),
            "disk_space": await self._check_disk_space(),
            "memory_usage": await self._check_memory_usage(),
            "gpu_status": await self._check_gpu_status(),
            "ollama_service": await self._check_ollama_service(),
            "dashboard": await self._check_dashboard(),
            "logs_rotation": await self._check_logs_rotation(),
        }
        
        # Calcular estado general
        critical_issues = [k for k, v in checks.items() if isinstance(v, dict) and v.get("severity") == "critical"]
        warnings = [k for k, v in checks.items() if isinstance(v, dict) and v.get("severity") == "warning"]
        
        checks["overall_status"] = "healthy" if not critical_issues else "critical" if critical_issues else "warning"
        checks["issues_count"] = {"critical": len(critical_issues), "warning": len(warnings)}
        
        # Guardar en historial
        self.checks_history.append(checks)
        if len(self.checks_history) > 1000:  # Mantener últimas 1000 verificaciones
            self.checks_history = self.checks_history[-1000:]
        
        # Ejecutar acciones correctivas automáticas
        await self._execute_auto_fixes(checks)
        
        # Log resumen
        if checks["overall_status"] != "healthy":
            self.logger.warning("Diagnóstico: %s - Críticas: %d, Advertencias: %d", 
                              checks["overall_status"], len(critical_issues), len(warnings))
        else:
            self.logger.debug("Diagnóstico: healthy")
        
        return checks

    async def _check_brain_health(self) -> Dict:
        """Verifica que Brain V9 responde correctamente."""
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                async with session.get("http://localhost:8090/health") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        return {
                            "status": "ok",
                            "sessions": data.get("sessions", 0),
                            "version": data.get("version", "unknown"),
                            "severity": None
                        }
                    else:
                        return {
                            "status": "error",
                            "http_code": resp.status,
                            "severity": "critical",
                            "action": "restart_brain"
                        }
        except Exception as e:
            return {
                "status": "unreachable",
                "error": str(e),
                "severity": "critical",
                "action": "restart_brain"
            }

    async def _check_disk_space(self) -> Dict:
        """Verifica espacio en disco."""
        try:
            disk = shutil.disk_usage("C:/")
            used_percent = (disk.used / disk.total) * 100
            free_gb = disk.free / (1024**3)
            
            if used_percent >= self.DISK_CRITICAL_PERCENT:
                return {
                    "status": "critical",
                    "used_percent": round(used_percent, 2),
                    "free_gb": round(free_gb, 2),
                    "severity": "critical",
                    "action": "emergency_cleanup"
                }
            elif used_percent >= self.DISK_WARNING_PERCENT:
                return {
                    "status": "warning",
                    "used_percent": round(used_percent, 2),
                    "free_gb": round(free_gb, 2),
                    "severity": "warning",
                    "action": "cleanup_old_logs"
                }
            else:
                return {
                    "status": "ok",
                    "used_percent": round(used_percent, 2),
                    "free_gb": round(free_gb, 2),
                    "severity": None
                }
        except Exception as e:
            return {"status": "error", "error": str(e), "severity": "warning"}

    async def _check_memory_usage(self) -> Dict:
        """Verifica uso de memoria RAM."""
        try:
            import psutil
            memory = psutil.virtual_memory()
            
            if memory.percent >= self.MEMORY_WARNING_PERCENT:
                return {
                    "status": "warning",
                    "used_percent": memory.percent,
                    "available_gb": round(memory.available / (1024**3), 2),
                    "severity": "warning",
                    "action": "clear_cache"
                }
            else:
                return {
                    "status": "ok",
                    "used_percent": memory.percent,
                    "available_gb": round(memory.available / (1024**3), 2),
                    "severity": None
                }
        except ImportError:
            return {"status": "unknown", "note": "psutil no disponible", "severity": None}
        except Exception as e:
            return {"status": "error", "error": str(e), "severity": "warning"}

    async def _check_gpu_status(self) -> Dict:
        """Verifica que GPU está siendo utilizada."""
        try:
            import subprocess
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5
            )
            
            if result.returncode == 0:
                gpu_percent = float(result.stdout.strip())
                
                if gpu_percent < self.GPU_IDLE_THRESHOLD:
                    return {
                        "status": "idle",
                        "usage_percent": gpu_percent,
                        "severity": "warning",
                        "action": "check_ollama_gpu",
                        "note": "GPU disponible pero no en uso - Ollama puede estar en CPU"
                    }
                else:
                    return {
                        "status": "active",
                        "usage_percent": gpu_percent,
                        "severity": None
                    }
            else:
                return {"status": "error", "severity": "warning", "note": "nvidia-smi falló"}
        except Exception as e:
            return {"status": "error", "error": str(e), "severity": None}

    async def _check_ollama_service(self) -> Dict:
        """Verifica que Ollama responde."""
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=3)) as session:
                async with session.get("http://localhost:11434/api/tags") as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        models = [m.get("name") for m in data.get("models", [])]
                        return {
                            "status": "ok",
                            "models_loaded": len(models),
                            "models": models[:5],  # Primeros 5
                            "severity": None
                        }
                    else:
                        return {
                            "status": "error",
                            "http_code": resp.status,
                            "severity": "critical",
                            "action": "restart_ollama"
                        }
        except Exception as e:
            return {
                "status": "unreachable",
                "error": str(e),
                "severity": "critical",
                "action": "restart_ollama"
            }

    async def _check_dashboard(self) -> Dict:
        """Verifica que dashboard integrado en Brain V9 :8090/ui responde."""
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=3)) as session:
                async with session.get("http://localhost:8090/health") as resp:
                    if resp.status == 200:
                        return {"status": "ok", "severity": None}
                    else:
                        return {
                            "status": "error",
                            "http_code": resp.status,
                            "severity": "warning",
                            "action": "restart_brain_v9"
                        }
        except Exception as e:
            return {
                "status": "unreachable",
                "error": str(e),
                "severity": "warning",
                "action": "restart_brain_v9"
            }

    async def _check_logs_rotation(self) -> Dict:
        """Verifica si logs necesitan rotación en TODOS los directorios de acumulación."""
        try:
            total_files = 0
            total_size = 0
            old_files_count = 0
            large_logs = []
            cutoff_date = datetime.now() - timedelta(days=LOG_RETENTION_DAYS)
            dir_stats = {}

            for log_dir in LOG_ACCUMULATION_DIRS:
                if not log_dir.exists():
                    continue
                dir_count = 0
                dir_size = 0
                for log_file in log_dir.glob("*.log"):
                    try:
                        size = log_file.stat().st_size
                        total_size += size
                        dir_size += size
                        total_files += 1
                        dir_count += 1

                        if size > 100 * 1024 * 1024:  # 100MB
                            large_logs.append(str(log_file))

                        mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
                        if mtime < cutoff_date:
                            old_files_count += 1
                    except Exception as exc:
                        self.logger.debug("Error reading log file %s: %s", log_file, exc)
                dir_stats[str(log_dir)] = {"files": dir_count, "size_mb": round(dir_size / (1024 * 1024), 2)}

            if old_files_count > 50 or total_size > 500 * 1024 * 1024:  # 500MB total
                return {
                    "status": "cleanup_needed",
                    "total_files": total_files,
                    "old_files_count": old_files_count,
                    "large_logs": large_logs[:10],
                    "total_size_mb": round(total_size / (1024 * 1024), 2),
                    "dir_stats": dir_stats,
                    "severity": "warning",
                    "action": "rotate_logs"
                }

            return {
                "status": "ok",
                "total_files": total_files,
                "total_size_mb": round(total_size / (1024 * 1024), 2),
                "dir_stats": dir_stats,
                "severity": None
            }
        except Exception as e:
            return {"status": "error", "error": str(e), "severity": None}

    async def _execute_auto_fixes(self, checks: Dict):
        """Ejecuta acciones correctivas automáticas."""
        fixes_executed = []
        
        for check_name, check_data in checks.items():
            if not isinstance(check_data, dict):
                continue
            
            action = check_data.get("action")
            severity = check_data.get("severity")
            
            if not action or severity not in ["critical", "warning"]:
                continue
            
            # Verificar cooldown para evitar spam
            if await self._should_skip_alert(action):
                continue
            
            try:
                if action == "cleanup_old_logs":
                    await self._cleanup_old_logs()
                    fixes_executed.append(f"{action}: cleaned old logs")
                
                elif action == "emergency_cleanup":
                    await self._emergency_cleanup()
                    fixes_executed.append(f"{action}: emergency cleanup executed")
                
                elif action == "clear_cache":
                    await self._clear_system_cache()
                    fixes_executed.append(f"{action}: cache cleared")
                
                elif action == "rotate_logs":
                    await self._rotate_logs()
                    fixes_executed.append(f"{action}: logs rotated")
                
                elif action == "check_ollama_gpu":
                    self.logger.warning("GPU idle - Ollama puede estar usando CPU en lugar de GPU")
                    # No ejecutar acción automática - requiere decisión humana
                
                # Marcar tiempo de última alerta
                self.last_alert_time = time.time()
                
            except Exception as e:
                self.logger.error("Error ejecutando fix %s: %s", action, e)
        
        if fixes_executed:
            self.logger.info("Auto-fixes ejecutados: %s", fixes_executed)

    async def _should_skip_alert(self, action: str) -> bool:
        """Verifica si debemos saltar alerta por cooldown."""
        current_time = time.time()
        return (current_time - self.last_alert_time) < self.alert_cooldown_seconds

    async def _cleanup_old_logs(self):
        """Limpia logs antiguos en TODOS los directorios de acumulación."""
        cutoff_date = datetime.now() - timedelta(days=LOG_RETENTION_DAYS)
        total_deleted = 0
        total_freed_bytes = 0

        for log_dir in LOG_ACCUMULATION_DIRS:
            if not log_dir.exists():
                continue
            for log_file in log_dir.glob("*.log"):
                try:
                    mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
                    if mtime < cutoff_date:
                        size = log_file.stat().st_size
                        log_file.unlink()
                        total_deleted += 1
                        total_freed_bytes += size
                except Exception as e:
                    self.logger.warning("Error eliminando %s: %s", log_file, e)

        freed_mb = round(total_freed_bytes / (1024 * 1024), 2)
        self.logger.info(
            "Log cleanup: eliminados %d archivos, liberados %.2f MB",
            total_deleted, freed_mb
        )
        return {"deleted": total_deleted, "freed_mb": freed_mb}

    async def _emergency_cleanup(self):
        """Limpieza de emergencia cuando disco >95%."""
        self.logger.warning("Ejecutando limpieza de emergencia...")
        
        # 1. Limpiar __pycache__
        for pycache in BASE_PATH.rglob("__pycache__"):
            try:
                shutil.rmtree(pycache)
            except Exception as exc:
                self.logger.debug("Could not remove pycache %s: %s", pycache, exc)
        
        # 2. Limpiar .pyc
        for pyc in BASE_PATH.rglob("*.pyc"):
            try:
                pyc.unlink()
            except Exception as exc:
                self.logger.debug("Could not remove pyc %s: %s", pyc, exc)
        
        # 3. Limpiar logs antiguos
        await self._cleanup_old_logs()
        
        self.logger.info("Limpieza de emergencia completada")

    async def _clear_system_cache(self):
        """Limpia caché del sistema operativo (Windows)."""
        try:
            import subprocess
            subprocess.run(["ipconfig", "/flushdns"], capture_output=True)
            self.logger.info("DNS cache limpiada")
        except Exception as e:
            self.logger.warning("Error limpiando caché: %s", e)

    async def _rotate_logs(self):
        """Rota logs grandes y limpia antiguos en TODOS los directorios de acumulación."""
        rotated = 0
        for log_dir in LOG_ACCUMULATION_DIRS:
            if not log_dir.exists():
                continue
            for log_file in log_dir.glob("*.log"):
                try:
                    size = log_file.stat().st_size
                    if size > 100 * 1024 * 1024:  # 100MB
                        backup_name = log_file.with_suffix(f".log.{datetime.now():%Y%m%d}")
                        shutil.copy2(log_file, backup_name)
                        log_file.write_text(f"# Log rotado el {datetime.now():%Y-%m-%d %H:%M:%S}\n")
                        rotated += 1
                        self.logger.info("Log rotado: %s -> %s", log_file.name, backup_name.name)
                except Exception as e:
                    self.logger.warning("Error rotando %s: %s", log_file, e)

        # After rotating large files, also clean old ones
        cleanup_result = await self._cleanup_old_logs()
        self.logger.info("Log rotation: %d rotados, cleanup: %s", rotated, cleanup_result)
        return {"rotated": rotated, "cleanup": cleanup_result}

    def get_status_report(self) -> Dict:
        """Genera reporte de estado actual."""
        if not self.checks_history:
            return {"status": "no_data", "message": "No hay historial de diagnóstico"}
        
        latest = self.checks_history[-1]
        
        # Calcular tendencias
        if len(self.checks_history) >= 10:
            recent = self.checks_history[-10:]
            statuses = [c.get("overall_status", "unknown") for c in recent]
            healthy_count = statuses.count("healthy")
            health_trend = (healthy_count / len(statuses)) * 100
        else:
            health_trend = 100 if latest.get("overall_status") == "healthy" else 0
        
        return {
            "timestamp": latest.get("timestamp"),
            "overall_status": latest.get("overall_status"),
            "issues": latest.get("issues_count"),
            "health_trend_10_checks": f"{health_trend:.0f}%",
            "last_check": latest,
            "checks_history_count": len(self.checks_history),
        }

    async def perform_log_cleanup(self, force: bool = False) -> Dict:
        """
        Public method for on-demand log cleanup (invocable from endpoint).
        Scans all LOG_ACCUMULATION_DIRS, reports status, and cleans if needed or forced.
        """
        # First scan
        scan = await self._check_logs_rotation()
        needs_cleanup = scan.get("status") == "cleanup_needed" or force

        result = {
            "scan": scan,
            "action_taken": None,
            "cleanup_result": None,
        }

        if needs_cleanup:
            cleanup_result = await self._rotate_logs()
            result["action_taken"] = "rotate_and_cleanup"
            result["cleanup_result"] = cleanup_result

            # Re-scan after cleanup
            post_scan = await self._check_logs_rotation()
            result["post_cleanup_scan"] = post_scan
        else:
            result["action_taken"] = "none_needed"

        return result

    async def run_single_check(self) -> Dict:
        """Ejecuta un diagnóstico único (para testing)."""
        return await self.run_diagnostic_cycle()


# Instancia global
_self_diagnostic_instance: Optional[SelfDiagnostic] = None


def get_self_diagnostic() -> SelfDiagnostic:
    """Obtiene instancia singleton del autodiagnóstico."""
    global _self_diagnostic_instance
    if _self_diagnostic_instance is None:
        _self_diagnostic_instance = SelfDiagnostic()
    return _self_diagnostic_instance


async def start_self_diagnostic():
    """Inicia el servicio de autodiagnóstico."""
    diagnostic = get_self_diagnostic()
    await diagnostic.start()


def stop_self_diagnostic():
    """Detiene el servicio de autodiagnóstico."""
    global _self_diagnostic_instance
    if _self_diagnostic_instance:
        _self_diagnostic_instance.stop()
        _self_diagnostic_instance = None
