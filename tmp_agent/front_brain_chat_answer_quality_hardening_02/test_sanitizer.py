"""Tests for sanitize_user_facing_content in response_normalizer.

Front: FRONT-BRAIN-CHAT-ANSWER-QUALITY-HARDENING-02
Verifies that finalizer boilerplate is stripped while real content is preserved.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from tmp_agent.brain_v9.core.agent_kernel_v2.response_normalizer import sanitize_user_facing_content


def test_summary_header_removed():
    content = "## Summary\n\nThe dashboard has 3 endpoints available."
    result = sanitize_user_facing_content(content)
    assert "## Summary" not in result
    assert "The dashboard has 3 endpoints available." in result


def test_finalizacion_header_removed():
    content = "## Finalización de Ejecución Agent V2 — Diagnóstico: Diferencia\n\nLa diferencia es..."
    result = sanitize_user_facing_content(content)
    assert "Finalización de Ejecución Agent V2" not in result
    assert "La diferencia es..." in result


def test_finalizacion_mojibake_header_removed():
    content_a3 = "## FinalizaciA3n de ejecuciA3n Agent V2\n\nTexto util."
    result_a3 = sanitize_user_facing_content(content_a3)
    assert "FinalizaciA3n" not in result_a3
    assert "Texto util." in result_a3
    content_double = "## Finalizaci\u00c3\u00b3n de ejecuci\u00c3\u00b3n Agent V2\n\nTexto util."
    result_double = sanitize_user_facing_content(content_double)
    assert "Agent V2" not in result_double.split("\n")[0]
    assert "Texto util." in result_double


def test_ill_finalize_removed():
    content = "I'll finalize this Agent V2 run using only the provided evidence, clearly distinguishing requested vs scheduled vs executed tools.\n\nThe answer is 42."
    result = sanitize_user_facing_content(content)
    assert "I'll finalize this Agent V2 run" not in result
    assert "The answer is 42." in result


def test_the_user_requested_removed():
    content = "The user requested: \"escribe en memoria semántica esto ahora: 'clave=valor'\". This run executed in read-only mode.\n\nNo se ejecutó la escritura."
    result = sanitize_user_facing_content(content)
    assert "The user requested" not in result
    assert "No se ejecutó la escritura." in result


def test_evidence_required_framing_removed():
    content = "This is an evidence-required diagnosis run in read-only mode. The user asked: \"analiza los endpoints\".\n\nLos endpoints son..."
    result = sanitize_user_facing_content(content)
    assert "evidence-required diagnosis run" not in result
    assert "Los endpoints son..." in result


def test_normal_markdown_preserved():
    content = "## Instalación\n\nPara instalar, ejecuta:\n\n```bash\npip install foo\n```"
    result = sanitize_user_facing_content(content)
    assert "## Instalación" in result
    assert "```bash" in result
    assert "pip install foo" in result


def test_code_blocks_preserved():
    content = "## Summary\n\nHere is the code:\n\n```python\nprint('hello')\n```"
    result = sanitize_user_facing_content(content)
    assert "## Summary" not in result
    assert "```python" in result
    assert "print('hello')" in result


def test_safety_refusal_preserved():
    content = "No puedo conectar con IBKR ni ejecutar órdenes de trading. Esa capacidad está permanentemente bloqueada por gobernanza del sistema."
    result = sanitize_user_facing_content(content)
    assert "No puedo conectar con IBKR" in result
    assert "permanentemente bloqueada por gobernanza" in result


def test_spanish_preserved():
    content = "## Summary\n\nEl modo READ es simplemente una forma de trabajo en la que solo puedo leer información."
    result = sanitize_user_facing_content(content)
    assert "## Summary" not in result
    assert "El modo READ es simplemente" in result


def test_empty_input_safe():
    assert sanitize_user_facing_content("") == ""
    assert sanitize_user_facing_content(None) == ""


def test_all_boilerplate_still_returns_original_if_empty_result():
    content = "## Summary\n## Evidence used\n## Actions performed"
    result = sanitize_user_facing_content(content)
    assert result == content.strip()


def test_requested_vs_scheduled_removed():
    content = "Requested vs Scheduled vs Executed: route_probe was requested but not scheduled.\n\nThe endpoint is live."
    result = sanitize_user_facing_content(content)
    assert "Requested vs Scheduled" not in result
    assert "The endpoint is live." in result


def test_metadata_not_altered():
    raw = {
        "final_answer": "## Summary\n\nThe answer.",
        "run_id": "agv2_123",
        "trace_url": "/v2/agent/runs/agv2_123/trace",
        "blocked_tools": ["ibkr_connect"],
        "mode_effective": "read_only",
    }
    from tmp_agent.brain_v9.core.agent_kernel_v2.response_normalizer import normalize_agent_v2_chat_response
    out = normalize_agent_v2_chat_response(raw)
    assert "## Summary" not in out["final_answer"]
    assert "The answer." in out["final_answer"]
    assert out["run_id"] == "agv2_123"
    assert out["trace_url"] == "/v2/agent/runs/agv2_123/trace"
    assert out["blocked_tools"] == ["ibkr_connect"]
    assert out["mode_effective"] == "read_only"
    assert out["sanitizer_applied"] is True


if __name__ == "__main__":
    tests = [
        test_summary_header_removed, test_finalizacion_header_removed,
        test_finalizacion_mojibake_header_removed,
        test_ill_finalize_removed, test_the_user_requested_removed,
        test_evidence_required_framing_removed, test_normal_markdown_preserved,
        test_code_blocks_preserved, test_safety_refusal_preserved,
        test_spanish_preserved, test_empty_input_safe,
        test_all_boilerplate_still_returns_original_if_empty_result,
        test_requested_vs_scheduled_removed, test_metadata_not_altered,
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
