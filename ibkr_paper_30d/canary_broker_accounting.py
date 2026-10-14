"""Import authenticated canary fills without changing the regular sleeve."""

from decimal import Decimal
from pathlib import Path
from typing import Any

from .canonical import sha256_json
from .contract_ownership import ContractOwnershipStore
from .multi_universe_models import CapitalSleeve
from .persistence import Database
from .sleeve_ledger import SleeveLedgerStore


class CanaryBrokerAccounting:
    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)

    def __call__(self, request: Any, facts: dict[str, Any]) -> bool:
        from .production_continuity_runtime import _ProductionCanaryStore

        if (facts.get("request_sha256") != request.sha256
                or facts.get("account_identity_sha256") != request.account_identity_sha256
                or facts.get("contract_identity_sha256") != request.canonical_contract.sha256
                or facts.get("complete") is not True):
            raise ValueError("CANARY_BROKER_FACT_IDENTITY_MISMATCH")
        store = _ProductionCanaryStore(self.db_path)
        stored = store.load_request(request.candidate_sha256)
        if stored is None or stored.sha256 != request.sha256:
            raise ValueError("CANARY_EXECUTION_REQUEST_HASH_MISMATCH")
        fills = list(facts.get("fills") or ())
        quantity = Decimal(str(facts["position_quantity"]))
        costs = {"BUY": Decimal("0"), "SELL": Decimal("0")}
        quantities = {"BUY": Decimal("0"), "SELL": Decimal("0")}
        seen = set()
        fees = Decimal("0")
        fees_complete = bool(fills)
        for fill in fills:
            key = str(fill["execution_id_sha256"])
            if key in seen:
                raise ValueError("CANARY_DUPLICATE_EXECUTION_FACT")
            seen.add(key)
            action = fill["action"]
            amount = Decimal(str(fill["quantity"]))
            price = Decimal(str(fill["price"]))
            if action not in costs or not amount.is_finite() or not price.is_finite() or amount <= 0 or price <= 0:
                raise ValueError("CANARY_BROKER_FILL_INVALID")
            quantities[action] += amount
            costs[action] += amount * price
            commission = fill.get("commission")
            if commission is None or fill.get("commission_currency") != "USD":
                fees_complete = False
            else:
                fee = Decimal(str(commission))
                if not fee.is_finite() or fee < 0 or fee > request.fee_allowance_usd:
                    raise ValueError("CANARY_BROKER_FEE_INVALID")
                fees += fee
        if any(amount > request.quantity for amount in quantities.values()):
            raise ValueError("CANARY_BROKER_FILL_SIZE_MISMATCH")
        if quantities["BUY"] - quantities["SELL"] != quantity:
            raise ValueError("CANARY_BROKER_POSITION_FILL_MISMATCH")
        if fees > request.fee_allowance_usd:
            raise ValueError("CANARY_BROKER_FEE_ALLOWANCE_EXCEEDED")
        flat = quantity == 0 and int(facts["open_order_count"]) == 0
        reconciled = flat and fees_complete and all(amount == request.quantity for amount in quantities.values())
        sleeve = CapitalSleeve.CONTINUOUS_SLEEVE
        with Database.open(self.db_path) as db, db.transaction():
            ownership = ContractOwnershipStore(db).projection()
            owned = ownership.owner_of(request.canonical_contract.sha256)
            if owned is None or owned.sleeve is not sleeve:
                raise ValueError("CANARY_OWNERSHIP_REQUIRED")
            events = store._verified_events(db)
            ledger = SleeveLedgerStore(db)
            prior = ledger._events()

            def insert(event_type, payload):
                ledger._insert(sleeve=sleeve, currency="USD", event_type=event_type, payload=payload)

            for fill in fills:
                key = fill["execution_id_sha256"]
                imported = next((e for e in prior if e["event_type"] == "CANARY_FILL_IMPORTED" and e.get("execution_id_sha256") == key), None)
                if imported is not None:
                    original_fill = imported["fill"]
                    if (original_fill["action"] != fill["action"] or any(
                            Decimal(str(original_fill[field])) != Decimal(str(fill[field]))
                            for field in ("quantity", "price"))):
                        raise ValueError("CANARY_BROKER_FILL_CONFLICT")
                else:
                    gross = Decimal(str(fill["quantity"])) * Decimal(str(fill["price"]))
                    if fill["action"] == "BUY" and ledger.project(sleeve).balance("USD") < gross:
                        raise ValueError("SLEEVE_CURRENCY_INSUFFICIENT")
                    insert("CURRENCY_DEBIT" if fill["action"] == "BUY" else "CURRENCY_CREDIT", {"amount": str(gross)})
                    insert("FILL_RECORDED", {"execution_id_sha256": key})
                    insert("CANARY_FILL_IMPORTED", {"execution_id_sha256": key, "request_sha256": request.sha256, "fill": fill})
                fee_imported = any(e["event_type"] == "CANARY_FEE_IMPORTED" and e.get("execution_id_sha256") == key for e in prior)
                if not fee_imported and fill.get("commission") is not None and fill.get("commission_currency") == "USD":
                    fee = Decimal(str(fill["commission"]))
                    if fee > 0:
                        insert("CURRENCY_DEBIT", {"amount": str(fee)})
                        insert("FEE_CHARGED", {"amount_usd": str(fee)})
                    insert("CANARY_FEE_IMPORTED", {"execution_id_sha256": key, "commission": str(fee)})
            if reconciled and not any(e["event_type"] == "CANARY_ECONOMICS_IMPORTED" and e.get("request_sha256") == request.sha256 for e in prior):
                insert("REALIZED_PNL", {"amount_usd": str(costs["SELL"] - costs["BUY"] - fees)})
                insert("CANARY_ECONOMICS_IMPORTED", {"request_sha256": request.sha256, "facts_sha256": sha256_json(facts)})
            if not any(e.get("event_type") == "BROKER_FACTS_OBSERVED" and e.get("facts_sha256") == sha256_json(facts) for e in events):
                store._append_in_transaction(db, authorization_id=request.canary_id,
                    event_type="BROKER_FACTS_OBSERVED", body={
                        "candidate_sha256": request.candidate_sha256,
                        "request_sha256": request.sha256,
                        "facts_sha256": sha256_json(facts), "facts": facts,
                        "economics_reconciled": reconciled,
                    })
        return reconciled
