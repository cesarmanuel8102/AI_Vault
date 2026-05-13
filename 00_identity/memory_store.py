import os
import json
import time
import re
from typing import Any, Dict, List, Optional, Tuple

VAULT_ROOT = r"C:\AI_VAULT"
STATE_ROOT = os.path.join(VAULT_ROOT, "state")

VALID_KINDS = {"fact", "rule", "sop"}

def _room_dir(room_id: str) -> str:
    d = os.path.join(STATE_ROOT, room_id)
    os.makedirs(d, exist_ok=True)
    return d

def facts_path(room_id: str) -> str:
    return os.path.join(_room_dir(room_id), "memory_facts.jsonl")

def _now_epoch() -> int:
    return int(time.time())

def append_fact(
    room_id: str,
    text: str,
    tags: Optional[List[str]] = None,
    source: Optional[str] = None,
    kind: str = "fact",
) -> Dict[str, Any]:
    text = (text or "").strip()
    if not text:
        raise ValueError("text vacío")

    kind = (kind or "fact").strip().lower()
    if kind not in VALID_KINDS:
        kind = "fact"

    rec = {
        "id": f"f{_now_epoch()}_{int(time.time()*1000)%100000}",
        "ts_epoch": _now_epoch(),
        "kind": kind,
        "text": text,
        "tags": [str(t).strip() for t in (tags or []) if str(t).strip()],
        "source": source or None,
    }

    p = facts_path(room_id)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec

def list_facts(room_id: str, limit: int = 50) -> List[Dict[str, Any]]:
    limit = max(1, min(int(limit), 500))
    p = facts_path(room_id)
    if not os.path.exists(p):
        return []

    with open(p, "r", encoding="utf-8") as f:
        lines = f.readlines()

    out: List[Dict[str, Any]] = []
    for line in lines[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except Exception:
            continue
    return out

_word_re = re.compile(r"[A-Za-z0-9_]+", re.UNICODE)

def _tokenize(s: str) -> List[str]:
    return [w.lower() for w in _word_re.findall(s or "") if w]

def query_facts(
    room_id: str,
    query: str,
    limit: int = 10,
    kinds: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    limit = max(1, min(int(limit), 50))
    q = (query or "").strip()
    if not q:
        return []

    qtok = set(_tokenize(q))
    if not qtok:
        return []

    allow_kinds = None
    if kinds:
        allow_kinds = set([(k or "").strip().lower() for k in kinds if (k or "").strip()])
        allow_kinds = set([k for k in allow_kinds if k in VALID_KINDS]) or None

    facts = list_facts(room_id, limit=500)
    scored: List[Tuple[int, Dict[str, Any]]] = []

    for rec in facts:
        kind = (rec.get("kind") or "fact").lower()
        if allow_kinds and kind not in allow_kinds:
            continue

        text = rec.get("text", "")
        tags = rec.get("tags", []) or []
        tok = set(_tokenize(text)) | set([str(t).lower() for t in tags])

        inter = len(qtok & tok)
        if inter == 0:
            continue

        # Bonus por tags
        bonus_tags = 2 if any(str(t).lower() in qtok for t in tags) else 0

        # Peso por kind (rules/sops arriba)
        bonus_kind = 0
        if kind == "rule":
            bonus_kind = 6
        elif kind == "sop":
            bonus_kind = 4

        score = inter + bonus_tags + bonus_kind
        scored.append((score, rec))

    scored.sort(key=lambda x: (x[0], x[1].get("ts_epoch", 0)), reverse=True)
    return [r for _, r in scored[:limit]]


def _norm_text(s: str) -> str:
    return " ".join((s or "").strip().lower().split())

def _infer_kind_from_tags(kind: str, tags: List[str], text: str = "") -> str:
    # Respeta kind explícito si ya viene en VALID_KINDS y no es "fact"
    k = (kind or "fact").strip().lower()
    if k in VALID_KINDS and k != "fact":
        return k

    # Heurística por texto (más fuerte que tags)
    t = (text or "").strip().lower()
    if t.startswith("regla:") or t.startswith("rule:"):
        return "rule"
    if t.startswith("sop:") or t.startswith("playbook:"):
        return "sop"

    # Fallback por tags
    tags_l = [str(tg).lower() for tg in (tags or [])]
    if "rule" in tags_l:
        return "rule"
    if "sop" in tags_l:
        return "sop"
    return "fact"

def compact_facts(room_id: str, promote: bool = True, keep_backup: bool = True) -> Dict[str, Any]:
    """
    Dedupe facts por (kind+text_normalizado). Mantiene el más reciente.
    Escribe memory_facts_compacted.jsonl y opcionalmente backup del original.
    """
    src = facts_path(room_id)
    if not os.path.exists(src):
        return {"ok": True, "note": "no facts file", "kept": 0, "dropped": 0}

    with open(src, "r", encoding="utf-8") as f:
        lines = [ln.strip() for ln in f.readlines() if ln.strip()]

    items: List[Dict[str, Any]] = []
    bad = 0
    for ln in lines:
        try:
            items.append(json.loads(ln))
        except Exception:
            bad += 1

    # dedupe: mantener más reciente por key
    best: Dict[str, Dict[str, Any]] = {}
    for rec in items:
        text = rec.get("text", "")
        tags = rec.get("tags", []) or []
        kind = rec.get("kind", "fact")

        if promote:
            kind = _infer_kind_from_tags(kind, tags, text=text)
            rec["kind"] = kind

        key = f"{kind}|{_norm_text(text)}"
        ts = int(rec.get("ts_epoch", 0) or 0)

        cur = best.get(key)
        if (cur is None) or (int(cur.get("ts_epoch", 0) or 0) <= ts):
            best[key] = rec

    kept = list(best.values())
    kept.sort(key=lambda r: int(r.get("ts_epoch", 0) or 0))

    out_path = os.path.join(_room_dir(room_id), "memory_facts_compacted.jsonl")
    with open(out_path, "w", encoding="utf-8") as f:
        for rec in kept:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    backup_path = None
    if keep_backup:
        backup_path = os.path.join(_room_dir(room_id), f"memory_facts.backup_{_now_epoch()}.jsonl")
        try:
            os.replace(src, backup_path)
            os.replace(out_path, src)  # compacted pasa a ser el principal
        except Exception:
            # si falla replace, deja compacted aparte
            backup_path = None

    dropped = max(0, len(items) - len(kept))
    return {
        "ok": True,
        "kept": len(kept),
        "dropped": dropped,
        "bad_lines": bad,
        "backup_path": backup_path,
        "final_path": src if backup_path else out_path,
    }




