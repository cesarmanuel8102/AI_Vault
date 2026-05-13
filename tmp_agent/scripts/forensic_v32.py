"""
Forensic Analysis — MTF Trend Pullback V3.2
Analyzes 1071 closed trades from backtest b0564d9f27b245921e2f1067b70fe11d
Period: 2023-01-01 to 2024-12-28
"""
import json
import numpy as np
from datetime import datetime, timedelta
from collections import defaultdict

with open("C:/AI_VAULT/tmp_agent/strategies/mtf_trend/bt_v32_trades.json", "r") as f:
    trades = json.load(f)

print(f"Total closed trades: {len(trades)}")
print()

# ===================== 1. BASIC METRICS =====================
pnls = [t["profitLoss"] for t in trades]
fees = [t["totalFees"] for t in trades]
maes = [t["mae"] for t in trades]
mfes = [t["mfe"] for t in trades]
wins = [t for t in trades if t["isWin"]]
losses = [t for t in trades if not t["isWin"]]

total_pnl = sum(pnls)
total_fees = sum(fees)
gross_profit = sum(t["profitLoss"] for t in wins)
gross_loss = sum(t["profitLoss"] for t in losses)

print("=" * 70)
print("1. BASIC METRICS")
print("=" * 70)
print(f"  Total Trades:     {len(trades)}")
print(f"  Winners:          {len(wins)} ({len(wins)/len(trades)*100:.1f}%)")
print(f"  Losers:           {len(losses)} ({len(losses)/len(trades)*100:.1f}%)")
print(f"  Total P/L:        ${total_pnl:,.2f}")
print(f"  Total Fees:       ${total_fees:,.2f}")
print(f"  Gross Profit:     ${gross_profit:,.2f}")
print(f"  Gross Loss:       ${gross_loss:,.2f}")
print(f"  Profit Factor:    {abs(gross_profit/gross_loss):.3f}" if gross_loss != 0 else "  PF: N/A")
print(f"  Avg Win:          ${np.mean([t['profitLoss'] for t in wins]):,.2f}")
print(f"  Avg Loss:         ${np.mean([t['profitLoss'] for t in losses]):,.2f}")
print(f"  Avg P/L Ratio:    {abs(np.mean([t['profitLoss'] for t in wins])/np.mean([t['profitLoss'] for t in losses])):.3f}")
print(f"  Largest Win:      ${max(pnls):,.2f}")
print(f"  Largest Loss:     ${min(pnls):,.2f}")
print(f"  Max Consec Wins:  searching...")
print(f"  Max Consec Losses: searching...")

# Consecutive wins/losses
max_cw = 0; max_cl = 0; cw = 0; cl = 0
for t in trades:
    if t["isWin"]:
        cw += 1; cl = 0
        max_cw = max(max_cw, cw)
    else:
        cl += 1; cw = 0
        max_cl = max(max_cl, cl)
print(f"  Max Consec Wins:  {max_cw}")
print(f"  Max Consec Losses: {max_cl}")

# ===================== 2. DIRECTION ANALYSIS =====================
print()
print("=" * 70)
print("2. DIRECTION ANALYSIS (Long vs Short)")
print("=" * 70)

# direction: 0 = Long (based on QC convention where direction in closedTrades is 0=Long, 1=Short)
longs = [t for t in trades if t["direction"] == 0]
shorts = [t for t in trades if t["direction"] == 1]

for label, subset in [("LONG", longs), ("SHORT", shorts)]:
    if not subset:
        print(f"  {label}: No trades")
        continue
    w = [t for t in subset if t["isWin"]]
    l = [t for t in subset if not t["isWin"]]
    tp = sum(t["profitLoss"] for t in subset)
    gp = sum(t["profitLoss"] for t in w)
    gl = sum(t["profitLoss"] for t in l)
    pf = abs(gp/gl) if gl != 0 else float('inf')
    print(f"  {label}: {len(subset)} trades, WR {len(w)/len(subset)*100:.1f}%, "
          f"P/L ${tp:,.2f}, PF {pf:.3f}, "
          f"AvgW ${np.mean([t['profitLoss'] for t in w]):,.2f}" if w else "",
          f"AvgL ${np.mean([t['profitLoss'] for t in l]):,.2f}" if l else "")

# ===================== 3. HOLDING TIME ANALYSIS =====================
print()
print("=" * 70)
print("3. HOLDING TIME ANALYSIS")
print("=" * 70)

def parse_duration(d):
    """Parse duration string like '03:09:20.1120723' or '1.02:30:00' to seconds"""
    if not d:
        return 0
    parts = d.split(".")
    if len(parts) >= 2 and ":" in parts[0] and len(parts[0].split(":")) == 1:
        # Format: days.HH:MM:SS
        days = int(parts[0])
        time_part = parts[1].split(":")
        hours = int(time_part[0])
        minutes = int(time_part[1]) if len(time_part) > 1 else 0
        secs = int(time_part[2].split(".")[0]) if len(time_part) > 2 else 0
        return days * 86400 + hours * 3600 + minutes * 60 + secs
    else:
        # Format: HH:MM:SS or HH:MM:SS.ffffff
        time_str = d.split(".")[0] if "." in d and ":" in d.split(".")[1] else d.split(".")[0]
        parts = time_str.split(":")
        hours = int(parts[0])
        minutes = int(parts[1]) if len(parts) > 1 else 0
        secs = int(parts[2]) if len(parts) > 2 else 0
        return hours * 3600 + minutes * 60 + secs

buckets = [
    ("0-1 min", 0, 60),
    ("1-5 min", 60, 300),
    ("5-30 min", 300, 1800),
    ("30-60 min", 1800, 3600),
    ("1-2 hr", 3600, 7200),
    ("2-3 hr", 7200, 10800),
    ("3+ hr", 10800, 999999),
]

for label, lo, hi in buckets:
    subset = [t for t in trades if lo <= parse_duration(t["duration"]) < hi]
    if not subset:
        print(f"  {label:12s}: 0 trades")
        continue
    w = [t for t in subset if t["isWin"]]
    tp = sum(t["profitLoss"] for t in subset)
    print(f"  {label:12s}: {len(subset):4d} trades, WR {len(w)/len(subset)*100:5.1f}%, P/L ${tp:>10,.2f}")

# ===================== 4. MAE ANALYSIS (forensic) =====================
print()
print("=" * 70)
print("4. MAE ANALYSIS (Maximum Adverse Excursion)")
print("=" * 70)

# MAE as % of entry price
mae_pcts = []
for t in trades:
    entry = t["entryPrice"]
    if entry > 0:
        mae_pct = abs(t["mae"]) / (entry * t["quantity"]) * 100 if t["quantity"] != 0 else 0
        mae_pcts.append((mae_pct, t))

mae_buckets = [
    ("MAE 0-0.5%", 0, 0.5),
    ("MAE 0.5-1%", 0.5, 1.0),
    ("MAE 1-1.5%", 1.0, 1.5),
    ("MAE 1.5-2%", 1.5, 2.0),
    ("MAE 2%+", 2.0, 100),
]

for label, lo, hi in mae_buckets:
    subset = [(m, t) for m, t in mae_pcts if lo <= m < hi]
    if not subset:
        print(f"  {label:14s}: 0 trades")
        continue
    tds = [t for _, t in subset]
    w = [t for t in tds if t["isWin"]]
    tp = sum(t["profitLoss"] for t in tds)
    print(f"  {label:14s}: {len(tds):4d} trades, WR {len(w)/len(tds)*100:5.1f}%, P/L ${tp:>10,.2f}")

# ===================== 5. MFE ANALYSIS (profitable first then lost?) =====================
print()
print("=" * 70)
print("5. MFE ANALYSIS — Losers that were profitable first")
print("=" * 70)

losers_with_mfe = [t for t in losses if t["mfe"] > 0]
print(f"  Total losers: {len(losses)}")
print(f"  Losers with positive MFE: {len(losers_with_mfe)} ({len(losers_with_mfe)/len(losses)*100:.1f}%)")
if losers_with_mfe:
    avg_mfe = np.mean([t["mfe"] for t in losers_with_mfe])
    avg_loss = np.mean([t["profitLoss"] for t in losers_with_mfe])
    total_missed = sum(t["mfe"] for t in losers_with_mfe)
    print(f"  Avg MFE before losing: ${avg_mfe:,.2f}")
    print(f"  Avg final loss: ${avg_loss:,.2f}")
    print(f"  Total missed profits: ${total_missed:,.2f}")

# ===================== 6. MONTHLY ANALYSIS =====================
print()
print("=" * 70)
print("6. MONTHLY P/L ANALYSIS")
print("=" * 70)

monthly = defaultdict(lambda: {"pnl": 0, "trades": 0, "wins": 0})
for t in trades:
    entry_time = t["entryTime"][:7]  # YYYY-MM
    monthly[entry_time]["pnl"] += t["profitLoss"]
    monthly[entry_time]["trades"] += 1
    if t["isWin"]:
        monthly[entry_time]["wins"] += 1

for month in sorted(monthly.keys()):
    d = monthly[month]
    wr = d["wins"] / d["trades"] * 100 if d["trades"] > 0 else 0
    bar = "+" * int(abs(d["pnl"]) / 500) if d["pnl"] > 0 else "-" * int(abs(d["pnl"]) / 500)
    print(f"  {month}: {d['trades']:3d} trades, WR {wr:5.1f}%, P/L ${d['pnl']:>10,.2f} {bar}")

# Monthly trades average
total_months = len(monthly)
avg_trades_month = len(trades) / total_months if total_months > 0 else 0
print(f"\n  Avg trades/month: {avg_trades_month:.1f}")
print(f"  Total months: {total_months}")

# ===================== 7. TICKER ANALYSIS =====================
print()
print("=" * 70)
print("7. TOP/BOTTOM TICKERS")
print("=" * 70)

by_ticker = defaultdict(lambda: {"pnl": 0, "trades": 0, "wins": 0})
for t in trades:
    syms = t.get("symbols", [])
    ticker = syms[0]["value"] if syms else "UNKNOWN"
    by_ticker[ticker]["pnl"] += t["profitLoss"]
    by_ticker[ticker]["trades"] += 1
    if t["isWin"]:
        by_ticker[ticker]["wins"] += 1

sorted_tickers = sorted(by_ticker.items(), key=lambda x: x[1]["pnl"], reverse=True)

print("  TOP 10 Profitable:")
for ticker, d in sorted_tickers[:10]:
    wr = d["wins"] / d["trades"] * 100 if d["trades"] > 0 else 0
    print(f"    {ticker:8s}: {d['trades']:3d} trades, WR {wr:5.1f}%, P/L ${d['pnl']:>10,.2f}")

print("\n  BOTTOM 10 Losing:")
for ticker, d in sorted_tickers[-10:]:
    wr = d["wins"] / d["trades"] * 100 if d["trades"] > 0 else 0
    print(f"    {ticker:8s}: {d['trades']:3d} trades, WR {wr:5.1f}%, P/L ${d['pnl']:>10,.2f}")

print(f"\n  Unique tickers traded: {len(by_ticker)}")
profitable_tickers = [t for t, d in by_ticker.items() if d["pnl"] > 0]
losing_tickers = [t for t, d in by_ticker.items() if d["pnl"] <= 0]
print(f"  Profitable tickers: {len(profitable_tickers)}")
print(f"  Losing tickers: {len(losing_tickers)}")

# ===================== 8. EXIT REASON ANALYSIS =====================
print()
print("=" * 70)
print("8. TRADE SIZE ANALYSIS")
print("=" * 70)

quantities = [t["quantity"] for t in trades]
entry_values = [t["entryPrice"] * t["quantity"] for t in trades]
print(f"  Avg position size: {np.mean(quantities):.0f} shares")
print(f"  Avg entry value: ${np.mean(entry_values):,.2f}")
print(f"  Max entry value: ${max(entry_values):,.2f}")
print(f"  Min entry value: ${min(entry_values):,.2f}")

# Distribution of entry values
for label, lo, hi in [("<$5K", 0, 5000), ("$5K-$10K", 5000, 10000), ("$10K-$20K", 10000, 20000), ("$20K-$50K", 20000, 50000), ("$50K+", 50000, 999999)]:
    subset = [t for t in trades if lo <= t["entryPrice"] * t["quantity"] < hi]
    if subset:
        w = [t for t in subset if t["isWin"]]
        tp = sum(t["profitLoss"] for t in subset)
        print(f"  {label:12s}: {len(subset):4d} trades, WR {len(w)/len(subset)*100:5.1f}%, P/L ${tp:>10,.2f}")

# ===================== 9. YEAR ANALYSIS =====================
print()
print("=" * 70)
print("9. YEAR-OVER-YEAR ANALYSIS")
print("=" * 70)

by_year = defaultdict(lambda: {"pnl": 0, "trades": 0, "wins": 0})
for t in trades:
    year = t["entryTime"][:4]
    by_year[year]["pnl"] += t["profitLoss"]
    by_year[year]["trades"] += 1
    if t["isWin"]:
        by_year[year]["wins"] += 1

for year in sorted(by_year.keys()):
    d = by_year[year]
    wr = d["wins"] / d["trades"] * 100 if d["trades"] > 0 else 0
    print(f"  {year}: {d['trades']:4d} trades, WR {wr:5.1f}%, P/L ${d['pnl']:>10,.2f}")

# ===================== 10. DAY OF WEEK =====================
print()
print("=" * 70)
print("10. DAY OF WEEK ANALYSIS")
print("=" * 70)

day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
by_dow = defaultdict(lambda: {"pnl": 0, "trades": 0, "wins": 0})
for t in trades:
    dt = datetime.strptime(t["entryTime"][:10], "%Y-%m-%d")
    dow = dt.weekday()
    by_dow[dow]["pnl"] += t["profitLoss"]
    by_dow[dow]["trades"] += 1
    if t["isWin"]:
        by_dow[dow]["wins"] += 1

for dow in range(5):
    d = by_dow[dow]
    if d["trades"] == 0:
        continue
    wr = d["wins"] / d["trades"] * 100
    print(f"  {day_names[dow]:12s}: {d['trades']:4d} trades, WR {wr:5.1f}%, P/L ${d['pnl']:>10,.2f}")

# ===================== 11. ENTRY PRICE RANGE =====================
print()
print("=" * 70)
print("11. ENTRY PRICE RANGE ANALYSIS")
print("=" * 70)

for label, lo, hi in [("$10-$25", 10, 25), ("$25-$50", 25, 50), ("$50-$100", 50, 100), ("$100-$200", 100, 200), ("$200-$500", 200, 500), ("$500+", 500, 99999)]:
    subset = [t for t in trades if lo <= t["entryPrice"] < hi]
    if not subset:
        continue
    w = [t for t in subset if t["isWin"]]
    tp = sum(t["profitLoss"] for t in subset)
    print(f"  {label:12s}: {len(subset):4d} trades, WR {len(w)/len(subset)*100:5.1f}%, P/L ${tp:>10,.2f}")

# ===================== 12. WORST TRADES (for debugging) =====================
print()
print("=" * 70)
print("12. WORST 15 TRADES")
print("=" * 70)

worst = sorted(trades, key=lambda t: t["profitLoss"])[:15]
for t in worst:
    syms = t.get("symbols", [])
    ticker = syms[0]["value"] if syms else "?"
    dirn = "LONG" if t["direction"] == 0 else "SHORT"
    print(f"  {ticker:8s} {dirn:5s} Entry:{t['entryTime'][:16]} "
          f"Price:${t['entryPrice']:.2f} Qty:{t['quantity']} "
          f"P/L:${t['profitLoss']:,.2f} MAE:${t['mae']:,.2f} MFE:${t['mfe']:,.2f} "
          f"Dur:{t['duration']}")

# ===================== 13. BEST TRADES =====================
print()
print("=" * 70)
print("13. BEST 15 TRADES")
print("=" * 70)

best = sorted(trades, key=lambda t: t["profitLoss"], reverse=True)[:15]
for t in best:
    syms = t.get("symbols", [])
    ticker = syms[0]["value"] if syms else "?"
    dirn = "LONG" if t["direction"] == 0 else "SHORT"
    print(f"  {ticker:8s} {dirn:5s} Entry:{t['entryTime'][:16]} "
          f"Price:${t['entryPrice']:.2f} Qty:{t['quantity']} "
          f"P/L:${t['profitLoss']:,.2f} MAE:${t['mae']:,.2f} MFE:${t['mfe']:,.2f} "
          f"Dur:{t['duration']}")

# ===================== 14. 1-MIN EXITS (insufficient buying power?) =====================
print()
print("=" * 70)
print("14. ULTRA-SHORT TRADES (<=1 min) — Possible Insufficient Buying Power")
print("=" * 70)

ultra_short = [t for t in trades if parse_duration(t["duration"]) <= 60]
print(f"  Trades <=1 min: {len(ultra_short)}")
if ultra_short:
    w = [t for t in ultra_short if t["isWin"]]
    tp = sum(t["profitLoss"] for t in ultra_short)
    print(f"  WR: {len(w)/len(ultra_short)*100:.1f}%, Total P/L: ${tp:,.2f}")
    print(f"  Avg P/L: ${np.mean([t['profitLoss'] for t in ultra_short]):,.2f}")
    
    # These are likely fills that got immediately reversed due to insufficient margin
    for t in sorted(ultra_short, key=lambda t: t["profitLoss"])[:10]:
        syms = t.get("symbols", [])
        ticker = syms[0]["value"] if syms else "?"
        dirn = "LONG" if t["direction"] == 0 else "SHORT"
        print(f"    {ticker:8s} {dirn:5s} {t['entryTime'][:16]} "
              f"Qty:{t['quantity']} P/L:${t['profitLoss']:,.2f} "
              f"Entry:${t['entryPrice']:.2f} Exit:${t['exitPrice']:.2f}")

# ===================== SUMMARY VERDICTS =====================
print()
print("=" * 70)
print("SUMMARY & MODE A GATE CHECK")
print("=" * 70)
print(f"  CAGR:           24.4%  {'PASS (>12%)' if 24.4 > 12 else 'FAIL'}")
print(f"  Sharpe:         0.593  {'PASS (>1.0)' if 0.593 > 1.0 else 'FAIL (<1.0)'}")
print(f"  MaxDD:          25.9%  (high)")
print(f"  WR:             39.6%")
print(f"  Trades/month:   {avg_trades_month:.1f}  {'PASS (>6)' if avg_trades_month > 6 else 'FAIL (<6)'}")
print(f"  Trade PF:       0.864  NEGATIVE (trades lose money)")
print(f"  Portfolio return: +54.4% in 2 years")
print(f"")
print(f"  CONTRADICTION: Portfolio +54% but trades -$20K")
print(f"  This means unrealized gains at end are inflating the equity curve!")
print(f"  The strategy is HOLDING positions at backtest end that are up big.")
