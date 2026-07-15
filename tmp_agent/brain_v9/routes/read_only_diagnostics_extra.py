"""Extra read-only diagnostics routes split from main.py.

Front: FRONT-BRAIN-MAIN-ROUTER-FULL-MIGRATION-SWEEP-13F-TO-CLOSE

This router only exposes GET/status/list/read endpoints and avoids runtime
surfaces outside its narrow diagnostics/read scope.
"""
from __future__ import annotations

from fastapi import APIRouter

from brain_v9.brain.autonomous_governance_eval import read_autonomous_governance_eval_status
from brain_v9.brain.chat_product_governance import read_chat_product_status
from brain_v9.brain.meta_improvement import read_meta_improvement_status
from brain_v9.brain.roadmap_governance import read_roadmap_governance_status
from brain_v9.brain.self_improvement import get_change_status, get_self_improvement_ledger
from brain_v9.brain.utility import is_promotion_safe, read_utility_state
from brain_v9.brain.utility_governance import read_utility_governance_status
from brain_v9.brain.post_bl_roadmap import read_post_bl_roadmap_status
from brain_v9.learning import build_learning_status, read_learning_status
from brain_v9.research.knowledge_base import (
    build_strategy_candidates,
    get_research_summary,
    read_hypothesis_queue,
    read_indicator_registry,
    read_knowledge_base,
    read_strategy_specs,
)

router = APIRouter(tags=["read-only-diagnostics-extra"])


@router.get("/brain/utility")
async def brain_utility():
    state = read_utility_state()
    safe, reason = is_promotion_safe()
    return {
        "u_score": state["u_score"],
        "governance_u_score": state.get("governance_u_score"),
        "real_venue_u_score": state.get("real_venue_u_score"),
        "u_score_components": state.get("u_score_components", {}),
        "u_proxy_score": state.get("u_proxy_score"),
        "verdict": state["verdict"],
        "blockers": state["blockers"],
        "can_promote": safe,
        "promotion_reason": reason,
        "current_phase": state["current_phase"],
        "capital": state["capital"],
        "components": state["components"],
        "sample": state["sample"],
        "next_actions": state["next_actions"],
        "errors": state["errors"],
        "source": state["source"],
    }


@router.get("/brain/utility/v2")
async def brain_utility_v2():
    return await brain_utility()


@router.get("/brain/utility/status")
async def brain_utility_status():
    """Alias: utility status served from canonical /brain/utility/v2."""
    data = await brain_utility_v2()
    return {"ok": True, "route": "/brain/utility/status", "canonical": "/brain/utility/v2", **data}


@router.get("/brain/roadmap/governance")
async def brain_roadmap_governance():
    return read_roadmap_governance_status()


@router.get("/brain/roadmap/development-status")
async def brain_roadmap_development_status():
    governance = read_roadmap_governance_status()
    return governance.get("development_status", {})


@router.get("/brain/post-bl-roadmap/status")
async def brain_post_bl_roadmap_status():
    return read_post_bl_roadmap_status()


@router.get("/brain/meta-improvement/status")
async def brain_meta_improvement_status():
    return read_meta_improvement_status()


@router.get("/brain/chat-product/status")
async def brain_chat_product_status():
    return read_chat_product_status()


@router.get("/brain/autonomous-governance-eval/status")
async def brain_autonomous_governance_eval_status():
    return read_autonomous_governance_eval_status()


@router.get("/brain/utility-governance/status")
async def brain_utility_governance_status():
    return read_utility_governance_status()


@router.get("/brain/research/summary")
async def brain_research_summary():
    return get_research_summary()


@router.get("/brain/research/knowledge")
async def brain_research_knowledge():
    return read_knowledge_base()


@router.get("/brain/research/indicators")
async def brain_research_indicators():
    return read_indicator_registry()


@router.get("/brain/research/strategies")
async def brain_research_strategies():
    return read_strategy_specs()


@router.get("/brain/research/hypotheses")
async def brain_research_hypotheses():
    return read_hypothesis_queue()


@router.get("/brain/research/candidates")
async def brain_research_candidates():
    return {
        "updated_utc": get_research_summary().get("updated_utc"),
        "candidates": build_strategy_candidates(),
    }


@router.get("/brain/learning/status")
async def brain_learning_status(refresh: bool = False):
    return build_learning_status(refresh=True) if refresh else read_learning_status()


@router.get("/brain/self-improvement/ledger")
async def brain_self_improvement_ledger():
    return get_self_improvement_ledger()


@router.get("/brain/self-improvement/change/{change_id}/status")
async def brain_self_improvement_change_status(change_id: str):
    return get_change_status(change_id)
