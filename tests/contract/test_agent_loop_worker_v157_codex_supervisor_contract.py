#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROMPT = ROOT / ".github/codex/prompts/agent-loop-supervisor.md"
SCHEMA = ROOT / ".github/codex/review-schema.json"


def test_supervisor_prompt_requires_v157_worker_version() -> None:
    text = PROMPT.read_text(encoding="utf-8")
    assert "v1.5.7" in text, "supervisor prompt must reference v1.5.7"
    assert "WORKER_VERSION=1.5.7" in text
    assert "worker_version >= 1.5.7" in text


def test_supervisor_prompt_requires_prompt_delivery_ack() -> None:
    text = PROMPT.read_text(encoding="utf-8")
    assert "ACK_TASK_ID=" in text, "supervisor must require prompt-delivery ACK"
    assert "prompt-delivery contract" in text.lower()


def test_supervisor_prompt_requires_relative_workspace_path() -> None:
    text = PROMPT.read_text(encoding="utf-8")
    assert "relative path" in text.lower()
    assert "docs/agent_loop/pilot/PILOT_MARKER.md" in text
    assert "absolute paths" in text.lower()


def test_supervisor_prompt_requires_deterministic_transport() -> None:
    text = PROMPT.read_text(encoding="utf-8")
    assert "node.exe" in text and "JS entrypoint" in text, "supervisor must require lossless node.exe transport"


def test_supervisor_prompt_preserves_no_merge_no_canonical_sync() -> None:
    text = PROMPT.read_text(encoding="utf-8")
    assert "merge_performed=false" in text
    assert "canonical_local_sync=false" in text


def test_review_schema_has_v157_verdict_enum() -> None:
    text = SCHEMA.read_text(encoding="utf-8")
    assert '"verdict"' in text
    assert '"PASS"' in text
    assert '"CHANGES_REQUESTED"' in text
    assert '"BLOCKED"' in text


print(json.dumps({"status": "PASS", "tests": ["v157_worker_version", "prompt_delivery_ack", "relative_path", "lossless_transport", "no_merge_no_canonical", "review_schema"]}, indent=2))
