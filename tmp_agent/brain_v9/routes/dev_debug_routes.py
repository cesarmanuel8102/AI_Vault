"""Developer/debug diagnostic GET routes split from main.py."""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["dev-debug-diagnostics"])


@router.get("/brain/auto-surgeon/status")
async def brain_auto_surgeon_status():
    from brain_v9.brain.auto_surgeon import get_surgeon_status
    return get_surgeon_status()


@router.get("/brain/auto-surgeon/diagnostics")
async def brain_auto_surgeon_diagnostics():
    from brain_v9.brain.trade_diagnostics import get_diagnostics_status
    return get_diagnostics_status()


@router.get("/self-diagnostic")
async def self_diagnostic():
    """Endpoint para obtener estado del autodiagnóstico."""
    from brain_v9.core.self_diagnostic import get_self_diagnostic
    diagnostic = get_self_diagnostic()
    return diagnostic.get_status_report()


@router.get("/brain/metacognition/status")
async def brain_metacognition_status(refresh: bool = True):
    from brain_v9.brain.metacognition import build_metacognition_status, read_metacognition_status
    return build_metacognition_status() if refresh else read_metacognition_status()


@router.get("/brain/introspection/status")
async def brain_introspection_status(refresh: bool = True):
    from brain_v9.brain.technical_introspection import build_introspection_status, read_introspection_status
    return build_introspection_status() if refresh else read_introspection_status()


@router.get("/brain/introspection/gpu")
async def brain_introspection_gpu():
    from brain_v9.brain.technical_introspection import get_gpu_status
    return get_gpu_status()
