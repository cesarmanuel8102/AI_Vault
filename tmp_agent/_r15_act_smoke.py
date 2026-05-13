"""R15 end-to-end: simulate AgentLoop._act tool call that raises PermissionError on dir."""
import sys, asyncio, json
sys.path.insert(0, "C:/AI_VAULT/tmp_agent")
sys.path.insert(0, "C:/AI_VAULT")

from brain_v9.agent.loop import AgentLoop, ToolExecutor
from brain_v9.agent.tools import build_standard_executor

async def main():
    ex = build_standard_executor()
    loop = AgentLoop(llm=None, tools=ex)
    # _act takes List[Dict] with {tool, args}
    tc = {"tool": "read_file", "args": {"path": "C:/AI_VAULT/tmp_agent/brain_v9"}}
    results = await loop._act([tc])
    for r in results:
        print(f"tool={r.tool}  success={r.success}")
        print(f"  error={r.error}")
        print(f"  duration_ms={r.duration_ms:.0f}")
    print()
    # Also test FileNotFoundError
    tc2 = {"tool": "read_file", "args": {"path": "C:/nonexistent/zzz_xxx_999.txt"}}
    results2 = await loop._act([tc2])
    for r in results2:
        print(f"tool={r.tool}  success={r.success}")
        print(f"  error={r.error}")
    print()
    # Tail event_log
    print("--- last 5 capability.failed events ---")
    import json
    p = "C:/AI_VAULT/state/events/event_log.jsonl"
    try:
        lines = open(p, "r", encoding="utf-8").readlines()[-30:]
        for ln in lines:
            try:
                o = json.loads(ln)
                if o.get("event") == "capability.failed":
                    pl = o.get("payload", {})
                    print(f"  cap={pl.get('capability')}  err_type={pl.get('error_type')}  hint={pl.get('hint')}")
            except Exception:
                pass
    except Exception as e:
        print(f"  log read err: {e}")

asyncio.run(main())
