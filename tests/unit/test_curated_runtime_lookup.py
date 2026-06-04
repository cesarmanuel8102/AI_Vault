import pytest
from pathlib import Path
from brain.curated_runtime_lookup import (
    ALLOWED_STATES_FOR_LOOKUP,
    FORBIDDEN_STATES_FOR_LOOKUP,
    CuratedLookupQuery,
    CuratedLookupResult,
    EmptyLookupIndex,
    InvalidLookupState,
    LookupWriteAttemptBlocked,
    MissingProvenance,
    MissingProvenanceField,
    assert_lookup_is_read_only,
    filter_lookup_records,
    format_curated_lookup_for_chat,
    load_curated_lookup_index,
    search_curated_candidates,
    verify_lookup_does_not_import_semantic_writers,
)


FIXTURE_INDEX = Path("tests/fixtures/readonly_lookup_index.jsonl")


# ── 1. load_index_read_only ───────────────────────────────────────────────

def test_load_index_reads_all_valid_records():
    records = load_curated_lookup_index(FIXTURE_INDEX)
    assert len(records) == 5  # valid-001, valid-002, stale-005, low-score-006, valid-010
    # blocked-003, rejected-004, promoted-009, discovered-008 are invalid states
    # no-provenance-007 has empty provenance bundle


def test_load_index_returns_tuple():
    records = load_curated_lookup_index(FIXTURE_INDEX)
    assert isinstance(records, tuple)


def test_load_empty_index_returns_empty_tuple():
    records = load_curated_lookup_index("nonexistent_path.jsonl")
    assert records == ()


# ── 2. reject_missing_provenance ───────────────────────────────────────────

def test_missing_provenance_record_skipped():
    records = load_curated_lookup_index(FIXTURE_INDEX)
    ids = {r.candidate_id for r in records}
    assert "no-provenance-007" not in ids


# ── 3. reject_blocked_rejected_states ───────────────────────────────────

def test_blocked_record_not_loaded():
    records = load_curated_lookup_index(FIXTURE_INDEX)
    ids = {r.candidate_id for r in records}
    assert "blocked-003" not in ids


def test_rejected_record_not_loaded():
    records = load_curated_lookup_index(FIXTURE_INDEX)
    ids = {r.candidate_id for r in records}
    assert "rejected-004" not in ids


def test_promoted_real_write_not_loaded():
    records = load_curated_lookup_index(FIXTURE_INDEX)
    ids = {r.candidate_id for r in records}
    assert "promoted-009" not in ids


def test_discovered_record_not_loaded():
    records = load_curated_lookup_index(FIXTURE_INDEX)
    ids = {r.candidate_id for r in records}
    assert "discovered-008" not in ids


# ── 4. allow_only_verified_states ────────────────────────────────────────

def test_allowed_states_loaded():
    records = load_curated_lookup_index(FIXTURE_INDEX)
    for r in records:
        assert r.state in ALLOWED_STATES_FOR_LOOKUP
        assert r.state not in FORBIDDEN_STATES_FOR_LOOKUP


# ── 5. filter_by_validation_score ─────────────────────────────────────────

def test_filter_by_validation_score():
    all_records = load_curated_lookup_index(FIXTURE_INDEX)
    filtered = filter_lookup_records(
        all_records,
        min_validation_score=0.80,
        min_curation_score=0.70,
    )
    for r in filtered:
        assert r.validation_score >= 0.80
        assert r.curation_score >= 0.70


def test_low_score_filtered_out():
    # low-score-006 has validation_score 0.60, but load_curated_lookup_index does NOT filter by score
    # Filtering by score only happens in filter_lookup_records / search_curated_candidates
    all_records = load_curated_lookup_index(FIXTURE_INDEX)
    ids = {r.candidate_id for r in all_records}
    assert "low-score-006" in ids  # low-score IS loaded (score filtering is done in search/filter)
    # Now test filtering
    filtered = filter_lookup_records(all_records, min_validation_score=0.75, min_curation_score=0.70)
    filtered_ids = {r.candidate_id for r in filtered}
    assert "low-score-006" not in filtered_ids


# ── 6. filter_stale_records ───────────────────────────────────────────────

def test_stale_records_filtered_by_default():
    record = search_curated_candidates("cualquier cosa", index_path=FIXTURE_INDEX)
    for r in record.results:
        assert not r.is_stale


def test_include_stale_shows_stale():
    record = search_curated_candidates(
        "cualquier cosa",
        index_path=FIXTURE_INDEX,
        include_stale=True,
        top_k=10,
    )
    stale_ids = {r.candidate_id for r in record.results if r.is_stale}
    assert "stale-005" in stale_ids


# ── 7. format_chat_output_with_labels ─────────────────────────────────────

def test_format_includes_label():
    record = search_curated_candidates("chat-ops", index_path=FIXTURE_INDEX)
    formatted = format_curated_lookup_for_chat(record)
    assert "verified_curated_readonly" in formatted


def test_format_includes_evidence():
    record = search_curated_candidates("chat-ops", index_path=FIXTURE_INDEX)
    formatted = format_curated_lookup_for_chat(record)
    assert "Evidence:" in formatted


def test_format_empty_results():
    from brain.curated_runtime_lookup import CuratedLookupRecord, CuratedLookupQuery
    empty = CuratedLookupRecord(
        query=CuratedLookupQuery(text="xyz"),
        results=(),
        total_available=0,
        filtered_out=0,
    )
    formatted = format_curated_lookup_for_chat(empty)
    assert "No se encontró" in formatted


# ── 8. no_semantic_writer_imports ──────────────────────────────────────────

def test_no_semantic_writer_imports():
    decision = verify_lookup_does_not_import_semantic_writers()
    assert decision.allow_lookup is True
    assert decision.reason_codes == ()


# ── 9. no_real_adapter_imports ───────────────────────────────────────────

def test_module_has_no_write_functions():
    # assert_lookup_is_read_only se ejecuta al importar
    # Si hubiera funciones prohibidas, hubiera lanzado LookupWriteAttemptBlocked
    import brain.curated_runtime_lookup as lookup
    assert not hasattr(lookup, 'write_index')
    assert not hasattr(lookup, 'add_record')
    assert not hasattr(lookup, 'delete_record')


# ── 10. search_ranking ───────────────────────────────────────────────────

def test_search_ranking_by_score():
    record = search_curated_candidates("", index_path=FIXTURE_INDEX, top_k=2, include_stale=True)
    assert len(record.results) <= 2
    if len(record.results) >= 2:
        assert record.results[0].validation_score >= record.results[1].validation_score


def test_search_returns_counts():
    record = search_curated_candidates("", index_path=FIXTURE_INDEX, top_k=10, include_stale=True)
    assert record.total_available >= 0
    assert record.filtered_out >= 0
    assert len(record.results) <= record.total_available
