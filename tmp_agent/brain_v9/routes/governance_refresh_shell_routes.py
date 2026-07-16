"""Governance refresh shell routes split from main.py.

Front: FRONT-BRAIN-MAIN-ROUTER-LOW-RISK-SHELL-MOVE-16B
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from brain_v9.api_security import require_operator_access

router = APIRouter(tags=["governance-refresh-shell"])
OperatorAccess = Annotated[None, Depends(require_operator_access)]


@router.post("/brain/post-bl-roadmap/refresh")
async def brain_post_bl_roadmap_refresh(_operator: OperatorAccess):
    from brain_v9.brain.post_bl_roadmap import refresh_post_bl_roadmap_status
    return refresh_post_bl_roadmap_status()


@router.post("/brain/meta-improvement/refresh")
async def brain_meta_improvement_refresh(_operator: OperatorAccess):
    from brain_v9.brain.meta_improvement import refresh_meta_improvement_status
    return refresh_meta_improvement_status()


@router.post("/brain/chat-product/refresh")
async def brain_chat_product_refresh(_operator: OperatorAccess):
    from brain_v9.brain.chat_product_governance import refresh_chat_product_status
    return refresh_chat_product_status()


@router.post("/brain/autonomous-governance-eval/refresh")
async def brain_autonomous_governance_eval_refresh(_operator: OperatorAccess, run_self_test: bool = False):
    from brain_v9.brain.autonomous_governance_eval import build_autonomous_governance_eval
    return build_autonomous_governance_eval(refresh=True, run_self_test=run_self_test)


@router.post("/brain/utility-governance/refresh")
async def brain_utility_governance_refresh(_operator: OperatorAccess):
    from brain_v9.brain.utility_governance import refresh_utility_governance_status
    return refresh_utility_governance_status()


@router.post("/brain/roadmap/governance/refresh")
async def brain_roadmap_governance_refresh(_operator: OperatorAccess):
    from brain_v9.brain.roadmap_governance import promote_roadmap_if_ready
    return promote_roadmap_if_ready()
