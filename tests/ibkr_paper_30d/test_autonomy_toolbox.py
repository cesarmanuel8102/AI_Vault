from __future__ import annotations

from ibkr_paper_30d.autonomy_toolbox import AutonomyToolbox

SERVER_TIME = "2026-09-28T14:43:04Z"


class BrokerBaseToolbox:
    def __init__(self):
        self.calls = []
        self.proposal_validation = object()
        self.position_validation = object()
        self.open_order_validation = object()
        self.connection = object()
        self.contract = object()
        self.position = object()
        self.quote = {"success": True, "market_data_type": 1}

    def manifest(self):
        return []

    def _account_state(self, _arguments):
        return {
            "server_time_utc": SERVER_TIME,
            "net_liquidation": "253269.71",
            "cash": "252750.61",
            "buying_power": "1010762.18",
        }

    def _private_broker_operation(self):
        return "must-not-be-exposed"

    def validate_proposal(self, proposal, bundle, *, ib=None):
        self.calls.append(("validate_proposal", proposal, bundle, ib))
        return self.proposal_validation

    def validate_position_action(self, action, bundle, decision, *, ib=None):
        self.calls.append(
            ("validate_position_action", action, bundle, decision, ib)
        )
        return self.position_validation

    def validate_open_order_action(self, action, bundle, decision, *, ib=None):
        self.calls.append(
            ("validate_open_order_action", action, bundle, decision, ib)
        )
        return self.open_order_validation

    def _connect(self, *, client_id=None):
        self.calls.append(("_connect", client_id))
        return self.connection

    def _proposal_contract(self, ib, proposal):
        self.calls.append(("_proposal_contract", ib, proposal))
        return self.contract

    def _resolve_open_position(self, ib, action):
        self.calls.append(("_resolve_open_position", ib, action))
        return self.position

    def live_contract_quote_evidence(
        self, ib, contract, *, wait_seconds=2.0, max_age_seconds=15.0
    ):
        self.calls.append(
            (
                "live_contract_quote_evidence",
                ib,
                contract,
                wait_seconds,
                max_age_seconds,
            )
        )
        return self.quote


def test_toolbox_explicitly_exposes_only_broker_server_time() -> None:
    toolbox = AutonomyToolbox(BrokerBaseToolbox(), None)

    result = toolbox.broker_server_time_utc()

    assert result == SERVER_TIME
    assert isinstance(result, str)
    assert "253269" not in result
    assert "252750" not in result
    assert "1010762" not in result


def test_toolbox_has_no_generic_delegation_or_private_surface_expansion() -> None:
    toolbox = AutonomyToolbox(BrokerBaseToolbox(), None)

    assert "__getattr__" not in AutonomyToolbox.__dict__
    assert not hasattr(toolbox, "_account_state")
    assert not hasattr(toolbox, "_private_broker_operation")


def test_toolbox_explicit_validator_delegates_preserve_results_and_ib() -> None:
    base = BrokerBaseToolbox()
    toolbox = AutonomyToolbox(base, None)
    proposal = object()
    position_action = object()
    open_order_action = object()
    bundle = object()
    decision = object()
    ib = object()

    assert toolbox.validate_proposal(proposal, bundle) is base.proposal_validation
    assert (
        toolbox.validate_proposal(proposal, bundle, ib=ib)
        is base.proposal_validation
    )
    assert (
        toolbox.validate_position_action(position_action, bundle, decision)
        is base.position_validation
    )
    assert (
        toolbox.validate_position_action(
            position_action, bundle, decision, ib=ib
        )
        is base.position_validation
    )
    assert (
        toolbox.validate_open_order_action(open_order_action, bundle, decision)
        is base.open_order_validation
    )
    assert (
        toolbox.validate_open_order_action(
            open_order_action, bundle, decision, ib=ib
        )
        is base.open_order_validation
    )
    assert base.calls == [
        ("validate_proposal", proposal, bundle, None),
        ("validate_proposal", proposal, bundle, ib),
        ("validate_position_action", position_action, bundle, decision, None),
        ("validate_position_action", position_action, bundle, decision, ib),
        ("validate_open_order_action", open_order_action, bundle, decision, None),
        ("validate_open_order_action", open_order_action, bundle, decision, ib),
    ]


def test_toolbox_explicit_executor_host_delegates_preserve_arguments() -> None:
    base = BrokerBaseToolbox()
    toolbox = AutonomyToolbox(base, None)
    ib = object()
    proposal = object()
    action = object()
    contract = object()

    assert toolbox._connect(client_id=19761) is base.connection
    assert toolbox._proposal_contract(ib, proposal) is base.contract
    assert toolbox._resolve_open_position(ib, action) is base.position
    assert (
        toolbox.live_contract_quote_evidence(
            ib, contract, wait_seconds=1.25, max_age_seconds=7.5
        )
        is base.quote
    )
    assert base.calls == [
        ("_connect", 19761),
        ("_proposal_contract", ib, proposal),
        ("_resolve_open_position", ib, action),
        ("live_contract_quote_evidence", ib, contract, 1.25, 7.5),
    ]
