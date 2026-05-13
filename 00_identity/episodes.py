import os
import json
import time
from typing import Any, Dict, Optional

VAULT_ROOT = r"C:\AI_VAULT"
STATE_ROOT = os.path.join(VAULT_ROOT, "state")

def _room_dir(room_id: str) -> str:
    d = os.path.join(STATE_ROOT, room_id)
    os.makedirs(d, exist_ok=True)
    return d

def _episodes_root(room_id: str) -> str:
    d = os.path.join(_room_dir(room_id), "episodes")
    os.makedirs(d, exist_ok=True)
    return d

def _now_epoch() -> int:
    return int(time.time())

def _new_episode_id(room_id: str) -> str:
    return f"ep_{room_id}_{_now_epoch()}_{int(time.time()*1000)%100000}"

def _current_ptr_path(room_id: str) -> str:
    return os.path.join(_room_dir(room_id), "episode_current.json")

def get_current_episode_id(room_id: str) -> Optional[str]:
    p = _current_ptr_path(room_id)
    if not os.path.exists(p):
        return None
    try:
        with open(p, "r", encoding="utf-8") as f:
            obj = json.load(f)
        return obj.get("episode_id")
    except Exception:
        return None

def start_episode(room_id: str, mission: Optional[Dict[str, Any]] = None) -> str:
    ep_id = _new_episode_id(room_id)
    ep_dir = os.path.join(_episodes_root(room_id), ep_id)
    os.makedirs(ep_dir, exist_ok=True)

    ep = {
        "episode_id": ep_id,
        "room_id": room_id,
        "created_at": _now_epoch(),
        "mission": mission or {},
        "events": [],
    }

    with open(os.path.join(ep_dir, "episode.json"), "w", encoding="utf-8") as f:
        json.dump(ep, f, ensure_ascii=False, indent=2)

    with open(_current_ptr_path(room_id), "w", encoding="utf-8") as f:
        json.dump({"episode_id": ep_id, "updated_at": _now_epoch()}, f, ensure_ascii=False, indent=2)

    return ep_id

def _episode_path(room_id: str, episode_id: str) -> str:
    return os.path.join(_episodes_root(room_id), episode_id, "episode.json")

def append_episode_event(room_id: str, event: Dict[str, Any]) -> None:
    ep_id = get_current_episode_id(room_id)
    if not ep_id:
        # si no hay episodio, crearlo sin misión
        ep_id = start_episode(room_id, mission={})

    p = _episode_path(room_id, ep_id)
    if not os.path.exists(p):
        # episodio perdido: recrear
        ep_id = start_episode(room_id, mission={})
        p = _episode_path(room_id, ep_id)

    try:
        with open(p, "r", encoding="utf-8") as f:
            ep = json.load(f)
    except Exception:
        ep = {"episode_id": ep_id, "room_id": room_id, "created_at": _now_epoch(), "mission": {}, "events": []}

    event_line = {"ts_epoch": _now_epoch(), **event}
    ep.setdefault("events", []).append(event_line)

    with open(p, "w", encoding="utf-8") as f:
        json.dump(ep, f, ensure_ascii=False, indent=2)

    with open(_current_ptr_path(room_id), "w", encoding="utf-8") as f:
        json.dump({"episode_id": ep_id, "updated_at": _now_epoch()}, f, ensure_ascii=False, indent=2)

def get_latest_episode(room_id: str) -> Dict[str, Any]:
    ep_id = get_current_episode_id(room_id)
    if not ep_id:
        return {}
    p = _episode_path(room_id, ep_id)
    if not os.path.exists(p):
        return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def write_review(room_id: str, review: Dict[str, Any]) -> None:
    ep_id = get_current_episode_id(room_id)
    if not ep_id:
        ep_id = start_episode(room_id, mission={})
    ep_dir = os.path.join(_episodes_root(room_id), ep_id)
    os.makedirs(ep_dir, exist_ok=True)
    p = os.path.join(ep_dir, "review.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(review, f, ensure_ascii=False, indent=2)
