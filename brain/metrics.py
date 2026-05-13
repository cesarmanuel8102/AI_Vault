"""
Brain Chat V9 — brain/metrics.py
MetricsAggregator + PremisesChecker
Extraído de V8.0 líneas 4055-4489.
Correcciones: imports de config en lugar de globales.
"""
import asyncio
import json
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Tuple

from brain_v9.config import BASE_PATH, LOGS_PATH, MEMORY_PATH, PREMISES_FILE


class MetricsAggregator:
    """Agrega métricas de CPU, memoria, trading y rendimiento."""

    def __init__(self):
        self.logger          = logging.getLogger("MetricsAggregator")
        self.metrics_history: List[Dict] = []
        self.max_history_days = 30
        self.metrics_path    = BASE_PATH / "tmp_agent" / "state" / "metrics"
        try:
            self.metrics_path.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            self.logger.warning("No se pudo crear metrics_path: %s", e)

    async def aggregate_system_metrics(self) -> Dict:
        try:
            metrics = {
                "timestamp":   datetime.now().isoformat(),
                "system":      await self._system(),
                "memory":      await self._memory(),
                "trading":     await self._trading(),
                "performance": await self._performance(),
            }
            self.metrics_history.append(metrics)
            cutoff = datetime.now() - timedelta(days=self.max_history_days)
            self.metrics_history = [
                m for m in self.metrics_history
                if datetime.fromisoformat(m["timestamp"]) > cutoff
            ]
            return metrics
        except Exception as e:
            self.logger.error("Error agregando métricas: %s", e)
            return {"error": str(e)}

    async def _system(self) -> Dict:
        try:
            import psutil
            return {
                "cpu_percent":    psutil.cpu_percent(interval=1),
                "memory_percent": psutil.virtual_memory().percent,
                "disk_usage":     psutil.disk_usage("/").percent,
                "boot_time":      datetime.fromtimestamp(psutil.boot_time()).isoformat(),
            }
        except ImportError:
            return {"note": "psutil no disponible — instalar con: pip install psutil"}
        except Exception as e:
            return {"error": str(e)}

    async def _memory(self) -> Dict:
        try:
            files = list(MEMORY_PATH.glob("*.json"))
            total_size = sum(f.stat().st_size for f in files if f.exists())
            return {
                "memory_files":    len(files),
                "total_size_mb":   round(total_size / (1024 * 1024), 2),
            }
        except Exception as e:
            return {"error": str(e)}

    async def _trading(self) -> Dict:
        try:
            state_dir  = BASE_PATH / "tmp_agent" / "state"
            trade_files = list(state_dir.glob("*trade*.json")) if state_dir.exists() else []
            total_trades = 0
            profit_sum   = 0.0
            for f in trade_files:
                try:
                    data = json.loads(f.read_text(encoding="utf-8"))
                    trades = data.get("trades", [])
                    total_trades += len(trades)
                    profit_sum   += sum(t.get("profit", 0) for t in trades)
                except Exception:
                    pass
            return {
                "total_trades":  total_trades,
                "total_profit":  round(profit_sum, 2),
                "data_sources":  len(trade_files),
            }
        except Exception as e:
            return {"error": str(e)}

    async def _performance(self) -> Dict:
        return {
            "response_times": {"avg_ms": 150, "p95_ms": 300, "p99_ms": 500},
            "availability":   {"uptime_percentage": 99.5},
        }

    async def get_error_rates(self) -> Dict:
        try:
            errors = warnings = total = 0
            for lf in LOGS_PATH.glob("*.log"):
                try:
                    for line in lf.read_text(encoding="utf-8", errors="ignore").splitlines():
                        total += 1
                        if "ERROR" in line:
                            errors += 1
                        elif "WARNING" in line:
                            warnings += 1
                except Exception:
                    pass
            return {
                "error_count":   errors,
                "warning_count": warnings,
                "total_lines":   total,
                "error_rate":    round(errors / total * 100, 4) if total else 0,
            }
        except Exception as e:
            return {"error": str(e)}

    async def get_performance_trends(self, days: int = 7) -> Dict:
        cutoff = datetime.now() - timedelta(days=days)
        recent = [
            m for m in self.metrics_history
            if datetime.fromisoformat(m["timestamp"]) > cutoff
        ]
        if not recent:
            return {"status": "no_data", "days": days}
        cpu_vals = [m["system"].get("cpu_percent", 0) for m in recent if "system" in m]
        mem_vals = [m["system"].get("memory_percent", 0) for m in recent if "system" in m]
        def stats(vals):
            return {"avg": round(sum(vals)/len(vals), 2), "min": round(min(vals), 2), "max": round(max(vals), 2)} if vals else {}
        direction = "stable"
        if len(cpu_vals) >= 2:
            if cpu_vals[-1] > cpu_vals[0] * 1.1:
                direction = "increasing"
            elif cpu_vals[-1] < cpu_vals[0] * 0.9:
                direction = "decreasing"
        return {
            "days":    days,
            "samples": len(recent),
            "cpu":     stats(cpu_vals),
            "memory":  stats(mem_vals),
            "direction": direction,
        }


class PremisesChecker:
    """Valida acciones contra las premisas canónicas del sistema."""

    def __init__(self):
        self.logger      = logging.getLogger("PremisesChecker")
        self.premises    = {}
        self.constraints: List[str] = []
        self._load()

    def _load(self):
        try:
            if PREMISES_FILE.exists():
                content = PREMISES_FILE.read_text(encoding="utf-8")
                self.premises    = self._parse(content)
                self.constraints = self._extract_constraints(content)
                self.logger.info("Premisas cargadas: %d secciones", len(self.premises))
            else:
                self.logger.warning("Archivo de premisas no encontrado: %s", PREMISES_FILE)
        except Exception as e:
            self.logger.error("Error cargando premisas: %s", e)

    def _parse(self, content: str) -> Dict:
        out, section = {}, None
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("## "):
                section = line[3:].strip()
                out[section] = []
            elif section and line:
                out[section].append(line)
        return out

    def _extract_constraints(self, content: str) -> List[str]:
        keywords = ["prohibición","límite","restricción","no debe","debe","requiere"]
        return [
            line.strip().lower()
            for line in content.splitlines()
            if any(k in line.lower() for k in keywords) and len(line.strip()) > 10
        ]

    def check_action_compliance(self, action: Dict) -> Tuple[bool, str]:
        atype  = action.get("type", "").lower()
        params = action.get("params", {})
        violations = []

        destructive = ["delete","remove","destroy","rm -rf"]
        if any(d in atype for d in destructive):
            violations.append("Acción destructiva — requiere validación adicional")

        if "capital" in atype or "trade" in atype:
            if params.get("amount", 0) > 1000:
                violations.append(f"Monto {params['amount']} excede límites de seguridad")

        protected = ["AI_VAULT/Secrets","AI_VAULT/.env","config.json"]
        fpath = params.get("path", "")
        for p in protected:
            if p in fpath:
                violations.append(f"Afecta archivo protegido: {p}")

        if violations:
            return False, "; ".join(violations)
        return True, "Acción conforme con premisas canónicas"
