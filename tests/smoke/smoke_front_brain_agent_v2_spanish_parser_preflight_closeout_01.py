"""Smoke test: FRONT-BRAIN-AGENT-V2-SPANISH-PARSER-PREFLIGHT-CLOSEOUT-01

Tests Spanish parser fixes:
1. Quote sanitization
2. Endpoint path normalization
3. Indirect file reference skipping
4. Spanish final answer obligation detection
5. Inline numbered Spanish prompt extraction
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from tmp_agent.brain_v9.core.agent_kernel_v2.mandatory_tools import (
    _extract_checks, parse_mandatory_tool_requests
)


def test_spanish_mandatory_prompt_detected():
    """1. Spanish mandatory prompt detected."""
    goal = "MANDATORY TOOL TEST.\nResponde en español.\nDebes hacer todos estos checks:\n1. Buscar en código agent_kernel_v2.\n2. Probar /v2/agent/status."
    result = parse_mandatory_tool_requests(goal)
    assert result["mandatory_detected"], f"Spanish mandatory not detected: {result}"
    print("PASS: spanish_mandatory_prompt_detected")


def test_quote_sanitization_grep():
    """2. Quotes stripped from grep pattern."""
    goal = 'MANDATORY TOOL TEST.\n1. Buscar en código "agent_kernel_v2".\n2. Buscar en código "NativeAgentRuntimeV2".'
    checks = _extract_checks(goal)
    for c in checks:
        if c.get("tool_name") == "grep_search":
            pat = c["input"].get("pattern", "")
            assert '"' not in pat, f"Quotes not stripped: {pat}"
            assert pat in ("agent_kernel_v2", "NativeAgentRuntimeV2"), f"Wrong pattern: {pat}"
    print("PASS: quote_sanitization_grep")


def test_endpoint_path_normalization():
    """3. Endpoint path normalized to full URL."""
    goal = "MANDATORY TOOL TEST.\n1. Probar /v2/agent/status.\n2. Probar /v2/agent/capabilities."
    checks = _extract_checks(goal)
    for c in checks:
        if c.get("tool_name") == "route_probe":
            url = c["input"].get("url", "")
            if url.startswith("/v2/"):
                assert False, f"Path not normalized: {url}"
            if "8091" in url:
                assert url.startswith("http://127.0.0.1:8091"), f"Wrong URL: {url}"
    urls = [c["input"].get("url") for c in checks if c.get("tool_name") == "route_probe"]
    assert "http://127.0.0.1:8091/v2/agent/status" in urls, f"Missing status URL: {urls}"
    assert "http://127.0.0.1:8091/v2/agent/capabilities" in urls, f"Missing capabilities URL: {urls}"
    print("PASS: endpoint_path_normalization")


def test_indirect_file_reference_skipped():
    """4. Indirect file reference skipped."""
    goal = "MANDATORY TOOL TEST.\n1. Leer el archivo donde esté NativeAgentRuntimeV2.\n2. Buscar en código NativeAgentRuntimeV2."
    checks = _extract_checks(goal)
    fr = [c for c in checks if c.get("tool_name") == "file_read"]
    # Indirect reference should produce either no file_read or a clean path
    for c in fr:
        path = c["input"].get("path", "")
        assert " " not in path, f"Indirect reference not skipped: {path}"
    print("PASS: indirect_file_reference_skipped")


def test_spanish_final_answer_obligation():
    """5. Spanish final answer obligation detected."""
    goal = "MANDATORY TOOL TEST.\n1. Probar /v2/agent/status.\n2. En la respuesta final, decir el nombre exacto del kernel."
    checks = _extract_checks(goal)
    fa = [c for c in checks if c.get("is_final_answer_requirement")]
    assert len(fa) >= 1, f"No final answer obligation found: {[c['description'] for c in checks]}"
    assert fa[0]["tool_name"] is None
    print("PASS: spanish_final_answer_obligation")


def test_inline_numbered_spanish_prompt():
    """6. Inline numbered Spanish prompt extracts all checks."""
    goal = ("MANDATORY TOOL TEST.\n"
            "Responde en español.\n"
            "Debes hacer todos estos checks:\n"
            "1. Buscar en código agent_kernel_v2.\n"
            "2. Buscar en código NativeAgentRuntimeV2.\n"
            "3. Probar /v2/agent/status.\n"
            "4. Probar /v2/agent/capabilities.\n"
            "5. En la respuesta final, decir el nombre exacto del kernel, clase runtime, endpoints y funcionalidades principales.")
    checks = _extract_checks(goal)
    tools = [c["tool_name"] for c in checks if c.get("tool_name")]
    assert "grep_search" in tools, f"Missing grep: {tools}"
    assert "route_probe" in tools, f"Missing route_probe: {tools}"
    # Count route probes
    rp = [c for c in checks if c.get("tool_name") == "route_probe"]
    assert len(rp) >= 2, f"Expected 2+ route_probe, got {len(rp)}: {[c['input'] for c in rp]}"
    # Final answer obligation
    fa = [c for c in checks if c.get("is_final_answer_requirement")]
    assert len(fa) >= 1, f"Missing final answer: {[c['description'] for c in checks]}"
    print("PASS: inline_numbered_spanish_prompt")


if __name__ == "__main__":
    tests = [
        test_spanish_mandatory_prompt_detected,
        test_quote_sanitization_grep,
        test_endpoint_path_normalization,
        test_indirect_file_reference_skipped,
        test_spanish_final_answer_obligation,
        test_inline_numbered_spanish_prompt,
    ]
    passed = 0
    failed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except AssertionError as e:
            print(f"FAIL: {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"ERROR: {t.__name__}: {e}")
            failed += 1
    print(f"\n{passed}/{len(tests)} passed, {failed} failed")
    sys.exit(0 if failed == 0 else 1)
