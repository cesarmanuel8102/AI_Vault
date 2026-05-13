import json
import os
from datetime import datetime
from typing import Dict, Any, Tuple

ROOT = os.path.dirname(os.path.abspath(__file__))
GOV = os.path.join(os.path.dirname(ROOT), "governance")
LOGS = os.path.join(os.path.dirname(ROOT), "logs")

def _load_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)

def _append_jsonl(path: str, obj: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8-sig") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")

def score_proposal(proposal: Dict[str, Any], policy: Dict[str, Any]) -> Tuple[int, Dict[str, int], list]:
    weights = policy.get("weights", {})
    reasons = {}
    tags = []

    # Basic heuristics  deterministic and auditable
    flags = set(proposal.get("flags", []) or [])
    action = (proposal.get("action") or "").lower()
    desc = (proposal.get("description") or "").lower()

    def add(tag: str, key: str, points: int):
        tags.append(tag)
        reasons[key] = reasons.get(key, 0) + points

    # Hard signals
    if "spam" in flags or "spam" in desc:
        add("spam", "tos_risk", weights.get("tos_risk", 80))
    if "imperson" in desc or "suplant" in desc:
        add("impersonation", "legal_risk", weights.get("legal_risk", 100))
    if "fraud" in flags or "fraud" in desc or "estafa" in desc:
        add("fraud", "legal_risk", weights.get("legal_risk", 100))

    # Money movement / financial risk
    if proposal.get("money_move") is True:
        add("money_move", "financial_risk", weights.get("financial_risk", 60))

    # Live trading is high-risk operationally
    if action == "trading_live":
        add("trading_live", "financial_risk", weights.get("financial_risk", 60))

    # Uncertainty placeholder (if no evidence)
    if proposal.get("evidence") in (None, "", []):
        add("low_evidence", "uncertainty", weights.get("uncertainty", 40))

    total = sum(reasons.values())
    return total, reasons, tags

def decide(proposal: Dict[str, Any]) -> Dict[str, Any]:
    constitution = _load_json(os.path.join(GOV, "constitution.json"))
    policy = _load_json(os.path.join(GOV, "ethics_policy.json"))
    tests_path = os.path.join(GOV, "ethics_tests.json")

    total, reasons, tags = score_proposal(proposal, policy)

    # Always-block / always-review tags
    always_block = set(policy.get("always_block", []))
    always_review = set(policy.get("always_review", []))

    if any(t in always_block for t in tags):
        verdict = "block"
    elif proposal.get("action") in always_review:
        verdict = "review"
    else:
        th = policy.get("thresholds", {})
        allow_max = int(th.get("allow_max_score", 25))
        block_min = int(th.get("block_min_score", 60))
        verdict = "allow" if total <= allow_max else ("block" if total >= block_min else "review")

    out = {
        "ts": datetime.utcnow().isoformat() + "Z",
        "proposal": proposal,
        "verdict": verdict,
        "score": total,
        "reasons": reasons,
        "tags": tags,
        "policy_version": policy.get("version"),
        "constitution_version": constitution.get("version")
    }

    _append_jsonl(os.path.join(LOGS, "ethics_decisions.jsonl"), out)
    return out

def run_tests() -> Dict[str, Any]:
    tests = _load_json(os.path.join(GOV, "ethics_tests.json"))
    results = []
    passed = 0
    for t in tests:
        got = decide(t["proposal"])["verdict"]
        ok = (got == t["expect"])
        results.append({"id": t["id"], "expect": t["expect"], "got": got, "pass": ok})
        if ok: passed += 1
    summary = {"passed": passed, "total": len(tests), "results": results}
    _append_jsonl(os.path.join(LOGS, "ethics_test_runs.jsonl"), {"ts": datetime.utcnow().isoformat()+"Z", **summary})
    return summary

def evolve_policy(feedback: Dict[str, Any]) -> Dict[str, Any]:
    """
    feedback example:
    {
      "change": "weights",
      "set": {"uncertainty": 55}
    }
    or
    {
      "change": "allowed_actions_add",
      "value": "publish_content"
    }
    """
    path = os.path.join(GOV, "ethics_policy.json")
    pol = _load_json(path)

    ch = (feedback.get("change") or "").lower()
    if ch == "weights" and isinstance(feedback.get("set"), dict):
        pol["weights"].update(feedback["set"])
    elif ch == "allowed_actions_add":
        v = feedback.get("value")
        if v and v not in pol.get("allowed_actions", []):
            pol["allowed_actions"].append(v)
    elif ch == "always_review_add":
        v = feedback.get("value")
        if v and v not in pol.get("always_review", []):
            pol["always_review"].append(v)
    else:
        raise ValueError("Unsupported feedback change")

    # bump patch version
    old = pol.get("version","0.1.0").split(".")
    if len(old)==3:
        old[2] = str(int(old[2]) + 1)
        pol["version"] = ".".join(old)

    with open(path, "w", encoding="utf-8-sig") as f:
        json.dump(pol, f, ensure_ascii=False, indent=2)

    _append_jsonl(os.path.join(LOGS, "ethics_policy_evolution.jsonl"), {
        "ts": datetime.utcnow().isoformat()+"Z",
        "feedback": feedback,
        "new_version": pol["version"]
    })
    return pol

