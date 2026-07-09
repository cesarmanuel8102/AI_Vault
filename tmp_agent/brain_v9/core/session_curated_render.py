"""
brain_v9.core.session_curated_render
====================================

B7-STRANGLER-06A: Curated lookup renderers, parsers, and utility helpers
extracted from BrainSession.

Contract:
  - No imports from brain_v9.core.session (no circular dependency).
  - No I/O, no network, no subprocess, no config.
  - No memory/FAISS writes.
  - No trading/QC/IBKR.
  - Functions are pure or receive explicit DI for providers.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

__all__ = [
    "format_curated_lookup_chat_response",
    "parse_curated_lookup_command",
    "run_curated_lookup_command",
    "get_curated_ingestion_response",
    "utility_score",
    "utility_blockers",
]


def utility_score(utility: Dict) -> object:
    """Extract utility score from a utility dict."""
    return utility.get("u_score", utility.get("u_proxy_score", "N/A"))


def utility_blockers(utility: Dict) -> List[str]:
    """Extract blockers from a utility dict's promotion_gate."""
    gate = utility.get("promotion_gate") or {}
    blockers = gate.get("blockers")
    return blockers if isinstance(blockers, list) else []


def format_curated_lookup_chat_response(
    query: str,
    lookup_result: Any,
    warnings: Optional[List[str]] = None,
    error: Optional[str] = None,
) -> str:
    """Format curated lookup results into a human-readable chat response.

    Pure function extracted from BrainSession._format_curated_lookup_chat_response.
    Uses duck-typing on lookup_result (getattr for .results, .total_available, etc.).
    """
    warnings = list(warnings or [])
    query = (query or "").strip()
    lines = ["[verified_curated_readonly]", ""]

    if not query:
        lines.append("Consulta vac\u00eda. Usa: busca en conocimiento curado: <tema>")
    elif error:
        lines.append("No pude consultar el \u00edndice curated read-only de forma segura.")
        lines.append(f"Motivo: {error}")
        lines.append("No se ejecut\u00f3 fallback LLM ni escritura de memoria.")
    else:
        results = list(getattr(lookup_result, "results", ()) or ())
        total_available = getattr(lookup_result, "total_available", len(results))
        filtered_out = getattr(lookup_result, "filtered_out", 0)
        if not results:
            lines.append(f"No encontr\u00e9 resultados curados para: \"{query}\".")
            lines.append("")
            lines.append("Esto no activa LLM fallback ni b\u00fasqueda externa.")
        else:
            lines.append(f"Encontr\u00e9 {len(results)} resultados curados para: \"{query}\"")
            lines.append(f"Total disponible: {total_available}; filtrados: {filtered_out}")
            lines.append("")
            for idx, item in enumerate(results, 1):
                text = (getattr(item, "text", "") or "").strip()
                snippet = text[:360] + ("..." if len(text) > 360 else "")
                evidence_refs = list(getattr(item, "evidence_refs", ()) or ())
                lines.append(f"{idx}. Resumen:")
                lines.append(f"   {snippet or '(sin texto)'}")
                lines.append("   Fuente:")
                lines.append(f"   source_id: {getattr(item, 'source_id', 'unknown')}")
                lines.append("   Evidencia:")
                if evidence_refs:
                    for ref in evidence_refs[:5]:
                        lines.append(f"   - {ref}")
                else:
                    lines.append("   - unknown")
                lines.append("   Scores:")
                lines.append(f"   validation_score: {getattr(item, 'validation_score', 'unknown')}")
                lines.append(f"   curation_score: {getattr(item, 'curation_score', 'unknown')}")
                lines.append(f"   trust_score: {getattr(item, 'trust_score', 'unknown')}")
                lines.append(f"   freshness: {getattr(item, 'freshness', 'unknown')}")
                lines.append(f"   dry_run_id: {getattr(item, 'dry_run_id', 'unknown')}")
                lines.append("")

    if warnings:
        lines.append("Warnings:")
        for warning in warnings:
            lines.append(f"- {warning}")
        lines.append("")

    lines.append("Limitaci\u00f3n:")
    lines.append("Esto es conocimiento curado read-only. No est\u00e1 promovido a memoria real.")
    return "\n".join(lines).strip()


def parse_curated_lookup_command(message: str) -> Optional[Dict]:
    """Parse explicit read-only curated-knowledge chat commands.

    Pure function extracted from BrainSession._parse_curated_lookup_command.
    Returns None if the message doesn't match curated lookup triggers.
    """
    raw = (message or "").strip()
    if not raw:
        return None

    lowered = raw.lower()
    colon_trigger = "busca en conocimiento curado:"
    prefix_triggers = (
        "que aprendiste sobre",
        "qu\u00e9 aprendiste sobre",
        "usa curated knowledge para responder",
        "usa conocimiento curado para responder",
    )

    query: Optional[str] = None
    if lowered.startswith(colon_trigger):
        query = raw.split(":", 1)[1].strip() if ":" in raw else ""
    else:
        for trigger in prefix_triggers:
            if lowered.startswith(trigger):
                query = raw[len(trigger):].strip()
                break

    if query is None:
        return None

    return {
        "query": query[:500].strip(),
        "top_k": 5,
    }


def run_curated_lookup_command(
    query: str,
    top_k: int = 5,
    *,
    format_func=format_curated_lookup_chat_response,
    search_func=None,
) -> Dict:
    """Run curated lookup without LLM fallback, writes, or promotion.

    Extracted from BrainSession._run_curated_lookup_command.
    Uses DI for the format function and search function.

    Parameters
    ----------
    query : str
        Search query string.
    top_k : int
        Maximum results to return.
    format_func : callable
        Function to format the response (default: format_curated_lookup_chat_response).
    search_func : callable, optional
        Function to search curated candidates. If None, returns "lookup_unavailable".
    """
    query = (query or "").strip()
    warnings: List[str] = []
    if not query:
        content = format_func(query, None, warnings=["query_required"])
        return {
            "success": False,
            "content": content,
            "response": content,
            "route": "curated_lookup_readonly",
            "intent": "QUERY",
            "model": "curated_lookup_readonly",
            "metadata": {
                "label": "verified_curated_readonly",
                "result_count": 0,
                "warnings": ["query_required"],
                "real_write_allowed": False,
                "faiss_write_allowed": False,
                "llm_fallback_used": False,
                "automatic_context_injection": False,
            },
        }

    if search_func is None:
        warnings = ["lookup_unavailable"]
        content = format_func(query, None, warnings=warnings, error="search_func not provided")
        return {
            "success": False,
            "content": content,
            "response": content,
            "route": "curated_lookup_readonly",
            "intent": "QUERY",
            "model": "curated_lookup_readonly",
            "metadata": {
                "label": "verified_curated_readonly",
                "result_count": 0,
                "warnings": warnings,
                "real_write_allowed": False,
                "faiss_write_allowed": False,
                "llm_fallback_used": False,
                "automatic_context_injection": False,
            },
        }

    try:
        record = search_func(
            query,
            top_k=max(1, min(int(top_k or 5), 10)),
            require_provenance=True,
            include_stale=False,
        )
        content = format_func(query, record, warnings=warnings)
        result_count = len(getattr(record, "results", ()) or ())
        return {
            "success": True,
            "content": content,
            "response": content,
            "route": "curated_lookup_readonly",
            "intent": "QUERY",
            "model": "curated_lookup_readonly",
            "metadata": {
                "label": "verified_curated_readonly",
                "result_count": result_count,
                "total_available": getattr(record, "total_available", 0),
                "filtered_out": getattr(record, "filtered_out", 0),
                "warnings": warnings,
                "real_write_allowed": False,
                "faiss_write_allowed": False,
                "llm_fallback_used": False,
                "automatic_context_injection": False,
            },
        }
    except Exception as exc:
        warnings = ["lookup_unavailable"]
        content = format_func(query, None, warnings=warnings, error=str(exc)[:160])
        return {
            "success": False,
            "content": content,
            "response": content,
            "route": "curated_lookup_readonly",
            "intent": "QUERY",
            "model": "curated_lookup_readonly",
            "metadata": {
                "label": "verified_curated_readonly",
                "result_count": 0,
                "warnings": warnings,
                "real_write_allowed": False,
                "faiss_write_allowed": False,
                "llm_fallback_used": False,
                "automatic_context_injection": False,
            },
        }


def get_curated_ingestion_response(
    project_state_provider_available: bool = False,
    create_provider_func=None,
) -> str:
    """Return updated P2 pipeline status from canonical source.

    Extracted from BrainSession._get_curated_ingestion_response.
    Uses DI for the provider availability flag and factory function.

    Parameters
    ----------
    project_state_provider_available : bool
        Whether the ProjectStateProvider is available.
    create_provider_func : callable, optional
        Factory function to create a provider instance.
    """
    if not project_state_provider_available:
        return (
            "No puedo confirmar estado P2 desde fuente can\u00f3nica local en este turno. "
            "No debo inventarlo."
        )

    try:
        provider = create_provider_func()
        state = provider.get_p2_state()

        lines = ["Estado Pipeline P2 (desde archivos locales):", ""]

        if state.p2_a_completed:
            lines.append("P2-A: Completado (InformationCurator contract)")
        else:
            lines.append("P2-A: No detectado")

        if state.p2_b_completed:
            lines.append("P2-B: Completado (contrato InformationCurator-LearningValidator)")
        else:
            lines.append("P2-B: No detectado")

        if state.p2_c_completed:
            lines.append("P2-C: Completado (CurationValidationAdapter implementado)")
            if state.p2_c_commit_hash:
                lines.append(f"       Commit: {state.p2_c_commit_hash}")
        else:
            lines.append("P2-C: No detectado (falta adapter)")

        if state.p2_d_completed:
            lines.append("P2-D: Completado (documentacion + smoke tests)")
            if state.p2_d_commit_hash:
                lines.append(f"       Commit: {state.p2_d_commit_hash}")
        else:
            lines.append("P2-D: No detectado (falta documentacion)")

        lines.append("")
        lines.append("Limitaciones:")
        lines.append("- Adapter NO escribe en SemanticMemoryBridge ni FAISS.")
        lines.append("- Adapter NO conecta runtime/chat.")
        lines.append("- Adapter NO activa autoaprendizaje.")

        return "\n".join(lines)

    except Exception as e:
        return (
            f"Error al consultar estado P2: {str(e)}. "
            "No puedo confirmar estado desde fuente can\u00f3nica local."
        )