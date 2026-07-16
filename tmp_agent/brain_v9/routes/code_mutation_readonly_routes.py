"""Read-only code mutation observability routes split from main.py.

Front: FRONT-BRAIN-MAIN-ROUTER-LOW-RISK-SHELL-MOVE-16B
"""
from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["code-mutation-readonly"])


@router.get("/brain/mutations")
async def brain_mutations(limit: int = 20):
    """List recent code mutations."""
    try:
        from brain_v9.agent.code_mutator import CodeMutator
        mutator = CodeMutator.get()
        mutations = mutator.list_mutations(limit)
        return {"count": len(mutations), "mutations": mutations}
    except Exception as exc:
        return {"_error": str(exc), "count": 0, "mutations": []}


@router.get("/brain/mutations/{mutation_id}")
async def brain_mutation_detail(mutation_id: str):
    """Get details of a specific mutation."""
    try:
        from brain_v9.agent.code_mutator import CodeMutator
        mutator = CodeMutator.get()
        m = mutator.get_mutation(mutation_id)
        if not m:
            raise HTTPException(status_code=404, detail=f"Mutation {mutation_id} not found")
        return m
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
