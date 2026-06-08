"""Smoke test for FRONT-REAL-RUNTIME-LOOKUP-ENDPOINT-LIVE-SMOKE-01."""

import json
import os

EVIDENCE_DIR = "tmp_agent/front_real_runtime_lookup_endpoint_live_smoke_01"


def test_baseline_snapshot_exists():
    assert os.path.isfile(f"{EVIDENCE_DIR}/baseline_snapshot.json")


def test_live_result_exists():
    assert os.path.isfile(f"{EVIDENCE_DIR}/live_endpoint_result.json")


def test_live_result_success():
    with open(f"{EVIDENCE_DIR}/live_endpoint_result.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data.get("status_code") == 200
    assert data.get("body", {}).get("status") == "ok"
    assert data.get("body", {}).get("found") is True
    assert data.get("body", {}).get("count") == 1


def test_live_result_no_write():
    with open(f"{EVIDENCE_DIR}/live_endpoint_result.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data.get("body", {}).get("no_write") is True


def test_live_result_no_faiss():
    with open(f"{EVIDENCE_DIR}/live_endpoint_result.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data.get("body", {}).get("faiss_used") is False


def test_live_result_no_promotion():
    with open(f"{EVIDENCE_DIR}/live_endpoint_result.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data.get("body", {}).get("promotion") is False


def test_live_result_canary_is_last():
    with open(f"{EVIDENCE_DIR}/live_endpoint_result.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data.get("body", {}).get("is_last_line") is True


def test_live_result_validation_valid():
    with open(f"{EVIDENCE_DIR}/live_endpoint_result.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data.get("body", {}).get("validation", {}).get("valid") is True


def test_post_smoke_snapshot_exists():
    assert os.path.isfile(f"{EVIDENCE_DIR}/post_smoke_snapshot.json")


def test_hashes_unchanged():
    with open(f"{EVIDENCE_DIR}/post_smoke_snapshot.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data.get("hashes_unchanged") is True


def test_runtime_stop_decision_exists():
    assert os.path.isfile(f"{EVIDENCE_DIR}/runtime_stop_decision.json")


def test_runtime_stopped():
    with open(f"{EVIDENCE_DIR}/runtime_stop_decision.json", "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data.get("runtime_stopped") is True


def test_doc_exists():
    assert os.path.isfile("docs/FRONT_REAL_RUNTIME_LOOKUP_ENDPOINT_LIVE_SMOKE_01.md")


def test_doc_decision_present():
    with open("docs/FRONT_REAL_RUNTIME_LOOKUP_ENDPOINT_LIVE_SMOKE_01.md", "r", encoding="utf-8") as f:
        content = f.read()
    assert "LIVE_SMOKE_PASSED" in content
