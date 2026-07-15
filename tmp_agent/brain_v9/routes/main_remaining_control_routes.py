"""Remaining controlled diagnostics/ops routes split from main.py.

Front: FRONT-BRAIN-MAIN-ROUTER-MEGA-AGGRESSIVE-SWEEP-14B
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from brain_v9.api_security import require_operator_access

router = APIRouter(tags=["main-remaining-control"])
OperatorAccess = Annotated[None, Depends(require_operator_access)]


@router.post("/brain/ops/log-cleanup")
async def brain_ops_log_cleanup(_operator: OperatorAccess, force: bool = False):
    """Fase 7.1: On-demand log cleanup across all accumulation directories."""
    from brain_v9.core.self_diagnostic import get_self_diagnostic

    diag = get_self_diagnostic()
    return await diag.perform_log_cleanup(force=force)


@router.get("/brain/ops/log-status")
async def brain_ops_log_status():
    """Fase 7.1: Scan log accumulation status without cleanup."""
    from brain_v9.core.self_diagnostic import get_self_diagnostic

    diag = get_self_diagnostic()
    return await diag._check_logs_rotation()


@router.get("/brain/ops/adn-quality")
async def brain_ops_adn_quality():
    """Fase 7.2: Codebase quality score (ADN modular)."""
    from brain_v9.governance.adn_quality import build_adn_quality_report

    return build_adn_quality_report()


@router.get("/brain/ops/upgrade-check")
async def brain_ops_upgrade_check():
    """Fase 7.3: Run full pre+post upgrade validation checks."""
    from brain_v9.ops.upgrade_protocol import run_full_upgrade_validation

    return await run_full_upgrade_validation()


@router.get("/brain/ops/pre-upgrade")
async def brain_ops_pre_upgrade():
    """Fase 7.3: Run pre-upgrade checks only."""
    from brain_v9.ops.upgrade_protocol import run_pre_upgrade_checks

    return await run_pre_upgrade_checks()


@router.get("/brain/ops/post-upgrade")
async def brain_ops_post_upgrade():
    """Fase 7.3: Run post-upgrade checks only."""
    from brain_v9.ops.upgrade_protocol import run_post_upgrade_checks

    return await run_post_upgrade_checks()


@router.get("/brain/ops/ethics")
async def brain_ops_ethics():
    """Fase 7.4: Ethics kernel compliance check."""
    from brain_v9.governance.ethics_kernel import check_ethics_compliance

    return check_ethics_compliance()


@router.post("/self-diagnostic/run")
async def run_self_diagnostic(_operator: OperatorAccess):
    """Ejecuta un ciclo de diagnóstico manualmente."""
    from brain_v9.core.self_diagnostic import get_self_diagnostic

    diagnostic = get_self_diagnostic()
    return await diagnostic.run_single_check()
