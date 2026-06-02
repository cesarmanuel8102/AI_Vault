"""B7-STRANGLER-07 behavior smoke: pure-function correctness for grounded helpers."""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TMP_AGENT = _REPO_ROOT / "tmp_agent"
if str(_TMP_AGENT) not in sys.path:
    sys.path.insert(0, str(_TMP_AGENT))


def test_extract_symbol_hint_quoted_priority():
    from brain_v9.core.session_grounded_excerpt import extract_symbol_hint
    assert extract_symbol_hint("revisa `foo_bar` aqui") == "foo_bar"
    assert extract_symbol_hint('explica "MyClass" detalle') == "MyClass"
    assert extract_symbol_hint("usa 'helper' por favor") == "helper"


def test_extract_symbol_hint_underscored_fallback():
    from brain_v9.core.session_grounded_excerpt import extract_symbol_hint
    # No quoted token; pick longest underscored identifier
    out = extract_symbol_hint("inspecciona detect_local_network y scan_local_network")
    assert out in ("detect_local_network", "scan_local_network")


def test_extract_symbol_hint_call_pattern():
    from brain_v9.core.session_grounded_excerpt import extract_symbol_hint
    assert extract_symbol_hint("llama a validate(x) directamente") == "validate"


def test_extract_symbol_hint_empty_and_stop_words_only():
    from brain_v9.core.session_grounded_excerpt import extract_symbol_hint
    assert extract_symbol_hint("") == ""
    assert extract_symbol_hint(None) == ""  # type: ignore[arg-type]
    assert extract_symbol_hint("revisa lee resume dime explica") == ""


def test_slice_lines_clamping():
    from brain_v9.core.session_grounded_excerpt import slice_lines
    lines = ["a", "b", "c", "d", "e"]
    # near start
    assert slice_lines(lines, 0, 2) == "0001: a\n0002: b\n0003: c"
    # near end
    assert slice_lines(lines, 4, 2) == "0003: c\n0004: d\n0005: e"
    # radius zero
    assert slice_lines(lines, 2, 0) == "0003: c"


def test_extract_candidate_paths_no_match_returns_empty():
    from brain_v9.core.session_grounded_excerpt import extract_candidate_paths
    assert extract_candidate_paths("") == []
    assert extract_candidate_paths(None) == []  # type: ignore[arg-type]
    assert extract_candidate_paths("no file references here") == []


def test_extract_candidate_paths_caps_at_three_and_dedups():
    """Even with many path tokens, only up to 3 existing-and-in-BASE_PATH files survive."""
    from brain_v9.core.session_grounded_excerpt import extract_candidate_paths
    # Reference an existing file (the new module itself) twice -> dedup
    rel = "tmp_agent/brain_v9/core/session_grounded_excerpt.py"
    msg = f"mira {rel} y {rel} y {rel}"
    out = extract_candidate_paths(msg)
    assert len(out) == 1
    assert out[0].name == "session_grounded_excerpt.py"


def test_find_test_references_empty_hint_returns_empty():
    from brain_v9.core.session_grounded_excerpt import find_test_references
    assert find_test_references("") == []


def test_find_test_references_finds_self():
    """The string 'extract_candidate_paths' appears in this file → at least one hit."""
    from brain_v9.core.session_grounded_excerpt import find_test_references
    hits = find_test_references("extract_candidate_paths")
    assert len(hits) >= 1
    assert all(p.name.startswith("test_") and p.suffix == ".py" for p in hits)
    assert len(hits) <= 4


def test_build_grounded_file_excerpt_finds_symbol():
    from brain_v9.core import session_grounded_excerpt as g
    target = Path(g.__file__)
    out = g.build_grounded_file_excerpt(target, "revisa extract_symbol_hint", "extract_symbol_hint")
    assert "extract_symbol_hint" in out
    # Numbered output format
    assert "0001:" in out or any(line[:4].isdigit() for line in out.splitlines() if line)


def test_build_grounded_file_excerpt_falls_back_to_head_when_nothing_matches():
    """When no targets match, the helper returns the first 140 numbered lines."""
    from brain_v9.core.session_grounded_excerpt import build_grounded_file_excerpt
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "x.py"
        body = "\n".join(f"line {i}" for i in range(50))
        p.write_text(body, encoding="utf-8")
        out = build_grounded_file_excerpt(p, "no match here", "")
        assert "0001: line 0" in out
        assert "0050: line 49" in out


def test_build_test_reference_excerpt_with_and_without_match():
    from brain_v9.core.session_grounded_excerpt import build_test_reference_excerpt
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "test_foo.py"
        p.write_text("alpha\nbeta\ngamma_marker\ndelta\n", encoding="utf-8")
        hit = build_test_reference_excerpt(p, "gamma_marker")
        assert hit.startswith(f"TEST: {p}")
        assert "gamma_marker" in hit
        miss = build_test_reference_excerpt(p, "no_such_token_xyz")
        assert miss == f"TEST: {p}"
