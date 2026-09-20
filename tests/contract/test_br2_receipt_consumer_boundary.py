"""BR2-2 contract: Brain-side immutable receipt consumer boundary."""
from __future__ import annotations

from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def _sv_receipt(**overrides):
    from tmp_agent.brain_v9.core.hive_receipt_boundary import (
        StrategyValidationReceipt,
    )

    values = {
        "receipt_id": "sv_receipt_001",
        "strategy_id": "strategy_trend_a",
        "issuer_id": "hive_strategy_validation_authority",
        "eligibility": "PAPER_ELIGIBLE",
        "validation_window_start": "2010-01-01T00:00:00.000Z",
        "validation_window_end": "2018-12-31T00:00:00.000Z",
        "validation_evidence_sha256": "a" * 64,
        "source_commit_sha": "b" * 40,
    }
    values.update(overrides)
    missing = [k for k, v in values.items() if v is ...]
    for k in missing:
        del values[k]
    return StrategyValidationReceipt(**values)


def _pe_receipt(**overrides):
    from tmp_agent.brain_v9.core.hive_receipt_boundary import (
        PaperExecutionReceipt,
    )

    values = {
        "receipt_id": "pe_receipt_001",
        "strategy_id": "strategy_trend_a",
        "issuer_id": "hive_paper_execution_authority",
        "paper_only": True,
        "executed_window_start": "2026-01-01T00:00:00.000Z",
        "executed_window_end": "2026-03-01T00:00:00.000Z",
        "execution_evidence_sha256": "c" * 64,
        "source_commit_sha": "d" * 40,
    }
    values.update(overrides)
    missing = [k for k, v in values.items() if v is ...]
    for k in missing:
        del values[k]
    return PaperExecutionReceipt(**values)


def test_valid_strategy_validation_receipt_passes():
    from tmp_agent.brain_v9.core.hive_receipt_boundary import (
        validate_strategy_validation_receipt,
    )

    validated = validate_strategy_validation_receipt(_sv_receipt())
    assert validated.receipt_id == "sv_receipt_001"


def test_valid_paper_execution_receipt_passes_and_non_paper_fails():
    from tmp_agent.brain_v9.core.hive_receipt_boundary import (
        validate_paper_execution_receipt,
    )

    assert validate_paper_execution_receipt(_pe_receipt()).paper_only is True
    with pytest.raises(ValueError, match="paper_only_required"):
        validate_paper_execution_receipt(_pe_receipt(paper_only=False))


def test_malformed_receipts_fail_closed():
    from tmp_agent.brain_v9.core.hive_receipt_boundary import (
        validate_paper_execution_receipt,
        validate_strategy_validation_receipt,
    )

    bad_cases = [
        (lambda: _sv_receipt(issuer_id="Bad Issuer"), "issuer_id"),
        (lambda: _sv_receipt(validation_evidence_sha256="NOT-HEX"), "validation_evidence_sha256"),
        (lambda: _sv_receipt(source_commit_sha="short"), "source_commit_sha"),
        (lambda: _sv_receipt(eligibility="LIVE"), "eligibility"),
        (lambda: _sv_receipt(validation_window_start="09/10/2026"), "window_start"),
        (
            lambda: _sv_receipt(
                validation_window_start="2018-12-31T00:00:00.000Z",
                validation_window_end="2010-01-01T00:00:00.000Z",
            ),
            "window_order",
        ),
        (lambda: _pe_receipt(execution_evidence_sha256="g" * 64), "execution_evidence_sha256"),
    ]
    for make, pattern in bad_cases:
        with pytest.raises(ValueError, match=pattern):
            receipt = make()
            if hasattr(receipt, "paper_only"):
                validate_paper_execution_receipt(receipt)
            else:
                validate_strategy_validation_receipt(receipt)


def test_wrong_receipt_type_is_rejected():
    from tmp_agent.brain_v9.core.hive_receipt_boundary import (
        validate_paper_execution_receipt,
        validate_strategy_validation_receipt,
    )

    with pytest.raises(ValueError, match="invalid_receipt_type"):
        validate_strategy_validation_receipt(_pe_receipt())
    with pytest.raises(ValueError, match="invalid_receipt_type"):
        validate_paper_execution_receipt(_sv_receipt())


def test_forbidden_transport_fails_closed():
    from tmp_agent.brain_v9.core.hive_receipt_boundary import (
        reject_receipt_transport,
    )

    for operation in (
        "raw_strategy_code",
        "mutable_qc_experiment_state",
        "hive_optimizer_state",
        "hive_selector_implementation",
        "network_transport",
        "live_trading",
    ):
        with pytest.raises(ValueError, match="receipt_boundary_forbidden"):
            reject_receipt_transport(operation)


def test_boundary_module_has_no_transport_or_hive_imports():
    """The boundary module must stay pure: no network, HIVE runtime, or QC imports."""
    source = (ROOT / "tmp_agent/brain_v9/core/hive_receipt_boundary.py").read_text(
        encoding="utf-8"
    )
    for forbidden in (
        "import requests",
        "import socket",
        "urllib",
        "from tmp_agent.hive",
        "quantconnect",
        "subprocess",
        "import os",
    ):
        assert forbidden not in source, f"boundary module must not contain {forbidden}"


def test_receipt_binding_is_canonical_and_stable():
    from tmp_agent.brain_v9.core.hive_receipt_boundary import (
        receipt_binding_sha256,
    )

    receipt = _sv_receipt()
    assert receipt_binding_sha256(receipt) == receipt_binding_sha256(
        _sv_receipt()
    )
    assert len(receipt_binding_sha256(receipt)) == 64