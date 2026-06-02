"""Routing constants extracted from BrainSession (B7-STRANGLER-04).

This module hosts the agent-routing keyword lists, pre-compiled keyword
patterns, and the ancillary regex patterns used by BrainSession's chat
pipeline (path detection, chain-of-thought leak detection, "continue"
short-message detection, user-correction detection).

These symbols are re-exported from ``brain_v9.core.session`` for full
backward compatibility (existing tests, debug scripts and external callers
that monkeypatch ``session_mod._AGENT_PATTERNS`` continue to work
unchanged).

Design rules (do not break):
- No I/O, no network, no globals/state.
- Does NOT import brain_v9.core.session (avoids circular import).
- Does NOT reference BrainSession.
- Does NOT use ``self`` or ``cls``.
- Only depends on the standard library ``re`` module.

Symbols extracted:
- ``AGENT_INTENTS``           : set[str] of canonical intent labels.
- ``AGENT_KEYWORDS``          : list[str] of raw regex sources.
- ``_AGENT_PATTERNS``         : list[re.Pattern] pre-compiled with IGNORECASE.
- ``_CODE_ANALYSIS_PATH_RE``  : re.Pattern detecting Windows / unix-style paths.
- ``_LEAK_TAIL_RE``           : re.Pattern detecting CoT leak tails.
- ``_CONTINUE_WORDS_RE``      : re.Pattern detecting short "continue" messages.
- ``_CORRECTION_RE``          : re.Pattern detecting user corrections.
"""

from __future__ import annotations

import re

AGENT_INTENTS = {"SYSTEM", "CODE", "COMMAND", "TRADING"}

# Words that REQUIRE tool execution (not just informational questions).
# Matched with word boundaries to avoid false positives like "log" in "lograr".
AGENT_KEYWORDS = [
    # ── Spanish imperative actions ──
    r"\brevisa\b", r"\bverifica\b", r"\bdiagnostica\b", r"\bchequea\b",
    r"\bejecutar?\b", r"\bcorre\b", r"\binspecciona\b",
    r"\barregla\b", r"\binicia\b", r"\barranca\b",
    r"\bdetén\b", r"\breinicia\b",
    r"\blee\b", r"\bleer\b", r"\bmuestra\b", r"\babre\b",
    r"\blista\b", r"\blistar\b", r"\blistame\b", r"\blistá\b",
    r"\bdescribe\b", r"\bdescribir\b", r"\benumera\b",
    r"\bcambios?\b", r"\bmodificaci[oó]n(?:es)?\b", r"\bmejoras?\b",
    r"\brecientes?\b", r"\bultimos?\b", r"\bú?ltimos?\b",
    r"\bbrain\b", r"\bcerebro\b", r"\bsistema\b",
    # PHASE R3.1: UI / dashboard queries — must fetch HTML, not search backend code
    r"\bpesta[ñn]a\b", r"\btab\b", r"\bdashboard\b", r"\bui\b", r"\bgui\b",
    r"\binterfaz\b", r"\bventana\b", r"\bpantalla\b", r"\bvista\b",
    # ── English imperative actions ──
    r"\bcheck\b", r"\bverify\b", r"\bdiagnose\b", r"\binspect\b",
    r"\bexecute\b", r"\brun\b", r"\bfix\b", r"\bstart\b", r"\bstop\b",
    r"\brestart\b", r"\blaunch\b",
    r"\bread\b", r"\bopen\b", r"\bcat\b",
    # ── Spanish system queries (need live data) ──
    r"\bestado de\b", r"\bestado del\b",
    r"\bpuerto\b", r"\bproceso\b", r"\blogs?\b",
    r"\barchivo\b", r"\bcarpeta\b", r"\bdirectorio\b",
    r"\bque hay en\b", r"\bqué hay en\b",
    r"\bque esta corriendo\b", r"\bqué está corriendo\b",
    r"\bcorriendo en\b",
    # ── Path-like patterns (user referencing a file path) ──
    r"\b\w+\.py\b", r"\b\w+\.json\b", r"\b\w+\.log\b", r"\b\w+\.yaml\b",
    # ── English system queries (need live data) ──
    r"\bstatus of\b", r"\bstatus\b",
    r"\bport\b", r"\bprocess\b", r"\blogs?\b",
    r"\bfile\b", r"\bfolder\b", r"\bdirectory\b",
    r"\bwhat.?s running\b", r"\bshow me\b",
    r"\blist\b",
    # ── R22: anti-hallucination — quantitative & scan/network queries ──
    # Plurals & "cuántos" - prevent LLM from fabricating counts
    r"\barchivos?\b", r"\bcarpetas?\b", r"\bdirectorios?\b",
    r"\bprocesos?\b", r"\bpuertos?\b", r"\bhosts?\b",
    r"\bcu[aá]nt[oa]s?\b", r"\bhow\s+many\b",
    # Network scan keywords
    r"\bescane[oa]r?\b", r"\bescanea\b", r"\bscan\b", r"\bsweep\b",
    r"\bred\s+local\b", r"\blocal\s+network\b", r"\bnetwork\b",
    # CIDR / IPv4 in message — strong signal of operational intent
    r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}(?:/\d{1,2})?\b",
    # Report / mini-report intent
    r"\breporte\b", r"\breport\b", r"\bmini[\s-]?reporte\b",
    # ── End R22 ──
    # ── Connection / access actions ──
    r"\bconecta\b", r"\bconectate\b", r"\bconnect\b",
    r"\baccede\b", r"\bacceder\b", r"\baccess\b",
    # ── Tool / capability queries ──
    r"\bherramienta\b", r"\btool\b", r"\bnecesita\b", r"\bfalta\b",
    # ── Install / package ──
    r"\binstala\b", r"\binstall\b",
    # ── Trading platforms ──
    r"\bquantconnect\b", r"\bqc\b", r"\bbacktest\b",
    r"\bibkr\b", r"\binteractive.?brokers?\b",
    # ── Download / fetch actions ──
    r"\bobtener\b", r"\bdescargar\b", r"\bdownload\b", r"\bextraer\b",
    # ── API / credentials ──
    r"\bapi\b", r"\bcredencial\b", r"\bcredentials?\b",
    # ── Trading pipeline bridge (Phase III) ──
    r"\bestrategia\b", r"\bestrategias\b", r"\bstrategy\b", r"\bstrategies\b",
    r"\bcongela\b", r"\bfreeze\b", r"\bdescongela\b", r"\bunfreeze\b",
    r"\bscorecard\b", r"\bscorecards\b",
    r"\bledger\b", r"\btrades\b", r"\bhistorial\b",
    r"\bacción\b", r"\bacciones\b",
    r"\bexpectancy\b", r"\bwin.?rate\b", r"\bpnl\b",
    # ── Closed-loop trading (Phase 9) ──
    r"\borden\b", r"\border\b", r"\borders\b", r"\bordenes\b",
    r"\bposicion\b", r"\bposiciones\b", r"\bpositions?\b",
    r"\bpaper\b", r"\bpaper.?trad\b",
    r"\bingesta\b", r"\bingest\b",
    r"\bpromoci[oó]n\b", r"\bpromot\b", r"\bpromover\b",
    r"\bcuenta\b", r"\baccount\b",
    r"\blive.?paper\b",
    # ── Subsystem-specific (language-neutral) ──
    r"\bdashboard\b", r"\bpocketoption\b", r"\brooms\b",
    r"\bautonomía\b", r"\bautonomia\b", r"\bdiagnóstico\b",
    r"\bautonomy\b", r"\bdiagnostic\b",
]

# Pre-compile for performance
_AGENT_PATTERNS = [re.compile(p, re.IGNORECASE) for p in AGENT_KEYWORDS]

_CODE_ANALYSIS_PATH_RE = re.compile(
    r"(?P<path>(?:[A-Za-z]:[\\/][^\\/:*?\"<>|\r\n]+(?:[\\/][^\\/:*?\"<>|\r\n]+)*|"
    r"(?:tmp_agent|brain|core|tests)[\\/][^\s\"']+\.(?:py|json|md|txt|ps1|yaml|yml)))",
    re.IGNORECASE,
)

# PHASE R3: detect chain-of-thought leak in final responses (used by chat() guard)
_LEAK_TAIL_RE = re.compile(
    r"(?:revisando|verificando|analizando|consultando|comprobando|chequeando|buscando|procesando|pensando|esperando|explorando)"
    r"[^.\n]{0,120}\.{3,}\s*$",
    re.IGNORECASE,
)

_CONTINUE_WORDS_RE = re.compile(
    r"^\s*(?:continua|continúa|continue|sigue|seguir|prosigue|adelante|y\s*\?|y\s+que\s+mas\??|mas\??|mas detalle|más|"
    r"mas info|sigue\s+por\s+favor|mas|next|go on|keep going|expand|expande)\s*[\.\!\?]*\s*$",
    re.IGNORECASE,
)

# PHASE R4.4: detect user corrections to persist them in semantic memory
# Matches: "no, eso es...", "te equivocas/equivocaste", "estas mal", "el correcto es",
# "el nombre real es", "es X no Y", "incorrecto", "falso", "mentira", "no es asi"
_CORRECTION_RE = re.compile(
    r"\b("
    r"no\s+es\s+(?:asi|así|cierto|correcto|verdad)|"
    r"te\s+equivoca(?:s|ste)|"
    r"est[áa]s?\s+(?:mal|equivocad[oa])|"
    r"(?:eso|esto|lo\s+que\s+dijiste)\s+(?:es|esta|está)\s+(?:mal|incorrecto|falso|equivocad[oa])|"
    r"el\s+(?:nombre\s+)?(?:real|correcto|verdadero)\s+es|"
    r"en\s+realidad\s+es|"
    r"corrige|corrigete|corríjete|"
    r"incorrecto|"
    r"esa\s+tool\s+no\s+(?:existe|es)|"
    r"esa\s+(?:funci[óo]n|herramienta|api)\s+no\s+(?:existe|es)|"
    r"lo\s+correcto\s+es"
    r")\b",
    re.IGNORECASE,
)


__all__ = [
    "AGENT_INTENTS",
    "AGENT_KEYWORDS",
    "_AGENT_PATTERNS",
    "_CODE_ANALYSIS_PATH_RE",
    "_LEAK_TAIL_RE",
    "_CONTINUE_WORDS_RE",
    "_CORRECTION_RE",
]
