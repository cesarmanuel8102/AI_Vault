"""
Brain V9 - Post-trade hypothesis synthesis

Builds a canonical hypothesis packet from post-trade analysis plus edge/ranking
artifacts. The base layer is deterministic and always available. An optional
LLM layer adds a concise narrative synthesis when the local/chat model responds
within a short timeout.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, List

from brain_v9.config import BASE_PATH
from brain_v9.core.llm import LLMManager
from brain_v9.core.state_io import read_json, write_json
from brain_v9.trading.post_trade_analysis import build_post_trade_analysis_snapshot

STATE_PATH = BASE_PATH / "tmp_agent" / "state"
ENGINE_PATH = STATE_PATH / "strategy_engine"
POST_TRADE_PATH = ENGINE_PATH / "post_trade_analysis_latest.json"
EDGE_PATH = ENGINE_PATH / "edge_validation_latest.json"
RANKING_PATH = ENGINE_PATH / "strategy_ranking_v2_latest.json"
OUTPUT_PATH = ENGINE_PATH / "post_trade_hypotheses_latest.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _top_negative(items: List[Dict[str, Any]], key: str) -> Dict[str, Any]:
    negatives = [row for row in items if _safe_float(row.get("net_profit")) < 0]
    if not negatives:
        return {}
    negatives.sort(key=lambda row: _safe_float(row.get("net_profit")))
    best = dict(negatives[0])
    best["dimension"] = key
    return best


def _build_findings(post_trade: Dict[str, Any], edge: Dict[str, Any], ranking: Dict[str, Any]) -> List[Dict[str, Any]]:
    findings: List[Dict[str, Any]] = []
    summary = post_trade.get("summary") or {}
    edge_summary = edge.get("summary") or {}
    top_action = ranking.get("top_action")

    duplicate_count = int(summary.get("duplicate_anomaly_count", 0) or 0)
    if duplicate_count > 0:
        findings.append({
            "severity": "high",
            "type": "execution_integrity",
            "title": "Possible duplicate execution bursts detected",
            "evidence": {
                "duplicate_anomaly_count": duplicate_count,
                "next_focus": summary.get("next_focus"),
            },
            "recommended_action": "audit_duplicate_execution",
        })

    if int(edge_summary.get("validated_count", 0) or 0) == 0:
        findings.append({
            "severity": "high",
            "type": "edge_gap",
            "title": "No validated edge is currently available",
            "evidence": {
                "validated_count": edge_summary.get("validated_count", 0),
                "probation_count": edge_summary.get("probation_count", 0),
                "top_action": top_action,
            },
            "recommended_action": "keep_probation_separate_from_exploitation",
        })

    if _safe_float(summary.get("net_profit")) < 0:
        findings.append({
            "severity": "medium",
            "type": "profitability",
            "title": "Recent resolved trades remain net negative",
            "evidence": {
                "recent_resolved_trades": summary.get("recent_resolved_trades", 0),
                "net_profit": summary.get("net_profit", 0.0),
                "win_rate": summary.get("win_rate", 0.0),
            },
            "recommended_action": "reduce_lossy_contexts",
        })

    worst_strategy = _top_negative(post_trade.get("by_strategy") or [], "strategy_id")
    if worst_strategy:
        findings.append({
            "severity": "medium",
            "type": "loss_cluster",
            "title": "One strategy concentrates the recent losses",
            "evidence": worst_strategy,
            "recommended_action": "deprioritize_or_refine_strategy",
        })

    worst_venue = _top_negative(post_trade.get("by_venue") or [], "venue")
    if worst_venue:
        findings.append({
            "severity": "medium",
            "type": "venue_drag",
            "title": "One venue is dragging recent performance",
            "evidence": worst_venue,
            "recommended_action": "tighten_context_filters_for_venue",
        })

    return findings


def _build_hypotheses(post_trade: Dict[str, Any], edge: Dict[str, Any], ranking: Dict[str, Any]) -> List[Dict[str, Any]]:
    hypotheses: List[Dict[str, Any]] = []
    summary = post_trade.get("summary") or {}
    edge_summary = edge.get("summary") or {}
    probation = ranking.get("probation_candidate") or edge_summary.get("best_probation") or {}

    if int(summary.get("duplicate_anomaly_count", 0) or 0) > 0:
        hypotheses.append({
            "hypothesis_id": "hyp_audit_duplicate_execution",
            "priority": 1,
            "category": "integrity",
            "statement": "Some recent losses may be contaminated by duplicate submission bursts rather than pure signal quality.",
            "proposed_test": "Audit duplicate clusters, dedupe affected records, and retest the same context with one-trade-per-window enforcement.",
            "target_strategy_id": (post_trade.get("anomalies") or [{}])[0].get("strategy_id"),
            "expected_outcome": "Cleaner attribution between execution quality and strategy quality.",
        })

    if int(edge_summary.get("validated_count", 0) or 0) == 0 and probation:
        hypotheses.append({
            "hypothesis_id": "hyp_promising_probation_needs_sample",
            "priority": 2,
            "category": "sampling",
            "statement": f"The best current candidate `{probation.get('strategy_id', 'unknown')}` may still be noise because its edge has not survived enough forward sample.",
            "proposed_test": "Keep fixed-size probation trades, cap batch size, and require forward validation before exploitation.",
            "target_strategy_id": probation.get("strategy_id"),
            "expected_outcome": "Either the candidate stabilizes into forward_validation or is refuted quickly.",
        })

    lossy_context = _top_negative(post_trade.get("by_symbol") or [], "symbol")
    if lossy_context:
        hypotheses.append({
            "hypothesis_id": "hyp_context_filter_needed",
            "priority": 3,
            "category": "context",
            "statement": f"The context around `{lossy_context.get('symbol', 'unknown')}` is net negative and likely needs tighter filters rather than more volume.",
            "proposed_test": "Restrict execution to higher-confidence regime/setup windows for that symbol and compare forward results.",
            "target_symbol": lossy_context.get("symbol"),
            "expected_outcome": "Reduced drag from the noisiest context bucket.",
        })

    return hypotheses[:5]


def build_post_trade_hypothesis_base(force_refresh_analysis: bool = False) -> Dict[str, Any]:
    if force_refresh_analysis:
        post_trade = build_post_trade_analysis_snapshot()
    else:
        post_trade = read_json(POST_TRADE_PATH, {})
        if not post_trade:
            post_trade = build_post_trade_analysis_snapshot()

    edge = read_json(EDGE_PATH, {})
    ranking = read_json(RANKING_PATH, {})

    findings = _build_findings(post_trade, edge, ranking)
    hypotheses = _build_hypotheses(post_trade, edge, ranking)

    top_finding = findings[0] if findings else {}
    payload = {
        "schema_version": "post_trade_hypotheses_v1",
        "updated_utc": _utc_now(),
        "base_only": True,
        "summary": {
            "top_finding": top_finding.get("title"),
            "next_focus": (post_trade.get("summary") or {}).get("next_focus"),
            "finding_count": len(findings),
            "hypothesis_count": len(hypotheses),
            "validated_edge_count": (edge.get("summary") or {}).get("validated_count", 0),
            "probation_count": (edge.get("summary") or {}).get("probation_count", 0),
        },
        "findings": findings,
        "suggested_hypotheses": hypotheses,
        "post_trade_summary": post_trade.get("summary") or {},
        "ranking_summary": {
            "top_action": ranking.get("top_action"),
            "probation_candidate": (ranking.get("probation_candidate") or {}).get("strategy_id"),
            "exploit_candidate": (ranking.get("exploit_candidate") or {}).get("strategy_id"),
        },
        "llm_summary": {
            "available": False,
            "model_used": None,
            "text": None,
            "error": None,
        },
    }
    return payload


async def build_post_trade_hypothesis_snapshot(
    include_llm: bool = True,
    force_refresh_analysis: bool = False,
) -> Dict[str, Any]:
    payload = build_post_trade_hypothesis_base(force_refresh_analysis=force_refresh_analysis)

    if include_llm:
        llm = LLMManager()
        findings = payload.get("findings") or []
        hypotheses = payload.get("suggested_hypotheses") or []
        summary = payload.get("post_trade_summary") or {}
        prompt = (
            "Analiza este paquete post-trade del Brain V9 y produce una sintesis breve en espanol.\n\n"
            f"Resumen canonico: {summary}\n"
            f"Hallazgos: {findings}\n"
            f"Hipotesis sugeridas: {hypotheses}\n\n"
            "Responde en 3 secciones cortas:\n"
            "1. Que esta pasando realmente\n"
            "2. Riesgo principal\n"
            "3. Proximo experimento mas util\n"
            "No inventes datos y no contradigas la evidencia canonica."
        )
        try:
            result = await asyncio.wait_for(
                llm.query([{"role": "user", "content": prompt}], model_priority="chat"),
                timeout=25,
            )
            if result.get("success") and result.get("content"):
                payload["llm_summary"] = {
                    "available": True,
                    "model_used": result.get("model_used") or result.get("model"),
                    "text": result.get("content"),
                    "error": None,
                }
                payload["base_only"] = False
            else:
                payload["llm_summary"]["error"] = result.get("error", "llm_failed")
        except Exception as exc:
            payload["llm_summary"]["error"] = str(exc) or exc.__class__.__name__

    write_json(OUTPUT_PATH, payload)
    return payload


def read_post_trade_hypothesis_snapshot() -> Dict[str, Any]:
    payload = read_json(OUTPUT_PATH, {})
    if payload:
        return payload
    payload = build_post_trade_hypothesis_base(force_refresh_analysis=False)
    write_json(OUTPUT_PATH, payload)
    return payload
