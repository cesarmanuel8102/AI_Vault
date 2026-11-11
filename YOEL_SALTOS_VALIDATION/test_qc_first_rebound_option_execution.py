from pathlib import Path


SOURCE = (
    Path(__file__).parent / "Yoel First Rebound Options 20261025" / "main.py"
).read_text()


def test_debit_spread_uses_atomic_combo_orders_for_entry_and_exit():
    entry = SOURCE.split("def _enter_ready_contracts", 1)[1].split(
        "def _manage_positions", 1
    )[0]
    close = SOURCE.split("def _close", 1)[1].split("def _age_positions", 1)[0]

    assert "self.combo_market_order(" in entry
    assert "self.combo_market_order(" in close


def test_position_state_changes_only_after_filled_tickets_are_verified():
    entry = SOURCE.split("def _enter_ready_contracts", 1)[1].split(
        "def _manage_positions", 1
    )[0]
    close = SOURCE.split("def _close", 1)[1].split("def _age_positions", 1)[0]

    assert entry.index("OrderStatus.FILLED") < entry.index("self.positions[ticker] =")
    assert close.index("OrderStatus.FILLED") < close.index("self.positions.pop(")


def test_backtest_boundary_flattens_before_the_end_date():
    assert "def _flatten_at_backtest_boundary" in SOURCE
    assert "self._flatten_at_backtest_boundary" in SOURCE
    boundary = SOURCE.split("def _flatten_at_backtest_boundary", 1)[1].split(
        "def on_end_of_algorithm", 1
    )[0]
    assert "self.liquidate(" in boundary
