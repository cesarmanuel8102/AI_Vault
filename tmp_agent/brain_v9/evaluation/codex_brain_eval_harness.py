from __future__ import annotations

import argparse
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

RAW_COT_RE = re.compile(r"raw_chain_of_thought|chain[- ]of[- ]thought|scratchpad|<thinking>|</thinking>|\bCoT\b", re.I)
TIMEOUT_FALLBACK_RE = re.compile(r"tard[oó] demasiado|timed out|timeout fallback|fallback determin[ií]stico|llm lento|no disponible", re.I)


def load_suite(path: str | Path, max_prompts: Optional[int] = None) -> List[Dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    raw_prompts = list(data.get("prompts", []))
    prompts: List[Dict[str, Any]] = []
    for idx, item in enumerate(raw_prompts):
        prompt_text = item.get("prompt") or item.get("query") or item.get("content")
        if not prompt_text:
            continue
        prompts.append(
            {
                "prompt_id": item.get("prompt_id") or item.get("id") or f"prompt_{idx:03d}",
                "category": item.get("category") or data.get("pack_id") or "general",
                "prompt": prompt_text,
                "expected": item.get("must_include") or item.get("expected") or [],
            }
        )
    return prompts[:max_prompts] if max_prompts else prompts


def extract_brain_metadata(response: Dict[str, Any]) -> Dict[str, Any]:
    choice_meta = response.get("choices", [{}])[0].get("message", {}).get("metadata") or {}
    return response.get("brain") or response.get("brain_metadata") or response.get("metadata") or choice_meta or {}


def call_brain(base_url: str, model: str, prompt: str, timeout: int) -> Dict[str, Any]:
    payload = {"model": model, "messages": [{"role": "user", "content": prompt}], "stream": False}
    req = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            parsed = json.loads(resp.read().decode("utf-8", errors="replace"))
            content = parsed.get("choices", [{}])[0].get("message", {}).get("content", "")
            return {
                "status_code": resp.status,
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
                "content": content,
                "brain": extract_brain_metadata(parsed),
                "raw_object": parsed.get("object"),
                "error": None,
            }
    except urllib.error.HTTPError as exc:
        return {"status_code": exc.code, "latency_ms": round((time.perf_counter() - started) * 1000, 2), "content": exc.read().decode("utf-8", errors="replace")[:1000], "brain": {}, "error": "HTTPError"}
    except Exception as exc:
        return {"status_code": None, "latency_ms": round((time.perf_counter() - started) * 1000, 2), "content": "", "brain": {}, "error": repr(exc)}


def classify_row(row: Dict[str, Any]) -> Dict[str, Any]:
    content = row.get("content") or ""
    brain = row.get("brain") or {}
    fallback_used = bool(row.get("error")) or bool(TIMEOUT_FALLBACK_RE.search(content))
    raw_cot = bool(RAW_COT_RE.search(content))
    metadata_full = bool(
        brain.get("intent")
        and brain.get("route")
        and brain.get("governance_applied") is True
        and brain.get("no_cot_leak") is True
        and str(brain.get("canonical_path", "")).replace("\\", "/").endswith("AI_VAULT_CANONICAL")
    )
    row.update(
        {
            "fallback_used": fallback_used,
            "fallback_reason": "timeout_or_deterministic_fallback" if fallback_used else None,
            "timeout_ms": row.get("latency_ms") if fallback_used else None,
            "model_attempted": brain.get("model") or brain.get("adapter") or "brain-v9-local",
            "recovery_suggestion": "Use shorter prompt, inspect local LLM health, or rerun with higher timeout." if fallback_used else None,
            "raw_cot_marker": raw_cot,
            "metadata_full": metadata_full,
            "useful_response": bool(content.strip()) and not fallback_used and not raw_cot,
        }
    )
    return row


def score_results(results: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    rows = [classify_row(dict(row)) for row in results]
    count = len(rows) or 1
    categories = sorted({row.get("category") or "general" for row in rows})
    domain_scores = {}
    for category in categories:
        subset = [row for row in rows if (row.get("category") or "general") == category]
        denom = len(subset) or 1
        domain_scores[category] = round(sum(1 for row in subset if row["useful_response"]) / denom, 3)
    return {
        "prompts_attempted": len(rows),
        "successful_responses": sum(1 for row in rows if row["useful_response"]),
        "timeout_fallback_count": sum(1 for row in rows if row["fallback_used"]),
        "metadata_full_rate": round(sum(1 for row in rows if row["metadata_full"]) / count, 3),
        "no_cot_rate": round(sum(1 for row in rows if not row["raw_cot_marker"]) / count, 3),
        "raw_cot_count": sum(1 for row in rows if row["raw_cot_marker"]),
        "average_score": round(sum((1 if row["useful_response"] else 0) + (1 if row["metadata_full"] else 0) + (1 if not row["raw_cot_marker"] else 0) for row in rows) / (count * 3), 3),
        "domain_scores": domain_scores,
    }


def run_harness(base_url: str, model: str, suite_path: str, out_dir: str, timeout: int = 45, max_prompts: Optional[int] = None, compact: bool = False) -> Dict[str, Any]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    prompts = load_suite(suite_path, max_prompts=max_prompts)
    results = []
    for item in prompts:
        result = call_brain(base_url, model, item["prompt"], timeout)
        result.update({"prompt_id": item["prompt_id"], "category": item["category"], "prompt": item["prompt"]})
        results.append(classify_row(result))
    summary = score_results(results)
    payload = {"base_url": base_url, "model": model, "suite_path": str(suite_path), "summary": summary, "results": results if not compact else []}
    (out / "eval_results.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "eval_summary.md").write_text("# Codex Brain Eval Summary\n\n" + "\n".join(f"- {k}: `{v}`" for k, v in summary.items()) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8091/v1")
    parser.add_argument("--model", default="brain-v9-local")
    parser.add_argument("--suite", default="tmp_agent/brain_v9/evaluation/default_codex_brain_eval_suite.json")
    parser.add_argument("--out", required=True)
    parser.add_argument("--timeout", type=int, default=45)
    parser.add_argument("--max-prompts", type=int, default=None)
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run_harness(args.base_url, args.model, args.suite, args.out, args.timeout, args.max_prompts, args.compact)["summary"], indent=2))


if __name__ == "__main__":
    main()
