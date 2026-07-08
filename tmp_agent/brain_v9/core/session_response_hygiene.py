"""
brain_v9.core.session_response_hygiene
======================================

B7-STRANGLER-05: Pure, side-effect-free LLM chat-response sanitizer extracted
from BrainSession._sanitize_llm_chat_response (formerly in
tmp_agent/brain_v9/core/session.py @ lines 1993-2072).

Contract:
  - Module-level pure function `sanitize_llm_chat_response(content: str) -> str`.
  - No imports from `brain_v9.core.session` (no circular dependency).
  - No I/O, no network, no config.
  - Behavior is byte-identical to the prior staticmethod.

BrainSession keeps the public attribute `_sanitize_llm_chat_response` as a
staticmethod shim that delegates here, preserving full backward compatibility
for both instance-attr access (e.g. `session._sanitize_llm_chat_response(...)`
from `tmp_agent/brain_v9/main.py:1257`) and class-attr access used by tests.
"""
from __future__ import annotations

import re
from typing import List, Optional

__all__ = ["sanitize_llm_chat_response", "sanitize_memory_content", "extract_numbered_sequence"]


def sanitize_llm_chat_response(content: str) -> str:
    if not content:
        return content
    banned_lines = (
        "Utilicé la herramienta",
        "Utilice la herramienta",
        "Use la herramienta",
        "He utilizado la herramienta",
        "I used the tool",
        "I used the inference tool",
    )
    cleaned_lines = [
        line for line in content.splitlines()
        if not any(marker.lower() in line.lower() for marker in banned_lines)
    ]
    cleaned = "\n".join(line for line in cleaned_lines if line.strip())
    cleaned = cleaned.strip() or content.strip()
    # Suprime teatro ORAV en respuestas del chat puro: si el LLM emite
    # marcadores [OBSERVE]/[REASON]/[ACT]/[VERIFY] o "*[Agente ORAV" cuando
    # no hubo ejecucion real de herramientas, sugiere accion que no ocurre.
    # Strip-only de los marcadores decorativos (preservamos la prosa).
    import re as _re
    orav_markers = _re.compile(
        r"^\s*(?:\*?\[)?(?:OBSERVE|OBSERVAR|REASON|RAZONAR|ACT|ACTUAR|VERIFY|VERIFICAR|Agente\s+ORAV[^\]]*)\]\s*:?\s*",
        _re.IGNORECASE | _re.MULTILINE,
    )
    # Patrones de teatro adicionales (no marcadores estructurados sino prosa)
    theater_prose = _re.compile(
        r"(?im)^\s*(?:\*+\s*)?(?:Activando\s+(?:Agente\s+ORAV|escaneo|deteccion|diagnostico|herramienta)|Ejecutando\s+(?:herramientas|el\s+ciclo|escaneo|deteccion)|Ejecuci[oó]n\s+paralela|Iniciando\s+ciclo\s+ORAV|Realizando\s+(?:escaneo|deteccion))[^\n]*\n?"
    )
    # Bloques JSON con "tool_calls" simulados (no son ejecuciones reales en chat path)
    fake_tool_call_block = _re.compile(
        r"```json\s*\{\s*\"tool_calls\"[\s\S]*?\}\s*```",
        _re.IGNORECASE,
    )
    raw_tool_markup = _re.compile(
        r"(?is)<function_calls>[\s\S]*?</function_calls>|<invoke\s+name=[^>]+>[\s\S]*?</invoke>"
    )
    # Placeholders del tipo [resultado de X], [output], [ipconfig], [salida]
    placeholders = _re.compile(
        r"\[(?:resultado(?:\s+de)?[^\]]*|output|salida|ipconfig[^\]]*|stdout[^\]]*|stderr[^\]]*)\]",
        _re.IGNORECASE,
    )
    had_theater = bool(
        orav_markers.search(cleaned)
        or theater_prose.search(cleaned)
        or placeholders.search(cleaned)
        or fake_tool_call_block.search(cleaned)
        or raw_tool_markup.search(cleaned)
    )
    cleaned2 = orav_markers.sub("", cleaned)
    cleaned2 = theater_prose.sub("", cleaned2)
    cleaned2 = fake_tool_call_block.sub("", cleaned2)
    cleaned2 = raw_tool_markup.sub("", cleaned2)
    cleaned2 = placeholders.sub("[no_ejecutado]", cleaned2).strip()

    # HARDENING: Bloquear afirmaciones de "verificación real" sin tool trace
    # Si el contenido afirma haber verificado endpoints HTTP realmente sin evidencia de tool
    fake_verification_patterns = _re.compile(
        r'(?i)(verifiqu[ée]|verifique|consult[eé]).*?(realmente|real|endpoint|/brain/metrics|HTTP \d{3}|c[oó]digo HTTP|status \d{3})|'
        r'(HTTP [12]\d{2}|c[oó]digo [12]\d{2}|status [12]\d{2}).*?(OK|200|éxito|success)',
        _re.IGNORECASE
    )

    if fake_verification_patterns.search(cleaned2):
        # Reemplazar afirmación de verificación fake con disclaimer
        cleaned2 = (
            "No puedo confirmar estado real sin ejecución HTTP/tool actual. "
            "Necesito herramienta HTTP real o confirmación explícita para verificar ese endpoint."
        )

    if had_theater and cleaned2:
        cleaned2 += (
            "\n\n_Nota: respuesta del modulo de chat (sin ejecucion de herramientas). "
            "Capacidades nativas disponibles para red: `detect_local_network`, `scan_local_network`. "
            "Pidemelo explicito si quieres que las invoque via agente._"
        )
    if had_theater:
        return cleaned2
    return cleaned2 or cleaned


# ---------------------------------------------------------------------------
# B7-STRANGLER-04B: Memory content sanitizer + numbered sequence extractor
# ---------------------------------------------------------------------------

def sanitize_memory_content(text: str) -> str:
    """Remove internal markers from memory-bound text before persistence.

    Pure function extracted from BrainSession._sanitize_memory_content.
    Strips lines containing agent theater, dev markers, raw tool markup,
    extractive summary markers, and internal state prefixes.
    """
    if not text:
        return text
    lines = []
    for line in str(text).splitlines():
        stripped = line.strip()
        if stripped.startswith("*[Agente ORAV"):
            continue
        if stripped.startswith("---") and "[DEV]" in stripped:
            continue
        if stripped.startswith("<function_calls") or stripped.startswith("<invoke "):
            continue
        if stripped.startswith("</function_calls>") or stripped.startswith("</invoke>"):
            continue
        if stripped.startswith("*[Resumen extractivo"):
            continue
        if stripped.startswith("(estado interno:"):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def extract_numbered_sequence(message: str) -> Optional[List[str]]:
    """Extract numbered steps, including inline lists like '1. a 2. b'.

    Pure function extracted from BrainSession._extract_numbered_sequence.
    Falls back to bullet/dash lists if no numbered markers found.
    Returns None if no steps are found.
    """
    marker_re = re.compile(r"(?<!\d)(\d+)\.\s+")
    markers = list(marker_re.finditer(message))
    steps: List[str] = []
    if markers:
        for index, marker in enumerate(markers):
            start = marker.end()
            end = markers[index + 1].start() if index + 1 < len(markers) else len(message)
            step = message[start:end].strip()
            if step:
                steps.append(re.sub(r"\s+", " ", step))
        return steps if steps else None

    for line in message.splitlines():
        m = re.match(r"^\s*(?:-\s*|\*\s*)\s*(.+)\s*$", line)
        if m:
            steps.append(m.group(1).strip())
    return steps if steps else None
