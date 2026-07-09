"""Tests for session_curated_render extracted helpers.

Front: FRONT-B7-SESSION-STRANGLER-PURE-RENDERERS-BATCH-06A
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from tmp_agent.brain_v9.core.session_curated_render import (
    format_curated_lookup_chat_response,
    parse_curated_lookup_command,
    run_curated_lookup_command,
    get_curated_ingestion_response,
    utility_score,
    utility_blockers,
)


# --- utility_score tests ---

def test_utility_score_u_score():
    assert utility_score({"u_score": 0.85}) == 0.85


def test_utility_score_u_proxy_score():
    assert utility_score({"u_proxy_score": 0.5}) == 0.5


def test_utility_score_default():
    assert utility_score({}) == "N/A"


# --- utility_blockers tests ---

def test_utility_blockers_with_list():
    result = utility_blockers({"promotion_gate": {"blockers": ["a", "b"]}})
    assert result == ["a", "b"]


def test_utility_blockers_empty():
    result = utility_blockers({"promotion_gate": {}})
    assert result == []


def test_utility_blockers_no_gate():
    result = utility_blockers({})
    assert result == []


# --- format_curated_lookup_chat_response tests ---

def test_format_curated_empty_query():
    result = format_curated_lookup_chat_response("", None)
    assert "[verified_curated_readonly]" in result
    assert "Consulta vac" in result


def test_format_curated_error():
    result = format_curated_lookup_chat_response("test", None, error="timeout")
    assert "No pude consultar" in result
    assert "timeout" in result


def test_format_curated_no_results():
    class FakeResult:
        results = ()
        total_available = 0
        filtered_out = 0
    result = format_curated_lookup_chat_response("test", FakeResult())
    assert "No encontr" in result


def test_format_curated_with_results():
    class FakeItem:
        text = "some curated text"
        source_id = "src1"
        evidence_refs = ["ref1"]
        validation_score = 0.9
        curation_score = 0.8
        trust_score = 0.7
        freshness = "2026-01"
        dry_run_id = "dr1"
    class FakeResult:
        results = [FakeItem()]
        total_available = 1
        filtered_out = 0
    result = format_curated_lookup_chat_response("test", FakeResult())
    assert "1 resultados curados" in result
    assert "src1" in result
    assert "ref1" in result


def test_format_curated_with_warnings():
    result = format_curated_lookup_chat_response("test", None, warnings=["warn1"])
    assert "Warnings:" in result
    assert "warn1" in result


# --- parse_curated_lookup_command tests ---

def test_parse_curated_colon_trigger():
    result = parse_curated_lookup_command("busca en conocimiento curado: python")
    assert result is not None
    assert result["query"] == "python"


def test_parse_curated_prefix_trigger():
    result = parse_curated_lookup_command("que aprendiste sobre trading")
    assert result is not None
    assert "trading" in result["query"]


def test_parse_curated_no_match():
    assert parse_curated_lookup_command("hola") is None


def test_parse_curated_empty():
    assert parse_curated_lookup_command("") is None


# --- run_curated_lookup_command tests ---

def test_run_curated_empty_query():
    result = run_curated_lookup_command("")
    assert result["success"] is False
    assert "query_required" in result["metadata"]["warnings"]


def test_run_curated_no_search_func():
    result = run_curated_lookup_command("test", search_func=None)
    assert result["success"] is False
    assert "lookup_unavailable" in result["metadata"]["warnings"]


def test_run_curated_with_mock_search():
    class FakeRecord:
        results = ()
        total_available = 0
        filtered_out = 0
    def mock_search(query, top_k=5, require_provenance=True, include_stale=False):
        return FakeRecord()
    result = run_curated_lookup_command("test", search_func=mock_search)
    assert result["success"] is True
    assert result["route"] == "curated_lookup_readonly"


# --- get_curated_ingestion_response tests ---

def test_ingestion_response_provider_unavailable():
    result = get_curated_ingestion_response(project_state_provider_available=False)
    assert "No puedo confirmar" in result


def test_ingestion_response_provider_available():
    class FakeState:
        p2_a_completed = True
        p2_b_completed = False
        p2_c_completed = True
        p2_c_commit_hash = "abc123"
        p2_d_completed = False
        p2_d_commit_hash = None
    class FakeProvider:
        def get_p2_state(self):
            return FakeState()
    def create_provider():
        return FakeProvider()
    result = get_curated_ingestion_response(
        project_state_provider_available=True,
        create_provider_func=create_provider,
    )
    assert "P2-A: Completado" in result
    assert "P2-B: No detectado" in result
    assert "P2-C: Completado" in result
    assert "abc123" in result
    assert "P2-D: No detectado" in result


def test_ingestion_response_provider_error():
    def create_provider():
        raise Exception("connection error")
    result = get_curated_ingestion_response(
        project_state_provider_available=True,
        create_provider_func=create_provider,
    )
    assert "Error al consultar" in result
    assert "connection error" in result


# --- module safety ---

def test_module_does_not_import_session():
    import inspect
    import tmp_agent.brain_v9.core.session_curated_render as mod
    src = inspect.getsource(mod)
    lines = [l for l in src.splitlines() if l.strip().startswith("import ") or l.strip().startswith("from ")]
    for line in lines:
        assert "brain_v9.core.session" not in line, f"session_curated_render must NOT import session.py, found: {line.strip()}"


# --- structural test ---

def test_curated_render_shims_are_thin():
    import ast
    from pathlib import Path

    p = Path(__file__).resolve().parents[2] / "tmp_agent" / "brain_v9" / "core" / "session.py"
    txt = p.read_text(encoding="utf-8", errors="ignore")
    tree = ast.parse(txt)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "BrainSession")
    methods = {n.name: n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}

    targets = [
        "_format_curated_lookup_chat_response",
        "_parse_curated_lookup_command",
        "_run_curated_lookup_command",
        "_get_curated_ingestion_response",
        "_utility_score",
        "_utility_blockers",
    ]

    for name in targets:
        assert name in methods, f"{name} not found in BrainSession"
        src = ast.get_source_segment(txt, methods[name])
        assert "_curated_render." in src, f"{name} must delegate to _curated_render"

    # Verify no old body tokens in format
    fmt_src = ast.get_source_segment(txt, methods["_format_curated_lookup_chat_response"])
    forbidden = ["lines = [", "getattr(item", "evidence_refs"]
    for token in forbidden:
        assert token not in fmt_src, f"forbidden token in _format_curated_lookup_chat_response: {token}"

    # Verify no old body in run_curated
    run_src = ast.get_source_segment(txt, methods["_run_curated_lookup_command"])
    forbidden_run = ["content = self._format", "record = search_curated"]
    for token in forbidden_run:
        assert token not in run_src, f"forbidden token in _run_curated_lookup_command: {token}"


if __name__ == "__main__":
    tests = [
        test_utility_score_u_score,
        test_utility_score_u_proxy_score,
        test_utility_score_default,
        test_utility_blockers_with_list,
        test_utility_blockers_empty,
        test_utility_blockers_no_gate,
        test_format_curated_empty_query,
        test_format_curated_error,
        test_format_curated_no_results,
        test_format_curated_with_results,
        test_format_curated_with_warnings,
        test_parse_curated_colon_trigger,
        test_parse_curated_prefix_trigger,
        test_parse_curated_no_match,
        test_parse_curated_empty,
        test_run_curated_empty_query,
        test_run_curated_no_search_func,
        test_run_curated_with_mock_search,
        test_ingestion_response_provider_unavailable,
        test_ingestion_response_provider_available,
        test_ingestion_response_provider_error,
        test_module_does_not_import_session,
        test_curated_render_shims_are_thin,
    ]
    passed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
            passed += 1
        except AssertionError as e:
            print(f"FAIL  {t.__name__}: {e}")
        except Exception as e:
            print(f"ERROR {t.__name__}: {e}")
    print(f"\n{passed}/{len(tests)} passed")