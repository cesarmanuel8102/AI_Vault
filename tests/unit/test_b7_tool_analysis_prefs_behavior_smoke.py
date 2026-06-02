"""B7-STRANGLER-09: behaviour smoke tests for tool-analysis preference predicates.

Exercises representative inputs to lock in the semantics of
:func:`brain_v9.core.session_tool_analysis_prefs.prefers_no_tool_analysis` and
:func:`...has_explicit_tool_target`, as well as the BrainSession shim path.

This complements the import-compat tests: those check the surface and shim
descriptor types; these check observable behaviour (true/false outputs,
case-insensitivity, empty-string safety, target-overrides-no-tool semantics).
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TMP_AGENT = _REPO_ROOT / "tmp_agent"
if str(_TMP_AGENT) not in sys.path:
    sys.path.insert(0, str(_TMP_AGENT))

import pytest

from brain_v9.core import session_tool_analysis_prefs as tap
from brain_v9.core.session import BrainSession


# ── prefers_no_tool_analysis: positive cases ────────────────────────────────


@pytest.mark.parametrize(
    "msg",
    [
        "no uses tools",
        "no use tools",
        "no herramientas",
        "sin herramientas",
        "sin tools",
        "no ejecutes herramientas",
        "no ejecutar herramientas",
        "no modifiques nada",
        "no modificar el archivo",
        "no cambies el codigo",
        "no cambiar la logica",
        "no edites el repo",
        "no editar nada",
        "no toques la config",
        "sin cambios por favor",
        "sin modificar archivos",
        "no hagas cambios",
        "solo analiza el flujo",
        "solo analizar la salida",
        "solo razona sobre esto",
        "solo explica el bug",
        # Case-insensitivity
        "NO USES TOOLS",
        "Solo Analiza esto",
    ],
)
def test_prefers_no_tool_analysis_positive(msg):
    assert tap.prefers_no_tool_analysis(msg) is True
    assert BrainSession._prefers_no_tool_analysis(msg) is True


# ── prefers_no_tool_analysis: negative cases ────────────────────────────────


@pytest.mark.parametrize(
    "msg",
    [
        "",
        "hola",
        "ejecuta el script",
        "modifica el archivo",
        "cambia la configuracion",
        "que ves?",
        "lista de tools disponibles",
        "ana liza esto",  # word-fragment must not match "analiza"
    ],
)
def test_prefers_no_tool_analysis_negative(msg):
    assert tap.prefers_no_tool_analysis(msg) is False
    assert BrainSession._prefers_no_tool_analysis(msg) is False


def test_prefers_no_tool_analysis_none_safe():
    # Original code uses ``(message or "").lower()`` so None must be safe.
    assert tap.prefers_no_tool_analysis(None) is False  # type: ignore[arg-type]


# ── has_explicit_tool_target: positive cases ────────────────────────────────


@pytest.mark.parametrize(
    "msg",
    [
        # Windows-style absolute path (matches the [a-z]:[\\/] regex)
        "revisa C:\\AI_VAULT\\tmp_agent\\brain_v9\\core\\session.py",
        # POSIX-style absolute path
        "abre /var/log/syslog",
        # Port mention
        "verifica el puerto 8000",
        "check port 4321",
        # IP address (with optional CIDR)
        "haz ping a 192.168.1.1",
        "block 10.0.0.0/8",
        # Run/execute verb followed by token
        "ejecuta run_phase207.py",
        "ejecutar build:dev",
        "corre tests/unit",
        "run pytest -q",
        "execute the script",
        # Service / object tokens
        "estado del servicio brain",
        "los servicios brain estan ok",
        "consulta ollama",
        "abre el dashboard",
        "revisa el log",
        "los logs estan en /var",
        "lee el archivo",
        "abre la carpeta",
        "lista el directorio",
        "open this file",
        "list the folder",
        "show me the directory",
    ],
)
def test_has_explicit_tool_target_positive(msg):
    assert tap.has_explicit_tool_target(msg) is True
    assert BrainSession._has_explicit_tool_target(msg) is True


# ── has_explicit_tool_target: negative cases ────────────────────────────────


@pytest.mark.parametrize(
    "msg",
    [
        "",
        "hola",
        "que opinas?",
        "explicame la idea",
        "no entiendo",
    ],
)
def test_has_explicit_tool_target_negative(msg):
    assert tap.has_explicit_tool_target(msg) is False
    assert BrainSession._has_explicit_tool_target(msg) is False


def test_has_explicit_tool_target_none_safe():
    assert tap.has_explicit_tool_target(None) is False  # type: ignore[arg-type]


# ── Combined semantics: explicit target overrides no-tool preference ────────


def test_target_overrides_no_tool_preference():
    """The two predicates are independent. ``_should_use_agent`` (which we do NOT
    re-implement here) uses ``has_explicit_tool_target`` to override
    ``prefers_no_tool_analysis``; this test pins the building-block semantics
    needed for that override to keep working unchanged after extraction.
    """
    msg = "no uses tools, pero revisa /var/log/syslog"
    assert tap.prefers_no_tool_analysis(msg) is True
    assert tap.has_explicit_tool_target(msg) is True


def test_pure_no_tool_message_has_no_target():
    msg = "solo analiza esto, por favor"
    assert tap.prefers_no_tool_analysis(msg) is True
    assert tap.has_explicit_tool_target(msg) is False


# ── Shim equivalence (catch-all) ────────────────────────────────────────────


def test_shim_equivalence_random_strings():
    samples = [
        "", " ", "x", "PUERTO 80", "puerto 8",  # port < 2 digits → no match
        "1.2.3", "1.2.3.4", "1.2.3.4/24",
        "/", "/a", "/a/b/", "C:/x", "c:\\x",
        "ejecutarx algo",  # no \b boundary on suffix → still matches "ejecutar"
        "no usestools",  # missing space → no marker match
        "Sin Herramientas Por Favor",
    ]
    for s in samples:
        assert tap.prefers_no_tool_analysis(s) == BrainSession._prefers_no_tool_analysis(s), s
        assert tap.has_explicit_tool_target(s) == BrainSession._has_explicit_tool_target(s), s
