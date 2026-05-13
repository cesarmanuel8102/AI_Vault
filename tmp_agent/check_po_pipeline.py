"""Quick check of PO pipeline state — run periodically to monitor."""
import json, urllib.request, sys

def fetch(url):
    try:
        with urllib.request.urlopen(url, timeout=5) as r:
            return json.loads(r.read())
    except Exception as e:
        return {"error": str(e)}

# Features
features = fetch("http://localhost:8090/brain/strategy-engine/features")
for item in features.get("items", []):
    if item.get("venue") == "pocket_option" and "1m" in item.get("key", ""):
        rsi = item.get("rsi_14", 0)
        stk = item.get("stoch_k", 0)
        std = item.get("stoch_d", 0)
        bbp = item.get("bb_pct_b", 0)
        adx = item.get("adx", 0)
        pay = item.get("payout_pct", 0)
        vol = item.get("volatility_proxy_pct", 0)
        regime = item.get("market_regime", "?")
        session = item.get("session_name", "?")
        candles = item.get("candle_count", 0)
        rsi_extreme = "**EXTREME**" if rsi > 70 or rsi < 30 else ""
        stk_extreme = "**EXTREME**" if stk > 80 or stk < 20 else ""
        bbp_extreme = "**EXTREME**" if bbp > 0.95 or bbp < 0.05 else ""
        print(f"=== PO 1m Features ===")
        print(f"  RSI:    {rsi:6.2f} {rsi_extreme}")
        print(f"  StochK: {stk:6.2f} {stk_extreme}")
        print(f"  StochD: {std:6.2f}")
        print(f"  BB%b:   {bbp:6.4f} {bbp_extreme}")
        print(f"  ADX:    {adx:6.2f}")
        print(f"  Payout: {pay:.0f}%  Vol: {vol:.4f}")
        print(f"  Regime: {regime}  Session: {session}  Candles: {candles}")

# Signals
signals = fetch("http://localhost:8090/brain/strategy-engine/signals")
po_signals = [i for i in signals.get("items", []) if "po_" in i.get("strategy_id", "")]
ready_count = 0
for item in po_signals:
    sigs = item.get("signals", [])
    for s in sigs:
        if s.get("execution_ready"):
            ready_count += 1
            print(f"\n*** SIGNAL READY: {item['strategy_id']} ***")
            print(f"  dir={s.get('direction')} conf={s.get('confidence')} valid={s.get('signal_valid')}")
if ready_count == 0:
    print(f"\nSignals: 0 ready ({len(po_signals)} PO items, signals not yet at extremes)")

# Candidates
cands = fetch("http://localhost:8090/brain/strategy-engine/candidates")
for c in cands.get("candidates", []):
    if "po_" in c.get("strategy_id", ""):
        print(f"\n{c['strategy_id']}:")
        print(f"  edge={c.get('edge_state')} lane={c.get('execution_lane')}")
        print(f"  exec_rdy={c.get('execution_ready_now')} sig_rdy={c.get('signal_ready')}")
        print(f"  ctx_edge={c.get('current_context_edge_state')} ctx_allowed={c.get('current_context_execution_allowed')}")
        print(f"  dl_grace={'YES' if c.get('deadlock_unfreeze_utc') else 'NO'}")

top = cands.get("top_candidate")
recov = cands.get("top_recovery_candidate")
prob = cands.get("probation_candidate")
print(f"\nTop: {(top or {}).get('strategy_id', 'None')}")
print(f"Recovery: {(recov or {}).get('strategy_id', 'None')}")
print(f"Probation: {(prob or {}).get('strategy_id', 'None')}")

# Bridge
bridge = fetch("http://localhost:8765/health")
print(f"\nBridge: connected={bridge.get('connected')} fresh={bridge.get('is_fresh')} order_ready={bridge.get('demo_order_api_ready')}")
