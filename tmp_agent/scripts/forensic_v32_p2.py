"""
Deep forensic analysis V3.2 — Part 2: Unrealized gains investigation
and exit reason reconstruction
"""
import json
import numpy as np
from collections import defaultdict
from datetime import datetime

with open("C:/AI_VAULT/tmp_agent/strategies/mtf_trend/bt_v32_trades.json", "r") as f:
    trades = json.load(f)

with open("C:/AI_VAULT/tmp_agent/strategies/mtf_trend/backtest_results_v32.json", "r") as f:
    bt = json.load(f)

print("=" * 70)
print("A. UNREALIZED GAINS INVESTIGATION")
print("=" * 70)

stats = bt.get("runtimeStatistics", {})
print(f"  Equity:      {stats.get('Equity','?')}")
print(f"  Holdings:    {stats.get('Holdings','?')}")
print(f"  Unrealized:  {stats.get('Unrealized','?')}")
print(f"  Net Profit:  {stats.get('Net Profit','?')}")
print(f"  Fees:        {stats.get('Fees','?')}")

total_closed_pnl = sum(t["profitLoss"] for t in trades)
total_fees = sum(t["totalFees"] for t in trades)
print(f"\n  Closed trades P/L:    ${total_closed_pnl:,.2f}")
print(f"  Closed trades fees:   ${total_fees:,.2f}")
print(f"  Expected equity (no unrealized): ${100000 + total_closed_pnl:,.2f}")
print(f"  Actual equity:        $154,371.09")
print(f"  Difference (unrealized): ${154371.09 - (100000 + total_closed_pnl):,.2f}")
print()
print("  ** CRITICAL: The 24.4% CAGR is INFLATED by $74K+ unrealized gains **")
print("  ** Without unrealized, real equity = $80K = -20% loss over 2 years **")

# Check last trades to find potential untracked positions
print()
print("=" * 70)
print("B. LAST TRADES — LOOKING FOR UNTRACKED POSITIONS")
print("=" * 70)

# Sort by exit time
by_exit = sorted(trades, key=lambda t: t["exitTime"])
print("  Last 20 closed trades:")
for t in by_exit[-20:]:
    syms = t.get("symbols", [])
    ticker = syms[0]["value"] if syms else "?"
    dirn = "L" if t["direction"] == 0 else "S"
    print(f"    {ticker:8s} {dirn} Entry:{t['entryTime'][:16]} Exit:{t['exitTime'][:16]} "
          f"Dur:{t['duration']:12s} P/L:${t['profitLoss']:>8,.2f} Qty:{t['quantity']}")

# Look for trades still open near end
print()
last_entries = sorted(trades, key=lambda t: t["entryTime"])
print("  Last 20 entries:")
for t in last_entries[-20:]:
    syms = t.get("symbols", [])
    ticker = syms[0]["value"] if syms else "?"
    dirn = "L" if t["direction"] == 0 else "S"
    print(f"    {ticker:8s} {dirn} Entry:{t['entryTime'][:16]} Exit:{t['exitTime'][:16]} "
          f"Dur:{t['duration']:12s} P/L:${t['profitLoss']:>8,.2f} Qty:{t['quantity']}")

# ===================== C. EXIT REASON RECONSTRUCTION =====================
print()
print("=" * 70)
print("C. EXIT REASON RECONSTRUCTION (from duration patterns)")
print("=" * 70)

def parse_duration_secs(d):
    if not d:
        return 0
    # Handle days format: "13.23:58:00"
    days = 0
    time_part = d
    if "." in d:
        parts = d.split(".")
        if len(parts) == 2 and ":" in parts[1]:
            # Could be days.HH:MM:SS or HH:MM:SS.fraction
            if ":" not in parts[0]:
                days = int(parts[0])
                time_part = parts[1]
            else:
                time_part = parts[0]  # HH:MM:SS, ignore fraction
        elif len(parts) == 3:
            # days.HH:MM:SS.fraction
            days = int(parts[0])
            time_part = parts[1]
    
    hms = time_part.split(":")
    hours = int(hms[0]) if hms[0] else 0
    minutes = int(hms[1]) if len(hms) > 1 else 0
    secs = int(hms[2].split(".")[0]) if len(hms) > 2 else 0
    return days * 86400 + hours * 3600 + minutes * 60 + secs

# Classify exits by duration
exit_reasons = defaultdict(lambda: {"count": 0, "pnl": 0, "wins": 0})

for t in trades:
    dur_s = parse_duration_secs(t["duration"])
    pnl = t["profitLoss"]
    mae = abs(t["mae"])
    mfe = t["mfe"]
    entry = t["entryPrice"]
    qty = t["quantity"]
    
    # Estimate exit reason from patterns
    if dur_s <= 60:
        # 1-min exit = immediate MAE cut or SL hit on first bar
        if mae > 0 and mfe == 0:
            reason = "Immediate SL/MAE (1st bar)"
        elif mae > 0 and mfe > 0:
            reason = "Quick reversal after brief profit"
        else:
            reason = "Unknown quick exit"
    elif dur_s <= 1800:  # <= 30 min
        if pnl < 0 and mfe == 0:
            reason = "SL/MAE hit (no profit ever)"
        elif pnl < 0 and mfe > 0:
            reason = "SL after brief MFE"
        else:
            reason = "Early profit exit"
    elif 1800 <= dur_s <= 2400:  # 30-40 min
        if pnl < 0:
            reason = "30-min losing rule"
        else:
            reason = "Unknown 30-40min exit"
    elif 10500 <= dur_s <= 11100:  # ~3 hours (with some slack)
        reason = "Time stop 3h"
    elif dur_s > 11100:
        reason = "Held >3h (possible bug)"
    else:
        if pnl < 0:
            reason = "SL/MAE mid-trade"
        else:
            reason = "Trailing stop profit"
    
    exit_reasons[reason]["count"] += 1
    exit_reasons[reason]["pnl"] += pnl
    if t["isWin"]:
        exit_reasons[reason]["wins"] += 1

print(f"  {'Exit Reason':40s} {'Count':>6s} {'WR':>6s} {'Total P/L':>12s}")
print(f"  {'-'*40} {'-'*6} {'-'*6} {'-'*12}")
for reason in sorted(exit_reasons.keys(), key=lambda r: exit_reasons[r]["pnl"]):
    d = exit_reasons[reason]
    wr = d["wins"] / d["count"] * 100 if d["count"] > 0 else 0
    print(f"  {reason:40s} {d['count']:6d} {wr:5.1f}% ${d['pnl']:>11,.2f}")

# ===================== D. 1-MIN TRADE DEEP DIVE =====================
print()
print("=" * 70)
print("D. 1-MIN TRADES DEEP DIVE — The $52K Hole")
print("=" * 70)

one_min = [t for t in trades if parse_duration_secs(t["duration"]) <= 60]

# Calculate gap between entry and exit for these
gaps = []
for t in one_min:
    entry = t["entryPrice"]
    exit_p = t["exitPrice"]
    dirn = t["direction"]
    if dirn == 0:  # long
        gap_pct = (exit_p - entry) / entry * 100
    else:  # short
        gap_pct = (entry - exit_p) / entry * 100
    gaps.append(gap_pct)

print(f"  Total 1-min trades: {len(one_min)}")
print(f"  Avg gap%: {np.mean(gaps):.2f}%")
print(f"  Median gap%: {np.median(gaps):.2f}%")
print(f"  Max adverse gap%: {min(gaps):.2f}%")
print(f"  Trades with >2% adverse gap: {sum(1 for g in gaps if g < -2)}")
print(f"  Trades with >5% adverse gap: {sum(1 for g in gaps if g < -5)}")

# Distribution of loss sizes
loss_sizes = [t["profitLoss"] for t in one_min if t["profitLoss"] < 0]
print(f"\n  1-min loss distribution:")
for label, lo, hi in [("$0-$100", 0, 100), ("$100-$300", 100, 300), ("$300-$500", 300, 500), 
                       ("$500-$1000", 500, 1000), ("$1000+", 1000, 99999)]:
    count = sum(1 for l in loss_sizes if lo <= abs(l) < hi)
    total = sum(l for l in loss_sizes if lo <= abs(l) < hi)
    print(f"    {label:12s}: {count:4d} trades, Total ${total:>10,.2f}")

# ===================== E. TRADES LASTING >3 HOURS — BUG? =====================
print()
print("=" * 70)
print("E. TRADES LASTING >3 HOURS — POSSIBLE TRACKING BUG")
print("=" * 70)

long_trades = [t for t in trades if parse_duration_secs(t["duration"]) > 11100]
print(f"  Trades >3h05m: {len(long_trades)}")
for t in sorted(long_trades, key=lambda t: parse_duration_secs(t["duration"]), reverse=True)[:15]:
    syms = t.get("symbols", [])
    ticker = syms[0]["value"] if syms else "?"
    dirn = "L" if t["direction"] == 0 else "S"
    print(f"    {ticker:8s} {dirn} Entry:{t['entryTime'][:16]} Exit:{t['exitTime'][:16]} "
          f"Dur:{t['duration']:15s} P/L:${t['profitLoss']:>8,.2f}")

# ===================== F. SETUP TYPE ANALYSIS =====================
print()
print("=" * 70)
print("F. TRADE CLUSTERING — Same day, same time entries")
print("=" * 70)

# Group by entry date
by_date = defaultdict(list)
for t in trades:
    date = t["entryTime"][:10]
    by_date[date].append(t)

# Find days with too many entries (>3 = max_positions bug?)
print("  Days with >3 entries:")
excess_days = {d: ts for d, ts in by_date.items() if len(ts) > 3}
print(f"  Count: {len(excess_days)}")
for date in sorted(excess_days.keys())[:10]:
    ts = excess_days[date]
    pnl = sum(t["profitLoss"] for t in ts)
    tickers = [t["symbols"][0]["value"] for t in ts if t.get("symbols")]
    print(f"    {date}: {len(ts)} trades, P/L ${pnl:,.2f}, Tickers: {', '.join(tickers[:6])}")

# ===================== G. EQUITY CURVE SHAPE =====================
print()
print("=" * 70)
print("G. CUMULATIVE P/L TRAJECTORY (closed trades only)")
print("=" * 70)

# Sort by exit time and compute cumulative P/L
sorted_trades = sorted(trades, key=lambda t: t["exitTime"])
cum_pnl = 0
checkpoints = []
for i, t in enumerate(sorted_trades):
    cum_pnl += t["profitLoss"]
    # Print every 100 trades
    if (i + 1) % 100 == 0 or i == len(sorted_trades) - 1:
        checkpoints.append((i + 1, t["exitTime"][:10], cum_pnl))

for count, date, cpnl in checkpoints:
    bar = "+" * int(cpnl / 1000) if cpnl > 0 else "-" * int(abs(cpnl) / 1000)
    print(f"  Trade {count:4d} ({date}): ${cpnl:>10,.2f} {bar}")

# Find max drawdown on closed P/L
peak = 0
max_dd = 0
for t in sorted_trades:
    cum_pnl_check = sum(tt["profitLoss"] for tt in sorted_trades[:sorted_trades.index(t)+1])
    # Actually let's do it properly
cum_pnl_2 = 0
peak = 0
max_dd = 0
for t in sorted_trades:
    cum_pnl_2 += t["profitLoss"]
    if cum_pnl_2 > peak:
        peak = cum_pnl_2
    dd = peak - cum_pnl_2
    if dd > max_dd:
        max_dd = dd

print(f"\n  Max closed-trade drawdown: ${max_dd:,.2f}")
print(f"  Final closed P/L: ${sum(t['profitLoss'] for t in trades):,.2f}")
