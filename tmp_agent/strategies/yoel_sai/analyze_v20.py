import json
from datetime import datetime, timedelta
from collections import defaultdict

# Load V2.0 results
with open("C:/AI_VAULT/tmp_agent/strategies/yoel_sai/backtest_results_v20.json") as f:
    data = json.load(f)

tp = data.get("totalPerformance", {})
trades = tp.get("closedTrades", [])
print(f"Total closed trades: {len(trades)}")
if not trades:
    print("NO TRADES - check if totalPerformance has data")
    import sys; sys.exit()

# Parse trades
parsed = []
for t in trades:
    sym_val = t.get("symbol", {}).get("value", "") if isinstance(t.get("symbol"), dict) else ""
    # Try alternative structures
    if not sym_val:
        syms = t.get("symbols", [])
        if syms:
            sym_val = syms[0].get("value", "") if isinstance(syms[0], dict) else str(syms[0])
    
    is_put = "P0" in sym_val or "P 0" in sym_val
    is_call = "C0" in sym_val or "C 0" in sym_val
    direction = "PUT" if is_put else ("CALL" if is_call else "UNKNOWN")
    
    # Extract ticker from symbol
    # Symbol format: "AAPL ..." or "SPY ..."
    ticker = sym_val.split(" ")[0] if sym_val else "?"
    # For options it might be like "AAPL 32ND..."
    
    pnl = t.get("profitLoss", 0)
    fees = t.get("totalFees", 0)
    net_pnl = pnl - abs(fees)
    entry_price = t.get("entryPrice", 0)
    exit_price = t.get("exitPrice", 0)
    mae = t.get("mae", 0)  # max adverse excursion ($)
    mfe = t.get("mfe", 0)  # max favorable excursion ($)
    is_win = t.get("isWin", False)
    duration = t.get("duration", "")
    qty = t.get("quantity", 0)
    entry_time = t.get("entryTime", "")
    exit_time = t.get("exitTime", "")
    
    # Calculate P&L % on option premium
    if entry_price > 0 and qty != 0:
        pnl_pct = (exit_price - entry_price) / entry_price * 100
        mae_pct = mae / (entry_price * abs(qty) * 100) * 100 if entry_price > 0 else 0
        mfe_pct = mfe / (entry_price * abs(qty) * 100) * 100 if entry_price > 0 else 0
    else:
        pnl_pct = 0
        mae_pct = 0
        mfe_pct = 0
    
    # Parse duration to minutes
    hold_mins = 0
    if duration:
        try:
            parts = duration.split(":")
            if "." in parts[0]:
                day_hr = parts[0].split(".")
                days = int(day_hr[0])
                hours = int(day_hr[1])
            else:
                days = 0
                hours = int(parts[0])
            mins = int(parts[1])
            secs = float(parts[2]) if len(parts) > 2 else 0
            hold_mins = days * 24 * 60 + hours * 60 + mins + secs / 60
        except:
            hold_mins = 0
    
    parsed.append({
        "ticker": ticker,
        "direction": direction,
        "entry_price": entry_price,
        "exit_price": exit_price,
        "pnl": pnl,
        "net_pnl": net_pnl,
        "fees": fees,
        "pnl_pct": pnl_pct,
        "mae": mae,
        "mfe": mfe,
        "mae_pct": mae_pct,
        "mfe_pct": mfe_pct,
        "is_win": is_win,
        "hold_mins": hold_mins,
        "duration": duration,
        "qty": qty,
        "entry_time": entry_time,
        "exit_time": exit_time,
        "symbol": sym_val,
    })

# ============================================================
# ANALYSIS
# ============================================================
wins = [t for t in parsed if t["is_win"]]
losses = [t for t in parsed if not t["is_win"]]
puts = [t for t in parsed if t["direction"] == "PUT"]
calls = [t for t in parsed if t["direction"] == "CALL"]

print(f"\n{'='*60}")
print(f"V2.0 MULTI-TICKER FORENSIC ANALYSIS")
print(f"{'='*60}")
print(f"Total trades: {len(parsed)}")
print(f"Wins: {len(wins)} ({len(wins)/len(parsed)*100:.1f}%)")
print(f"Losses: {len(losses)} ({len(losses)/len(parsed)*100:.1f}%)")
print(f"Total P&L: ${sum(t['pnl'] for t in parsed):,.0f}")
print(f"Total Fees: ${sum(t['fees'] for t in parsed):,.0f}")
print(f"Avg Win P&L%: {sum(t['pnl_pct'] for t in wins)/len(wins):.1f}%" if wins else "")
print(f"Avg Loss P&L%: {sum(t['pnl_pct'] for t in losses)/len(losses):.1f}%" if losses else "")

# --- BY DIRECTION ---
print(f"\n--- BY DIRECTION ---")
for label, group in [("PUT", puts), ("CALL", calls)]:
    if not group:
        continue
    w = [t for t in group if t["is_win"]]
    l = [t for t in group if not t["is_win"]]
    total_pnl = sum(t["pnl"] for t in group)
    wr = len(w) / len(group) * 100
    avg_win = sum(t["pnl_pct"] for t in w) / len(w) if w else 0
    avg_loss = sum(t["pnl_pct"] for t in l) / len(l) if l else 0
    print(f"  {label}: {len(group)} trades | WR {wr:.1f}% | P&L ${total_pnl:,.0f} | AvgWin {avg_win:.1f}% | AvgLoss {avg_loss:.1f}%")

# --- BY TICKER ---
print(f"\n--- BY TICKER ---")
ticker_groups = defaultdict(list)
for t in parsed:
    ticker_groups[t["ticker"]].append(t)

for ticker in sorted(ticker_groups.keys(), key=lambda k: sum(t["pnl"] for t in ticker_groups[k])):
    group = ticker_groups[ticker]
    w = [t for t in group if t["is_win"]]
    total_pnl = sum(t["pnl"] for t in group)
    wr = len(w) / len(group) * 100
    print(f"  {ticker:6s}: {len(group):3d} trades | WR {wr:.1f}% | P&L ${total_pnl:+,.0f}")

# --- BY HOLDING TIME ---
print(f"\n--- BY HOLDING TIME ---")
time_buckets = [
    ("0-15 min", 0, 15),
    ("15-30 min", 15, 30),
    ("30-60 min", 30, 60),
    ("1-2 hrs", 60, 120),
    ("2-4 hrs", 120, 240),
    ("4+ hrs", 240, 99999),
]
for label, lo, hi in time_buckets:
    group = [t for t in parsed if lo <= t["hold_mins"] < hi]
    if not group:
        continue
    w = [t for t in group if t["is_win"]]
    total_pnl = sum(t["pnl"] for t in group)
    wr = len(w) / len(group) * 100
    print(f"  {label:12s}: {len(group):3d} trades | WR {wr:.1f}% | P&L ${total_pnl:+,.0f}")

# --- EXIT TYPE ANALYSIS (from tags would be ideal, but we use P&L patterns) ---
print(f"\n--- EXIT PATTERNS ---")
# TP hits (pnl_pct close to +30%)
tp_hits = [t for t in parsed if t["pnl_pct"] >= 25]
sl_hits = [t for t in parsed if t["pnl_pct"] <= -25]
mid_exits = [t for t in parsed if -25 < t["pnl_pct"] < 25]
print(f"  TP hits (>+25%): {len(tp_hits)} ({len(tp_hits)/len(parsed)*100:.1f}%)")
print(f"  SL hits (<-25%): {len(sl_hits)} ({len(sl_hits)/len(parsed)*100:.1f}%)")
print(f"  Mid exits (time/EOD): {len(mid_exits)} ({len(mid_exits)/len(parsed)*100:.1f}%)")

# --- MAE ANALYSIS ---
print(f"\n--- MAE (Max Adverse Excursion) ---")
mae_buckets = [
    ("0-5%", 0, 5),
    ("5-10%", 5, 10),
    ("10-15%", 10, 15),
    ("15-20%", 15, 20),
    ("20-30%", 20, 30),
    ("30%+", 30, 999),
]
for label, lo, hi in mae_buckets:
    group = [t for t in parsed if lo <= abs(t["mae_pct"]) < hi]
    if not group:
        continue
    w = [t for t in group if t["is_win"]]
    wr = len(w) / len(group) * 100
    total_pnl = sum(t["pnl"] for t in group)
    print(f"  MAE {label:8s}: {len(group):3d} trades | WR {wr:.1f}% | P&L ${total_pnl:+,.0f}")

# --- MFE ANALYSIS (losers that were profitable first) ---
print(f"\n--- LOSERS THAT WERE PROFITABLE FIRST ---")
losers_with_mfe = [t for t in losses if t["mfe"] > 0]
print(f"  Losers with positive MFE: {len(losers_with_mfe)} of {len(losses)} ({len(losers_with_mfe)/len(losses)*100:.1f}%)")
if losers_with_mfe:
    avg_mfe = sum(t["mfe_pct"] for t in losers_with_mfe) / len(losers_with_mfe)
    print(f"  Avg MFE of those losers: {avg_mfe:.1f}%")

# --- DIRECTION BY TICKER ---
print(f"\n--- PUT vs CALL BY TICKER ---")
for ticker in sorted(ticker_groups.keys()):
    group = ticker_groups[ticker]
    p = [t for t in group if t["direction"] == "PUT"]
    c = [t for t in group if t["direction"] == "CALL"]
    pw = len([t for t in p if t["is_win"]]) / len(p) * 100 if p else 0
    cw = len([t for t in c if t["is_win"]]) / len(c) * 100 if c else 0
    pp = sum(t["pnl"] for t in p)
    cp = sum(t["pnl"] for t in c)
    print(f"  {ticker:6s}: PUT {len(p):2d} (WR {pw:.0f}%, ${pp:+,.0f}) | CALL {len(c):2d} (WR {cw:.0f}%, ${cp:+,.0f})")

# --- YEARLY BREAKDOWN ---
print(f"\n--- BY YEAR ---")
year_groups = defaultdict(list)
for t in parsed:
    if t["entry_time"]:
        try:
            yr = t["entry_time"][:4]
            year_groups[yr].append(t)
        except:
            pass

for yr in sorted(year_groups.keys()):
    group = year_groups[yr]
    w = [t for t in group if t["is_win"]]
    total_pnl = sum(t["pnl"] for t in group)
    wr = len(w) / len(group) * 100 if group else 0
    print(f"  {yr}: {len(group):3d} trades | WR {wr:.1f}% | P&L ${total_pnl:+,.0f}")
