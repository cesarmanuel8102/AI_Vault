$server = "C:\AI_VAULT\00_identity\brain_server.py"
$markerStart = "# ===== Brain Lab Agent Endpoints (v4) ====="

if (!(Test-Path $server)) { throw "No existe: $server" }

$txt = Get-Content -LiteralPath $server -Raw -ErrorAction Stop

if ($txt.Contains($markerStart)) {
  Write-Host "SKIP: El bloque v4 ya existe en brain_server.py" -ForegroundColor Yellow
  exit 0
}

$block = @"
# ===== Brain Lab Agent Endpoints (v4) =====
import os
import sys
from typing import Any, Dict, Optional

from fastapi import Body
from pydantic import BaseModel, Field

TMP_AGENT_ROOT = os.environ.get("BRAIN_TMP_AGENT_ROOT", r"C:\AI_VAULT\tmp_agent")
if TMP_AGENT_ROOT not in sys.path:
    sys.path.append(TMP_AGENT_ROOT)

from agent_state import AgentStateStore  # noqa: E402

agent_store = AgentStateStore(root=TMP_AGENT_ROOT)


class AgentPlanRequest(BaseModel):
    goal: str = Field(..., min_length=1)
    room_id: Optional[str] = None
    context: Optional[Dict[str, Any]] = None


class AgentPlanResponse(BaseModel):
    ok: bool
    mission: Dict[str, Any]
    plan: Dict[str, Any]


class AgentEvalRequest(BaseModel):
    observation: Dict[str, Any] = Field(default_factory=dict)
    room_id: Optional[str] = None


class AgentEvalResponse(BaseModel):
    ok: bool
    plan: Dict[str, Any]
    verdict: Dict[str, Any]


@app.post("/v1/agent/plan", response_model=AgentPlanResponse)
def agent_plan(req: AgentPlanRequest):
    mission, plan = agent_store.load()

    if not plan.get("steps"):
        plan["status"] = "planned"
        plan["steps"] = [
            {"id": "S1", "title": "Ensure state persistence files exist", "status": "done"},
            {"id": "S2", "title": "Expose /v1/agent/plan and /v1/agent/evaluate endpoints", "status": "in_progress"},
            {"id": "S3", "title": "Add gated /v1/agent/execute (filesystem only) + smoke tests", "status": "todo"},
        ]
        agent_store.save_plan(plan)

    plan = agent_store.append_history({
        "kind": "plan",
        "goal": req.goal,
        "room_id": req.room_id,
    })

    mission2, plan2 = agent_store.load()
    return {"ok": True, "mission": mission2, "plan": plan2}


@app.post("/v1/agent/evaluate", response_model=AgentEvalResponse)
def agent_evaluate(req: AgentEvalRequest):
    _, plan = agent_store.load()

    obs_ok = bool(req.observation.get("ok", False))
    verdict = {"status": "no_change", "notes": []}

    steps = plan.get("steps", [])
    for s in steps:
        if s.get("id") == "S2" and s.get("status") == "in_progress" and obs_ok:
            s["status"] = "done"
            plan["status"] = "ready_for_next_step"
            verdict["status"] = "progress"
            verdict["notes"].append("Marked S2 done because observation.ok=true")

    plan["steps"] = steps
    plan["last_eval"] = {"room_id": req.room_id, "observation": req.observation}
    agent_store.save_plan(plan)

    plan = agent_store.append_history({
        "kind": "evaluate",
        "room_id": req.room_id,
        "observation": req.observation,
        "verdict": verdict
    })

    _, plan2 = agent_store.load()
    return {"ok": True, "plan": plan2, "verdict": verdict}
# ===== End Agent Endpoints =====
"@

if (-not $txt.EndsWith("`r`n")) { $txt += "`r`n" }
$txt += "`r`n" + $block + "`r`n"

$tmp = "$server.tmp"
Set-Content -LiteralPath $tmp -Value $txt -Encoding UTF8
Move-Item -Force -LiteralPath $tmp -Destination $server

Write-Host "OK: Bloque v4 agregado al final de brain_server.py" -ForegroundColor Green
