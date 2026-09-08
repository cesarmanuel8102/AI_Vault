"""Pure response-governance boundary used by the canonical chat router."""

from typing import Any, Dict, Optional


RAW_COT_MARKERS = (
    "raw_chain_of_thought",
    "private_reasoning",
    "hidden reasoning",
    "chain of thought",
    "analysis:",
    "thinking...",
    "done thinking",
    "<thinking>",
    "<think>",
    "scratchpad:",
    "chain-of-thought:",
)


def _strip_raw_cot_fields(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _strip_raw_cot_fields(item)
            for key, item in value.items()
            if str(key).lower() not in {"raw_chain_of_thought", "private_reasoning"}
        }
    if isinstance(value, list):
        return [_strip_raw_cot_fields(item) for item in value]
    return value


def _contains_cot_marker(text: str) -> bool:
    lower = (text or "").lower()
    return any(marker in lower for marker in RAW_COT_MARKERS)


def apply_governance(content: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """Apply response hygiene without owning mutable route or session state."""
    metadata = _strip_raw_cot_fields(metadata or {})
    sanitized = content or ""
    try:
        from brain_v9.core.session import BrainSession

        sanitized, hygiene = BrainSession._sanitize_llm_chat_response_with_metadata(sanitized)
        metadata["thinking_stripped"] = bool(metadata.get("thinking_stripped") or hygiene["thinking_stripped"])
    except Exception:
        sanitized = sanitized.strip()

    no_cot_leak = not _contains_cot_marker(sanitized)
    if not no_cot_leak:
        sanitized = (
            "No puedo exponer razonamiento privado o chain-of-thought. "
            "Puedo dar una respuesta breve, verificable y con evidencia visible."
        )
        no_cot_leak = True

    return {
        "content": sanitized,
        "metadata": metadata,
        "governance_applied": True,
        "no_cot_leak": no_cot_leak,
    }
