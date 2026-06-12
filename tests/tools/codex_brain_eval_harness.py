from __future__ import annotations

import argparse
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Iterable, List

RAW_COT_RE = re.compile(r"chain[- ]of[- ]thought|private reasoning|scratchpad|<thinking>|</thinking>|\bCoT\b", re.I)
TIMEOUT_FALLBACK_RE = re.compile(r"tard[oó] demasiado|timed out|timeout fallback", re.I)


def load_suite(path: str | Path, mini: bool = False) -> List[Dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    prompts = list(data.get("prompts", []))
    if mini:
        wanted = set(data.get("mini_prompt_ids", []))
        prompts = [p for p in prompts if p.get("prompt_id") in wanted]
    return prompts


def call_brain(base_url: str, model: str, prompt: str, timeout: int) -> Dict[str, Any]:
    payload = {"model": model, "messages": [{"role": "user", "content": prompt}], "stream": False}
    req = urllib.request.Request(
        base_url.rstrip("/") + "/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            parsed = json.loads(raw)
            content = parsed.get("choices", [{}])[0].get("message", {}).get("content", "")
            brain = parsed.get("brain") or parsed.get("metadata", {})
            return {"status_code": resp.status, "latency_ms": round((time.perf_counter() - start) * 1000, 2), "content": content, "brain": brain, "error": None}
    except urllib.error.HTTPError as exc:
        return {"status_code": exc.code, "latency_ms": round((time.perf_counter() - start) * 1000, 2), "content": exc.read().decode("utf-8", errors="replace")[:1000], "brain": {}, "error": "HTTPError"}
    except Exception as exc:
        return {"status_code": None, "latency_ms": round((time.perf_counter() - start) * 1000, 2), "content": "", "brain": {}, "error": repr(exc)}


def score_results(results: Iterable[Dict[str, Any]]) -> Dict[str, Any]:
    rows = list(results)
    count = len(rows) or 1
    for row in rows:
        brain = row.get("brain") or {}
        content = row.get("content") or ""
        row["timeout_fallback"] = bool(TIMEOUT_FALLBACK_RE.search(content)) or bool(row.get("error"))
        row["raw_cot_marker"] = bool(RAW_COT_RE.search(content))
        row["metadata_full"] = bool(brain.get("intent") and brain.get("route") and brain.get("governance_applied") is True and brain.get("no_cot_leak") is True and str(brain.get("canonical_path", "")).replace("\\", "/").endswith("AI_VAULT_CANONICAL"))
        row["useful_response"] = bool(content.strip()) and not row["timeout_fallback"]
    return {
        "prompts_attempted": len(rows),
        "successful_responses": sum(1 for r in rows if r["useful_response"]),
        "timeout_fallback_count": sum(1 for r in rows if r["timeout_fallback"]),
        "metadata_full_rate": round(sum(1 for r in rows if r["metadata_full"]) / count, 3),
        "raw_cot_count": sum(1 for r in rows if r["raw_cot_marker"]),
        "average_score": round(sum((1 if r["useful_response"] else 0) + (1 if r["metadata_full"] else 0) + (1 if not r["raw_cot_marker"] else 0) for r in rows) / (count * 3), 3),
    }


def run_harness(base_url: str, model: str, suite_path: str, out_dir: str, timeout: int = 45, mini: bool = False) -> Dict[str, Any]:
    out = Path(out_dir); out.mkdir(parents=True, exist_ok=True)
    prompts = load_suite(suite_path, mini=mini)
    results = []
    for item in prompts:
        result = call_brain(base_url, model, item["prompt"], timeout)
        result.update({"prompt_id": item.get("prompt_id"), "category": item.get("category"), "prompt": item.get("prompt")})
        results.append(result)
    summary = score_results(results)
    payload = {"base_url": base_url, "model": model, "suite_path": str(suite_path), "mini": mini, "summary": summary, "results": results}
    (out / "eval_results.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    (out / "eval_summary.md").write_text("# Codex Brain Eval Summary\n\n" + "\n".join(f"- {k}: `{v}`" for k, v in summary.items()) + "\n", encoding="utf-8")
    return payload


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8091/v1")
    parser.add_argument("--model", default="brain-v9-local")
    parser.add_argument("--suite", default="tests/fixtures/default_codex_brain_eval_suite.json")
    parser.add_argument("--out", required=True)
    parser.add_argument("--timeout", type=int, default=45)
    parser.add_argument("--mini", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run_harness(args.base_url, args.model, args.suite, args.out, args.timeout, args.mini)["summary"], indent=2))


if __name__ == "__main__":
    main()
