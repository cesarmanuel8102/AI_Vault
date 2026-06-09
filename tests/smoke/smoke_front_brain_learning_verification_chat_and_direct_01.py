"""Smoke test for FRONT-BRAIN-LEARNING-VERIFICATION-CHAT-AND-DIRECT-01.

Validates that the Brain learned the canary and that the front was read-only.
"""

import subprocess
import sys
import json
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parent.parent.parent)
canary_id = "front_first_real_local_memory_faiss_canary_01"


def test_roadmap_status_json_valid():
    result = subprocess.run(
        [sys.executable, "-m", "json.tool", "ROADMAP_STATUS.json"],
        capture_output=True, text=True, cwd=".",
    )
    assert result.returncode == 0


def test_semantic_memory_canary_exists_exactly_once():
    with open("memory/semantic/semantic_memory.jsonl", encoding="utf-8") as fh:
        count = sum(1 for line in fh if canary_id in line)
    assert count == 1


def test_faiss_ids_canary_exists_exactly_once():
    ids = json.loads(Path("memory/semantic/semantic_memory_faiss_ids.json").read_text(encoding="utf-8"))
    assert ids.count(canary_id) == 1


def test_canary_source_path_exact():
    with open("memory/semantic/semantic_memory.jsonl", encoding="utf-8") as fh:
        for line in fh:
            if canary_id in line:
                obj = json.loads(line)
                assert obj["source_path"] == "docs/REAL_EXECUTION_POLICY.md"
                return
    raise AssertionError("canary not found")


def test_canary_source_sha256_exact():
    with open("memory/semantic/semantic_memory.jsonl", encoding="utf-8") as fh:
        for line in fh:
            if canary_id in line:
                obj = json.loads(line)
                assert obj["source_sha256"] == "b493b364185a60c2c9ad116907a347e69890c9978ec6fa6bb18c7bee0ae1801d"
                return
    raise AssertionError("canary not found")


def test_semantic_memory_write_executed_true():
    with open("memory/semantic/semantic_memory.jsonl", encoding="utf-8") as fh:
        for line in fh:
            if canary_id in line:
                obj = json.loads(line)
                assert obj["evidence"]["semantic_memory_write_executed"] is True
                return
    raise AssertionError("canary not found")


def test_faiss_write_executed_true():
    with open("memory/semantic/semantic_memory.jsonl", encoding="utf-8") as fh:
        for line in fh:
            if canary_id in line:
                obj = json.loads(line)
                assert obj["evidence"]["faiss_write_executed"] is True
                return
    raise AssertionError("canary not found")


def test_network_called_false():
    with open("memory/semantic/semantic_memory.jsonl", encoding="utf-8") as fh:
        for line in fh:
            if canary_id in line:
                obj = json.loads(line)
                assert obj["evidence"]["network_called"] is False
                return
    raise AssertionError("canary not found")


def test_connector_called_false():
    with open("memory/semantic/semantic_memory.jsonl", encoding="utf-8") as fh:
        for line in fh:
            if canary_id in line:
                obj = json.loads(line)
                assert obj["evidence"]["connector_called"] is False
                return
    raise AssertionError("canary not found")


def test_trading_executed_false():
    with open("memory/semantic/semantic_memory.jsonl", encoding="utf-8") as fh:
        for line in fh:
            if canary_id in line:
                obj = json.loads(line)
                assert obj["evidence"]["trading_executed"] is False
                return
    raise AssertionError("canary not found")


def test_b8_touched_false():
    with open("memory/semantic/semantic_memory.jsonl", encoding="utf-8") as fh:
        for line in fh:
            if canary_id in line:
                obj = json.loads(line)
                assert obj["evidence"]["b8_touched"] is False
                return
    raise AssertionError("canary not found")


def test_brain_learning_assessment_exists():
    p = Path("tmp_agent/front_brain_learning_verification_chat_and_direct_01/brain_learning_assessment.md")
    assert p.exists()


def test_direct_memory_verification_exists():
    p = Path("tmp_agent/front_brain_learning_verification_chat_and_direct_01/direct_memory_verification.json")
    assert p.exists()


def test_direct_faiss_verification_exists():
    p = Path("tmp_agent/front_brain_learning_verification_chat_and_direct_01/direct_faiss_verification.json")
    assert p.exists()


def test_no_semantic_memory_staged():
    result = subprocess.run(["git", "diff", "--cached", "--name-status"], capture_output=True, text=True, cwd=".")
    staged = result.stdout.strip()
    if staged:
        assert "memory/semantic/semantic_memory.jsonl" not in staged


def test_no_faiss_staged():
    result = subprocess.run(["git", "diff", "--cached", "--name-status"], capture_output=True, text=True, cwd=".")
    staged = result.stdout.strip()
    if staged:
        assert "semantic_memory_faiss" not in staged


def test_no_env_staged():
    result = subprocess.run(["git", "diff", "--cached", "--name-status"], capture_output=True, text=True, cwd=".")
    staged = result.stdout.strip()
    if staged:
        assert ".env" not in staged


def test_no_trading_or_b8_staged():
    result = subprocess.run(["git", "diff", "--cached", "--name-status"], capture_output=True, text=True, cwd=".")
    staged = result.stdout.strip()
    if staged:
        lines = staged.split("\n")
        bad = any("trading" in line or "b8" in line.lower() for line in lines)
        assert not bad


def test_no_session_py_staged():
    result = subprocess.run(["git", "diff", "--cached", "--name-status"], capture_output=True, text=True, cwd=".")
    staged = result.stdout.strip()
    if staged:
        assert "session.py" not in staged


def test_no_main_py_staged():
    result = subprocess.run(["git", "diff", "--cached", "--name-status"], capture_output=True, text=True, cwd=".")
    staged = result.stdout.strip()
    if staged:
        assert "main.py" not in staged


def test_no_execution_gate_py_staged():
    result = subprocess.run(["git", "diff", "--cached", "--name-status"], capture_output=True, text=True, cwd=".")
    staged = result.stdout.strip()
    if staged:
        assert "execution_gate.py" not in staged


def test_no_curated_runtime_lookup_staged():
    result = subprocess.run(["git", "diff", "--cached", "--name-status"], capture_output=True, text=True, cwd=".")
    staged = result.stdout.strip()
    if staged:
        assert "curated_runtime_lookup.py" not in staged
