"""BR2-1 contract: paper-eligible receipts must carry immutable provenance.

A caller may not present a strategy-validation receipt without proof of
origin: the receipt must bind the issuing authority and the SHA-256 of the
validation evidence that produced it. This mirrors the BR1 evidence
standard (PR #391) at the Brain-side portfolio consumer.
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]


def _receipt(**overrides):
    from tmp_agent.brain_v9.core.portfolio_manager_paper_baseline import (
        PaperEligibleStrategyValidationReceipt,
    )

    values = {
        "receipt_id": "receipt_alpha_001",
        "strategy_id": "strategy_trend_a",
        "eligibility": "PAPER_ELIGIBLE",
        "asset_bucket": "equity",
        "correlation_group": "trend",
        "expected_attribution_bps": 25,
        "issuer_id": "hive_strategy_validation_authority",
        "validation_evidence_sha256": "a" * 64,
    }
    values.update(overrides)
    missing = [k for k, v in values.items() if v is ...]
    if missing:
        for k in missing:
            del values[k]
    return PaperEligibleStrategyValidationReceipt(**values)


def _build(receipts):
    from tmp_agent.brain_v9.core.portfolio_manager_paper_baseline import (
        build_paper_only_portfolio_baseline,
    )

    return build_paper_only_portfolio_baseline(
        portfolio_id="portfolio_br2_001",
        total_capital_cents=100_000_00,
        receipts=tuple(receipts),
        cash_reserve_bps=0,
        max_strategy_weight_bps=10_000,
        max_asset_weight_bps=10_000,
        max_correlation_group_weight_bps=10_000,
    )


def test_valid_provenance_receipt_is_accepted_and_hashes_are_stable():
    portfolio = _build([_receipt()])
    assert portfolio.portfolio.portfolio_sha256
    again = _build([_receipt()])
    assert portfolio.portfolio.portfolio_sha256 == again.portfolio.portfolio_sha256


def test_receipt_missing_provenance_fields_is_rejected():
    with pytest.raises(TypeError):
        _receipt(issuer_id=..., validation_evidence_sha256=...)


def test_receipt_malformed_issuer_is_rejected():
    from tmp_agent.brain_v9.core.portfolio_manager_paper_baseline import (
        PaperEligibleStrategyValidationReceipt,
    )

    base = dict(
        receipt_id="receipt_alpha_002",
        strategy_id="strategy_trend_b",
        eligibility="PAPER_ELIGIBLE",
        asset_bucket="equity",
        correlation_group="trend",
        expected_attribution_bps=25,
        validation_evidence_sha256="b" * 64,
    )
    for bad_issuer in ("", "1starts_with_digit", "has spaces", "UPPER", "x" * 65):
        with pytest.raises(ValueError, match="issuer_id"):
            _build(
                [
                    PaperEligibleStrategyValidationReceipt(
                        **base, issuer_id=bad_issuer
                    )
                ]
            )


def test_receipt_malformed_evidence_digest_is_rejected():
    from tmp_agent.brain_v9.core.portfolio_manager_paper_baseline import (
        PaperEligibleStrategyValidationReceipt,
    )

    base = dict(
        receipt_id="receipt_alpha_003",
        strategy_id="strategy_trend_c",
        eligibility="PAPER_ELIGIBLE",
        asset_bucket="equity",
        correlation_group="trend",
        expected_attribution_bps=25,
        issuer_id="hive_strategy_validation_authority",
    )
    for bad_digest in ("", "z" * 64, "A" * 64, "a" * 63, "a" * 65, "not-hex!!"):
        with pytest.raises(ValueError, match="validation_evidence_sha256"):
            _build(
                [
                    PaperEligibleStrategyValidationReceipt(
                        **base, validation_evidence_sha256=bad_digest
                    )
                ]
            )


def test_provenance_does_not_change_allocation_math():
    """With valid provenance, weights equal the plain capital-proportional math."""
    portfolio = _build(
        [
            _receipt(
                receipt_id="receipt_alpha_004",
                strategy_id="strategy_trend_d",
                expected_attribution_bps=50,
                validation_evidence_sha256="c" * 64,
            ),
            _receipt(
                receipt_id="receipt_alpha_005",
                strategy_id="strategy_mr_e",
                asset_bucket="fx_bucket",
                correlation_group="mean_reversion",
                expected_attribution_bps=50,
                validation_evidence_sha256="d" * 64,
            ),
        ]
    )
    entries = sorted(portfolio.ledger.entries, key=lambda e: e.strategy_id)
    assert [e.target_weight_bps for e in entries] == [5000, 5000]
    assert sum(e.allocated_capital_cents for e in entries) == portfolio.portfolio.total_capital_cents


def test_receipt_is_immutable():
    receipt = _receipt()
    with pytest.raises(Exception):
        receipt.eligibility = "LIVE"