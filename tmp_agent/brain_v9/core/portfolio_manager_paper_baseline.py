"""Deterministic paper-only portfolio allocation and ledger baseline for R12.1.

This module consumes only validated PAPER_ELIGIBLE strategy receipts. It models
allocation evidence and never imports broker, trading, provider, network, or
financial-autonomy runtime code.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import re


_IDENTIFIER = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
_BPS = 10_000
_PAPER_ELIGIBLE = "PAPER_ELIGIBLE"
_FORBIDDEN_EFFECTS = frozenset(
    {
        "broker_connect",
        "broker_order",
        "order_submit",
        "provider_call",
        "network_fetch",
        "runtime_import",
        "runtime_mutation",
        "configuration_mutation",
        "scheduler_mutation",
        "canonical_local_sync",
        "live_trading",
        "real_money",
        "auto_merge",
    }
)


@dataclass(frozen=True)
class PaperEligibleStrategyValidationReceipt:
    receipt_id: str
    strategy_id: str
    eligibility: str
    asset_bucket: str
    correlation_group: str
    expected_attribution_bps: int


@dataclass(frozen=True)
class PaperAllocationEntry:
    receipt_id: str
    strategy_id: str
    asset_bucket: str
    correlation_group: str
    target_weight_bps: int
    allocated_capital_cents: int


@dataclass(frozen=True)
class PaperPortfolio:
    portfolio_id: str
    total_capital_cents: int
    paper_only: bool
    cash_reserve_bps: int
    portfolio_sha256: str


@dataclass(frozen=True)
class PaperPortfolioLedger:
    entries: tuple[PaperAllocationEntry, ...]
    total_allocated_bps: int
    cash_reserve_bps: int
    ledger_sha256: str


@dataclass(frozen=True)
class PaperPortfolioRiskSummary:
    max_strategy_weight_bps_observed: int
    asset_exposure_bps: dict[str, int]
    correlation_group_exposure_bps: dict[str, int]


@dataclass(frozen=True)
class PaperPortfolioAttribution:
    expected_attribution_bps: int


@dataclass(frozen=True)
class PaperOnlyPortfolioBaseline:
    portfolio: PaperPortfolio
    ledger: PaperPortfolioLedger
    risk_summary: PaperPortfolioRiskSummary
    attribution: PaperPortfolioAttribution


def _canonical_sha256(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return sha256(payload.encode("ascii")).hexdigest()


def _validate_identifier(value: str, field: str) -> None:
    if not isinstance(value, str) or not _IDENTIFIER.fullmatch(value):
        raise ValueError(f"invalid_{field}")


def _validate_bps(value: int, field: str, *, allow_zero: bool = True) -> None:
    if not isinstance(value, int) or isinstance(value, bool) or not 0 <= value <= _BPS:
        raise ValueError(f"invalid_{field}")
    if not allow_zero and value == 0:
        raise ValueError(f"invalid_{field}")


def _validated_receipts(
    receipts: tuple[PaperEligibleStrategyValidationReceipt, ...],
) -> tuple[PaperEligibleStrategyValidationReceipt, ...]:
    if not receipts:
        raise ValueError("paper_eligible_receipts_required")

    receipt_ids: set[str] = set()
    strategy_ids: set[str] = set()
    validated: list[PaperEligibleStrategyValidationReceipt] = []
    for receipt in receipts:
        if not isinstance(receipt, PaperEligibleStrategyValidationReceipt):
            raise ValueError("invalid_strategy_validation_receipt")
        _validate_identifier(receipt.receipt_id, "receipt_id")
        _validate_identifier(receipt.strategy_id, "strategy_id")
        _validate_identifier(receipt.asset_bucket, "asset_bucket")
        _validate_identifier(receipt.correlation_group, "correlation_group")
        _validate_bps(receipt.expected_attribution_bps, "expected_attribution_bps")
        if receipt.eligibility != _PAPER_ELIGIBLE:
            raise ValueError("receipt_not_paper_eligible")
        if receipt.receipt_id in receipt_ids:
            raise ValueError("duplicate_receipt_id")
        if receipt.strategy_id in strategy_ids:
            raise ValueError("duplicate_strategy_id")
        receipt_ids.add(receipt.receipt_id)
        strategy_ids.add(receipt.strategy_id)
        validated.append(receipt)
    return tuple(sorted(validated, key=lambda receipt: receipt.receipt_id))


def build_paper_only_portfolio_baseline(
    *,
    portfolio_id: str,
    total_capital_cents: int,
    receipts: tuple[PaperEligibleStrategyValidationReceipt, ...],
    cash_reserve_bps: int,
    max_strategy_weight_bps: int,
    max_asset_weight_bps: int,
    max_correlation_group_weight_bps: int,
) -> PaperOnlyPortfolioBaseline:
    """Build immutable allocation evidence without executing any financial action."""
    _validate_identifier(portfolio_id, "portfolio_id")
    if not isinstance(total_capital_cents, int) or isinstance(total_capital_cents, bool) or total_capital_cents <= 0:
        raise ValueError("invalid_total_capital_cents")
    _validate_bps(cash_reserve_bps, "cash_reserve_bps")
    _validate_bps(max_strategy_weight_bps, "max_strategy_weight_bps", allow_zero=False)
    _validate_bps(max_asset_weight_bps, "max_asset_weight_bps", allow_zero=False)
    _validate_bps(max_correlation_group_weight_bps, "max_correlation_group_weight_bps", allow_zero=False)
    validated = _validated_receipts(receipts)

    investable_bps = _BPS - cash_reserve_bps
    if len(validated) * max_strategy_weight_bps < investable_bps:
        raise ValueError("insufficient_strategy_capacity")

    base_weight, remainder = divmod(investable_bps, len(validated))
    weights = tuple(base_weight + (index < remainder) for index in range(len(validated)))
    if max(weights, default=0) > max_strategy_weight_bps:
        raise ValueError("strategy_weight_limit_exceeded")

    entries = tuple(
        PaperAllocationEntry(
            receipt_id=receipt.receipt_id,
            strategy_id=receipt.strategy_id,
            asset_bucket=receipt.asset_bucket,
            correlation_group=receipt.correlation_group,
            target_weight_bps=weight,
            allocated_capital_cents=(total_capital_cents * weight) // _BPS,
        )
        for receipt, weight in zip(validated, weights, strict=True)
    )
    asset_exposure: dict[str, int] = {}
    correlation_exposure: dict[str, int] = {}
    for entry in entries:
        asset_exposure[entry.asset_bucket] = asset_exposure.get(entry.asset_bucket, 0) + entry.target_weight_bps
        correlation_exposure[entry.correlation_group] = (
            correlation_exposure.get(entry.correlation_group, 0) + entry.target_weight_bps
        )
    if max(asset_exposure.values(), default=0) > max_asset_weight_bps:
        raise ValueError("asset_exposure_limit_exceeded")
    if max(correlation_exposure.values(), default=0) > max_correlation_group_weight_bps:
        raise ValueError("correlation_group_limit_exceeded")

    ledger_payload = {
        "cash_reserve_bps": cash_reserve_bps,
        "entries": [
            {
                "allocated_capital_cents": entry.allocated_capital_cents,
                "asset_bucket": entry.asset_bucket,
                "correlation_group": entry.correlation_group,
                "receipt_id": entry.receipt_id,
                "strategy_id": entry.strategy_id,
                "target_weight_bps": entry.target_weight_bps,
            }
            for entry in entries
        ],
        "portfolio_id": portfolio_id,
        "total_allocated_bps": investable_bps,
        "total_capital_cents": total_capital_cents,
    }
    portfolio_payload = {
        "cash_reserve_bps": cash_reserve_bps,
        "paper_only": True,
        "portfolio_id": portfolio_id,
        "total_capital_cents": total_capital_cents,
    }
    attribution = sum(
        (entry.target_weight_bps * receipt.expected_attribution_bps) // _BPS
        for entry, receipt in zip(entries, validated, strict=True)
    )
    return PaperOnlyPortfolioBaseline(
        portfolio=PaperPortfolio(**portfolio_payload, portfolio_sha256=_canonical_sha256(portfolio_payload)),
        ledger=PaperPortfolioLedger(
            entries=entries,
            total_allocated_bps=investable_bps,
            cash_reserve_bps=cash_reserve_bps,
            ledger_sha256=_canonical_sha256(ledger_payload),
        ),
        risk_summary=PaperPortfolioRiskSummary(
            max_strategy_weight_bps_observed=max(weights, default=0),
            asset_exposure_bps=dict(sorted(asset_exposure.items())),
            correlation_group_exposure_bps=dict(sorted(correlation_exposure.items())),
        ),
        attribution=PaperPortfolioAttribution(expected_attribution_bps=attribution),
    )


def reject_portfolio_baseline_effect(operation: str) -> None:
    """Fail closed for every operation outside the paper-only baseline contract."""
    if operation in _FORBIDDEN_EFFECTS:
        raise ValueError("paper_only_portfolio_baseline_no_effects")
    raise ValueError("unsupported_paper_only_portfolio_baseline_operation")
