"""
Portfolio Combination Analysis
CMR-V2.0 + TP-V1.2 + Squeeze V4.0b

Estimates combined portfolio metrics assuming low/moderate correlation
between mean-reversion (CMR), trend-pullback (TP), and squeeze (SQZ) strategies.
"""

import math

# ==========================================
# Individual Strategy Metrics (Full Period 2020-2024)
# ==========================================

strategies = {
    "CMR-V2.0": {
        "desc": "Commodity Cross Mean Reversion",
        "cagr_full": 6.78,      # % full period
        "cagr_is": 7.04,        # % IS 2020-2022
        "cagr_oos": 5.98,       # % OOS 2023-2024
        "dd_full": 9.2,         # % max DD
        "dd_is": 9.2,
        "dd_oos": 6.8,
        "pl_full": 1.47,
        "pl_oos": 1.69,
        "trades_annual": 96,    # 480/5
        "wr_full": 49,
        "status": "CANDIDATE_PAPER (OOS VALIDATED)",
        "regime": "range/choppy",  # works better in ranging markets
        "pairs": ["AUDCAD", "NZDCAD", "AUDNZD", "EURGBP"],
    },
    "TP-V1.2": {
        "desc": "Trend Pullback",
        "cagr_full": 3.04,      # % full period
        "cagr_is": 0.72,        # % IS 2020-2022
        "cagr_oos": 6.59,       # % OOS 2023-2024
        "dd_full": 14.3,
        "dd_is": 14.3,
        "dd_oos": 4.0,
        "pl_full": 1.68,
        "pl_oos": 1.79,
        "trades_annual": 56,    # 282/5
        "wr_full": 45,
        "status": "CANDIDATE_PAPER (OOS >> IS, regime-dependent)",
        "regime": "trending",   # works better in trending markets
        "pairs": ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "NZDUSD", "USDCAD"],
    },
    "SQZ-V4.0b": {
        "desc": "Volatility Squeeze",
        "cagr_full": 1.24,      # ~6.32%/5yr
        "dd_full": 8.8,
        "pl_full": 1.07,
        "trades_annual": 20,    # 104/5
        "wr_full": None,        # not recorded
        "status": "MARGINAL (low trade frequency, low CAGR)",
        "regime": "expansion",  # volatility expansion after squeeze
        "pairs": ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "NZDUSD", "USDCAD"],
    }
}

print("=" * 70)
print("  PORTFOLIO COMBINATION ANALYSIS — Brain V9 Forex")
print("  Capital: $10,000 | Aspiration: $1K/week compound")
print("=" * 70)

# ==========================================
# Individual Strategy Summary
# ==========================================
print("\n--- Individual Strategies ---\n")
for name, s in strategies.items():
    calmar = s["cagr_full"] / s["dd_full"] if s["dd_full"] > 0 else 0
    print(f"  {name}: {s['desc']}")
    print(f"    CAGR: {s['cagr_full']:.2f}% | DD: {s['dd_full']:.1f}% | P/L: {s['pl_full']:.2f} | Calmar: {calmar:.2f}")
    print(f"    Trades/yr: {s['trades_annual']} | Regime: {s['regime']}")
    print(f"    Status: {s['status']}")
    print()

# ==========================================
# Correlation Analysis
# ==========================================
print("--- Correlation Estimation ---\n")
print("  CMR vs TP:")
print("    - CMR trades commodity crosses (AUDCAD, NZDCAD, AUDNZD, EURGBP)")
print("    - TP trades majors (EURUSD, GBPUSD, USDJPY, AUDUSD, NZDUSD, USDCAD)")
print("    - Overlap: AUDUSD/NZDUSD in TP contain AUD/NZD from CMR pairs")
print("    - But: MR vs Trend = structurally OPPOSITE signals")
print("    - Regime: CMR works in range, TP works in trend = COMPLEMENTARY")
print("    - Estimated correlation: -0.10 to +0.20 (LOW)")
print()
print("  CMR vs SQZ:")
print("    - Different pairs, different logic")
print("    - SQZ is expansion-based, CMR is reversion-based")
print("    - Estimated correlation: ~0.00 to +0.15 (VERY LOW)")
print()
print("  TP vs SQZ:")
print("    - SAME pairs, both trend-oriented")
print("    - Estimated correlation: +0.30 to +0.50 (MODERATE)")
print()

# ==========================================
# Portfolio Combination Estimates
# ==========================================

# Using simple portfolio math:
# Portfolio CAGR ≈ weighted average of CAGRs
# Portfolio DD ≈ sqrt(sum(wi^2 * DDi^2) + 2*sum(wi*wj*rho*DDi*DDj))
# This is approximate since DD != volatility, but gives directional estimate

def portfolio_dd(weights, dds, corr_matrix):
    """Estimate portfolio DD using correlation-adjusted formula"""
    n = len(weights)
    var = 0
    for i in range(n):
        for j in range(n):
            var += weights[i] * weights[j] * dds[i] * dds[j] * corr_matrix[i][j]
    return math.sqrt(var)

def portfolio_cagr(weights, cagrs):
    return sum(w * c for w, c in zip(weights, cagrs))

# Scenarios
print("--- Portfolio Scenarios ---\n")

scenarios = [
    {
        "name": "A) CMR-V2.0 only (current champion)",
        "weights": [1.0, 0.0, 0.0],
    },
    {
        "name": "B) CMR + TP equal weight (50/50)",
        "weights": [0.50, 0.50, 0.0],
    },
    {
        "name": "C) CMR 60% + TP 40% (CMR-heavy)",
        "weights": [0.60, 0.40, 0.0],
    },
    {
        "name": "D) CMR 70% + TP 30% (conservative)",
        "weights": [0.70, 0.30, 0.0],
    },
    {
        "name": "E) CMR 50% + TP 35% + SQZ 15% (three-strategy)",
        "weights": [0.50, 0.35, 0.15],
    },
    {
        "name": "F) CMR 55% + TP 45% (no SQZ, it's marginal)",
        "weights": [0.55, 0.45, 0.0],
    },
]

cagrs = [6.78, 3.04, 1.24]
dds = [9.2, 14.3, 8.8]

# Correlation matrix [CMR, TP, SQZ]
# Using conservative (higher) correlation estimates
corr = [
    [1.00, 0.15, 0.05],
    [0.15, 1.00, 0.40],
    [0.05, 0.40, 1.00],
]

print(f"  {'Scenario':<55} {'CAGR':>6} {'Est.DD':>7} {'Calmar':>7} {'$/yr':>8}")
print(f"  {'-'*55} {'-'*6} {'-'*7} {'-'*7} {'-'*8}")

for sc in scenarios:
    w = sc["weights"]
    cagr = portfolio_cagr(w, cagrs)
    dd = portfolio_dd(w, dds, corr)
    calmar = cagr / dd if dd > 0 else 0
    annual_dollar = 10000 * cagr / 100
    print(f"  {sc['name']:<55} {cagr:>5.2f}% {dd:>6.1f}% {calmar:>6.2f}  ${annual_dollar:>6.0f}")

# ==========================================
# Path to $1K/week Analysis
# ==========================================
print("\n--- Path to Aspirational Goal ($1K/week = $52K/year) ---\n")

target_annual = 52000
capital = 10000

# With compound growth, need CAGR such that capital * (1 + CAGR)^t = capital + target
# For year 1: need 520% return — IMPOSSIBLE with current strategies
# But compound growth + growing capital base:

print("  Current reality check:")
print(f"    $1K/week on $10K = 520% annual return needed")
print(f"    Best combined CAGR estimate: ~5-7%")
print(f"    Year 1 realistic income: $500-$700")
print()
print("  Compound growth trajectory (CMR+TP combined, ~5.5% CAGR):")

cagr_estimate = 0.055
balance = capital
for year in range(1, 11):
    balance *= (1 + cagr_estimate)
    annual_income = balance * cagr_estimate
    weekly_income = annual_income / 52
    print(f"    Year {year:>2}: Balance ${balance:>10,.0f} | Annual ${annual_income:>8,.0f} | Weekly ${weekly_income:>6,.0f}")

print()
print("  HONEST ASSESSMENT:")
print("  - With $10K and ~5.5% CAGR, $1K/week is NOT achievable in 1-5 years")
print("  - Two realistic paths forward:")
print("    1. SCALE CAPITAL: At $200K capital and 5.5% CAGR -> ~$212/week")
print("       At $500K capital and 5.5% CAGR -> ~$529/week")
print("       At $1M capital and 5.5% CAGR -> ~$1,058/week <-- TARGET MET")
print("    2. INCREASE EDGE: Need more strategies, higher CAGR per strategy")
print("       At 15% CAGR on $200K -> ~$577/week")
print("       At 25% CAGR on $200K -> ~$962/week")
print()
print("  RECOMMENDED PATH:")
print("  - Deploy CMR-V2.0 + TP-V1.2 to paper NOW")
print("  - Continue developing new strategy families in parallel")
print("  - Validate paper performance for 2-4 weeks")
print("  - Scale capital when live validation confirms edge")

# ==========================================
# Risk Budget for Combined Portfolio
# ==========================================
print("\n--- Recommended Portfolio Allocation (Scenario C: CMR 60% + TP 40%) ---\n")
print("  CMR-V2.0 (60% allocation):")
print("    risk_per_trade: 0.03 * 0.60 = 0.018 (1.8%)")
print("    max_daily_risk: 0.04 * 0.60 = 0.024")
print("    max_weekly_risk: 0.06 * 0.60 = 0.036")
print()
print("  TP-V1.2 (40% allocation):")
print("    risk_per_trade: 0.015 * 0.40 = 0.006 (0.6%)")
print("    max_daily_risk: 0.03 * 0.40 = 0.012")
print("    max_weekly_risk: N/A (no weekly limit in TP)")
print()
print("  ALTERNATIVE (simpler): Run both at full risk, accept combined DD")
print("    Combined max DD estimate: ~12-15%")
print("    Combined CAGR estimate: ~5-7%")
print("    This is simpler and uses the natural low correlation as diversification")
print("    RECOMMENDED: Start with this approach on paper, measure actual correlation")

print("\n" + "=" * 70)
print("  CONCLUSION: Deploy CMR-V2.0 + TP-V1.2 to paper trading")
print("  Both strategies are CANDIDATE_PAPER. Deploy simultaneously.")
print("  Squeeze V4.0b: EXCLUDE (marginal CAGR, low trade count)")
print("=" * 70)
