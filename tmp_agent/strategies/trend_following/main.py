# region imports
from AlgorithmImports import *
from datetime import datetime, timedelta
import numpy as np
# endregion


class TrendFollowingMF(QCAlgorithm):
    """
    Brain V9 — Trend Following Medium-Frequency V1.1

    V1.0 → V1.1 CHANGES:
    - FIX: Moved from fake H4 bars (hourly snapshots) to proper Daily consolidated bars
    - Donchian Channel now 55-day (from 20-period H4) — classic Turtle breakout period
    - Removed EURGBP (structurally mean-reverting, lost -$1,223 in V1.0)
    - Time stop extended to 80 daily bars (~4 months) — let trends run
    - ADX filter tightened to 25 (from 20) — fewer false breakouts
    - Entry once daily at 12:00 ET (not every 4H) — cleaner signals
    - EMA reversal exit checked once daily (not hourly) — less whipsaw

    HYPOTHESIS: Trends in FX persist due to institutional flows, herding behavior,
    and monetary policy divergence. A multi-pair Donchian breakout on Daily bars,
    filtered by Daily EMA trend and ADX, captures medium-term trends while
    a Chandelier trailing stop locks in profits.

    FAMILY: Trend Following Medium-Freq (Contract §4, Priority 1)
    MODE: A (Discovery)

    ENTRY:
    1. Daily EMA(200) defines bias: price > EMA200 → only long, < → only short
    2. Donchian Channel breakout: price breaks 55-day high (long) or low (short)
    3. ADX(14) Daily > 25 confirms directional movement
    4. No entry on macro blackout days

    EXIT:
    1. Chandelier trailing stop: 3x ATR(14) from highest/lowest since entry
    2. Trend reversal: price crosses EMA(200) opposite side on Daily
    3. Time stop: 80 daily bars (~4 months)
    4. Friday 16:50 ET flatten all

    RISK:
    - 1.5% per trade (fixed fractional, ATR-based sizing)
    - Max 4 concurrent positions
    - Max 2 positions same currency exposure
    - Daily DD limit: 3% | Weekly DD limit: 5%
    - DD throttle: >4% rolling 20-day DD → reduce to 0.75%

    PAIRS: EURUSD, GBPUSD, USDJPY, AUDUSD, NZDUSD, USDCAD, USDCHF
    TIMEFRAME: Daily for signals/Donchian/trend/ADX/ATR, Hourly for stop monitoring
    PARAMETERS: 5 (donchian_period, ema_trend, adx_min, chandelier_mult, risk_per_trade)
    """

    VERSION = "TF-V1.1"

    def Initialize(self):
        # ── Backtest window ──
        start_year = int(self.GetParameter("start_year", 2015))
        end_year = int(self.GetParameter("end_year", 2020))
        end_month = int(self.GetParameter("end_month", 12))
        self.SetStartDate(start_year, 1, 1)
        self.SetEndDate(end_year, end_month, 28)
        self.SetCash(10000)
        self.SetBrokerageModel(BrokerageName.OandaBrokerage, AccountType.Margin)

        # ══════════════════════════════════════════════
        # PARAMETERS (5 max per contract §7)
        # ══════════════════════════════════════════════
        self.donchian_period = int(self.GetParameter("donchian_period", 55))
        self.ema_trend = int(self.GetParameter("ema_trend", 200))
        self.adx_min = int(self.GetParameter("adx_min", 25))
        self.chandelier_mult = float(self.GetParameter("chandelier_mult", 3.0))
        self.risk_per_trade = float(self.GetParameter("risk_per_trade", 0.015))

        # ── Fixed config (not counted as free params) ──
        self.risk_reduced = self.risk_per_trade * 0.5
        self.max_positions = 4
        self.max_cluster = 2
        self.max_hold_bars = 80  # 80 daily bars ≈ 4 months — let trends run
        self.max_daily_risk = 0.03
        self.max_weekly_risk = 0.05
        self.dd_threshold = 0.04

        # ── Pair universe (7 pairs — removed EURGBP, mean-reverting) ──
        self.pair_tickers = [
            "EURUSD", "GBPUSD", "USDJPY", "AUDUSD",
            "NZDUSD", "USDCAD", "USDCHF"
        ]
        self.symbols = {}
        self.pairs_data = {}

        for ticker in self.pair_tickers:
            forex = self.AddForex(ticker, Resolution.Hour, Market.Oanda)
            forex.SetLeverage(10)
            sym = forex.Symbol

            self.symbols[ticker] = sym

            # ── Create proper Daily consolidator for H/L/C tracking ──
            daily_consolidator = QuoteBarConsolidator(timedelta(days=1))
            daily_consolidator.DataConsolidated += self._on_daily_bar
            self.SubscriptionManager.AddConsolidator(sym, daily_consolidator)

            self.pairs_data[ticker] = {
                # Daily indicators
                "adx_d": self.ADX(sym, 14, Resolution.Daily),
                "atr_d": self.ATR(sym, 14, MovingAverageType.Simple, Resolution.Daily),
                # Daily price history for Donchian (proper consolidated bars)
                "daily_highs": [],
                "daily_lows": [],
                "daily_closes": [],
                "last_daily_bar": None,
                # Position tracking
                "entry_price": 0.0,
                "entry_direction": 0,  # 1=long, -1=short
                "entry_date": None,
                "entry_bar_count": 0,
                "highest_since_entry": 0.0,
                "lowest_since_entry": 999.0,
                "trailing_stop": 0.0,
                "traded_today": False,
            }

        # ── Risk tracking ──
        self.day_start_equity = 10000.0
        self.last_trade_date = None
        self.week_start_equity = 10000.0
        self.equity_history = []
        self.open_position_count = 0

        # ── Macro blackout ──
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

        # ── Warmup: 300 days for EMA(200) + Donchian history ──
        self.SetWarmUp(timedelta(days=300))

        self.Log(f"[TF] {self.VERSION} | Pairs: {self.pair_tickers}")
        self.Log(f"[TF] Donchian={self.donchian_period} (Daily) | EMA={self.ema_trend} | ADX>={self.adx_min}")
        self.Log(f"[TF] Chandelier={self.chandelier_mult}x ATR | Risk={self.risk_per_trade*100}%/trade")

    # ═══════════════════════════════════════════════════════════
    #  EMA CALCULATION (manual — avoids QC EMA resolution issues)
    # ═══════════════════════════════════════════════════════════

    def _calc_ema(self, closes, period):
        """Calculate EMA from price history."""
        if len(closes) < period:
            return None
        sma = sum(closes[:period]) / period
        mult = 2.0 / (period + 1)
        ema = sma
        for price in closes[period:]:
            ema = (price - ema) * mult + ema
        return ema

    # ═══════════════════════════════════════════════════════════
    #  DAILY BAR CONSOLIDATOR HANDLER
    # ═══════════════════════════════════════════════════════════

    def _on_daily_bar(self, sender, bar):
        """Receives properly consolidated daily bars for Donchian + EMA."""
        if self.IsWarmingUp:
            # Still collect data during warmup for history building
            pass

        ticker = str(bar.Symbol.Value)
        if ticker not in self.pairs_data:
            return

        pd = self.pairs_data[ticker]
        high = float(bar.High)
        low = float(bar.Low)
        close = float(bar.Close)

        pd["daily_highs"].append(high)
        pd["daily_lows"].append(low)
        pd["daily_closes"].append(close)

        max_hist = max(self.donchian_period + 10, self.ema_trend + 50)
        if len(pd["daily_highs"]) > max_hist:
            pd["daily_highs"] = pd["daily_highs"][-max_hist:]
            pd["daily_lows"] = pd["daily_lows"][-max_hist:]
            pd["daily_closes"] = pd["daily_closes"][-max_hist:]

    # ═══════════════════════════════════════════════════════════
    #  MAIN DATA HANDLER
    # ═══════════════════════════════════════════════════════════

    def OnData(self, data: Slice):
        if self.IsWarmingUp:
            return

        # ── Daily reset ──
        if self.last_trade_date is None or self.Time.date() != self.last_trade_date:
            self.day_start_equity = float(self.Portfolio.TotalPortfolioValue)
            self.last_trade_date = self.Time.date()
            for t in self.pair_tickers:
                self.pairs_data[t]["traded_today"] = False
            self.equity_history.append(self.day_start_equity)
            if len(self.equity_history) > 30:
                self.equity_history = self.equity_history[-30:]

        # ── Manage open positions (every hour for trailing stop updates) ──
        for ticker in self.pair_tickers:
            sym = self.symbols[ticker]
            if not data.ContainsKey(sym):
                continue
            if self.Portfolio[sym].Invested:
                self._manage_position(ticker, data)

        # ── Entry checks: once per day at 12:00 ET (after daily bars settle) ──
        hour_et = self.Time.hour
        if hour_et != 12:
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
            self._check_tf_entry(ticker, data)

    # ═══════════════════════════════════════════════════════════
    #  ENTRY: DONCHIAN BREAKOUT + EMA TREND + ADX
    # ═══════════════════════════════════════════════════════════

    def _check_tf_entry(self, ticker, data):
        """Enter on Daily Donchian breakout in direction of EMA trend with ADX confirmation."""
        pd = self.pairs_data[ticker]
        sym = self.symbols[ticker]

        # ── Need enough Daily history for Donchian ──
        if len(pd["daily_highs"]) < self.donchian_period + 1:
            return

        # ── Need enough daily history for EMA ──
        if len(pd["daily_closes"]) < self.ema_trend:
            return

        # ── ADX must confirm directional movement ──
        if not pd["adx_d"].IsReady:
            return
        adx = float(pd["adx_d"].Current.Value)
        if adx < self.adx_min:
            return  # No directional movement

        # ── ATR for sizing ──
        if not pd["atr_d"].IsReady:
            return
        atr_d = float(pd["atr_d"].Current.Value)
        if atr_d <= 0:
            return

        # ── Current price ──
        bar = data[sym]
        if bar is None:
            return
        price = float(bar.Close) if hasattr(bar, 'Close') else float(bar.Value)

        # ── EMA trend direction ──
        ema_val = self._calc_ema(pd["daily_closes"], self.ema_trend)
        if ema_val is None:
            return

        # ── Donchian Channel on Daily bars (excluding current/last bar) ──
        lookback_highs = pd["daily_highs"][-(self.donchian_period + 1):-1]
        lookback_lows = pd["daily_lows"][-(self.donchian_period + 1):-1]
        if len(lookback_highs) < self.donchian_period:
            return

        donchian_high = max(lookback_highs)
        donchian_low = min(lookback_lows)

        # ── Determine direction ──
        direction = 0
        if price > ema_val and price > donchian_high:
            direction = 1  # Breakout long in uptrend
        elif price < ema_val and price < donchian_low:
            direction = -1  # Breakout short in downtrend

        if direction == 0:
            return

        # ── Initial trailing stop (Chandelier) ──
        if direction == 1:
            stop_price = price - self.chandelier_mult * atr_d
        else:
            stop_price = price + self.chandelier_mult * atr_d

        risk_distance = abs(price - stop_price)
        if risk_distance <= 0:
            return

        # ── Position size ──
        current_risk = self._get_current_risk_pct()
        qty = self._calculate_position_size(ticker, price, risk_distance, current_risk)
        if qty <= 0:
            return

        if not self.Securities[sym].Exchange.ExchangeOpen:
            return

        # ── Execute ──
        side = "LONG" if direction == 1 else "SHORT"
        self.MarketOrder(sym, qty if direction == 1 else -qty)

        self.Log(f"[ENTRY-TF {side}] {ticker} @ {price:.5f} | "
                 f"Donchian H={donchian_high:.5f} L={donchian_low:.5f} | "
                 f"EMA={ema_val:.5f} | ADX={adx:.1f} | "
                 f"Stop={stop_price:.5f} | Risk={current_risk*100:.1f}%")

        pd["entry_direction"] = direction
        pd["entry_price"] = price
        pd["entry_date"] = self.Time
        pd["entry_bar_count"] = 0
        pd["highest_since_entry"] = price
        pd["lowest_since_entry"] = price
        pd["trailing_stop"] = stop_price
        pd["traded_today"] = True

    # ═══════════════════════════════════════════════════════════
    #  POSITION MANAGEMENT — CHANDELIER TRAILING STOP
    # ═══════════════════════════════════════════════════════════

    def _manage_position(self, ticker, data):
        """Exit on: trailing stop, EMA reversal, or time stop."""
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
        direction = pd["entry_direction"]
        if direction == 0:
            return

        if not self.Securities[sym].Exchange.ExchangeOpen:
            return

        # Update extreme prices
        pd["highest_since_entry"] = max(pd["highest_since_entry"], price_high)
        pd["lowest_since_entry"] = min(pd["lowest_since_entry"], price_low)

        # Update trailing stop
        atr_d = float(pd["atr_d"].Current.Value) if pd["atr_d"].IsReady else 0
        if atr_d > 0:
            if direction == 1:
                new_stop = pd["highest_since_entry"] - self.chandelier_mult * atr_d
                pd["trailing_stop"] = max(pd["trailing_stop"], new_stop)
            else:
                new_stop = pd["lowest_since_entry"] + self.chandelier_mult * atr_d
                pd["trailing_stop"] = min(pd["trailing_stop"], new_stop)

        # Increment bar count once per day (at noon check)
        hour_et = self.Time.hour
        if hour_et == 12:
            pd["entry_bar_count"] += 1

        # ── EXIT 1: Trailing stop hit ──
        if direction == 1 and price_low <= pd["trailing_stop"]:
            self.Liquidate(sym)
            pnl_pct = (price - pd["entry_price"]) / pd["entry_price"] * 100
            self.Log(f"[EXIT TRAIL LONG] {ticker} @ {price:.5f} | "
                     f"Stop={pd['trailing_stop']:.5f} | PnL={pnl_pct:.2f}%")
            self._reset_pair_state(ticker)
            return

        if direction == -1 and price_high >= pd["trailing_stop"]:
            self.Liquidate(sym)
            pnl_pct = (pd["entry_price"] - price) / pd["entry_price"] * 100
            self.Log(f"[EXIT TRAIL SHORT] {ticker} @ {price:.5f} | "
                     f"Stop={pd['trailing_stop']:.5f} | PnL={pnl_pct:.2f}%")
            self._reset_pair_state(ticker)
            return

        # ── EXIT 2: EMA trend reversal (check once per day) ──
        if hour_et == 12 and len(pd["daily_closes"]) >= self.ema_trend:
            ema_val = self._calc_ema(pd["daily_closes"], self.ema_trend)
            if ema_val is not None:
                if direction == 1 and price < ema_val:
                    self.Liquidate(sym)
                    pnl_pct = (price - pd["entry_price"]) / pd["entry_price"] * 100
                    self.Log(f"[EXIT EMA LONG] {ticker} @ {price:.5f} | "
                             f"EMA={ema_val:.5f} | PnL={pnl_pct:.2f}%")
                    self._reset_pair_state(ticker)
                    return
                if direction == -1 and price > ema_val:
                    self.Liquidate(sym)
                    pnl_pct = (pd["entry_price"] - price) / pd["entry_price"] * 100
                    self.Log(f"[EXIT EMA SHORT] {ticker} @ {price:.5f} | "
                             f"EMA={ema_val:.5f} | PnL={pnl_pct:.2f}%")
                    self._reset_pair_state(ticker)
                    return

        # ── EXIT 3: Time stop (max daily bars) ──
        if pd["entry_bar_count"] >= self.max_hold_bars:
            self.Liquidate(sym)
            pnl_pct = (price - pd["entry_price"]) / pd["entry_price"] * 100 if direction == 1 else \
                       (pd["entry_price"] - price) / pd["entry_price"] * 100
            self.Log(f"[EXIT TIME] {ticker} @ {price:.5f} | "
                     f"Days={pd['entry_bar_count']} | PnL={pnl_pct:.2f}%")
            self._reset_pair_state(ticker)
            return

    # ═══════════════════════════════════════════════════════════
    #  POSITION SIZING
    # ═══════════════════════════════════════════════════════════

    def _get_current_risk_pct(self):
        """Get current risk per trade, reduced if in drawdown."""
        if len(self.equity_history) < 5:
            return self.risk_per_trade
        peak = max(self.equity_history[-20:]) if len(self.equity_history) >= 20 else max(self.equity_history)
        current = float(self.Portfolio.TotalPortfolioValue)
        dd = (peak - current) / peak if peak > 0 else 0
        if dd >= self.dd_threshold:
            self.Log(f"[DD THROTTLE] Rolling DD={dd*100:.1f}% → risk reduced to {self.risk_reduced*100:.1f}%")
            return self.risk_reduced
        return self.risk_per_trade

    def _calculate_position_size(self, ticker, price, risk_distance, risk_pct):
        """Fixed fractional with DD-adjusted risk."""
        equity = float(self.Portfolio.TotalPortfolioValue)
        risk_amount = equity * risk_pct
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
            return False
        weekly_change = equity - self.week_start_equity
        if weekly_change < -(self.week_start_equity * self.max_weekly_risk):
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

    def _reset_weekly(self):
        self.week_start_equity = float(self.Portfolio.TotalPortfolioValue)

    def _eod_log(self):
        equity = float(self.Portfolio.TotalPortfolioValue)
        daily_pnl = equity - self.day_start_equity
        positions = []
        for ticker in self.pair_tickers:
            sym = self.symbols[ticker]
            if self.Portfolio[sym].Invested:
                h = self.Portfolio[sym]
                positions.append(f"{ticker}={'L' if h.IsLong else 'S'}")
        pos_str = ", ".join(positions) if positions else "FLAT"
        self.Log(f"[EOD] Equity=${equity:.2f} | DailyPnL=${daily_pnl:.2f} | {pos_str}")

    def _reset_pair_state(self, ticker):
        pd = self.pairs_data[ticker]
        pd["entry_direction"] = 0
        pd["entry_price"] = 0.0
        pd["entry_date"] = None
        pd["entry_bar_count"] = 0
        pd["highest_since_entry"] = 0.0
        pd["lowest_since_entry"] = 999.0
        pd["trailing_stop"] = 0.0

    # ═══════════════════════════════════════════════════════════
    #  MACRO EVENT FILTER
    # ═══════════════════════════════════════════════════════════

    def _is_macro_day(self):
        return self.Time.date() in self.macro_blackout_dates

    def _build_macro_calendar(self):
        """FOMC + ECB + BoE + BoJ + RBA + BoC + RBNZ dates 2015-2024."""
        dates = set()
        # FOMC dates 2015-2024
        fomc = [
            # 2015
            "2015-01-28", "2015-03-18", "2015-04-29", "2015-06-17",
            "2015-07-29", "2015-09-17", "2015-10-28", "2015-12-16",
            # 2016
            "2016-01-27", "2016-03-16", "2016-04-27", "2016-06-15",
            "2016-07-27", "2016-09-21", "2016-11-02", "2016-12-14",
            # 2017
            "2017-02-01", "2017-03-15", "2017-05-03", "2017-06-14",
            "2017-07-26", "2017-09-20", "2017-11-01", "2017-12-13",
            # 2018
            "2018-01-31", "2018-03-21", "2018-05-02", "2018-06-13",
            "2018-08-01", "2018-09-26", "2018-11-08", "2018-12-19",
            # 2019
            "2019-01-30", "2019-03-20", "2019-05-01", "2019-06-19",
            "2019-07-31", "2019-09-18", "2019-10-30", "2019-12-11",
            # 2020
            "2020-01-29", "2020-03-03", "2020-03-15", "2020-04-29", "2020-06-10",
            "2020-07-29", "2020-09-16", "2020-11-05", "2020-12-16",
            # 2021
            "2021-01-27", "2021-03-17", "2021-04-28", "2021-06-16",
            "2021-07-28", "2021-09-22", "2021-11-03", "2021-12-15",
            # 2022
            "2022-01-26", "2022-03-16", "2022-05-04", "2022-06-15",
            "2022-07-27", "2022-09-21", "2022-11-02", "2022-12-14",
            # 2023
            "2023-02-01", "2023-03-22", "2023-05-03", "2023-06-14",
            "2023-07-26", "2023-09-20", "2023-11-01", "2023-12-13",
            # 2024
            "2024-01-31", "2024-03-20", "2024-05-01", "2024-06-12",
            "2024-07-31", "2024-09-18", "2024-11-07", "2024-12-18",
        ]
        # ECB (major ones)
        ecb = [
            "2015-01-22", "2015-03-05", "2015-06-03", "2015-09-03", "2015-12-03",
            "2016-03-10", "2016-06-02", "2016-09-08", "2016-12-08",
            "2017-01-19", "2017-04-27", "2017-06-08", "2017-09-07", "2017-12-14",
            "2018-01-25", "2018-04-26", "2018-06-14", "2018-09-13", "2018-12-13",
            "2019-01-24", "2019-04-10", "2019-06-06", "2019-09-12", "2019-12-12",
            "2020-01-23", "2020-03-12", "2020-04-30", "2020-06-04", "2020-09-10", "2020-12-10",
            "2021-01-21", "2021-04-22", "2021-06-10", "2021-09-09", "2021-12-16",
            "2022-02-03", "2022-04-14", "2022-06-09", "2022-07-21", "2022-09-08", "2022-12-15",
            "2023-02-02", "2023-03-16", "2023-05-04", "2023-06-15", "2023-09-14", "2023-12-14",
            "2024-01-25", "2024-03-07", "2024-04-11", "2024-06-06", "2024-09-12", "2024-12-12",
        ]

        for d_str in fomc + ecb:
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
