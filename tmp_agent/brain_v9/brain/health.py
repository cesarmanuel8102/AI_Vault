"""
Brain Chat V9 — BrainHealthMonitor
Verifica conectividad de servicios activos del runtime actual.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Any, Dict

from aiohttp import ClientSession, ClientTimeout

import brain_v9.config as _cfg


class BrainHealthMonitor:
    SERVICES = {
        "brain_v9": {
            "url": "http://127.0.0.1:8090/health",
            "name": "Brain V9",
            "required": True,
            "success_statuses": {200},
        },
        "bridge": {
            "url": f"{_cfg.POCKETOPTION_BRIDGE_URL}/healthz",
            "name": "PocketOption Bridge",
            "required": False,
            "success_statuses": {200},
        },
        "ollama": {
            "url": "http://127.0.0.1:11434/api/tags",
            "name": "Ollama",
            "required": False,
            "success_statuses": {200},
        },
    }

    def __init__(self):
        self.logger = logging.getLogger("BrainHealthMonitor")

    async def check_all_services(self) -> Dict[str, Any]:
        results = {
            "timestamp": datetime.now().isoformat(),
            "overall_status": "healthy",
            "services": {},
            "summary": {
                "total": len(self.SERVICES),
                "healthy": 0,
                "unhealthy": 0,
                "required_unhealthy": 0,
                "optional_unhealthy": 0,
            },
        }
        for svc_id, cfg in self.SERVICES.items():
            status = await self._check(svc_id, cfg)
            results["services"][svc_id] = status
            if status.get("healthy"):
                results["summary"]["healthy"] += 1
            else:
                results["summary"]["unhealthy"] += 1
                if status.get("required"):
                    results["summary"]["required_unhealthy"] += 1
                else:
                    results["summary"]["optional_unhealthy"] += 1

        if results["summary"]["required_unhealthy"] > 0:
            results["overall_status"] = "critical"
        elif results["summary"]["optional_unhealthy"] > 0:
            results["overall_status"] = "degraded"

        return results

    async def _check(self, name: str, cfg: Dict[str, Any]) -> Dict[str, Any]:
        url = str(cfg.get("url") or "")
        required = bool(cfg.get("required", False))
        success_statuses = set(cfg.get("success_statuses") or {200})
        try:
            t0 = time.time()
            async with ClientSession(timeout=ClientTimeout(total=5)) as s:
                async with s.get(url) as r:
                    latency_ms = (time.time() - t0) * 1000
                    payload: Dict[str, Any] | None = None
                    try:
                        payload = await r.json(content_type=None)
                    except Exception as exc:
                        self.logger.debug("Non-JSON health payload for %s: %s", name, exc)
                    healthy = r.status in success_statuses
                    if isinstance(payload, dict):
                        if "healthy" in payload:
                            healthy = bool(payload.get("healthy"))
                        elif "status" in payload:
                            healthy = str(payload.get("status")).lower() in {"healthy", "available", "ok"}
                        elif payload.get("models") is not None and name == "ollama":
                            healthy = True
                    return {
                        "healthy": healthy,
                        "required": required,
                        "latency_ms": round(latency_ms, 1),
                        "status_code": r.status,
                        "url": url,
                    }
        except Exception as exc:
            return {
                "healthy": False,
                "required": required,
                "url": url,
                "error": str(exc),
            }
