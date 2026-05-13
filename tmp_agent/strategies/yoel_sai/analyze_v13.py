"""Forensic analysis of V1.3 backtest trades - reads from local saved file."""
import json
from datetime import datetime
from collections import defaultdict

# Load from local saved backtest result
with open("C:/AI_VAULT/tmp_agent/strategies/yoel_sai/backtest_results_v13.json") as f:
    data = json.load(f)

perf = data.get("totalPerformance", {})
closed = perf.get("closedTrades", [])
print(f"Total closed trades: {len(closed)}")

if not closed:
    print("NO TRADES FOUND")
    exit()

# Parse trades
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
    
    # Determine PUT or CALL from symbol
    sym_val = t.get("symbols", [{}])[0].get("value", "")
    is_call = "C0" in sym_val
    is_put = "P0" in sym_val
    option_type = "CALL" if is_call else ("PUT" if is_put else "UNKNOWN")
    
    trades.append({
        "entry_time": entry_time,
        "exit_time": exit_time,
        "duration_min": duration_min,
        "entry_px": entry_px,
        "exit_px": exit_px,
        "pnl": pnl,
        "pnl_pct": pnl_pct,
        "fees": fees,
        "mae": mae,
        "mae_pct": mae_pct,
        "mfe": mfe,
        "mfe_pct": mfe_pct,
        "is_win": is_win,
        "qty": qty,
        "entry_cost": entry_cost,
        "option_type": option_type,
        "symbol": sym_val
    })

print(f"\n{'='*60}")
print(f"  FORENSIC ANALYSIS V1.3 — {len(trades)} trades")
print(f"{'='*60}")

# 1. HOLDING TIME ANALYSIS
print(f"\n--- 1. HOLDING TIME ANALYSIS ---")
time_buckets = [
    ("0-15 min", 0, 15),
    ("15-30 min", 15, 30),
    ("30-60 min", 30, 60),
    ("60-90 min", 60, 90),
    ("90-120 min", 90, 120),
    ("2-4 hrs", 120, 240),
    ("4+ hrs", 240, 9999),
]

print(f"{'Time':<15} {'Trades':>7} {'WR':>7} {'P&L':>12} {'Avg P&L':>10}")
for label, lo, hi in time_buckets:
    bucket = [t for t in trades if lo <= t["duration_min"] < hi]
    if not bucket:
        print(f"{label:<15} {'0':>7}")
        continue
    wins = sum(1 for t in bucket if t["is_win"])
    wr = wins / len(bucket) * 100
    total_pnl = sum(t["pnl"] for t in bucket)
    avg_pnl = total_pnl / len(bucket)
    print(f"{label:<15} {len(bucket):>7} {wr:>6.1f}% ${total_pnl:>10,.0f} ${avg_pnl:>8,.0f}")

# 2. PUT vs CALL ANALYSIS
print(f"\n--- 2. PUT vs CALL ANALYSIS ---")
for otype in ["PUT", "CALL"]:
    subset = [t for t in trades if t["option_type"] == otype]
    if not subset:
        continue
    wins = sum(1 for t in subset if t["is_win"])
    wr = wins / len(subset) * 100
    total_pnl = sum(t["pnl"] for t in subset)
    avg_win = sum(t["pnl"] for t in subset if t["is_win"]) / max(1, wins)
    avg_loss = sum(t["pnl"] for t in subset if not t["is_win"]) / max(1, len(subset) - wins)
    pl_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else 0
    print(f"{otype}: {len(subset)} trades, WR {wr:.1f}%, P&L ${total_pnl:,.0f}, Avg Win ${avg_win:,.0f}, Avg Loss ${avg_loss:,.0f}, P/L Ratio {pl_ratio:.2f}")

# 3. MFE ON LOSERS
print(f"\n--- 3. MFE ON LOSERS (were profitable first?) ---")
losers = [t for t in trades if not t["is_win"]]
winners = [t for t in trades if t["is_win"]]
print(f"Total winners: {len(winners)}, Total losers: {len(losers)}")

losers_with_mfe = [t for t in losers if t["mfe"] > 0]
print(f"Losers that were profitable first: {len(losers_with_mfe)}/{len(losers)} ({len(losers_with_mfe)/len(losers)*100:.1f}%)")
if losers_with_mfe:
    avg_mfe = sum(t["mfe_pct"] for t in losers_with_mfe) / len(losers_with_mfe)
    total_mfe = sum(t["mfe"] for t in losers_with_mfe)
    avg_pnl_lost = sum(t["pnl"] for t in losers_with_mfe) / len(losers_with_mfe)
    print(f"Avg MFE % on those losers: {avg_mfe:.1f}%")
    print(f"Total profit left on table: ${total_mfe:,.0f}")
    print(f"Avg final P&L on those losers: ${avg_pnl_lost:,.0f}")

# 4. MAE ANALYSIS
print(f"\n--- 4. MAE ANALYSIS ---")
mae_buckets = [
    ("0-10%", 0, 10),
    ("10-20%", 10, 20),
    ("20-30%", 20, 30),
    ("30-50%", 30, 50),
    ("50-75%", 50, 75),
    ("75%+", 75, 999),
]

print(f"{'MAE':<12} {'Trades':>7} {'WR':>7} {'P&L':>12}")
for label, lo, hi in mae_buckets:
    bucket = [t for t in trades if lo <= t["mae_pct"] < hi]
    if not bucket:
        print(f"{label:<12} {'0':>7}")
        continue
    wins = sum(1 for t in bucket if t["is_win"])
    wr = wins / len(bucket) * 100
    total_pnl = sum(t["pnl"] for t in bucket)
    print(f"{label:<12} {len(bucket):>7} {wr:>6.1f}% ${total_pnl:>10,.0f}")

# 5. EXIT PATTERN ANALYSIS
print(f"\n--- 5. EXIT PATTERN ANALYSIS (estimated from P&L% and duration) ---")
tp_like = [t for t in trades if t["pnl_pct"] >= 20]
sl_like = [t for t in trades if t["pnl_pct"] <= -25]
time_stop_like = [t for t in trades if 85 <= t["duration_min"] <= 95 and t not in tp_like and t not in sl_like]
eod_like = [t for t in trades if t["duration_min"] > 200]

print(f"TP-like (P&L >= +20%): {len(tp_like)} trades, ${sum(t['pnl'] for t in tp_like):,.0f}")
print(f"SL-like (P&L <= -25%): {len(sl_like)} trades, ${sum(t['pnl'] for t in sl_like):,.0f}")
print(f"Time stop-like (85-95 min): {len(time_stop_like)} trades, ${sum(t['pnl'] for t in time_stop_like):,.0f}")
print(f"EOD-like (>200 min): {len(eod_like)} trades, ${sum(t['pnl'] for t in eod_like):,.0f}")

# 6. YEAR-BY-YEAR
print(f"\n--- 6. YEAR-BY-YEAR ---")
for year in [2021, 2022, 2023, 2024]:
    year_trades = [t for t in trades if t["entry_time"].year == year]
    if not year_trades:
        continue
    wins = sum(1 for t in year_trades if t["is_win"])
    wr = wins / len(year_trades) * 100
    total_pnl = sum(t["pnl"] for t in year_trades)
    print(f"{year}: {len(year_trades)} trades, WR {wr:.1f}%, P&L ${total_pnl:,.0f}")

# 7. MONTHLY DETAIL
print(f"\n--- 7. MONTHLY DETAIL ---")
monthly = defaultdict(list)
for t in trades:
    key = f"{t['entry_time'].year}-{t['entry_time'].month:02d}"
    monthly[key].append(t)

for key in sorted(monthly.keys()):
    m_trades = monthly[key]
    wins = sum(1 for t in m_trades if t["is_win"])
    wr = wins / len(m_trades) * 100
    total_pnl = sum(t["pnl"] for t in m_trades)
    print(f"{key}: {len(m_trades):>3} trades, WR {wr:>5.1f}%, P&L ${total_pnl:>8,.0f}")

# 8. WHAT-IF ANALYSES
print(f"\n--- 8. WHAT-IF SCENARIOS ---")

for label, filter_fn in [
    ("Only PUTs", lambda t: t["option_type"] == "PUT"),
    ("Only CALLs", lambda t: t["option_type"] == "CALL"),
    ("Only trades < 30 min", lambda t: t["duration_min"] < 30),
    ("Only trades < 45 min", lambda t: t["duration_min"] < 45),
    ("Only trades < 60 min", lambda t: t["duration_min"] < 60),
    ("Only PUTs < 45 min", lambda t: t["option_type"] == "PUT" and t["duration_min"] < 45),
    ("Only trades with MAE < 20%", lambda t: t["mae_pct"] < 20),
]:
    subset = [t for t in trades if filter_fn(t)]
    if not subset:
        print(f"\n{label}: 0 trades")
        continue
    wins = sum(1 for t in subset if t["is_win"])
    total_pnl = sum(t["pnl"] for t in subset)
    wr = wins / len(subset) * 100
    avg_win = sum(t["pnl"] for t in subset if t["is_win"]) / max(1, wins)
    avg_loss = sum(t["pnl"] for t in subset if not t["is_win"]) / max(1, len(subset) - wins)
    pl_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else 0
    breakeven_wr = 1 / (1 + pl_ratio) * 100 if pl_ratio > 0 else 100
    edge = wr - breakeven_wr
    print(f"\n{label}: {len(subset)} trades, WR {wr:.1f}%, P&L ${total_pnl:,.0f}")
    print(f"  Avg Win ${avg_win:,.0f}, Avg Loss ${avg_loss:,.0f}, P/L {pl_ratio:.2f}, Breakeven WR {breakeven_wr:.1f}%, Edge {edge:+.1f}%")

# 9. TRADE DURATION DISTRIBUTION
print(f"\n--- 9. DURATION DISTRIBUTION ---")
durations = sorted([t["duration_min"] for t in trades])
print(f"Min: {durations[0]:.0f} min, Max: {durations[-1]:.0f} min")
print(f"Median: {durations[len(durations)//2]:.0f} min")
print(f"Mean: {sum(durations)/len(durations):.0f} min")

# Count how many hit time stop exactly
time_stop_exact = [t for t in trades if 89 <= t["duration_min"] <= 91]
print(f"Trades at exactly ~90 min (time stop): {len(time_stop_exact)}")

# 10. CONSECUTIVE WIN/LOSS STREAKS
print(f"\n--- 10. CONSECUTIVE STREAKS ---")
max_win_streak = 0
max_loss_streak = 0
current_streak = 0
for t in sorted(trades, key=lambda x: x["entry_time"]):
    if t["is_win"]:
        if current_streak > 0:
            current_streak += 1
        else:
            current_streak = 1
        max_win_streak = max(max_win_streak, current_streak)
    else:
        if current_streak < 0:
            current_streak -= 1
        else:
            current_streak = -1
        max_loss_streak = max(max_loss_streak, abs(current_streak))

print(f"Max consecutive wins: {max_win_streak}")
print(f"Max consecutive losses: {max_loss_streak}")

# 11. COMPARISON TABLE: V1.1b vs V1.2 vs V1.3
print(f"\n{'='*60}")
print(f"  V1.3 TRADE STATISTICS SUMMARY")
print(f"{'='*60}")
ts = perf.get("tradeStatistics", {})
print(f"Total trades: {ts.get('totalNumberOfTrades', 'N/A')}")
print(f"Winners: {ts.get('numberOfWinningTrades', 'N/A')}")
print(f"Losers: {ts.get('numberOfLosingTrades', 'N/A')}")
print(f"Win Rate: {float(ts.get('winRate', 0))*100:.1f}%")
print(f"P/L Ratio: {ts.get('profitLossRatio', 'N/A')}")
print(f"Avg Profit: ${float(ts.get('averageProfit', 0)):,.2f}")
print(f"Avg Loss: ${float(ts.get('averageLoss', 0)):,.2f}")
print(f"Avg Trade Duration: {ts.get('averageTradeDuration', 'N/A')}")
print(f"Avg Winning Duration: {ts.get('averageWinningTradeDuration', 'N/A')}")
print(f"Avg Losing Duration: {ts.get('averageLosingTradeDuration', 'N/A')}")
print(f"Profit Factor: {ts.get('profitFactor', 'N/A')}")
print(f"Total Fees: ${float(ts.get('totalFees', 0)):,.2f}")

print("\nDONE")
