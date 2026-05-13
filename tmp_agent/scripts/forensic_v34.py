"""Forensic analysis V3.4 — EOD time stop
Compares with V3.3 (3h time stop) to measure impact of extended holding.
"""
import json
from datetime import datetime, timedelta
from collections import defaultdict

def load_trades(path):
    with open(path) as f:
        return json.load(f)

def parse_dt(s):
    if not s:
        return None
    for fmt in ["%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S"]:
        try:
            return datetime.strptime(s, fmt)
        except:
            continue
    return None

def analyze(trades, label):
    print(f"\n{'='*70}")
    print(f"  FORENSIC: {label}  ({len(trades)} trades)")
    print(f"{'='*70}")

    wins = [t for t in trades if t.get("isWin")]
    losses = [t for t in trades if not t.get("isWin")]
    total_pl = sum(t.get("profitLoss", 0) for t in trades)
    total_fees = sum(t.get("totalFees", 0) for t in trades)
    net = total_pl - total_fees

    print(f"\n--- OVERALL ---")
    print(f"  Trades: {len(trades)}")
    print(f"  Wins: {len(wins)} ({100*len(wins)/len(trades):.1f}%)")
    print(f"  Losses: {len(losses)} ({100*len(losses)/len(trades):.1f}%)")
    print(f"  Gross P/L: ${total_pl:,.2f}")
    print(f"  Fees: ${total_fees:,.2f}")
    print(f"  Net P/L: ${net:,.2f}")

    # Average win/loss
    avg_win = sum(t["profitLoss"] for t in wins) / len(wins) if wins else 0
    avg_loss = sum(t["profitLoss"] for t in losses) / len(losses) if losses else 0
    print(f"  Avg Win: ${avg_win:,.2f}")
    print(f"  Avg Loss: ${avg_loss:,.2f}")
    pl_ratio = abs(avg_win / avg_loss) if avg_loss != 0 else 0
    print(f"  P/L Ratio: {pl_ratio:.2f}")

    # Expectancy
    wr = len(wins) / len(trades) if trades else 0
    expectancy = wr * avg_win + (1 - wr) * avg_loss
    print(f"  Expectancy/trade: ${expectancy:,.2f}")

    # --- HOLDING TIME ANALYSIS ---
    print(f"\n--- HOLDING TIME DISTRIBUTION ---")
    buckets = {
        "< 30 min": (0, 1800),
        "30min - 1h": (1800, 3600),
        "1h - 2h": (3600, 7200),
        "2h - 3h": (7200, 10800),
        "3h - 4h": (10800, 14400),
        "4h - 5h": (14400, 18000),
        "5h - 6h": (18000, 21600),
        "6h+ (EOD)": (21600, 999999),
    }

    for bname, (lo, hi) in buckets.items():
        bucket_trades = []
        for t in trades:
            entry = parse_dt(t.get("entryTime"))
            exit_ = parse_dt(t.get("exitTime"))
            if entry and exit_:
                secs = (exit_ - entry).total_seconds()
                if lo <= secs < hi:
                    bucket_trades.append(t)
        if bucket_trades:
            bwins = [t for t in bucket_trades if t.get("isWin")]
            bpl = sum(t["profitLoss"] for t in bucket_trades)
            bwr = 100 * len(bwins) / len(bucket_trades) if bucket_trades else 0
            print(f"  {bname:>15}: {len(bucket_trades):>4} trades | WR {bwr:>5.1f}% | P/L ${bpl:>10,.2f}")

    # --- EXIT TYPE ANALYSIS (by tag) ---
    # QC doesn't give us the tag directly in trades, but we can infer from timing
    print(f"\n--- EXIT INFERENCE ---")
    sl_trades = []
    eod_trades = []
    other_trades = []

    for t in trades:
        entry = parse_dt(t.get("entryTime"))
        exit_ = parse_dt(t.get("exitTime"))
        if not entry or not exit_:
            other_trades.append(t)
            continue

        exit_hour = exit_.hour
        exit_min = exit_.minute
        hold_secs = (exit_ - entry).total_seconds()

        # EOD close = exit at 20:55 UTC (15:55 ET) or very close
        if exit_hour == 20 and 50 <= exit_min <= 59:
            eod_trades.append(t)
        elif exit_hour == 21 and exit_min <= 5:
            eod_trades.append(t)
        else:
            sl_trades.append(t)

    for label2, group in [("SL/Trailing", sl_trades), ("EOD 3:55PM", eod_trades), ("Other", other_trades)]:
        if group:
            gw = [t for t in group if t.get("isWin")]
            gpl = sum(t["profitLoss"] for t in group)
            gwr = 100 * len(gw) / len(group) if group else 0
            print(f"  {label2:>15}: {len(group):>4} trades | WR {gwr:>5.1f}% | P/L ${gpl:>10,.2f}")

    # --- MAE/MFE ANALYSIS ---
    print(f"\n--- MAE CLIFF ANALYSIS ---")
    mae_low = [t for t in trades if abs(t.get("mae", 0)) < 0.005 * t.get("entryPrice", 1) * t.get("quantity", 1)]
    mae_high = [t for t in trades if abs(t.get("mae", 0)) >= 0.005 * t.get("entryPrice", 1) * t.get("quantity", 1)]
    # Simpler: use dollar MAE thresholds
    mae_under_100 = [t for t in trades if abs(t.get("mae", 0)) < 100]
    mae_100_300 = [t for t in trades if 100 <= abs(t.get("mae", 0)) < 300]
    mae_over_300 = [t for t in trades if abs(t.get("mae", 0)) >= 300]

    for lbl, grp in [("MAE < $100", mae_under_100), ("MAE $100-300", mae_100_300), ("MAE > $300", mae_over_300)]:
        if grp:
            gw = [t for t in grp if t.get("isWin")]
            gpl = sum(t["profitLoss"] for t in grp)
            gwr = 100 * len(gw) / len(grp) if grp else 0
            print(f"  {lbl:>15}: {len(grp):>4} trades | WR {gwr:>5.1f}% | P/L ${gpl:>10,.2f}")

    # --- MFE WASTE (losers that were profitable) ---
    print(f"\n--- MFE WASTE (losers that were positive first) ---")
    losers_with_mfe = [t for t in losses if t.get("mfe", 0) > 0]
    if losers_with_mfe:
        avg_mfe = sum(t["mfe"] for t in losers_with_mfe) / len(losers_with_mfe)
        avg_final = sum(t["profitLoss"] for t in losers_with_mfe) / len(losers_with_mfe)
        total_waste = sum(t["mfe"] - t["profitLoss"] for t in losers_with_mfe)
        print(f"  {len(losers_with_mfe)} losers had positive MFE ({100*len(losers_with_mfe)/len(losses):.1f}% of all losers)")
        print(f"  Avg MFE before losing: ${avg_mfe:,.2f}")
        print(f"  Avg final P/L: ${avg_final:,.2f}")
        print(f"  Total MFE waste: ${total_waste:,.2f}")

    # --- MONTHLY BREAKDOWN ---
    print(f"\n--- MONTHLY P/L ---")
    monthly = defaultdict(lambda: {"trades": 0, "wins": 0, "pl": 0.0})
    for t in trades:
        entry = parse_dt(t.get("entryTime"))
        if not entry:
            continue
        key = entry.strftime("%Y-%m")
        monthly[key]["trades"] += 1
        monthly[key]["pl"] += t.get("profitLoss", 0)
        if t.get("isWin"):
            monthly[key]["wins"] += 1

    pos_months = 0
    for m in sorted(monthly.keys()):
        d = monthly[m]
        wr = 100 * d["wins"] / d["trades"] if d["trades"] else 0
        sign = "+" if d["pl"] >= 0 else ""
        if d["pl"] >= 0:
            pos_months += 1
        print(f"  {m}: {d['trades']:>3} trades | WR {wr:>5.1f}% | {sign}${d['pl']:>9,.2f}")
    print(f"  Positive months: {pos_months}/{len(monthly)}")

    # --- TOP 10 WORST TRADES ---
    print(f"\n--- TOP 10 WORST TRADES ---")
    by_pl = sorted(trades, key=lambda t: t.get("profitLoss", 0))
    for t in by_pl[:10]:
        sym = t.get("symbols", [{}])[0].get("value", "?")
        entry = parse_dt(t.get("entryTime"))
        exit_ = parse_dt(t.get("exitTime"))
        hold = ""
        if entry and exit_:
            hold = str(exit_ - entry)
        print(f"  {sym:>6} | P/L ${t['profitLoss']:>9,.2f} | MAE ${t.get('mae',0):>9,.2f} | Hold: {hold}")

    # --- TOP 10 BEST TRADES ---
    print(f"\n--- TOP 10 BEST TRADES ---")
    for t in by_pl[-10:]:
        sym = t.get("symbols", [{}])[0].get("value", "?")
        entry = parse_dt(t.get("entryTime"))
        exit_ = parse_dt(t.get("exitTime"))
        hold = ""
        if entry and exit_:
            hold = str(exit_ - entry)
        print(f"  {sym:>6} | P/L ${t['profitLoss']:>9,.2f} | MFE ${t.get('mfe',0):>9,.2f} | Hold: {hold}")

    # --- TICKER BREAKDOWN (top 10 best / worst) ---
    print(f"\n--- TICKER P/L (top 10 worst + best) ---")
    by_ticker = defaultdict(lambda: {"trades": 0, "pl": 0.0})
    for t in trades:
        sym = t.get("symbols", [{}])[0].get("value", "?")
        by_ticker[sym]["trades"] += 1
        by_ticker[sym]["pl"] += t.get("profitLoss", 0)
    sorted_tickers = sorted(by_ticker.items(), key=lambda x: x[1]["pl"])
    print("  WORST:")
    for sym, d in sorted_tickers[:10]:
        print(f"    {sym:>6}: {d['trades']:>3} trades | P/L ${d['pl']:>9,.2f}")
    print("  BEST:")
    for sym, d in sorted_tickers[-10:]:
        print(f"    {sym:>6}: {d['trades']:>3} trades | P/L ${d['pl']:>9,.2f}")

    return {
        "trades": len(trades),
        "wins": len(wins),
        "wr": wr * 100,
        "gross_pl": total_pl,
        "fees": total_fees,
        "net_pl": net,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "pl_ratio": pl_ratio,
        "expectancy": expectancy,
        "pos_months": pos_months,
        "total_months": len(monthly),
        "sl_trades": len(sl_trades),
        "eod_trades": len(eod_trades),
    }


def main():
    v33 = load_trades("C:/AI_VAULT/tmp_agent/strategies/mtf_trend/bt_v33_trades.json")
    v34 = load_trades("C:/AI_VAULT/tmp_agent/strategies/mtf_trend/bt_v34_trades.json")

    s33 = analyze(v33, "V3.3 — 3h Time Stop")
    s34 = analyze(v34, "V3.4 — EOD (3:55 PM)")

    print(f"\n\n{'='*70}")
    print(f"  COMPARISON: V3.3 (3h) vs V3.4 (EOD)")
    print(f"{'='*70}")
    print(f"  {'Metric':<25} {'V3.3 (3h)':>15} {'V3.4 (EOD)':>15} {'Delta':>15}")
    print(f"  {'-'*25} {'-'*15} {'-'*15} {'-'*15}")

    rows = [
        ("Trades", f"{s33['trades']}", f"{s34['trades']}", f"{s34['trades']-s33['trades']:+d}"),
        ("Win Rate", f"{s33['wr']:.1f}%", f"{s34['wr']:.1f}%", f"{s34['wr']-s33['wr']:+.1f}%"),
        ("Gross P/L", f"${s33['gross_pl']:,.0f}", f"${s34['gross_pl']:,.0f}", f"${s34['gross_pl']-s33['gross_pl']:+,.0f}"),
        ("Fees", f"${s33['fees']:,.0f}", f"${s34['fees']:,.0f}", f"${s34['fees']-s33['fees']:+,.0f}"),
        ("Net P/L", f"${s33['net_pl']:,.0f}", f"${s34['net_pl']:,.0f}", f"${s34['net_pl']-s33['net_pl']:+,.0f}"),
        ("Avg Win", f"${s33['avg_win']:,.2f}", f"${s34['avg_win']:,.2f}", f"${s34['avg_win']-s33['avg_win']:+,.2f}"),
        ("Avg Loss", f"${s33['avg_loss']:,.2f}", f"${s34['avg_loss']:,.2f}", f"${s34['avg_loss']-s33['avg_loss']:+,.2f}"),
        ("P/L Ratio", f"{s33['pl_ratio']:.2f}", f"{s34['pl_ratio']:.2f}", f"{s34['pl_ratio']-s33['pl_ratio']:+.2f}"),
        ("Expectancy/trade", f"${s33['expectancy']:,.2f}", f"${s34['expectancy']:,.2f}", f"${s34['expectancy']-s33['expectancy']:+,.2f}"),
        ("Positive Months", f"{s33['pos_months']}/{s33['total_months']}", f"{s34['pos_months']}/{s34['total_months']}", ""),
        ("SL/Trailing Exits", f"{s33['sl_trades']}", f"{s34['sl_trades']}", f"{s34['sl_trades']-s33['sl_trades']:+d}"),
        ("EOD/TimeStop Exits", f"{s33['eod_trades']}", f"{s34['eod_trades']}", f"{s34['eod_trades']-s33['eod_trades']:+d}"),
    ]

    for label, v33v, v34v, delta in rows:
        print(f"  {label:<25} {v33v:>15} {v34v:>15} {delta:>15}")


if __name__ == "__main__":
    main()
