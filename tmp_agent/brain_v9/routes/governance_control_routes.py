"""Governance/control routes split from main.py.

Front: FRONT-BRAIN-MAIN-ROUTER-MEGA-AGGRESSIVE-SWEEP-14B
"""
from __future__ import annotations

from typing import Annotated, Dict

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from brain_v9.api_security import require_operator_access
from brain_v9.brain.change_control import build_change_scorecard, get_change_scorecard_latest
from brain_v9.brain.control_layer import (
    build_control_layer_status,
    freeze_control_layer,
    get_control_layer_status_latest,
    unfreeze_control_layer,
)
from brain_v9.brain.meta_governance import build_meta_governance_status, get_meta_governance_status_latest
from brain_v9.brain.purpose import build_purpose_status, read_purpose_status
from brain_v9.brain.self_improvement import (
    create_staged_change,
    promote_staged_change,
    rollback_change,
    validate_staged_change,
)
from brain_v9.brain.utility import write_utility_snapshots

router = APIRouter(tags=["governance-control"])
OperatorAccess = Annotated[None, Depends(require_operator_access)]


class ChangeRequest(BaseModel):
    files: list[str]
    objective: str = ""
    change_type: str = "code_patch"


@router.get("/brain/meta-governance/status")
async def brain_meta_governance_status(refresh: bool = False):
    if refresh:
        result = write_utility_snapshots()
        return result.get("meta_governance") or build_meta_governance_status(
            utility_snapshot=result.get("snapshot"),
            utility_gate=result.get("gate"),
            raw_next_actions=result.get("next_actions"),
        )
    return get_meta_governance_status_latest()


@router.get("/brain/change-control/scorecard")
async def brain_change_control_scorecard(refresh: bool = False):
    return build_change_scorecard() if refresh else get_change_scorecard_latest()


@router.get("/brain/control-layer/status")
async def brain_control_layer_status(refresh: bool = False):
    return build_control_layer_status(refresh_change_scorecard=True) if refresh else get_control_layer_status_latest()


@router.get("/brain/purpose/status")
async def brain_purpose_status(refresh: bool = True):
    return build_purpose_status(refresh=refresh) if refresh else read_purpose_status()


@router.get("/brain/consciousness/status")
async def brain_consciousness_status(refresh: bool = True):
    status = build_purpose_status(refresh=refresh) if refresh else read_purpose_status()
    return {
        "note": "Operational software self-model, not literal sentience.",
        "purpose": status.get("purpose_layer", {}),
        "consciousness_layer": status.get("consciousness_layer", {}),
        "self_improvement_layer": status.get("self_improvement_layer", {}),
        "control_layer": status.get("control_layer", {}),
        "decision": status.get("decision", {}),
    }


@router.post("/brain/purpose/refresh")
async def brain_purpose_refresh(_operator: OperatorAccess):
    return build_purpose_status(refresh=True)


@router.post("/brain/control-layer/freeze")
async def brain_control_layer_freeze(_operator: OperatorAccess, reason: str = "manual_freeze"):
    return freeze_control_layer(reason=reason, source="api")


@router.post("/brain/control-layer/unfreeze")
async def brain_control_layer_unfreeze(_operator: OperatorAccess, reason: str = "manual_unfreeze"):
    return unfreeze_control_layer(reason=reason, source="api")


@router.post("/brain/self-improvement/change")
async def brain_self_improvement_create(req: ChangeRequest, _operator: OperatorAccess):
    return create_staged_change(req.files, req.objective, req.change_type)


@router.post("/brain/self-improvement/change/{change_id}/validate")
async def brain_self_improvement_validate(change_id: str, _operator: OperatorAccess):
    return validate_staged_change(change_id)


@router.post("/brain/self-improvement/change/{change_id}/promote")
async def brain_self_improvement_promote(change_id: str, _operator: OperatorAccess):
    return promote_staged_change(change_id)


@router.post("/brain/self-improvement/change/{change_id}/rollback")
async def brain_self_improvement_rollback(change_id: str, _operator: OperatorAccess):
    return rollback_change(change_id)


@router.post("/brain/validate")
async def validate_action(action: Dict, _operator: OperatorAccess):
    from brain_v9.brain.metrics import PremisesChecker

    ok, msg = PremisesChecker().check_action_compliance(action)
    return {"valid": ok, "message": msg}
