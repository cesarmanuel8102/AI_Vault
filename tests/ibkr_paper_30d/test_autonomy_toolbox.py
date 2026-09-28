from __future__ import annotations

from ibkr_paper_30d.autonomy_toolbox import AutonomyToolbox

SERVER_TIME = "2026-09-28T14:43:04Z"


class BrokerBaseToolbox:
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
