"""Smoke test: FRONT-BRAIN-AGENT-V2-MANDATORY-INLINE-NUMBERED-CHECK-PARSER-FIX-01

Direct parser tests for inline numbered mandatory multi-tool check extraction.
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from tmp_agent.brain_v9.core.agent_kernel_v2.mandatory_tools import _extract_checks, _split_inline_checks, parse_mandatory_tool_requests


def test_multiline_numbered_list():
    """A. Multiline list with newlines."""
    goal = """MANDATORY TOOL TEST.

1. Probe http://127.0.0.1:8091/v2/agent/status
2. Probe http://127.0.0.1:8092/brain-dashboard/agent-v2/status
3. Read repo status
4. In final answer, list tools used and checks passed.
"""
    checks = _extract_checks(goal)
    assert len(checks) >= 4, f"Expected >=4 checks, got {len(checks)}: {[c['description'] for c in checks]}"
    tool_checks = [c for c in checks if c.get("tool_name")]
    assert len(tool_checks) >= 3, f"Expected >=3 tool checks, got {len(tool_checks)}"
    assert any(c.get("tool_name") == "route_probe" and "8091" in str(c.get("input", {})) for c in checks)
    assert any(c.get("tool_name") == "route_probe" and "8092" in str(c.get("input", {})) for c in checks)
    assert any(c.get("tool_name") == "repo_status_read" for c in checks)
    assert any(c.get("is_final_answer_requirement") for c in checks)
    print("PASS: multiline_numbered_list")


def test_inline_dot_numbered():
    """B. Inline compact list with 1. 2. 3. markers."""
    goal = "MANDATORY TOOL TEST. Perform all these checks: 1. Probe http://127.0.0.1:8091/v2/agent/status 2. Probe http://127.0.0.1:8092/brain-dashboard/agent-v2/status 3. Read repo status 4. In final answer, list tools used and checks passed."
    checks = _extract_checks(goal)
    assert len(checks) >= 4, f"Expected >=4 checks, got {len(checks)}: {[c['description'] for c in checks]}"
    tool_checks = [c for c in checks if c.get("tool_name")]
    assert len(tool_checks) >= 3, f"Expected >=3 tool checks, got {len(tool_checks)}"
    assert any(c.get("tool_name") == "route_probe" and "8091" in str(c.get("input", {})) for c in checks)
    assert any(c.get("tool_name") == "route_probe" and "8092" in str(c.get("input", {})) for c in checks)
    assert any(c.get("tool_name") == "repo_status_read" for c in checks)
    assert any(c.get("is_final_answer_requirement") for c in checks)
    print("PASS: inline_dot_numbered")


def test_inline_paren_numbered():
    """C. Inline compact list with 1) 2) 3) markers."""
    goal = "MANDATORY TOOL TEST. Perform all these checks: 1) Probe http://127.0.0.1:8091/v2/agent/status 2) Probe http://127.0.0.1:8092/brain-dashboard/agent-v2/status 3) Read repo status 4) In final answer, list tools used and checks passed."
    checks = _extract_checks(goal)
    assert len(checks) >= 4, f"Expected >=4 checks, got {len(checks)}: {[c['description'] for c in checks]}"
    tool_checks = [c for c in checks if c.get("tool_name")]
    assert len(tool_checks) >= 3, f"Expected >=3 tool checks, got {len(tool_checks)}"
    assert any(c.get("tool_name") == "route_probe" and "8091" in str(c.get("input", {})) for c in checks)
    assert any(c.get("tool_name") == "route_probe" and "8092" in str(c.get("input", {})) for c in checks)
    assert any(c.get("tool_name") == "repo_status_read" for c in checks)
    assert any(c.get("is_final_answer_requirement") for c in checks)
    print("PASS: inline_paren_numbered")


def test_semicolon_separated():
    """D. Semicolon-separated numbered list."""
    goal = "MANDATORY TOOL TEST. Perform all these checks: 1) Probe 8091 status; 2) Probe 8092 dashboard status; 3) Read repo status; 4) List tools used."
    checks = _extract_checks(goal)
    assert len(checks) >= 3, f"Expected >=3 checks, got {len(checks)}: {[c['description'] for c in checks]}"
    assert any(c.get("tool_name") == "repo_status_read" for c in checks)
    print("PASS: semicolon_separated")


def test_dash_bullet_list():
    """E. Dash bullet list."""
    goal = """MANDATORY TOOL TEST:

- Probe 8091 status
- Probe 8092 dashboard status
- Read repo status
- List tools used
"""
    checks = _extract_checks(goal)
    assert len(checks) >= 3, f"Expected >=3 checks, got {len(checks)}: {[c['description'] for c in checks]}"
    assert any(c.get("tool_name") == "repo_status_read" for c in checks)
    print("PASS: dash_bullet_list")


def test_url_preservation():
    """F. URLs preserved in inline lists."""
    goal = "MANDATORY TOOL TEST. 1. Probe http://127.0.0.1:8091/v2/agent/status 2. Probe http://127.0.0.1:8092/brain-dashboard/agent-v2/status"
    checks = _extract_checks(goal)
    route_probes = [c for c in checks if c.get("tool_name") == "route_probe"]
    assert len(route_probes) >= 2, f"Expected >=2 route_probe, got {len(route_probes)}"
    for p in route_probes:
        url = p.get("input", {}).get("url", "")
        assert url.startswith("http://"), f"URL not preserved: {url}"
        assert "8091" in url or "8092" in url, f"URL missing port: {url}"
    print("PASS: url_preservation")


def test_two_route_probe_extracted():
    """G. Two route_probe tools extracted from inline list."""
    goal = "MANDATORY TOOL TEST. 1. Probe http://127.0.0.1:8091/v2/agent/status 2. Probe http://127.0.0.1:8092/brain-dashboard/agent-v2/status 3. Read repo status"
    checks = _extract_checks(goal)
    route_probes = [c for c in checks if c.get("tool_name") == "route_probe"]
    assert len(route_probes) >= 2, f"Expected >=2 route_probe, got {len(route_probes)}"
    assert any("8091" in str(c.get("input", {})) for c in route_probes)
    assert any("8092" in str(c.get("input", {})) for c in route_probes)
    print("PASS: two_route_probe_extracted")


def test_repo_status_extracted():
    """H. repo_status_read extracted."""
    goal = "MANDATORY TOOL TEST. 1. Read repo status 2. Probe http://127.0.0.1:8091/v2/agent/status"
    checks = _extract_checks(goal)
    assert any(c.get("tool_name") == "repo_status_read" for c in checks)
    print("PASS: repo_status_extracted")


def test_final_answer_obligation():
    """I. Final answer check extracted as obligation, not tool."""
    goal = "MANDATORY TOOL TEST. 1. Probe http://127.0.0.1:8091/v2/agent/status 2. In final answer, list tools used and checks passed."
    checks = _extract_checks(goal)
    assert any(c.get("is_final_answer_requirement") for c in checks), "No final answer obligation found"
    fa = [c for c in checks if c.get("is_final_answer_requirement")]
    assert len(fa) >= 1
    assert fa[0].get("tool_name") is None, "Final answer obligation should not have tool_name"
    print("PASS: final_answer_obligation")


def test_parser_metadata():
    """J. Full parser returns metadata correctly."""
    goal = "MANDATORY TOOL TEST. 1. Probe http://127.0.0.1:8091/v2/agent/status 2. Read repo status 3. In final answer, list tools used."
    result = parse_mandatory_tool_requests(goal)
    assert result["mandatory_detected"] is True
    assert len(result["requested_checks"]) >= 3
    assert any(c.get("is_final_answer_requirement") for c in result["requested_checks"])
    tool_checks = [c for c in result["requested_checks"] if c.get("tool_name")]
    assert len(tool_checks) >= 2
    print("PASS: parser_metadata")


if __name__ == "__main__":
    tests = [
        test_multiline_numbered_list,
        test_inline_dot_numbered,
        test_inline_paren_numbered,
        test_semicolon_separated,
        test_dash_bullet_list,
        test_url_preservation,
        test_two_route_probe_extracted,
        test_repo_status_extracted,
        test_final_answer_obligation,
        test_parser_metadata,
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
