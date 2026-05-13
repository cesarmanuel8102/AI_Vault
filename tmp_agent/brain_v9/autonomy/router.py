"""
Brain Chat V9 — autonomy/router.py
Endpoints del sistema de autonomía.
"""
from typing import Annotated, Dict, List

from fastapi import APIRouter, Depends

from brain_v9.api_security import require_operator_access
from brain_v9.autonomy.manager import AutonomyManager, get_autonomy_manager

router  = APIRouter(prefix="/autonomy", tags=["autonomy"])
OperatorAccess = Annotated[None, Depends(require_operator_access)]


def get_manager() -> AutonomyManager:
    return get_autonomy_manager()


@router.get("/status")
async def status() -> Dict:
    return get_manager().get_status()


@router.get("/cycle")
async def cycle() -> Dict:
    return get_manager().get_cycle_snapshot()


@router.get("/reports")
async def reports(limit: int = 20) -> List[Dict]:
    return get_manager().get_recent_reports(limit)


@router.post("/start")
async def start(_operator: OperatorAccess) -> Dict:
    await get_manager().start()
    return {"ok": True, "message": "AutonomyManager iniciado"}


@router.post("/stop")
async def stop(_operator: OperatorAccess) -> Dict:
    await get_manager().stop()
    return {"ok": True, "message": "AutonomyManager detenido"}


@router.delete("/reports")
async def clear_reports(_operator: OperatorAccess) -> Dict:
    get_manager().clear_reports()
    return {"ok": True}
