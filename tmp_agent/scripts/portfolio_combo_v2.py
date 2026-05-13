"""
Portfolio Combination Analysis V2
MA-TF V1.2 OOS (2021-2024) + CMR-V2.0 OOS (2023-2024)

Extracts monthly returns from QC backtest JSON rolling windows,
calculates real correlation, and evaluates combined portfolio
against Contract §3.1 gates.
"""

import json
import math
import re
import sys

# ===========================================
# Load backtest results
# ===========================================

def load_json(path):
    with open(path, 'r') as f:
        return json.load(f)

matf_path = "C:/AI_VAULT/tmp_agent/strategies/multi_asset_tf/backtest_results.json"
cmr_path = "C:/AI_VAULT/tmp_agent/strategies/commodity_mr/backtest_results.json"

matf = load_json(matf_path)
cmr = load_json(cmr_path)

# ===========================================
# Extract monthly returns from rollingWindow
# ===========================================

def extract_monthly_returns(bt_data):
    """
    Extract monthly returns from M1_ keys in rollingWindow.
    Returns dict: {YYYYMM: monthly_return_pct}
    """
    rw = bt_data.get("rollingWindow", {})
    monthly = {}
    
    for key, val in rw.items():
        # Only M1_ keys (1-month windows)
        if not key.startswith("M1_"):
            continue
        
        date_str = key[3:]  # e.g., "20210131"
        year = int(date_str[:4])
        month = int(date_str[4:6])
        ym = f"{year}{month:02d}"
        
        ps = val.get("portfolioStatistics", {})
        start_eq = float(ps.get("startEquity", 0))
        end_eq = float(ps.get("endEquity", 0))
        
        if start_eq > 0:
            ret_pct = (end_eq - start_eq) / start_eq * 100
        else:
            ret_pct = 0.0
        
        monthly[ym] = ret_pct
    
    return monthly

matf_monthly = extract_monthly_returns(matf)
cmr_monthly = extract_monthly_returns(cmr)

# Sort keys
matf_months = sorted(matf_monthly.keys())
cmr_months = sorted(cmr_monthly.keys())

print("=" * 70)
print("  PORTFOLIO COMBINATION ANALYSIS V2")
print("  MA-TF V1.2 OOS + CMR-V2.0 OOS")
print("=" * 70)

print(f"\n  MA-TF V1.2 OOS: {len(matf_months)} months ({matf_months[0]} to {matf_months[-1]})")
print(f"  CMR-V2.0 OOS:   {len(cmr_months)} months ({cmr_months[0]} to {cmr_months[-1]})")

# ===========================================
# Find overlap period
# ===========================================

overlap_months = sorted(set(matf_months) & set(cmr_months))
print(f"  Overlap:         {len(overlap_months)} months ({overlap_months[0]} to {overlap_months[-1]})")

# ===========================================
# Individual strategy metrics (full OOS periods)
# ===========================================

def calc_metrics(returns_list, label, period_years):
    """Calculate key metrics from monthly returns list"""
    n = len(returns_list)
    if n == 0:
        return {}
    
    total_ret = 1.0
    for r in returns_list:
        total_ret *= (1 + r / 100)
    
    total_pct = (total_ret - 1) * 100
    cagr = (total_ret ** (1.0 / period_years) - 1) * 100 if period_years > 0 else 0
    
    # Monthly stats
    avg_monthly = sum(returns_list) / n
    if n > 1:
        variance = sum((r - avg_monthly) ** 2 for r in returns_list) / (n - 1)
        std_monthly = math.sqrt(variance)
    else:
        std_monthly = 0
    
    # Annualized
    std_annual = std_monthly * math.sqrt(12)
    
    # Sharpe (annualized from monthly)
    sharpe = (avg_monthly * 12) / std_annual if std_annual > 0 else 0
    
    # Max drawdown (from monthly equity curve)
    equity = [10000]
    for r in returns_list:
        equity.append(equity[-1] * (1 + r / 100))
    
    peak = equity[0]
    max_dd = 0
    dd_start = 0
    max_tuw = 0
    current_tuw = 0
    
    for i, eq in enumerate(equity):
        if eq > peak:
            peak = eq
            if current_tuw > max_tuw:
                max_tuw = current_tuw
            current_tuw = 0
        else:
            dd = (peak - eq) / peak * 100
            if dd > max_dd:
                max_dd = dd
            current_tuw += 1
    
    if current_tuw > max_tuw:
        max_tuw = current_tuw
    
    # Max daily DD approximation (worst month)
    worst_month = min(returns_list)
    
    # Return/MaxDD
    ret_dd = total_pct / max_dd if max_dd > 0 else 0
    
    # Positive months
    pos_months = sum(1 for r in returns_list if r > 0)
    pos_pct = pos_months / n * 100
    
    # Trades per month (from trade stats - not available here, skip)
    
    # Best day as % of positive P&L (approximate as best month / total positive months)
    pos_returns = [r for r in returns_list if r > 0]
    total_pos = sum(pos_returns)
    best_month = max(returns_list) if returns_list else 0
    best_day_pct = (best_month / total_pos * 100) if total_pos > 0 else 0
    
    # TUW as % of period
    tuw_pct = max_tuw / n * 100 if n > 0 else 0
    
    return {
        "label": label,
        "months": n,
        "total_ret": total_pct,
        "cagr": cagr,
        "max_dd": max_dd,
        "sharpe_est": sharpe,
        "ret_dd": ret_dd,
        "worst_month": worst_month,
        "best_month": best_month,
        "avg_monthly": avg_monthly,
        "std_monthly": std_monthly,
        "pos_months_pct": pos_pct,
        "tuw_pct": tuw_pct,
        "best_day_pct": best_day_pct,
        "equity": equity,
        "returns": returns_list,
    }

# Full period metrics
matf_oos_returns = [matf_monthly[m] for m in matf_months]
cmr_oos_returns = [cmr_monthly[m] for m in cmr_months]

matf_metrics = calc_metrics(matf_oos_returns, "MA-TF V1.2 OOS (2021-2024)", 4.0)
cmr_metrics = calc_metrics(cmr_oos_returns, "CMR-V2.0 OOS (2023-2024)", 2.0)

def print_metrics(m):
    print(f"\n  {m['label']}:")
    print(f"    Months:        {m['months']}")
    print(f"    Total Return:  {m['total_ret']:+.2f}%")
    print(f"    CAGR:          {m['cagr']:+.2f}%")
    print(f"    Max DD:        {m['max_dd']:.2f}%")
    print(f"    Est. Sharpe:   {m['sharpe_est']:.3f}")
    print(f"    Return/DD:     {m['ret_dd']:.2f}")
    print(f"    Avg Monthly:   {m['avg_monthly']:+.3f}%")
    print(f"    Std Monthly:   {m['std_monthly']:.3f}%")
    print(f"    Worst Month:   {m['worst_month']:+.2f}%")
    print(f"    Best Month:    {m['best_month']:+.2f}%")
    print(f"    Positive Mos:  {m['pos_months_pct']:.0f}%")
    print(f"    TUW (months):  {m['tuw_pct']:.0f}%")

print("\n--- Individual Strategy Metrics ---")
print_metrics(matf_metrics)
print_metrics(cmr_metrics)

# ===========================================
# Correlation Analysis (overlap period only)
# ===========================================

matf_overlap = [matf_monthly[m] for m in overlap_months]
cmr_overlap = [cmr_monthly[m] for m in overlap_months]

n_overlap = len(overlap_months)
mean_matf = sum(matf_overlap) / n_overlap
mean_cmr = sum(cmr_overlap) / n_overlap

cov = sum((matf_overlap[i] - mean_matf) * (cmr_overlap[i] - mean_cmr) for i in range(n_overlap)) / (n_overlap - 1)
var_matf = sum((x - mean_matf) ** 2 for x in matf_overlap) / (n_overlap - 1)
var_cmr = sum((x - mean_cmr) ** 2 for x in cmr_overlap) / (n_overlap - 1)

correlation = cov / (math.sqrt(var_matf) * math.sqrt(var_cmr)) if var_matf > 0 and var_cmr > 0 else 0

print("\n\n--- Correlation Analysis (Overlap: 2023-2024) ---")
print(f"  Months in overlap: {n_overlap}")
print(f"  MA-TF V1.2 mean:  {mean_matf:+.3f}%/mo")
print(f"  CMR-V2.0 mean:    {mean_cmr:+.3f}%/mo")
print(f"  Covariance:        {cov:.4f}")
print(f"  CORRELATION:       {correlation:+.3f}")

if abs(correlation) < 0.2:
    print(f"  -> LOW correlation — decorrelation benefit expected")
elif abs(correlation) < 0.5:
    print(f"  -> MODERATE correlation — some decorrelation benefit")
else:
    print(f"  -> HIGH correlation — limited decorrelation benefit")

# Show monthly comparison
print(f"\n  {'Month':<10} {'MA-TF':>8} {'CMR':>8} {'Direction':>10}")
print(f"  {'-'*10} {'-'*8} {'-'*8} {'-'*10}")
for m in overlap_months:
    matf_r = matf_monthly[m]
    cmr_r = cmr_monthly[m]
    same = "SAME" if (matf_r > 0 and cmr_r > 0) or (matf_r < 0 and cmr_r < 0) else "DIFF"
    print(f"  {m:<10} {matf_r:>+7.2f}% {cmr_r:>+7.2f}% {same:>10}")

same_count = sum(1 for m in overlap_months if (matf_monthly[m] > 0) == (cmr_monthly[m] > 0))
print(f"\n  Same direction: {same_count}/{n_overlap} ({same_count/n_overlap*100:.0f}%)")

# ===========================================
# Combined Portfolio Scenarios (overlap period)
# ===========================================

print("\n\n--- Combined Portfolio Scenarios (Overlap: 2023-2024) ---\n")

# Only analyze overlap period where both strategies have data
period_years = n_overlap / 12.0

scenarios = [
    ("MA-TF only",         1.0, 0.0),
    ("CMR only",           0.0, 1.0),
    ("50/50",              0.5, 0.5),
    ("60 CMR / 40 MA-TF",  0.4, 0.6),
    ("70 CMR / 30 MA-TF",  0.3, 0.7),
    ("80 CMR / 20 MA-TF",  0.2, 0.8),
]

print(f"  {'Scenario':<25} {'CAGR':>7} {'MaxDD':>7} {'Sharpe':>7} {'Ret/DD':>7} {'Pos%':>5} {'TUW%':>5} {'§3.1?':>6}")
print(f"  {'-'*25} {'-'*7} {'-'*7} {'-'*7} {'-'*7} {'-'*5} {'-'*5} {'-'*6}")

for name, w_matf, w_cmr in scenarios:
    combined = [w_matf * matf_overlap[i] + w_cmr * cmr_overlap[i] for i in range(n_overlap)]
    m = calc_metrics(combined, name, period_years)
    
    # §3.1 gate check
    passes_sharpe = m['sharpe_est'] > 0.5
    passes_retdd = m['ret_dd'] > 0.8
    passes_tuw = m['tuw_pct'] < 70
    passes_worst = abs(m['worst_month']) < 3.0  # proxy for daily DD
    
    gates = sum([passes_sharpe, passes_retdd, passes_tuw, passes_worst])
    gate_str = f"{gates}/4"
    if gates == 4:
        gate_str = "PASS"
    
    print(f"  {name:<25} {m['cagr']:>+6.2f}% {m['max_dd']:>6.2f}% {m['sharpe_est']:>+6.3f} {m['ret_dd']:>6.2f} {m['pos_months_pct']:>4.0f}% {m['tuw_pct']:>4.0f}% {gate_str:>6}")

# ===========================================
# Extended analysis: MA-TF full period + CMR simulated
# ===========================================

print("\n\n--- Full Period Analysis (2021-2024) ---")
print("  NOTE: CMR only has data 2023-2024, so for 2021-2022 we simulate CMR=0%")
print("  This is conservative (assumes CMR adds nothing in first 2 years)")

all_months_sorted = sorted(set(matf_months))  # 2021-2024
full_combined_returns = {}

for weight_label, w_matf, w_cmr in [("50/50", 0.5, 0.5), ("60 CMR / 40 MA-TF", 0.4, 0.6), ("70 CMR / 30 MA-TF", 0.3, 0.7)]:
    combined_rets = []
    for m in all_months_sorted:
        matf_r = matf_monthly.get(m, 0)
        cmr_r = cmr_monthly.get(m, 0)  # 0 for months where CMR has no data
        combined_rets.append(w_matf * matf_r + w_cmr * cmr_r)
    
    metrics = calc_metrics(combined_rets, f"Full 2021-2024 ({weight_label})", 4.0)
    print_metrics(metrics)

# ===========================================
# §3.1 Gate Assessment
# ===========================================

print("\n\n" + "=" * 70)
print("  §3.1 GATE ASSESSMENT — COMBINED PORTFOLIO")
print("=" * 70)

# Use best scenario from overlap period
print("\n  Best overlap scenario results:")
best_combo = [0.5 * matf_overlap[i] + 0.5 * cmr_overlap[i] for i in range(n_overlap)]
best_m = calc_metrics(best_combo, "50/50 overlap", period_years)

gates = {
    "Sharpe OOS > 0.5": (best_m['sharpe_est'], best_m['sharpe_est'] > 0.5),
    "Return/MaxDD > 0.8": (best_m['ret_dd'], best_m['ret_dd'] > 0.8),
    "TUW < 70%": (best_m['tuw_pct'], best_m['tuw_pct'] < 70),
    "Max Daily DD < 3.0%": (abs(best_m['worst_month']), abs(best_m['worst_month']) < 3.0),
}

all_pass = True
for gate, (val, passes) in gates.items():
    status = "PASS" if passes else "FAIL"
    if not passes:
        all_pass = False
    print(f"  {gate:<25} -> {val:>6.2f}  [{status}]")

print(f"\n  OVERALL: {'ALL GATES PASS' if all_pass else 'GATES FAILED — does NOT meet §3.1'}")

# ===========================================
# Verdict
# ===========================================

print("\n\n" + "=" * 70)
print("  VERDICT")
print("=" * 70)

if all_pass:
    print("\n  Portfolio combination PASSES §3.1 -> proceed to Mode B evaluation")
else:
    print("\n  Portfolio combination FAILS §3.1 gates.")
    print("  Combined with individual strategy failures:")
    print("    - MA-TF V1.2: IS Sharpe 0.462 (FAIL >0.5), OOS Sharpe -0.343 (CATASTROPHIC)")
    print("    - CMR-V2.0: FX-only, previously classified MARGINAL")
    print("    - 13 FX families: ALL DEAD")
    print("    - 7 MA iterations (6 TF + 1 MR): approaching ceiling")
    print("")
    print("  RECOMMENDATION:")
    print("    Option A: Try MA-TF V1.6 with momentum-ranked filter (last MA-TF attempt)")
    print("    Option B: Declare TECHO ESTRUCTURAL on MA-TF, pivot to Stat-Arb or Intraday")
    print("    Option C: If momentum filter also fails -> formal full ceiling declaration")

print("\n" + "=" * 70)
