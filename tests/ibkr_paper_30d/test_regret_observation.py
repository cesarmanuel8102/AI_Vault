from __future__ import annotations

import json
import sqlite3

import pytest

from ibkr_paper_30d.canonical import sha256_json
from ibkr_paper_30d.decision_diagnostics import (
    build_regret_record,
    load_regret_records,
    observation_without_identifiable_candidate,
    persist_regret_record,
)
from ibkr_paper_30d.persistence import Database


EX_ANTE_EVIDENCE = {
    "quote": {"bid": "4.45", "ask": "4.55"},
    "feasibility": {"initMarginChange": "455.00"},
}


def record(**overrides):
    return build_regret_record(
        decision_cycle_id="cycle-regret-1",
        candidate={"symbol": "NVDA", "sec_type": "OPT", "strike": "200", "right": "C"},
        ex_ante_evidence=EX_ANTE_EVIDENCE,
        rejection_reason_codes=("EXPERIMENT_CAPITAL_BOUNDARY",),
        **overrides,
    )


def test_regret_record_preserves_candidate_cycle_evidence_and_reason():
    item = record()

    assert item["candidate"]["symbol"] == "NVDA"
    assert item["decision_cycle_id"] == "cycle-regret-1"
    assert item["ex_ante_evidence_sha256"] == sha256_json(EX_ANTE_EVIDENCE)
    assert item["rejection_reason_codes"] == ["EXPERIMENT_CAPITAL_BOUNDARY"]
    assert item["rejection_mechanism"]
    assert item["ex_ante_evidence"] == EX_ANTE_EVIDENCE
    assert item["timestamp_utc"]
    assert item["ex_post_outcome"] is None


def test_regret_record_rejects_unidentifiable_candidate():
    with pytest.raises(ValueError, match="identifiable candidate"):
        build_regret_record(
            decision_cycle_id="cycle-regret-2",
            candidate={},
            ex_ante_evidence=EX_ANTE_EVIDENCE,
            rejection_reason_codes=("NO_EDGE_FOUND",),
        )


def test_regret_record_requires_real_ex_ante_evidence():
    with pytest.raises(ValueError, match="ex-ante evidence"):
        build_regret_record(
            decision_cycle_id="cycle-regret-3",
            candidate={"symbol": "AAPL", "sec_type": "STK"},
            ex_ante_evidence={},
            rejection_reason_codes=("NO_EDGE_FOUND",),
        )


def test_no_identifiable_candidate_yields_observational_note_not_fake_record():
    note = observation_without_identifiable_candidate(
        decision_cycle_id="cycle-regret-4",
        reason_codes=("NO_EDGE_FOUND",),
    )

    assert note["observation_type"] == "NO_IDENTIFIABLE_REJECTED_CANDIDATE"
    assert "candidate" not in note
    assert note["reason_codes"] == ["NO_EDGE_FOUND"]


def test_record_is_observational_only_despite_sample_size():
    """Ruling U2: sample_size/repeated_mechanism are descriptive fields.

    No count, however large, may automatically transition policy status.
    """

    item = record()
    for sample_size in (1, 3, 10, 1000):
        item = record(
            sample_size=sample_size,
            repeated_mechanism=(sample_size > 1),
        )
        assert item["policy_status"] == "OBSERVATION"
        assert item["sample_size"] == sample_size
        assert item["repeated_mechanism"] == (sample_size > 1)


def test_no_automatic_policy_change_states_exist():
    import ibkr_paper_30d.decision_diagnostics as module

    source = json.dumps(
        {
            "module": inspect_source(module),
        }
    ).lower()
    for forbidden in (
        "policy_changed",
        "loosen_threshold",
        "tighten_threshold",
        "change_strategy",
    ):
        assert forbidden not in source, forbidden


def inspect_source(module):
    import inspect

    return inspect.getsource(module)


def test_ex_post_outcome_attached_later_without_policy_flip():
    item = record()
    updated = {
        **item,
        "ex_post_outcome": {"observed_price": "6.10", "direction_favorable": True},
        "ex_post_observed_at_utc": "2026-09-24T21:00:00Z",
    }

    assert updated["ex_post_outcome"]["observed_price"] == "6.10"
    assert updated["policy_status"] == "OBSERVATION"


def test_uncertainty_is_recorded_descriptively():
    item = record()
    assert "uncertainty" in item
    assert item["uncertainty"]["sample_size_note"]


def test_persist_and_load_round_trip(tmp_path):
    with Database.open(tmp_path / "autonomous.sqlite3") as db:
        event_id = persist_regret_record(db, record())
        rows = db.execute(
            "SELECT payload_json FROM autonomous_research_events "
            "WHERE event_type='regret_observation'"
        ).fetchall()

    assert rows
    loaded = load_regret_records(tmp_path / "autonomous.sqlite3")
    assert len(loaded) == 1
    assert loaded[0]["candidate"]["symbol"] == "NVDA"
    assert loaded[0]["ex_ante_evidence_sha256"] == record()["ex_ante_evidence_sha256"]


def test_persisted_payload_hash_matches(tmp_path):
    with Database.open(tmp_path / "autonomous.sqlite3") as db:
        persist_regret_record(db, record())
        row = db.execute(
            "SELECT payload_json, payload_sha256 FROM autonomous_research_events "
            "WHERE event_type='regret_observation'"
        ).fetchone()

    payload = json.loads(row[0])
    assert sha256_json(payload) == row[1]