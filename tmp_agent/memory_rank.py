import os
import json
import time
from typing import Any, Dict, List, Optional, Tuple

VAULT_ROOT = r"C:\AI_VAULT"
STATE_ROOT = os.path.join(VAULT_ROOT, "state")

def _room_dir(room_id: str) -> str:
    d = os.path.join(STATE_ROOT, room_id)
    os.makedirs(d, exist_ok=True)
    return d

def _rank_path(room_id: str) -> str:
    return os.path.join(_room_dir(room_id), "memory_rank.json")

def _now_epoch() -> int:
    return int(time.time())

def load_rank(room_id: str) -> Dict[str, Any]:
    p = _rank_path(room_id)
    if not os.path.exists(p):
        return {"room_id": room_id, "updated_at": _now_epoch(), "items": {}}
    try:
        with open(p, "r", encoding="utf-8") as f:
            obj = json.load(f)
        if not isinstance(obj, dict):
            return {"room_id": room_id, "updated_at": _now_epoch(), "items": {}}
        obj.setdefault("room_id", room_id)
        obj.setdefault("items", {})
        return obj
    except Exception:
        return {"room_id": room_id, "updated_at": _now_epoch(), "items": {}}

def save_rank(room_id: str, rank: Dict[str, Any]) -> None:
    rank["room_id"] = room_id
    rank["updated_at"] = _now_epoch()
    p = _rank_path(room_id)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(rank, f, ensure_ascii=False, indent=2)

def _laplace_conf(good: int, seen: int) -> float:
    # Suavizado: (good+1)/(seen+2)
    return float(good + 1) / float(seen + 2) if seen >= 0 else 0.5

def _extract_hits_from_episode(ep: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not isinstance(ep, dict):
        return out
    for ev in ep.get("events", []) or []:
        if not isinstance(ev, dict):
            continue
        if ev.get("type") != "memory_hits":
            continue
        hits = ev.get("hits", []) or []
        where = ev.get("where", "")
        for h in hits:
            if isinstance(h, dict) and h.get("id"):
                out.append({"where": where, **h})
    return out

def update_rank_from_episode(
    room_id: str,
    episode: Dict[str, Any],
    verdict: Dict[str, Any],
) -> Dict[str, Any]:
    rank = load_rank(room_id)
    items: Dict[str, Any] = rank.get("items", {})
    if not isinstance(items, dict):
        items = {}

    ep_id = (episode or {}).get("episode_id")
    hits = _extract_hits_from_episode(episode)

    # Señal de éxito/fracaso
    ok = bool(verdict.get("ok", False))
    score = int(verdict.get("score", 0) or 0)

    # criterio simple:
    good = ok and score >= 80
    bad = (not ok) or score <= 60

    touched = 0
    for h in hits:
        fid = h.get("id")
        if not fid:
            continue
        
        # Datos del hit
        h_text = (h.get("text", "") or "")
        h_tags = (h.get("tags", []) or [])
        h_kind = (h.get("kind", "fact") or "fact")
        
        # Anti-drift: infer kind desde texto/tags si viene "fact" o incoherente
        inferred_kind = _infer_kind(h_kind, h_tags, h_text)
        if not fid:
            continue

        rec = items.get(fid) or {}
        if not isinstance(rec, dict):
            rec = {}

        rec.setdefault("id", fid)
        rec["text"] = h.get("text", rec.get("text"))
        prev_kind = (rec.get("kind") or "fact").strip().lower()

        def _klevel(k: str) -> int:
            k = (k or "fact").strip().lower()
            if k == "rule":
                return 3
            if k == "sop":
                return 2
            return 1

        # Promover si inferred_kind es más alto; nunca degradar
        rec["kind"] = inferred_kind if _klevel(inferred_kind) >= _klevel(prev_kind) else prev_kind

        rec["tags"] = h.get("tags", rec.get("tags", []))
        rec["source"] = h.get("source", rec.get("source"))
        rec["last_seen"] = _now_epoch()
        rec["last_episode_id"] = ep_id
        rec["seen"] = int(rec.get("seen", 0) or 0) + 1
        rec["seen_planner"] = int(rec.get("seen_planner", 0) or 0) + (1 if h.get("where") == "planner" else 0)
        rec["seen_executor"] = int(rec.get("seen_executor", 0) or 0) + (1 if h.get("where") == "executor" else 0)

        if good:
            rec["good"] = int(rec.get("good", 0) or 0) + 1
        if bad:
            rec["bad"] = int(rec.get("bad", 0) or 0) + 1

        rec["confidence"] = round(_laplace_conf(int(rec.get("good", 0) or 0), int(rec.get("seen", 0) or 0)), 6)

        items[fid] = rec
        touched += 1

    rank["items"] = items
    save_rank(room_id, rank)

    return {"ok": True, "episode_id": ep_id, "touched": touched, "good": good, "bad": bad, "score": score}

def get_rank_list(
    room_id: str,
    min_seen: int = 1,
    kinds: Optional[List[str]] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    rank = load_rank(room_id)
    items = rank.get("items", {})
    if not isinstance(items, dict):
        return []

    allow = None
    if kinds:
        allow = set([(k or "").strip().lower() for k in kinds if (k or "").strip()])

    out = []
    for _, rec in items.items():
        if not isinstance(rec, dict):
            continue
        seen = int(rec.get("seen", 0) or 0)
        if seen < int(min_seen):
            continue
        kind = (rec.get("kind") or "fact").strip().lower()
        if allow and kind not in allow:
            continue
        out.append(rec)

    out.sort(key=lambda r: (float(r.get("confidence", 0.0) or 0.0), int(r.get("seen", 0) or 0)), reverse=True)
    return out[: max(1, min(int(limit), 200))]


# --- kind promotion helper (anti-drift) ---
VALID_KINDS = {"fact", "rule", "sop"}

def _infer_kind(kind: str, tags: List[str], text: str = "") -> str:
    k = (kind or "fact").strip().lower()
    if k in VALID_KINDS and k != "fact":
        return k

    t = (text or "").strip().lower()
    if t.startswith("sop:") or t.startswith("playbook:"):
        return "sop"
    if t.startswith("regla:") or t.startswith("rule:"):
        return "rule"

    tags_l = [str(tg).lower() for tg in (tags or [])]
    if "sop" in tags_l:
        return "sop"
    if "rule" in tags_l:
        return "rule"
    return "fact"






