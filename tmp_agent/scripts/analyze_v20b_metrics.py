"""
Analyze V2.0b backtest: TUW, monthly trade distribution, equity curve.
Uses QC API to download backtest results + chart data.
"""
import time, json, requests, sys
from hashlib import sha256
from base64 import b64encode
from datetime import datetime, timedelta
from collections import defaultdict

UID = "384945"
TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
BASE = "https://www.quantconnect.com/api/v2"
PROJECT_ID = 29490680
BT_ID = "d8d2e81ee03a062291164e48716d3977"

def headers():
    ts = str(int(time.time()))
    h = sha256(f"{TOKEN}:{ts}".encode()).hexdigest()
    auth = b64encode(f"{UID}:{h}".encode()).decode()
    return {"Authorization": f"Basic {auth}", "Timestamp": ts, "Content-Type": "application/json"}

# ========================================
# 1. Get backtest results (includes charts)
# ========================================
print("=" * 60)
print("FETCHING BACKTEST RESULTS...")
print("=" * 60)

r = requests.get(
    f"{BASE}/backtests/read?projectId={PROJECT_ID}&backtestId={BT_ID}",
    headers=headers()
)
data = r.json()

if not data.get("success"):
    print(f"ERROR fetching backtest: {data}")
    sys.exit(1)

bt = data.get("backtest", data)  # Sometimes nested, sometimes not

# Save full response for inspection
with open("C:/AI_VAULT/tmp_agent/strategies/yoel_options/v20b_backtest_result.json", "w") as f:
    json.dump(data, f, indent=2, default=str)
print("Full result saved to v20b_backtest_result.json")

# ========================================
# 2. Extract equity curve from charts
# ========================================
print("\n" + "=" * 60)
print("EXTRACTING EQUITY CURVE...")
print("=" * 60)

charts = bt.get("charts", {})
strategy_eq = charts.get("Strategy Equity", {})
series = strategy_eq.get("series", {})
equity_series = series.get("Equity", {})
equity_values = equity_series.get("values", [])

print(f"Equity data points: {len(equity_values)}")

if not equity_values:
    print("No equity data found in charts. Checking alternative locations...")
    # Try to get from result directly
    print(f"Available chart keys: {list(charts.keys())}")
    if charts:
        for chart_name, chart_data in charts.items():
            print(f"  Chart '{chart_name}': series keys = {list(chart_data.get('series', {}).keys())}")
    sys.exit(1)

# Parse equity curve - QC returns timestamps as Unix epoch (seconds)
equity_curve = []
for point in equity_values:
    if isinstance(point, dict):
        ts = point.get("x", 0)
        val = point.get("y", 0)
    elif isinstance(point, (list, tuple)):
        ts, val = point[0], point[1]
    else:
        continue
    
    # QC timestamps can be in seconds or milliseconds
    if ts > 1e12:
        ts = ts / 1000  # Convert ms to seconds
    
    dt = datetime.utcfromtimestamp(ts)
    equity_curve.append((dt, val))

equity_curve.sort(key=lambda x: x[0])
print(f"Parsed {len(equity_curve)} equity points from {equity_curve[0][0].date()} to {equity_curve[-1][0].date()}")
print(f"Start equity: ${equity_curve[0][1]:,.2f}")
print(f"End equity: ${equity_curve[-1][1]:,.2f}")
print(f"Peak equity: ${max(e[1] for e in equity_curve):,.2f}")

# ========================================
# 3. Calculate TUW (Time Under Water)
# ========================================
print("\n" + "=" * 60)
print("CALCULATING TUW (Time Under Water)...")
print("=" * 60)

running_peak = 0
days_underwater = 0
total_days = 0
max_tuw_days = 0
current_tuw_streak = 0
tuw_periods = []
current_tuw_start = None

for dt, eq in equity_curve:
    total_days += 1
    
    if eq >= running_peak:
        # At or above peak = NOT underwater
        if current_tuw_streak > 0:
            tuw_periods.append((current_tuw_start, dt, current_tuw_streak))
        running_peak = eq
        current_tuw_streak = 0
        current_tuw_start = None
    else:
        # Below peak = underwater
        days_underwater += 1
        current_tuw_streak += 1
        if current_tuw_start is None:
            current_tuw_start = dt
        max_tuw_days = max(max_tuw_days, current_tuw_streak)

# If still underwater at end
if current_tuw_streak > 0:
    tuw_periods.append((current_tuw_start, equity_curve[-1][0], current_tuw_streak))

tuw_pct = (days_underwater / total_days * 100) if total_days > 0 else 0

print(f"Total data points: {total_days}")
print(f"Days underwater: {days_underwater}")
print(f"TUW %: {tuw_pct:.1f}%")
print(f"Max consecutive underwater streak: {max_tuw_days} data points")
print(f"Kill Gate (TUW <= 65%): {'PASS' if tuw_pct <= 65 else 'FAIL'}")

print(f"\nLongest underwater periods:")
tuw_periods.sort(key=lambda x: x[2], reverse=True)
for start, end, days in tuw_periods[:5]:
    print(f"  {start.date()} to {end.date()}: {days} data points")

# ========================================
# 4. Get trades for monthly distribution
# ========================================
print("\n" + "=" * 60)
print("FETCHING ORDERS FOR MONTHLY DISTRIBUTION...")
print("=" * 60)

r = requests.get(
    f"{BASE}/backtests/orders?projectId={PROJECT_ID}&backtestId={BT_ID}&start=0&end=5000",
    headers=headers()
)
orders_data = r.json()

if not orders_data.get("success"):
    print(f"ERROR fetching orders: {orders_data}")
else:
    orders = orders_data.get("orders", [])
    print(f"Total orders: {len(orders)}")
    
    # Count trades per month (a "trade" = a market/limit buy order that opens a position)
    # We want ENTRY orders, which are typically BUY orders for CALL options
    monthly_trades = defaultdict(int)
    
    for order in orders:
        # Parse order time
        order_time = order.get("time", order.get("Time", ""))
        direction = order.get("direction", order.get("Direction", ""))
        order_type = order.get("type", order.get("Type", ""))
        status = order.get("status", order.get("Status", ""))
        quantity = order.get("quantity", order.get("Quantity", 0))
        symbol = order.get("symbol", order.get("Symbol", ""))
        
        # We want filled buy orders (entries)
        # In QC, direction 0 = Buy, 1 = Sell. Status 3 = Filled
        is_buy = False
        if isinstance(direction, int):
            is_buy = direction == 0
        elif isinstance(direction, str):
            is_buy = direction.lower() in ("buy", "0")
        
        if isinstance(quantity, (int, float)):
            is_buy = is_buy or quantity > 0
        
        is_filled = False
        if isinstance(status, int):
            is_filled = status == 3
        elif isinstance(status, str):
            is_filled = status.lower() in ("filled", "3")
        
        if is_buy and is_filled:
            # Parse date
            if isinstance(order_time, str):
                try:
                    dt = datetime.fromisoformat(order_time.replace("Z", "+00:00"))
                    month_key = f"{dt.year}-{dt.month:02d}"
                    monthly_trades[month_key] += 1
                except:
                    pass
    
    print(f"\n{'Month':<12} {'Trades':>8}")
    print("-" * 22)
    total_trades = 0
    months_list = sorted(monthly_trades.keys())
    months_below_6 = 0
    for m in months_list:
        count = monthly_trades[m]
        total_trades += count
        flag = " <-- BELOW 6" if count < 6 else ""
        if count < 6:
            months_below_6 += 1
        print(f"{m:<12} {count:>8}{flag}")
    
    num_months = len(months_list)
    avg_per_month = total_trades / num_months if num_months > 0 else 0
    print("-" * 22)
    print(f"{'Total':<12} {total_trades:>8}")
    print(f"{'Months':<12} {num_months:>8}")
    print(f"{'Avg/month':<12} {avg_per_month:>8.1f}")
    print(f"{'Below 6':<12} {months_below_6:>8} months")
    print(f"\nKill Gate (>= 6 trades/month avg): {'PASS' if avg_per_month >= 6 else 'FAIL'}")

# ========================================
# 5. Monthly PnL from equity curve
# ========================================
print("\n" + "=" * 60)
print("MONTHLY PnL FROM EQUITY CURVE...")
print("=" * 60)

monthly_equity = {}
for dt, eq in equity_curve:
    month_key = f"{dt.year}-{dt.month:02d}"
    monthly_equity[month_key] = eq  # Last equity value of each month

prev_eq = None
print(f"\n{'Month':<12} {'End Equity':>12} {'PnL':>10} {'PnL%':>8}")
print("-" * 45)
for m in sorted(monthly_equity.keys()):
    eq = monthly_equity[m]
    if prev_eq is not None:
        pnl = eq - prev_eq
        pnl_pct = (pnl / prev_eq * 100) if prev_eq > 0 else 0
        flag = " ***" if pnl < -500 else ""
        print(f"{m:<12} ${eq:>10,.2f} {pnl:>+10,.2f} {pnl_pct:>+7.1f}%{flag}")
    else:
        print(f"{m:<12} ${eq:>10,.2f} {'START':>10}")
    prev_eq = eq

# ========================================
# 6. Drawdown analysis
# ========================================
print("\n" + "=" * 60)
print("DRAWDOWN ANALYSIS...")
print("=" * 60)

running_peak = 0
max_dd = 0
max_dd_date = None
dd_series = []

for dt, eq in equity_curve:
    if eq > running_peak:
        running_peak = eq
    dd = (eq - running_peak) / running_peak * 100 if running_peak > 0 else 0
    dd_series.append((dt, dd, eq, running_peak))
    if dd < max_dd:
        max_dd = dd
        max_dd_date = dt

print(f"Max Drawdown: {max_dd:.2f}% on {max_dd_date.date() if max_dd_date else 'N/A'}")
print(f"Peak at max DD: ${dd_series[0][3]:,.2f}" if dd_series else "No data")

# Find the peak before max DD
for dt, dd, eq, peak in dd_series:
    if dt == max_dd_date:
        print(f"At max DD: equity=${eq:,.2f}, peak=${peak:,.2f}")
        break

# Worst DD periods
print("\nDrawdown periods > 10%:")
in_dd = False
dd_start = None
dd_peak = 0
for dt, dd, eq, peak in dd_series:
    if dd < -10 and not in_dd:
        in_dd = True
        dd_start = dt
        dd_peak = peak
    elif dd >= 0 and in_dd:
        in_dd = False
        print(f"  {dd_start.date()} to {dt.date()}: peak=${dd_peak:,.2f}")

if in_dd:
    print(f"  {dd_start.date()} to END (still underwater): peak=${dd_peak:,.2f}")

print("\n" + "=" * 60)
print("ANALYSIS COMPLETE")
print("=" * 60)
