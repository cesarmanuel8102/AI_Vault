"""
Forensic Analysis Part 2: Deep trade-by-trade analysis
Parse every OPEN/CLOSE pair, calculate P&L distribution, 
identify wick patterns and decline periods.
"""
import json, re
from collections import defaultdict
from datetime import datetime, timedelta

with open("C:/AI_VAULT/tmp_agent/strategies/yoel_options/forensic_raw.json") as f:
    data = json.load(f)

# Focus on BASELINE
label = "BASELINE"
opens = data[label]["opens"]
closes = data[label]["closes"]

print("=" * 80)
print(f"FORENSIC ANALYSIS - {label} (PT=0.35, SL=-0.20, Risk=0.05)")
print("=" * 80)

# ========================================
# 1. Parse all trades into structured data
# ========================================
trade_list = []
for i, (o, c) in enumerate(zip(opens, closes)):
    # Parse OPEN
    # Format: 2023-02-13 09:35:00 OPEN YOEL_CALL_QQQ_230213_1: x3 ask=$9.31 lim=$12.57 DTE=24 K=300.0 conf=1.25[...]
    o_match = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+OPEN\s+(\S+):\s+x(\d+)\s+ask=\$([0-9.]+)\s+lim=\$([0-9.]+)\s+DTE=(\d+)\s+K=([0-9.]+)\s+conf=([0-9.]+)\[sc=([0-9.]+),rg=([0-9.]+),hl=([0-9.]+)\]', o)
    
    # Parse CLOSE
    # Format: 2023-02-14 10:12:00 CLOSE YOEL_CALL_QQQ_230213_1: LIMIT_FILL_TP PnL=$+978(+35%) held=1d
    c_match = re.match(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+CLOSE\s+(\S+):\s+(\S+)\s+PnL=\$([+-]?[0-9,]+)\(([+-]?\d+)%\)\s+held=(\d+)d', c)
    
    if not o_match or not c_match:
        # Try to still parse what we can
        # Just get basic info from the strings
        pass
    
    if o_match and c_match:
        open_date = datetime.strptime(o_match.group(1), "%Y-%m-%d %H:%M:%S")
        trade_id = o_match.group(2)
        qty = int(o_match.group(3))
        ask = float(o_match.group(4))
        limit = float(o_match.group(5))
        dte = int(o_match.group(6))
        strike = float(o_match.group(7))
        conf = float(o_match.group(8))
        score = float(o_match.group(9))
        regime = float(o_match.group(10))
        health = float(o_match.group(11))
        
        close_date = datetime.strptime(c_match.group(1), "%Y-%m-%d %H:%M:%S")
        exit_type = c_match.group(3)
        pnl_dollar = int(c_match.group(4).replace(",", ""))
        pnl_pct = int(c_match.group(5))
        held_days = int(c_match.group(6))
        
        # Extract ticker from trade_id: YOEL_CALL_QQQ_230213_1 -> QQQ
        ticker_match = re.search(r'YOEL_CALL_(\w+)_\d+', trade_id)
        ticker = ticker_match.group(1) if ticker_match else "?"
        
        trade_list.append({
            "idx": i+1,
            "open_date": open_date,
            "close_date": close_date,
            "ticker": ticker,
            "qty": qty,
            "ask": ask,
            "limit": limit,
            "dte": dte,
            "strike": strike,
            "conf": conf,
            "score": score,
            "regime": regime,
            "health": health,
            "exit_type": exit_type,
            "pnl_dollar": pnl_dollar,
            "pnl_pct": pnl_pct,
            "held_days": held_days,
        })

print(f"\nParsed {len(trade_list)} / {len(opens)} trades")

# ========================================
# 2. EXIT TYPE ANALYSIS (why wicks happen)
# ========================================
print("\n" + "=" * 80)
print("2. EXIT TYPE DISTRIBUTION")
print("=" * 80)

exit_types = defaultdict(lambda: {"count": 0, "total_pnl": 0, "pnls": []})
for t in trade_list:
    et = t["exit_type"]
    exit_types[et]["count"] += 1
    exit_types[et]["total_pnl"] += t["pnl_dollar"]
    exit_types[et]["pnls"].append(t["pnl_pct"])

for et, data_et in sorted(exit_types.items(), key=lambda x: -x[1]["count"]):
    avg_pnl = sum(data_et["pnls"]) / len(data_et["pnls"]) if data_et["pnls"] else 0
    print(f"  {et:<25} Count: {data_et['count']:>3} | Total $: {data_et['total_pnl']:>+8,} | Avg %: {avg_pnl:>+6.1f}%")

# ========================================
# 3. P&L DISTRIBUTION ANALYSIS
# ========================================
print("\n" + "=" * 80)
print("3. P&L DISTRIBUTION")
print("=" * 80)

winners = [t for t in trade_list if t["pnl_dollar"] > 0]
losers = [t for t in trade_list if t["pnl_dollar"] < 0]
breakeven = [t for t in trade_list if t["pnl_dollar"] == 0]

print(f"  Winners: {len(winners)} ({len(winners)/len(trade_list)*100:.0f}%)")
print(f"  Losers:  {len(losers)} ({len(losers)/len(trade_list)*100:.0f}%)")
print(f"  BE:      {len(breakeven)}")

if winners:
    avg_win = sum(t["pnl_dollar"] for t in winners) / len(winners)
    max_win = max(t["pnl_dollar"] for t in winners)
    avg_win_pct = sum(t["pnl_pct"] for t in winners) / len(winners)
    print(f"  Avg Win:  ${avg_win:,.0f} ({avg_win_pct:+.0f}%) | Max Win: ${max_win:,}")

if losers:
    avg_loss = sum(t["pnl_dollar"] for t in losers) / len(losers)
    max_loss = min(t["pnl_dollar"] for t in losers)
    avg_loss_pct = sum(t["pnl_pct"] for t in losers) / len(losers)
    print(f"  Avg Loss: ${avg_loss:,.0f} ({avg_loss_pct:+.0f}%) | Max Loss: ${max_loss:,}")

# ========================================
# 4. WICK ANALYSIS: Trades that hit TP at exactly 35%
#    vs trades that could have gone higher
# ========================================
print("\n" + "=" * 80)
print("4. WICK ANALYSIS - Money left on the table")
print("=" * 80)

tp_trades = [t for t in trade_list if "TP" in t["exit_type"] or "FILL_TP" in t["exit_type"]]
sl_trades = [t for t in trade_list if "SL" in t["exit_type"]]

print(f"  TP exits: {len(tp_trades)} (all exit at +35% by design)")
print(f"  SL exits: {len(sl_trades)}")

# The TP trades ALL exit at exactly +35%. If the underlying kept moving up,
# the strategy missed the rest. The "wick" on the equity chart is:
# - Trade opens, moves up, hits +35%, closes -> equity jumps
# - But if the option would have gone to +100%, we left +65% on the table

# Analyze TP trades by held_days
print(f"\n  TP trades by hold duration:")
tp_by_hold = defaultdict(list)
for t in tp_trades:
    tp_by_hold[t["held_days"]].append(t)
for days in sorted(tp_by_hold.keys()):
    trades_d = tp_by_hold[days]
    total_pnl = sum(t["pnl_dollar"] for t in trades_d)
    print(f"    Held {days}d: {len(trades_d)} trades, total ${total_pnl:+,}")

# TP trades that close same day (held=0d) - these moved FAST
fast_tp = [t for t in tp_trades if t["held_days"] == 0]
print(f"\n  FAST TP (same day, held=0d): {len(fast_tp)} trades")
print(f"  These options moved +35% in HOURS - very likely continued higher")
for t in fast_tp[:10]:
    print(f"    {t['open_date'].strftime('%Y-%m-%d')} {t['ticker']} x{t['qty']} ${t['pnl_dollar']:+,} conf={t['conf']}")

# ========================================
# 5. LOSING STREAKS ANALYSIS (decline periods)
# ========================================
print("\n" + "=" * 80)
print("5. LOSING STREAKS / DECLINE PERIODS")
print("=" * 80)

# Build equity curve from trades
equity = 10000
equity_curve = [(trade_list[0]["open_date"], equity)]
peak = equity
max_dd = 0
dd_start = None
dd_periods = []
current_streak = 0
max_streak = 0
streak_start = None

for t in trade_list:
    equity += t["pnl_dollar"]
    equity_curve.append((t["close_date"], equity))
    
    if equity > peak:
        if dd_start and max_dd > 0.10:  # record DD periods > 10%
            dd_periods.append({
                "start": dd_start,
                "end": t["close_date"],
                "peak_equity": peak_before_dd,
                "trough_equity": trough_equity,
                "dd_pct": (peak_before_dd - trough_equity) / peak_before_dd * 100,
                "recovery_date": t["close_date"],
            })
        peak = equity
        peak_before_dd = peak
        trough_equity = equity
        dd_start = None
        max_dd = 0
    else:
        if dd_start is None:
            dd_start = t["close_date"]
            peak_before_dd = peak
            trough_equity = equity
        trough_equity = min(trough_equity, equity)
        dd = (peak - equity) / peak
        max_dd = max(max_dd, dd)
    
    # Streak tracking
    if t["pnl_dollar"] < 0:
        if current_streak >= 0:
            current_streak = -1
            streak_start = t["open_date"]
        else:
            current_streak -= 1
    else:
        if current_streak < 0:
            if abs(current_streak) >= 3:
                print(f"  Losing streak: {abs(current_streak)} trades from {streak_start.strftime('%Y-%m-%d')} to {t['open_date'].strftime('%Y-%m-%d')}")
                # Show what happened
                streak_idx = trade_list.index(t)
                for si in range(max(0, streak_idx + current_streak), streak_idx):
                    st = trade_list[si]
                    print(f"    {st['open_date'].strftime('%Y-%m-%d')} {st['ticker']} {st['exit_type']} ${st['pnl_dollar']:+,} ({st['pnl_pct']:+d}%) conf={st['conf']} regime={st['regime']} health={st['health']}")
        current_streak = 1

print(f"\n  Major drawdown periods (>10%):")
for dp in dd_periods:
    duration = (dp["recovery_date"] - dp["start"]).days
    print(f"    {dp['start'].strftime('%Y-%m-%d')} to {dp['recovery_date'].strftime('%Y-%m-%d')} ({duration}d)")
    print(f"      Peak: ${dp['peak_equity']:,.0f} -> Trough: ${dp['trough_equity']:,.0f} = DD {dp['dd_pct']:.1f}%")

# ========================================
# 6. MONTHLY P&L BREAKDOWN
# ========================================
print("\n" + "=" * 80)
print("6. MONTHLY P&L BREAKDOWN")
print("=" * 80)

monthly = defaultdict(lambda: {"trades": 0, "wins": 0, "pnl": 0, "pnls": []})
for t in trade_list:
    key = t["close_date"].strftime("%Y-%m")
    monthly[key]["trades"] += 1
    monthly[key]["pnl"] += t["pnl_dollar"]
    monthly[key]["pnls"].append(t["pnl_dollar"])
    if t["pnl_dollar"] > 0:
        monthly[key]["wins"] += 1

print(f"  {'Month':<8} {'Trades':>6} {'Wins':>5} {'WR':>5} {'PnL':>9} {'Avg':>8}")
print(f"  {'-'*45}")
for month in sorted(monthly.keys()):
    m = monthly[month]
    wr = m["wins"] / m["trades"] * 100 if m["trades"] else 0
    avg = m["pnl"] / m["trades"] if m["trades"] else 0
    marker = " ***" if m["pnl"] < -500 else " +++" if m["pnl"] > 2000 else ""
    print(f"  {month:<8} {m['trades']:>6} {m['wins']:>5} {wr:>4.0f}% ${m['pnl']:>+8,} ${avg:>+7,.0f}{marker}")

# ========================================
# 7. REGIME + HEALTH ANALYSIS
# ========================================
print("\n" + "=" * 80)
print("7. TRADE OUTCOMES BY CONFIDENCE COMPONENTS")
print("=" * 80)

# By regime multiplier
print(f"\n  By Regime Multiplier:")
regime_groups = defaultdict(lambda: {"count": 0, "wins": 0, "pnl": 0})
for t in trade_list:
    rg = t["regime"]
    regime_groups[rg]["count"] += 1
    regime_groups[rg]["pnl"] += t["pnl_dollar"]
    if t["pnl_dollar"] > 0:
        regime_groups[rg]["wins"] += 1

for rg in sorted(regime_groups.keys()):
    g = regime_groups[rg]
    wr = g["wins"] / g["count"] * 100 if g["count"] else 0
    print(f"    regime={rg:.2f}: {g['count']:>3} trades, WR={wr:.0f}%, PnL=${g['pnl']:>+8,}")

# By health
print(f"\n  By Health Multiplier:")
health_groups = defaultdict(lambda: {"count": 0, "wins": 0, "pnl": 0})
for t in trade_list:
    hl = t["health"]
    health_groups[hl]["count"] += 1
    health_groups[hl]["pnl"] += t["pnl_dollar"]
    if t["pnl_dollar"] > 0:
        health_groups[hl]["wins"] += 1

for hl in sorted(health_groups.keys()):
    g = health_groups[hl]
    wr = g["wins"] / g["count"] * 100 if g["count"] else 0
    print(f"    health={hl:.2f}: {g['count']:>3} trades, WR={wr:.0f}%, PnL=${g['pnl']:>+8,}")

# By confidence ranges
print(f"\n  By Confidence Range:")
conf_groups = defaultdict(lambda: {"count": 0, "wins": 0, "pnl": 0})
for t in trade_list:
    if t["conf"] <= 0.50:
        bucket = "0.50 (floor)"
    elif t["conf"] <= 0.75:
        bucket = "0.51-0.75"
    elif t["conf"] <= 1.00:
        bucket = "0.76-1.00"
    elif t["conf"] <= 1.50:
        bucket = "1.01-1.50"
    else:
        bucket = "1.51+"
    conf_groups[bucket]["count"] += 1
    conf_groups[bucket]["pnl"] += t["pnl_dollar"]
    if t["pnl_dollar"] > 0:
        conf_groups[bucket]["wins"] += 1

for bucket in ["0.50 (floor)", "0.51-0.75", "0.76-1.00", "1.01-1.50", "1.51+"]:
    if bucket in conf_groups:
        g = conf_groups[bucket]
        wr = g["wins"] / g["count"] * 100 if g["count"] else 0
        avg = g["pnl"] / g["count"]
        print(f"    conf {bucket:<12}: {g['count']:>3} trades, WR={wr:.0f}%, PnL=${g['pnl']:>+8,}, Avg=${avg:>+6,.0f}")

# ========================================
# 8. TICKER ANALYSIS
# ========================================
print("\n" + "=" * 80)
print("8. TICKER BREAKDOWN")
print("=" * 80)

ticker_stats = defaultdict(lambda: {"count": 0, "wins": 0, "pnl": 0, "tp": 0, "sl": 0})
for t in trade_list:
    tk = t["ticker"]
    ticker_stats[tk]["count"] += 1
    ticker_stats[tk]["pnl"] += t["pnl_dollar"]
    if t["pnl_dollar"] > 0:
        ticker_stats[tk]["wins"] += 1
    if "TP" in t["exit_type"]:
        ticker_stats[tk]["tp"] += 1
    if "SL" in t["exit_type"]:
        ticker_stats[tk]["sl"] += 1

for tk in sorted(ticker_stats.keys(), key=lambda x: -ticker_stats[x]["pnl"]):
    s = ticker_stats[tk]
    wr = s["wins"] / s["count"] * 100 if s["count"] else 0
    print(f"  {tk:<6}: {s['count']:>3} trades, WR={wr:.0f}%, PnL=${s['pnl']:>+8,} | TP={s['tp']} SL={s['sl']}")

# ========================================
# 9. HOLD DURATION vs OUTCOME
# ========================================
print("\n" + "=" * 80)
print("9. HOLD DURATION vs OUTCOME")
print("=" * 80)

hold_groups = defaultdict(lambda: {"count": 0, "wins": 0, "pnl": 0})
for t in trade_list:
    hd = t["held_days"]
    if hd == 0:
        bucket = "0d (intraday)"
    elif hd <= 2:
        bucket = "1-2d"
    elif hd <= 5:
        bucket = "3-5d"
    elif hd <= 10:
        bucket = "6-10d"
    else:
        bucket = "11d+"
    hold_groups[bucket]["count"] += 1
    hold_groups[bucket]["pnl"] += t["pnl_dollar"]
    if t["pnl_dollar"] > 0:
        hold_groups[bucket]["wins"] += 1

for bucket in ["0d (intraday)", "1-2d", "3-5d", "6-10d", "11d+"]:
    if bucket in hold_groups:
        g = hold_groups[bucket]
        wr = g["wins"] / g["count"] * 100 if g["count"] else 0
        avg = g["pnl"] / g["count"]
        print(f"  {bucket:<15}: {g['count']:>3} trades, WR={wr:.0f}%, PnL=${g['pnl']:>+8,}, Avg=${avg:>+6,.0f}")

print("\n" + "=" * 80)
print("ANALYSIS COMPLETE")
print("=" * 80)
