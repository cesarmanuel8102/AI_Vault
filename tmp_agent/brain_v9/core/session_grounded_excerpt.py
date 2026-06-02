"""
brain_v9.core.session_grounded_excerpt
======================================

B7-STRANGLER-07: Pure, side-effect-free helpers for the grounded code-analysis
fastpath, extracted from BrainSession (formerly in
``tmp_agent/brain_v9/core/session.py`` @ lines 3990-4117).

These helpers locate candidate file paths and symbol hints inside a chat
message, slice context windows out of source files, and gather test-reference
excerpts. They are consumed by ``BrainSession._maybe_grounded_code_analysis_fastpath``.

Contract
--------
* Module-level pure functions; behaviour byte-identical to the prior
  ``@staticmethod`` / ``@classmethod`` bundle on ``BrainSession``.
* No imports from ``brain_v9.core.session`` (no circular dependency).
* Filesystem reads are scoped to ``BASE_PATH`` (resolved-relative check).
* Regex source: ``brain_v9.core.session_routing_constants._CODE_ANALYSIS_PATH_RE``.

BrainSession keeps the original methods as one-line shims that delegate here,
preserving the descriptor type (``@staticmethod`` vs ``@classmethod``) so
external bindings such as ``BrainSession._extract_candidate_paths`` (used by
``tests/unit/test_grounded_code_fastpath.py``) keep resolving.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import List

from brain_v9.config import BASE_PATH
from brain_v9.core.session_routing_constants import _CODE_ANALYSIS_PATH_RE

__all__ = [
    "extract_candidate_paths",
    "extract_symbol_hint",
    "slice_lines",
    "build_grounded_file_excerpt",
    "find_test_references",
    "build_test_reference_excerpt",
]


def extract_candidate_paths(message: str) -> List[Path]:
    """Return up to 3 existing files referenced inside ``message`` and scoped under BASE_PATH."""
    paths: List[Path] = []
    seen = set()
    for match in _CODE_ANALYSIS_PATH_RE.finditer(message or ""):
        raw = match.group("path").strip().strip("\"'")
        ext_match = re.search(r"^.+?\.(?:py|json|md|txt|ps1|yaml|yml)", raw, re.IGNORECASE)
        if ext_match:
            raw = ext_match.group(0)
        raw = raw.replace("/", os.sep).replace("\\", os.sep)
        p = Path(raw)
        if not p.is_absolute():
            p = BASE_PATH / raw
        try:
            resolved = p.resolve()
        except Exception:
            resolved = p
        try:
            resolved.relative_to(BASE_PATH)
        except Exception:
            continue
        if resolved.exists() and resolved.is_file():
            key = str(resolved).lower()
            if key not in seen:
                seen.add(key)
                paths.append(resolved)
    return paths[:3]


def extract_symbol_hint(message: str) -> str:
    """Return the most likely symbol identifier referenced in ``message`` (or '')."""
    msg = message or ""
    m = re.search(r"[`'\"]([A-Za-z_][A-Za-z0-9_]*)[`'\"]", msg)
    if m:
        return m.group(1)
    underscored = re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*_[A-Za-z0-9_]+)\b", msg)
    if underscored:
        return max(underscored, key=len)
    m = re.search(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(", msg)
    if m:
        return m.group(1)
    stop = {
        "revisa", "lee", "resume", "dime", "como", "explica", "condicion",
        "exacta", "inspecciona", "corrigio", "prueba", "cubre", "fallback",
    }
    words = [w for w in re.findall(r"\b([A-Za-z_][A-Za-z0-9_]{3,})\b", msg) if w.lower() not in stop]
    return max(words, key=len) if words else ""


def slice_lines(lines: List[str], start_idx: int, radius: int = 18) -> str:
    """Return a numbered slice of ``lines`` around ``start_idx`` with +/- ``radius`` context."""
    lo = max(0, start_idx - radius)
    hi = min(len(lines), start_idx + radius + 1)
    out = []
    for i in range(lo, hi):
        out.append(f"{i+1:04d}: {lines[i]}")
    return "\n".join(out)


def build_grounded_file_excerpt(path: Path, message: str, symbol_hint: str) -> str:
    """Read ``path`` and return numbered excerpts near ``symbol_hint`` and message-driven targets."""
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    msg_l = (message or "").lower()
    targets = []
    if symbol_hint:
        targets.append(symbol_hint)
    if "resumen extractivo" in msg_l:
        targets.extend(["Resumen extractivo", "extractive_fallback", "_looks_like_canned_failure", "extractive"])
    if "fallback" in msg_l:
        targets.extend(["CHAINS =", "timeout", "fallback"])
    if any(token in msg_l for token in ("confirmado", "confirmacion", "confirmación", "si,", "sí,")):
        targets.extend([
            "_is_confirmation",
            "_maybe_resume_pending_continuation",
            "_pending_continuation",
            "confirmation_noop",
            "_cmd_approve",
        ])
    if "scan_local_network" in msg_l:
        targets.extend(["def scan_local_network", "scan_local_network", "cidr='auto'", 'cidr="auto"', "detect_local_network"])
    seen = set()
    snippets: List[str] = []
    max_snippets = 5 if any(
        token in msg_l for token in ("confirmado", "confirmacion", "confirmación", "confirmation_noop")
    ) else 3
    for target in targets:
        if not target:
            continue
        for idx, line in enumerate(lines):
            if target.lower() in line.lower():
                block = slice_lines(lines, idx)
                if block not in seen:
                    seen.add(block)
                    snippets.append(block)
                if len(snippets) >= max_snippets:
                    break
        if len(snippets) >= max_snippets:
            break
    if not snippets:
        head = "\n".join(f"{i+1:04d}: {line}" for i, line in enumerate(lines[:140]))
        snippets.append(head)
    return "\n\n".join(snippets[:max_snippets])


def find_test_references(symbol_hint: str) -> List[Path]:
    """Return up to 4 ``tests/test_*.py`` paths whose content mentions ``symbol_hint``."""
    if not symbol_hint:
        return []
    hits: List[Path] = []
    tests_root = BASE_PATH / "tests"
    if not tests_root.exists():
        return hits
    for path in tests_root.rglob("test_*.py"):
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue
        if symbol_hint.lower() in content.lower():
            hits.append(path)
        if len(hits) >= 4:
            break
    return hits


def build_test_reference_excerpt(path: Path, symbol_hint: str) -> str:
    """Return a labelled excerpt of ``path`` around the first occurrence of ``symbol_hint``."""
    text = path.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    for idx, line in enumerate(lines):
        if symbol_hint.lower() in line.lower():
            return f"TEST: {path}\n{slice_lines(lines, idx, radius=12)}"
    return f"TEST: {path}"
