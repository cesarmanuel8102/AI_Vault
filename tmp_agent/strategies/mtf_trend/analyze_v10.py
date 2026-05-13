"""Forensic analysis for MTF Trend Pullback V1.0"""
import json
from collections import defaultdict
from datetime import datetime

with open("C:/AI_VAULT/tmp_agent/strategies/mtf_trend/backtest_results.json") as f:
    bt = json.load(f)

trades = bt["totalPerformance"]["closedTrades"]
print(f"Total closed trades: {len(trades)}")

# Parse
parsed = []
for t in trades:
    sym = t["symbols"][0]["value"]
    direction = "LONG" if t["direction"] == 0 else "SHORT"
    entry_time = datetime.fromisoformat(t["entryTime"].replace("Z", "+00:00"))
    exit_time = datetime.fromisoformat(t["exitTime"].replace("Z", "+00:00"))
    duration_parts = t["duration"].split(".")
    if len(duration_parts) == 3:  # d.hh:mm:ss
        days = int(duration_parts[0])
        hm = duration_parts[1].split(":")
        hours = days * 24 + int(hm[0])
    elif len(duration_parts) == 2:
        days = int(duration_parts[0])
        hm = duration_parts[1].split(":")
        hours = days * 24 + int(hm[0])
    else:
        hm = duration_parts[0].split(":")
        hours = int(hm[0])
        
    pnl = t["profitLoss"]
    fees = t["totalFees"]
    mae = t["mae"]
    mfe = t["mfe"]
    entry_price = t["entryPrice"]
    exit_price = t["exitPrice"]
    qty = t["quantity"]
    is_win = t["isWin"]
    
    # Percentage moves
    if direction == "LONG":
        pnl_pct = (exit_price - entry_price) / entry_price * 100
        mae_pct = mae / (entry_price * qty) * 100 if qty > 0 else 0
        mfe_pct = mfe / (entry_price * qty) * 100 if qty > 0 else 0
    else:
        pnl_pct = (entry_price - exit_price) / entry_price * 100
        mae_pct = mae / (entry_price * qty) * 100 if qty > 0 else 0
        mfe_pct = mfe / (entry_price * qty) * 100 if qty > 0 else 0
    
    parsed.append({
        "sym": sym, "dir": direction, "entry_time": entry_time, "exit_time": exit_time,
        "hours": hours, "pnl": pnl, "fees": fees, "mae": mae, "mfe": mfe,
        "entry_price": entry_price, "exit_price": exit_price, "qty": qty,
        "is_win": is_win, "pnl_pct": pnl_pct, "mae_pct": mae_pct, "mfe_pct": mfe_pct,
        "year": entry_time.year
    })

# ===== OVERALL STATS =====
wins = [t for t in parsed if t["is_win"]]
losses = [t for t in parsed if not t["is_win"]]
total_pnl = sum(t["pnl"] for t in parsed)
total_fees = sum(t["fees"] for t in parsed)

print(f"\n{'='*70}")
print(f"OVERALL: {len(parsed)} trades, WR {len(wins)/len(parsed)*100:.1f}%")
print(f"Total P&L: ${total_pnl:,.0f}, Total Fees: ${total_fees:,.0f}")
print(f"Avg Win: ${sum(t['pnl'] for t in wins)/len(wins):,.0f}, Avg Loss: ${sum(t['pnl'] for t in losses)/len(losses):,.0f}")
print(f"Avg Win%: {sum(t['pnl_pct'] for t in wins)/len(wins):.2f}%, Avg Loss%: {sum(t['pnl_pct'] for t in losses)/len(losses):.2f}%")

# ===== BY TICKER =====
print(f"\n{'='*70}")
print(f"BY TICKER:")
print(f"{'Ticker':<8} {'Trades':>7} {'WR':>6} {'P&L':>10} {'AvgWin':>8} {'AvgLoss':>8} {'PF':>6}")
by_ticker = defaultdict(list)
for t in parsed:
    by_ticker[t["sym"]].append(t)

for sym in sorted(by_ticker.keys()):
    tt = by_ticker[sym]
    w = [t for t in tt if t["is_win"]]
    l = [t for t in tt if not t["is_win"]]
    pnl = sum(t["pnl"] for t in tt)
    wr = len(w)/len(tt)*100 if tt else 0
    avg_w = sum(t["pnl"] for t in w)/len(w) if w else 0
    avg_l = sum(t["pnl"] for t in l)/len(l) if l else 0
    gross_w = sum(t["pnl"] for t in w)
    gross_l = abs(sum(t["pnl"] for t in l))
    pf = gross_w / gross_l if gross_l > 0 else 999
    print(f"{sym:<8} {len(tt):>7} {wr:>5.1f}% ${pnl:>9,.0f} ${avg_w:>7,.0f} ${avg_l:>7,.0f} {pf:>5.2f}")

# ===== BY DIRECTION =====
print(f"\n{'='*70}")
print(f"BY DIRECTION:")
for d in ["LONG", "SHORT"]:
    tt = [t for t in parsed if t["dir"] == d]
    if not tt:
        print(f"  {d}: 0 trades")
        continue
    w = [t for t in tt if t["is_win"]]
    l = [t for t in tt if not t["is_win"]]
    pnl = sum(t["pnl"] for t in tt)
    wr = len(w)/len(tt)*100
    print(f"  {d}: {len(tt)} trades, WR {wr:.1f}%, P&L ${pnl:,.0f}")

# ===== BY YEAR =====
print(f"\n{'='*70}")
print(f"BY YEAR:")
print(f"{'Year':<6} {'Trades':>7} {'WR':>6} {'P&L':>10}")
for year in sorted(set(t["year"] for t in parsed)):
    tt = [t for t in parsed if t["year"] == year]
    w = [t for t in tt if t["is_win"]]
    pnl = sum(t["pnl"] for t in tt)
    wr = len(w)/len(tt)*100 if tt else 0
    print(f"{year:<6} {len(tt):>7} {wr:>5.1f}% ${pnl:>9,.0f}")

# ===== BY HOLDING TIME =====
print(f"\n{'='*70}")
print(f"BY HOLDING TIME:")
time_buckets = [
    ("0-4 hrs", 0, 4),
    ("4-8 hrs", 4, 8),
    ("8-24 hrs", 8, 24),
    ("1-2 days", 24, 48),
    ("2-3 days", 48, 72),
    ("3-5 days", 72, 120),
    ("5+ days", 120, 9999)
]
print(f"{'Bucket':<12} {'Trades':>7} {'WR':>6} {'P&L':>10} {'AvgPnL':>8}")
for name, lo, hi in time_buckets:
    tt = [t for t in parsed if lo <= t["hours"] < hi]
    if not tt:
        continue
    w = [t for t in tt if t["is_win"]]
    pnl = sum(t["pnl"] for t in tt)
    wr = len(w)/len(tt)*100 if tt else 0
    avg = pnl/len(tt)
    print(f"{name:<12} {len(tt):>7} {wr:>5.1f}% ${pnl:>9,.0f} ${avg:>7,.0f}")

# ===== EXIT TYPE ANALYSIS =====
# Can't get exit tags from closedTrades, but can infer from patterns
# Losers that were profitable first (MFE > 0 but is_win == False)
losers_with_mfe = [t for t in losses if t["mfe"] > 0]
print(f"\n{'='*70}")
print(f"LOSERS THAT WERE PROFITABLE FIRST: {len(losers_with_mfe)}/{len(losses)} ({len(losers_with_mfe)/len(losses)*100:.1f}%)")
if losers_with_mfe:
    avg_mfe = sum(t["mfe"] for t in losers_with_mfe) / len(losers_with_mfe)
    avg_loss = sum(t["pnl"] for t in losers_with_mfe) / len(losers_with_mfe)
    print(f"  Avg MFE before losing: ${avg_mfe:,.0f}")
    print(f"  Avg final loss: ${avg_loss:,.0f}")

# ===== MAE ANALYSIS =====
print(f"\n{'='*70}")
print(f"MAE ANALYSIS (Max Adverse Excursion):")
mae_buckets = [
    ("$0-100", 0, 100),
    ("$100-300", 100, 300),
    ("$300-500", 300, 500),
    ("$500-1000", 500, 1000),
    ("$1000-2000", 1000, 2000),
    ("$2000+", 2000, 999999)
]
print(f"{'MAE Bucket':<12} {'Trades':>7} {'WR':>6} {'P&L':>10}")
for name, lo, hi in mae_buckets:
    tt = [t for t in parsed if lo <= abs(t["mae"]) < hi]
    if not tt:
        continue
    w = [t for t in tt if t["is_win"]]
    pnl = sum(t["pnl"] for t in tt)
    wr = len(w)/len(tt)*100 if tt else 0
    print(f"{name:<12} {len(tt):>7} {wr:>5.1f}% ${pnl:>9,.0f}")

# ===== MFE ANALYSIS (how much profit left on table) =====
print(f"\n{'='*70}")
print(f"MFE ANALYSIS (profit left on table):")
for t in wins:
    t["left_on_table"] = t["mfe"] - t["pnl"]
avg_left = sum(t["left_on_table"] for t in wins) / len(wins) if wins else 0
avg_captured = sum(t["pnl"] for t in wins) / len(wins) if wins else 0
avg_mfe_wins = sum(t["mfe"] for t in wins) / len(wins) if wins else 0
print(f"  Avg MFE (wins): ${avg_mfe_wins:,.0f}")
print(f"  Avg captured: ${avg_captured:,.0f}")
print(f"  Avg left on table: ${avg_left:,.0f}")
print(f"  Capture ratio: {avg_captured/avg_mfe_wins*100:.1f}%" if avg_mfe_wins > 0 else "  N/A")

# ===== PARTIAL TP IMPACT =====
# Trades with partial exit (look for trades where qty halved)
print(f"\n{'='*70}")
print(f"TRADE SIZE DISTRIBUTION:")
sizes = [t["qty"] for t in parsed]
print(f"  Min qty: {min(sizes)}, Max qty: {max(sizes)}, Median: {sorted(sizes)[len(sizes)//2]}")
print(f"  Avg position size: ${sum(t['entry_price']*t['qty'] for t in parsed)/len(parsed):,.0f}")

# ===== MONTHLY TRADE COUNT =====
print(f"\n{'='*70}")
months = set()
for t in parsed:
    months.add((t["entry_time"].year, t["entry_time"].month))
trades_per_month = len(parsed) / len(months) if months else 0
print(f"TRADES PER MONTH: {trades_per_month:.1f} ({len(months)} months)")

# ===== KEY METRICS SUMMARY =====
print(f"\n{'='*70}")
print(f"KEY METRICS SUMMARY:")
gross_wins = sum(t["pnl"] for t in wins)
gross_losses = abs(sum(t["pnl"] for t in losses))
pf = gross_wins / gross_losses if gross_losses > 0 else 999
print(f"  Win Rate: {len(wins)/len(parsed)*100:.1f}%")
print(f"  Profit Factor: {pf:.2f}")
print(f"  Expectancy: ${sum(t['pnl'] for t in parsed)/len(parsed):,.2f}")
print(f"  Gross Wins: ${gross_wins:,.0f}")
print(f"  Gross Losses: ${-sum(t['pnl'] for t in losses):,.0f}")
print(f"  Total Fees: ${total_fees:,.0f}")
