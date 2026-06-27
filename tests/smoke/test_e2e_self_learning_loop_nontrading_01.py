"""
FRONT-E2E-SELF-LEARNING-LOOP-NONTRADING-01
Non-trading E2E self-learning loop harness.

Simulates the full pipeline:
source/read-only input → staging candidate → validation → retrieval simulation
→ finalizer/evidence-use simulation → governance decision → rollback/no-write safety verification

Rules:
- No canonical memory mutation.
- No FAISS rebuild.
- No candidate promotion.
- Deterministic, isolated, uses temp/front fixtures only.
"""
import json
import os
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

# ── constants ──
ROOT = Path(r"C:\AI_VAULT_CANONICAL")
FIXTURE_DIR = ROOT / "tmp_agent/front_e2e_self_learning_loop_nontrading_01/fixtures"
MEMORY_JSONL = ROOT / "memory/semantic/semantic_memory.jsonl"
MEMORY_IDS = ROOT / "memory/semantic/semantic_memory_faiss_ids.json"
MEMORY_IDX = ROOT / "memory/semantic/semantic_memory_faiss.index"
PROMOTION_QUEUE = ROOT / "memory/promotion_queue"
SEMANTIC_STAGING = ROOT / "memory/semantic_staging"

FRONT_ID = "FRONT-E2E-SELF-LEARNING-LOOP-NONTRADING-01"

SECRETS_PATTERNS = ["ghp_", "github_pat_", "api_key=", "Authorization:", "BRAIN_ADMIN_TOKEN", "FRED_API_KEY"]
TRADING_PATTERNS = ["live_trading", "broker", "ibkr", "quantconnect", "backtester", "portfolio_manager", "financial_autonomy"]
RAW_COT_PATTERNS = ["<thinking>", "</thinking>", "<internal>", "</internal>", "raw_chain_of_thought"]


# ── helpers ──

def load_fixture(name: str) -> dict:
    path = FIXTURE_DIR / name
    assert path.is_file(), f"Fixture missing: {path}"
    return json.loads(path.read_text(encoding="utf-8"))


def stable_id(source_id: str) -> str:
    """Deterministic stable UUID from source_id."""
    return str(uuid.uuid5(uuid.NAMESPACE_OID, f"{FRONT_ID}:{source_id}"))


def sha256_text(text: str) -> str:
    import hashlib
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def get_memory_baseline() -> dict:
    import faiss
    records = [l for l in MEMORY_JSONL.read_text(encoding="utf-8").splitlines() if l.strip()]
    ids = json.loads(MEMORY_IDS.read_text(encoding="utf-8"))
    ntotal = int(faiss.read_index(str(MEMORY_IDX)).ntotal)
    blank = sum(1 for r in records if json.loads(r).get("text", "").strip() == "")
    dup = len(records) - len({json.loads(r).get("id", "") for r in records})
    return {
        "records": len(records),
        "ids": len(ids),
        "ntotal": ntotal,
        "blank": blank,
        "dup": dup,
    }


# ── pipeline stages ──

def stage_a_source_read() -> list:
    """Read 3 fixture source items."""
    sources = [
        load_fixture("source_1_governance_security.json"),
        load_fixture("source_2_memory_quality.json"),
        load_fixture("source_3_routing_finalizer.json"),
    ]
    return sources


def stage_b_build_candidates(sources: list, staging_dir: Path) -> list:
    """Build staging candidates in isolated directory."""
    candidates = []
    for src in sources:
        cand = {
            "candidate_id": stable_id(src["source_id"]),
            "source_id": src["source_id"],
            "topic": src["topic"],
            "text": src["text"],
            "provider": src["provider"],
            "retrieved_at": src["retrieved_at"],
            "metadata": {
                **src["metadata"],
                "front_id": FRONT_ID,
                "staging_path": str(staging_dir),
            },
            "state": "candidate_staged",
            "label": "unverified_e2e_candidate",
            "real_write_allowed": False,
            "faiss_write_allowed": False,
            "memory_write_allowed": False,
            "promotion_allowed": False,
            "dry_run_only": True,
        }
        candidates.append(cand)
    # Write to isolated staging
    staging_dir.mkdir(parents=True, exist_ok=True)
    (staging_dir / "candidates.json").write_text(json.dumps(candidates, indent=2), encoding="utf-8")
    (staging_dir / "candidates.jsonl").write_text(
        "\n".join(json.dumps(c) for c in candidates), encoding="utf-8"
    )
    return candidates


def stage_c_validate(candidates: list) -> dict:
    """Validate candidates without mutating canonical memory."""
    results = {
        "all_valid": True,
        "errors": [],
        "warnings": [],
    }
    for cand in candidates:
        # C1: non-empty text
        if not cand.get("text", "").strip():
            results["errors"].append(f"{cand['candidate_id']}: empty text")
            results["all_valid"] = False
        # C2: stable id
        if not cand.get("candidate_id"):
            results["errors"].append(f"missing candidate_id")
            results["all_valid"] = False
        # C3: source metadata
        if not cand.get("metadata", {}).get("source_type"):
            results["warnings"].append(f"{cand['candidate_id']}: missing source_type")
        # C4: trust label
        if cand.get("metadata", {}).get("trust_label") not in ("verified", "unverified", "rejected"):
            results["warnings"].append(f"{cand['candidate_id']}: unexpected trust_label")
        # C5-C7: no secrets, no raw CoT, no trading
        raw = json.dumps(cand)
        for pat in SECRETS_PATTERNS:
            if pat in raw:
                results["errors"].append(f"{cand['candidate_id']}: secret marker '{pat}' found")
                results["all_valid"] = False
        for pat in RAW_COT_PATTERNS:
            if pat in raw.lower():
                results["warnings"].append(f"{cand['candidate_id']}: raw CoT marker '{pat}' found")
        for pat in TRADING_PATTERNS:
            if pat in raw.lower():
                results["errors"].append(f"{cand['candidate_id']}: trading marker '{pat}' found")
                results["all_valid"] = False
    return results


import re


STOP_WORDS = {"the", "a", "an", "is", "are", "was", "were", "be", "been", "being", "have", "has", "had", "do", "does", "did", "will", "would", "could", "should", "may", "might", "must", "shall", "can", "need", "dare", "ought", "used", "to", "of", "in", "for", "on", "with", "at", "by", "from", "as", "into", "through", "during", "before", "after", "above", "below", "between", "under", "again", "further", "then", "once", "here", "there", "when", "where", "why", "how", "all", "each", "few", "more", "most", "other", "some", "such", "no", "nor", "not", "only", "own", "same", "so", "than", "too", "very", "just", "and", "but", "if", "or", "because", "until", "while", "what", "which", "who", "whom", "this", "that", "these", "those", "am", "it", "its", "i", "me", "my", "we", "our", "you", "your", "he", "him", "his", "she", "her", "they", "them", "their"}


def stage_d_retrieval_simulation(candidates: list, query: str) -> list:
    """Simulate retrieval using in-memory keyword overlap (no FAISS touch). Stop words excluded."""
    def _tokens(text: str) -> set:
        return set(re.sub(r"[^\w\s]", "", text.lower()).split()) - STOP_WORDS
    query_tokens = _tokens(query)
    scored = []
    for cand in candidates:
        cand_tokens = _tokens(cand["text"])
        overlap = len(query_tokens & cand_tokens)
        scored.append((overlap, cand))
    scored.sort(key=lambda x: (-x[0], x[1]["candidate_id"]))
    return [cand for _, cand in scored]


def stage_e_finalizer_evidence_simulation(retrieved: list, query: str) -> dict:
    """Simulate finalizer: Brain-specific queries use evidence; generic queries answer directly."""
    brain_keywords = ["brain", "security", "operator", "dev endpoint", "governance", "memory", "routing"]
    is_brain_specific = any(kw in query.lower() for kw in brain_keywords)
    if is_brain_specific and retrieved:
        top = retrieved[0]
        return {
            "mode": "evidence_based",
            "answer": f"Based on evidence [{top['candidate_id']}]: {top['text'][:200]}...",
            "evidence_used": True,
            "candidate_ids": [top["candidate_id"]],
        }
    else:
        return {
            "mode": "direct",
            "answer": "Direct answer without memory evidence.",
            "evidence_used": False,
            "candidate_ids": [],
        }


def stage_f_governance_decision(candidates: list) -> dict:
    """Governance: DRY_RUN_ONLY, no write, no promotion."""
    return {
        "decision": "DRY_RUN_ONLY",
        "write_performed": False,
        "promotion_performed": False,
        "candidate_count": len(candidates),
        "approved_ids": [],
        "rejected_ids": [],
        "notes": "E2E simulation only. No canonical mutation.",
    }


# ── tests ──

def test_source_fixtures_load():
    sources = stage_a_source_read()
    assert len(sources) == 3
    print("PASS: source_fixtures_load")


def test_exactly_three_source_items():
    sources = stage_a_source_read()
    assert len(sources) == 3, f"Expected 3 sources, got {len(sources)}"
    print("PASS: exactly_three_source_items")


def test_candidates_built_in_isolated_staging():
    with tempfile.TemporaryDirectory() as td:
        staging = Path(td) / "staging"
        sources = stage_a_source_read()
        candidates = stage_b_build_candidates(sources, staging)
        assert staging.is_dir()
        assert (staging / "candidates.json").is_file()
        assert (staging / "candidates.jsonl").is_file()
        assert len(candidates) == 3
    print("PASS: candidates_built_in_isolated_staging")


def test_candidate_ids_stable_and_nonempty():
    sources = stage_a_source_read()
    with tempfile.TemporaryDirectory() as td:
        candidates = stage_b_build_candidates(sources, Path(td) / "staging")
        for c in candidates:
            assert c["candidate_id"], "candidate_id must be non-empty"
            # stability: same source → same id
            cid2 = stable_id(c["source_id"])
            assert c["candidate_id"] == cid2, f"ID unstable: {c['candidate_id']} != {cid2}"
    print("PASS: candidate_ids_stable_and_nonempty")


def test_candidate_texts_nonempty():
    sources = stage_a_source_read()
    with tempfile.TemporaryDirectory() as td:
        candidates = stage_b_build_candidates(sources, Path(td) / "staging")
        for c in candidates:
            assert c["text"].strip(), f"candidate {c['candidate_id']} has empty text"
    print("PASS: candidate_texts_nonempty")


def test_candidate_metadata_includes_source_trust_front():
    sources = stage_a_source_read()
    with tempfile.TemporaryDirectory() as td:
        candidates = stage_b_build_candidates(sources, Path(td) / "staging")
        for c in candidates:
            assert c["metadata"]["source_type"]
            assert c["metadata"]["trust_label"]
            assert c["metadata"]["front_id"] == FRONT_ID
    print("PASS: candidate_metadata_includes_source_trust_front")


def test_no_secret_markers_in_candidates():
    sources = stage_a_source_read()
    with tempfile.TemporaryDirectory() as td:
        candidates = stage_b_build_candidates(sources, Path(td) / "staging")
        for c in candidates:
            raw = json.dumps(c)
            for pat in SECRETS_PATTERNS:
                assert pat not in raw, f"secret marker '{pat}' in candidate {c['candidate_id']}"
    print("PASS: no_secret_markers_in_candidates")


def test_no_raw_cot_in_candidates():
    sources = stage_a_source_read()
    with tempfile.TemporaryDirectory() as td:
        candidates = stage_b_build_candidates(sources, Path(td) / "staging")
        for c in candidates:
            raw = json.dumps(c).lower()
            for pat in RAW_COT_PATTERNS:
                assert pat not in raw, f"raw CoT marker '{pat}' in candidate {c['candidate_id']}"
    print("PASS: no_raw_cot_in_candidates")


def test_no_trading_content_in_candidates():
    sources = stage_a_source_read()
    with tempfile.TemporaryDirectory() as td:
        candidates = stage_b_build_candidates(sources, Path(td) / "staging")
        for c in candidates:
            raw = json.dumps(c).lower()
            for pat in TRADING_PATTERNS:
                assert pat not in raw, f"trading marker '{pat}' in candidate {c['candidate_id']}"
    print("PASS: no_trading_content_in_candidates")


def test_validation_accepts_all_three():
    sources = stage_a_source_read()
    with tempfile.TemporaryDirectory() as td:
        candidates = stage_b_build_candidates(sources, Path(td) / "staging")
        result = stage_c_validate(candidates)
        assert result["all_valid"], f"Validation failed: {result['errors']}"
    print("PASS: validation_accepts_all_three")


def test_retrieval_simulation_returns_expected_for_brain_query():
    sources = stage_a_source_read()
    with tempfile.TemporaryDirectory() as td:
        candidates = stage_b_build_candidates(sources, Path(td) / "staging")
        result = stage_c_validate(candidates)
        assert result["all_valid"]
        # Query with words present in governance source text
        retrieved = stage_d_retrieval_simulation(candidates, "How does the backend use auth?")
        assert len(retrieved) >= 1
        # Top should be governance security (most overlap with "backend", "auth")
        assert "StrictOperatorAccess" in retrieved[0]["text"]
    print("PASS: retrieval_simulation_returns_expected_for_brain_query")


def test_retrieval_does_not_contaminate_generic_query():
    sources = stage_a_source_read()
    with tempfile.TemporaryDirectory() as td:
        candidates = stage_b_build_candidates(sources, Path(td) / "staging")
        result = stage_c_validate(candidates)
        assert result["all_valid"]
        # Generic query: after stop-word removal, no content overlap expected
        retrieved = stage_d_retrieval_simulation(candidates, "What is the weather today?")
        # Top candidate should have 0 overlap (all do, but verify top)
        top = retrieved[0]
        top_tokens = set(re.sub(r"[^\w\s]", "", top["text"].lower()).split()) - STOP_WORDS
        query_tokens = set(re.sub(r"[^\w\s]", "", "What is the weather today?".lower()).split()) - STOP_WORDS
        assert len(query_tokens & top_tokens) == 0, (
            f"Generic query contaminated top candidate with overlap: {query_tokens & top_tokens}"
        )
    print("PASS: retrieval_does_not_contaminate_generic_query")


def test_finalizer_uses_evidence_for_brain_specific_query():
    sources = stage_a_source_read()
    with tempfile.TemporaryDirectory() as td:
        candidates = stage_b_build_candidates(sources, Path(td) / "staging")
        retrieved = stage_d_retrieval_simulation(candidates, "How does StrictOperatorAccess work?")
        final = stage_e_finalizer_evidence_simulation(retrieved, "How does StrictOperatorAccess work?")
        assert final["mode"] == "evidence_based"
        assert final["evidence_used"] is True
        assert len(final["candidate_ids"]) >= 1
    print("PASS: finalizer_uses_evidence_for_brain_specific_query")


def test_finalizer_answers_generic_query_directly():
    sources = stage_a_source_read()
    with tempfile.TemporaryDirectory() as td:
        candidates = stage_b_build_candidates(sources, Path(td) / "staging")
        retrieved = stage_d_retrieval_simulation(candidates, "What is 2+2?")
        final = stage_e_finalizer_evidence_simulation(retrieved, "What is 2+2?")
        assert final["mode"] == "direct"
        assert final["evidence_used"] is False
        assert len(final["candidate_ids"]) == 0
    print("PASS: finalizer_answers_generic_query_directly")


def test_governance_decision_remains_dry_run_only():
    sources = stage_a_source_read()
    with tempfile.TemporaryDirectory() as td:
        candidates = stage_b_build_candidates(sources, Path(td) / "staging")
        decision = stage_f_governance_decision(candidates)
        assert decision["decision"] == "DRY_RUN_ONLY"
    print("PASS: governance_decision_remains_dry_run_only")


def test_write_performed_false():
    sources = stage_a_source_read()
    with tempfile.TemporaryDirectory() as td:
        candidates = stage_b_build_candidates(sources, Path(td) / "staging")
        decision = stage_f_governance_decision(candidates)
        assert decision["write_performed"] is False
    print("PASS: write_performed_false")


def test_promotion_performed_false():
    sources = stage_a_source_read()
    with tempfile.TemporaryDirectory() as td:
        candidates = stage_b_build_candidates(sources, Path(td) / "staging")
        decision = stage_f_governance_decision(candidates)
        assert decision["promotion_performed"] is False
    print("PASS: promotion_performed_false")


# ── canonical no-mutation guards ──

def test_canonical_memory_records_unchanged():
    pre = get_memory_baseline()
    # Run full pipeline (isolated, no canonical writes)
    sources = stage_a_source_read()
    with tempfile.TemporaryDirectory() as td:
        candidates = stage_b_build_candidates(sources, Path(td) / "staging")
        stage_c_validate(candidates)
        stage_d_retrieval_simulation(candidates, "test")
        stage_e_finalizer_evidence_simulation(candidates, "test")
        stage_f_governance_decision(candidates)
    post = get_memory_baseline()
    assert post["records"] == pre["records"], f"Memory records changed: {pre['records']} -> {post['records']}"
    print("PASS: canonical_memory_records_unchanged")


def test_canonical_faiss_ids_unchanged():
    pre = get_memory_baseline()
    sources = stage_a_source_read()
    with tempfile.TemporaryDirectory() as td:
        candidates = stage_b_build_candidates(sources, Path(td) / "staging")
        stage_c_validate(candidates)
    post = get_memory_baseline()
    assert post["ids"] == pre["ids"], f"FAISS ids changed: {pre['ids']} -> {post['ids']}"
    print("PASS: canonical_faiss_ids_unchanged")


def test_canonical_faiss_ntotal_unchanged():
    pre = get_memory_baseline()
    sources = stage_a_source_read()
    with tempfile.TemporaryDirectory() as td:
        candidates = stage_b_build_candidates(sources, Path(td) / "staging")
        stage_c_validate(candidates)
    post = get_memory_baseline()
    assert post["ntotal"] == pre["ntotal"], f"FAISS ntotal changed: {pre['ntotal']} -> {post['ntotal']}"
    print("PASS: canonical_faiss_ntotal_unchanged")


def test_blank_text_count_remains_zero():
    pre = get_memory_baseline()
    sources = stage_a_source_read()
    with tempfile.TemporaryDirectory() as td:
        candidates = stage_b_build_candidates(sources, Path(td) / "staging")
        stage_c_validate(candidates)
    post = get_memory_baseline()
    assert post["blank"] == 0, f"blank_text_count non-zero: {post['blank']}"
    assert post["blank"] == pre["blank"]
    print("PASS: blank_text_count_remains_zero")


def test_duplicate_id_count_remains_zero():
    pre = get_memory_baseline()
    sources = stage_a_source_read()
    with tempfile.TemporaryDirectory() as td:
        candidates = stage_b_build_candidates(sources, Path(td) / "staging")
        stage_c_validate(candidates)
    post = get_memory_baseline()
    assert post["dup"] == 0, f"duplicate_id_count non-zero: {post['dup']}"
    assert post["dup"] == pre["dup"]
    print("PASS: duplicate_id_count_remains_zero")


def test_memory_semantic_git_status_clean():
    result = subprocess.run(
        ["git", "status", "--short", "--", str(MEMORY_JSONL.parent)],
        cwd=str(ROOT), capture_output=True, text=True,
    )
    staged = [l for l in result.stdout.splitlines() if l.strip().startswith(("A", "M", "D"))]
    assert not staged, f"memory/semantic dirty/staged: {staged}"
    print("PASS: memory_semantic_git_status_clean")


def test_promotion_queue_git_status_clean():
    result = subprocess.run(
        ["git", "status", "--short", "--", str(PROMOTION_QUEUE)],
        cwd=str(ROOT), capture_output=True, text=True,
    )
    staged = [l for l in result.stdout.splitlines() if l.strip().startswith(("A", "M", "D"))]
    assert not staged, f"promotion_queue dirty/staged: {staged}"
    print("PASS: promotion_queue_git_status_clean")


def test_semantic_staging_git_status_clean():
    result = subprocess.run(
        ["git", "status", "--short", "--", str(SEMANTIC_STAGING)],
        cwd=str(ROOT), capture_output=True, text=True,
    )
    staged = [l for l in result.stdout.splitlines() if l.strip().startswith(("A", "M", "D"))]
    assert not staged, f"semantic_staging dirty/staged: {staged}"
    print("PASS: semantic_staging_git_status_clean")


def test_no_trading_files_touched():
    result = subprocess.run(
        ["git", "diff", "--name-only", "HEAD"],
        cwd=str(ROOT), capture_output=True, text=True,
    )
    dirty = result.stdout.splitlines()
    trading_dirty = [f for f in dirty if any(p in f.lower() for p in TRADING_PATTERNS)]
    assert not trading_dirty, f"Trading files touched: {trading_dirty}"
    print("PASS: no_trading_files_touched")


def test_guard_passes():
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/git_hygiene/check_no_sensitive_paths_staged.py")],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, f"Guard failed:\n{result.stdout}\n{result.stderr}"
    print("PASS: guard_passes")


if __name__ == "__main__":
    test_source_fixtures_load()
    test_exactly_three_source_items()
    test_candidates_built_in_isolated_staging()
    test_candidate_ids_stable_and_nonempty()
    test_candidate_texts_nonempty()
    test_candidate_metadata_includes_source_trust_front()
    test_no_secret_markers_in_candidates()
    test_no_raw_cot_in_candidates()
    test_no_trading_content_in_candidates()
    test_validation_accepts_all_three()
    test_retrieval_simulation_returns_expected_for_brain_query()
    test_retrieval_does_not_contaminate_generic_query()
    test_finalizer_uses_evidence_for_brain_specific_query()
    test_finalizer_answers_generic_query_directly()
    test_governance_decision_remains_dry_run_only()
    test_write_performed_false()
    test_promotion_performed_false()
    test_canonical_memory_records_unchanged()
    test_canonical_faiss_ids_unchanged()
    test_canonical_faiss_ntotal_unchanged()
    test_blank_text_count_remains_zero()
    test_duplicate_id_count_remains_zero()
    test_memory_semantic_git_status_clean()
    test_promotion_queue_git_status_clean()
    test_semantic_staging_git_status_clean()
    test_no_trading_files_touched()
    test_guard_passes()
    print("\nALL 27 E2E SELF-LEARNING LOOP TESTS PASSED")
