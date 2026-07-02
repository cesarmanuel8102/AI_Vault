from __future__ import annotations
import json
import time
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List

try:
    from brain_v9.config import API_ENDPOINTS, PRIMARY_KIMI_MODEL
except Exception:
    API_ENDPOINTS = {"ollama": "http://127.0.0.1:11434/api/chat"}
    PRIMARY_KIMI_MODEL = "kimi-k2.6:cloud"

FALLBACK_MODELS = ["deepseek-v4-pro:cloud", "gpt-oss:120b-cloud", "kimi-k2.5:cloud"]
FORBIDDEN_FINAL_MARKERS = ("chain-of-thought", "hidden reasoning", "private reasoning", "scratchpad")

# Repair B1 (front-brain-agent-v2-intent-floor-and-identity-preamble-repair-01):
# Deterministic Brain Agent V2 identity + capability + anti-denial preamble.
# Prepended to system_content for ALL finalizer templates so the cloud LLM
# never denies being Agent V2, never claims it has no tools/no memory as a
# system capability, and never claims broker/IBKR/real-money capability.
AGENT_V2_IDENTITY_PREAMBLE = (
    "You are Brain Agent V2 (Canonical Agent V2) running inside Brain Chat V9. "
    "Backend runtime: langgraph_parity (LangGraphParityRuntimeV2). "
    "You have real tools available: file_read, grep_search, brain_self_knowledge_lookup, "
    "capability_registry_read, semantic_retrieve, memory_structure_inspect, "
    "promotion_queue_status, semantic_memory_status, trace_inspect, repo_status_read, "
    "repo_history_read, route_probe, smoke_test_readonly, repo_file_search, repo_file_read. "
    "You have persistent semantic memory (read-only in this mode). "
    "You must NOT deny being Agent V2. You must NOT claim you have no tools or "
    "no persistent memory as a system capability. If no tools were executed IN THIS RUN, "
    "say exactly that ('no tools were executed in this run') but do NOT deny the "
    "capability itself. Never claim broker/IBKR/real-money capability - these are "
    "permanently blocked by governance. Write operations to memory or repo require "
    "explicit operator approval and are not performed automatically."
)


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


def _ollama_chat(model: str, prompt: str, timeout: int = 45, system_content: str|None = None) -> str:
    default_system = "You are Brain Agent V2 finalizer. Produce concise operational answers grounded only in provided evidence. Do not reveal chain-of-thought or private reasoning. Include summary, evidence, actions, risks/gates, and next safe action."
    body = {
        "model": model,
        "stream": False,
        "think": False,
        "messages": [
            {"role": "system", "content": system_content or default_system},
            {"role": "user", "content": prompt},
        ],
        "options": {"temperature": 0.1, "num_predict": 900},
    }
    ollama_chat_url = API_ENDPOINTS["ollama"]
    req = urllib.request.Request(ollama_chat_url, data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8", "replace"))
    content = ((data.get("message") or {}).get("content") or "").strip()
    if not content:
        raise RuntimeError("empty_provider_response")
    return content


def _structured_fallback(goal: str, mode: str, memory_hits: List[Dict[str, Any]], tool_results: List[Dict[str, Any]], reason: str) -> str:
    evidence = []
    executed_tools = []
    failed_tools = []
    blocked_tools = []
    
    for item in tool_results[:6]:
        tn = item.get('tool_name') or 'unknown_tool'
        evidence.append(f"- {tn}: ok={item.get('ok')} blocked={item.get('blocked')} approval_required={item.get('approval_required')} error={item.get('error')}")
        if item.get('ok'):
            executed_tools.append(tn)
        elif item.get('blocked'):
            blocked_tools.append(tn)
        else:
            failed_tools.append(tn)
    
    if memory_hits:
        evidence.append(f"- semantic_retrieve: {len(memory_hits)} read-only memory hit(s)")
    
    if not tool_results and not memory_hits:
        evidence.append("- No tools executed and no memory hits.")
    elif not evidence:
        evidence.append("- Tool results present but could not be summarized.")
    elif executed_tools:
        evidence.append(f"- Executed tools: {', '.join(executed_tools)}")
    if failed_tools:
        evidence.append(f"- Failed tools: {', '.join(failed_tools)}")
    if blocked_tools:
        evidence.append(f"- Blocked tools: {', '.join(blocked_tools)}")
    
    return "\n".join([
        "Summary: Brain Agent V2 completed the run with an explicit degraded finalizer fallback.",
        f"Goal: {goal}",
        f"Mode: {mode}",
        "Evidence used:",
        *evidence,
        "Actions performed: planned and executed governed read-only/approval-gated tools available for this goal.",
        "Risks/gates: no semantic/FAISS write, no trading action, write tools remain approval-gated.",
        f"Provider status: degraded fallback because {reason}.",
        "Inference boundary: Conclusions beyond the above evidence are inference, not verified fact.",
        "Next safe action: inspect trace and tool outputs; restart/check Ollama Kimi provider if Kimi synthesis is required.",
    ])


CRITICAL_FINALIZER_TOOL_NAMES = {
    "promotion_queue_status",
    "semantic_memory_status",
    "memory_structure_inspect",
    "capability_registry_read",
    "brain_self_knowledge_lookup",
}


def _select_finalizer_tool_results(tool_results: List[Dict[str, Any]], limit: int = 10) -> List[Dict[str, Any]]:
    """Keep prompt bounded without dropping the decisive evidence tool.

    Generic supporting tools can push the actual diagnostic tool past the first
    N results. If that happens, the finalizer sees the tool as executed in the
    distinction table but cannot see its payload, then hallucinates a missing
    evidence gap. Preserve critical read-only diagnostic tools explicitly.
    """
    selected = list(tool_results[:limit])
    selected_ids = {id(item) for item in selected}
    for item in tool_results[limit:]:
        if item.get("tool_name") in CRITICAL_FINALIZER_TOOL_NAMES and id(item) not in selected_ids:
            selected.append(item)
            selected_ids.add(id(item))
    return selected


def _compact_critical_tool_result(item: Dict[str, Any]) -> Any:
    """Return a small high-signal payload for known diagnostic tools."""
    if item.get("tool_name") != "promotion_queue_status":
        return item.get("result", {})

    result = item.get("result", {})
    if not isinstance(result, list):
        return result

    compact: Dict[str, Any] = {
        "tool_name": "promotion_queue_status",
        "queue_dirs": [],
    }
    for entry in result:
        if not isinstance(entry, dict):
            continue
        if "dir" in entry:
            compact["queue_dirs"].append({
                "dir": entry.get("dir"),
                "exists": entry.get("exists"),
                "entry_count": entry.get("entry_count"),
                "json_file_count": entry.get("json_file_count"),
                "dashboard_status_source": entry.get("dashboard_status_source"),
            })
        if "dashboard_status_memory_reconciliation" in entry:
            rec = entry.get("dashboard_status_memory_reconciliation") or {}
            compact["dashboard_status_memory_reconciliation"] = {
                "dashboard_route": rec.get("dashboard_route"),
                "frontend_field": rec.get("frontend_field"),
                "formula": rec.get("formula"),
                "promotion_queue_count": rec.get("promotion_queue_count"),
                "active_review_required_count": rec.get("active_review_required_count"),
                "review_required_false_count": rec.get("review_required_false_count"),
                "resolved_utc_present_count": rec.get("resolved_utc_present_count"),
                "terminal_status_counts": rec.get("terminal_status_counts"),
                "canonical_promotion_counts": rec.get("canonical_promotion_counts"),
                "pending_interpretation": rec.get("pending_interpretation"),
            }
        if "dashboard_learning_reconciliation" in entry:
            rec = entry.get("dashboard_learning_reconciliation") or {}
            compact["dashboard_learning_reconciliation"] = {
                "dashboard_route": rec.get("dashboard_route"),
                "candidate_promote_count": rec.get("candidate_promote_count"),
                "proposal_count": rec.get("proposal_count"),
                "note": rec.get("note"),
            }
    return compact


def build_finalizer_prompt(run: Dict[str, Any], memory_hits: List[Dict[str, Any]], tool_results: List[Dict[str, Any]], requested_checks: List[Dict[str, Any]]|None = None, scheduled_tools: List[str]|None = None, executed_tools: List[str]|None = None, template_override: str|None = None, recent_context: Dict[str, Any]|None = None) -> str:
    safe_results = []
    for idx, item in enumerate(_select_finalizer_tool_results(tool_results), start=1):
        result_for_prompt = (
            _compact_critical_tool_result(item)
            if item.get("tool_name") in CRITICAL_FINALIZER_TOOL_NAMES
            else item.get("result", {})
        )
        safe_results.append({
            "evidence_id": f"tool_{idx}",
            "tool_name": item.get("tool_name"),
            "ok": item.get("ok"),
            "blocked": item.get("blocked"),
            "approval_required": item.get("approval_required"),
            "error": item.get("error"),
            "result_preview": _safe_preview(result_for_prompt, 1800),
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
    }

    # Template selection
    if template_override == "direct_assistant":
        payload["required_format"] = ["Direct answer", "Concise prose", "No operational summary"]
        payload["mandatory_instruction"] = "Answer directly as a helpful assistant. Use natural, conversational prose. Do NOT use structured sections like Summary/Evidence/Actions/Risks unless the user explicitly asks for analysis. Do NOT claim tool evidence, memory evidence, or any operational tool usage."
        payload["safety_constraints"] = ["no raw chain-of-thought", "no semantic/FAISS writes", "no trading", "no tool evidence claims"]
    elif template_override == "brain_evidence":
        payload["required_format"] = ["Summary", "Brain evidence", "Actions performed", "Risks/gates", "Next safe action"]
        payload["mandatory_instruction"] = "Focus on Brain-specific evidence (front dirs, traces, ledgers). Use deterministic source data. Do NOT hallucinate tool results. Distinguish MEMORY EVIDENCE (persistent context) from LIVE TOOL EVIDENCE (current run). Label inference clearly as inference, not fact."
        payload["safety_constraints"] = ["no raw chain-of-thought", "no semantic/FAISS writes", "no trading", "write tools approval-gated", "no hallucinated tool results"]
    elif template_override == "mixed_brain_reasoning":
        payload["required_format"] = ["Reasoning", "Brain evidence", "Conclusion", "Risks/gates"]
        payload["mandatory_instruction"] = "Start with generic reasoning, then ground with Brain evidence. Distinguish what you know vs what the evidence shows. Distinguish MEMORY EVIDENCE (persistent context) from LIVE TOOL EVIDENCE (current run). Label inference clearly as inference."
        payload["safety_constraints"] = ["no raw chain-of-thought", "no semantic/FAISS writes", "no trading", "write tools approval-gated"]
    else:
        payload["required_format"] = ["Summary", "Evidence used", "Actions performed", "Risks/gates", "Next safe action"]
        payload["mandatory_instruction"] = "If tools were requested but not scheduled, say 'planner did not schedule requested tool'. If scheduled but failed, say 'tool scheduled but failed'. If executed and blocked, say 'executed and correctly blocked'. If executed and passed, say 'executed and passed'. Do NOT say tools are 'unavailable' unless the tool gateway explicitly lacks that capability. Distinguish MEMORY EVIDENCE from LIVE TOOL EVIDENCE. Label inference as inference."
        payload["safety_constraints"] = ["no raw chain-of-thought", "no semantic/FAISS writes", "no trading", "write tools approval-gated"]

    payload["tool_evidence"] = safe_results
    payload["memory_evidence"] = safe_hits
    payload["tool_distinction"] = tool_distinction

    # Inject session context summary if available
    if recent_context:
        ctx = recent_context
        ctx_lines = ["RECENT SESSION CONTEXT:"]
        if ctx.get("prev_goal"):
            ctx_lines.append(f"- Previous user asked: {ctx['prev_goal'][:120]}")
        if ctx.get("prev_route"):
            ctx_lines.append(f"- Previous route: {ctx['prev_route']}")
        if ctx.get("prev_sources"):
            ctx_lines.append(f"- Previous sources: {', '.join(ctx['prev_sources'][:5])}")
        if ctx.get("prev_answer"):
            ctx_lines.append(f"- Previous answer summary: {ctx['prev_answer'][:200]}")
        if ctx.get("is_follow_up"):
            ctx_lines.append("- Current message appears to be a FOLLOW-UP. Keep the prior topic unless the user explicitly switches subject.")
        payload["session_context"] = "\n".join(ctx_lines)
    else:
        payload["session_context"] = ""

    prompt_header = (
        "Finalize this Agent V2 run using only this evidence. "
        "Distinguish requested vs scheduled vs executed tools clearly. "
        "Do not claim tools are unavailable when they were simply not scheduled."
    )
    if payload.get("session_context"):
        prompt_header += "\nUse the recent session context below to understand references, but still distinguish current evidence from previous context."

    return prompt_header + "\n" + json.dumps(payload, ensure_ascii=False, indent=2)


def finalize_agent_run(run: Dict[str, Any], memory_hits: List[Dict[str, Any]], tool_results: List[Dict[str, Any]], requested_checks: List[Dict[str, Any]]|None = None, scheduled_tools: List[str]|None = None, executed_tools: List[str]|None = None, template_override: str|None = None, recent_context: Dict[str, Any]|None = None) -> tuple[str, Dict[str, Any]]:
    prompt = build_finalizer_prompt(run, memory_hits, tool_results, requested_checks, scheduled_tools, executed_tools, template_override, recent_context)
    meta = FinalizerMetadata(provider_attempted=[])
    started = time.perf_counter()
    models = [PRIMARY_KIMI_MODEL] + FALLBACK_MODELS
    last_error = "not_attempted"
    
    # Select system prompt based on template
    # Repair B2 (front-brain-agent-v2-intent-floor-and-identity-preamble-repair-01):
    # Prepend AGENT_V2_IDENTITY_PREAMBLE to every template so the cloud LLM
    # cannot deny being Agent V2 or claim it has no tools / no persistent memory.
    _role_specific = None
    if template_override == "direct_assistant":
        _role_specific = "You are a helpful assistant. Answer directly and naturally. Use conversational prose. Do NOT use structured sections like Summary, Evidence, Actions, Risks, or Next Safe Action unless the user explicitly asks for analysis."
    elif template_override == "brain_evidence":
        _role_specific = "You are Brain Agent V2 evidence analyst. Focus on Brain-specific evidence from front dirs, traces, and ledgers. Use deterministic source data. Do NOT hallucinate. Do NOT claim no evidence exists if evidence files were searched."
    elif template_override == "mixed_brain_reasoning":
        _role_specific = "You are Brain Agent V2 reasoning engine. Start with general concepts, then ground with Brain-specific evidence. Distinguish what you know from what the evidence shows."
    if _role_specific is None:
        system_content = AGENT_V2_IDENTITY_PREAMBLE
    else:
        system_content = AGENT_V2_IDENTITY_PREAMBLE + "\n\n" + _role_specific
    
    for model in models:
        meta.provider_attempted.append(f"ollama:{model}")
        if model == PRIMARY_KIMI_MODEL:
            meta.kimi_available = True
        try:
            answer = _ollama_chat(model, prompt, system_content=system_content)
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
