"""H0 contract: the HIVE inventory is factual, immutable, and non-promotional."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / "docs/audit/HIVE_NEXT_H0_CURRENT_STATE_FORENSIC_AUDIT.md"
INVENTORY = ROOT / "docs/audit/HIVE_NEXT_H0_STATIC_STRATEGY_INVENTORY.json"

AUDITED_SOURCE_HASHES = {
    "tmp_agent/brain_v9/trading/strategy_selector.py": "e444c6bdfab85406de7ea22d0d5d2e3e187b31adb56be64232637e474a32d1f6",
    "tmp_agent/brain_v9/trading/active_strategy_catalog.py": "56eb3bf1ef42b23d68f925f6ee581d1d02555b8ce581c2598801aa3a29c19d0f",
    "tmp_agent/brain_v9/trading/strategy_archive.py": "eb0186284a6980d692ab5208d6bb4271d763397de3ea11e7e0b283374a73bba3",
    "tmp_agent/brain_v9/trading/strategy_scorecard.py": "75d4f219d3d3276bb3c52abc76991319adb63d1f5a48c8154085b6b52e147f0d",
    "tmp_agent/brain_v9/trading/edge_validation.py": "4fda37ba43ac1b32590e9ff6f9c82f1bec1db95c99980a987a28da90b8d334eb",
    "tmp_agent/brain_v9/trading/context_edge_validation.py": "bd43a0cfc629e872f32a806d82fae62dcf8a8f944b2874677bb3a0544b349922",
}


def test_h0_records_exact_selector_sources_limitations_and_non_promotional_scope():
    text = AUDIT.read_text(encoding="utf-8")

    for source in (
        "strategy_selector.py",
        "active_strategy_catalog.py",
        "strategy_archive.py",
        "strategy_scorecard.py",
        "edge_validation.py",
        "context_edge_validation.py",
    ):
        assert source in text

    for required_finding in (
        "immutable audit source snapshot",
        "REGIME_DETECTION: PRECOMPUTED_INPUT_ONLY",
        "DOWNSIDE_CORRELATION: NOT_IMPLEMENTED",
        "PAPER_DEGRADATION: NOT_IMPLEMENTED",
        "VALIDATION_LINEAGE: NOT_BOUND_TO_RANKING",
        "SELECTOR_DETERMINISM: UNSAFE_ON_TIED_UNORDERABLE_CANDIDATES",
        "NO_WINNER_DECLARED=true",
        "QC_EXECUTED=false",
        "PAPER_ORDERS_EXECUTED=false",
    ):
        assert required_finding in text

    for source_path, source_sha256 in AUDITED_SOURCE_HASHES.items():
        assert source_path in text
        assert source_sha256 in text


def test_h0_static_strategy_inventory_is_complete_and_non_promotional():
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))

    assert inventory["audit_mode"] == "STATIC_READ_ONLY"
    assert inventory["winner_declared"] is False
    assert inventory["source_commit"] == "8c17580fe0d530b4af3f5a5be26dcc947d0a3d71"
    assert inventory["source_commit_role"] == "AUDIT_SOURCE_SNAPSHOT_NOT_PR_PARENT"
    assert len(inventory["candidates"]) == 25

    paths = {candidate["source_path"] for candidate in inventory["candidates"]}
    assert "tmp_agent/strategies/mean_reversion_eq/main.py" in paths
    assert "tmp_agent/strategies/trend_following/main.py" in paths
    assert all(candidate["evidence_classification"] == "RESEARCH_ONLY" for candidate in inventory["candidates"])
    assert all(len(candidate["source_sha256"]) == 64 for candidate in inventory["candidates"])
    source_commit = inventory["source_commit"]
    assert len(source_commit) == 40
    source_paths = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", source_commit, "--", "tmp_agent/strategies"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    snapshot_candidate_paths = {path for path in source_paths if path.endswith("/main.py")}
    inventory_candidate_paths = {candidate["source_path"] for candidate in inventory["candidates"]}
    assert len(inventory_candidate_paths) == inventory["candidate_count"]
    assert inventory_candidate_paths == snapshot_candidate_paths

    for candidate in inventory["candidates"]:
        completed = subprocess.run(
            ["git", "show", f"{source_commit}:{candidate['source_path']}"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        )
        assert hashlib.sha256(completed.stdout).hexdigest() == candidate["source_sha256"]

    for source_path, source_sha256 in AUDITED_SOURCE_HASHES.items():
        completed = subprocess.run(
            ["git", "show", f"{source_commit}:{source_path}"],
            cwd=ROOT,
            check=True,
            capture_output=True,
        )
        assert hashlib.sha256(completed.stdout).hexdigest() == source_sha256
