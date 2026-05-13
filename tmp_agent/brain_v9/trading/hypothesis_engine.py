"""
Brain V9 - Hypothesis engine
Evalua hipotesis ligadas a estrategias usando scorecards.
"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from brain_v9.config import BASE_PATH
from brain_v9.core.state_io import write_json

STATE_PATH = BASE_PATH / "tmp_agent" / "state"
ENGINE_PATH = STATE_PATH / "strategy_engine"
ENGINE_PATH.mkdir(parents=True, exist_ok=True)
HYP_RESULTS_PATH = ENGINE_PATH / "hypothesis_results.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def evaluate_hypotheses(hypotheses: List[Dict], scorecards: Dict[str, Dict]) -> Dict:
    results = []
    for hyp in hypotheses:
        strategy_id = hyp.get("strategy_id") or (hyp.get("linked_strategies") or [None])[0]
        card = scorecards.get(strategy_id, {})
        resolved = int(card.get("entries_resolved", 0) or 0)
        expectancy = float(card.get("expectancy", 0.0) or 0.0)
        sample_quality = float(card.get("sample_quality", 0.0) or 0.0)
        if resolved == 0:
            status = "queued"
            result = "no_sample"
        elif sample_quality < 1.0:
            status = "in_test"
            result = "insufficient_sample"
        elif expectancy > 0:
            status = "pass"
            result = "positive_expectancy"
        elif expectancy < 0:
            status = "fail"
            result = "negative_expectancy"
        else:
            status = "inconclusive"
            result = "flat_expectancy"
        results.append({
            "hypothesis_id": hyp.get("id"),
            "strategy_id": strategy_id,
            "statement": hyp.get("objective") or hyp.get("statement"),
            "success_metric": hyp.get("success_metric"),
            "entries_resolved": resolved,
            "sample_quality": sample_quality,
            "expectancy": expectancy,
            "status": status,
            "result": result,
        })

    payload = {
        "schema_version": "hypothesis_results_v1",
        "updated_utc": _utc_now(),
        "results": results,
    }
    write_json(HYP_RESULTS_PATH, payload)
    return payload
