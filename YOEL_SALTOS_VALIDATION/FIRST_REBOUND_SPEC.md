# Frozen First-Rebound Study

## Hypothesis

The first pullback to a relevant moving average after a trend becomes established
has positive forward expectancy when the daily trend, hourly trend, Bollinger
structure, reversal candle, and liquidity agree.

## Universe and period

- Preferred liquid underlyings: AAPL, AMZN, COIN, DIA, GLD, IWM, META, NFLX,
  NIO, QQQ, SPY, TSLA, USO, XPEV, and LI.
- Frozen test period: 2020-01-01 through 2025-12-31.
- Initial capital: USD 100,000.
- Regular market hours only.

## Signal

- Decision timeframe: exchange-aligned 60-minute bars beginning at 09:30 ET.
- Context timeframe: daily bars.
- Bull trend: hourly `close > SMA20 > SMA40 > SMA100 > SMA200` and daily
  `close > SMA20 > SMA40`. Bear trend is the exact inverse.
- A regime begins when this alignment first becomes true and ends when it breaks.
- Each of SMA20, SMA40, SMA100, and SMA200 can signal only on its first touch in
  that regime.
- A valid touch crosses the average intrabar after the prior hourly bar was at
  least 0.25 ATR away, then closes back on the trend side of the average.
- Bollinger confirmation: SMA20/middle-band slope agrees with direction, the
  close recovers to the trend side of the middle band, and current bandwidth is
  at least 80% of prior bandwidth.
- Candle confirmation: close above open for calls/longs; close below open for
  puts/shorts.
- Relative hourly volume must be at least 0.8 of its 20-hour average.
- If several averages are touched in the same bar, use the longest-period average.

## Stock expression

- Enter after the confirming hourly bar.
- Stop beyond the touched average by 0.5 ATR.
- Target 2R.
- Risk 0.5% of current equity, maximum 10% notional, one position per symbol.
- Exit after five trading sessions if neither barrier is reached.

## Option expression

- Reuse exactly the accepted stock signals; options do not generate signals.
- Long option: nearest slightly ITM call/put, 21-45 DTE, max 1% premium at risk.
- Debit spread: the same long leg plus the nearest OTM short leg in the signal
  direction and same expiry; max 1% debit at risk.
- Exit when the underlying invalidates the frozen stock stop, at 30% option/spread
  profit, or after five sessions / seven DTE, whichever is first.
- No averaging down and no expiry or exercise.

## Sequence

1. Test the stock signal first.
2. If the stock signal fails the gate, option results remain diagnostic and cannot
   be described as a rescue without independent evidence.
3. Compare long options and debit spreads without parameter changes.

## GO gate

Positive return and CAGR, Sharpe >= 0.75, profit factor >= 1.20, drawdown <= 20%,
at least 150 completed trades, at least four of six positive years, at least 55%
positive symbols, and no single symbol contributing more than 35% of total gross
profit.

