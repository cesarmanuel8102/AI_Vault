"""Forensic analysis of V1.5 backtest trades."""
import json
from datetime import datetime
from collections import defaultdict

with open("C:/AI_VAULT/tmp_agent/strategies/yoel_sai/backtest_results_v15.json") as f:
    data = json.load(f)

perf = data.get("totalPerformance", {})
closed = perf.get("closedTrades", [])
print(f"Total closed trades: {len(closed)}")

if not closed:
    print("NO TRADES FOUND")
    exit()

trades = []
for t in closed:
    entry_time = datetime.fromisoformat(t["entryTime"].replace("Z", ""))
    exit_time = datetime.fromisoformat(t["exitTime"].replace("Z", ""))
    duration_min = (exit_time - entry_time).total_seconds() / 60.0
    entry_px = t["entryPrice"]; exit_px = t["exitPrice"]
    pnl = t["profitLoss"]; fees = t["totalFees"]
    mae = t.get("mae", 0); mfe = t.get("mfe", 0)
    is_win = t["isWin"]; qty = abs(t["quantity"])
    entry_cost = entry_px * qty * 100 if entry_px > 0 else 1
    pnl_pct = pnl / entry_cost * 100 if entry_cost > 0 else 0
    mae_pct = abs(mae) / entry_cost * 100 if entry_cost > 0 else 0
    mfe_pct = mfe / entry_cost * 100 if entry_cost > 0 else 0
    sym_val = t.get("symbols", [{}])[0].get("value", "")
    option_type = "CALL" if "C0" in sym_val else ("PUT" if "P0" in sym_val else "UNK")
    
    trades.append({
        "entry_time": entry_time, "exit_time": exit_time, "duration_min": duration_min,
        "entry_px": entry_px, "exit_px": exit_px, "pnl": pnl, "pnl_pct": pnl_pct,
        "fees": fees, "mae": mae, "mae_pct": mae_pct, "mfe": mfe, "mfe_pct": mfe_pct,
        "is_win": is_win, "qty": qty, "entry_cost": entry_cost, "option_type": option_type,
    })

print(f"\n{'='*60}")
print(f"  FORENSIC ANALYSIS V1.5 — {len(trades)} trades")
print(f"{'='*60}")

# Option type verification
puts = sum(1 for t in trades if t["option_type"] == "PUT")
calls = sum(1 for t in trades if t["option_type"] == "CALL")
print(f"\nPUTs: {puts}, CALLs: {calls} (should be 0 if PUTS_ONLY works)")

# 1. HOLDING TIME
print(f"\n--- 1. HOLDING TIME ---")
buckets = [("0-10", 0, 10), ("10-20", 10, 20), ("20-30", 20, 30), ("30-45", 30, 45), ("45-60", 45, 60), ("60+", 60, 9999)]
print(f"{'Time':<10} {'N':>5} {'WR':>7} {'P&L':>12} {'Avg':>10}")
for label, lo, hi in buckets:
    b = [t for t in trades if lo <= t["duration_min"] < hi]
    if not b: print(f"{label:<10} {'0':>5}"); continue
    w = sum(1 for t in b if t["is_win"])
    print(f"{label:<10} {len(b):>5} {w/len(b)*100:>6.1f}% ${sum(t['pnl'] for t in b):>10,.0f} ${sum(t['pnl'] for t in b)/len(b):>8,.0f}")

# 2. MAE
print(f"\n--- 2. MAE ---")
mae_b = [("0-5%", 0, 5), ("5-10%", 5, 10), ("10-15%", 10, 15), ("15-20%", 15, 20), ("20%+", 20, 999)]
print(f"{'MAE':<10} {'N':>5} {'WR':>7} {'P&L':>12}")
for label, lo, hi in mae_b:
    b = [t for t in trades if lo <= t["mae_pct"] < hi]
    if not b: print(f"{label:<10} {'0':>5}"); continue
    w = sum(1 for t in b if t["is_win"])
    print(f"{label:<10} {len(b):>5} {w/len(b)*100:>6.1f}% ${sum(t['pnl'] for t in b):>10,.0f}")

# 3. MFE on losers
print(f"\n--- 3. MFE ON LOSERS ---")
losers = [t for t in trades if not t["is_win"]]
losers_mfe = [t for t in losers if t["mfe"] > 0]
print(f"Losers: {len(losers)}, With positive MFE: {len(losers_mfe)} ({len(losers_mfe)/max(1,len(losers))*100:.1f}%)")
if losers_mfe:
    print(f"Avg MFE%: {sum(t['mfe_pct'] for t in losers_mfe)/len(losers_mfe):.1f}%")
    print(f"Total MFE left: ${sum(t['mfe'] for t in losers_mfe):,.0f}")

# 4. YEAR-BY-YEAR
print(f"\n--- 4. YEAR-BY-YEAR ---")
for y in [2021, 2022, 2023, 2024]:
    yt = [t for t in trades if t["entry_time"].year == y]
    if not yt: continue
    w = sum(1 for t in yt if t["is_win"])
    print(f"{y}: {len(yt)} trades, WR {w/len(yt)*100:.1f}%, P&L ${sum(t['pnl'] for t in yt):,.0f}")

# 5. MONTHLY
print(f"\n--- 5. MONTHLY ---")
monthly = defaultdict(list)
for t in trades:
    key = f"{t['entry_time'].year}-{t['entry_time'].month:02d}"
    monthly[key].append(t)
for key in sorted(monthly.keys()):
    m = monthly[key]
    w = sum(1 for t in m if t["is_win"])
    pnl = sum(t["pnl"] for t in m)
    print(f"{key}: {len(m):>3} trades, WR {w/len(m)*100:>5.1f}%, P&L ${pnl:>8,.0f}")

# 6. WHAT-IF
print(f"\n--- 6. WHAT-IF ---")
for label, fn in [
    ("All trades", lambda t: True),
    ("< 20 min", lambda t: t["duration_min"] < 20),
    ("< 30 min", lambda t: t["duration_min"] < 30),
    ("MAE < 10%", lambda t: t["mae_pct"] < 10),
    ("MAE < 15%", lambda t: t["mae_pct"] < 15),
]:
    s = [t for t in trades if fn(t)]
    if not s: continue
    w = sum(1 for t in s if t["is_win"])
    aw = sum(t["pnl"] for t in s if t["is_win"]) / max(1, w)
    al = sum(t["pnl"] for t in s if not t["is_win"]) / max(1, len(s) - w)
    pl = abs(aw / al) if al != 0 else 0
    bwr = 1 / (1 + pl) * 100 if pl > 0 else 100
    edge = w/len(s)*100 - bwr
    print(f"\n{label}: {len(s)} trades, WR {w/len(s)*100:.1f}%, P&L ${sum(t['pnl'] for t in s):,.0f}")
    print(f"  AvgWin ${aw:,.0f}, AvgLoss ${al:,.0f}, P/L {pl:.2f}, BkEven WR {bwr:.1f}%, Edge {edge:+.1f}%")

# 7. Stats
print(f"\n{'='*60}")
ts = perf.get("tradeStatistics", {})
print(f"Total: {ts.get('totalNumberOfTrades')}, Win: {ts.get('numberOfWinningTrades')}, Loss: {ts.get('numberOfLosingTrades')}")
print(f"WR: {float(ts.get('winRate',0))*100:.1f}%, P/L Ratio: {ts.get('profitLossRatio')}")
print(f"Avg Win: ${float(ts.get('averageProfit',0)):,.2f}, Avg Loss: ${float(ts.get('averageLoss',0)):,.2f}")
print(f"Expectancy: {float(ts.get('profitLossRatio','0')) * float(ts.get('winRate','0')) - float(ts.get('lossRate','0')):.3f}")
print(f"Profit Factor: {ts.get('profitFactor')}")
print(f"Max DD: {data.get('statistics',{}).get('Drawdown','N/A')}")
print("\nDONE")
