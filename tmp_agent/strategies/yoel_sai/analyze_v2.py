"""Forensic analysis V2 - using closedTrades from QC API."""
import json
from collections import defaultdict
from datetime import datetime

# Load trades
with open("C:/AI_VAULT/tmp_agent/strategies/yoel_sai/closed_trades.json") as f:
    trades = json.load(f)

print(f"Total closed trades: {len(trades)}")

# Parse symbol info
for t in trades:
    sym_val = t["symbols"][0]["value"]  # e.g. "SPY   210111P00380000"
    # Extract option type (C/P) and strike from symbol
    # Format: SPY   YYMMDD[C/P]SSSSSSSS
    parts = sym_val.strip()
    # Find C or P after date
    t["opt_type"] = "PUT" if "P0" in parts or "P00" in parts else "CALL"
    t["entry_dt"] = t["entryTime"][:10]
    t["exit_dt"] = t["exitTime"][:10]
    t["entry_hour"] = int(t["entryTime"][11:13])
    t["exit_hour"] = int(t["exitTime"][11:13])
    t["pnl_pct"] = (t["exitPrice"] - t["entryPrice"]) / t["entryPrice"] * 100 if t["entryPrice"] > 0 else 0
    
    # Parse duration
    dur = t.get("duration", "00:00:00")
    parts_d = dur.split(":")
    t["hold_minutes"] = int(parts_d[0]) * 60 + int(parts_d[1])
    
    # MAE/MFE as % of entry cost
    cost = t["entryPrice"] * t["quantity"] * 100
    t["mae_pct"] = t["mae"] / cost * 100 if cost > 0 else 0
    t["mfe_pct"] = t["mfe"] / cost * 100 if cost > 0 else 0
    
    # Infer exit type from exit time and P&L
    exit_h = t["exit_hour"]
    if t["pnl_pct"] >= 30:  # ~35% TP
        t["exit_type"] = "TP"
    elif exit_h >= 19:  # 3PM+ ET = 19:00+ UTC? or check 15:00 ET
        t["exit_type"] = "EOD"
    elif t["pnl_pct"] <= -45:  # ~50% SL
        t["exit_type"] = "SL"
    else:
        t["exit_type"] = "EOD"  # default to EOD for anything else
    
    # Determine same-day vs overnight
    t["same_day"] = t["entry_dt"] == t["exit_dt"]

wins = [t for t in trades if t["isWin"]]
losses = [t for t in trades if not t["isWin"]]

print(f"Wins: {len(wins)} ({len(wins)/len(trades)*100:.1f}%)")
print(f"Losses: {len(losses)} ({len(losses)/len(trades)*100:.1f}%)")
print(f"Total P&L: ${sum(t['profitLoss'] for t in trades):,.0f}")
print(f"Total Fees: ${sum(t['totalFees'] for t in trades):,.0f}")

# ============================================================
print("\n" + "=" * 70)
print("1. WIN vs LOSS DEEP COMPARISON")
print("=" * 70)

for label, group in [("WINS", wins), ("LOSSES", losses)]:
    if not group:
        continue
    avg_entry = sum(t["entryPrice"] for t in group) / len(group)
    avg_pnl = sum(t["profitLoss"] for t in group) / len(group)
    avg_pnl_pct = sum(t["pnl_pct"] for t in group) / len(group)
    avg_hold = sum(t["hold_minutes"] for t in group) / len(group)
    avg_mae = sum(t["mae_pct"] for t in group) / len(group)
    avg_mfe = sum(t["mfe_pct"] for t in group) / len(group)
    avg_qty = sum(t["quantity"] for t in group) / len(group)
    puts = len([t for t in group if t["opt_type"] == "PUT"])
    calls = len([t for t in group if t["opt_type"] == "CALL"])
    same_day = len([t for t in group if t["same_day"]])
    overnight = len([t for t in group if not t["same_day"]])
    
    print(f"\n  {label} ({len(group)} trades):")
    print(f"    Avg Entry Premium: ${avg_entry:.2f}")
    print(f"    Avg P&L: ${avg_pnl:+,.0f} ({avg_pnl_pct:+.1f}%)")
    print(f"    Avg Hold Time: {avg_hold:.0f} min")
    print(f"    Avg MAE (worst drawdown): {avg_mae:.1f}%")
    print(f"    Avg MFE (best unrealized): {avg_mfe:.1f}%")
    print(f"    Avg Qty: {avg_qty:.0f} contracts")
    print(f"    Puts: {puts} | Calls: {calls}")
    print(f"    Same-day exit: {same_day} | Overnight: {overnight}")

# ============================================================
print("\n" + "=" * 70)
print("2. PUT vs CALL PERFORMANCE")
print("=" * 70)

for opt_type in ["PUT", "CALL"]:
    group = [t for t in trades if t["opt_type"] == opt_type]
    if not group:
        continue
    w = len([t for t in group if t["isWin"]])
    total_pnl = sum(t["profitLoss"] for t in group)
    avg_pnl_pct = sum(t["pnl_pct"] for t in group) / len(group)
    print(f"\n  {opt_type}: {len(group)} trades | WR: {w/len(group)*100:.1f}% | "
          f"Total P&L: ${total_pnl:+,.0f} | Avg: {avg_pnl_pct:+.1f}%")

# ============================================================
print("\n" + "=" * 70)
print("3. SAME-DAY vs OVERNIGHT EXIT")
print("=" * 70)

for label, condition in [("Same-Day", True), ("Overnight", False)]:
    group = [t for t in trades if t["same_day"] == condition]
    if not group:
        print(f"  {label}: 0 trades")
        continue
    w = len([t for t in group if t["isWin"]])
    total_pnl = sum(t["profitLoss"] for t in group)
    avg_pnl = sum(t["pnl_pct"] for t in group) / len(group)
    print(f"  {label}: {len(group)} trades | WR: {w/len(group)*100:.1f}% | "
          f"Total P&L: ${total_pnl:+,.0f} | Avg: {avg_pnl:+.1f}%")

# ============================================================
print("\n" + "=" * 70)
print("4. ENTRY PREMIUM BUCKETS")
print("=" * 70)

buckets = [
    ("$0-1", 0, 1), ("$1-2", 1, 2), ("$2-3", 2, 3), 
    ("$3-5", 3, 5), ("$5-10", 5, 10), ("$10+", 10, 999)
]
for label, lo, hi in buckets:
    group = [t for t in trades if lo <= t["entryPrice"] < hi]
    if not group:
        continue
    w = len([t for t in group if t["isWin"]])
    total_pnl = sum(t["profitLoss"] for t in group)
    avg_pnl = sum(t["pnl_pct"] for t in group) / len(group)
    print(f"  {label:8s}: {len(group):3d} trades | WR: {w/len(group)*100:.1f}% | "
          f"Total P&L: ${total_pnl:+10,.0f} | Avg: {avg_pnl:+.1f}%")

# ============================================================
print("\n" + "=" * 70)
print("5. MFE ANALYSIS - Are we leaving money on the table?")
print("=" * 70)

# For losses: what was the MFE (max profit we COULD have taken)?
loss_mfe = [t for t in losses if t["mfe"] > 0]
print(f"\n  Losing trades that were IN PROFIT at some point: {len(loss_mfe)} / {len(losses)} ({len(loss_mfe)/len(losses)*100:.1f}%)")
if loss_mfe:
    avg_mfe_loss = sum(t["mfe_pct"] for t in loss_mfe) / len(loss_mfe)
    avg_final_pnl = sum(t["pnl_pct"] for t in loss_mfe) / len(loss_mfe)
    print(f"  These trades had avg MFE of +{avg_mfe_loss:.1f}% before turning into losses of {avg_final_pnl:.1f}%")
    total_missed = sum(t["mfe"] for t in loss_mfe)
    print(f"  Total profit LEFT ON TABLE: ${total_missed:,.0f}")

# For wins: how much MORE could we have made?
print(f"\n  Winning trades MFE vs actual exit:")
if wins:
    for t in wins:
        t["captured_pct"] = t["profitLoss"] / t["mfe"] * 100 if t["mfe"] > 0 else 0
    avg_captured = sum(t["captured_pct"] for t in wins) / len(wins)
    print(f"  Avg % of MFE captured: {avg_captured:.1f}%")

# ============================================================
print("\n" + "=" * 70)
print("6. MAE ANALYSIS - How deep do losers go before exit?")
print("=" * 70)

mae_buckets = [
    ("0-10%", 0, 10), ("10-20%", 10, 20), ("20-30%", 20, 30),
    ("30-50%", 30, 50), ("50-75%", 50, 75), ("75-100%", 75, 100)
]

for label, lo, hi in mae_buckets:
    group = [t for t in trades if lo <= abs(t["mae_pct"]) < hi]
    if not group:
        continue
    w = len([t for t in group if t["isWin"]])
    total_pnl = sum(t["profitLoss"] for t in group)
    print(f"  MAE {label:8s}: {len(group):3d} trades | WR: {w/len(group)*100:.1f}% | P&L: ${total_pnl:+10,.0f}")

# ============================================================
print("\n" + "=" * 70)
print("7. HOLDING TIME ANALYSIS")
print("=" * 70)

time_buckets = [
    ("0-15 min", 0, 15), ("15-30 min", 15, 30), ("30-60 min", 30, 60),
    ("1-2 hrs", 60, 120), ("2-4 hrs", 120, 240), ("4+ hrs", 240, 9999)
]

for label, lo, hi in time_buckets:
    group = [t for t in trades if lo <= t["hold_minutes"] < hi]
    if not group:
        continue
    w = len([t for t in group if t["isWin"]])
    total_pnl = sum(t["profitLoss"] for t in group)
    avg_pnl = sum(t["pnl_pct"] for t in group) / len(group)
    print(f"  {label:12s}: {len(group):3d} trades | WR: {w/len(group)*100:.1f}% | "
          f"P&L: ${total_pnl:+10,.0f} | Avg: {avg_pnl:+.1f}%")

# ============================================================
print("\n" + "=" * 70)
print("8. MONTHLY BREAKDOWN")
print("=" * 70)

by_month = defaultdict(list)
for t in trades:
    m = t["entry_dt"][:7]
    by_month[m].append(t)

positive_months = 0
negative_months = 0
for m in sorted(by_month.keys()):
    group = by_month[m]
    total = sum(t["profitLoss"] for t in group)
    w = len([t for t in group if t["isWin"]])
    l = len(group) - w
    if total > 0: positive_months += 1
    else: negative_months += 1
    bar = "+" * max(0, int(total / 500)) + "-" * max(0, int(-total / 500))
    print(f"  {m}: {len(group):2d} trades | W:{w:2d} L:{l:2d} | ${total:+10,.0f} | {bar}")

print(f"\n  Positive months: {positive_months} | Negative months: {negative_months} ({positive_months/(positive_months+negative_months)*100:.0f}% positive)")

# ============================================================
print("\n" + "=" * 70)
print("9. TOP 15 WORST TRADES")
print("=" * 70)

sorted_trades = sorted(trades, key=lambda t: t["profitLoss"])
for i, t in enumerate(sorted_trades[:15]):
    sym = t["symbols"][0]["value"].strip()
    print(f"  {i+1:2d}. {t['entry_dt']} | {t['opt_type']:4s} | Entry: ${t['entryPrice']:.2f} → "
          f"Exit: ${t['exitPrice']:.2f} | P&L: ${t['profitLoss']:+7,.0f} ({t['pnl_pct']:+.1f}%) | "
          f"Hold: {t['hold_minutes']}min | MAE:{t['mae_pct']:.0f}% MFE:{t['mfe_pct']:.0f}%")

# ============================================================
print("\n" + "=" * 70)
print("10. TOP 15 BEST TRADES")
print("=" * 70)

for i, t in enumerate(sorted(trades, key=lambda t: t["profitLoss"], reverse=True)[:15]):
    sym = t["symbols"][0]["value"].strip()
    print(f"  {i+1:2d}. {t['entry_dt']} | {t['opt_type']:4s} | Entry: ${t['entryPrice']:.2f} → "
          f"Exit: ${t['exitPrice']:.2f} | P&L: ${t['profitLoss']:+7,.0f} ({t['pnl_pct']:+.1f}%) | "
          f"Hold: {t['hold_minutes']}min | MAE:{t['mae_pct']:.0f}% MFE:{t['mfe_pct']:.0f}%")

# ============================================================
print("\n" + "=" * 70)
print("11. YEARLY BREAKDOWN")
print("=" * 70)

by_year = defaultdict(list)
for t in trades:
    by_year[t["entry_dt"][:4]].append(t)

for y in sorted(by_year.keys()):
    group = by_year[y]
    total = sum(t["profitLoss"] for t in group)
    w = len([t for t in group if t["isWin"]])
    wr = w / len(group) * 100
    fees = sum(t["totalFees"] for t in group)
    avg_pnl = sum(t["pnl_pct"] for t in group) / len(group)
    print(f"  {y}: {len(group):3d} trades | WR: {wr:.1f}% | P&L: ${total:+10,.0f} | Fees: ${fees:,.0f} | Avg: {avg_pnl:+.1f}%")

# ============================================================
print("\n" + "=" * 70)
print("12. QUANTITY ANALYSIS")  
print("=" * 70)

qty_buckets = [(f"{lo}-{hi}", lo, hi) for lo, hi in [(1,5),(5,10),(10,20),(20,30),(30,50)]]
for label, lo, hi in qty_buckets:
    group = [t for t in trades if lo <= t["quantity"] < hi]
    if not group:
        continue
    w = len([t for t in group if t["isWin"]])
    total_pnl = sum(t["profitLoss"] for t in group)
    avg_pnl = sum(t["pnl_pct"] for t in group) / len(group)
    print(f"  Qty {label:6s}: {len(group):3d} trades | WR: {w/len(group)*100:.1f}% | P&L: ${total_pnl:+10,.0f}")

# ============================================================
print("\n" + "=" * 70)
print("KEY FINDINGS SUMMARY")
print("=" * 70)

# Key metrics
total_pnl = sum(t["profitLoss"] for t in trades)
total_fees = sum(t["totalFees"] for t in trades)
pnl_before_fees = total_pnl + total_fees
loss_from_overnight = sum(t["profitLoss"] for t in trades if not t["same_day"])
loss_from_same_day = sum(t["profitLoss"] for t in trades if t["same_day"])

print(f"\n  Total P&L: ${total_pnl:+,.0f}")
print(f"  Total Fees: ${total_fees:,.0f}")
print(f"  P&L Before Fees: ${pnl_before_fees:+,.0f}")
print(f"  P&L Same-Day exits: ${loss_from_same_day:+,.0f}")
print(f"  P&L Overnight exits: ${loss_from_overnight:+,.0f}")

if loss_mfe:
    print(f"\n  CRITICAL: {len(loss_mfe)} losing trades ({len(loss_mfe)/len(losses)*100:.0f}% of losers) were in profit before turning to loss")
    print(f"  Total profit left on table from these: ${total_missed:,.0f}")

print(f"\n  If we had captured even 50% of missed MFE on losers: ${total_pnl + total_missed*0.5:+,.0f}")
print(f"\n{'=' * 70}")
