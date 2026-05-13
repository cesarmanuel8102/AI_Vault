"""Quick TUW + trades/month for V2.0c."""
import json, re
from datetime import datetime, timedelta
from collections import defaultdict

logs = json.load(open("C:/AI_VAULT/tmp_agent/strategies/yoel_options/v20b_all_logs.json"))

# First re-download V2.0c logs
import time, requests
from hashlib import sha256
from base64 import b64encode

UID = "384945"
TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
BASE = "https://www.quantconnect.com/api/v2"
PROJECT_ID = 29490680
BT_ID = "0602179e98de8735846428ef8e4e0e71"

def headers():
    ts = str(int(time.time()))
    h = sha256(f"{TOKEN}:{ts}".encode()).hexdigest()
    auth = b64encode(f"{UID}:{h}".encode()).decode()
    return {"Authorization": f"Basic {auth}", "Timestamp": ts, "Content-Type": "application/json"}

all_logs = []
start = 0
while True:
    r = requests.post(f"{BASE}/backtests/read/log", headers=headers(), json={
        "projectId": PROJECT_ID, "backtestId": BT_ID,
        "start": start, "end": start + 200, "query": " "
    })
    d = r.json()
    logs_batch = d.get("logs", [])
    total = d.get("length", 0)
    all_logs.extend(logs_batch)
    if len(logs_batch) < 200 or start + 200 >= total:
        break
    start += 200

print(f"Downloaded {len(all_logs)} logs")

# Extract trades
close_pattern = re.compile(r"(\d{4}-\d{2}-\d{2}) \d{2}:\d{2}:\d{2} CLOSE (\S+): (\S+) PnL=\$([+-]?[0-9,]+)\(([+-]?\d+)%\) held=(\d+)d")
trades = []
for log in all_logs:
    m = close_pattern.search(log)
    if m:
        date_str, trade_id, exit_type, pnl_str, pnl_pct, held_days = m.groups()
        pnl = float(pnl_str.replace(",", ""))
        trades.append({"close_date": date_str, "pnl": pnl})

print(f"Extracted {len(trades)} trades")

# Reconstruct equity curve
equity = 10000.0
equity_curve = [(datetime(2023, 1, 1), equity)]
for t in sorted(trades, key=lambda x: x["close_date"]):
    equity += t["pnl"]
    equity_curve.append((datetime.strptime(t["close_date"], "%Y-%m-%d"), equity))

print(f"End equity: ${equity:,.2f}")
print(f"Peak equity: ${max(e[1] for e in equity_curve):,.2f}")

# Build daily equity
start_date = datetime(2023, 1, 1)
end_date = datetime(2024, 12, 28)
total_days = (end_date - start_date).days + 1

trade_eq = {dt.date(): eq for dt, eq in equity_curve}
current_eq = 10000.0
daily = {}
for i in range(total_days):
    d = (start_date + timedelta(days=i)).date()
    if d in trade_eq:
        current_eq = trade_eq[d]
    daily[d] = current_eq

# TUW
running_peak = 0
days_uw = 0
max_streak = 0
streak = 0
streak_start = None
tuw_periods = []

for d in sorted(daily.keys()):
    eq = daily[d]
    if eq >= running_peak:
        if streak > 0:
            tuw_periods.append((streak_start, d, streak))
        running_peak = eq
        streak = 0
        streak_start = None
    else:
        days_uw += 1
        streak += 1
        if streak_start is None:
            streak_start = d
        max_streak = max(max_streak, streak)

if streak > 0:
    tuw_periods.append((streak_start, sorted(daily.keys())[-1], streak))

tuw = days_uw / total_days * 100
print(f"\n=== TUW ANALYSIS ===")
print(f"TUW: {tuw:.1f}% ({days_uw}/{total_days} days)")
print(f"Max streak: {max_streak} days")
print(f"Kill Gate (<=65%): {'PASS' if tuw <= 65 else 'FAIL'}")

tuw_periods.sort(key=lambda x: x[2], reverse=True)
print("\nLongest underwater periods:")
for s, e, d in tuw_periods[:5]:
    print(f"  {s} to {e}: {d} days")

# Monthly trades
print(f"\n=== MONTHLY TRADES ===")
monthly = defaultdict(int)
for t in trades:
    m = t["close_date"][:7]
    monthly[m] += 1

for m in sorted(monthly.keys()):
    flag = " <-- LOW" if monthly[m] < 6 else ""
    print(f"  {m}: {monthly[m]} trades{flag}")

num_months = len(monthly)
total_t = sum(monthly.values())
avg = total_t / num_months if num_months > 0 else 0
print(f"\nAvg trades/month: {avg:.1f} ({total_t}/{num_months})")
print(f"Kill Gate (>=6): {'PASS' if avg >= 6 else 'FAIL'}")

# DD analysis
print(f"\n=== DRAWDOWN ===")
running_peak = 10000
max_dd = 0
max_dd_date = None
for dt, eq in equity_curve:
    if eq > running_peak:
        running_peak = eq
    dd = (eq - running_peak) / running_peak * 100 if running_peak > 0 else 0
    if dd < max_dd:
        max_dd = dd
        max_dd_date = dt

print(f"Max DD: {max_dd:.1f}% on {max_dd_date.date() if max_dd_date else 'N/A'}")
