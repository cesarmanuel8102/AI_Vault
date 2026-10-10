"""Deterministic PAPER account reconciliation across capital sleeves."""

from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, InvalidOperation
from typing import Any, Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field

from .canonical import sha256_json
from .multi_universe_models import CapitalSleeve
from .contract_ownership import BrokerLineageEvidence


_LINEAGE_EVENTS = frozenset(
    {
        "OPTION_ASSIGNMENT",
        "OPTION_EXERCISE",
        "BAG_LEG_MATERIALIZATION",
        "SETTLEMENT",
        "SPLIT",
        "MERGER",
        "SPIN_OFF",
        "CONTRACT_REPLACEMENT",
    }
)


class MultiSleeveReconciliationReceipt(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    schema: Literal["MULTI_SLEEVE_RECONCILIATION_RECEIPT_V1"] = (
        "MULTI_SLEEVE_RECONCILIATION_RECEIPT_V1"
    )
    status: Literal["PASS", "BLOCK"]
    reason_codes: tuple[str, ...]
    freeze_new_entries: bool
    per_sleeve: dict[str, dict[str, Any]]
    aggregate_currency_balances: dict[str, str]
    lineage_assignments: dict[str, str]
    account_snapshot_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    sleeve_ledgers_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    ownership_projection_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @property
    def sha256(self) -> str:
        return sha256_json(self)


def _dump(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if hasattr(value, "model_dump"):
        return dict(value.model_dump(mode="python"))
    raise TypeError("reconciliation input must be a mapping or Pydantic model")


def _decimal(value: Any) -> Decimal:
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("RECONCILIATION_NUMERIC_VALUE_INVALID") from exc
    if not result.is_finite():
        raise ValueError("RECONCILIATION_NUMERIC_VALUE_INVALID")
    return result


def _canonical_decimal(value: Decimal) -> str:
    normalized = value.normalize()
    if normalized == normalized.to_integral():
        return str(normalized.quantize(Decimal("1")))
    return format(normalized, "f")


def _currency_map(rows: Any) -> dict[str, Decimal]:
    result: dict[str, Decimal] = defaultdict(Decimal)
    for raw in rows or ():
        row = _dump(raw)
        result[str(row["currency"]).upper()] += _decimal(row["amount"])
    return dict(result)


def _classified_currency_map(rows: Any, reasons: set[str]) -> dict[str, Decimal]:
    result: dict[str, Decimal] = defaultdict(Decimal)
    for raw in rows or ():
        row = _dump(raw)
        provenance = str(row.get("provenance_sha256") or "")
        if len(provenance) != 64 or any(char not in "0123456789abcdef" for char in provenance):
            reasons.add("EXTERNAL_CASH_PROVENANCE_REQUIRED")
            continue
        result[str(row["currency"]).upper()] += _decimal(row["amount"])
    return dict(result)


class SleeveReconciler:
    """Attribute every broker fact, then compare it to both sleeve ledgers."""

    @staticmethod
    def reconcile(
        account_snapshot: Any,
        sleeve_ledgers: Any,
        ownership: Any,
    ) -> MultiSleeveReconciliationReceipt:
        account = _dump(account_snapshot)
        ledgers = _dump(sleeve_ledgers)
        ownership_data = _dump(ownership)
        reasons: set[str] = set()
        if account.get("paper_only") is not True:
            reasons.add("PAPER_ACCOUNT_REQUIRED")

        sleeve_keys = {
            CapitalSleeve.REGULAR_SLEEVE.value: "regular",
            CapitalSleeve.EXTENDED_SLEEVE.value: "extended",
        }
        owner_by_contract: dict[str, str] = {}
        historical_owner_by_contract: dict[str, str] = {}
        for raw in ownership_data.get("active_contracts", ()):
            row = _dump(raw)
            contract_hash = str(row.get("contract_identity_sha256") or "")
            sleeve_value = row.get("sleeve")
            sleeve = (
                sleeve_value.value
                if isinstance(sleeve_value, CapitalSleeve)
                else str(sleeve_value)
            )
            if contract_hash in owner_by_contract and owner_by_contract[contract_hash] != sleeve:
                reasons.add("CONTRACT_OWNERSHIP_AMBIGUOUS")
            owner_by_contract[contract_hash] = sleeve
            historical_owner_by_contract[contract_hash] = sleeve
        for raw in ownership_data.get("released_contracts", ()):
            row = _dump(raw)
            contract_hash = str(row.get("contract_identity_sha256") or "")
            sleeve_value = row.get("sleeve")
            sleeve = (
                sleeve_value.value
                if isinstance(sleeve_value, CapitalSleeve)
                else str(sleeve_value)
            )
            existing = historical_owner_by_contract.get(contract_hash)
            if existing is not None and existing != sleeve:
                reasons.add("CONTRACT_OWNERSHIP_AMBIGUOUS")
            historical_owner_by_contract[contract_hash] = sleeve

        lineage_assignments: dict[str, str] = {}

        def attribute(
            raw: Any, *, allow_released: bool = False
        ) -> tuple[str | None, dict[str, Any]]:
            row = _dump(raw)
            contract_hash = str(row.get("contract_identity_sha256") or "")
            sleeve = (
                historical_owner_by_contract.get(contract_hash)
                if allow_released
                else owner_by_contract.get(contract_hash)
            )
            if sleeve is None:
                try:
                    lineage = BrokerLineageEvidence.model_validate(
                        row.get("lineage_evidence")
                    )
                except Exception:
                    lineage = None
                source = "" if lineage is None else lineage.source_contract_sha256
                source_sleeve = owner_by_contract.get(source)
                if (
                    lineage is not None
                    and lineage.descendant_contract_sha256 == contract_hash
                    and source_sleeve is not None
                    and lineage.lineage_event in _LINEAGE_EVENTS
                ):
                    existing = lineage_assignments.get(contract_hash)
                    if existing is not None and existing != source_sleeve:
                        reasons.add("CONTRACT_OWNERSHIP_AMBIGUOUS")
                        return None, row
                    sleeve = source_sleeve
                    lineage_assignments[contract_hash] = sleeve
                    owner_by_contract[contract_hash] = sleeve
            if sleeve not in sleeve_keys:
                reasons.add("UNATTRIBUTED_ACCOUNT_EVENT")
                return None, row
            return sleeve, row

        observed: dict[str, dict[str, Any]] = {
            sleeve: {
                "positions": defaultdict(Decimal),
                "open_order_count": 0,
                "execution_count": 0,
                "fees_usd": Decimal("0"),
                "financing_usd": Decimal("0"),
            }
            for sleeve in sleeve_keys
        }
        for raw in account.get("positions", ()):
            sleeve, row = attribute(raw)
            if sleeve is not None:
                quantity = _decimal(row.get("quantity", "0"))
                if quantity != 0:
                    observed[sleeve]["positions"][
                        str(row["contract_identity_sha256"])
                    ] += quantity
        for raw in account.get("open_orders", ()):
            sleeve, _ = attribute(raw)
            if sleeve is not None:
                observed[sleeve]["open_order_count"] += 1
        for raw in account.get("executions", ()):
            sleeve, _ = attribute(raw, allow_released=True)
            if sleeve is not None:
                observed[sleeve]["execution_count"] += 1
        for collection, field in (("fees", "fees_usd"), ("financing", "financing_usd")):
            for raw in account.get(collection, ()):
                sleeve, row = attribute(raw, allow_released=True)
                if sleeve is not None:
                    observed[sleeve][field] += _decimal(row.get("amount", "0"))

        per_sleeve: dict[str, dict[str, Any]] = {}
        for sleeve, ledger_key in sleeve_keys.items():
            ledger = _dump(ledgers.get(ledger_key, ledgers.get(sleeve, {})))
            expected_positions = {
                str(_dump(item)["contract_identity_sha256"]): _decimal(
                    _dump(item).get("quantity", "0")
                )
                for item in ledger.get("positions", ())
            }
            actual_positions = dict(observed[sleeve]["positions"])
            if actual_positions != expected_positions:
                reasons.add(f"SLEEVE_POSITION_MISMATCH:{sleeve}")
            expected_orders = int(ledger.get("open_order_count", 0))
            if observed[sleeve]["open_order_count"] != expected_orders:
                reasons.add(f"SLEEVE_OPEN_ORDER_MISMATCH:{sleeve}")
            expected_fees = _decimal(ledger.get("fees_usd", "0"))
            if observed[sleeve]["fees_usd"] != expected_fees:
                reasons.add(f"SLEEVE_FEES_MISMATCH:{sleeve}")
            expected_financing = _decimal(ledger.get("financing_usd", "0"))
            if observed[sleeve]["financing_usd"] != expected_financing:
                reasons.add(f"SLEEVE_FINANCING_MISMATCH:{sleeve}")
            per_sleeve[sleeve] = {
                "position_count": len(actual_positions),
                "open_order_count": observed[sleeve]["open_order_count"],
                "execution_count": observed[sleeve]["execution_count"],
                "fees_usd": _canonical_decimal(observed[sleeve]["fees_usd"]),
                "financing_usd": _canonical_decimal(
                    observed[sleeve]["financing_usd"]
                ),
            }

        broker_currency = _currency_map(account.get("currency_balances", ()))
        expected_currency = _currency_map(
            ledgers.get("aggregate_currency_balances", ())
        )
        for classification in (
            "classified_canary_currency_balances",
            "classified_non_experiment_currency_balances",
        ):
            classified = _classified_currency_map(account.get(classification, ()), reasons)
            for currency, amount in classified.items():
                expected_currency[currency] = expected_currency.get(
                    currency, Decimal("0")
                ) + amount
        for currency in sorted(set(broker_currency) | set(expected_currency)):
            if broker_currency.get(currency, Decimal("0")) != expected_currency.get(
                currency, Decimal("0")
            ):
                reasons.add(f"AGGREGATE_CURRENCY_MISMATCH:{currency}")

        reason_codes = tuple(sorted(reasons))
        return MultiSleeveReconciliationReceipt(
            status="BLOCK" if reason_codes else "PASS",
            reason_codes=reason_codes,
            freeze_new_entries=bool(reason_codes),
            per_sleeve=per_sleeve,
            aggregate_currency_balances={
                key: _canonical_decimal(value)
                for key, value in sorted(broker_currency.items())
            },
            lineage_assignments=dict(sorted(lineage_assignments.items())),
            account_snapshot_sha256=sha256_json(account),
            sleeve_ledgers_sha256=sha256_json(ledgers),
            ownership_projection_sha256=str(
                ownership_data.get("projection_sha256") or sha256_json(ownership_data)
            ),
        )
