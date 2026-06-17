from __future__ import annotations
import json
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List

PRIMARY_KIMI_MODEL = "kimi-k2.6:cloud"
FALLBACK_MODELS = ["deepseek-v4-pro:cloud", "gpt-oss:120b-cloud", "kimi-k2.5:cloud"]
OLLAMA_CHAT_URL = "http://127.0.0.1:11434/api/chat"
FORBIDDEN_FINAL_MARKERS = ("chain-of-thought", "hidden reasoning", "private reasoning", "scratchpad")


@dataclass
class FinalizerMetadata:
    provider_attempted: List[str] = field(default_factory=list)
    provider_used: str = "structured_operational_finalizer"
    model_used: str = "structured_operational_finalizer"
    provider_degraded: bool = True
    fallback_reason: str = "not_attempted"
    latency_ms: int = 0
    kimi_available: bool = False
    raw_cot_exposed: bool = False


def _safe_preview(value: Any, limit: int = 1800) -> str:
    text = json.dumps(value, ensure_ascii=False, default=str) if not isinstance(value, str) else value
    for marker in FORBIDDEN_FINAL_MARKERS:
        text = text.replace(marker, "[redacted-marker]")
    return text[:limit]


def _ollama_chat(model: str, prompt: str, timeout: int = 45) -> str:
    body = {
        "model": model,
        "stream": False,
        "think": False,
        "messages": [
            {"role": "system", "content": "You are Brain Agent V2 finalizer. Produce concise operational answers grounded only in provided evidence. Do not reveal chain-of-thought or private reasoning. Include summary, evidence, actions, risks/gates, and next safe action."},
            {"role": "user", "content": prompt},
        ],
        "options": {"temperature": 0.1, "num_predict": 900},
    }
    req = urllib.request.Request(OLLAMA_CHAT_URL, data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8", "replace"))
    content = ((data.get("message") or {}).get("content") or "").strip()
    if not content:
        raise RuntimeError("empty_provider_response")
    return content


def _structured_fallback(goal: str, mode: str, memory_hits: List[Dict[str, Any]], tool_results: List[Dict[str, Any]], reason: str) -> str:
    evidence = []
    for item in tool_results[:6]:
        evidence.append(f"- {item.get('tool_name')}: ok={item.get('ok')} blocked={item.get('blocked')} approval_required={item.get('approval_required')} error={item.get('error')}")
    if memory_hits:
        evidence.append(f"- semantic_retrieve: {len(memory_hits)} read-only memory hit(s)")
    if not evidence:
        evidence.append("- No tool evidence produced beyond run metadata.")
    return "\n".join([
        "Summary: Brain Agent V2 completed the run with an explicit degraded finalizer fallback.",
        f"Goal: {goal}",
        f"Mode: {mode}",
        "Evidence used:",
        *evidence,
        "Actions performed: planned and executed governed read-only/approval-gated tools available for this goal.",
        "Risks/gates: no semantic/FAISS write, no trading action, write tools remain approval-gated.",
        f"Provider status: degraded fallback because {reason}.",
        "Next safe action: inspect trace and tool outputs; restart/check Ollama Kimi provider if Kimi synthesis is required.",
    ])


def build_finalizer_prompt(run: Dict[str, Any], memory_hits: List[Dict[str, Any]], tool_results: List[Dict[str, Any]], requested_checks: List[Dict[str, Any]]|None = None, scheduled_tools: List[str]|None = None, executed_tools: List[str]|None = None) -> str:
    safe_results = []
    for idx, item in enumerate(tool_results[:10], start=1):
        safe_results.append({
            "evidence_id": f"tool_{idx}",
            "tool_name": item.get("tool_name"),
            "ok": item.get("ok"),
            "blocked": item.get("blocked"),
            "approval_required": item.get("approval_required"),
            "error": item.get("error"),
            "result_preview": _safe_preview(item.get("result", {}), 900),
        })
    safe_hits = []
    for idx, hit in enumerate(memory_hits[:6], start=1):
        safe_hits.append({"evidence_id": f"memory_{idx}", "preview": _safe_preview(hit, 700)})
    # Build requested/scheduled/executed distinction
    tool_distinction = {}
    if requested_checks:
        for check in requested_checks:
            tool_name = check.get("tool_name")
            if tool_name:
                tool_distinction[tool_name] = {
                    "requested": True,
                    "scheduled": tool_name in (scheduled_tools or []),
                    "executed": tool_name in (executed_tools or []),
                    "description": check.get("description", ""),
                }
    for tool_name in (scheduled_tools or []):
        if tool_name not in tool_distinction:
            tool_distinction[tool_name] = {"requested": False, "scheduled": True, "executed": tool_name in (executed_tools or [])}
    payload = {
        "goal": run.get("goal"),
        "mode": run.get("mode"),
        "classification": run.get("classification"),
        "tool_evidence": safe_results,
        "memory_evidence": safe_hits,
        "tool_distinction": tool_distinction,
        "safety_constraints": ["no raw chain-of-thought", "no semantic/FAISS writes", "no trading", "write tools approval-gated"],
        "required_format": ["Summary", "Evidence used", "Actions performed", "Risks/gates", "Next safe action"],
        "mandatory_instruction": "If tools were requested but not scheduled, say 'planner did not schedule requested tool'. If scheduled but failed, say 'tool scheduled but failed'. If executed and blocked, say 'executed and correctly blocked'. If executed and passed, say 'executed and passed'. Do NOT say tools are 'unavailable' unless the tool gateway explicitly lacks that capability.",
    }
    return "Finalize this Agent V2 run using only this evidence. Distinguish requested vs scheduled vs executed tools clearly. Do not claim tools are unavailable when they were simply not scheduled.\n" + json.dumps(payload, ensure_ascii=False, indent=2)


def finalize_agent_run(run: Dict[str, Any], memory_hits: List[Dict[str, Any]], tool_results: List[Dict[str, Any]], requested_checks: List[Dict[str, Any]]|None = None, scheduled_tools: List[str]|None = None, executed_tools: List[str]|None = None) -> tuple[str, Dict[str, Any]]:
    prompt = build_finalizer_prompt(run, memory_hits, tool_results, requested_checks, scheduled_tools, executed_tools)
    meta = FinalizerMetadata(provider_attempted=[])
    started = time.perf_counter()
    models = [PRIMARY_KIMI_MODEL] + FALLBACK_MODELS
    last_error = "not_attempted"
    for model in models:
        meta.provider_attempted.append(f"ollama:{model}")
        if model == PRIMARY_KIMI_MODEL:
            meta.kimi_available = True
        try:
            answer = _ollama_chat(model, prompt)
            lower = answer.lower()
            meta.raw_cot_exposed = any(marker in lower for marker in FORBIDDEN_FINAL_MARKERS)
            if meta.raw_cot_exposed:
                raise RuntimeError("provider_output_raw_cot_marker_blocked")
            meta.provider_used = "ollama_cloud"
            meta.model_used = model
            meta.provider_degraded = model != PRIMARY_KIMI_MODEL
            meta.fallback_reason = "none" if model == PRIMARY_KIMI_MODEL else f"primary_failed:{last_error}"
            meta.latency_ms = int((time.perf_counter() - started) * 1000)
            return answer.strip(), meta.__dict__
        except Exception as exc:
            last_error = str(exc)[:220]
            continue
    meta.provider_used = "structured_operational_finalizer"
    meta.model_used = "structured_operational_finalizer"
    meta.provider_degraded = True
    meta.fallback_reason = last_error
    meta.latency_ms = int((time.perf_counter() - started) * 1000)
    answer = _structured_fallback(str(run.get("goal", "")), str(run.get("mode", "read_only")), memory_hits, tool_results, last_error)
    return answer, meta.__dict__
