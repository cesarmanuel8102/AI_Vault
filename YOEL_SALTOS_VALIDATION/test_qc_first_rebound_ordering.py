from pathlib import Path


def test_entry_intent_is_published_before_market_order_can_fill():
    source = (Path(__file__).parent / "Yoel First Rebound 20261025" / "main.py").read_text()
    method = source.split("def _on_hourly", 1)[1].split("def on_data", 1)[0]
    publish = method.index("self.pending_entries[symbol] =")
    send = method.index("self.market_order(")
    assert publish < send
