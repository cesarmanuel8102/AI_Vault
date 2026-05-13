# region imports
from AlgorithmImports import *
from datetime import datetime, timedelta
# endregion


class TrendPullbackFX(QCAlgorithm):
    """
    Brain V9 — Trend Pullback V1.0

    STRATEGY CARD (Anexo A):
    ─────────────────────────────────────────────
    strategy_name: FX Trend Pullback
    version: V1.0
    family: Trend pullback
    asset_class: Forex
    universe: EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD, NZDUSD
    timeframes: Daily (trend), Daily (entry/exit)
    market_regime_target: Trending (ADX > 25)
    session_constraints: None (daily bars)
    macro_exclusion_rules: FOMC + NFP blackout
    entry_rules:
      1. ADX(14) > adx_min (25) — confirms active trend
      2. Price above EMA(50) for longs, below for shorts — trend direction
      3. Price pulls back to touch/cross EMA(20) — pullback zone
      4. RSI(14) rebounds from 40-50 zone (longs) or 50-60 zone (shorts) — momentum resumes
      5. Entry on next bar after RSI rebounds
    exit_rules:
      1. Chandelier trailing stop: ATR(14) * chandelier_mult below highest high (longs)
      2. Trend reversal: ADX drops below adx_exit OR price crosses EMA(50) against position
      3. Max hold: max_hold_days bars
    stop_rules: ATR-based initial stop at entry - ATR * stop_atr_mult
    target_rules: No fixed target; let winners run with trailing stop
    position_sizing: Fixed fractional (risk_per_trade % of equity per stop distance)
    portfolio_constraints: max_positions concurrent, max_cluster per direction
    execution_assumptions: Daily bars, market orders, Oanda brokerage
    cost_assumptions: Oanda spread model (embedded in backtest)
    hypothesis: In trending FX pairs, pullbacks to EMA(20) when ADX>25 provide
      high-probability entries with tight stops. The trend is macro-driven and
      persists, making pullbacks temporary noise rather than reversals.
    failure_conditions: WR < 40%, P/L < 1.1, or majority of profit from single pair.
    baseline_reference: First version — no parent.
    ─────────────────────────────────────────────

    RESEARCH BASIS:
    - Trend following in FX documented by Asness/Moskowitz/Pedersen (2013)
    - Pullback entries have better risk/reward than breakout entries (smaller stops)
    - ADX as trend filter is well-established
    - EMA confluence as dynamic support/resistance
    """

    VERSION = "TP-V1.0"

    def Initialize(self):
        # ── Backtest window ──
        start_year = int(self.GetParameter("start_year", 2020))
        end_year = int(self.GetParameter("end_year", 2024))
        end_month = int(self.GetParameter("end_month", 12))
        self.SetStartDate(start_year, 1, 1)
        self.SetEndDate(end_year, end_month, 28)
        self.SetCash(10000)
        self.SetBrokerageModel(BrokerageName.OandaBrokerage, AccountType.Margin)

        # ── Parameters ──
        self.ema_fast = int(self.GetParameter("ema_fast", 20))         # Pullback target
        self.ema_slow = int(self.GetParameter("ema_slow", 50))         # Trend direction
        self.adx_min = float(self.GetParameter("adx_min", 25))        # Min ADX for trend
        self.adx_exit = float(self.GetParameter("adx_exit", 20))      # ADX below = trend dead
        self.rsi_period = int(self.GetParameter("rsi_period", 14))
        self.rsi_pullback_low = float(self.GetParameter("rsi_pullback_low", 40))   # RSI zone for long pullback
        self.rsi_pullback_high = float(self.GetParameter("rsi_pullback_high", 60))  # RSI zone for short pullback
        self.atr_period = int(self.GetParameter("atr_period", 14))
        self.stop_atr_mult = float(self.GetParameter("stop_atr_mult", 1.5))       # Initial stop
        self.chandelier_mult = float(self.GetParameter("chandelier_mult", 2.5))    # Trailing stop
        self.risk_per_trade = float(self.GetParameter("risk_per_trade", 0.02))
        self.max_positions = int(self.GetParameter("max_positions", 4))
        self.max_hold_days = int(self.GetParameter("max_hold_days", 15))
        self.max_daily_risk = float(self.GetParameter("max_daily_risk", 0.04))

        # ── FX Majors ──
        self.pair_tickers = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "NZDUSD"]
        self.symbols = {}
        self.pairs_data = {}
        self.ema_fast_ind = {}
        self.ema_slow_ind = {}
        self.adx_ind = {}
        self.rsi_ind = {}
        self.atr_ind = {}

        for ticker in self.pair_tickers:
            forex = self.AddForex(ticker, Resolution.Daily, Market.Oanda)
            forex.SetLeverage(10)
            sym = forex.Symbol
            self.symbols[ticker] = sym

            # Indicators
            self.ema_fast_ind[ticker] = self.EMA(sym, self.ema_fast, Resolution.Daily)
            self.ema_slow_ind[ticker] = self.EMA(sym, self.ema_slow, Resolution.Daily)
            self.adx_ind[ticker] = self.ADX(sym, 14, Resolution.Daily)
            self.rsi_ind[ticker] = self.RSI(sym, self.rsi_period, MovingAverageType.Simple, Resolution.Daily)
            self.atr_ind[ticker] = self.ATR(sym, self.atr_period, MovingAverageType.Simple, Resolution.Daily)

            self.pairs_data[ticker] = {
                "entry_direction": 0,        # +1 long, -1 short
                "entry_price": 0.0,
                "stop_price": 0.0,
                "highest_since_entry": 0.0,
                "lowest_since_entry": 999.0,
                "entry_bar": 0,
                "bars_held": 0,
                "prev_rsi": None,            # For RSI rebound detection
                "prev_price_near_ema": False, # For pullback detection
                "pullback_detected": False,   # True when price touched EMA(20) zone
            }

        # ── Tracking ──
        self.daily_loss = 0.0
        self.last_day = None
        self.bar_count = 0

        # ── Macro blackout ──
        self.macro_blackout_dates = self._build_macro_calendar()

        # ── Friday flatten ──
        self.Schedule.On(
            self.DateRules.Every(DayOfWeek.Friday),
            self.TimeRules.At(16, 50),
            self._friday_flatten
        )

        self.Schedule.On(
            self.DateRules.EveryDay(),
            self.TimeRules.At(16, 55),
            self._eod_log
        )

        # ── Warmup ──
        self.SetWarmUp(timedelta(days=100))

        self.Log(f"[TP] {self.VERSION} | Pairs: {self.pair_tickers}")
        self.Log(f"[TP] EMA fast={self.ema_fast}, slow={self.ema_slow} | ADX min={self.adx_min}")
        self.Log(f"[TP] Risk: {self.risk_per_trade*100}% | Stop: {self.stop_atr_mult}x ATR | Trail: {self.chandelier_mult}x ATR")

    # ═══════════════════════════════════════════════════════════
    #  DAILY SIGNAL LOGIC
    # ═══════════════════════════════════════════════════════════

    def OnData(self, data: Slice):
        if self.IsWarmingUp:
            return

        self.bar_count += 1

        # Daily risk reset
        current_day = self.Time.date()
        if self.last_day != current_day:
            self.daily_loss = 0.0
            self.last_day = current_day

        # Macro blackout
        if current_day in self.macro_blackout_dates:
            return

        for ticker in self.pair_tickers:
            sym = self.symbols[ticker]
            if not data.ContainsKey(sym):
                continue
            bar = data[sym]
            if bar is None:
                continue

            price = float(bar.Close) if hasattr(bar, 'Close') else float(bar.Value)
            high = float(bar.High) if hasattr(bar, 'High') else price
            low = float(bar.Low) if hasattr(bar, 'Low') else price
            pd = self.pairs_data[ticker]

            # Get indicator values
            if not self._indicators_ready(ticker):
                continue

            ema_f = float(self.ema_fast_ind[ticker].Current.Value)
            ema_s = float(self.ema_slow_ind[ticker].Current.Value)
            adx = float(self.adx_ind[ticker].Current.Value)
            rsi = float(self.rsi_ind[ticker].Current.Value)
            atr = float(self.atr_ind[ticker].Current.Value)

            if atr <= 0:
                continue

            # ── Manage existing positions ──
            if self.Portfolio[sym].Invested:
                pd["bars_held"] += 1
                self._manage_position(ticker, price, high, low, adx, ema_s, atr)
                pd["prev_rsi"] = rsi
                continue

            # ── Look for new entries ──
            # Step 1: Is market trending?
            if adx < self.adx_min:
                pd["pullback_detected"] = False
                pd["prev_rsi"] = rsi
                continue

            # Step 2: Determine trend direction
            uptrend = price > ema_s and ema_f > ema_s
            downtrend = price < ema_s and ema_f < ema_s

            if not uptrend and not downtrend:
                pd["pullback_detected"] = False
                pd["prev_rsi"] = rsi
                continue

            # Step 3: Detect pullback to EMA(fast)
            # Price touches or dips below EMA(fast) in uptrend, or above in downtrend
            near_ema_tolerance = atr * 0.3  # Within 30% of ATR of EMA

            if uptrend:
                price_near_ema = low <= ema_f + near_ema_tolerance
                if price_near_ema:
                    pd["pullback_detected"] = True

                # Step 4: Entry — pullback was detected + RSI rebounds from 40-50 zone
                if pd["pullback_detected"] and pd["prev_rsi"] is not None:
                    rsi_was_low = pd["prev_rsi"] <= self.rsi_pullback_high and pd["prev_rsi"] >= self.rsi_pullback_low
                    rsi_rebounds = rsi > pd["prev_rsi"]  # RSI turning up

                    if rsi_was_low and rsi_rebounds and price > ema_f:
                        # ENTRY LONG
                        self._enter_trade(ticker, sym, price, atr, 1, ema_f, ema_s, adx, rsi)
                        pd["pullback_detected"] = False

            elif downtrend:
                price_near_ema = high >= ema_f - near_ema_tolerance
                if price_near_ema:
                    pd["pullback_detected"] = True

                # Step 4: Entry — pullback detected + RSI rebounds from 50-60 zone
                if pd["pullback_detected"] and pd["prev_rsi"] is not None:
                    rsi_was_high = pd["prev_rsi"] >= self.rsi_pullback_low and pd["prev_rsi"] <= self.rsi_pullback_high
                    rsi_rebounds = rsi < pd["prev_rsi"]  # RSI turning down (back to trend)

                    if rsi_was_high and rsi_rebounds and price < ema_f:
                        # ENTRY SHORT
                        self._enter_trade(ticker, sym, price, atr, -1, ema_f, ema_s, adx, rsi)
                        pd["pullback_detected"] = False

            pd["prev_rsi"] = rsi

    # ═══════════════════════════════════════════════════════════
    #  ENTRY
    # ═══════════════════════════════════════════════════════════

    def _enter_trade(self, ticker, sym, price, atr, direction, ema_f, ema_s, adx, rsi):
        """Enter a trend pullback trade."""
        pd = self.pairs_data[ticker]

        # Position limit check
        equity = float(self.Portfolio.TotalPortfolioValue)
        if self.daily_loss >= equity * self.max_daily_risk:
            return

        open_count = sum(1 for t in self.pair_tickers if self.Portfolio[self.symbols[t]].Invested)
        if open_count >= self.max_positions:
            return

        if not self.Securities[sym].Exchange.ExchangeOpen:
            return

        # Calculate stop
        stop_distance = atr * self.stop_atr_mult
        if direction == 1:
            stop_price = price - stop_distance
        else:
            stop_price = price + stop_distance

        # Position sizing
        risk_amount = equity * self.risk_per_trade
        if stop_distance <= 0:
            return
        qty = int(risk_amount / stop_distance)
        qty = (qty // 1000) * 1000
        if qty < 1000:
            return

        # Execute
        self.MarketOrder(sym, qty * direction)
        pd["entry_direction"] = direction
        pd["entry_price"] = price
        pd["stop_price"] = stop_price
        pd["highest_since_entry"] = price if direction == 1 else 0
        pd["lowest_since_entry"] = price if direction == -1 else 999.0
        pd["bars_held"] = 0

        side = "LONG" if direction == 1 else "SHORT"
        self.Log(f"[TP ENTRY {side}] {ticker} | Price={price:.5f} | EMA20={ema_f:.5f} | "
                 f"EMA50={ema_s:.5f} | ADX={adx:.1f} | RSI={rsi:.1f} | "
                 f"Stop={stop_price:.5f} | Qty={qty * direction} | ATR={atr:.5f}")

    # ═══════════════════════════════════════════════════════════
    #  POSITION MANAGEMENT
    # ═══════════════════════════════════════════════════════════

    def _manage_position(self, ticker, price, high, low, adx, ema_s, atr):
        """Manage open position: trailing stop, trend reversal, max hold."""
        pd = self.pairs_data[ticker]
        sym = self.symbols[ticker]

        if not self.Securities[sym].Exchange.ExchangeOpen:
            return

        # ── Max hold check ──
        if pd["bars_held"] >= self.max_hold_days:
            pnl = float(self.Portfolio[sym].UnrealizedProfit)
            self.Liquidate(sym)
            if pnl < 0:
                self.daily_loss += abs(pnl)
            self.Log(f"[TP MAX HOLD] {ticker} | Bars={pd['bars_held']} | PnL=${pnl:.2f}")
            pd["entry_direction"] = 0
            return

        # ── Trend reversal exit ──
        if pd["entry_direction"] == 1 and price < ema_s:
            pnl = float(self.Portfolio[sym].UnrealizedProfit)
            self.Liquidate(sym)
            if pnl < 0:
                self.daily_loss += abs(pnl)
            self.Log(f"[TP TREND REV] {ticker} | Price {price:.5f} < EMA50 {ema_s:.5f} | PnL=${pnl:.2f}")
            pd["entry_direction"] = 0
            return

        if pd["entry_direction"] == -1 and price > ema_s:
            pnl = float(self.Portfolio[sym].UnrealizedProfit)
            self.Liquidate(sym)
            if pnl < 0:
                self.daily_loss += abs(pnl)
            self.Log(f"[TP TREND REV] {ticker} | Price {price:.5f} > EMA50 {ema_s:.5f} | PnL=${pnl:.2f}")
            pd["entry_direction"] = 0
            return

        # ── ADX death exit ──
        if adx < self.adx_exit:
            pnl = float(self.Portfolio[sym].UnrealizedProfit)
            self.Liquidate(sym)
            if pnl < 0:
                self.daily_loss += abs(pnl)
            self.Log(f"[TP ADX EXIT] {ticker} | ADX={adx:.1f} < {self.adx_exit} | PnL=${pnl:.2f}")
            pd["entry_direction"] = 0
            return

        # ── Chandelier trailing stop ──
        if pd["entry_direction"] == 1:
            if high > pd["highest_since_entry"]:
                pd["highest_since_entry"] = high
            new_stop = pd["highest_since_entry"] - atr * self.chandelier_mult
            if new_stop > pd["stop_price"]:
                pd["stop_price"] = new_stop

            if low <= pd["stop_price"]:
                pnl = float(self.Portfolio[sym].UnrealizedProfit)
                self.Liquidate(sym)
                if pnl < 0:
                    self.daily_loss += abs(pnl)
                self.Log(f"[TP STOP LONG] {ticker} | Stop={pd['stop_price']:.5f} | PnL=${pnl:.2f}")
                pd["entry_direction"] = 0

        elif pd["entry_direction"] == -1:
            if low < pd["lowest_since_entry"]:
                pd["lowest_since_entry"] = low
            new_stop = pd["lowest_since_entry"] + atr * self.chandelier_mult
            if new_stop < pd["stop_price"]:
                pd["stop_price"] = new_stop

            if high >= pd["stop_price"]:
                pnl = float(self.Portfolio[sym].UnrealizedProfit)
                self.Liquidate(sym)
                if pnl < 0:
                    self.daily_loss += abs(pnl)
                self.Log(f"[TP STOP SHORT] {ticker} | Stop={pd['stop_price']:.5f} | PnL=${pnl:.2f}")
                pd["entry_direction"] = 0

    # ═══════════════════════════════════════════════════════════
    #  HELPERS
    # ═══════════════════════════════════════════════════════════

    def _indicators_ready(self, ticker):
        """Check all indicators are warmed up."""
        return (self.ema_fast_ind[ticker].IsReady and
                self.ema_slow_ind[ticker].IsReady and
                self.adx_ind[ticker].IsReady and
                self.rsi_ind[ticker].IsReady and
                self.atr_ind[ticker].IsReady)

    def _friday_flatten(self):
        """Flatten all positions before weekend."""
        if self.IsWarmingUp:
            return
        for ticker in self.pair_tickers:
            sym = self.symbols[ticker]
            if self.Portfolio[sym].Invested:
                if self.Securities[sym].Exchange.ExchangeOpen:
                    pnl = float(self.Portfolio[sym].UnrealizedProfit)
                    self.Liquidate(sym)
                    self.Log(f"[TP FRIDAY] {ticker} | PnL=${pnl:.2f}")
                    self.pairs_data[ticker]["entry_direction"] = 0

    def _eod_log(self):
        """Daily summary."""
        equity = float(self.Portfolio.TotalPortfolioValue)
        positions = []
        for ticker in self.pair_tickers:
            sym = self.symbols[ticker]
            if self.Portfolio[sym].Invested:
                h = self.Portfolio[sym]
                pnl = float(h.UnrealizedProfit)
                pd = self.pairs_data[ticker]
                positions.append(f"{ticker}={'L' if h.IsLong else 'S'}(${pnl:.0f},d{pd['bars_held']})")
        pos_str = ", ".join(positions) if positions else "FLAT"
        self.Log(f"[EOD] Equity=${equity:.2f} | {pos_str}")

    # ═══════════════════════════════════════════════════════════
    #  MACRO CALENDAR
    # ═══════════════════════════════════════════════════════════

    def _build_macro_calendar(self):
        """FOMC + NFP dates 2020-2024."""
        dates = set()
        fomc = [
            "2020-01-29", "2020-03-03", "2020-03-15", "2020-04-29", "2020-06-10",
            "2020-07-29", "2020-09-16", "2020-11-05", "2020-12-16",
            "2021-01-27", "2021-03-17", "2021-04-28", "2021-06-16",
            "2021-07-28", "2021-09-22", "2021-11-03", "2021-12-15",
            "2022-01-26", "2022-03-16", "2022-05-04", "2022-06-15",
            "2022-07-27", "2022-09-21", "2022-11-02", "2022-12-14",
            "2023-02-01", "2023-03-22", "2023-05-03", "2023-06-14",
            "2023-07-26", "2023-09-20", "2023-11-01", "2023-12-13",
            "2024-01-31", "2024-03-20", "2024-05-01", "2024-06-12",
            "2024-07-31", "2024-09-18", "2024-11-07", "2024-12-18",
        ]
        nfp = []
        for year in range(2020, 2025):
            for month in range(1, 13):
                d = datetime(year, month, 1)
                days_until_fri = (4 - d.weekday()) % 7
                first_friday = d + timedelta(days=days_until_fri)
                nfp.append(first_friday.strftime("%Y-%m-%d"))
        for d_str in fomc + nfp:
            try:
                dates.add(datetime.strptime(d_str, "%Y-%m-%d").date())
            except ValueError:
                pass
        return dates

    # ═══════════════════════════════════════════════════════════
    #  EVENT HANDLERS
    # ═══════════════════════════════════════════════════════════

    def OnOrderEvent(self, orderEvent):
        if orderEvent.Status == OrderStatus.Filled:
            sym = orderEvent.Symbol
            ticker = str(sym).split(" ")[0] if " " in str(sym) else str(sym)
            self.Log(f"[ORDER] {ticker} | Qty={orderEvent.FillQuantity} @ "
                     f"{orderEvent.FillPrice:.5f} | Fee={orderEvent.OrderFee}")

    def OnEndOfAlgorithm(self):
        equity = float(self.Portfolio.TotalPortfolioValue)
        total_return = (equity - 10000) / 10000 * 100
        self.Log(f"[FINAL] {self.VERSION} | Equity=${equity:.2f} | Return={total_return:.2f}%")
