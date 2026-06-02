"""B7-STRANGLER-05 behavior smoke: pin sanitizer behavior on representative inputs."""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TMP_AGENT = _REPO_ROOT / "tmp_agent"
if str(_TMP_AGENT) not in sys.path:
    sys.path.insert(0, str(_TMP_AGENT))

from brain_v9.core.session_response_hygiene import sanitize_llm_chat_response  # noqa: E402


def test_empty_input_returned_verbatim():
    assert sanitize_llm_chat_response("") == ""


def test_none_like_falsy_passthrough():
    # The function early-returns on falsy content
    assert sanitize_llm_chat_response("") == ""


def test_plain_text_preserved():
    txt = "Hola, esta es una respuesta sin teatro."
    out = sanitize_llm_chat_response(txt)
    assert "Hola" in out
    assert "teatro" in out


def test_banned_lines_stripped():
    txt = "Linea util\nUtilicé la herramienta scan\nOtra linea util"
    out = sanitize_llm_chat_response(txt)
    assert "Utilicé la herramienta" not in out
    assert "Linea util" in out
    assert "Otra linea util" in out


def test_orav_markers_stripped():
    txt = "[OBSERVE]: revisando red\n[ACT]: ejecutando\nResultado real"
    out = sanitize_llm_chat_response(txt)
    assert "[OBSERVE]" not in out
    assert "[ACT]" not in out
    # When theater detected, a chat-module disclaimer note is appended
    assert "modulo de chat" in out


def test_theater_prose_stripped():
    txt = "Activando Agente ORAV para escaneo\nRespuesta real del modelo"
    out = sanitize_llm_chat_response(txt)
    assert "Activando Agente ORAV" not in out


def test_fake_tool_call_block_stripped():
    txt = 'Texto antes\n```json\n{"tool_calls": [{"name": "x"}]}\n```\nTexto despues'
    out = sanitize_llm_chat_response(txt)
    assert "tool_calls" not in out
    assert "Texto antes" in out
    assert "Texto despues" in out


def test_raw_tool_markup_stripped():
    txt = "Antes <function_calls><invoke name=\"foo\">bar</invoke></function_calls> despues"
    out = sanitize_llm_chat_response(txt)
    assert "function_calls" not in out
    assert "invoke" not in out


def test_placeholders_replaced():
    txt = "El resultado es [resultado de ipconfig] y luego [output] vacio."
    out = sanitize_llm_chat_response(txt)
    assert "[resultado de ipconfig]" not in out
    assert "[output]" not in out
    assert "[no_ejecutado]" in out


def test_fake_verification_disclaimer():
    txt = "Verifiqué realmente el endpoint /brain/metrics con HTTP 200 OK"
    out = sanitize_llm_chat_response(txt)
    assert "No puedo confirmar estado real" in out


def test_idempotency_on_clean_input():
    txt = "Una respuesta perfectamente limpia."
    once = sanitize_llm_chat_response(txt)
    twice = sanitize_llm_chat_response(once)
    assert once == twice


def test_unicode_preservation():
    txt = "Acentos: áéíóú ñ — emojis no, pero sí caracteres especiales: ¿qué tal?"
    out = sanitize_llm_chat_response(txt)
    assert "áéíóú" in out
    assert "ñ" in out
    assert "¿qué tal?" in out
