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

    def import_broker_net_pnl(
        self, request: Any, observation: dict[str, Any]
    ) -> dict[str, Any]:
        """Integrate broker-reported net realized PnL into the continuous sleeve
        ledger when individual commission reports are missing or incomplete.

        The ledger records the broker net as canonical realized PnL and debits
        the inferred cost difference from the sleeve cash balance. The excess
        over the candidate fee allowance is preserved explicitly; recording the
        cost is not an authorization to exceed the allowance.
        """
        from .production_continuity_runtime import _ProductionCanaryStore

        if (
            observation.get("account_identity_sha256")
            != request.account_identity_sha256
            or observation.get("candidate_sha256") != request.candidate_sha256
            or observation.get("original_request_sha256") != request.sha256
        ):
            raise ValueError("CANARY_BROKER_PNL_IDENTITY_MISMATCH")
        if observation.get("contract_id") != request.canonical_contract.con_id:
            raise ValueError("CANARY_BROKER_PNL_IDENTITY_MISMATCH")

        try:
            broker_net = Decimal(str(observation["broker_realized_pnl_usd"]))
            gross_pnl = Decimal(str(observation["gross_execution_pnl_usd"]))
            cost_difference = Decimal(str(observation["cost_difference_usd"]))
        except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
            raise ValueError("CANARY_BROKER_PNL_VALUE_INVALID") from exc
        if not all(v.is_finite() for v in (broker_net, gross_pnl, cost_difference)):
            raise ValueError("CANARY_BROKER_PNL_VALUE_INVALID")

        expected_cost_difference = gross_pnl - broker_net
        if cost_difference != expected_cost_difference:
            raise ValueError("CANARY_BROKER_PNL_COST_DIFFERENCE_MISMATCH")

        evidence_sha256 = str(observation.get("evidence_sha256") or "")
        if len(evidence_sha256) != 64 or any(
            c not in "0123456789abcdef" for c in evidence_sha256
        ):
            raise ValueError("CANARY_BROKER_PNL_EVIDENCE_INVALID")

        try:
            fee_allowance = Decimal(
                str(observation.get("candidate_fee_allowance_usd"))
            )
        except (TypeError, ValueError, ArithmeticError) as exc:
            raise ValueError("CANARY_BROKER_PNL_ALLOWANCE_INVALID") from exc
        if not fee_allowance.is_finite() or fee_allowance < 0:
            raise ValueError("CANARY_BROKER_PNL_ALLOWANCE_INVALID")
        exceeds_allowance = cost_difference > fee_allowance

        executions = list(observation.get("executions") or ())
        execution_ids = {str(e.get("id_sha256")) for e in executions}
        if len(execution_ids) != len(executions):
            raise ValueError("CANARY_BROKER_PNL_EXECUTION_DUPLICATE")

        with Database.open(self.db_path) as db, db.transaction():
            store = _ProductionCanaryStore(self.db_path)
            events = store._verified_events(db)
            if any(
                e.get("event_type") == "BROKER_NET_PNL_RECONCILED"
                and e.get("evidence_sha256") == evidence_sha256
                for e in events
            ):
                return {
                    "integrated": False,
                    "reason": "BROKER_NET_PNL_ALREADY_RECONCILED",
                    "evidence_sha256": evidence_sha256,
                }

            ledger = SleeveLedgerStore(db)
            prior = ledger._events()
            imported_fills = [
                e
                for e in prior
                if e["event_type"] == "CANARY_FILL_IMPORTED"
                and e.get("request_sha256") == request.sha256
            ]
            imported_keys = {
                str(e["fill"].get("execution_id_sha256")) for e in imported_fills
            }
            if not imported_keys:
                raise ValueError("CANARY_BROKER_PNL_FILLS_MISSING")
            if execution_ids != imported_keys:
                raise ValueError("CANARY_BROKER_PNL_EXECUTION_MISMATCH")

            computed_gross = Decimal("0")
            for event in imported_fills:
                fill = event["fill"]
                amount = Decimal(str(fill["quantity"])) * Decimal(str(fill["price"]))
                if fill["action"] == "BUY":
                    computed_gross -= amount
                elif fill["action"] == "SELL":
                    computed_gross += amount
            if computed_gross != gross_pnl:
                raise ValueError("CANARY_BROKER_PNL_GROSS_MISMATCH")

            state = ledger.project(CapitalSleeve.CONTINUOUS_SLEEVE)
            if not state.initialized:
                raise ValueError("CONTINUOUS_SLEEVE_NOT_INITIALIZED")

            def insert(event_type, payload):
                ledger._insert(
                    sleeve=CapitalSleeve.CONTINUOUS_SLEEVE,
                    currency="USD",
                    event_type=event_type,
                    payload=payload,
                )

            insert("REALIZED_PNL", {"amount_usd": str(broker_net)})
            if cost_difference > 0:
                if state.balance("USD") < cost_difference:
                    raise ValueError("SLEEVE_CURRENCY_INSUFFICIENT_FOR_COST_DIFFERENCE")
                insert("CURRENCY_DEBIT", {"amount": str(cost_difference)})
            elif cost_difference < 0:
                insert("CURRENCY_CREDIT", {"amount": str(-cost_difference)})
            insert(
                "BROKER_NET_PNL_RECONCILED",
                {
                    "evidence_sha256": evidence_sha256,
                    "request_sha256": request.sha256,
                    "broker_realized_pnl_usd": str(broker_net),
                    "gross_execution_pnl_usd": str(gross_pnl),
                    "cost_difference_usd": str(cost_difference),
                    "candidate_fee_allowance_usd": str(fee_allowance),
                    "cost_difference_exceeds_candidate_fee_allowance": exceeds_allowance,
                    "cost_difference_is_inference": bool(
                        observation.get("cost_difference_is_inference")
                    ),
                    "individual_commission_reports_missing": bool(
                        observation.get("individual_commission_reports_missing")
                    ),
                },
            )
            store._append_in_transaction(
                db,
                authorization_id=request.canary_id,
                event_type="BROKER_NET_PNL_RECONCILED",
                body={
                    "candidate_sha256": request.candidate_sha256,
                    "request_sha256": request.sha256,
                    "evidence_sha256": evidence_sha256,
                    "broker_realized_pnl_usd": str(broker_net),
                    "cost_difference_usd": str(cost_difference),
                    "cost_difference_exceeds_candidate_fee_allowance": exceeds_allowance,
                },
            )

        return {
            "integrated": True,
            "evidence_sha256": evidence_sha256,
            "broker_realized_pnl_usd": broker_net,
            "cost_difference_usd": cost_difference,
            "cost_difference_exceeds_candidate_fee_allowance": exceeds_allowance,
            "candidate_fee_allowance_usd": fee_allowance,
        }

    def reconcile_terminal_recovery(
        self, request: Any, facts: dict[str, Any], observation: dict[str, Any]
    ) -> dict[str, Any]:
        """Complete a canary recovery that has returned to flat.

        Imports broker fills, integrates broker-net realized PnL, and releases
        the continuous-sleeve liability reservation when the position is flat
        and open orders are zero. Each action is idempotent and recorded as a
        distinct durable event.
        """
        from .production_continuity_runtime import _ProductionCanaryStore

        if facts.get("request_sha256") != request.sha256:
            raise ValueError("CANARY_BROKER_FACT_IDENTITY_MISMATCH")
        quantity = Decimal(str(facts.get("position_quantity") or "0"))
        open_orders = int(facts.get("open_order_count") or 0)
        if quantity != 0 or open_orders != 0:
            raise ValueError("CANARY_RECOVERY_NOT_TERMINAL")

        self(request, facts)
        pnl_result = self.import_broker_net_pnl(request, observation)

        facts_sha256 = sha256_json(facts)
        with Database.open(self.db_path) as db, db.transaction():
            ledger = SleeveLedgerStore(db)
            prior = ledger._events()
            reservation = next(
                (
                    e
                    for e in prior
                    if e["event_type"] == "LIABILITY_RESERVED"
                    and e.get("reservation_key") == request.execution_key
                ),
                None,
            )
            if reservation is None:
                return {
                    "pnl_integrated": pnl_result["integrated"],
                    "liability_released": False,
                    "reason": "NO_LIABILITY_RESERVATION_FOR_REQUEST",
                }
            already_released = any(
                e["event_type"] == "LIABILITY_RELEASED"
                and e.get("reservation_key") == request.execution_key
                for e in prior
            )
            if already_released:
                return {
                    "pnl_integrated": pnl_result["integrated"],
                    "liability_released": False,
                    "reason": "LIABILITY_ALREADY_RELEASED",
                }
            amount = Decimal(str(reservation.get("amount_usd")))
            ledger.release_liability_in_transaction(
                CapitalSleeve.CONTINUOUS_SLEEVE,
                amount_usd=amount,
                reservation_key=request.execution_key,
                broker_snapshot_sha256=facts_sha256,
            )
            store = _ProductionCanaryStore(self.db_path)
            store._append_in_transaction(
                db,
                authorization_id=request.canary_id,
                event_type="CANARY_RECOVERY_RECONCILED",
                body={
                    "candidate_sha256": request.candidate_sha256,
                    "request_sha256": request.sha256,
                    "facts_sha256": facts_sha256,
                    "evidence_sha256": observation.get("evidence_sha256"),
                    "liability_released_usd": str(amount),
                },
            )

        return {
            "pnl_integrated": pnl_result["integrated"],
            "liability_released": True,
            "evidence_sha256": observation.get("evidence_sha256"),
        }
