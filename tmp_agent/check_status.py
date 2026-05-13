import json, time

time.sleep(15)

# Feature snapshot
d = json.load(open('C:/AI_VAULT/tmp_agent/state/strategy_engine/market_feature_snapshot_latest.json'))
items = d.get('items', [])
for item in items:
    if 'EURUSD' in str(item.get('symbol', '')):
        print(f"candle_alive_ratio: {item.get('candle_alive_ratio')}")
        print(f"candle_count: {item.get('candle_count')}")
        print(f"price_frozen: {item.get('price_frozen')}")
        print(f"captured_utc: {item.get('captured_utc')}")
        break

# Candle buffer
d2 = json.load(open('C:/AI_VAULT/tmp_agent/state/strategy_engine/po_candle_buffer.json'))
candles = d2.get('candles', [])
alive = sum(1 for c in candles if abs(c.get('h', 0) - c.get('l', 0)) > 1e-7)
print(f"\nCandle buffer: {len(candles)} total, {alive} alive")
last20 = candles[-20:] if len(candles) >= 20 else candles
alive20 = sum(1 for c in last20 if abs(c.get('h', 0) - c.get('l', 0)) > 1e-7)
print(f"Last {len(last20)} alive ratio: {alive20}/{len(last20)} = {alive20/len(last20):.0%}" if last20 else "No candles")

# Signal snapshot
d3 = json.load(open('C:/AI_VAULT/tmp_agent/state/strategy_engine/strategy_signal_snapshot_latest.json'))
items3 = d3.get('items', [])
for item in items3:
    print(f"\nStrategy: {item.get('strategy_id')}")
    print(f"  signal: {item.get('signal')}")
    print(f"  direction: {item.get('direction')}")
    print(f"  blockers: {item.get('blockers', [])}")
    reasons = item.get('signal_reasons', [])
    print(f"  signal_reasons: {len(reasons)}")
    for r in reasons[:5]:
        print(f"    - {r}")
