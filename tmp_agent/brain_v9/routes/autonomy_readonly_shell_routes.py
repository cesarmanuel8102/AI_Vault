"""Read-only autonomy shell routes split from main.py.

Front: FRONT-BRAIN-MAIN-ROUTER-LOW-RISK-SHELL-MOVE-16B
"""
from __future__ import annotations

from fastapi import APIRouter

from brain_v9.brain.utility import write_utility_snapshots

router = APIRouter(tags=["autonomy-readonly"])


@router.get("/brain/autonomy/next-actions")
async def brain_autonomy_next_actions():
    result = write_utility_snapshots()
    return result["next_actions"]
