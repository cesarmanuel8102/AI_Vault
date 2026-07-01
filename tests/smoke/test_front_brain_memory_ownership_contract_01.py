import json
import sys
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tmp_agent"))


def test_semantic_memory_exposes_public_promote_record_boundary(tmp_path, monkeypatch):
    from brain_v9.core.semantic_memory_faiss import SemanticMemoryFAISS

    mem = SemanticMemoryFAISS(root=tmp_path / "semantic", dims=3, ollama_url="http://127.0.0.1:9")
    monkeypatch.setattr(mem, "embed_text", lambda _text: np.array([1.0, 0.0, 0.0], dtype=np.float32))

    result = mem.promote_record(
        {
            "id": "candidate_contract_001",
            "text": "contract test promoted record",
            "source": "contract_test",
            "session_id": "contract",
            "kind": "canonical_candidate",
            "metadata": {"test": True},
        }
    )

    assert result["ok"] is True
    assert result["inserted"] is True
    assert result["id"] == "candidate_contract_001"

    records = [
        json.loads(line)
        for line in mem.records_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(records) == 1
    assert records[0]["id"] == "candidate_contract_001"

    mem._ensure_index_loaded()
    assert mem._index is not None
    assert mem._index.ntotal == 1
    assert mem._ids == ["candidate_contract_001"]


def test_promotion_candidate_promoter_does_not_call_private_faiss_add_to_index():
    source = (ROOT / "tmp_agent/brain_v9/memory/promotion_candidate_promoter.py").read_text(encoding="utf-8")
    assert "mem.promote_record(" in source
    assert "mem._add_to_index(" not in source
