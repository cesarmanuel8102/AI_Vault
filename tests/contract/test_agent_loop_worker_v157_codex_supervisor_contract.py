#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROMPT = ROOT / ".github/codex/prompts/agent-loop-supervisor.md"
SCHEMA = ROOT / ".github/codex/review-schema.json"
WORKFLOW = ROOT / ".github/workflows/agent-loop-pilot.yml"


def _workflow() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def _prompt() -> str:
    return PROMPT.read_text(encoding="utf-8")


def _schema() -> dict:
    return json.loads(SCHEMA.read_text(encoding="utf-8"))


def _job_block(text: str, job: str) -> str:
    marker = f"\n  {job}:\n"
    start = text.find(marker)
    assert start >= 0, f"missing job {job}"
    next_job = re.search(r"\n  [A-Za-z0-9_-]+:\n", text[start + len(marker):])
    end = start + len(marker) + next_job.start() if next_job else len(text)
    return text[start:end]


def test_supervisor_prompt_requires_v157_worker_version() -> None:
    text = _prompt()
    assert "v1.5.7" in text
    assert "WORKER_VERSION=1.5.7" in text
    assert "worker_version >= 1.5.7" in text
    assert "EXECUTOR=OPENCODE_OLLAMA_TOOL_EXECUTOR" in text
    assert "OpenCode/Ollama tool executor" in text
    assert "Kimi" not in text


def test_supervisor_prompt_requires_prompt_delivery_ack() -> None:
    text = _prompt()
    assert "ACK_TASK_ID=" in text
    assert "worker_parsed_opencode_jsonl" in text
    assert "task_acknowledged=true" in text
    assert "log_sha256" in text


def test_supervisor_prompt_requires_relative_workspace_path() -> None:
    text = _prompt()
    assert "relative path" in text.lower()
    assert "docs/agent_loop/pilot/PILOT_MARKER.md" in text
    assert "absolute paths" in text.lower()
    assert "write_tool_completed=true" in text
    assert "write_tool_target_kind=relative" in text


def test_supervisor_prompt_requires_deterministic_transport() -> None:
    text = _prompt()
    assert "node.exe" in text and "JS entrypoint" in text


def test_supervisor_prompt_preserves_no_merge_no_canonical_sync() -> None:
    text = _prompt()
    assert "merge_performed=false" in text
    assert "canonical_local_sync=false" in text
    assert "live_trading_enabled=false" in text
    assert "roadmap_binding" in text
    assert "human_final_authority=true" in text
    assert "git show <PR base SHA>:docs/roadmap/BRAIN_101_MANIFEST.json" in text
    assert "git show <PR base SHA>:docs/roadmap/BRAIN_101_ROADMAP.md" in text
    assert "Reading HEAD or merely checking internal consistency is insufficient" in text
    assert "Missing or mismatched canonical roadmap governance evidence is BLOCKED" in text


def test_review_schema_is_strict_json_schema() -> None:
    schema = _schema()
    assert schema["type"] == "object"
    assert schema["additionalProperties"] is False
    assert schema["required"] == ["verdict", "head_sha", "summary", "findings"]
    verdict = schema["properties"]["verdict"]
    assert verdict["enum"] == ["PASS", "CHANGES_REQUESTED", "BLOCKED"]
    assert schema["properties"]["head_sha"]["pattern"] == "^[0-9a-f]{7,40}$"


def test_workflow_deterministic_codex_publish_topology() -> None:
    text = _workflow()
    assert "deterministic:" in text
    assert "codex:" in text
    assert "publish:" in text
    codex = _job_block(text, "codex")
    publish = _job_block(text, "publish")
    assert "needs: deterministic" in codex
    assert "if: needs.deterministic.result == 'success'" in codex
    assert "sandbox: read-only" in codex
    assert "contents: read" in codex
    assert "issues: write" not in codex
    assert "pull-requests: write" not in codex
    assert "--output-schema" in codex and ".github/codex/review-schema.json" in codex
    assert "needs: [deterministic, codex]" in publish
    assert "issues: write" in publish and "pull-requests: write" in publish


def test_workflow_verdict_transitions_are_explicit() -> None:
    text = _workflow()
    publish = _job_block(text, "publish")
    assert "DETERMINISTIC_FAILURE" in publish and "loop:repairing" in publish
    assert "CODEX_ACTION_FAILURE" in publish and "loop:blocked" in publish
    assert "INVALID_CODEX_JSON" in publish and "loop:blocked" in publish
    assert "parsed.verdict === 'PASS' && parsed.head_sha === process.env.HEAD_SHA" in publish
    assert "loop:ready-human-audit" in publish
    assert "parsed.verdict === 'CHANGES_REQUESTED'" in publish and "loop:repairing" in publish
    assert "Codex returned BLOCKED" in publish and "loop:blocked" in publish


def test_workflow_has_no_merge_push_or_write_credentials() -> None:
    text = _workflow().lower()
    forbidden = ["git push", "gh pr merge", "contents: write"]
    for token in forbidden:
        assert token not in text, token
    assert "persist-credentials: false" in text


def test_workflow_head_mismatch_cannot_pass() -> None:
    publish = _job_block(_workflow(), "publish")
    assert "parsed.head_sha === process.env.HEAD_SHA" in publish
    assert "HEAD_SHA: ${{ github.event.pull_request.head.sha }}" in publish


def test_workflow_derives_exact_front_from_commit_and_cross_checks_report() -> None:
    deterministic = _job_block(_workflow(), "deterministic")
    assert "git log -1 --format=%s" in deterministic
    assert "test(agent-loop): complete " in deterministic
    assert "front_id=\"${subject#\"$prefix\"}\"" in deterministic
    assert "report.get('front_id') != front_id" in deterministic
    assert "OpenCode/Ollama tool executor" in deterministic
    assert "--expected-front-id \"${{ steps.pilot_meta.outputs.front_id }}\"" in deterministic
    assert "PILOT_MARKER.md" not in deterministic.split("Derive trusted pilot metadata", 1)[1].split("Verify pilot scope", 1)[0]


def test_publish_uses_executor_neutral_language() -> None:
    publish = _job_block(_workflow(), "publish")
    assert "OpenCode executor local gates" in publish
    assert "Kimi local gates" not in publish


def main() -> int:
    tests = [
        test_supervisor_prompt_requires_v157_worker_version,
        test_supervisor_prompt_requires_prompt_delivery_ack,
        test_supervisor_prompt_requires_relative_workspace_path,
        test_supervisor_prompt_requires_deterministic_transport,
        test_supervisor_prompt_preserves_no_merge_no_canonical_sync,
        test_review_schema_is_strict_json_schema,
        test_workflow_deterministic_codex_publish_topology,
        test_workflow_verdict_transitions_are_explicit,
        test_workflow_has_no_merge_push_or_write_credentials,
        test_workflow_head_mismatch_cannot_pass,
        test_workflow_derives_exact_front_from_commit_and_cross_checks_report,
        test_publish_uses_executor_neutral_language,
    ]
    failed = 0
    for test in tests:
        try:
            test()
            print(f"PASS: {test.__name__}")
        except Exception as exc:
            failed += 1
            print(f"FAIL: {test.__name__}: {type(exc).__name__}: {exc}")
    print(json.dumps({"status": "PASS" if failed == 0 else "FAIL", "passed": len(tests) - failed, "failed": failed}, indent=2))
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
