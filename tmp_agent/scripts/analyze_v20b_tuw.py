"""
Analyze V2.0b logs to calculate TUW, monthly trade distribution, 
and reconstruct equity curve from trade PnL.
"""
import json, re
from datetime import datetime, timedelta
from collections import defaultdict

logs = json.load(open("C:/AI_VAULT/tmp_agent/strategies/yoel_options/v20b_all_logs.json"))

# ========================================
# 1. Extract all trades from logs
# ========================================
trades = []
open_pattern = re.compile(r"(\d{4}-\d{2}-\d{2}) \d{2}:\d{2}:\d{2} OPEN (\S+):.+conf=([0-9.]+)\[.+risk=([0-9.]+)%")
close_pattern = re.compile(r"(\d{4}-\d{2}-\d{2}) \d{2}:\d{2}:\d{2} CLOSE (\S+): (\S+) PnL=\$([+-]?[0-9,]+)\(([+-]?\d+)%\) held=(\d+)d")

open_trades = {}
for log in logs:
    m = open_pattern.search(log)
    if m:
        date_str, trade_id, conf, risk = m.groups()
        open_trades[trade_id] = {
            "open_date": date_str,
            "conf": float(conf),
            "risk_pct": float(risk)
        }
    
    m = close_pattern.search(log)
    if m:
        date_str, trade_id, exit_type, pnl_str, pnl_pct, held_days = m.groups()
        pnl = float(pnl_str.replace(",", ""))
        open_info = open_trades.get(trade_id, {})
        trades.append({
            "close_date": date_str,
            "open_date": open_info.get("open_date", ""),
            "trade_id": trade_id,
            "exit_type": exit_type,
            "pnl": pnl,
            "pnl_pct": int(pnl_pct),
            "held_days": int(held_days),
            "conf": open_info.get("conf", 0),
            "risk_pct": open_info.get("risk_pct", 0)
        })

print(f"Extracted {len(trades)} trades")

# ========================================
# 2. Reconstruct equity curve from trades
# ========================================
equity = 10000.0
equity_curve = [(datetime(2023, 1, 1), equity)]

for trade in sorted(trades, key=lambda t: t["close_date"]):
    equity += trade["pnl"]
    dt = datetime.strptime(trade["close_date"], "%Y-%m-%d")
    equity_curve.append((dt, equity))

print(f"Equity curve: {len(equity_curve)} points")
print(f"Start: ${equity_curve[0][1]:,.2f} on {equity_curve[0][0].date()}")
print(f"End: ${equity_curve[-1][1]:,.2f} on {equity_curve[-1][0].date()}")
print(f"Peak: ${max(e[1] for e in equity_curve):,.2f}")

# ========================================
# 3. Calculate TUW (Time Under Water)
# ========================================
print("\n" + "=" * 60)
print("TUW ANALYSIS (Time Under Water)")
print("=" * 60)

# For TUW we need daily data. Interpolate equity between trades.
# Use calendar days from 2023-01-01 to 2024-12-28
start_date = datetime(2023, 1, 1)
end_date = datetime(2024, 12, 28)
total_cal_days = (end_date - start_date).days + 1

# Build daily equity by carrying forward last known equity
daily_equity = {}
trade_dates = {dt.date(): eq for dt, eq in equity_curve}

current_eq = 10000.0
for day_offset in range(total_cal_days):
    d = (start_date + timedelta(days=day_offset)).date()
    if d in trade_dates:
        current_eq = trade_dates[d]
    daily_equity[d] = current_eq

# Calculate TUW
running_peak = 0
days_underwater = 0
max_tuw_streak = 0
current_streak = 0
current_streak_start = None
tuw_periods = []

dates_sorted = sorted(daily_equity.keys())
for d in dates_sorted:
    eq = daily_equity[d]
    if eq >= running_peak:
        if current_streak > 0:
            tuw_periods.append((current_streak_start, d, current_streak))
        running_peak = eq
        current_streak = 0
        current_streak_start = None
    else:
        days_underwater += 1
        current_streak += 1
        if current_streak_start is None:
            current_streak_start = d
        max_tuw_streak = max(max_tuw_streak, current_streak)

# If still underwater at end
if current_streak > 0:
    tuw_periods.append((current_streak_start, dates_sorted[-1], current_streak))

tuw_pct = days_underwater / total_cal_days * 100

print(f"Total calendar days: {total_cal_days}")
print(f"Days underwater: {days_underwater}")
print(f"TUW: {tuw_pct:.1f}%")
print(f"Max consecutive days underwater: {max_tuw_streak}")
print(f"Kill Gate (TUW <= 65%): {'PASS' if tuw_pct <= 65 else 'FAIL'}")

print(f"\nLongest underwater periods:")
tuw_periods.sort(key=lambda x: x[2], reverse=True)
for start, end, days in tuw_periods[:10]:
    print(f"  {start} to {end}: {days} calendar days")

# ========================================
# 4. Monthly trade distribution
# ========================================
print("\n" + "=" * 60)
print("MONTHLY TRADE DISTRIBUTION")
print("=" * 60)

monthly = defaultdict(lambda: {"trades": 0, "wins": 0, "pnl": 0})
for trade in trades:
    dt = datetime.strptime(trade["close_date"], "%Y-%m-%d")
    m = f"{dt.year}-{dt.month:02d}"
    monthly[m]["trades"] += 1
    monthly[m]["pnl"] += trade["pnl"]
    if trade["pnl"] > 0:
        monthly[m]["wins"] += 1

print(f"\n{'Month':<10} {'Trades':>7} {'WR%':>6} {'PnL':>10} {'Cum PnL':>10} {'Status':>10}")
print("-" * 56)
cum_pnl = 0
months_below_6 = 0
total_trades = 0
for m in sorted(monthly.keys()):
    d = monthly[m]
    wr = d["wins"] / d["trades"] * 100 if d["trades"] > 0 else 0
    cum_pnl += d["pnl"]
    flag = "<-- LOW" if d["trades"] < 6 else ""
    if d["trades"] < 6:
        months_below_6 += 1
    total_trades += d["trades"]
    print(f"{m:<10} {d['trades']:>7} {wr:>5.0f}% {d['pnl']:>+10,.0f} {cum_pnl:>+10,.0f} {flag:>10}")

num_months = len(monthly)
avg_per_month = total_trades / num_months if num_months > 0 else 0
print("-" * 56)
print(f"{'TOTAL':<10} {total_trades:>7} {'':>6} {cum_pnl:>+10,.0f}")
print(f"Months: {num_months}")
print(f"Avg trades/month: {avg_per_month:.1f}")
print(f"Months below 6 trades: {months_below_6}")
print(f"Kill Gate (>= 6 trades/month avg): {'PASS' if avg_per_month >= 6 else 'FAIL'}")

# ========================================
# 5. Drawdown analysis (detailed)
# ========================================
print("\n" + "=" * 60)
print("DRAWDOWN ANALYSIS (from equity curve)")
print("=" * 60)

running_peak = 10000
max_dd_pct = 0
max_dd_date = None

for dt, eq in equity_curve:
    if eq > running_peak:
        running_peak = eq
    dd_pct = (eq - running_peak) / running_peak * 100 if running_peak > 0 else 0
    if dd_pct < max_dd_pct:
        max_dd_pct = dd_pct
        max_dd_date = dt
        max_dd_eq = eq
        max_dd_peak = running_peak

print(f"Max DD: {max_dd_pct:.1f}% on {max_dd_date.date()}")
print(f"At max DD: equity=${max_dd_eq:,.2f}, peak was=${max_dd_peak:,.2f}")
print(f"Dollar DD: ${max_dd_eq - max_dd_peak:,.2f}")

# Monthly equity snapshot
print("\n--- Monthly Equity Snapshots ---")
monthly_eq = {}
for dt, eq in equity_curve:
    m = f"{dt.year}-{dt.month:02d}"
    monthly_eq[m] = eq

for m in sorted(monthly_eq.keys()):
    print(f"  {m}: ${monthly_eq[m]:,.2f}")

# ========================================
# 6. KILL GATE SUMMARY
# ========================================
print("\n" + "=" * 60)
print("KILL GATE ASSESSMENT (Contract v2.1 Mode A)")
print("=" * 60)

cagr = 66.4
sharpe = 1.337
trades_per_month = avg_per_month

print(f"{'Gate':<25} {'Threshold':<15} {'Actual':<15} {'Status':<10}")
print("-" * 65)
print(f"{'CAGR':<25} {'>= 12%':<15} {cagr:.1f}%{'':<8} {'PASS' if cagr >= 12 else 'FAIL':<10}")
print(f"{'Sharpe':<25} {'>= 1.0':<15} {sharpe:.3f}{'':<8} {'PASS' if sharpe >= 1.0 else 'FAIL':<10}")
print(f"{'TUW':<25} {'<= 65%':<15} {tuw_pct:.1f}%{'':<8} {'PASS' if tuw_pct <= 65 else 'FAIL':<10}")
print(f"{'Trades/month':<25} {'>= 6':<15} {trades_per_month:.1f}{'':<10} {'PASS' if trades_per_month >= 6 else 'FAIL':<10}")
print(f"{'Max DD':<25} {'(prop ~10%)':<15} {max_dd_pct:.1f}%{'':<7} {'CONCERN' if abs(max_dd_pct) > 15 else 'OK':<10}")

# ========================================
# 7. Prop Firm DD Assessment
# ========================================
print("\n" + "=" * 60)
print("PROP FIRM MAX DD ASSESSMENT")
print("=" * 60)
print("""
Typical prop firm DD limits:
  - FTMO: 10% daily, 10% total
  - TopStep: 3-4.5% trailing
  - Apex: $2,500-$3,000 on $50K (5-6%)
  - The5ers: 4% daily, 10% total
  
V2.0b Max DD: {:.1f}% = EXCEEDS ALL PROP FIRM LIMITS
This is the #1 issue to fix before going live.

Options:
  1. Reduce base risk from 5% to 2-3%
  2. Tighten confidence cap from 3.0x to 1.5-2.0x  
  3. Add monthly circuit breaker (halt after -5% monthly)
  4. Add daily DD limit (halt after -3% daily)
  5. Reduce max position size
""".format(abs(max_dd_pct)))
