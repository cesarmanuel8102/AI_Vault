"""
G15 Forensic Analysis: Deep x10think analysis of every OOS trade vs IS patterns.
Identify structural causes of degradation.
"""
import json, os
from datetime import datetime
from collections import defaultdict

OUTPUT_DIR = "C:/AI_VAULT/tmp_agent/strategies/yoel_options"

def load_trades(filepath):
    with open(filepath, 'r') as f:
        d = json.load(f)
    tp = d.get('totalPerformance', {})
    trades = tp.get('closedTrades', [])
    ts = tp.get('tradeStatistics', {})
    ps = tp.get('portfolioStatistics', {})
    return trades, ts, ps

def parse_trade(t):
    """Parse a single trade into a clean dict."""
    sym_info = t.get('symbols', [{}])[0]
    underlying = sym_info.get('underlying', {}).get('value', '?')
    option_str = sym_info.get('value', '?')
    
    # Parse option details from string like "QQQ   250124C00512500"
    option_type = 'CALL' if 'C' in option_str[6:12] else 'PUT'
    
    entry_time = t.get('entryTime', '')
    exit_time = t.get('exitTime', '')
    
    entry_dt = datetime.fromisoformat(entry_time.replace('Z', '+00:00')) if entry_time else None
    exit_dt = datetime.fromisoformat(exit_time.replace('Z', '+00:00')) if exit_time else None
    
    hold_duration = t.get('duration', '')
    
    entry_price = t.get('entryPrice', 0)
    exit_price = t.get('exitPrice', 0)
    pnl = t.get('profitLoss', 0)
    pnl_pct = (exit_price / entry_price - 1) if entry_price > 0 else 0
    
    mae = t.get('mae', 0)  # Maximum Adverse Excursion (worst drawdown during trade)
    mfe = t.get('mfe', 0)  # Maximum Favorable Excursion (best unrealized gain)
    
    fees = t.get('totalFees', 0)
    is_win = t.get('isWin', False)
    
    # Determine exit reason from PnL pattern
    if pnl_pct >= 0.30:
        exit_reason = 'TP'
    elif pnl_pct <= -0.18:
        exit_reason = 'SL'
    elif hold_duration and 'd' in str(hold_duration):
        days_str = str(hold_duration).split('.')[0] if '.' in str(hold_duration) else '0'
        try:
            days = int(days_str)
        except:
            days = 0
        if days >= 5:
            exit_reason = 'TIME'
        else:
            exit_reason = 'OTHER'
    else:
        exit_reason = 'OTHER'
    
    # Month
    month = entry_dt.strftime('%Y-%m') if entry_dt else '?'
    dow = entry_dt.strftime('%A') if entry_dt else '?'
    
    return {
        'ticker': underlying,
        'option_type': option_type,
        'entry_time': entry_time,
        'exit_time': exit_time,
        'entry_price': entry_price,
        'exit_price': exit_price,
        'pnl': pnl,
        'pnl_pct': pnl_pct,
        'mae': mae,
        'mfe': mfe,
        'fees': fees,
        'is_win': is_win,
        'duration': hold_duration,
        'exit_reason': exit_reason,
        'month': month,
        'dow': dow,
        'entry_dt': entry_dt,
        'option_str': option_str,
    }

# ================================================================
# LOAD DATA
# ================================================================
print("=" * 80)
print("G15 FORENSIC ANALYSIS — x10think")
print("=" * 80)

oos_trades_raw, oos_ts, oos_ps = load_trades(f"{OUTPUT_DIR}/g15_g15_oos_full_bt_data.json")
is_trades_raw, is_ts, is_ps = load_trades(f"{OUTPUT_DIR}/g15_g15_is_full_bt_data.json")

oos_trades = [parse_trade(t) for t in oos_trades_raw]
is_trades = [parse_trade(t) for t in is_trades_raw]

print(f"\nIS trades: {len(is_trades)}")
print(f"OOS trades: {len(oos_trades)}")

# ================================================================
# 1. TRADE-BY-TRADE OOS DUMP
# ================================================================
print(f"\n{'='*120}")
print("1. ALL OOS TRADES (chronological)")
print(f"{'='*120}")
print(f"{'#':>3} {'Date':>12} {'Ticker':>6} {'Type':>5} {'Entry$':>8} {'Exit$':>8} {'PnL$':>8} {'PnL%':>7} {'MAE$':>8} {'MFE$':>8} {'Win':>4} {'Exit':>6}")
print("-" * 120)

cumulative_pnl = 0
monthly_pnl = defaultdict(float)
ticker_pnl = defaultdict(lambda: {'pnl': 0, 'wins': 0, 'losses': 0, 'trades': 0})

for i, t in enumerate(oos_trades):
    cumulative_pnl += t['pnl']
    monthly_pnl[t['month']] += t['pnl']
    tk = ticker_pnl[t['ticker']]
    tk['pnl'] += t['pnl']
    tk['trades'] += 1
    if t['is_win']:
        tk['wins'] += 1
    else:
        tk['losses'] += 1
    
    win_str = 'W' if t['is_win'] else 'L'
    date_str = t['entry_time'][:10] if t['entry_time'] else '?'
    print(f"{i+1:>3} {date_str:>12} {t['ticker']:>6} {t['option_type']:>5} "
          f"{t['entry_price']:>8.2f} {t['exit_price']:>8.2f} {t['pnl']:>+8.0f} "
          f"{t['pnl_pct']:>+7.1%} {t['mae']:>+8.0f} {t['mfe']:>+8.0f} "
          f"{win_str:>4} {t['exit_reason']:>6}")

print(f"\nCumulative PnL: ${cumulative_pnl:+,.0f}")

# ================================================================
# 2. OOS BY MONTH
# ================================================================
print(f"\n{'='*80}")
print("2. OOS PnL BY MONTH")
print(f"{'='*80}")
for month in sorted(monthly_pnl.keys()):
    month_trades = [t for t in oos_trades if t['month'] == month]
    wins = sum(1 for t in month_trades if t['is_win'])
    total = len(month_trades)
    wr = wins/total*100 if total > 0 else 0
    print(f"  {month}: {monthly_pnl[month]:>+8.0f}  ({total} trades, WR={wr:.0f}%)")

# ================================================================
# 3. OOS BY TICKER
# ================================================================
print(f"\n{'='*80}")
print("3. OOS PnL BY TICKER")
print(f"{'='*80}")
for ticker in sorted(ticker_pnl.keys()):
    tk = ticker_pnl[ticker]
    wr = tk['wins']/tk['trades']*100 if tk['trades'] > 0 else 0
    avg = tk['pnl']/tk['trades'] if tk['trades'] > 0 else 0
    print(f"  {ticker}: PnL={tk['pnl']:>+8.0f}  trades={tk['trades']:>3}  W={tk['wins']:>2}  L={tk['losses']:>2}  WR={wr:>5.1f}%  avg={avg:>+7.1f}")

# ================================================================
# 4. IS BY TICKER (for comparison)
# ================================================================
print(f"\n{'='*80}")
print("4. IS PnL BY TICKER (comparison)")
print(f"{'='*80}")
is_ticker_pnl = defaultdict(lambda: {'pnl': 0, 'wins': 0, 'losses': 0, 'trades': 0})
for t in is_trades:
    tk = is_ticker_pnl[t['ticker']]
    tk['pnl'] += t['pnl']
    tk['trades'] += 1
    if t['is_win']:
        tk['wins'] += 1
    else:
        tk['losses'] += 1

for ticker in sorted(is_ticker_pnl.keys()):
    tk = is_ticker_pnl[ticker]
    wr = tk['wins']/tk['trades']*100 if tk['trades'] > 0 else 0
    avg = tk['pnl']/tk['trades'] if tk['trades'] > 0 else 0
    print(f"  {ticker}: PnL={tk['pnl']:>+8.0f}  trades={tk['trades']:>3}  W={tk['wins']:>2}  L={tk['losses']:>2}  WR={wr:>5.1f}%  avg={avg:>+7.1f}")

# ================================================================
# 5. IS vs OOS TICKER COMPARISON
# ================================================================
print(f"\n{'='*80}")
print("5. IS vs OOS TICKER COMPARISON")
print(f"{'='*80}")
all_tickers = sorted(set(list(ticker_pnl.keys()) + list(is_ticker_pnl.keys())))
print(f"{'Ticker':>6} | {'IS PnL':>8} {'IS Trades':>10} {'IS WR':>6} {'IS Avg':>8} | {'OOS PnL':>8} {'OOS Trades':>10} {'OOS WR':>6} {'OOS Avg':>8} | {'Delta WR':>9}")
print("-" * 105)
for ticker in all_tickers:
    is_tk = is_ticker_pnl.get(ticker, {'pnl': 0, 'wins': 0, 'losses': 0, 'trades': 0})
    oos_tk = ticker_pnl.get(ticker, {'pnl': 0, 'wins': 0, 'losses': 0, 'trades': 0})
    is_wr = is_tk['wins']/is_tk['trades']*100 if is_tk['trades'] > 0 else 0
    oos_wr = oos_tk['wins']/oos_tk['trades']*100 if oos_tk['trades'] > 0 else 0
    is_avg = is_tk['pnl']/is_tk['trades'] if is_tk['trades'] > 0 else 0
    oos_avg = oos_tk['pnl']/oos_tk['trades'] if oos_tk['trades'] > 0 else 0
    delta = oos_wr - is_wr
    print(f"{ticker:>6} | {is_tk['pnl']:>+8.0f} {is_tk['trades']:>10} {is_wr:>5.1f}% {is_avg:>+8.1f} | {oos_tk['pnl']:>+8.0f} {oos_tk['trades']:>10} {oos_wr:>5.1f}% {oos_avg:>+8.1f} | {delta:>+8.1f}%")

# ================================================================
# 6. MAE/MFE ANALYSIS
# ================================================================
print(f"\n{'='*80}")
print("6. MAE/MFE ANALYSIS (Adverse vs Favorable Excursion)")
print(f"{'='*80}")

for label, trades in [("IS", is_trades), ("OOS", oos_trades)]:
    winners = [t for t in trades if t['is_win']]
    losers = [t for t in trades if not t['is_win']]
    
    avg_mae_w = sum(t['mae'] for t in winners)/len(winners) if winners else 0
    avg_mfe_w = sum(t['mfe'] for t in winners)/len(winners) if winners else 0
    avg_mae_l = sum(t['mae'] for t in losers)/len(losers) if losers else 0
    avg_mfe_l = sum(t['mfe'] for t in losers)/len(losers) if losers else 0
    
    # Efficiency: how much of MFE was captured
    captured_w = [t['pnl']/t['mfe'] if t['mfe'] > 0 else 0 for t in winners]
    avg_capture_w = sum(captured_w)/len(captured_w) if captured_w else 0
    
    # How much of MAE was the final loss (losers)
    loss_vs_mae = [t['pnl']/t['mae'] if t['mae'] < 0 else 0 for t in losers]
    avg_loss_ratio = sum(loss_vs_mae)/len(loss_vs_mae) if loss_vs_mae else 0
    
    # MFE that was given back (losers who had positive MFE)
    losers_with_mfe = [t for t in losers if t['mfe'] > 0]
    avg_given_back = sum(t['mfe'] for t in losers_with_mfe)/len(losers_with_mfe) if losers_with_mfe else 0
    
    print(f"\n  {label}:")
    print(f"    Winners ({len(winners)}): avg MAE={avg_mae_w:>+.0f}  avg MFE={avg_mfe_w:>+.0f}  capture={avg_capture_w:.1%}")
    print(f"    Losers  ({len(losers)}):  avg MAE={avg_mae_l:>+.0f}  avg MFE={avg_mfe_l:>+.0f}")
    print(f"    Losers with positive MFE: {len(losers_with_mfe)}/{len(losers)} ({len(losers_with_mfe)/len(losers)*100:.0f}%) avg given back: ${avg_given_back:+.0f}")

# ================================================================
# 7. EXIT REASON ANALYSIS
# ================================================================
print(f"\n{'='*80}")
print("7. EXIT REASON ANALYSIS (IS vs OOS)")
print(f"{'='*80}")

for label, trades in [("IS", is_trades), ("OOS", oos_trades)]:
    reasons = defaultdict(lambda: {'pnl': 0, 'count': 0, 'wins': 0})
    for t in trades:
        r = reasons[t['exit_reason']]
        r['pnl'] += t['pnl']
        r['count'] += 1
        if t['is_win']:
            r['wins'] += 1
    
    print(f"\n  {label}:")
    for reason in sorted(reasons.keys()):
        r = reasons[reason]
        wr = r['wins']/r['count']*100 if r['count'] > 0 else 0
        avg = r['pnl']/r['count'] if r['count'] > 0 else 0
        print(f"    {reason:>8}: {r['count']:>4} trades  PnL={r['pnl']:>+8.0f}  WR={wr:>5.1f}%  avg={avg:>+7.1f}")

# ================================================================
# 8. CONSECUTIVE LOSS STREAKS IN OOS
# ================================================================
print(f"\n{'='*80}")
print("8. CONSECUTIVE LOSS STREAKS IN OOS")
print(f"{'='*80}")

streak = 0
max_streak = 0
streak_pnl = 0
streaks = []
for t in oos_trades:
    if not t['is_win']:
        streak += 1
        streak_pnl += t['pnl']
    else:
        if streak > 0:
            streaks.append({'length': streak, 'pnl': streak_pnl})
        streak = 0
        streak_pnl = 0
if streak > 0:
    streaks.append({'length': streak, 'pnl': streak_pnl})

for s in sorted(streaks, key=lambda x: x['pnl']):
    print(f"  Streak {s['length']} losses: PnL={s['pnl']:>+8.0f}")
print(f"  Max consecutive losses: {max(s['length'] for s in streaks) if streaks else 0}")

# ================================================================
# 9. HOLD TIME ANALYSIS
# ================================================================
print(f"\n{'='*80}")
print("9. HOLD TIME vs OUTCOME")
print(f"{'='*80}")

for label, trades in [("IS", is_trades), ("OOS", oos_trades)]:
    # Bucket by hold duration
    buckets = {'<1d': [], '1d': [], '2d': [], '3d': [], '4d': [], '5d+': []}
    for t in trades:
        if t['entry_dt'] and t.get('exit_time'):
            exit_dt = datetime.fromisoformat(t['exit_time'].replace('Z', '+00:00'))
            days = (exit_dt - t['entry_dt']).days
            if days < 1:
                buckets['<1d'].append(t)
            elif days == 1:
                buckets['1d'].append(t)
            elif days == 2:
                buckets['2d'].append(t)
            elif days == 3:
                buckets['3d'].append(t)
            elif days == 4:
                buckets['4d'].append(t)
            else:
                buckets['5d+'].append(t)
    
    print(f"\n  {label}:")
    for bucket, trades_b in buckets.items():
        if not trades_b:
            continue
        wins = sum(1 for t in trades_b if t['is_win'])
        total = len(trades_b)
        pnl = sum(t['pnl'] for t in trades_b)
        wr = wins/total*100 if total > 0 else 0
        avg = pnl/total if total > 0 else 0
        print(f"    {bucket:>4}: {total:>4} trades  PnL={pnl:>+8.0f}  WR={wr:>5.1f}%  avg={avg:>+7.1f}")

# ================================================================
# 10. BIGGEST OOS LOSERS — DEEP DIVE
# ================================================================
print(f"\n{'='*80}")
print("10. TOP 10 BIGGEST OOS LOSERS (by PnL$)")
print(f"{'='*80}")
sorted_losses = sorted(oos_trades, key=lambda t: t['pnl'])
for i, t in enumerate(sorted_losses[:10]):
    date = t['entry_time'][:10]
    exit_date = t['exit_time'][:10] if t['exit_time'] else '?'
    mfe_capture = t['mfe']/t['entry_price']/100 if t['entry_price'] > 0 else 0
    print(f"  #{i+1}: {date} {t['ticker']} {t['option_type']} "
          f"entry=${t['entry_price']:.2f} exit=${t['exit_price']:.2f} "
          f"PnL=${t['pnl']:+.0f} ({t['pnl_pct']:+.1%}) "
          f"MAE=${t['mae']:+.0f} MFE=${t['mfe']:+.0f} "
          f"exitDate={exit_date}")

# ================================================================
# 11. BIGGEST OOS WINNERS
# ================================================================
print(f"\n{'='*80}")
print("11. TOP 10 BIGGEST OOS WINNERS (by PnL$)")
print(f"{'='*80}")
sorted_wins = sorted(oos_trades, key=lambda t: t['pnl'], reverse=True)
for i, t in enumerate(sorted_wins[:10]):
    date = t['entry_time'][:10]
    exit_date = t['exit_time'][:10] if t['exit_time'] else '?'
    print(f"  #{i+1}: {date} {t['ticker']} {t['option_type']} "
          f"entry=${t['entry_price']:.2f} exit=${t['exit_price']:.2f} "
          f"PnL=${t['pnl']:+.0f} ({t['pnl_pct']:+.1%}) "
          f"MAE=${t['mae']:+.0f} MFE=${t['mfe']:+.0f} "
          f"exitDate={exit_date}")

# ================================================================
# 12. KEY PATTERN: LOSERS WITH HIGH MFE (Left money on table)
# ================================================================
print(f"\n{'='*80}")
print("12. OOS LOSERS THAT HAD SIGNIFICANT MFE (unrealized profit given back)")
print(f"{'='*80}")
losers_mfe = [t for t in oos_trades if not t['is_win'] and t['mfe'] > 50]
losers_mfe.sort(key=lambda t: t['mfe'], reverse=True)
total_given_back = sum(t['mfe'] for t in losers_mfe)
print(f"  {len(losers_mfe)} losers had MFE > $50. Total MFE given back: ${total_given_back:+,.0f}")
for t in losers_mfe[:15]:
    date = t['entry_time'][:10]
    print(f"    {date} {t['ticker']}: MFE=${t['mfe']:+.0f} but PnL=${t['pnl']:+.0f} (gave back ${t['mfe']-t['pnl']:,.0f})")

# ================================================================
# 13. REGIME ANALYSIS (SPY direction at entry)
# ================================================================
print(f"\n{'='*80}")
print("13. TEMPORAL CLUSTERING OF LOSSES")
print(f"{'='*80}")
# Find periods with concentrated losses
window = 5
for i in range(len(oos_trades) - window + 1):
    chunk = oos_trades[i:i+window]
    chunk_pnl = sum(t['pnl'] for t in chunk)
    chunk_losses = sum(1 for t in chunk if not t['is_win'])
    if chunk_losses >= 4:  # 4+ losses in 5 trades
        dates = f"{chunk[0]['entry_time'][:10]} to {chunk[-1]['entry_time'][:10]}"
        tickers = ', '.join(t['ticker'] for t in chunk)
        print(f"  Cluster: {dates} -> {chunk_losses}/{window} losses, PnL=${chunk_pnl:+.0f} [{tickers}]")

# ================================================================
# SUMMARY
# ================================================================
print(f"\n{'='*80}")
print("FORENSIC SUMMARY")
print(f"{'='*80}")

print(f"\n  IS:  {len(is_trades)} trades, {sum(1 for t in is_trades if t['is_win'])} wins ({sum(1 for t in is_trades if t['is_win'])/len(is_trades)*100:.0f}%)")
print(f"       Total PnL: ${sum(t['pnl'] for t in is_trades):+,.0f}")
print(f"       Avg trade: ${sum(t['pnl'] for t in is_trades)/len(is_trades):+,.1f}")

print(f"\n  OOS: {len(oos_trades)} trades, {sum(1 for t in oos_trades if t['is_win'])} wins ({sum(1 for t in oos_trades if t['is_win'])/len(oos_trades)*100:.0f}%)")
print(f"       Total PnL: ${sum(t['pnl'] for t in oos_trades):+,.0f}")
print(f"       Avg trade: ${sum(t['pnl'] for t in oos_trades)/len(oos_trades):+,.1f}")

# IS vs OOS key metric deltas
print(f"\n  KEY DELTAS (IS -> OOS):")
print(f"    WR:       {is_ts.get('winRate',0)*100:.1f}% -> {oos_ts.get('winRate',0)*100:.1f}%  (delta {(oos_ts.get('winRate',0)-is_ts.get('winRate',0))*100:+.1f}%)")
print(f"    AvgWin:   ${is_ts.get('averageProfit',0):+.0f} -> ${oos_ts.get('averageProfit',0):+.0f}")
print(f"    AvgLoss:  ${is_ts.get('averageLoss',0):+.0f} -> ${oos_ts.get('averageLoss',0):+.0f}")
print(f"    P/L Rat:  {is_ts.get('profitLossRatio',0):.3f} -> {oos_ts.get('profitLossRatio',0):.3f}")
print(f"    MaxConsW: {is_ts.get('maxConsecutiveWinningTrades',0)} -> {oos_ts.get('maxConsecutiveWinningTrades',0)}")
print(f"    MaxConsL: {is_ts.get('maxConsecutiveLosingTrades',0)} -> {oos_ts.get('maxConsecutiveLosingTrades',0)}")
print(f"    ProfitF:  {is_ts.get('profitFactor',0):.3f} -> {oos_ts.get('profitFactor',0):.3f}")

# Save forensic summary
forensic = {
    "is_trades": len(is_trades),
    "oos_trades": len(oos_trades),
    "is_ticker_breakdown": {k: dict(v) for k, v in is_ticker_pnl.items()},
    "oos_ticker_breakdown": {k: dict(v) for k, v in ticker_pnl.items()},
    "oos_monthly_pnl": dict(monthly_pnl),
    "is_trade_stats": is_ts,
    "oos_trade_stats": oos_ts,
}
with open(f"{OUTPUT_DIR}/g15_forensic_summary.json", "w") as f:
    json.dump(forensic, f, indent=2, default=str)
print(f"\nForensic summary saved to {OUTPUT_DIR}/g15_forensic_summary.json")

print("\nDONE.")
