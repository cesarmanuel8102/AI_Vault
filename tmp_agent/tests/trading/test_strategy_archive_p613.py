"""
P6-13 — Tests for brain_v9/trading/strategy_archive.py

Covers:
  - _utc_now helper
  - build_strategy_archive: classification into archived/active/watchlist/testing,
    archive reasons, payload structure, summary counts, write_json call
  - read_strategy_archive: happy path, missing file, corrupt file
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import MagicMock, patch

import pytest

from brain_v9.trading.strategy_archive import (
    _utc_now,
    build_strategy_archive,
    read_strategy_archive,
    ARCHIVE_PATH,
)


# ── _utc_now ────────────────────────────────────────────────────────

class TestUtcNow:
    def test_returns_iso_string(self):
        ts = _utc_now()
        assert isinstance(ts, str)
        assert "T" in ts

    def test_ends_with_z(self):
        assert _utc_now().endswith("Z")

    def test_parseable(self):
        dt = datetime.fromisoformat(_utc_now().replace("Z", "+00:00"))
        assert dt.tzinfo is not None


# ── helpers ─────────────────────────────────────────────────────────

def _strategy(sid: str = "s1", venue: str = "PocketOption", family: str = "trend",
              min_resolved_trades: int = 20, **kw) -> Dict[str, Any]:
    base: Dict[str, Any] = {
        "strategy_id": sid,
        "venue": venue,
        "family": family,
        "success_criteria": {"min_resolved_trades": min_resolved_trades},
    }
    base.update(kw)
    return base


def _cards(**entries: Dict[str, Any]) -> Dict[str, Any]:
    """Build a scorecards wrapper: { "scorecards": { sid: card, ... } }"""
    return {"scorecards": entries}


def _card(entries_resolved: int = 0, expectancy: float = 0.0,
          governance_state: str = "paper_candidate") -> Dict[str, Any]:
    return {
        "entries_resolved": entries_resolved,
        "expectancy": expectancy,
        "governance_state": governance_state,
    }


def _hyp_results(*items: Dict[str, Any]) -> Dict[str, Any]:
    return {"results": list(items)}


def _hyp_item(strategy_id: str, status: str) -> Dict[str, Any]:
    return {"strategy_id": strategy_id, "status": status}


# ── build_strategy_archive — classification ─────────────────────────

class TestClassificationActive:
    """paper_active or promote_candidate → active bucket"""

    @patch("brain_v9.trading.strategy_archive.write_json")
    def test_paper_active_classified_as_active(self, mock_wj: MagicMock):
        out = build_strategy_archive(
            [_strategy("s1")],
            _cards(s1=_card(governance_state="paper_active")),
            _hyp_results(),
        )
        assert len(out["active"]) == 1
        assert out["active"][0]["archive_state"] == "active"

    @patch("brain_v9.trading.strategy_archive.write_json")
    def test_promote_candidate_classified_as_active(self, mock_wj: MagicMock):
        out = build_strategy_archive(
            [_strategy("s1")],
            _cards(s1=_card(governance_state="promote_candidate")),
            _hyp_results(),
        )
        assert len(out["active"]) == 1


class TestClassificationWatchlist:
    """paper_watch → watchlist bucket"""

    @patch("brain_v9.trading.strategy_archive.write_json")
    def test_paper_watch_in_watchlist(self, mock_wj: MagicMock):
        out = build_strategy_archive(
            [_strategy("s1")],
            _cards(s1=_card(governance_state="paper_watch")),
            _hyp_results(),
        )
        assert len(out["watchlist"]) == 1
        assert out["watchlist"][0]["archive_state"] == "watch"


class TestClassificationTesting:
    """Any other state (paper_candidate, paper_probe, etc.) → testing"""

    @patch("brain_v9.trading.strategy_archive.write_json")
    def test_paper_candidate_in_testing(self, mock_wj: MagicMock):
        out = build_strategy_archive(
            [_strategy("s1")],
            _cards(s1=_card(governance_state="paper_candidate")),
            _hyp_results(),
        )
        assert len(out["testing"]) == 1
        assert out["testing"][0]["archive_state"] == "testing"

    @patch("brain_v9.trading.strategy_archive.write_json")
    def test_paper_probe_in_testing(self, mock_wj: MagicMock):
        out = build_strategy_archive(
            [_strategy("s1")],
            _cards(s1=_card(governance_state="paper_probe")),
            _hyp_results(),
        )
        assert len(out["testing"]) == 1


# ── build_strategy_archive — archive reasons ────────────────────────

class TestArchiveRefuted:
    """frozen + resolved >= min_resolved + expectancy <= 0 → archived_refuted"""

    @patch("brain_v9.trading.strategy_archive.write_json")
    def test_frozen_negative_expectancy_archived(self, mock_wj: MagicMock):
        out = build_strategy_archive(
            [_strategy("s1", min_resolved_trades=20)],
            _cards(s1=_card(governance_state="frozen", entries_resolved=25, expectancy=-0.5)),
            _hyp_results(),
        )
        assert len(out["archived"]) == 1
        assert out["archived"][0]["archive_reason"] == "refuted_after_minimum_sample"

    @patch("brain_v9.trading.strategy_archive.write_json")
    def test_frozen_zero_expectancy_archived(self, mock_wj: MagicMock):
        out = build_strategy_archive(
            [_strategy("s1", min_resolved_trades=20)],
            _cards(s1=_card(governance_state="frozen", entries_resolved=20, expectancy=0.0)),
            _hyp_results(),
        )
        assert len(out["archived"]) == 1

    @patch("brain_v9.trading.strategy_archive.write_json")
    def test_frozen_positive_expectancy_not_archived(self, mock_wj: MagicMock):
        out = build_strategy_archive(
            [_strategy("s1", min_resolved_trades=20)],
            _cards(s1=_card(governance_state="frozen", entries_resolved=25, expectancy=0.5)),
            _hyp_results(),
        )
        assert len(out["archived"]) == 0

    @patch("brain_v9.trading.strategy_archive.write_json")
    def test_frozen_below_min_resolved_not_archived(self, mock_wj: MagicMock):
        out = build_strategy_archive(
            [_strategy("s1", min_resolved_trades=20)],
            _cards(s1=_card(governance_state="frozen", entries_resolved=10, expectancy=-0.5)),
            _hyp_results(),
        )
        assert len(out["archived"]) == 0
        assert len(out["testing"]) == 1  # goes to testing since frozen is not active/watch


class TestArchiveHypothesisFailed:
    """hypothesis status=fail and resolved >= max(10, min_resolved//2) → archived"""

    @patch("brain_v9.trading.strategy_archive.write_json")
    def test_hypothesis_failed_with_material_sample(self, mock_wj: MagicMock):
        out = build_strategy_archive(
            [_strategy("s1", min_resolved_trades=20)],
            _cards(s1=_card(governance_state="paper_candidate", entries_resolved=10, expectancy=-0.1)),
            _hyp_results(_hyp_item("s1", "fail")),
        )
        assert len(out["archived"]) == 1
        assert out["archived"][0]["archive_reason"] == "hypothesis_failed_with_material_sample"

    @patch("brain_v9.trading.strategy_archive.write_json")
    def test_hypothesis_failed_below_threshold_not_archived(self, mock_wj: MagicMock):
        # min_resolved=20, half=10, max(10,10)=10 → need >= 10, have 9
        out = build_strategy_archive(
            [_strategy("s1", min_resolved_trades=20)],
            _cards(s1=_card(governance_state="paper_candidate", entries_resolved=9, expectancy=-0.1)),
            _hyp_results(_hyp_item("s1", "fail")),
        )
        assert len(out["archived"]) == 0

    @patch("brain_v9.trading.strategy_archive.write_json")
    def test_hypothesis_pass_not_archived(self, mock_wj: MagicMock):
        out = build_strategy_archive(
            [_strategy("s1", min_resolved_trades=20)],
            _cards(s1=_card(governance_state="paper_candidate", entries_resolved=30, expectancy=0.5)),
            _hyp_results(_hyp_item("s1", "pass")),
        )
        assert len(out["archived"]) == 0


class TestArchivePriority:
    """Frozen-archive takes priority over hypothesis-archive (first condition wins)"""

    @patch("brain_v9.trading.strategy_archive.write_json")
    def test_frozen_archive_reason_wins(self, mock_wj: MagicMock):
        out = build_strategy_archive(
            [_strategy("s1", min_resolved_trades=20)],
            _cards(s1=_card(governance_state="frozen", entries_resolved=25, expectancy=-0.5)),
            _hyp_results(_hyp_item("s1", "fail")),
        )
        assert out["archived"][0]["archive_reason"] == "refuted_after_minimum_sample"


# ── build_strategy_archive — item fields ────────────────────────────

class TestItemFields:
    @patch("brain_v9.trading.strategy_archive.write_json")
    def test_all_fields_present(self, mock_wj: MagicMock):
        out = build_strategy_archive(
            [_strategy("s1", venue="IBKR", family="breakout")],
            _cards(s1=_card(governance_state="paper_active", entries_resolved=15, expectancy=0.3)),
            _hyp_results(_hyp_item("s1", "in_test")),
        )
        item = out["active"][0]
        assert item["strategy_id"] == "s1"
        assert item["venue"] == "IBKR"
        assert item["family"] == "breakout"
        assert item["governance_state"] == "paper_active"
        assert item["entries_resolved"] == 15
        assert item["expectancy"] == 0.3
        assert item["hypothesis_status"] == "in_test"
        assert item["archive_state"] == "active"


# ── build_strategy_archive — payload structure ──────────────────────

class TestPayloadStructure:
    @patch("brain_v9.trading.strategy_archive.write_json")
    def test_schema_version(self, mock_wj: MagicMock):
        out = build_strategy_archive([], {}, {})
        assert out["schema_version"] == "strategy_archive_v1"

    @patch("brain_v9.trading.strategy_archive.write_json")
    def test_generated_utc_present(self, mock_wj: MagicMock):
        out = build_strategy_archive([], {}, {})
        assert "generated_utc" in out
        assert isinstance(out["generated_utc"], str)

    @patch("brain_v9.trading.strategy_archive.write_json")
    def test_all_bucket_keys(self, mock_wj: MagicMock):
        out = build_strategy_archive([], {}, {})
        for key in ("archived", "active", "watchlist", "testing"):
            assert key in out
            assert isinstance(out[key], list)

    @patch("brain_v9.trading.strategy_archive.write_json")
    def test_summary_counts(self, mock_wj: MagicMock):
        strategies = [
            _strategy("s1"), _strategy("s2"), _strategy("s3"), _strategy("s4"),
        ]
        cards = _cards(
            s1=_card(governance_state="paper_active"),
            s2=_card(governance_state="paper_watch"),
            s3=_card(governance_state="paper_candidate"),
            s4=_card(governance_state="frozen", entries_resolved=30, expectancy=-1.0),
        )
        out = build_strategy_archive(strategies, cards, _hyp_results())
        s = out["summary"]
        assert s["active_count"] == 1
        assert s["watch_count"] == 1
        assert s["testing_count"] == 1
        assert s["archived_count"] == 1

    @patch("brain_v9.trading.strategy_archive.write_json")
    def test_empty_strategies(self, mock_wj: MagicMock):
        out = build_strategy_archive([], {}, {})
        assert out["summary"] == {
            "archived_count": 0, "active_count": 0,
            "watch_count": 0, "testing_count": 0,
        }


# ── build_strategy_archive — write_json call ────────────────────────

class TestBuildWriteJson:
    @patch("brain_v9.trading.strategy_archive.write_json")
    def test_called_once(self, mock_wj: MagicMock):
        build_strategy_archive([], {}, {})
        mock_wj.assert_called_once()

    @patch("brain_v9.trading.strategy_archive.write_json")
    def test_path_matches(self, mock_wj: MagicMock):
        build_strategy_archive([], {}, {})
        assert mock_wj.call_args[0][0] == ARCHIVE_PATH


# ── build_strategy_archive — edge cases ─────────────────────────────

class TestEdgeCases:
    @patch("brain_v9.trading.strategy_archive.write_json")
    def test_missing_scorecard_defaults(self, mock_wj: MagicMock):
        """Strategy with no matching scorecard gets defaults."""
        out = build_strategy_archive([_strategy("s1")], _cards(), _hyp_results())
        item = out["testing"][0]
        assert item["entries_resolved"] == 0
        assert item["expectancy"] == 0.0
        assert item["governance_state"] == "paper_candidate"

    @patch("brain_v9.trading.strategy_archive.write_json")
    def test_none_in_card_fields(self, mock_wj: MagicMock):
        """None values in card should be coerced to 0."""
        cards = _cards(s1={"entries_resolved": None, "expectancy": None, "governance_state": None})
        out = build_strategy_archive([_strategy("s1")], cards, _hyp_results())
        item = out["testing"][0]
        assert item["entries_resolved"] == 0
        assert item["expectancy"] == 0.0

    @patch("brain_v9.trading.strategy_archive.write_json")
    def test_scorecards_key_none_handled(self, mock_wj: MagicMock):
        """If scorecards is None, fallback to empty dict."""
        out = build_strategy_archive([_strategy("s1")], {"scorecards": None}, _hyp_results())
        assert len(out["testing"]) == 1

    @patch("brain_v9.trading.strategy_archive.write_json")
    def test_governance_state_from_promotion_state(self, mock_wj: MagicMock):
        """Falls back to promotion_state if governance_state is missing."""
        cards = _cards(s1={"entries_resolved": 5, "expectancy": 0.1, "promotion_state": "paper_active"})
        out = build_strategy_archive([_strategy("s1")], cards, _hyp_results())
        assert len(out["active"]) == 1

    @patch("brain_v9.trading.strategy_archive.write_json")
    def test_hypothesis_index_ignores_non_dicts(self, mock_wj: MagicMock):
        """Non-dict items in hypothesis results are skipped."""
        hyp = {"results": ["not_a_dict", 42, None]}
        out = build_strategy_archive([_strategy("s1")], _cards(), hyp)
        # Should not crash, strategy lands in testing
        assert len(out["testing"]) == 1


# ── read_strategy_archive ───────────────────────────────────────────

class TestReadStrategyArchive:
    def test_reads_existing_file(self, tmp_path: Path):
        payload = {"schema_version": "strategy_archive_v1", "archived": ["x"]}
        archive = tmp_path / "strategy_archive_latest.json"
        archive.write_text(json.dumps(payload), encoding="utf-8")
        with patch("brain_v9.trading.strategy_archive.ARCHIVE_PATH", archive):
            result = read_strategy_archive()
        assert result["archived"] == ["x"]

    def test_missing_file_returns_default(self, tmp_path: Path):
        missing = tmp_path / "nonexistent.json"
        with patch("brain_v9.trading.strategy_archive.ARCHIVE_PATH", missing):
            result = read_strategy_archive()
        assert result["schema_version"] == "strategy_archive_v1"
        assert result["archived"] == []
        assert result["generated_utc"] is None

    def test_corrupt_json_returns_default(self, tmp_path: Path):
        bad = tmp_path / "bad.json"
        bad.write_text("{{{invalid", encoding="utf-8")
        with patch("brain_v9.trading.strategy_archive.ARCHIVE_PATH", bad):
            result = read_strategy_archive()
        assert result["schema_version"] == "strategy_archive_v1"
        assert result["summary"] == {}

    def test_default_has_all_expected_keys(self, tmp_path: Path):
        missing = tmp_path / "nope.json"
        with patch("brain_v9.trading.strategy_archive.ARCHIVE_PATH", missing):
            result = read_strategy_archive()
        expected_keys = {"schema_version", "generated_utc", "archived", "active", "watchlist", "testing", "summary"}
        assert set(result.keys()) == expected_keys
