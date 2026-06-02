"""B7-STRANGLER-07 import-compat: BrainSession grounded-excerpt shim integrity.

Verifies:
* The 6 module-level helpers exist in brain_v9.core.session_grounded_excerpt
  and are callable.
* Each BrainSession method (3 staticmethods + 3 classmethods) still resolves
  via attribute lookup AND preserves its original descriptor type, which
  matters for external callers that bind the staticmethod directly (see
  ``tests/unit/test_grounded_code_fastpath.py`` consuming
  ``BrainSession._extract_candidate_paths``).
* The shim and the standalone helper produce identical output for sample inputs.
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_TMP_AGENT = _REPO_ROOT / "tmp_agent"
if str(_TMP_AGENT) not in sys.path:
    sys.path.insert(0, str(_TMP_AGENT))


_HELPERS = (
    "extract_candidate_paths",
    "extract_symbol_hint",
    "slice_lines",
    "build_grounded_file_excerpt",
    "find_test_references",
    "build_test_reference_excerpt",
)


def test_helpers_module_exposes_6_functions():
    from brain_v9.core import session_grounded_excerpt as g
    for n in _HELPERS:
        fn = getattr(g, n, None)
        assert callable(fn), f"missing/uncallable {n}"


def test_brain_session_shim_methods_present_and_callable():
    from brain_v9.core.session import BrainSession
    expected = {
        "_extract_candidate_paths": "staticmethod",
        "_extract_symbol_hint": "staticmethod",
        "_slice_lines": "staticmethod",
        "_build_grounded_file_excerpt": "classmethod",
        "_find_test_references": "classmethod",
        "_build_test_reference_excerpt": "classmethod",
    }
    for name, descriptor in expected.items():
        raw = BrainSession.__dict__.get(name)
        assert raw is not None, f"BrainSession.{name} missing"
        assert type(raw).__name__ == descriptor, (
            f"BrainSession.{name} expected {descriptor}, got {type(raw).__name__}"
        )
        bound = getattr(BrainSession, name)
        assert callable(bound)


def test_extract_symbol_hint_shim_matches_helper():
    from brain_v9.core.session import BrainSession
    from brain_v9.core import session_grounded_excerpt as g
    samples = [
        "revisa la funcion 'foo_bar' por favor",
        "explica `MyClass` en detalle",
        'la prueba scan_local_network("auto") falla',
        "como funciona resolver_authority?",
        "",
        "revisa lee resume",  # only stop words → ""
    ]
    for msg in samples:
        assert BrainSession._extract_symbol_hint(msg) == g.extract_symbol_hint(msg)


def test_slice_lines_shim_matches_helper():
    from brain_v9.core.session import BrainSession
    from brain_v9.core import session_grounded_excerpt as g
    lines = [f"line_{i}" for i in range(20)]
    for idx in (0, 5, 10, 19):
        for r in (0, 3, 18):
            assert BrainSession._slice_lines(lines, idx, r) == g.slice_lines(lines, idx, r)


def test_extract_candidate_paths_shim_matches_helper():
    from brain_v9.core.session import BrainSession
    from brain_v9.core import session_grounded_excerpt as g
    msgs = ["", "no paths here", "see foo/bar.py and baz.py", "ruta: a/b/c.json"]
    for m in msgs:
        assert BrainSession._extract_candidate_paths(m) == g.extract_candidate_paths(m)


def test_find_test_references_shim_matches_helper():
    from brain_v9.core.session import BrainSession
    from brain_v9.core import session_grounded_excerpt as g
    for hint in ("", "extract_candidate_paths", "definitely_no_such_symbol_xyz_123"):
        assert BrainSession._find_test_references(hint) == g.find_test_references(hint)


def test_build_grounded_file_excerpt_via_self_module():
    """Use the new module file itself as the target: deterministic and small."""
    from brain_v9.core.session import BrainSession
    from brain_v9.core import session_grounded_excerpt as g
    target = Path(g.__file__)
    msg = "revisa `extract_symbol_hint`"
    hint = "extract_symbol_hint"
    a = BrainSession._build_grounded_file_excerpt(target, msg, hint)
    b = g.build_grounded_file_excerpt(target, msg, hint)
    assert a == b
    assert "extract_symbol_hint" in a
