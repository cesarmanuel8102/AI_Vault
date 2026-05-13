"""
Brain Chat V9 — BrainHealthMonitor
Verifica conectividad de todos los servicios del ecosistema AI_VAULT.
"""
import logging
import time
from typing import Dict

from aiohttp import ClientSession, ClientTimeout


class BrainHealthMonitor:
    SERVICES = {
        "brain_v9":   {"url": "http://127.0.0.1:8090", "name": "Brain V9"},
        "brain_api":  {"url": "http://127.0.0.1:8000", "name": "Brain API"},
        "dashboard":  {"url": "http://127.0.0.1:8070", "name": "Dashboard"},
        "bridge":     {"url": "http://127.0.0.1:8765", "name": "PocketOption Bridge"},
        "ollama":     {"url": "http://127.0.0.1:11434","name": "Ollama"},
    }

    def __init__(self):
        self.logger = logging.getLogger("BrainHealthMonitor")

    async def check_all_services(self) -> Dict:
        results = {
            "timestamp":      __import__("datetime").datetime.now().isoformat(),
            "overall_status": "healthy",
            "services":       {},
            "summary":        {"total": len(self.SERVICES), "healthy": 0, "unhealthy": 0},
        }
        for svc_id, cfg in self.SERVICES.items():
            status = await self._check(svc_id, cfg["url"])
            results["services"][svc_id] = status
            if status.get("healthy"):
                results["summary"]["healthy"] += 1
            else:
                results["summary"]["unhealthy"] += 1

        if results["summary"]["unhealthy"] > results["summary"]["healthy"]:
            results["overall_status"] = "critical"
        elif results["summary"]["unhealthy"] > 0:
            results["overall_status"] = "degraded"

        return results

    async def _check(self, name: str, url: str) -> Dict:
        try:
            t0 = time.time()
            async with ClientSession(timeout=ClientTimeout(total=5)) as s:
                async with s.get(f"{url}/health") as r:
                    latency_ms = (time.time() - t0) * 1000
                    return {"healthy": r.status == 200, "latency_ms": round(latency_ms, 1)}
        except Exception as e:
            return {"healthy": False, "error": str(e)}
