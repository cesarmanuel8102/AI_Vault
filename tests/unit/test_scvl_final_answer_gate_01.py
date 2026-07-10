from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TMP_AGENT = ROOT / "tmp_agent"
if str(TMP_AGENT) not in sys.path:
    sys.path.insert(0, str(TMP_AGENT))

from brain_v9.core import session_scvl_gate as gate


def _set_flag(value: str) -> None:
    os.environ["BRAIN_SCVL_GATE_ENABLED"] = value


def test_flag_false_preserves_result_exactly() -> None:
    _set_flag("false")
    called = {"value": False}

    def validator(**kwargs):
        called["value"] = True
        return {"coherence_score": 0.0, "contradictions_detected": 1}

    result = {"success": True, "content": "ok", "response": "ok", "route": "agent"}
    out = gate.apply_scvl_final_answer_gate(
        message="hola",
        result=result,
        context={"validator": validator},
    )
    assert out is result
    assert out == result
    assert called["value"] is False


def test_flag_true_coherent_response_passes() -> None:
    _set_flag("true")

    def validator(**kwargs):
        return {"coherence_score": 0.95, "contradictions_detected": 0}

    out = gate.apply_scvl_final_answer_gate(
        message="resume el sistema",
        result={"success": True, "content": "resumen del sistema", "response": "resumen del sistema"},
        context={"validator": validator, "route": "agent"},
    )
    assert out["success"] is True
    assert out["scvl"]["enabled"] is True
    assert out["scvl"]["passed"] is True


def test_flag_true_incoherent_response_blocks() -> None:
    _set_flag("true")

    def validator(**kwargs):
        return {"coherence_score": 0.2, "contradictions_detected": 1, "recommended_action": "low coherence"}

    out = gate.apply_scvl_final_answer_gate(
        message="no uses herramientas",
        result={"success": True, "content": "he verificado con herramientas", "response": "he verificado con herramientas"},
        context={"validator": validator, "route": "agent"},
    )
    assert out["success"] is False
    assert "SCVL" in out["content"]
    assert out["response"] == out["content"]
    assert out["scvl"]["enabled"] is True
    assert out["scvl"]["passed"] is False
    assert out["scvl"]["score"] == 0.2


def test_flag_true_scvl_exception_blocks_explicitly() -> None:
    _set_flag("true")

    def validator(**kwargs):
        raise RuntimeError("boom")

    out = gate.apply_scvl_final_answer_gate(
        message="hola",
        result={"success": True, "content": "ok", "response": "ok"},
        context={"validator": validator, "route": "agent"},
    )
    assert out["success"] is False
    assert out["scvl"]["passed"] is False
    assert out["scvl"]["reason"] == "scvl_exception"


def test_production_call_exists_outside_tests() -> None:
    source = (ROOT / "tmp_agent" / "brain_v9" / "core" / "session_agent_route.py").read_text(encoding="utf-8")
    assert "apply_scvl_final_answer_gate(" in source
    assert "from brain_v9.core.session_scvl_gate import apply_scvl_final_answer_gate" in source


def test_no_memory_or_faiss_mutation_tokens() -> None:
    source = (ROOT / "tmp_agent" / "brain_v9" / "core" / "session_scvl_gate.py").read_text(encoding="utf-8")
    forbidden = [
        "promote_record(",
        "ingest_text(",
        "rebuild_index(",
        "faiss.write_index",
        "faiss.add",
        "memory" + "/semantic",
        "dry_run_only = False",
        "dry_run_only=False",
    ]
    assert not [token for token in forbidden if token in source]


def test_flag_false_route_preserves_result_exactly() -> None:
    _set_flag("off")
    result = {"success": True, "content": "visible", "response": "visible", "route": "agent"}
    out = gate.apply_scvl_final_answer_gate(
        message="pregunta",
        result=result,
        context={"route": "agent", "validator": lambda **_: {"coherence_score": 0.0}},
    )
    assert out is result
    assert out == {"success": True, "content": "visible", "response": "visible", "route": "agent"}


if __name__ == "__main__":
    tests = [
        test_flag_false_preserves_result_exactly,
        test_flag_true_coherent_response_passes,
        test_flag_true_incoherent_response_blocks,
        test_flag_true_scvl_exception_blocks_explicitly,
        test_production_call_exists_outside_tests,
        test_no_memory_or_faiss_mutation_tokens,
        test_flag_false_route_preserves_result_exactly,
    ]
    old_flag = os.environ.get("BRAIN_SCVL_GATE_ENABLED")
    try:
        for test in tests:
            test()
    finally:
        if old_flag is None:
            os.environ.pop("BRAIN_SCVL_GATE_ENABLED", None)
        else:
            os.environ["BRAIN_SCVL_GATE_ENABLED"] = old_flag
    print(f"OK: {len(tests)} SCVL final answer gate tests passed")
