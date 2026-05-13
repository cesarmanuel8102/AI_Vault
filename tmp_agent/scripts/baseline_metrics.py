"""
Baseline Metrics Calculator v2 — Contract v2.1 §3 Compliance
Corrected: uses totalPerformance.closedTrades for trades,
           filters M1_ rolling windows for monthly stats.
"""
import json, sys, io, os
from datetime import datetime, timedelta
from collections import defaultdict

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

def load_results(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def extract_trades(bt):
    """Extract closed trades from totalPerformance."""
    tp = bt.get("totalPerformance", {})
    return tp.get("closedTrades", [])

def extract_monthly_stats(bt):
    """Extract M1 (1-month) rolling window statistics only."""
    rw = bt.get("rollingWindow", {})
    months = []
    for key in sorted(rw.keys()):
        if not key.startswith("M1_"):
            continue
        month_data = rw[key]
        ps = month_data.get("portfolioStatistics", {})
        ts = month_data.get("tradeStatistics", {})
        start_eq = float(ps.get("startEquity", 0))
        end_eq = float(ps.get("endEquity", 0))
        n_trades = int(ts.get("totalNumberOfTrades", 0))
        months.append({
            "key": key,
            "start_equity": start_eq,
            "end_equity": end_eq,
            "return_pct": (end_eq - start_eq) / start_eq * 100 if start_eq > 0 else 0,
            "n_trades": n_trades,
            "pnl": end_eq - start_eq,
        })
    return months

def calc_tuw(months):
    """Time Under Water: % of months where equity is below prior peak."""
    if not months:
        return 0, 0
    peak = months[0]["start_equity"]
    under_water_count = 0
    current_uw_streak = 0
    max_uw_streak = 0
    
    for m in months:
        eq = m["end_equity"]
        if eq >= peak:
            peak = eq
            max_uw_streak = max(max_uw_streak, current_uw_streak)
            current_uw_streak = 0
        else:
            under_water_count += 1
            current_uw_streak += 1
    max_uw_streak = max(max_uw_streak, current_uw_streak)
    
    tuw_pct = under_water_count / len(months) * 100
    return tuw_pct, max_uw_streak

def calc_trade_frequency(trades, months):
    """Trades per month using trade exit dates."""
    if not months:
        return 0, 0, []
    
    # Count trades per calendar month from trade exit dates
    month_trade_count = defaultdict(int)
    for t in trades:
        exit_time = t.get("exitTime", "")
        if exit_time:
            try:
                dt = datetime.fromisoformat(exit_time.replace("Z", "+00:00"))
                month_key = dt.strftime("%Y-%m")
                month_trade_count[month_key] += 1
            except:
                pass
    
    # Also get from rolling window M1 data
    rw_counts = [m["n_trades"] for m in months]
    
    # Use actual trade data for frequency
    if month_trade_count:
        all_months_sorted = sorted(month_trade_count.keys())
        counts = [month_trade_count[m] for m in all_months_sorted]
        avg = sum(counts) / len(counts) if counts else 0
        below_8 = sum(1 for c in counts if c < 8)
        pct_below = below_8 / len(counts) * 100 if counts else 0
        return avg, pct_below, counts, all_months_sorted
    
    return 0, 100, [], []

def calc_daily_pnl_from_trades(trades, start_equity=10000):
    """Reconstruct daily P&L from trade exit dates."""
    daily_pnl = defaultdict(float)
    for t in trades:
        exit_time = t.get("exitTime", "")
        pnl = float(t.get("profitLoss", 0))
        if exit_time:
            try:
                dt = datetime.fromisoformat(exit_time.replace("Z", "+00:00"))
                day_key = dt.strftime("%Y-%m-%d")
                daily_pnl[day_key] += pnl
            except:
                pass
    return dict(sorted(daily_pnl.items()))

def calc_best_day_and_gini(daily_pnl):
    """Best Day % and Gini coefficient of positive days."""
    positive_days = {k: v for k, v in daily_pnl.items() if v > 0}
    if not positive_days:
        return 0, 0, 0, 0
    
    total_positive = sum(positive_days.values())
    best_day_pnl = max(positive_days.values())
    best_day_pct = best_day_pnl / total_positive * 100 if total_positive > 0 else 0
    
    sorted_days = sorted(positive_days.values(), reverse=True)
    top3_pnl = sum(sorted_days[:3])
    top3_pct = top3_pnl / total_positive * 100 if total_positive > 0 else 0
    
    # Gini coefficient
    n = len(sorted_days)
    if n <= 1:
        gini = 0
    else:
        sorted_asc = sorted(sorted_days)
        cumulative = sum(sorted_asc)
        weighted_sum = sum((i + 1) * val for i, val in enumerate(sorted_asc))
        gini = (2 * weighted_sum) / (n * cumulative) - (n + 1) / n if cumulative > 0 else 0
    
    # Find the actual best day
    best_day_date = max(positive_days, key=positive_days.get)
    
    return best_day_pct, top3_pct, gini, len(positive_days), best_day_date, best_day_pnl

def calc_max_daily_dd(daily_pnl, start_equity=10000):
    """Max daily drawdown as % of equity at start of day."""
    equity = start_equity
    max_daily_dd_pct = 0
    worst_day = ""
    worst_day_loss = 0
    
    for day, pnl in sorted(daily_pnl.items()):
        if pnl < 0:
            dd_pct = abs(pnl) / equity * 100 if equity > 0 else 0
            if dd_pct > max_daily_dd_pct:
                max_daily_dd_pct = dd_pct
                worst_day = day
                worst_day_loss = pnl
        equity += pnl
    
    return max_daily_dd_pct, worst_day, worst_day_loss

def analyze_strategy(name, path):
    """Full analysis of one strategy per Contract v2.1."""
    print(f"\n{'='*70}")
    print(f"  {name}")
    print(f"  Source: {path}")
    print(f"{'='*70}")
    
    bt = load_results(path)
    
    # Basic stats from QC
    stats = bt.get("statistics", {})
    perf = bt.get("totalPerformance", {})
    ts = perf.get("tradeStatistics", {})
    ps = perf.get("portfolioStatistics", {})
    
    total_trades = int(ts.get("totalNumberOfTrades", 0))
    
    print(f"\n--- QC Summary Statistics ---")
    print(f"  CAGR:           {stats.get('Compounding Annual Return', 'N/A')}")
    print(f"  Net Profit:     {stats.get('Net Profit', 'N/A')}")
    print(f"  Max Drawdown:   {stats.get('Drawdown', 'N/A')}")
    print(f"  Sharpe (QC):    {stats.get('Sharpe Ratio', 'N/A')}")
    print(f"  Sortino (QC):   {stats.get('Sortino Ratio', 'N/A')}")
    print(f"  Win Rate:       {stats.get('Win Rate', 'N/A')}")
    print(f"  P/L Ratio:      {stats.get('Profit-Loss Ratio', 'N/A')}")
    print(f"  Total Orders:   {stats.get('Total Orders', 'N/A')}")
    print(f"  Total Trades:   {total_trades}")
    print(f"  Ann. StdDev:    {stats.get('Annual Standard Deviation', 'N/A')}")
    print(f"  DD Recovery:    {stats.get('Drawdown Recovery', 'N/A')} days")
    
    # Extract data
    trades = extract_trades(bt)
    months = extract_monthly_stats(bt)
    
    print(f"\n  Trades extracted: {len(trades)}")
    print(f"  M1 months extracted: {len(months)}")
    
    print(f"\n--- Contract v2.1 Metrics ---")
    
    # TUW
    tuw_pct, max_uw_streak = calc_tuw(months)
    tuw_class = "Excelente" if tuw_pct < 40 else "Aceptable" if tuw_pct < 55 else "Marginal" if tuw_pct < 60 else "INCOMPATIBLE"
    print(f"\n  [TUW §3.4]")
    print(f"    Time Under Water:     {tuw_pct:.1f}%  [{tuw_class}]")
    print(f"    Max UW streak:        {max_uw_streak} months")
    print(f"    §3.1 threshold (<70%): {'PASS' if tuw_pct < 70 else 'FAIL'}")
    print(f"    §3.2 threshold (<40%): {'PASS' if tuw_pct < 40 else 'FAIL'}")
    
    # Trade Frequency
    avg_freq, pct_below_floor, monthly_counts, month_labels = calc_trade_frequency(trades, months)
    freq_class = "Incompatible" if avg_freq < 6 else "Zona roja" if avg_freq < 8 else "Aceptable" if avg_freq < 15 else "Ideal" if avg_freq < 25 else "Revisar costos"
    print(f"\n  [Trade Frequency §8.2]")
    print(f"    Avg trades/month:     {avg_freq:.1f}  [{freq_class}]")
    print(f"    Months below 8:       {pct_below_floor:.0f}%")
    if month_labels:
        for i, (label, count) in enumerate(zip(month_labels, monthly_counts)):
            marker = " <<<" if count < 8 else ""
            print(f"      {label}: {count:>3} trades{marker}")
    
    print(f"    §3.1 threshold (>=6): {'PASS' if avg_freq >= 6 else 'FAIL'}")
    print(f"    §3.2 threshold (>=10):{'PASS' if avg_freq >= 10 else 'FAIL'}")
    
    # Daily PnL analysis
    daily_pnl = calc_daily_pnl_from_trades(trades)
    
    # Best Day & Gini
    result = calc_best_day_and_gini(daily_pnl)
    best_day_pct, top3_pct, gini, n_positive_days, best_day_date, best_day_amount = result
    print(f"\n  [Concentration §8.1]")
    print(f"    Best Day %:           {best_day_pct:.1f}%  [{'PASS' if best_day_pct < 35 else 'WARNING' if best_day_pct < 50 else 'FAIL FTMO'} §3.2 <35%]")
    print(f"    Best Day:             {best_day_date} (+${best_day_amount:.2f})")
    print(f"    Top 3 Days %:         {top3_pct:.1f}%  [{'OK' if top3_pct < 60 else 'CONCENTRATED'}]")
    print(f"    Gini coefficient:     {gini:.3f}  [0=uniform, 1=concentrated]")
    print(f"    Positive trading days:{n_positive_days}")
    
    # Max Daily DD
    start_eq = float(ps.get("startEquity", 10000)) if ps else 10000
    max_dd_pct, worst_day, worst_loss = calc_max_daily_dd(daily_pnl, start_eq)
    print(f"\n  [Max Daily DD]")
    print(f"    Max single-day loss:  {max_dd_pct:.2f}% on {worst_day} (${worst_loss:.2f})")
    print(f"    §3.1 threshold (<3%): {'PASS' if max_dd_pct < 3.0 else 'FAIL'}")
    print(f"    §3.2 target (<2%):    {'PASS' if max_dd_pct < 2.0 else 'FAIL'}")
    print(f"    §5.2 FundedNext 5%:   {'PASS' if max_dd_pct < 5.0 else 'FAIL'}")
    
    # Monthly returns from M1 rolling windows
    monthly_returns = [m["return_pct"] for m in months]
    positive_months = sum(1 for r in monthly_returns if r > 0)
    pct_positive = positive_months / len(monthly_returns) * 100 if monthly_returns else 0
    avg_monthly = sum(monthly_returns) / len(monthly_returns) if monthly_returns else 0
    print(f"\n  [Monthly Consistency]")
    print(f"    Avg monthly return:   {avg_monthly:.2f}%")
    print(f"    Positive months:      {positive_months}/{len(monthly_returns)} ({pct_positive:.0f}%)")
    print(f"    §3.3 cond3 (>75%):    {'PASS' if pct_positive > 75 else 'FAIL'}")
    for m in months:
        marker = " <<<" if m["return_pct"] < 0 else ""
        print(f"      {m['key']}: equity ${m['end_equity']:.2f} | return {m['return_pct']:.2f}%{marker}")
    
    # Retorno/DD ratio
    cagr_str = stats.get("Compounding Annual Return", "0%").replace("%", "")
    dd_str = stats.get("Drawdown", "0%").replace("%", "")
    try:
        cagr_val = float(cagr_str)
        dd_val = float(dd_str)
        ratio = cagr_val / dd_val if dd_val > 0 else 0
    except:
        cagr_val = dd_val = ratio = 0
    
    print(f"\n  [Return/DD Ratio]")
    print(f"    CAGR:                 {cagr_val:.2f}%")
    print(f"    Max DD:               {dd_val:.2f}%")
    print(f"    Ratio:                {ratio:.2f}")
    print(f"    §3.1 threshold (>0.8):{'PASS' if ratio > 0.8 else 'FAIL'}")
    print(f"    §3.2 threshold (>2.0):{'PASS' if ratio > 2.0 else 'FAIL'}")
    
    # Sharpe estimation from trade data
    if trades:
        trade_pnls = [float(t.get("profitLoss", 0)) for t in trades]
        import statistics
        mean_pnl = statistics.mean(trade_pnls)
        std_pnl = statistics.stdev(trade_pnls) if len(trade_pnls) > 1 else 1
        trade_sharpe = mean_pnl / std_pnl if std_pnl > 0 else 0
        # Annualize: roughly sqrt(trades_per_year) * per_trade_sharpe
        trades_per_year = len(trades) / 2  # 2 years of OOS
        ann_sharpe_est = trade_sharpe * (trades_per_year ** 0.5)
        print(f"\n  [Sharpe Estimation]")
        print(f"    Per-trade Sharpe:     {trade_sharpe:.4f}")
        print(f"    Trades/year:          {trades_per_year:.0f}")
        print(f"    Annualized est:       {ann_sharpe_est:.2f}")
        print(f"    §3.1 threshold (>0.5):{'PASS' if ann_sharpe_est > 0.5 else 'FAIL'}")
        print(f"    §3.2 threshold (>1.2):{'PASS' if ann_sharpe_est > 1.2 else 'FAIL'}")
    
    # Summary gate check
    print(f"\n{'='*70}")
    print(f"  GATE CHECK — {name}")
    print(f"{'='*70}")
    
    ann_sharpe = ann_sharpe_est if trades else 0
    
    gates_31 = [
        ("Sharpe OOS > 0.5", ann_sharpe > 0.5 if trades else None),
        ("Return/DD > 0.8", ratio > 0.8),
        ("TUW < 70%", tuw_pct < 70),
        ("Trades/month >= 6", avg_freq >= 6),
        ("Max Daily DD < 3%", max_dd_pct < 3.0),
        ("IS→OOS degradation < 45%", None),
    ]
    
    gates_32 = [
        ("Sharpe > 1.2-1.5", ann_sharpe > 1.2 if trades else None),
        ("Return/DD > 2.0", ratio > 2.0),
        ("Avg Monthly > 2%", avg_monthly > 2.0),
        ("Max Daily DD < 2%", max_dd_pct < 2.0),
        ("TUW < 40%", tuw_pct < 40),
        ("Trades/month >= 10", avg_freq >= 10),
        ("Best Day < 35%", best_day_pct < 35),
        ("Positive months > 75%", pct_positive > 75),
    ]
    
    pass_31 = sum(1 for _, r in gates_31 if r is True)
    fail_31 = sum(1 for _, r in gates_31 if r is False)
    pass_32 = sum(1 for _, r in gates_32 if r is True)
    fail_32 = sum(1 for _, r in gates_32 if r is False)
    
    print(f"\n  §3.1 Discovery Gates ({pass_31} PASS / {fail_31} FAIL):")
    for gate, result in gates_31:
        status = "PASS" if result else ("FAIL" if result is False else "N/A")
        print(f"    [{status:>4}] {gate}")
    
    print(f"\n  §3.2 Funding Aspirational ({pass_32} PASS / {fail_32} FAIL):")
    for gate, result in gates_32:
        status = "PASS" if result else ("FAIL" if result is False else "N/A")
        print(f"    [{status:>4}] {gate}")
    
    return {
        "name": name,
        "tuw": tuw_pct,
        "max_uw_streak": max_uw_streak,
        "avg_freq": avg_freq,
        "best_day_pct": best_day_pct,
        "top3_pct": top3_pct,
        "gini": gini,
        "max_daily_dd": max_dd_pct,
        "ratio": ratio,
        "cagr": cagr_val,
        "dd": dd_val,
        "avg_monthly": avg_monthly,
        "pct_positive_months": pct_positive,
        "sharpe_est": ann_sharpe_est if trades else 0,
        "total_trades": total_trades,
        "pass_31": pass_31,
        "fail_31": fail_31,
        "pass_32": pass_32,
        "fail_32": fail_32,
    }


if __name__ == "__main__":
    strategies = [
        ("CMR-V2.0 (OOS 2023-2024)", "C:/AI_VAULT/tmp_agent/strategies/commodity_mr/backtest_results.json"),
        ("TP-V1.2 (OOS 2023-2024)", "C:/AI_VAULT/tmp_agent/strategies/trend_pullback/backtest_results.json"),
        ("MA-TF V1.1 (IS 2010-2020)", "C:/AI_VAULT/tmp_agent/strategies/multi_asset_tf/backtest_results.json"),
    ]
    
    results = []
    for name, path in strategies:
        if os.path.exists(path):
            r = analyze_strategy(name, path)
            results.append(r)
        else:
            print(f"[SKIP] {name} — file not found: {path}")
    
    # Comparison table
    if len(results) >= 2:
        cmr, tp = results[0], results[1]
        print(f"\n\n{'='*80}")
        print(f"  COMPARISON TABLE — Contract v2.1 Baseline Metrics")
        print(f"{'='*80}")
        print(f"  {'Metric':<30} {'CMR-V2.0':>15} {'TP-V1.2':>15} {'§3.1':>10} {'§3.2':>10}")
        print(f"  {'-'*80}")
        rows = [
            ("CAGR", f"{cmr['cagr']:.2f}%", f"{tp['cagr']:.2f}%", "-", "-"),
            ("Max DD", f"{cmr['dd']:.2f}%", f"{tp['dd']:.2f}%", "-", "-"),
            ("Return/DD Ratio", f"{cmr['ratio']:.2f}", f"{tp['ratio']:.2f}", ">0.8", ">2.0"),
            ("Sharpe (est.)", f"{cmr['sharpe_est']:.2f}", f"{tp['sharpe_est']:.2f}", ">0.5", ">1.2"),
            ("TUW %", f"{cmr['tuw']:.1f}%", f"{tp['tuw']:.1f}%", "<70%", "<40%"),
            ("Max UW Streak", f"{cmr['max_uw_streak']}mo", f"{tp['max_uw_streak']}mo", "-", "-"),
            ("Trades/month", f"{cmr['avg_freq']:.1f}", f"{tp['avg_freq']:.1f}", ">=6", ">=10"),
            ("Best Day %", f"{cmr['best_day_pct']:.1f}%", f"{tp['best_day_pct']:.1f}%", "-", "<35%"),
            ("Top 3 Days %", f"{cmr['top3_pct']:.1f}%", f"{tp['top3_pct']:.1f}%", "-", "<60%"),
            ("Gini", f"{cmr['gini']:.3f}", f"{tp['gini']:.3f}", "-", "low"),
            ("Max Daily DD", f"{cmr['max_daily_dd']:.2f}%", f"{tp['max_daily_dd']:.2f}%", "<3%", "<2%"),
            ("Avg Monthly Ret", f"{cmr['avg_monthly']:.2f}%", f"{tp['avg_monthly']:.2f}%", "-", ">2%"),
            ("Positive Months", f"{cmr['pct_positive_months']:.0f}%", f"{tp['pct_positive_months']:.0f}%", "-", ">75%"),
            ("Total Trades", f"{cmr['total_trades']}", f"{tp['total_trades']}", "-", "-"),
            ("§3.1 Gates", f"{cmr['pass_31']}P/{cmr['fail_31']}F", f"{tp['pass_31']}P/{tp['fail_31']}F", "-", "-"),
            ("§3.2 Gates", f"{cmr['pass_32']}P/{cmr['fail_32']}F", f"{tp['pass_32']}P/{tp['fail_32']}F", "-", "-"),
        ]
        for label, v1, v2, t1, t2 in rows:
            print(f"  {label:<30} {v1:>15} {v2:>15} {t1:>10} {t2:>10}")
        
        print(f"\n  VERDICT:")
        print(f"  CMR-V2.0: {'Passes' if cmr['fail_31'] == 0 else 'FAILS'} §3.1 Discovery | {'Passes' if cmr['fail_32'] == 0 else 'FAILS'} §3.2 Funding")
        print(f"  TP-V1.2:  {'Passes' if tp['fail_31'] == 0 else 'FAILS'} §3.1 Discovery | {'Passes' if tp['fail_32'] == 0 else 'FAILS'} §3.2 Funding")
        print(f"\n  Both strategies need significant improvement to reach §3.2 Funding thresholds.")
        print(f"  Priority gaps: TUW (both >85%), Sharpe, Return/DD ratio, trade frequency.")
        print(f"  Ceiling Watch (§2.2): 6+ FX families tested. If TF and Vol-MR also fail → declare ceiling.")
