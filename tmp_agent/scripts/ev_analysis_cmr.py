"""
Monte Carlo EV Analysis for CMR-V2.0 Funding Adaptation
Per Contract §10 — MANDATORY before any GO decision

Uses actual OOS trade data from CMR-V2.0 (2023-2024) to simulate
challenge outcomes under FundedNext Stellar $200K rules.
"""

import json
import math
import random

# ===========================================
# Load CMR-V2.0 OOS trade data
# ===========================================

def load_json(path):
    with open(path, 'r') as f:
        return json.load(f)

cmr_path = "C:/AI_VAULT/tmp_agent/strategies/commodity_mr/backtest_results.json"
cmr = load_json(cmr_path)

# Extract closed trades from totalPerformance
trades = cmr.get("totalPerformance", {}).get("closedTrades", [])
print(f"Total closed trades in OOS: {len(trades)}")

# Extract monthly returns for equity curve analysis
rw = cmr.get("rollingWindow", {})
monthly_returns = {}
for key, val in rw.items():
    if not key.startswith("M1_"):
        continue
    date_str = key[3:]
    year = int(date_str[:4])
    month = int(date_str[4:6])
    ym = f"{year}{month:02d}"
    ps = val.get("portfolioStatistics", {})
    start_eq = float(ps.get("startEquity", 0))
    end_eq = float(ps.get("endEquity", 0))
    if start_eq > 0:
        monthly_returns[ym] = (end_eq - start_eq) / start_eq
    else:
        monthly_returns[ym] = 0.0

months_sorted = sorted(monthly_returns.keys())
print(f"Monthly periods: {len(months_sorted)} ({months_sorted[0]} to {months_sorted[-1]})")

# Extract per-trade P&L
trade_pnls = []
for t in trades:
    pnl = float(t.get("profitLoss", 0))
    trade_pnls.append(pnl)

print(f"Trades with P&L data: {len(trade_pnls)}")
if trade_pnls:
    print(f"  Avg P&L: ${sum(trade_pnls)/len(trade_pnls):.2f}")
    print(f"  Win rate: {sum(1 for p in trade_pnls if p > 0)/len(trade_pnls)*100:.1f}%")
    print(f"  Total P&L: ${sum(trade_pnls):.2f}")

# ===========================================
# Extract daily returns from monthly data
# Approximate: distribute monthly return across ~21 trading days
# ===========================================

# Better approach: use monthly returns directly for Monte Carlo
monthly_rets_list = [monthly_returns[m] for m in months_sorted]

print(f"\nMonthly returns:")
for m in months_sorted:
    print(f"  {m}: {monthly_returns[m]*100:+.2f}%")

# ===========================================
# Strategy metrics at current risk level (3% per trade)
# ===========================================

print("\n" + "=" * 70)
print("  CMR-V2.0 OOS METRICS AT CURRENT RISK (3% per trade)")
print("=" * 70)

# From portfolio analysis V2
total_ret = 1.0
for r in monthly_rets_list:
    total_ret *= (1 + r)
total_pct = (total_ret - 1) * 100
cagr = (total_ret ** (1.0 / 2.0) - 1) * 100  # 2 years

avg_monthly = sum(monthly_rets_list) / len(monthly_rets_list) * 100
n = len(monthly_rets_list)
std_monthly = math.sqrt(sum((r*100 - avg_monthly)**2 for r in monthly_rets_list) / (n-1))

# Max DD from equity curve
equity_curve = [10000]
for r in monthly_rets_list:
    equity_curve.append(equity_curve[-1] * (1 + r))

peak = equity_curve[0]
max_dd = 0
for eq in equity_curve:
    if eq > peak:
        peak = eq
    dd = (peak - eq) / peak
    if dd > max_dd:
        max_dd = dd

sharpe_est = (avg_monthly * 12) / (std_monthly * math.sqrt(12)) if std_monthly > 0 else 0

print(f"  CAGR:          {cagr:.2f}%")
print(f"  Total Return:  {total_pct:.2f}% (2 years)")
print(f"  Max DD:        {max_dd*100:.2f}%")
print(f"  Sharpe (est):  {sharpe_est:.3f}")
print(f"  Avg Monthly:   {avg_monthly:.3f}%")
print(f"  Std Monthly:   {std_monthly:.3f}%")

# ===========================================
# FundedNext Stellar $200K Parameters
# ===========================================

print("\n" + "=" * 70)
print("  FUNDEDNEXT STELLAR $200K — CHALLENGE PARAMETERS")
print("=" * 70)

CAPITAL = 200000
PHASE1_TARGET = 0.08  # 8%
PHASE2_TARGET = 0.05  # 5%
DAILY_DD_LIMIT = 0.05  # 5% (firm limit)
TOTAL_DD_LIMIT = 0.10  # 10% (firm limit)
INTERNAL_DAILY_DD = 0.02  # 2.0% internal limit
INTERNAL_TOTAL_DD = 0.06  # 6% internal limit
PHASE1_DAYS = 60  # max calendar days Phase 1
PHASE2_DAYS = 60  # max calendar days Phase 2
FEE = 999  # FundedNext Stellar $200K fee (approximate)
PROFIT_SPLIT = 0.80  # 80% profit split once funded

print(f"  Capital:           ${CAPITAL:,}")
print(f"  Phase 1 target:    {PHASE1_TARGET*100}% (${CAPITAL*PHASE1_TARGET:,.0f})")
print(f"  Phase 2 target:    {PHASE2_TARGET*100}% (${CAPITAL*PHASE2_TARGET:,.0f})")
print(f"  Daily DD limit:    {DAILY_DD_LIMIT*100}% (firm) / {INTERNAL_DAILY_DD*100}% (internal)")
print(f"  Total DD limit:    {TOTAL_DD_LIMIT*100}% (firm) / {INTERNAL_TOTAL_DD*100}% (internal)")
print(f"  Challenge fee:     ${FEE}")
print(f"  Profit split:      {PROFIT_SPLIT*100}%")

# ===========================================
# Risk Scaling Analysis
# ===========================================

print("\n" + "=" * 70)
print("  RISK SCALING — CURRENT 3% vs ADAPTED LEVELS")
print("=" * 70)

# Current OOS: 3% risk per trade on $10K
# On $200K with same 3%: same % returns apply
# But we need internal daily DD < 2% and total DD < 6%

# Current max DD was 4.83% on 3% risk
# If we scale to X% risk: DD scales proportionally (approximately)
# To get total DD < 6%: 3% * (6/4.83) = 3.73% — so 3% is OK for total DD

# For daily DD < 2%: need to check worst daily loss
# Worst month was -2.73% => worst day likely worse
# With 3% risk, max 3 positions, worst case: 3 * 2.5 ATR stop = 7.5% risk
# But that's position-level, not daily level

# Let's analyze different risk levels
risk_levels = [0.01, 0.015, 0.02, 0.025, 0.03]

print(f"\n  Risk scaling (proportional to current 3% OOS performance):")
print(f"  {'Risk/Trade':>12} {'Est CAGR':>10} {'Est MaxDD':>10} {'Est Sharpe':>12} {'Daily DD fit':>14} {'Total DD fit':>14}")
print(f"  {'-'*12} {'-'*10} {'-'*10} {'-'*12} {'-'*14} {'-'*14}")

for risk in risk_levels:
    scale = risk / 0.03  # Scale factor vs current 3%
    scaled_cagr = cagr * scale
    scaled_dd = max_dd * 100 * scale
    # Sharpe doesn't change with leverage (in theory)
    scaled_sharpe = sharpe_est
    daily_dd_ok = "OK" if (scaled_dd / 20) < INTERNAL_DAILY_DD * 100 else "RISK"  # rough daily estimate
    total_dd_ok = "OK" if scaled_dd < INTERNAL_TOTAL_DD * 100 else "FAIL"
    
    print(f"  {risk*100:>10.1f}% {scaled_cagr:>9.2f}% {scaled_dd:>9.2f}% {scaled_sharpe:>11.3f} {daily_dd_ok:>14} {total_dd_ok:>14}")

# ===========================================
# Monte Carlo Simulation — §10
# ===========================================

print("\n" + "=" * 70)
print("  MONTE CARLO SIMULATION — §10")
print("  10,000 runs per scenario")
print("=" * 70)

random.seed(42)
N_SIMS = 10000

def simulate_challenge(monthly_rets, capital, phase_target, max_months, 
                       daily_dd_limit, total_dd_limit, risk_scale=1.0):
    """
    Simulate a single challenge phase using bootstrapped monthly returns.
    Returns: (passed, final_equity, hit_dd_limit, months_used)
    """
    equity = capital
    peak_equity = capital
    start_equity = capital
    target = capital * (1 + phase_target)
    
    for month in range(max_months):
        # Bootstrap a monthly return, scaled by risk factor
        r = random.choice(monthly_rets) * risk_scale
        
        equity *= (1 + r)
        
        # Check total DD (from starting balance, not peak - FundedNext uses balance-based)
        total_dd = (start_equity - equity) / start_equity
        if total_dd >= total_dd_limit:
            return False, equity, True, month + 1
        
        # Track peak for internal monitoring
        if equity > peak_equity:
            peak_equity = equity
        
        # Check if target reached
        if equity >= target:
            return True, equity, False, month + 1
    
    # Time expired
    return False, equity, False, max_months


def run_monte_carlo(monthly_rets, risk_scale, label):
    """Run full 2-phase challenge simulation N_SIMS times."""
    phase1_passes = 0
    phase2_passes = 0
    full_passes = 0
    dd_busts = 0
    time_busts = 0
    funded_profits = []
    
    for _ in range(N_SIMS):
        # Phase 1
        passed1, eq1, dd_bust1, months1 = simulate_challenge(
            monthly_rets, CAPITAL, PHASE1_TARGET, 
            3,  # ~3 months for Phase 1 (60 days ≈ 3 trading months)
            DAILY_DD_LIMIT, INTERNAL_TOTAL_DD, risk_scale
        )
        
        if not passed1:
            if dd_bust1:
                dd_busts += 1
            else:
                time_busts += 1
            continue
        
        phase1_passes += 1
        
        # Phase 2 (start from $200K again, target 5%)
        passed2, eq2, dd_bust2, months2 = simulate_challenge(
            monthly_rets, CAPITAL, PHASE2_TARGET,
            3,  # ~3 months for Phase 2
            DAILY_DD_LIMIT, INTERNAL_TOTAL_DD, risk_scale
        )
        
        if not passed2:
            if dd_bust2:
                dd_busts += 1
            else:
                time_busts += 1
            continue
        
        phase2_passes += 1
        full_passes += 1
        
        # If funded: simulate 6 months of funded trading
        funded_equity = CAPITAL
        for m in range(6):
            r = random.choice(monthly_rets) * risk_scale
            funded_equity *= (1 + r)
            # Check DD — if hit, lose funded account
            if (CAPITAL - funded_equity) / CAPITAL >= INTERNAL_TOTAL_DD:
                funded_equity = 0
                break
        
        if funded_equity > CAPITAL:
            profit = (funded_equity - CAPITAL) * PROFIT_SPLIT
            funded_profits.append(profit)
        elif funded_equity > 0:
            funded_profits.append(0)
        else:
            funded_profits.append(-CAPITAL * 0.1)  # Lost account
    
    p_pass = full_passes / N_SIMS
    p_phase1 = phase1_passes / N_SIMS
    
    # EV calculation
    # Cost per attempt: fee
    # Expected gain per attempt: P_pass * E[funded_profit] - fee
    avg_funded_profit = sum(funded_profits) / len(funded_profits) if funded_profits else 0
    ev_per_attempt = p_pass * avg_funded_profit - FEE
    
    # How many attempts needed on average to pass
    attempts_to_pass = 1 / p_pass if p_pass > 0 else float('inf')
    total_fee_burn = attempts_to_pass * FEE
    
    # VEN = E[profit once funded] - total_fee_burn
    ven = avg_funded_profit - total_fee_burn if p_pass > 0 else -FEE
    
    # Monte Carlo P(VEN>0) - simplified
    ven_positive_count = 0
    for _ in range(1000):
        # Simulate: how many attempts to pass, then funded profit
        attempts = 0
        passed = False
        total_fees = 0
        while attempts < 10 and not passed:
            attempts += 1
            total_fees += FEE
            p1, _, _, _ = simulate_challenge(monthly_rets, CAPITAL, PHASE1_TARGET, 3, 
                                              DAILY_DD_LIMIT, INTERNAL_TOTAL_DD, risk_scale)
            if p1:
                p2, _, _, _ = simulate_challenge(monthly_rets, CAPITAL, PHASE2_TARGET, 3,
                                                  DAILY_DD_LIMIT, INTERNAL_TOTAL_DD, risk_scale)
                if p2:
                    passed = True
        
        if passed:
            # Simulate funded period
            f_eq = CAPITAL
            for m in range(12):  # 12 months funded
                r = random.choice(monthly_rets) * risk_scale
                f_eq *= (1 + r)
                if (CAPITAL - f_eq) / CAPITAL >= INTERNAL_TOTAL_DD:
                    f_eq = 0
                    break
            if f_eq > CAPITAL:
                net_gain = (f_eq - CAPITAL) * PROFIT_SPLIT - total_fees
            else:
                net_gain = -total_fees
        else:
            net_gain = -total_fees
        
        if net_gain > 0:
            ven_positive_count += 1
    
    p_ven_positive = ven_positive_count / 1000
    
    return {
        "label": label,
        "risk_scale": risk_scale,
        "p_phase1": p_phase1,
        "p_pass": p_pass,
        "dd_busts": dd_busts / N_SIMS,
        "time_busts": time_busts / N_SIMS,
        "avg_funded_profit": avg_funded_profit,
        "ev_per_attempt": ev_per_attempt,
        "attempts_to_pass": attempts_to_pass,
        "total_fee_burn": total_fee_burn,
        "ven": ven,
        "p_ven_positive": p_ven_positive,
    }

# Run simulations at different risk levels
# risk_scale = 1.0 means same risk as OOS (3% per trade)
# risk_scale = 0.5 means 1.5% per trade
# risk_scale = 0.67 means 2% per trade

scenarios = [
    (1.0, "3.0% risk (current)"),
    (0.83, "2.5% risk"),
    (0.67, "2.0% risk"),
    (0.50, "1.5% risk"),
    (0.33, "1.0% risk"),
]

results = []
for scale, label in scenarios:
    print(f"\n  Simulating: {label}...")
    r = run_monte_carlo(monthly_rets_list, scale, label)
    results.append(r)

# ===========================================
# Results Table
# ===========================================

print("\n\n" + "=" * 70)
print("  MONTE CARLO RESULTS — FundedNext Stellar $200K")
print("=" * 70)

print(f"\n  {'Scenario':<22} {'P_phase1':>9} {'P_pass':>8} {'DD bust':>8} {'Time out':>9} {'Avg Profit':>11} {'EV/attempt':>11} {'Att->Pass':>10} {'Fee Burn':>9} {'VEN':>10} {'P(VEN>0)':>9}")
print(f"  {'-'*22} {'-'*9} {'-'*8} {'-'*8} {'-'*9} {'-'*11} {'-'*11} {'-'*10} {'-'*9} {'-'*10} {'-'*9}")

for r in results:
    print(f"  {r['label']:<22} {r['p_phase1']:>8.1%} {r['p_pass']:>7.1%} {r['dd_busts']:>7.1%} {r['time_busts']:>8.1%} ${r['avg_funded_profit']:>9,.0f} ${r['ev_per_attempt']:>9,.0f} {r['attempts_to_pass']:>9.1f} ${r['total_fee_burn']:>8,.0f} ${r['ven']:>9,.0f} {r['p_ven_positive']:>8.1%}")

# ===========================================
# §10.2 Tier Classification
# ===========================================

print("\n\n" + "=" * 70)
print("  §10.2 / §10.3 TIER CLASSIFICATION")
print("=" * 70)

for r in results:
    p_pass = r['p_pass']
    p_ven = r['p_ven_positive']
    
    # §10.2 P_pass tiers
    if p_pass >= 0.40:
        pass_tier = "STRONG CANDIDATE"
    elif p_pass >= 0.25:
        pass_tier = "MODERATE CANDIDATE"
    elif p_pass >= 0.15:
        pass_tier = "MARGINAL — conditional"
    else:
        pass_tier = "REJECT"
    
    # §10.3 VEN tiers
    if p_ven >= 0.70:
        ven_tier = "GO STRONG"
    elif p_ven >= 0.60:
        ven_tier = "GO CONDITIONAL"
    elif p_ven >= 0.50:
        ven_tier = "MARGINAL"
    else:
        ven_tier = "REJECT"
    
    print(f"\n  {r['label']}:")
    print(f"    P_pass = {p_pass:.1%} -> {pass_tier}")
    print(f"    P(VEN>0) = {p_ven:.1%} -> {ven_tier}")

# ===========================================
# Recommendation
# ===========================================

print("\n\n" + "=" * 70)
print("  D9 / D10 PRELIMINARY ASSESSMENT")
print("=" * 70)

# Find best scenario
best = max(results, key=lambda r: r['p_ven_positive'])
print(f"\n  Best scenario: {best['label']}")
print(f"    P_pass:      {best['p_pass']:.1%}")
print(f"    P(VEN>0):    {best['p_ven_positive']:.1%}")
print(f"    VEN:          ${best['ven']:,.0f}")
print(f"    Fee burn:    ${best['total_fee_burn']:,.0f}")

if best['p_ven_positive'] >= 0.70:
    print(f"\n  ASSESSMENT: GO STRONG — proceed to challenge")
    exit_code = "Salida 1: CHALLENGE_CANDIDATE"
elif best['p_ven_positive'] >= 0.60:
    print(f"\n  ASSESSMENT: GO CONDITIONAL — proceed with caution")
    exit_code = "Salida 2: CHALLENGE_CANDIDATE_CONDITIONAL"
elif best['p_ven_positive'] >= 0.50:
    print(f"\n  ASSESSMENT: MARGINAL — consider paper validation first")
    exit_code = "Salida 3: EXPERIMENTAL_ATTEMPT"
elif best['p_pass'] > 0:
    print(f"\n  ASSESSMENT: INSUFFICIENT — strategy needs improvement")
    exit_code = "Salida 4: NOT_READY_ITERATE"
else:
    print(f"\n  ASSESSMENT: REJECT — strategy not viable for prop firms")
    exit_code = "Salida 5: REJECT_PIVOT"

print(f"\n  §12 Exit Classification: {exit_code}")

print("\n" + "=" * 70)
