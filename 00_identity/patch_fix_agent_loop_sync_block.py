import re
from pathlib import Path

p = Path("brain_router.py")
s = p.read_text(encoding="utf-8", errors="ignore")

# Reemplazar el bloque agent_loop_sync existente por versión correcta
pat = re.compile(
    r'\n\s*# agent_loop_sync:.*?\n\s*try:\n.*?\n\s*except Exception:\n\s*pass\n',
    re.S
)

m = pat.search(s)
if not m:
    raise SystemExit("ERROR: No encontré el bloque agent_loop_sync para reemplazar en brain_router.py")

replacement = """
    # agent_loop_sync: crear mission.json/plan.json compatibles con AgentLoop (mission_id + plan.mission_id)
    try:
        # Reusar room_id normalizado ya calculado arriba
        loop = AgentLoop(paths=AgentPaths.default(room_id=room_id))
        loop.plan(goal=str(body.objective), profile="default", force_new=True)
    except Exception as _e:
        # No romper el endpoint; registrar en logs de episodio si quieres (por ahora silencioso)
        pass
"""

s = s[:m.start()] + "\n" + replacement.strip("\n") + "\n" + s[m.end():]
p.write_text(s, encoding="utf-8")
print("OK: agent_loop_sync corregido (usa body.objective y room_id).")
