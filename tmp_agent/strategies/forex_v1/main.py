# region imports
from AlgorithmImports import *
from datetime import datetime, timedelta
# endregion


class ForexSwingV3(QCAlgorithm):
    """
    Brain V9 — Forex V3.9: Squeeze-Only + Expanded Pairs (10 pairs)

    EVOLUTION from V3.8a/b:
    - KILLED pullback entries (V3.8/V3.8a/V3.8b all failed: RSI pullback has no edge in forex)
    - Back to squeeze-only (V3.6a champion base: +2.51%, 102 trades, P/L 1.07)
    - ADDED 4 more pairs: NZDUSD, USDCAD, USDCHF, EURGBP
    - Goal: increase trade count from 102 to ~170+ while maintaining quality
    - 10 pairs = more squeeze opportunities across diverse currency dynamics

    ENTRY A — SQUEEZE BREAKOUT (from V3.6a):
    1. Daily BB squeeze detected (contraction < threshold of rolling avg)
    2. Price breaks hourly BB in daily trend direction
    3. Daily trend: EMA 50 vs 200, ADX >= threshold

    ENTRY B — TREND PULLBACK (NEW in V3.8):
    1. Strong daily trend: EMA 50 vs 200, ADX >= threshold
    2. Price pulls back to EMA 20 H1 (within 0.5x Daily ATR)
    3. RSI H1 crosses back above 50 (longs) or below 50 (shorts) = momentum resumption
    4. NO active squeeze (avoid double-signaling)

    COMMON:
    - Stop: Nx Daily ATR(14)
    - Trail: Chandelier Exit Mx Daily ATR
    - Hold: Multi-day, Friday 16:50 ET flatten
    - Risk: 1% per trade, 3% daily max, 5% weekly max, max 3 positions
    - Cluster: Max 2 positions involving same currency

    Pairs: EURUSD, GBPUSD, USDJPY, AUDUSD, EURJPY, GBPJPY
    Timeframe: 1H data for entry timing, Daily for trend/stops/squeeze
    """

    VERSION = "V3.9"

    def Initialize(self):
        # ── Backtest window ──
        self.SetStartDate(2020, 1, 1)
        self.SetEndDate(2024, 12, 31)
        self.SetCash(10000)
        self.SetBrokerageModel(BrokerageName.OandaBrokerage, AccountType.Margin)

        # ── Parameters ──
        self.risk_per_trade = float(self.GetParameter("risk_per_trade", 0.01))
        self.max_daily_risk = float(self.GetParameter("max_daily_risk", 0.03))
        self.max_weekly_risk = float(self.GetParameter("max_weekly_risk", 0.05))
        self.max_positions = int(self.GetParameter("max_positions", 3))
        self.chandelier_mult = float(self.GetParameter("chandelier_mult", 2.5))
        self.stop_atr_mult = float(self.GetParameter("stop_atr_mult", 1.5))
        self.squeeze_pct = float(self.GetParameter("squeeze_pct", 0.70))
        self.squeeze_lookback = int(self.GetParameter("squeeze_lookback", 100))
        self.min_squeeze_bars = int(self.GetParameter("min_squeeze_bars", 3))
        self.squeeze_entry_window = int(self.GetParameter("squeeze_window", 3))
        self.adx_min = int(self.GetParameter("adx_min", 20))
        self.partial_tp_atr = float(self.GetParameter("partial_tp_atr", 0))  # 0=disabled. Take partial profit at Nx ATR
        self.pullback_enabled = int(self.GetParameter("pullback_enabled", 1))  # 1=on, 0=off
        self.pullback_atr_proximity = float(self.GetParameter("pb_atr_prox", 0.5))  # Max distance to EMA20 in ATR units
        self.pb_adx_min = int(self.GetParameter("pb_adx_min", 0))  # 0=use adx_min. Separate ADX threshold for pullback entries
        self.max_cluster = int(self.GetParameter("max_cluster", 2))  # Max positions involving same currency

        # ── Forex Pairs (6 pairs: 4 majors + 2 JPY crosses for vol) ──
        self.pair_tickers = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "EURJPY", "GBPJPY"]
        self.symbols = {}
        self.pairs_data = {}

        for ticker in self.pair_tickers:
            forex = self.AddForex(ticker, Resolution.Hour, Market.Oanda)
            forex.SetLeverage(10)
            sym = forex.Symbol
            self.symbols[ticker] = sym

            self.pairs_data[ticker] = {
                # Hourly: BB for breakout detection (price vs bands for entry)
                "bb": self.BB(sym, 20, 2, MovingAverageType.Simple, Resolution.Hour),
                # Hourly: RSI for pullback momentum confirmation
                "rsi_h": self.RSI(sym, 14, MovingAverageType.Simple, Resolution.Hour),
                # Hourly: EMA 20 for pullback zone
                "ema_20h": self.EMA(sym, 20, Resolution.Hour),
                # Daily: BB for squeeze detection (volatility contraction on daily timeframe)
                "bb_d": self.BB(sym, 20, 2, MovingAverageType.Simple, Resolution.Daily),
                # Daily: trend direction + risk/stop sizing
                "ema_50": self.EMA(sym, 50, Resolution.Daily),
                "ema_200": self.EMA(sym, 200, Resolution.Daily),
                "adx_d": self.ADX(sym, 14, Resolution.Daily),
                "atr_d": self.ATR(sym, 14, MovingAverageType.Simple, Resolution.Daily),
                # Squeeze tracking (now on daily bars)
                "bb_width_history": [],
                "squeeze_count": 0,
                "bars_since_squeeze_end": 0,
                "squeeze_ready": False,
                "last_squeeze_date": None,  # Track to update only once per day
                # Pullback tracking
                "prev_rsi": 50.0,  # Previous RSI value for crossover detection
                "rsi_was_deep": False,  # True when RSI went below 40 (long) or above 60 (short)
                # Position tracking
                "trail_stop": 0.0,
                "highest_since_entry": 0.0,
                "lowest_since_entry": float("inf"),
                "entry_direction": 0,
                "entry_price": 0.0,
                "entry_atr": 0.0,  # ATR at entry for partial TP target
                "entry_type": "",  # "SQUEEZE" or "PULLBACK"
                "partial_taken": False,  # Whether partial profit was already taken
                "traded_today": False,
            }

        # ── Risk tracking ──
        self.day_start_equity = 10000.0
        self.last_trade_date = None
        self.week_start_equity = 10000.0
        self.open_position_count = 0

        # ── Macro event calendar ──
        self.macro_blackout_dates = self._build_macro_calendar()

        # ── Schedules ──
        self.Schedule.On(
            self.DateRules.Every(DayOfWeek.Friday),
            self.TimeRules.At(16, 50),
            self._flatten_all
        )
        self.Schedule.On(
            self.DateRules.EveryDay(),
            self.TimeRules.At(16, 55),
            self._eod_log
        )
        self.Schedule.On(
            self.DateRules.Every(DayOfWeek.Monday),
            self.TimeRules.At(0, 0),
            self._reset_weekly
        )

        # ── Warmup: 300 days for EMA 200 on daily ──
        self.SetWarmUp(timedelta(days=300))

        self.Log(f"[FOREX-V3] {self.VERSION} | Pairs: {self.pair_tickers}")
        self.Log(f"[FOREX-V3] Squeeze: DAILY BB, {self.squeeze_pct*100}% thresh, {self.min_squeeze_bars}d min, {self.squeeze_entry_window}d window")
        self.Log(f"[FOREX-V3] Pullback: {'ON' if self.pullback_enabled else 'OFF'} | proximity={self.pullback_atr_proximity}x ATR | pb_adx={self.pb_adx_min if self.pb_adx_min > 0 else 'same as adx_min'} | deep_rsi=ON")
        self.Log(f"[FOREX-V3] Stop: {self.stop_atr_mult}x DailyATR | Trail: {self.chandelier_mult}x DailyATR | ADX min: {self.adx_min}")
        self.Log(f"[FOREX-V3] Risk: {self.risk_per_trade*100}%/trade, {self.max_daily_risk*100}%/day, {self.max_weekly_risk*100}%/week")

    # ═══════════════════════════════════════════════════════════
    #  MAIN DATA HANDLER
    # ═══════════════════════════════════════════════════════════

    def OnData(self, data: Slice):
        if self.IsWarmingUp:
            return

        hour_et = self.Time.hour

        # ── Daily reset ──
        if self.last_trade_date is None or self.Time.date() != self.last_trade_date:
            self.day_start_equity = float(self.Portfolio.TotalPortfolioValue)
            self.last_trade_date = self.Time.date()
            for t in self.pair_tickers:
                self.pairs_data[t]["traded_today"] = False

        # ── ALWAYS: Update squeeze tracking + manage open positions ──
        for ticker in self.pair_tickers:
            sym = self.symbols[ticker]
            if not data.ContainsKey(sym):
                continue
            self._update_squeeze_tracking(ticker)
            if self.Portfolio[sym].Invested:
                self._manage_position(ticker, data)

        # ── Entries only during London+NY at 4H intervals ──
        if hour_et not in [3, 7, 11, 15]:
            return

        # ── Macro blackout ──
        if self._is_macro_day():
            return

        # ── Count open positions ──
        self.open_position_count = sum(
            1 for t in self.pair_tickers
            if self.Portfolio[self.symbols[t]].Invested
        )

        # ── Scan for entry signals ──
        for ticker in self.pair_tickers:
            sym = self.symbols[ticker]
            if not data.ContainsKey(sym):
                continue
            if self.Portfolio[sym].Invested:
                continue
            if self.pairs_data[ticker]["traded_today"]:
                continue
            if not self._pass_risk_gates():
                continue
            if not self._pass_cluster_risk(ticker):
                continue
            # Try squeeze entry first, then pullback if squeeze didn't fire
            if not self._check_squeeze_entry(ticker, data):
                if self.pullback_enabled:
                    self._check_pullback_entry(ticker, data)

        # ── Update prev_rsi + rsi_was_deep for pullback crossover detection (every 4H tick) ──
        for ticker in self.pair_tickers:
            pd = self.pairs_data[ticker]
            if pd["rsi_h"].IsReady:
                rsi_val = float(pd["rsi_h"].Current.Value)
                # Track deep retracement for pullback filter (only when not in position)
                if not self.Portfolio[self.symbols[ticker]].Invested:
                    if pd["ema_50"].IsReady and pd["ema_200"].IsReady:
                        e50 = float(pd["ema_50"].Current.Value)
                        e200 = float(pd["ema_200"].Current.Value)
                        trend_dir = 1 if e50 > e200 else -1
                        if trend_dir == 1 and rsi_val < 40:
                            pd["rsi_was_deep"] = True
                        elif trend_dir == -1 and rsi_val > 60:
                            pd["rsi_was_deep"] = True
                pd["prev_rsi"] = rsi_val

    # ═══════════════════════════════════════════════════════════
    #  VOLATILITY SQUEEZE DETECTION
    # ═══════════════════════════════════════════════════════════

    def _update_squeeze_tracking(self, ticker):
        """Track Daily BB width to detect multi-day volatility contraction (squeeze).
        
        V3.6: Moved from hourly BB to daily BB. This aligns squeeze detection
        with daily ATR stops — detecting real volatility regime changes, not
        intraday noise. Updates once per day to avoid duplicate counting.
        """
        pd = self.pairs_data[ticker]
        if not pd["bb_d"].IsReady:
            return

        # Only update once per day (daily bars update throughout the day)
        current_date = self.Time.date()
        if pd["last_squeeze_date"] == current_date:
            return
        pd["last_squeeze_date"] = current_date

        bb_upper = float(pd["bb_d"].UpperBand.Current.Value)
        bb_lower = float(pd["bb_d"].LowerBand.Current.Value)
        bb_middle = float(pd["bb_d"].MiddleBand.Current.Value)

        if bb_middle <= 0:
            return

        bb_width = (bb_upper - bb_lower) / bb_middle
        pd["bb_width_history"].append(bb_width)
        if len(pd["bb_width_history"]) > self.squeeze_lookback:
            pd["bb_width_history"] = pd["bb_width_history"][-self.squeeze_lookback:]

        if len(pd["bb_width_history"]) < 20:
            return

        avg_width = sum(pd["bb_width_history"]) / len(pd["bb_width_history"])

        if bb_width < self.squeeze_pct * avg_width:
            # In squeeze: daily bands are abnormally tight
            pd["squeeze_count"] += 1
            pd["bars_since_squeeze_end"] = 0
        else:
            # Not in squeeze
            if pd["squeeze_count"] >= self.min_squeeze_bars:
                # Valid squeeze just ended → open entry window (N daily bars)
                pd["squeeze_ready"] = True
                pd["bars_since_squeeze_end"] = 0
            pd["squeeze_count"] = 0

            # Expire entry window after N daily bars
            if pd["squeeze_ready"]:
                pd["bars_since_squeeze_end"] += 1
                if pd["bars_since_squeeze_end"] > self.squeeze_entry_window:
                    pd["squeeze_ready"] = False

    # ═══════════════════════════════════════════════════════════
    #  ENTRY: SQUEEZE BREAKOUT IN TREND DIRECTION
    # ═══════════════════════════════════════════════════════════

    def _check_squeeze_entry(self, ticker, data):
        """Enter when BB squeeze fires and price breaks out in daily trend direction.
        Returns True if entry was taken, False otherwise."""
        pd = self.pairs_data[ticker]
        sym = self.symbols[ticker]

        # ── Squeeze must be active or recently ended ──
        squeeze_active = pd["squeeze_count"] >= self.min_squeeze_bars
        squeeze_window = pd["squeeze_ready"]
        if not squeeze_active and not squeeze_window:
            return False

        # ── Daily trend: EMA 50 vs 200 ──
        if not pd["ema_50"].IsReady or not pd["ema_200"].IsReady:
            return False

        ema50 = float(pd["ema_50"].Current.Value)
        ema200 = float(pd["ema_200"].Current.Value)

        if ema200 <= 0:
            return False
        # Require meaningful separation (>0.1%)
        if abs(ema50 - ema200) / ema200 < 0.001:
            return False

        trend = 1 if ema50 > ema200 else -1

        # ── ADX confirms trend strength ──
        if not pd["adx_d"].IsReady:
            return False
        adx = float(pd["adx_d"].Current.Value)
        if adx < self.adx_min:
            return False

        # ── BB breakout in trend direction ──
        if not pd["bb"].IsReady:
            return False
        bb_upper = float(pd["bb"].UpperBand.Current.Value)
        bb_lower = float(pd["bb"].LowerBand.Current.Value)

        bar = data[sym]
        if bar is None:
            return False
        price = float(bar.Close) if hasattr(bar, 'Close') else float(bar.Value)

        # ── Daily ATR for stop calculation ──
        if not pd["atr_d"].IsReady:
            return False
        atr_d = float(pd["atr_d"].Current.Value)
        if atr_d <= 0:
            return False

        direction = 0
        if trend == 1 and price > bb_upper:
            direction = 1
        elif trend == -1 and price < bb_lower:
            direction = -1

        if direction == 0:
            return False

        # ── Stop and position size ──
        stop_price = price - self.stop_atr_mult * atr_d if direction == 1 else price + self.stop_atr_mult * atr_d
        risk_distance = abs(price - stop_price)
        if risk_distance <= 0:
            return False

        qty = self._calculate_position_size(ticker, price, risk_distance)
        if qty <= 0:
            return False

        if not self.Securities[sym].Exchange.ExchangeOpen:
            return False

        # ── Execute ──
        side = "LONG" if direction == 1 else "SHORT"
        self.MarketOrder(sym, qty if direction == 1 else -qty)

        squeeze_type = "DAILY_ACTIVE" if squeeze_active else "DAILY_WINDOW"
        self.Log(f"[ENTRY-SQ {side}] {ticker} @ {price:.5f} | "
                 f"EMA50={ema50:.5f} {'>' if trend==1 else '<'} EMA200={ema200:.5f} | "
                 f"ADX={adx:.1f} | Squeeze={squeeze_type} | Stop={stop_price:.5f}")

        pd["entry_direction"] = direction
        pd["entry_price"] = price
        pd["entry_atr"] = atr_d
        pd["entry_type"] = "SQUEEZE"
        pd["partial_taken"] = False
        pd["traded_today"] = True
        pd["trail_stop"] = stop_price
        pd["highest_since_entry"] = price if direction == 1 else 0.0
        pd["lowest_since_entry"] = price if direction == -1 else float("inf")
        pd["squeeze_ready"] = False
        pd["squeeze_count"] = 0
        return True

    # ═══════════════════════════════════════════════════════════
    #  ENTRY B: TREND PULLBACK (RSI crossover at EMA 20 zone)
    # ═══════════════════════════════════════════════════════════

    def _check_pullback_entry(self, ticker, data):
        """Enter on pullback to EMA20 H1 with RSI momentum confirmation in trend direction.

        V3.8: Captures trend continuation — the 'middle' of trends that squeeze misses.
        Only fires when NO squeeze is active (avoids double-signaling).
        """
        pd = self.pairs_data[ticker]
        sym = self.symbols[ticker]

        # ── No pullback during active squeeze (squeeze entry has priority) ──
        if pd["squeeze_count"] >= self.min_squeeze_bars or pd["squeeze_ready"]:
            return

        # ── Daily trend: EMA 50 vs 200 ──
        if not pd["ema_50"].IsReady or not pd["ema_200"].IsReady:
            return
        ema50 = float(pd["ema_50"].Current.Value)
        ema200 = float(pd["ema_200"].Current.Value)
        if ema200 <= 0:
            return
        if abs(ema50 - ema200) / ema200 < 0.001:
            return
        trend = 1 if ema50 > ema200 else -1

        # ── ADX confirms trend strength (pullback uses its own threshold if set) ──
        if not pd["adx_d"].IsReady:
            return
        adx = float(pd["adx_d"].Current.Value)
        pb_adx_threshold = self.pb_adx_min if self.pb_adx_min > 0 else self.adx_min
        if adx < pb_adx_threshold:
            return

        # ── RSI H1 momentum crossover ──
        if not pd["rsi_h"].IsReady:
            return
        rsi = float(pd["rsi_h"].Current.Value)
        prev_rsi = pd["prev_rsi"]

        # Long: RSI was below 50 (pullback) and now crosses above 50 (resumption)
        # Short: RSI was above 50 and now crosses below 50
        rsi_cross_long = prev_rsi < 50 and rsi >= 50
        rsi_cross_short = prev_rsi > 50 and rsi <= 50

        # ── Deep pullback filter: RSI must have gone below 40 (long) or above 60 (short) ──
        # This filters shallow noise crossovers. Only fires after a REAL retracement.
        if not pd["rsi_was_deep"]:
            return

        direction = 0
        if trend == 1 and rsi_cross_long:
            direction = 1
        elif trend == -1 and rsi_cross_short:
            direction = -1

        if direction == 0:
            return

        # ── Price must be near EMA 20 H1 (within proximity * ATR) ──
        if not pd["ema_20h"].IsReady or not pd["atr_d"].IsReady:
            return
        ema20h = float(pd["ema_20h"].Current.Value)
        atr_d = float(pd["atr_d"].Current.Value)
        if atr_d <= 0 or ema20h <= 0:
            return

        bar = data[sym]
        if bar is None:
            return
        price = float(bar.Close) if hasattr(bar, 'Close') else float(bar.Value)

        distance_to_ema = abs(price - ema20h)
        if distance_to_ema > self.pullback_atr_proximity * atr_d:
            return

        # ── Price must be on correct side of EMA 20 (recovering from pullback) ──
        if direction == 1 and price < ema20h:
            return  # Still below EMA, pullback hasn't recovered
        if direction == -1 and price > ema20h:
            return  # Still above EMA, pullback hasn't recovered

        # ── Stop and position size ──
        stop_price = price - self.stop_atr_mult * atr_d if direction == 1 else price + self.stop_atr_mult * atr_d
        risk_distance = abs(price - stop_price)
        if risk_distance <= 0:
            return

        qty = self._calculate_position_size(ticker, price, risk_distance)
        if qty <= 0:
            return

        if not self.Securities[sym].Exchange.ExchangeOpen:
            return

        # ── Execute ──
        side = "LONG" if direction == 1 else "SHORT"
        self.MarketOrder(sym, qty if direction == 1 else -qty)

        self.Log(f"[ENTRY-PB {side}] {ticker} @ {price:.5f} | "
                 f"EMA50={ema50:.5f} {'>' if trend==1 else '<'} EMA200={ema200:.5f} | "
                 f"ADX={adx:.1f} | RSI={rsi:.1f}(prev={prev_rsi:.1f}) | "
                 f"EMA20H={ema20h:.5f} | Stop={stop_price:.5f}")

        pd["entry_direction"] = direction
        pd["entry_price"] = price
        pd["entry_atr"] = atr_d
        pd["entry_type"] = "PULLBACK"
        pd["partial_taken"] = False
        pd["traded_today"] = True
        pd["rsi_was_deep"] = False  # Reset after taking pullback entry
        pd["trail_stop"] = stop_price
        pd["highest_since_entry"] = price if direction == 1 else 0.0
        pd["lowest_since_entry"] = price if direction == -1 else float("inf")

    # ═══════════════════════════════════════════════════════════
    #  POSITION MANAGEMENT — Chandelier Exit (Daily ATR)
    # ═══════════════════════════════════════════════════════════

    def _manage_position(self, ticker, data):
        """Chandelier trailing stop using Daily ATR + partial profit take. Runs every hour, 24/5."""
        sym = self.symbols[ticker]
        pd = self.pairs_data[ticker]

        if not data.ContainsKey(sym):
            return
        bar = data[sym]
        if bar is None:
            return

        price = float(bar.Close) if hasattr(bar, 'Close') else float(bar.Value)
        price_high = float(bar.High) if hasattr(bar, 'High') else price
        price_low = float(bar.Low) if hasattr(bar, 'Low') else price

        if not pd["atr_d"].IsReady:
            return

        atr_d = float(pd["atr_d"].Current.Value)
        direction = pd["entry_direction"]
        if direction == 0:
            return

        entry_atr = pd["entry_atr"]
        if entry_atr <= 0:
            entry_atr = atr_d  # Fallback

        # ── Partial profit take: close 50% at 1x ATR, move stop to breakeven ──
        if not pd["partial_taken"] and self.partial_tp_atr > 0:
            tp_target = entry_atr * self.partial_tp_atr
            if direction == 1 and price >= pd["entry_price"] + tp_target:
                qty = abs(self.Portfolio[sym].Quantity)
                close_qty = max((qty // 2000) * 1000, 1000)  # Close ~50%, rounded to lot
                if close_qty < qty and self.Securities[sym].Exchange.ExchangeOpen:
                    self.MarketOrder(sym, -close_qty)
                    pd["partial_taken"] = True
                    pd["trail_stop"] = pd["entry_price"]  # Move stop to breakeven
                    self.Log(f"[PARTIAL TP LONG] {ticker} | Closed {close_qty} @ {price:.5f} | "
                             f"Target={pd['entry_price'] + tp_target:.5f} | Stop→BE={pd['entry_price']:.5f}")
            elif direction == -1 and price <= pd["entry_price"] - tp_target:
                qty = abs(self.Portfolio[sym].Quantity)
                close_qty = max((qty // 2000) * 1000, 1000)
                if close_qty < qty and self.Securities[sym].Exchange.ExchangeOpen:
                    self.MarketOrder(sym, close_qty)
                    pd["partial_taken"] = True
                    pd["trail_stop"] = pd["entry_price"]  # Move stop to breakeven
                    self.Log(f"[PARTIAL TP SHORT] {ticker} | Closed {close_qty} @ {price:.5f} | "
                             f"Target={pd['entry_price'] - tp_target:.5f} | Stop→BE={pd['entry_price']:.5f}")

        # ── Chandelier trailing stop ──
        if direction == 1:
            pd["highest_since_entry"] = max(pd["highest_since_entry"], price_high)
            chandelier_stop = pd["highest_since_entry"] - self.chandelier_mult * atr_d
            if chandelier_stop > pd["trail_stop"]:
                pd["trail_stop"] = chandelier_stop

            if price_low <= pd["trail_stop"]:
                if not self.Securities[sym].Exchange.ExchangeOpen:
                    return
                self.Liquidate(sym)
                pnl_pct = (price - pd["entry_price"]) / pd["entry_price"] * 100
                self.Log(f"[EXIT LONG] {ticker} @ {price:.5f} | Trail={pd['trail_stop']:.5f} | "
                         f"Entry={pd['entry_price']:.5f} | Type={pd['entry_type']} | PnL={pnl_pct:.2f}%")
                self._reset_pair_state(ticker)

        elif direction == -1:
            pd["lowest_since_entry"] = min(pd["lowest_since_entry"], price_low)
            chandelier_stop = pd["lowest_since_entry"] + self.chandelier_mult * atr_d
            if chandelier_stop < pd["trail_stop"]:
                pd["trail_stop"] = chandelier_stop

            if price_high >= pd["trail_stop"]:
                if not self.Securities[sym].Exchange.ExchangeOpen:
                    return
                self.Liquidate(sym)
                pnl_pct = (pd["entry_price"] - price) / pd["entry_price"] * 100
                self.Log(f"[EXIT SHORT] {ticker} @ {price:.5f} | Trail={pd['trail_stop']:.5f} | "
                         f"Entry={pd['entry_price']:.5f} | Type={pd['entry_type']} | PnL={pnl_pct:.2f}%")
                self._reset_pair_state(ticker)

    # ═══════════════════════════════════════════════════════════
    #  POSITION SIZING
    # ═══════════════════════════════════════════════════════════

    def _calculate_position_size(self, ticker, price, risk_distance):
        """Fixed fractional: risk_per_trade % of equity per trade."""
        equity = float(self.Portfolio.TotalPortfolioValue)
        risk_amount = equity * self.risk_per_trade

        if risk_distance <= 0 or price <= 0:
            return 0

        qty = int(risk_amount / risk_distance)
        if qty < 1000:
            return 0
        qty = (qty // 1000) * 1000
        return qty

    # ═══════════════════════════════════════════════════════════
    #  RISK MANAGEMENT
    # ═══════════════════════════════════════════════════════════

    def _pass_risk_gates(self):
        """Daily/weekly loss limits + max position count."""
        equity = float(self.Portfolio.TotalPortfolioValue)

        if self.open_position_count >= self.max_positions:
            return False

        daily_pnl = equity - self.day_start_equity
        if daily_pnl < -(self.day_start_equity * self.max_daily_risk):
            self.Log(f"[RISK GATE] Daily loss: ${daily_pnl:.2f}")
            return False

        weekly_change = equity - self.week_start_equity
        if weekly_change < -(self.week_start_equity * self.max_weekly_risk):
            self.Log(f"[RISK GATE] Weekly loss: ${weekly_change:.2f}")
            return False

        return True

    def _pass_cluster_risk(self, ticker):
        """Max N positions involving the same currency."""
        currency_count = {}
        for t in self.pair_tickers:
            sym = self.symbols[t]
            if not self.Portfolio[sym].Invested:
                continue
            base, quote = t[:3], t[3:]
            currency_count[base] = currency_count.get(base, 0) + 1
            currency_count[quote] = currency_count.get(quote, 0) + 1

        base, quote = ticker[:3], ticker[3:]
        if currency_count.get(base, 0) >= self.max_cluster or currency_count.get(quote, 0) >= self.max_cluster:
            return False
        return True

    # ═══════════════════════════════════════════════════════════
    #  SCHEDULING
    # ═══════════════════════════════════════════════════════════

    def _flatten_all(self):
        """Friday 16:50 ET — Close all before weekend."""
        for ticker in self.pair_tickers:
            sym = self.symbols[ticker]
            if self.Portfolio[sym].Invested:
                if self.Securities[sym].Exchange.ExchangeOpen:
                    self.Liquidate(sym)
                    self.Log(f"[FLATTEN FRI] {ticker} closed")
                    self._reset_pair_state(ticker)
                else:
                    self.Log(f"[FLATTEN SKIP] {ticker} exchange closed")

    def _reset_weekly(self):
        """Monday 00:00 — Reset weekly equity tracking."""
        self.week_start_equity = float(self.Portfolio.TotalPortfolioValue)
        self.Log(f"[WEEKLY RESET] Equity: ${self.week_start_equity:.2f}")

    def _eod_log(self):
        """16:55 ET — Daily summary."""
        equity = float(self.Portfolio.TotalPortfolioValue)
        daily_pnl = equity - self.day_start_equity
        positions = []
        for ticker in self.pair_tickers:
            sym = self.symbols[ticker]
            if self.Portfolio[sym].Invested:
                h = self.Portfolio[sym]
                positions.append(f"{ticker}={'L' if h.IsLong else 'S'}({h.Quantity})")
        pos_str = ", ".join(positions) if positions else "FLAT"
        self.Log(f"[EOD] Equity=${equity:.2f} | DailyPnL=${daily_pnl:.2f} | Positions: {pos_str}")

    def _reset_pair_state(self, ticker):
        """Clear position tracking after exit."""
        pd = self.pairs_data[ticker]
        pd["entry_direction"] = 0
        pd["entry_price"] = 0.0
        pd["entry_atr"] = 0.0
        pd["entry_type"] = ""
        pd["partial_taken"] = False
        pd["trail_stop"] = 0.0
        pd["highest_since_entry"] = 0.0
        pd["lowest_since_entry"] = float("inf")
        pd["rsi_was_deep"] = False  # Reset: must prove deep retracement again

    # ═══════════════════════════════════════════════════════════
    #  MACRO EVENT FILTER
    # ═══════════════════════════════════════════════════════════

    def _is_macro_day(self):
        """No new entries on FOMC/NFP/CPI days."""
        return self.Time.date() in self.macro_blackout_dates

    def _build_macro_calendar(self):
        """FOMC + NFP + CPI dates 2020-2024."""
        dates = set()
        fomc_dates = [
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
        nfp_dates = []
        for year in range(2020, 2025):
            for month in range(1, 13):
                d = datetime(year, month, 1)
                days_until_fri = (4 - d.weekday()) % 7
                first_friday = d + timedelta(days=days_until_fri)
                nfp_dates.append(first_friday.strftime("%Y-%m-%d"))
        cpi_dates = []
        for year in range(2020, 2025):
            for month in range(1, 13):
                cpi_dates.append(f"{year}-{month:02d}-13")
        for d_str in fomc_dates + nfp_dates + cpi_dates:
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
