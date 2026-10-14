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
    @staticmethod
    def recognizes_fill(db: Database, observed: dict[str, Any]) -> bool:
        """Recognize a journaled canary fill, without posting it to Day1 again."""
        from .canary_execution import CanaryExecutionRequest
        from .ibkr_readonly import expected_identity_hash
        from .multi_universe_models import CanaryAuthorization
        from .production_continuity_runtime import _ProductionCanaryStore

        events = _ProductionCanaryStore._verified_events(db)
        execution_hash = observed.get("execution_id_sha256")
        if not execution_hash:
            return False
        for event in reversed(events):
            if event.get("event_type") != "BROKER_FACTS_OBSERVED":
                continue
            facts = event.get("facts") or {}
            if sha256_json(facts) != event.get("facts_sha256"):
                raise ValueError("CANARY_BROKER_FACT_HASH_MISMATCH")
            matches = [f for f in facts.get("fills", ())
                       if f.get("execution_id_sha256") == execution_hash]
            if len(matches) != 1:
                continue
            anchor = next((e for e in events if e.get("event_type") == "EXECUTION_REQUEST"
                           and e.get("request_sha256") == facts.get("request_sha256")), None)
            if anchor is None:
                return False
            request = CanaryExecutionRequest.model_validate(anchor["request"])
            authorization_event = next((e for e in events if e.get("event_type") == "AUTHORIZED"
                                        and e.get("authorization_sha256") == request.authorization_sha256), None)
            if authorization_event is None:
                return False
            authorization = CanaryAuthorization.model_validate(authorization_event["authorization"])
            if (request.sha256 != anchor["request_sha256"]
                    or authorization.sha256 != request.authorization_sha256
                    or authorization.account_identity_sha256 != request.account_identity_sha256
                    or facts.get("account_identity_sha256") != request.account_identity_sha256
                    or facts.get("contract_identity_sha256") != request.canonical_contract.sha256
                    or facts.get("complete") is not True
                    or not any(e.get("event_type") == "EXECUTION_CLAIMED"
                               and e.get("execution_key") == request.execution_key
                               and e.get("request_sha256") == request.sha256 for e in events)):
                return False
            fill = matches[0]
            try:
                quantity = Decimal(str(observed.get("quantity")))
                cumulative = Decimal(str(observed.get("cumQty") or quantity))
                return (
                    expected_identity_hash(str(observed.get("account") or "")) == request.account_identity_sha256
                    and int((observed.get("contract") or {}).get("conId", 0)) == request.canonical_contract.con_id
                    and observed.get("orderRef") == fill.get("order_ref")
                    and int(observed.get("orderId", 0)) == int(fill.get("order_id", 0)) > 0
                    and int(observed.get("permId", 0)) == int(fill.get("perm_id", 0)) > 0
                    and int(observed.get("clientId", -1)) == int(fill.get("client_id", -2)) == 19761
                    and observed.get("side") == fill.get("action")
                    and quantity == Decimal(str(fill.get("quantity"))) > 0
                    and quantity <= cumulative <= request.quantity
                    and Decimal(str(observed.get("price"))) == Decimal(str(fill.get("price"))) > 0
                )
            except (TypeError, ValueError, ArithmeticError):
                return False
        return False

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)

    def recognizes_broker_fill(self, fill: Any) -> bool:
        execution = fill.execution
        observed = {'execution_id_sha256': sha256_json(execution.execId),
                    'account': execution.acctNumber, 'contract': {'conId': fill.contract.conId},
                    'orderRef': execution.orderRef, 'orderId': execution.orderId,
                    'permId': execution.permId, 'clientId': execution.clientId,
                    'side': 'BUY' if execution.side == 'BOT' else 'SELL' if execution.side == 'SLD' else 'UNKNOWN',
                    'quantity': str(execution.shares), 'cumQty': str(execution.cumQty),
                    'price': str(execution.price)}
        with Database.open(self.db_path) as db:
            return self.recognizes_fill(db, observed)

    def record_verified_baseline(self, request: Any, snapshot: dict[str, Any]) -> None:
        """Host collector boundary; never exposed to the model as a tool."""
        from .production_continuity_runtime import _ProductionCanaryStore

        if (snapshot.get('request_sha256') != request.sha256
                or snapshot.get('account_identity_sha256') != request.account_identity_sha256
                or snapshot.get('contract_id') != request.canonical_contract.con_id
                or snapshot.get('source') != 'IBKR_PAPER'
                or Decimal(snapshot['position_quantity']) != 0 or snapshot['open_order_count'] != 0):
            raise ValueError('CANARY_NET_BASELINE_INVALID')
        with Database.open(self.db_path) as db, db.transaction():
            store = _ProductionCanaryStore(self.db_path)
            events = store._verified_events(db)
            store._reservation_binding(events, request.execution_key, recovery=True)
            prior = next((e for e in events if e.get('event_type') == 'CANARY_ECONOMICS_BASELINE'
                          and e.get('request_sha256') == request.sha256), None)
            if prior is not None:
                if prior.get('snapshot_sha256') != sha256_json(snapshot):
                    raise ValueError('CANARY_NET_BASELINE_CONFLICT')
                return
            store._append_in_transaction(db, authorization_id=request.canary_id,
                event_type='CANARY_ECONOMICS_BASELINE', body={
                    'request_sha256': request.sha256, 'snapshot': snapshot,
                    'snapshot_sha256': sha256_json(snapshot)})

    def capture_baseline(self, request: Any, broker: Any) -> None:
        from .canary_net_economics import collect_net_snapshot
        self.record_verified_baseline(request, collect_net_snapshot(request, broker))

    def pending_flat_request(self) -> Any | None:
        from .canary_authority import CanaryBrokerLifecycleReceipt, CanaryLifecycleRecorder
        from .canary_execution import CanaryExecutionRequest
        from .production_continuity_runtime import _ProductionCanaryStore
        with Database.open(self.db_path) as db:
            events = _ProductionCanaryStore._verified_events(db)
        for event in reversed(events):
            if event.get('event_type') != 'EXECUTION_REQUEST':
                continue
            request = CanaryExecutionRequest.model_validate(event['request'])
            if request.sha256 != event['request_sha256']:
                raise ValueError('CANARY_EXECUTION_REQUEST_HASH_MISMATCH')
            if not any(e.get('event_type') == 'CANARY_ECONOMICS_BASELINE'
                       and e.get('request_sha256') == request.sha256 for e in events):
                continue
            recorder = CanaryLifecycleRecorder(request.canary_id, request.account_identity_sha256,
                                               request.product_family.sha256, request.canonical_contract.sha256)
            for e in events:
                if e.get('event_type') == 'LIFECYCLE_RECEIPT' and e['receipt']['canary_id'] == request.canary_id:
                    receipt = CanaryBrokerLifecycleReceipt.model_validate(e['receipt'])
                    if receipt.sha256 != e['receipt_sha256']:
                        raise ValueError('CANARY_RECEIPT_HASH_MISMATCH')
                    recorder.record(receipt)
            if recorder.projection().completed_steps == recorder.sequence[:-1]:
                return request
        return None

    def complete_pending_with_broker(self, request: Any, broker: Any) -> bool:
        from datetime import datetime, timezone
        from ib_insync import ExecutionFilter
        from .authoritative_broker_writer import AuthoritativeBrokerWriter
        from .canary_net_economics import collect_net_snapshot

        after = collect_net_snapshot(request, broker)
        observer = object.__new__(AuthoritativeBrokerWriter)
        observer.execution_client_id = 19761
        observer.canary_broker_accounting = self
        observer.now_utc = lambda: datetime.now(timezone.utc)
        observer._collect_evidence = lambda b: {
            'executions': b.reqExecutions(ExecutionFilter(acctCode=b.managedAccounts()[0])),
            'positions': b.reqPositions(), 'trades': b.reqAllOpenOrders()}
        facts = observer._canary_broker_facts(request, broker)
        return self.complete_flat_lifecycle(request, facts, after)

    def _net_observation(self, request: Any, facts: dict[str, Any], after: dict[str, Any]):
        from .canary_net_economics import verified_net_observation
        from .production_continuity_runtime import _ProductionCanaryStore
        with Database.open(self.db_path) as db:
            events = _ProductionCanaryStore._verified_events(db)
        baseline = next((e for e in events if e.get('event_type') == 'CANARY_ECONOMICS_BASELINE'
                         and e.get('request_sha256') == request.sha256), None)
        if baseline is None or sha256_json(baseline['snapshot']) != baseline['snapshot_sha256']:
            raise ValueError('CANARY_NET_BASELINE_REQUIRED')
        return verified_net_observation(request, baseline['snapshot'], after, facts)

    def reconcile_with_broker(self, request: Any, broker: Any, facts: dict[str, Any]) -> bool:
        from .canary_net_economics import collect_net_snapshot
        try:
            observation = self._net_observation(request, facts, collect_net_snapshot(request, broker))
        except (ValueError, TimeoutError):
            # Physical flatness is already proven; leave economics pending.
            return False
        result = self.import_broker_net_pnl(request, observation)
        return Decimal(observation['cost_difference_usd']) <= request.fee_allowance_usd

    def complete_flat_lifecycle(self, request: Any, facts: dict[str, Any], after: dict[str, Any]) -> bool:
        """Complete delayed economic evidence; never submits or replays an order."""
        from datetime import datetime, timezone
        from .canary_authority import CanaryBrokerLifecycleReceipt, CanaryLifecycleRecorder
        from .contract_ownership import ReleaseEvidence
        from .production_continuity_runtime import _ProductionCanaryStore

        observed = datetime.fromisoformat(after['observed_at_utc'].replace('Z', '+00:00'))
        if not 0 <= (datetime.now(timezone.utc)-observed).total_seconds() < 60:
            raise ValueError('CANARY_TERMINAL_ECONOMICS_STALE')
        observation = self._net_observation(request, facts, after)
        if Decimal(observation['cost_difference_usd']) > request.fee_allowance_usd:
            raise ValueError('CANARY_BROKER_FEE_ALLOWANCE_EXCEEDED')
        store = _ProductionCanaryStore(self.db_path)
        with Database.open(self.db_path) as db:
            events = store._verified_events(db)
            store._reservation_binding(events, request.execution_key, recovery=True)
        recorder = CanaryLifecycleRecorder(request.canary_id, request.account_identity_sha256,
                                           request.product_family.sha256, request.canonical_contract.sha256)
        for event in events:
            if event.get('event_type') == 'LIFECYCLE_RECEIPT' and event['receipt']['canary_id'] == request.canary_id:
                receipt = CanaryBrokerLifecycleReceipt.model_validate(event['receipt'])
                if receipt.sha256 != event.get('receipt_sha256'):
                    raise ValueError('CANARY_RECEIPT_HASH_MISMATCH')
                recorder.record(receipt)
        if recorder.projection().status == 'PASS':
            return True
        if recorder.projection().completed_steps != recorder.sequence[:-1]:
            raise ValueError('CANARY_TERMINAL_FLAT_RECEIPT_REQUIRED')
        self(request, facts)
        self.import_broker_net_pnl(request, observation)
        snapshot_sha = sha256_json(facts)
        receipt = CanaryBrokerLifecycleReceipt(
            canary_id=request.canary_id, step='ECONOMICS_RECONCILED', endpoint='PAPER',
            account_identity_sha256=request.account_identity_sha256,
            product_family_sha256=request.product_family.sha256,
            contract_identity_sha256=request.canonical_contract.sha256,
            broker_event_id_sha256=observation['evidence_sha256'], broker_snapshot_sha256=snapshot_sha,
            previous_receipt_sha256=recorder.last_receipt_sha256, observed_at_utc=observed,
            open_orders=0, positions=0, economics_reconciled=True)
        recorder.record(receipt)
        with Database.open(self.db_path) as db, db.transaction():
            current = store._verified_events(db)
            store._reservation_binding(current, request.execution_key, recovery=True)
            current_receipts = [e for e in current if e.get('event_type') == 'LIFECYCLE_RECEIPT'
                                and e['receipt']['canary_id'] == request.canary_id]
            if current_receipts[-1]['receipt_sha256'] != receipt.previous_receipt_sha256:
                if current_receipts[-1]['receipt']['step'] == 'ECONOMICS_RECONCILED':
                    return True
                raise ValueError('CANARY_TERMINAL_RECEIPT_CHANGED')
            store._append_in_transaction(db, authorization_id=request.canary_id,
                event_type='LIFECYCLE_RECEIPT', body={'receipt_sha256': receipt.sha256,
                                                    'receipt': receipt.model_dump(mode='json')})
            ledger = SleeveLedgerStore(db)
            if not any(e['event_type'] == 'LIABILITY_RELEASED' and e.get('reservation_key') == request.execution_key
                       for e in ledger._events()):
                ledger.release_liability_in_transaction(CapitalSleeve.CONTINUOUS_SLEEVE,
                    amount_usd=request.maximum_loss_usd, reservation_key=request.execution_key,
                    broker_snapshot_sha256=snapshot_sha)
            ownership = ContractOwnershipStore(db)
            if ownership.projection().owner_of(request.canonical_contract.sha256) is not None:
                ownership.release_in_transaction(request.canonical_contract.sha256,
                    ReleaseEvidence(position_quantity=Decimal(0), open_order_count=0,
                                    pending_execution_count=0, child_position_count=0, fill_ambiguity=False,
                                    broker_snapshot_sha256=snapshot_sha, expected_broker_snapshot_sha256=snapshot_sha,
                                    broker_snapshot_fresh=True))
        return True

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
        reconciled = (flat and fees_complete
                      and Decimal(0) < quantities["BUY"] == quantities["SELL"] <= request.quantity)
        sleeve = CapitalSleeve.CONTINUOUS_SLEEVE
        with Database.open(self.db_path) as db, db.transaction():
            ownership = ContractOwnershipStore(db).projection()
            owned = ownership.owner_of(request.canonical_contract.sha256)
            if owned is None or owned.sleeve is not sleeve:
                raise ValueError("CANARY_OWNERSHIP_REQUIRED")
            events = store._verified_events(db)
            ledger = SleeveLedgerStore(db)
            prior = ledger._events()
            net_imported = any(e['event_type'] == 'BROKER_NET_PNL_RECONCILED'
                               and e.get('request_sha256') == request.sha256 for e in prior)

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
                if not net_imported and not fee_imported and fill.get("commission") is not None and fill.get("commission_currency") == "USD":
                    fee = Decimal(str(fill["commission"]))
                    if fee > 0:
                        insert("CURRENCY_DEBIT", {"amount": str(fee)})
                        insert("FEE_CHARGED", {"amount_usd": str(fee)})
                    insert("CANARY_FEE_IMPORTED", {"execution_id_sha256": key, "commission": str(fee)})
            if reconciled and not net_imported and not any(e["event_type"] == "CANARY_ECONOMICS_IMPORTED" and e.get("request_sha256") == request.sha256 for e in prior):
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
            previous = next((e for e in events
                             if e.get("event_type") == "BROKER_NET_PNL_RECONCILED"
                             and e.get("request_sha256") == request.sha256), None)
            if previous is not None:
                if (Decimal(previous["broker_realized_pnl_usd"]) != broker_net
                        or Decimal(previous["cost_difference_usd"]) != cost_difference):
                    raise ValueError("CANARY_BROKER_PNL_CONFLICT")
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

            imported_fees = sum((Decimal(e['commission']) for e in prior
                                 if e['event_type'] == 'CANARY_FEE_IMPORTED'
                                 and e.get('execution_id_sha256') in imported_keys), Decimal(0))
            remaining_cost = cost_difference - imported_fees
            already_realized = Decimal(0)
            for index, event in enumerate(prior):
                if (event["event_type"] == "CANARY_ECONOMICS_IMPORTED"
                        and event.get("request_sha256") == request.sha256):
                    if index == 0 or prior[index - 1]["event_type"] != "REALIZED_PNL":
                        raise ValueError("CANARY_PRIOR_PNL_BINDING_INVALID")
                    already_realized += Decimal(prior[index - 1]["amount_usd"])
            insert("REALIZED_PNL", {"amount_usd": str(broker_net - already_realized)})
            if remaining_cost > 0:
                if state.balance("USD") < remaining_cost:
                    raise ValueError("SLEEVE_CURRENCY_INSUFFICIENT_FOR_COST_DIFFERENCE")
                insert("CURRENCY_DEBIT", {"amount": str(remaining_cost)})
            elif remaining_cost < 0:
                insert("CURRENCY_CREDIT", {"amount": str(-remaining_cost)})
            insert(
                "BROKER_NET_PNL_RECONCILED",
                {
                    "evidence_sha256": evidence_sha256,
                    "request_sha256": request.sha256,
                    "broker_realized_pnl_usd": str(broker_net),
                    "gross_execution_pnl_usd": str(gross_pnl),
                    "cost_difference_usd": str(cost_difference),
                    "candidate_fee_allowance_usd": str(fee_allowance),
                    "already_imported_individual_fees_usd": str(imported_fees),
                    "cost_difference_exceeds_candidate_fee_allowance": exceeds_allowance,
                    "observation": observation,
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
                    "observation": observation,
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
