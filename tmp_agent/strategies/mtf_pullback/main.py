# region imports
from AlgorithmImports import *
from datetime import datetime, timedelta
import math
# endregion


class MTFTrendPullback(QCAlgorithm):
    """
    Brain V9 — MTF Trend Pullback V2.0

    MODE A RESET — High-Velocity Edge Discovery
    Target: CAGR >= 20%, Sharpe >= 1.2
    Kill gates: CAGR < 12% or Sharpe < 1.0 = DEAD

    HYPOTHESIS: Multi-asset (indices + commodities) CFDs exhibit stronger,
    more sustained trends than FX pairs. A multi-timeframe pullback strategy
    aligned with the dominant trend on D1, confirmed on H4, and entered on
    H1 pullbacks to moving averages should produce higher CAGR than FX-only
    strategies while maintaining acceptable Sharpe.

    TIMEFRAMES:
      D1 — Macro direction: EMA200 + EMA50 alignment + ADX > 20
      H4 — Confirmation: price vs EMA50 + RSI(14) > 50 (long) / < 50 (short)
      H1 — Entry: pullback to EMA20-EMA50 zone + RSI 40-55 (long) / 45-60 (short)

    EXIT:
      1. Hard stop: 1.8x H1 ATR from entry
      2. Partial TP: close 50% at 1.5R
      3. Trailing stop: Chandelier 2.0x ATR from highest high (long) / lowest low (short)
      4. Time stop: 5 days max hold
      5. Regime break: D1 ADX drops below 15 while in trade

    RISK:
      1.5% per trade, max 4 positions simultaneously
      DD throttling: reduce to 0.75% if rolling 20-day DD > 8%
      Daily loss limit: 2.5%
      Weekly loss limit: 5%

    UNIVERSE (Oanda CFDs, verified data availability):
      Indices:     SPX500USD, NAS100USD, US30USD
      Commodities: XAUUSD, XAGUSD, WTICOUSD

    PARENT: New family (Mode A reset after CMR-V2.0 Mode B failure)
    BASELINE: CMR-V2.0 OOS (Sharpe 0.947, CAGR 6.78%) — need 3-4x more velocity
    """

    VERSION = "MTF-PB-V2.0"

    def Initialize(self):
        # -- Backtest window (parameterized for IS/OOS splits) --
        start_year = int(self.GetParameter("start_year", 2010))
        end_year = int(self.GetParameter("end_year", 2020))
        end_month = int(self.GetParameter("end_month", 12))
        self.SetStartDate(start_year, 1, 1)
        self.SetEndDate(end_year, end_month, 28)
        self.SetCash(10000)
        self.SetBrokerageModel(BrokerageName.OandaBrokerage, AccountType.Margin)

        # -- Risk parameters (5 free params total, per contract max) --
        self.risk_per_trade = float(self.GetParameter("risk_pct", 0.015))     # P1: 1.5%
        self.atr_stop_mult = float(self.GetParameter("atr_stop", 1.8))       # P2: stop distance
        self.trail_atr_mult = float(self.GetParameter("trail_atr", 2.0))     # P3: trailing stop
        self.partial_tp_r = float(self.GetParameter("partial_tp_r", 1.5))    # P4: partial TP in R
        self.adx_entry_min = int(self.GetParameter("adx_min", 20))           # P5: min ADX for trend

        # -- Fixed parameters (not counted as free) --
        self.risk_reduced = 0.0075
        self.max_positions = 4
        self.max_daily_loss = 0.025
        self.max_weekly_loss = 0.05
        self.dd_threshold = 0.08
        self.max_hold_days = 5
        self.adx_exit_min = 15
        self.partial_close_pct = 0.50

        # -- Universe --
        self.tickers_cfd = ["SPX500USD", "NAS100USD", "US30USD", "XAUUSD", "XAGUSD", "WTICOUSD"]
        self.symbols = {}
        self.instrument_data = {}

        for ticker in self.tickers_cfd:
            cfd = self.AddCfd(ticker, Resolution.Hour, Market.Oanda)
            cfd.SetLeverage(20)
            sym = cfd.Symbol
            self.symbols[ticker] = sym

            # -- Daily indicators (D1 timeframe) --
            # EMA200 and EMA50 on daily for macro direction
            # ADX on daily for trend strength
            # We register daily indicators directly
            ema200_d = self.EMA(sym, 200, Resolution.Daily)
            ema50_d = self.EMA(sym, 50, Resolution.Daily)
            adx_d = self.ADX(sym, 14, Resolution.Daily)

            # -- H1 indicators (native resolution) --
            ema20_h1 = self.EMA(sym, 20, Resolution.Hour)
            ema50_h1 = self.EMA(sym, 50, Resolution.Hour)
            rsi_h1 = self.RSI(sym, 14, MovingAverageType.Simple, Resolution.Hour)
            atr_h1 = self.ATR(sym, 14, MovingAverageType.Simple, Resolution.Hour)

            self.instrument_data[ticker] = {
                # Daily
                "ema200_d": ema200_d,
                "ema50_d": ema50_d,
                "adx_d": adx_d,
                # H4 — built from consolidator
                "h4_closes": [],
                "h4_highs": [],
                "h4_lows": [],
                "h4_ema50": None,   # calculated manually
                "h4_rsi": None,     # calculated manually
                "h4_bar_count": 0,
                # H1
                "ema20_h1": ema20_h1,
                "ema50_h1": ema50_h1,
                "rsi_h1": rsi_h1,
                "atr_h1": atr_h1,
                # Position tracking
                "entry_price": 0.0,
                "entry_direction": 0,   # 1=long, -1=short
                "entry_date": None,
                "hard_stop": 0.0,
                "risk_distance": 0.0,
                "partial_taken": False,
                "trail_stop": 0.0,
                "highest_since_entry": 0.0,
                "lowest_since_entry": 999999.0,
                "initial_qty": 0,
            }

            # -- H4 consolidator (QuoteBarConsolidator for CFDs) --
            h4_consolidator = QuoteBarConsolidator(timedelta(hours=4))
            h4_consolidator.DataConsolidated += self._on_h4_bar
            self.SubscriptionManager.AddConsolidator(sym, h4_consolidator)

        # -- Risk tracking --
        self.day_start_equity = 10000.0
        self.week_start_equity = 10000.0
        self.last_trade_date = None
        self.equity_history = []
        self.open_position_count = 0
        self.trades_this_month = 0
        self.current_month = 0

        # -- Schedules --
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

        # -- Warmup: 250 days for EMA200 daily --
        self.SetWarmUp(timedelta(days=300))

        self.Log(f"[MTF-PB] {self.VERSION} | Universe: {self.tickers_cfd}")
        self.Log(f"[MTF-PB] Risk: {self.risk_per_trade*100}%/trade | Stop: {self.atr_stop_mult}x ATR | Trail: {self.trail_atr_mult}x ATR")
        self.Log(f"[MTF-PB] Partial TP: {self.partial_tp_r}R ({self.partial_close_pct*100}%) | ADX min: {self.adx_entry_min}")
        self.Log(f"[MTF-PB] Max positions: {self.max_positions} | Max hold: {self.max_hold_days}d")

    # ================================================================
    #  H4 BAR CONSOLIDATION HANDLER
    # ================================================================

    def _on_h4_bar(self, sender, bar):
        """Called when a 4-hour bar completes. Update H4 data for the symbol."""
        if self.IsWarmingUp:
            return

        sym = bar.Symbol
        ticker = None
        for t, s in self.symbols.items():
            if s == sym:
                ticker = t
                break
        if ticker is None:
            return

        d = self.instrument_data[ticker]
        close = float(bar.Close)
        high = float(bar.High)
        low = float(bar.Low)

        d["h4_closes"].append(close)
        d["h4_highs"].append(high)
        d["h4_lows"].append(low)

        # Keep last 60 bars for indicator calculations
        max_hist = 60
        if len(d["h4_closes"]) > max_hist:
            d["h4_closes"] = d["h4_closes"][-max_hist:]
            d["h4_highs"] = d["h4_highs"][-max_hist:]
            d["h4_lows"] = d["h4_lows"][-max_hist:]

        d["h4_bar_count"] = len(d["h4_closes"])

        # Calculate H4 EMA50 manually
        if len(d["h4_closes"]) >= 50:
            d["h4_ema50"] = self._calc_ema(d["h4_closes"], 50)

        # Calculate H4 RSI(14) manually
        if len(d["h4_closes"]) >= 15:
            d["h4_rsi"] = self._calc_rsi(d["h4_closes"], 14)

    # ================================================================
    #  MANUAL INDICATOR CALCULATIONS (for H4)
    # ================================================================

    def _calc_ema(self, data, period):
        """Calculate EMA of last N values."""
        if len(data) < period:
            return None
        k = 2.0 / (period + 1)
        ema = sum(data[:period]) / period  # SMA seed
        for val in data[period:]:
            ema = val * k + ema * (1 - k)
        return ema

    def _calc_rsi(self, data, period):
        """Calculate RSI from price series."""
        if len(data) < period + 1:
            return None
        changes = [data[i] - data[i-1] for i in range(1, len(data))]
        gains = [max(c, 0) for c in changes]
        losses = [max(-c, 0) for c in changes]

        # Initial average
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period

        # Smoothed
        for i in range(period, len(gains)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period

        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    # ================================================================
    #  MAIN DATA HANDLER (H1 resolution)
    # ================================================================

    def OnData(self, data):
        if self.IsWarmingUp:
            return

        # -- Daily/monthly reset --
        if self.last_trade_date is None or self.Time.date() != self.last_trade_date:
            self.day_start_equity = float(self.Portfolio.TotalPortfolioValue)
            self.last_trade_date = self.Time.date()
            self.equity_history.append(self.day_start_equity)
            if len(self.equity_history) > 30:
                self.equity_history = self.equity_history[-30:]

            # Monthly trade counter
            if self.Time.month != self.current_month:
                if self.current_month != 0:
                    self.Log(f"[MONTH] {self.current_month} trades: {self.trades_this_month}")
                self.trades_this_month = 0
                self.current_month = self.Time.month

        # -- Manage open positions (every hour) --
        for ticker in self.tickers_cfd:
            sym = self.symbols[ticker]
            if not data.ContainsKey(sym):
                continue
            if self.Portfolio[sym].Invested:
                self._manage_position(ticker, data)

        # -- Entry checks: only during active session hours (8-20 ET) --
        hour_et = self.Time.hour
        if hour_et < 8 or hour_et > 19:
            return

        # -- Count open positions --
        self.open_position_count = sum(
            1 for t in self.tickers_cfd
            if self.Portfolio[self.symbols[t]].Invested
        )

        # -- Scan for entries --
        for ticker in self.tickers_cfd:
            sym = self.symbols[ticker]
            if not data.ContainsKey(sym):
                continue
            if self.Portfolio[sym].Invested:
                continue
            if not self._pass_risk_gates():
                continue
            self._check_entry(ticker, data)

    # ================================================================
    #  ENTRY LOGIC — MULTI-TIMEFRAME PULLBACK
    # ================================================================

    def _check_entry(self, ticker, data):
        """
        D1: EMA200/EMA50 alignment + ADX > threshold = macro trend
        H4: price vs EMA50 + RSI confirmation = trend confirmation
        H1: pullback to EMA20-EMA50 zone + RSI in range = entry trigger
        """
        sym = self.symbols[ticker]
        d = self.instrument_data[ticker]

        # -- Get current price --
        bar = data[sym]
        if bar is None:
            return
        price = float(bar.Close)
        price_high = float(bar.High)
        price_low = float(bar.Low)

        # ============ D1 FILTER: Macro Direction ============
        if not d["ema200_d"].IsReady or not d["ema50_d"].IsReady or not d["adx_d"].IsReady:
            return

        ema200 = float(d["ema200_d"].Current.Value)
        ema50_d = float(d["ema50_d"].Current.Value)
        adx_d = float(d["adx_d"].Current.Value)

        if adx_d < self.adx_entry_min:
            return  # No trend — skip

        # Determine D1 direction
        d1_long = (price > ema200) and (ema50_d > ema200)
        d1_short = (price < ema200) and (ema50_d < ema200)

        if not d1_long and not d1_short:
            return  # No clear direction

        # ============ H4 FILTER: Trend Confirmation ============
        if d["h4_ema50"] is None or d["h4_rsi"] is None:
            return

        h4_ema50 = d["h4_ema50"]
        h4_rsi = d["h4_rsi"]

        h4_long = (price > h4_ema50) and (h4_rsi > 50)
        h4_short = (price < h4_ema50) and (h4_rsi < 50)

        # ============ H1 ENTRY: Pullback to EMA zone ============
        if not d["ema20_h1"].IsReady or not d["ema50_h1"].IsReady:
            return
        if not d["rsi_h1"].IsReady or not d["atr_h1"].IsReady:
            return

        ema20 = float(d["ema20_h1"].Current.Value)
        ema50_h1 = float(d["ema50_h1"].Current.Value)
        rsi_h1 = float(d["rsi_h1"].Current.Value)
        atr_h1 = float(d["atr_h1"].Current.Value)

        if atr_h1 <= 0:
            return

        direction = 0

        # LONG: D1 up + H4 up + H1 pullback into EMA20-EMA50 zone + RSI 35-55
        if d1_long and h4_long:
            ema_lower = min(ema20, ema50_h1)
            ema_upper = max(ema20, ema50_h1)
            # Price should be near or within the EMA zone (within 0.5 ATR below upper)
            in_zone = (price >= ema_lower - 0.5 * atr_h1) and (price <= ema_upper + 0.3 * atr_h1)
            rsi_ok = 35 <= rsi_h1 <= 55
            if in_zone and rsi_ok:
                direction = 1

        # SHORT: D1 down + H4 down + H1 pullback into EMA20-EMA50 zone + RSI 45-65
        if d1_short and h4_short:
            ema_lower = min(ema20, ema50_h1)
            ema_upper = max(ema20, ema50_h1)
            in_zone = (price >= ema_lower - 0.3 * atr_h1) and (price <= ema_upper + 0.5 * atr_h1)
            rsi_ok = 45 <= rsi_h1 <= 65
            if in_zone and rsi_ok:
                direction = -1

        if direction == 0:
            return

        # ============ POSITION SIZING ============
        stop_distance = self.atr_stop_mult * atr_h1
        if direction == 1:
            stop_price = price - stop_distance
        else:
            stop_price = price + stop_distance

        current_risk = self._get_current_risk_pct()
        qty = self._calculate_position_size(ticker, price, stop_distance, current_risk)
        if qty <= 0:
            return

        if not self.Securities[sym].Exchange.ExchangeOpen:
            return

        # ============ EXECUTE ============
        side = "LONG" if direction == 1 else "SHORT"
        order_qty = qty if direction == 1 else -qty
        self.MarketOrder(sym, order_qty)

        d["entry_price"] = price
        d["entry_direction"] = direction
        d["entry_date"] = self.Time
        d["hard_stop"] = stop_price
        d["risk_distance"] = stop_distance
        d["partial_taken"] = False
        d["trail_stop"] = stop_price
        d["highest_since_entry"] = price
        d["lowest_since_entry"] = price
        d["initial_qty"] = qty

        self.trades_this_month += 1

        self.Log(f"[ENTRY {side}] {ticker} @ {price:.2f} | "
                 f"Stop={stop_price:.2f} ({stop_distance:.2f}) | "
                 f"D1: EMA200={ema200:.2f} EMA50={ema50_d:.2f} ADX={adx_d:.1f} | "
                 f"H4: EMA50={h4_ema50:.2f} RSI={h4_rsi:.1f} | "
                 f"H1: EMA20={ema20:.2f} EMA50={ema50_h1:.2f} RSI={rsi_h1:.1f} ATR={atr_h1:.2f} | "
                 f"Risk={current_risk*100:.2f}% Qty={order_qty}")

    # ================================================================
    #  POSITION MANAGEMENT
    # ================================================================

    def _manage_position(self, ticker, data):
        """Exit hierarchy: hard stop > partial TP > trailing > time > regime break."""
        sym = self.symbols[ticker]
        d = self.instrument_data[ticker]

        if not data.ContainsKey(sym):
            return
        bar = data[sym]
        if bar is None:
            return

        price = float(bar.Close)
        price_high = float(bar.High)
        price_low = float(bar.Low)
        direction = d["entry_direction"]
        if direction == 0:
            return

        if not self.Securities[sym].Exchange.ExchangeOpen:
            return

        # Update tracking
        if price_high > d["highest_since_entry"]:
            d["highest_since_entry"] = price_high
        if price_low < d["lowest_since_entry"]:
            d["lowest_since_entry"] = price_low

        # -- EXIT 1: Hard stop --
        if direction == 1 and price_low <= d["hard_stop"]:
            self.Liquidate(sym)
            pnl = (price - d["entry_price"]) / d["entry_price"] * 100
            self.Log(f"[EXIT STOP] {ticker} LONG @ {price:.2f} | Entry={d['entry_price']:.2f} | PnL={pnl:+.2f}%")
            self._reset_position(ticker)
            return

        if direction == -1 and price_high >= d["hard_stop"]:
            self.Liquidate(sym)
            pnl = (d["entry_price"] - price) / d["entry_price"] * 100
            self.Log(f"[EXIT STOP] {ticker} SHORT @ {price:.2f} | Entry={d['entry_price']:.2f} | PnL={pnl:+.2f}%")
            self._reset_position(ticker)
            return

        # -- EXIT 2: Partial TP at N*R --
        if not d["partial_taken"] and d["risk_distance"] > 0:
            tp_distance = self.partial_tp_r * d["risk_distance"]
            if direction == 1 and (price - d["entry_price"]) >= tp_distance:
                close_qty = int(d["initial_qty"] * self.partial_close_pct)
                if close_qty > 0:
                    self.MarketOrder(sym, -close_qty)
                    d["partial_taken"] = True
                    # Move stop to breakeven
                    d["hard_stop"] = d["entry_price"] + 0.1 * d["risk_distance"]
                    d["trail_stop"] = d["hard_stop"]
                    self.Log(f"[PARTIAL TP] {ticker} LONG closed {close_qty} @ {price:.2f} | "
                             f"Stop -> BE+0.1R={d['hard_stop']:.2f}")

            if direction == -1 and (d["entry_price"] - price) >= tp_distance:
                close_qty = int(d["initial_qty"] * self.partial_close_pct)
                if close_qty > 0:
                    self.MarketOrder(sym, close_qty)
                    d["partial_taken"] = True
                    d["hard_stop"] = d["entry_price"] - 0.1 * d["risk_distance"]
                    d["trail_stop"] = d["hard_stop"]
                    self.Log(f"[PARTIAL TP] {ticker} SHORT closed {close_qty} @ {price:.2f} | "
                             f"Stop -> BE+0.1R={d['hard_stop']:.2f}")

        # -- EXIT 3: Trailing stop (Chandelier) --
        if d["partial_taken"] and d["atr_h1"].IsReady:
            atr_h1 = float(d["atr_h1"].Current.Value)
            if atr_h1 > 0:
                if direction == 1:
                    new_trail = d["highest_since_entry"] - self.trail_atr_mult * atr_h1
                    if new_trail > d["trail_stop"]:
                        d["trail_stop"] = new_trail
                    if price_low <= d["trail_stop"]:
                        self.Liquidate(sym)
                        pnl = (price - d["entry_price"]) / d["entry_price"] * 100
                        self.Log(f"[EXIT TRAIL] {ticker} LONG @ {price:.2f} | Trail={d['trail_stop']:.2f} | PnL={pnl:+.2f}%")
                        self._reset_position(ticker)
                        return
                else:
                    new_trail = d["lowest_since_entry"] + self.trail_atr_mult * atr_h1
                    if new_trail < d["trail_stop"]:
                        d["trail_stop"] = new_trail
                    if price_high >= d["trail_stop"]:
                        self.Liquidate(sym)
                        pnl = (d["entry_price"] - price) / d["entry_price"] * 100
                        self.Log(f"[EXIT TRAIL] {ticker} SHORT @ {price:.2f} | Trail={d['trail_stop']:.2f} | PnL={pnl:+.2f}%")
                        self._reset_position(ticker)
                        return

        # -- EXIT 4: Time stop --
        if d["entry_date"] is not None:
            days_held = (self.Time - d["entry_date"]).days
            if days_held >= self.max_hold_days:
                self.Liquidate(sym)
                pnl_sign = 1 if direction == 1 else -1
                pnl = pnl_sign * (price - d["entry_price"]) / d["entry_price"] * 100
                self.Log(f"[EXIT TIME] {ticker} @ {price:.2f} | Days={days_held} | PnL={pnl:+.2f}%")
                self._reset_position(ticker)
                return

        # -- EXIT 5: Regime break (D1 ADX drops below threshold) --
        if d["adx_d"].IsReady:
            adx_d = float(d["adx_d"].Current.Value)
            if adx_d < self.adx_exit_min:
                self.Liquidate(sym)
                pnl_sign = 1 if direction == 1 else -1
                pnl = pnl_sign * (price - d["entry_price"]) / d["entry_price"] * 100
                self.Log(f"[EXIT REGIME] {ticker} @ {price:.2f} | ADX={adx_d:.1f}<{self.adx_exit_min} | PnL={pnl:+.2f}%")
                self._reset_position(ticker)
                return

    # ================================================================
    #  POSITION SIZING
    # ================================================================

    def _get_current_risk_pct(self):
        """DD-adjusted risk per trade."""
        if len(self.equity_history) < 5:
            return self.risk_per_trade

        lookback = min(20, len(self.equity_history))
        peak = max(self.equity_history[-lookback:])
        current = float(self.Portfolio.TotalPortfolioValue)
        dd = (peak - current) / peak if peak > 0 else 0

        if dd >= self.dd_threshold:
            self.Log(f"[DD THROTTLE] Rolling DD={dd*100:.1f}% >= {self.dd_threshold*100}% -> risk={self.risk_reduced*100}%")
            return self.risk_reduced
        return self.risk_per_trade

    def _calculate_position_size(self, ticker, price, risk_distance, risk_pct):
        """Fixed fractional position sizing."""
        equity = float(self.Portfolio.TotalPortfolioValue)
        risk_amount = equity * risk_pct

        if risk_distance <= 0 or price <= 0:
            return 0

        # For CFDs, position size = risk_amount / risk_distance
        # This gives us notional units
        qty = int(risk_amount / risk_distance)

        # Minimum size check depends on instrument
        # Indices: min 1 unit, commodities: varies
        if qty < 1:
            return 0

        return qty

    # ================================================================
    #  RISK MANAGEMENT
    # ================================================================

    def _pass_risk_gates(self):
        """Daily/weekly limits + max positions."""
        equity = float(self.Portfolio.TotalPortfolioValue)

        if self.open_position_count >= self.max_positions:
            return False

        daily_pnl = equity - self.day_start_equity
        if daily_pnl < -(self.day_start_equity * self.max_daily_loss):
            return False

        weekly_pnl = equity - self.week_start_equity
        if weekly_pnl < -(self.week_start_equity * self.max_weekly_loss):
            return False

        return True

    # ================================================================
    #  SCHEDULING & UTILITIES
    # ================================================================

    def _flatten_all(self):
        """Friday 16:50 ET — Close all before weekend."""
        for ticker in self.tickers_cfd:
            sym = self.symbols[ticker]
            if self.Portfolio[sym].Invested:
                if self.Securities[sym].Exchange.ExchangeOpen:
                    self.Liquidate(sym)
                    self.Log(f"[FLATTEN FRI] {ticker} closed")
                    self._reset_position(ticker)

    def _reset_weekly(self):
        """Monday reset."""
        self.week_start_equity = float(self.Portfolio.TotalPortfolioValue)

    def _eod_log(self):
        """Daily summary."""
        equity = float(self.Portfolio.TotalPortfolioValue)
        daily_pnl = equity - self.day_start_equity
        positions = []
        for ticker in self.tickers_cfd:
            sym = self.symbols[ticker]
            if self.Portfolio[sym].Invested:
                h = self.Portfolio[sym]
                side = "L" if h.IsLong else "S"
                unrealized = float(h.UnrealizedProfitPercent) * 100
                positions.append(f"{ticker}={side}({unrealized:+.1f}%)")
        pos_str = ", ".join(positions) if positions else "FLAT"
        self.Log(f"[EOD] Equity=${equity:.2f} | DailyPnL=${daily_pnl:+.2f} ({daily_pnl/self.day_start_equity*100:+.2f}%) | {pos_str}")

    def _reset_position(self, ticker):
        """Clear position state."""
        d = self.instrument_data[ticker]
        d["entry_price"] = 0.0
        d["entry_direction"] = 0
        d["entry_date"] = None
        d["hard_stop"] = 0.0
        d["risk_distance"] = 0.0
        d["partial_taken"] = False
        d["trail_stop"] = 0.0
        d["highest_since_entry"] = 0.0
        d["lowest_since_entry"] = 999999.0
        d["initial_qty"] = 0

    # ================================================================
    #  EVENT HANDLERS
    # ================================================================

    def OnOrderEvent(self, orderEvent):
        if orderEvent.Status == OrderStatus.Filled:
            sym = orderEvent.Symbol
            ticker = str(sym).split(" ")[0] if " " in str(sym) else str(sym)
            self.Log(f"[ORDER] {ticker} | Qty={orderEvent.FillQuantity} @ "
                     f"{orderEvent.FillPrice:.2f} | Fee={orderEvent.OrderFee}")

    def OnEndOfAlgorithm(self):
        equity = float(self.Portfolio.TotalPortfolioValue)
        total_return = (equity - 10000) / 10000 * 100
        self.Log(f"[FINAL] {self.VERSION} | Equity=${equity:.2f} | Return={total_return:+.2f}% | "
                 f"Trades last month: {self.trades_this_month}")
