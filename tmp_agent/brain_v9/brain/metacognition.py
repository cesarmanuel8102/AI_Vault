"""
Visible metacognition layer for Brain V9.

This module does not expose private chain-of-thought. It produces an auditable
preflight/checklist/confidence layer and a lightweight claim-risk audit.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

from brain_v9.config import STATE_PATH

STATUS_PATH = STATE_PATH / "metacognition_status_latest.json"
_NUMBER_RE = re.compile(r"(?:\b\d{1,4}(?:[.,]\d+)?%?\b|\$\s?\d+(?:[.,]\d+)?)")
_DATE_RE = re.compile(r"\b(?:20\d{2}|19\d{2})[-/]\d{1,2}[-/]\d{1,2}\b|\b(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre|january|february|march|april|may|june|july|august|september|october|november|december)\b", re.IGNORECASE)
_RISKY_WORD_RE = re.compile(r"\b(completado|validado|paso|pasó|fallo|falló|profit|return|retorno|drawdown|backtest|live|deploy|running|healthy|latest|ultimo|último|precio|costo|hoy|ayer|mañana)\b", re.IGNORECASE)
_REMOTE_RE = re.compile(r"\b(qc|quantconnect|ibkr|interactive brokers|gmail|google|api|broker|prop firm|tradeify|topstep|apex|myfundedfutures)\b", re.IGNORECASE)
_CODE_RE = re.compile(r"\b(codigo|código|archivo|python|endpoint|funcion|función|clase|import|compile|test|deploy)\b", re.IGNORECASE)


def build_visible_preflight(task: str, tools_available: Optional[Iterable[str]] = None, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    tools = sorted(set(tools_available or []))
    lower = (task or "").lower()
    task_type = "general"
    if _REMOTE_RE.search(task or ""):
        task_type = "remote_api_or_trading"
    elif _CODE_RE.search(task or ""):
        task_type = "code_system"
    elif len(lower.split()) > 20:
        task_type = "complex_analysis"

    likely_tools = []
    for candidate in (
        "grep_codebase", "read_file", "search_files", "get_system_info",
        "semantic_memory_search", "get_technical_introspection", "audit_claims",
        "run_command", "check_http_service",
    ):
        if candidate in tools:
            likely_tools.append(candidate)

    evidence_required = bool(_REMOTE_RE.search(task or "") or _NUMBER_RE.search(task or "") or _RISKY_WORD_RE.search(task or ""))
    risk_flags: List[str] = []
    if _REMOTE_RE.search(task or ""):
        risk_flags.append("datos_remotos_o_temporalmente_inestables_requieren_verificacion")
    if "live" in lower or "deploy" in lower:
        risk_flags.append("operacion_live_requiere_estado_actual_y_gates")
    if "trading" in lower or "fondeo" in lower or "broker" in lower:
        risk_flags.append("dominio_financiero_requiere_metricas_y_no_asumir")
    if _CODE_RE.search(task or ""):
        risk_flags.append("cambios_de_codigo_requieren_compilacion_o_pruebas")

    checks = [
        "verificar_tools_disponibles",
        "recuperar_memoria_semantica_relevante",
        "buscar_evidencia_local_o_remota_antes_de_afirmar",
        "chequear_contradicciones_con_resultados_previos",
        "estimar_confianza_y_reportar_limitaciones",
    ]
    confidence_start = 0.72
    if evidence_required:
        confidence_start -= 0.12
    if likely_tools:
        confidence_start += 0.08
    confidence_start = max(0.35, min(0.9, confidence_start))

    return {
        "schema_version": "visible_metacognition_preflight_v1",
        "task_type": task_type,
        "evidence_required": evidence_required,
        "checks": checks,
        "likely_tools": likely_tools,
        "risk_flags": risk_flags,
        "confidence_start": round(confidence_start, 2),
        "private_reasoning_policy": "No exponer cadena de pensamiento; mostrar solo auditoria, plan, evidencias y confianza.",
        "created_utc": _utc_now(),
    }


def audit_response_claims(text: str, evidence: Optional[Iterable[str] | str] = None) -> Dict[str, Any]:
    content = text or ""
    evidence_text = ""
    if isinstance(evidence, str):
        evidence_text = evidence
    elif evidence:
        evidence_text = "\n".join(str(x) for x in evidence)

    risky_spans = []
    for rx, kind in ((_NUMBER_RE, "number_or_money"), (_DATE_RE, "date"), (_RISKY_WORD_RE, "state_or_metric_claim")):
        for m in rx.finditer(content):
            value = m.group(0)
            risky_spans.append({"kind": kind, "value": value[:80], "start": m.start(), "end": m.end()})

    evidence_provided = bool(evidence_text.strip())
    has_remote_claims = bool(_REMOTE_RE.search(content))
    has_metrics = bool(_NUMBER_RE.search(content))
    risk_score = 0.15
    if risky_spans:
        risk_score += min(0.45, len(risky_spans) * 0.04)
    if has_remote_claims:
        risk_score += 0.2
    if has_metrics:
        risk_score += 0.15
    if evidence_provided:
        risk_score -= 0.25
    risk_score = max(0.0, min(1.0, risk_score))
    if risk_score >= 0.65:
        label = "high"
    elif risk_score >= 0.35:
        label = "medium"
    else:
        label = "low"

    return {
        "schema_version": "claim_audit_v1",
        "hallucination_risk": label,
        "risk_score": round(risk_score, 2),
        "evidence_provided": evidence_provided,
        "risky_claims_detected": len(risky_spans),
        "risky_claim_samples": risky_spans[:12],
        "note": "Proxy heuristico; no usa perplexity/logprobs porque el stack actual no expone esa senal.",
        "created_utc": _utc_now(),
    }


def build_metacognition_status() -> Dict[str, Any]:
    status = {
        "ok": True,
        "schema_version": "metacognition_status_v1",
        "visible_metacognition": {
            "enabled": True,
            "components": ["preflight", "evidence_requirement", "contradiction_check_placeholder", "confidence_score", "claim_audit"],
            "private_reasoning_policy": "No se expone razonamiento privado paso a paso.",
        },
        "hallucination_detection": {
            "enabled": True,
            "method": "claim_risk_proxy",
            "perplexity_scores": False,
            "reason": "El proveedor LLM actual no entrega logprobs/perplexity de forma uniforme.",
        },
        "status_path": str(STATUS_PATH),
        "updated_utc": _utc_now(),
    }
    STATUS_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATUS_PATH.write_text(json.dumps(status, ensure_ascii=False, indent=2), encoding="utf-8")
    return status


def read_metacognition_status() -> Dict[str, Any]:
    try:
        if STATUS_PATH.exists():
            return json.loads(STATUS_PATH.read_text(encoding="utf-8"))
    except Exception:
        pass
    return build_metacognition_status()


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
