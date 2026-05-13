"""Forensic analysis of YoelSAI V1.1b backtest trades."""
import json, time, requests, os
from hashlib import sha256
from base64 import b64encode
from collections import defaultdict
from datetime import datetime

UID = "384945"
TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
BASE = "https://www.quantconnect.com/api/v2"
PROJECT_ID = 29490680
BT_ID = "01a9c230219f519cea2da7e95abdaa72"

def headers():
    ts = str(int(time.time()))
    h = sha256(f"{TOKEN}:{ts}".encode()).hexdigest()
    auth = b64encode(f"{UID}:{h}".encode()).decode()
    return {"Authorization": f"Basic {auth}", "Timestamp": ts, "Content-Type": "application/json"}

# 1. Get orders from API
print("=" * 70)
print("FETCHING ORDERS FROM QC API...")
print("=" * 70)
r = requests.post(f"{BASE}/backtests/orders", headers=headers(), json={
    "projectId": PROJECT_ID, "backtestId": BT_ID, "start": 0, "end": 2000
})
orders_data = r.json()
orders = orders_data.get("orders", [])
print(f"Total orders fetched: {len(orders)}")

# Save raw orders
with open("C:/AI_VAULT/tmp_agent/strategies/yoel_sai/orders_raw.json", "w") as f:
    json.dump(orders, f, indent=2, default=str)
print("Saved orders_raw.json")

# 2. Parse orders into round-trip trades
buys = {}   # symbol -> order info
trades = []  # completed round trips

for o in orders:
    sym = o.get("symbol", {}).get("value", "unknown")
    qty = o.get("quantity", 0)
    status = o.get("status", "")
    tag = o.get("tag", "")
    fill_price = 0
    fill_time = None
    
    events = o.get("orderEvents", [])
    for ev in events:
        if ev.get("status") == "filled":
            fill_price = ev.get("fillPrice", 0)
            fill_time = ev.get("time", "")
            break
    
    if fill_price == 0:
        continue
    
    if qty > 0:  # BUY
        buys[sym] = {
            "entry_price": fill_price,
            "entry_time": fill_time,
            "qty": qty,
            "tag": tag,
            "symbol": sym
        }
    elif qty < 0:  # SELL
        if sym in buys:
            entry = buys[sym]
            pnl_pct = (fill_price - entry["entry_price"]) / entry["entry_price"] * 100 if entry["entry_price"] > 0 else 0
            pnl_dollar = (fill_price - entry["entry_price"]) * abs(qty) * 100  # options multiplier
            
            # Determine strategy from tag
            strategy = "Unknown"
            if "S5" in entry["tag"]: strategy = "S5-GapUp-PUT"
            elif "S6" in entry["tag"]: strategy = "S6-GapDn-CALL"
            elif "S7" in entry["tag"]: strategy = "S7-Iman-CALL"
            elif "S8" in entry["tag"]: strategy = "S8-Iman-PUT"
            
            # Determine exit type
            exit_type = "Unknown"
            if "TP@" in tag: exit_type = "TP"
            elif "SL@" in tag: exit_type = "SL"
            elif "EOD" in tag or "3PM" in tag: exit_type = "EOD"
            elif "Cleanup" in tag: exit_type = "Cleanup"
            elif "Expiry" in tag: exit_type = "Expiry"
            
            entry_dt = entry["entry_time"][:10] if entry["entry_time"] else "?"
            exit_dt = fill_time[:10] if fill_time else "?"
            
            trades.append({
                "entry_date": entry_dt,
                "exit_date": exit_dt,
                "entry_time": entry["entry_time"],
                "exit_time": fill_time,
                "strategy": strategy,
                "exit_type": exit_type,
                "entry_price": entry["entry_price"],
                "exit_price": fill_price,
                "qty": entry["qty"],
                "pnl_pct": round(pnl_pct, 2),
                "pnl_dollar": round(pnl_dollar, 2),
                "entry_tag": entry["tag"],
                "exit_tag": tag,
                "symbol": sym
            })
            del buys[sym]

print(f"\nTotal round-trip trades parsed: {len(trades)}")
print(f"Orphan buys (no matching sell): {len(buys)}")

# 3. ANALYSIS
print("\n" + "=" * 70)
print("STRATEGY BREAKDOWN")
print("=" * 70)

by_strat = defaultdict(list)
for t in trades:
    by_strat[t["strategy"]].append(t)

for strat in sorted(by_strat.keys()):
    tt = by_strat[strat]
    wins = [t for t in tt if t["pnl_pct"] > 0]
    losses = [t for t in tt if t["pnl_pct"] <= 0]
    total_pnl = sum(t["pnl_dollar"] for t in tt)
    avg_win = sum(t["pnl_pct"] for t in wins) / len(wins) if wins else 0
    avg_loss = sum(t["pnl_pct"] for t in losses) / len(losses) if losses else 0
    wr = len(wins) / len(tt) * 100 if tt else 0
    
    print(f"\n{strat}:")
    print(f"  Trades: {len(tt)} | Wins: {len(wins)} | Losses: {len(losses)}")
    print(f"  Win Rate: {wr:.1f}%")
    print(f"  Avg Win: {avg_win:.2f}% | Avg Loss: {avg_loss:.2f}%")
    print(f"  Total P&L: ${total_pnl:,.2f}")

# 4. EXIT TYPE ANALYSIS
print("\n" + "=" * 70)
print("EXIT TYPE BREAKDOWN")
print("=" * 70)

by_exit = defaultdict(list)
for t in trades:
    by_exit[t["exit_type"]].append(t)

for exit_type in sorted(by_exit.keys()):
    tt = by_exit[exit_type]
    wins = [t for t in tt if t["pnl_pct"] > 0]
    losses = [t for t in tt if t["pnl_pct"] <= 0]
    total_pnl = sum(t["pnl_dollar"] for t in tt)
    avg_pnl = sum(t["pnl_pct"] for t in tt) / len(tt) if tt else 0
    
    print(f"\n{exit_type}:")
    print(f"  Count: {len(tt)} | Wins: {len(wins)} | Losses: {len(losses)}")
    print(f"  Avg P&L%: {avg_pnl:.2f}%")
    print(f"  Total P&L: ${total_pnl:,.2f}")

# 5. WORST DAYS
print("\n" + "=" * 70)
print("TOP 20 WORST TRADES (biggest $ losses)")
print("=" * 70)

sorted_by_pnl = sorted(trades, key=lambda t: t["pnl_dollar"])
for i, t in enumerate(sorted_by_pnl[:20]):
    print(f"  {i+1:2d}. {t['entry_date']} | {t['strategy']:20s} | Exit: {t['exit_type']:7s} | "
          f"Entry: ${t['entry_price']:.2f} → Exit: ${t['exit_price']:.2f} | "
          f"P&L: {t['pnl_pct']:+.1f}% (${t['pnl_dollar']:+,.0f}) | Qty: {t['qty']}")

# 6. BEST DAYS (to understand what works)
print("\n" + "=" * 70)
print("TOP 20 BEST TRADES (biggest $ wins)")
print("=" * 70)

sorted_by_pnl_desc = sorted(trades, key=lambda t: t["pnl_dollar"], reverse=True)
for i, t in enumerate(sorted_by_pnl_desc[:20]):
    print(f"  {i+1:2d}. {t['entry_date']} | {t['strategy']:20s} | Exit: {t['exit_type']:7s} | "
          f"Entry: ${t['entry_price']:.2f} → Exit: ${t['exit_price']:.2f} | "
          f"P&L: {t['pnl_pct']:+.1f}% (${t['pnl_dollar']:+,.0f}) | Qty: {t['qty']}")

# 7. MONTHLY P&L
print("\n" + "=" * 70)
print("MONTHLY P&L")
print("=" * 70)

by_month = defaultdict(list)
for t in trades:
    month = t["entry_date"][:7]
    by_month[month].append(t)

for month in sorted(by_month.keys()):
    tt = by_month[month]
    total = sum(t["pnl_dollar"] for t in tt)
    wins = len([t for t in tt if t["pnl_pct"] > 0])
    losses = len([t for t in tt if t["pnl_pct"] <= 0])
    print(f"  {month}: {len(tt):3d} trades | W:{wins:2d} L:{losses:2d} | P&L: ${total:+10,.0f} | {'+++' if total > 0 else '---'}")

# 8. STRATEGY + EXIT CROSS-ANALYSIS
print("\n" + "=" * 70)
print("STRATEGY x EXIT TYPE CROSS-TABLE (avg P&L %)")
print("=" * 70)

strats = sorted(set(t["strategy"] for t in trades))
exits = sorted(set(t["exit_type"] for t in trades))
print(f"{'':25s}", end="")
for e in exits:
    print(f"{e:>10s}", end="")
print(f"{'TOTAL':>10s}")

for s in strats:
    print(f"{s:25s}", end="")
    for e in exits:
        tt = [t for t in trades if t["strategy"] == s and t["exit_type"] == e]
        if tt:
            avg = sum(t["pnl_pct"] for t in tt) / len(tt)
            print(f"{avg:+9.1f}%", end="")
        else:
            print(f"{'---':>10s}", end="")
    # total for strategy
    tt = [t for t in trades if t["strategy"] == s]
    avg = sum(t["pnl_pct"] for t in tt) / len(tt) if tt else 0
    print(f"{avg:+9.1f}%")

# Count table
print(f"\n{'(count)':25s}", end="")
for e in exits:
    print(f"{e:>10s}", end="")
print(f"{'TOTAL':>10s}")

for s in strats:
    print(f"{s:25s}", end="")
    for e in exits:
        tt = [t for t in trades if t["strategy"] == s and t["exit_type"] == e]
        print(f"{len(tt):>10d}", end="")
    tt = [t for t in trades if t["strategy"] == s]
    print(f"{len(tt):>10d}")

# 9. TIME-OF-DAY analysis for exits
print("\n" + "=" * 70)
print("HOLDING TIME ANALYSIS")
print("=" * 70)

for t in trades:
    try:
        entry_dt = datetime.fromisoformat(t["entry_time"].replace("Z", "+00:00")) if t["entry_time"] else None
        exit_dt = datetime.fromisoformat(t["exit_time"].replace("Z", "+00:00")) if t["exit_time"] else None
        if entry_dt and exit_dt:
            t["hold_minutes"] = (exit_dt - entry_dt).total_seconds() / 60
        else:
            t["hold_minutes"] = None
    except:
        t["hold_minutes"] = None

for exit_type in sorted(by_exit.keys()):
    tt = [t for t in by_exit[exit_type] if t.get("hold_minutes") is not None]
    if tt:
        avg_hold = sum(t["hold_minutes"] for t in tt) / len(tt)
        min_hold = min(t["hold_minutes"] for t in tt)
        max_hold = max(t["hold_minutes"] for t in tt)
        print(f"  {exit_type:10s}: avg {avg_hold:.0f} min | min {min_hold:.0f} min | max {max_hold:.0f} min")

# 10. ENTRY PRICE ANALYSIS (are we paying too much for premium?)
print("\n" + "=" * 70)
print("ENTRY PREMIUM ANALYSIS")
print("=" * 70)

premiums = [t["entry_price"] for t in trades]
avg_premium = sum(premiums) / len(premiums) if premiums else 0
print(f"  Avg entry premium: ${avg_premium:.2f}")
print(f"  Min: ${min(premiums):.2f} | Max: ${max(premiums):.2f}")

# Premium vs outcome
cheap = [t for t in trades if t["entry_price"] < 2.0]
mid = [t for t in trades if 2.0 <= t["entry_price"] < 5.0]
expensive = [t for t in trades if t["entry_price"] >= 5.0]

for label, group in [("< $2", cheap), ("$2-5", mid), (">= $5", expensive)]:
    if group:
        wr = len([t for t in group if t["pnl_pct"] > 0]) / len(group) * 100
        avg = sum(t["pnl_pct"] for t in group) / len(group)
        total = sum(t["pnl_dollar"] for t in group)
        print(f"  Premium {label:6s}: {len(group):3d} trades | WR: {wr:.1f}% | Avg P&L: {avg:+.2f}% | Total: ${total:+,.0f}")

# Save analysis
with open("C:/AI_VAULT/tmp_agent/strategies/yoel_sai/trades_parsed.json", "w") as f:
    json.dump(trades, f, indent=2, default=str)
print(f"\n[SAVED] trades_parsed.json ({len(trades)} trades)")

print("\n" + "=" * 70)
print("ANALYSIS COMPLETE")
print("=" * 70)
