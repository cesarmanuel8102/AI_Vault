"""
Brain Chat V9 — autonomy/router.py
Endpoints del sistema de autonomía.
"""
from typing import Dict, List

from fastapi import APIRouter

from brain_v9.autonomy.manager import AutonomyManager

router  = APIRouter(prefix="/autonomy", tags=["autonomy"])
_mgr: AutonomyManager = None


def get_manager() -> AutonomyManager:
    global _mgr
    if _mgr is None:
        _mgr = AutonomyManager()
    return _mgr


@router.get("/status")
async def status() -> Dict:
    return get_manager().get_status()


@router.get("/reports")
async def reports(limit: int = 20) -> List[Dict]:
    return get_manager().get_recent_reports(limit)


@router.post("/start")
async def start() -> Dict:
    await get_manager().start()
    return {"ok": True, "message": "AutonomyManager iniciado"}


@router.post("/stop")
async def stop() -> Dict:
    await get_manager().stop()
    return {"ok": True, "message": "AutonomyManager detenido"}


@router.delete("/reports")
async def clear_reports() -> Dict:
    get_manager().clear_reports()
    return {"ok": True}
