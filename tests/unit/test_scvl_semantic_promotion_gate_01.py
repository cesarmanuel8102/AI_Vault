from __future__ import annotations

import json
import os
import sys
import tempfile
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TMP_AGENT = ROOT / "tmp_agent"
if str(TMP_AGENT) not in sys.path:
    sys.path.insert(0, str(TMP_AGENT))

# The hygiene workflow intentionally keeps dependencies light. semantic_memory_faiss
# imports numpy at module import time, but these tests exercise only promote_record's
# gate boundary and monkeypatch _add_to_index. Provide a tiny import-time stub when
# numpy is absent so the test remains independent from the FAISS/numpy runtime stack.
try:
    import numpy  # noqa: F401
except ModuleNotFoundError:
    fake_numpy = types.ModuleType("numpy")
    fake_numpy.float32 = float
    fake_numpy.int32 = int
    fake_numpy.ndarray = object
    fake_numpy.zeros = lambda *args, **kwargs: []
    fake_numpy.array = lambda values, dtype=None: values
    fake_numpy.vstack = lambda vectors, *args, **kwargs: vectors
    fake_numpy.linalg = types.SimpleNamespace(norm=lambda vec: 0.0)
    sys.modules["numpy"] = fake_numpy

from brain_v9.core.scvl_promotion_gate import apply_scvl_promotion_gate
from brain_v9.core.semantic_memory_faiss import SemanticMemoryFAISS
import brain_v9.core.semantic_memory_faiss as faiss_module


FLAG = "BRAIN_SCVL_PROMOTION_GATE_ENABLED"


class EnvFlag:
    def __init__(self, value: str | None):
        self.value = value
        self.previous = os.environ.get(FLAG)

    def __enter__(self):
        if self.value is None:
            os.environ.pop(FLAG, None)
        else:
            os.environ[FLAG] = self.value

    def __exit__(self, exc_type, exc, tb):
        if self.previous is None:
            os.environ.pop(FLAG, None)
        else:
            os.environ[FLAG] = self.previous


def _semantic_memory_without_faiss(root: Path, *, dims: int = 3) -> SemanticMemoryFAISS:
    """Build a SemanticMemoryFAISS instance without requiring faiss-cpu in CI.

    The tests in this file exercise promote_record()'s JSONL/FAISS mutation
    boundary. They monkeypatch _add_to_index, so __init__'s FAISS availability
    guard is intentionally bypassed to keep the hygiene workflow dependency-light.
    """
    mem = SemanticMemoryFAISS.__new__(SemanticMemoryFAISS)
    mem.root = Path(root)
    mem.records_path = mem.root / faiss_module.RECORDS_PATH.name
    mem.index_path = mem.root / "semantic_memory_faiss.index"
    mem.ids_path = mem.root / "semantic_memory_faiss_ids.json"
    mem.status_path = mem.root / "semantic_memory_status.json"
    mem.dims = int(dims)
    mem.ollama_url = "http://127.0.0.1:9"
    mem.model = "test-embedding-model"
    mem._index = None
    mem._ids = []
    mem.root.mkdir(parents=True, exist_ok=True)
    mem.status_path.parent.mkdir(parents=True, exist_ok=True)
    return mem


def coherent_validator(**kwargs):
    assert kwargs["selected_route"] == "semantic_promotion"
    assert kwargs["response_content"]
    return {"passed": True, "coherence_score": 0.93, "contradictions_detected": 0}


def incoherent_validator(**kwargs):
    return {
        "passed": False,
        "coherence_score": 0.12,
        "contradictions_detected": 1,
        "recommended_action": "reject_incoherent_candidate",
    }


def exception_validator(**kwargs):
    raise RuntimeError("validator failed")


def test_flag_disabled_allows_without_calling_validator():
    def should_not_run(**kwargs):
        raise AssertionError("validator should not run when gate is disabled")

    with EnvFlag("false"):
        result = apply_scvl_promotion_gate(
            candidate={"id": "c1", "text": "coherent memory candidate"},
            context={"validator": should_not_run},
        )

    assert result["enabled"] is False
    assert result["allowed"] is True
    assert result["scvl"]["enabled"] is False


def test_flag_enabled_allows_coherent_candidate():
    with EnvFlag("true"):
        result = apply_scvl_promotion_gate(
            candidate={"id": "c2", "text": "coherent memory candidate"},
            context={"validator": coherent_validator},
        )

    assert result["enabled"] is True
    assert result["allowed"] is True
    assert result["scvl"]["passed"] is True
    assert result["scvl"]["score"] == 0.93


def test_flag_enabled_blocks_incoherent_candidate():
    with EnvFlag("true"):
        result = apply_scvl_promotion_gate(
            candidate={"id": "c3", "text": "contradictory memory candidate"},
            context={"validator": incoherent_validator},
        )

    assert result["enabled"] is True
    assert result["allowed"] is False
    assert result["scvl"]["passed"] is False
    assert result["scvl"]["reason"] == "reject_incoherent_candidate"


def test_missing_text_blocks_closed_when_enabled():
    with EnvFlag("true"):
        result = apply_scvl_promotion_gate(
            candidate={"id": "c4"},
            context={"validator": coherent_validator},
        )

    assert result["allowed"] is False
    assert result["scvl"]["reason"] == "missing_text"


def test_validator_exception_blocks_closed_when_enabled():
    with EnvFlag("true"):
        result = apply_scvl_promotion_gate(
            candidate={"id": "c5", "text": "candidate text"},
            context={"validator": exception_validator},
        )

    assert result["allowed"] is False
    assert result["scvl"]["reason"] == "scvl_exception"


def test_promote_record_blocks_before_jsonl_or_faiss_write():
    original_gate = faiss_module.apply_scvl_promotion_gate
    calls = {"add_to_index": 0}

    def blocked_gate(**kwargs):
        return {
            "enabled": True,
            "allowed": False,
            "scvl": {"enabled": True, "passed": False, "reason": "test_block"},
        }

    try:
        faiss_module.apply_scvl_promotion_gate = blocked_gate
        with tempfile.TemporaryDirectory() as tmp:
            mem = _semantic_memory_without_faiss(Path(tmp) / "semantic")

            def fake_add_to_index(record_id, text):
                calls["add_to_index"] += 1

            mem._add_to_index = fake_add_to_index
            result = mem.promote_record({"id": "blocked", "text": "blocked text"}, rebuild=True)

            assert result["ok"] is False
            assert result["inserted"] is False
            assert result["error"] == "scvl_promotion_blocked"
            assert result["scvl"]["reason"] == "test_block"
            assert calls["add_to_index"] == 0
            assert not mem.records_path.exists()
    finally:
        faiss_module.apply_scvl_promotion_gate = original_gate


def test_promote_record_legacy_path_unchanged_when_flag_disabled():
    original_gate = faiss_module.apply_scvl_promotion_gate
    calls = {"add_to_index": 0}

    def disabled_gate(**kwargs):
        return {"enabled": False, "allowed": True, "scvl": {"enabled": False}}

    try:
        faiss_module.apply_scvl_promotion_gate = disabled_gate
        with tempfile.TemporaryDirectory() as tmp:
            mem = _semantic_memory_without_faiss(Path(tmp) / "semantic")

            def fake_add_to_index(record_id, text):
                calls["add_to_index"] += 1

            mem._add_to_index = fake_add_to_index
            result = mem.promote_record({"id": "allowed", "text": "allowed text"}, rebuild=True)

            assert result["ok"] is True
            assert result["inserted"] is True
            assert calls["add_to_index"] == 1
            rows = [json.loads(line) for line in mem.records_path.read_text(encoding="utf-8").splitlines()]
            assert len(rows) == 1
            assert rows[0]["id"] == "allowed"
            assert "scvl" not in rows[0].get("metadata", {})
    finally:
        faiss_module.apply_scvl_promotion_gate = original_gate


def test_static_no_dangerous_tokens_in_gate_module():
    source = (TMP_AGENT / "brain_v9" / "core" / "scvl_promotion_gate.py").read_text(encoding="utf-8")
    forbidden = [
        "dry_run_only " + "= False",
        "dry_run_only" + "=False",
        "curated_memory",
        "GITHUB" + "_TOKEN",
        "api." + "github.com",
        "place" + "Order",
        "submit" + "_order",
    ]
    for token in forbidden:
        assert token not in source


if __name__ == "__main__":
    test_flag_disabled_allows_without_calling_validator()
    test_flag_enabled_allows_coherent_candidate()
    test_flag_enabled_blocks_incoherent_candidate()
    test_missing_text_blocks_closed_when_enabled()
    test_validator_exception_blocks_closed_when_enabled()
    test_promote_record_blocks_before_jsonl_or_faiss_write()
    test_promote_record_legacy_path_unchanged_when_flag_disabled()
    test_static_no_dangerous_tokens_in_gate_module()
    print("SCVL_SEMANTIC_PROMOTION_GATE_01_OK")
