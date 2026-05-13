import time
from typing import Any, Dict, List, Tuple, Optional
from memory_rank import load_rank

def _now_epoch() -> int:
    return int(time.time())

def _kind_weight(kind: str) -> int:
    k = (kind or "fact").strip().lower()
    if k == "rule":
        return 30
    if k == "sop":
        return 20
    return 0

def rank_sort_hits(room_id: str, hits: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Ordena hits priorizando:
    1) kind (rule > sop > fact)
    2) confidence (memory_rank)
    3) last_seen (memory_rank)
    4) ts_epoch del fact (si viene)
    """
    if not hits:
        return []

    rank = load_rank(room_id) or {}
    items = (rank.get("items") or {}) if isinstance(rank, dict) else {}
    if not isinstance(items, dict):
        items = {}

    scored: List[Tuple[Tuple[int, float, int, int], Dict[str, Any]]] = []
    for h in hits:
        if not isinstance(h, dict):
            continue
        fid = h.get("id")
        kind = h.get("kind", "fact")
        ts_fact = int(h.get("ts_epoch", 0) or 0)

        conf = 0.0
        last_seen = 0
        if fid and fid in items and isinstance(items[fid], dict):
            conf = float(items[fid].get("confidence", 0.0) or 0.0)
            last_seen = int(items[fid].get("last_seen", 0) or 0)

        key = (_kind_weight(kind), conf, last_seen, ts_fact)
        scored.append((key, h))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [h for _, h in scored]


def filter_hits_dynamic(
    room_id: str,
    hits: List[Dict[str, Any]],
    min_conf_fact: float = 0.6,
    min_rules_for_prune: int = 3,
    min_conf_rule: float = 0.7,
    keep_max: int = 12,
) -> List[Dict[str, Any]]:
    """
    Si hay suficientes RULE/SOP fuertes, elimina FACTS con confidence baja.
    - RULE/SOP fuertes: conf >= min_conf_rule
    - FACT se mantiene si conf >= min_conf_fact
    """
    if not hits:
        return []

    rank = load_rank(room_id) or {}
    items = (rank.get("items") or {}) if isinstance(rank, dict) else {}
    if not isinstance(items, dict):
        items = {}

    def _conf(fid: Optional[str]) -> float:
        if fid and fid in items and isinstance(items[fid], dict):
            try:
                return float(items[fid].get("confidence", 0.0) or 0.0)
            except Exception:
                return 0.0
        return 0.0

    # contar reglas/sops fuertes
    strong_rules = 0
    for h in hits:
        if not isinstance(h, dict):
            continue
        kind = (h.get("kind") or "fact").strip().lower()
        if kind in ("rule", "sop"):
            if _conf(h.get("id")) >= float(min_conf_rule):
                strong_rules += 1

    pruned: List[Dict[str, Any]] = []
    for h in hits:
        if not isinstance(h, dict):
            continue
        kind = (h.get("kind") or "fact").strip().lower()
        conf = _conf(h.get("id"))

        if strong_rules >= int(min_rules_for_prune) and kind == "fact" and conf < float(min_conf_fact):
            continue

        pruned.append(h)

    return pruned[: max(1, int(keep_max))]

