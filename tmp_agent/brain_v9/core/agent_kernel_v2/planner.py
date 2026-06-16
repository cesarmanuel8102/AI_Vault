from __future__ import annotations
from .runtime import get_agent_runtime_v2

def create_plan_for_goal(goal: str):
    rt = get_agent_runtime_v2()
    run = rt.create_run(goal, mode="read_only", user_id="planner_probe")
    return rt.plan_run(run["run_id"])["plan"]
