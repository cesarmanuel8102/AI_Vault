"""Forensic analysis of V1.4 backtest trades."""
import json
from datetime import datetime
from collections import defaultdict

with open("C:/AI_VAULT/tmp_agent/strategies/yoel_sai/backtest_results_v14.json") as f:
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
    
    entry_px = t["entryPrice"]
    exit_px = t["exitPrice"]
    pnl = t["profitLoss"]
    fees = t["totalFees"]
    mae = t.get("mae", 0)
    mfe = t.get("mfe", 0)
    is_win = t["isWin"]
    qty = abs(t["quantity"])
    
    entry_cost = entry_px * qty * 100 if entry_px > 0 else 1
    pnl_pct = pnl / entry_cost * 100 if entry_cost > 0 else 0
    mae_pct = abs(mae) / entry_cost * 100 if entry_cost > 0 else 0
    mfe_pct = mfe / entry_cost * 100 if entry_cost > 0 else 0
    
    sym_val = t.get("symbols", [{}])[0].get("value", "")
    is_call = "C0" in sym_val
    is_put = "P0" in sym_val
    option_type = "CALL" if is_call else ("PUT" if is_put else "UNKNOWN")
    
    trades.append({
        "entry_time": entry_time, "exit_time": exit_time, "duration_min": duration_min,
        "entry_px": entry_px, "exit_px": exit_px, "pnl": pnl, "pnl_pct": pnl_pct,
        "fees": fees, "mae": mae, "mae_pct": mae_pct, "mfe": mfe, "mfe_pct": mfe_pct,
        "is_win": is_win, "qty": qty, "entry_cost": entry_cost, "option_type": option_type,
    })

print(f"\n{'='*60}")
print(f"  FORENSIC ANALYSIS V1.4 — {len(trades)} trades")
print(f"{'='*60}")

# 1. HOLDING TIME
print(f"\n--- 1. HOLDING TIME ---")
buckets = [("0-15", 0, 15), ("15-30", 15, 30), ("30-45", 30, 45), ("45-60", 45, 60), ("60-90", 60, 90), ("90+", 90, 9999)]
print(f"{'Time':<10} {'N':>5} {'WR':>7} {'P&L':>12} {'Avg':>10}")
for label, lo, hi in buckets:
    b = [t for t in trades if lo <= t["duration_min"] < hi]
    if not b: print(f"{label:<10} {'0':>5}"); continue
    w = sum(1 for t in b if t["is_win"])
    print(f"{label:<10} {len(b):>5} {w/len(b)*100:>6.1f}% ${sum(t['pnl'] for t in b):>10,.0f} ${sum(t['pnl'] for t in b)/len(b):>8,.0f}")

# 2. PUT vs CALL
print(f"\n--- 2. PUT vs CALL ---")
for otype in ["PUT", "CALL"]:
    s = [t for t in trades if t["option_type"] == otype]
    if not s: continue
    w = sum(1 for t in s if t["is_win"])
    aw = sum(t["pnl"] for t in s if t["is_win"]) / max(1, w)
    al = sum(t["pnl"] for t in s if not t["is_win"]) / max(1, len(s) - w)
    pl = abs(aw / al) if al != 0 else 0
    print(f"{otype}: {len(s)} trades, WR {w/len(s)*100:.1f}%, P&L ${sum(t['pnl'] for t in s):,.0f}, P/L {pl:.2f}")

# 3. MAE
print(f"\n--- 3. MAE ---")
mae_b = [("0-5%", 0, 5), ("5-10%", 5, 10), ("10-15%", 10, 15), ("15-20%", 15, 20), ("20-30%", 20, 30), ("30%+", 30, 999)]
print(f"{'MAE':<10} {'N':>5} {'WR':>7} {'P&L':>12}")
for label, lo, hi in mae_b:
    b = [t for t in trades if lo <= t["mae_pct"] < hi]
    if not b: print(f"{label:<10} {'0':>5}"); continue
    w = sum(1 for t in b if t["is_win"])
    print(f"{label:<10} {len(b):>5} {wr:>6.1f}% ${sum(t['pnl'] for t in b):>10,.0f}" if (wr := w/len(b)*100) or True else "")

# 4. MFE on losers
print(f"\n--- 4. MFE ON LOSERS ---")
losers = [t for t in trades if not t["is_win"]]
losers_mfe = [t for t in losers if t["mfe"] > 0]
print(f"Losers: {len(losers)}, Losers with positive MFE: {len(losers_mfe)} ({len(losers_mfe)/max(1,len(losers))*100:.1f}%)")
if losers_mfe:
    print(f"Avg MFE% on those: {sum(t['mfe_pct'] for t in losers_mfe)/len(losers_mfe):.1f}%")
    print(f"Total MFE left on table: ${sum(t['mfe'] for t in losers_mfe):,.0f}")

# 5. YEAR-BY-YEAR
print(f"\n--- 5. YEAR-BY-YEAR ---")
for y in [2021, 2022, 2023, 2024]:
    yt = [t for t in trades if t["entry_time"].year == y]
    if not yt: continue
    w = sum(1 for t in yt if t["is_win"])
    print(f"{y}: {len(yt)} trades, WR {w/len(yt)*100:.1f}%, P&L ${sum(t['pnl'] for t in yt):,.0f}")

# 6. WHAT-IF
print(f"\n--- 6. WHAT-IF SCENARIOS ---")
for label, fn in [
    ("Only PUTs", lambda t: t["option_type"] == "PUT"),
    ("Only trades < 30 min", lambda t: t["duration_min"] < 30),
    ("Only PUTs < 30 min", lambda t: t["option_type"] == "PUT" and t["duration_min"] < 30),
    ("MAE < 15%", lambda t: t["mae_pct"] < 15),
    ("MAE < 10%", lambda t: t["mae_pct"] < 10),
]:
    s = [t for t in trades if fn(t)]
    if not s: print(f"\n{label}: 0 trades"); continue
    w = sum(1 for t in s if t["is_win"])
    aw = sum(t["pnl"] for t in s if t["is_win"]) / max(1, w)
    al = sum(t["pnl"] for t in s if not t["is_win"]) / max(1, len(s) - w)
    pl = abs(aw / al) if al != 0 else 0
    bwr = 1 / (1 + pl) * 100 if pl > 0 else 100
    edge = w/len(s)*100 - bwr
    print(f"\n{label}: {len(s)} trades, WR {w/len(s)*100:.1f}%, P&L ${sum(t['pnl'] for t in s):,.0f}")
    print(f"  AvgWin ${aw:,.0f}, AvgLoss ${al:,.0f}, P/L {pl:.2f}, BkEven WR {bwr:.1f}%, Edge {edge:+.1f}%")

# 7. Duration stats
print(f"\n--- 7. DURATION STATS ---")
ds = sorted([t["duration_min"] for t in trades])
print(f"Min: {ds[0]:.0f}, Max: {ds[-1]:.0f}, Median: {ds[len(ds)//2]:.0f}, Mean: {sum(ds)/len(ds):.0f}")
ts_exact = [t for t in trades if 58 <= t["duration_min"] <= 62]
print(f"Time stop (~60 min): {len(ts_exact)} trades")

# 8. Trade stats from QC
print(f"\n{'='*60}")
ts = perf.get("tradeStatistics", {})
print(f"Total: {ts.get('totalNumberOfTrades')}, Win: {ts.get('numberOfWinningTrades')}, Loss: {ts.get('numberOfLosingTrades')}")
print(f"WR: {float(ts.get('winRate',0))*100:.1f}%, P/L Ratio: {ts.get('profitLossRatio')}")
print(f"Avg Win: ${float(ts.get('averageProfit',0)):,.2f}, Avg Loss: ${float(ts.get('averageLoss',0)):,.2f}")
print(f"Avg Duration: {ts.get('averageTradeDuration')}")
print(f"Profit Factor: {ts.get('profitFactor')}")
print("\nDONE")
