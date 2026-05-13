import re
from pathlib import Path

p = Path("brain_router.py")
s = p.read_text(encoding="utf-8", errors="ignore")

# buscamos el bloque SYNC_PLAN_WITH_MISSION_V2 ya insertado
if "SYNC_PLAN_WITH_MISSION_V2" not in s:
    raise SystemExit("ERROR: No encuentro SYNC_PLAN_WITH_MISSION_V2 en brain_router.py")

# reemplazar solo la rama de 'else: reconciliar mission_id...' por un reset
# localizamos el fragmento exacto para no romper otras cosas
old = r'''    else:
        # reconciliar mission_id si está desalineado
        if plan_obj.get("mission_id") != mission.get("mission_id"):
            plan_obj["mission_id"] = mission.get("mission_id")
            # mantener created_ts existente si ya estaba, si no usar el de mission
            if not plan_obj.get("created_ts"):
                plan_obj["created_ts"] = mission.get("created_ts")
            plan_obj["updated_ts"] = mission.get("updated_ts")
            if not plan_obj.get("profile"):
                plan_obj["profile"] = "default"
            if "cursor" not in plan_obj:
                plan_obj["cursor"] = 0
            if "steps" not in plan_obj or plan_obj["steps"] is None:
                plan_obj["steps"] = []'''

new = r'''    else:
        # si cambia mission_id, este plan es de otra misión => reset duro
        if plan_obj.get("mission_id") != mission.get("mission_id"):
            plan_obj = {
                "mission_id": mission.get("mission_id"),
                "created_ts": mission.get("created_ts"),
                "updated_ts": mission.get("updated_ts"),
                "profile": "default",
                "cursor": 0,
                "steps": []
            }
        else:
            # misma misión: solo refrescar updated_ts si aplica
            plan_obj["updated_ts"] = mission.get("updated_ts") or plan_obj.get("updated_ts")
            if not plan_obj.get("profile"):
                plan_obj["profile"] = "default"
            if "cursor" not in plan_obj:
                plan_obj["cursor"] = 0
            if "steps" not in plan_obj or plan_obj["steps"] is None:
                plan_obj["steps"] = []'''

if old not in s:
    raise SystemExit("ERROR: No encontré el bloque esperado para reemplazar (quizá cambió el indent/fragmento).")

s = s.replace(old, new, 1)
p.write_text(s, encoding="utf-8")
print("OK: brain_router.py parcheado: POST /mission resetea plan.json si cambia mission_id (plan nuevo por misión nueva).")
