"""H0 contract: the HIVE inventory is factual, immutable, and non-promotional."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / "docs/audit/HIVE_NEXT_H0_CURRENT_STATE_FORENSIC_AUDIT.md"
INVENTORY = ROOT / "docs/audit/HIVE_NEXT_H0_STATIC_STRATEGY_INVENTORY.json"


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
        "REGIME_DETECTION: PRECOMPUTED_INPUT_ONLY",
        "DOWNSIDE_CORRELATION: NOT_IMPLEMENTED",
        "PAPER_DEGRADATION: NOT_IMPLEMENTED",
        "VALIDATION_LINEAGE: NOT_BOUND_TO_RANKING",
        "SELECTOR_DETERMINISM: DETERMINISTIC_FOR_IDENTICAL_INPUT",
        "NO_WINNER_DECLARED=true",
        "QC_EXECUTED=false",
        "PAPER_ORDERS_EXECUTED=false",
    ):
        assert required_finding in text

    assert "e444c6bdfab85406de7ea22d0d5d2e3e187b31adb56be64232637e474a32d1f6" in text
    assert "56eb3bf1ef42b23d68f925f6ee581d1d02555b8ce581c2598801aa3a29c19d0f" in text


def test_h0_static_strategy_inventory_is_complete_and_non_promotional():
    inventory = json.loads(INVENTORY.read_text(encoding="utf-8"))

    assert inventory["audit_mode"] == "STATIC_READ_ONLY"
    assert inventory["winner_declared"] is False
    assert inventory["source_commit"] == "8c17580fe0d530b4af3f5a5be26dcc947d0a3d71"
    assert len(inventory["candidates"]) == 25

    paths = {candidate["source_path"] for candidate in inventory["candidates"]}
    assert "tmp_agent/strategies/mean_reversion_eq/main.py" in paths
    assert "tmp_agent/strategies/trend_following/main.py" in paths
    assert all(candidate["evidence_classification"] == "RESEARCH_ONLY" for candidate in inventory["candidates"])
    assert all(len(candidate["source_sha256"]) == 64 for candidate in inventory["candidates"])
    assert len(list((ROOT / "tmp_agent/strategies").glob("**/main.py"))) == inventory["candidate_count"]

    for candidate in inventory["candidates"]:
        source = ROOT / candidate["source_path"]
        assert source.is_file()
        assert hashlib.sha256(source.read_bytes()).hexdigest() == candidate["source_sha256"]
