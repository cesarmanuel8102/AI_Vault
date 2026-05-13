from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict


def now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


def append_policy_event(policy_events_path: Path, event: Dict[str, Any]) -> None:
    policy_events_path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(event, ensure_ascii=False)
    with policy_events_path.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def load_policy_registry(registry_path: Path) -> Dict[str, Any]:
    if not registry_path.exists():
        return {"version": 1, "updated_at": "", "rules": [], "sops": [], "stats": {}}
    try:
        return json.loads(registry_path.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "updated_at": "", "rules": [], "sops": [], "stats": {"corrupt": True}}


def save_policy_registry(registry_path: Path, obj: Dict[str, Any]) -> None:
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    obj["updated_at"] = now_iso()
    registry_path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def update_registry_from_episode(*, registry_path: Path, policy_events_path: Path, episode_event: Dict[str, Any]) -> None:
    reg = load_policy_registry(registry_path)

    v = episode_event.get("violations") or []
    if isinstance(v, list) and v:
        reg.setdefault("stats", {})
        reg["stats"]["violations_total"] = int(reg["stats"].get("violations_total", 0)) + len(v)
        reg["stats"]["last_violation_at"] = episode_event.get("at", now_iso())

        append_policy_event(policy_events_path, {
            "type": "policy_violation",
            "at": episode_event.get("at", now_iso()),
            "room": episode_event.get("room"),
            "step_id": episode_event.get("step_id"),
            "violations": v,
        })

    if episode_event.get("type") in {"step_evaluated", "run_evaluated"}:
        append_policy_event(policy_events_path, {
            "type": "policy_eval",
            "at": episode_event.get("at", now_iso()),
            "room": episode_event.get("room"),
            "step_id": episode_event.get("step_id"),
            "score": episode_event.get("score"),
            "verdict": episode_event.get("verdict"),
        })

    save_policy_registry(registry_path, reg)
