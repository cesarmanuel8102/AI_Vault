import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "tests" / "fixtures" / "memory_faiss_retrieval_quality_pack_v1.json"
SEMANTIC_DIR = ROOT / "memory" / "semantic"
SEMANTIC_JSONL = SEMANTIC_DIR / "semantic_memory.jsonl"
FAISS_INDEX = SEMANTIC_DIR / "semantic_memory_faiss.index"
FAISS_IDS = SEMANTIC_DIR / "semantic_memory_faiss_ids.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git(args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def test_01_pack_shape_and_read_only_policy():
    data = json.loads(PACK.read_text(encoding="utf-8"))
    assert data["pack_id"] == "memory_faiss_retrieval_quality_pack_v1"
    assert data["mode"] == "read_only_quality_spec"
    assert len(data["evaluation_queries"]) >= 5
    policy = data["mutation_policy"]
    assert policy["semantic_memory_write_allowed"] is False
    assert policy["faiss_write_allowed"] is False
    assert policy["embedding_creation_allowed"] is False
    assert policy["reindex_allowed"] is False


def test_02_memory_artifacts_exist_and_are_readable():
    assert SEMANTIC_JSONL.exists()
    assert FAISS_INDEX.exists()
    assert FAISS_IDS.exists()
    assert SEMANTIC_JSONL.stat().st_size > 0
    assert FAISS_INDEX.stat().st_size > 0
    assert FAISS_IDS.stat().st_size > 0


def test_03_counts_are_positive_without_mutation():
    before = {p.name: _sha256(p) for p in (SEMANTIC_JSONL, FAISS_INDEX, FAISS_IDS)}
    line_count = sum(1 for _ in SEMANTIC_JSONL.open("r", encoding="utf-8"))
    ids = json.loads(FAISS_IDS.read_text(encoding="utf-8"))
    id_count = len(ids) if isinstance(ids, list) else len(ids.keys())
    after = {p.name: _sha256(p) for p in (SEMANTIC_JSONL, FAISS_INDEX, FAISS_IDS)}
    assert before == after
    assert line_count > 0
    assert id_count > 0


def test_04_no_protected_paths_staged():
    staged = _git(["diff", "--cached", "--name-only"]).replace("\\", "/")
    assert "memory/semantic" not in staged
    assert "trading/" not in staged
    assert "B8/" not in staged
    assert "tmp_agent/strategies" not in staged
