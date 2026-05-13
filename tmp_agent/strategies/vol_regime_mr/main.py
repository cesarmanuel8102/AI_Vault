# region imports
from AlgorithmImports import *
from datetime import datetime, timedelta
import numpy as np
# endregion


class VolRegimeMR(QCAlgorithm):
    """
    Brain V9 — Vol-Regime Mean Reversion V1.0

    EVOLUTION FROM: CMR-V2.0 (Commodity Cross Mean Reversion)
    PARENT: CMR-V2.0 (+12.26% OOS, Sharpe ~0.75, CAGR 5.98%)

    KEY CHANGES vs CMR-V2.0:
    1. Historical Volatility (HV) percentile filter — only trade when HV(20) is
       below 75th percentile of its 252-day history. This avoids MR during
       trending/crisis regimes where breakouts dominate.
    2. Added EURGBP (structurally mean-reverting European pair)
    3. Z-score entry at 1.5 (from 2.0) for higher trade frequency
    4. Tighter stop at 2.0 ATR (from 2.5) — cut losers faster
    5. Max hold 7 days (from 10) — faster rotation
    6. Max 4 positions (from 3) with 4 pairs

    HYPOTHESIS: Mean reversion on commodity crosses (AUDCAD, NZDCAD, AUDNZD) and
    European crosses (EURGBP) works reliably in LOW volatility regimes. A historical
    volatility filter disables trading during high-vol trending environments where
    breakouts dominate and MR loses money.

    FAMILY: Vol-Regime Mean Reversion (Contract §4, Priority 2)
    MODE: A (Discovery)

    ENTRY:
    1. HV(20) percentile < 75th of 252-day rolling window (low-vol regime)
    2. Z-score of H4 close vs SMA(50)/StdDev(50) crosses ±1.5
    3. Daily ADX < 25 (range-bound)
    4. RSI(14) H4 < 30 (long) or > 70 (short) — confirmation
    5. No entry on macro blackout days

    EXIT:
    1. Z-score crosses 0 (return to mean) → TP
    2. Hard stop: 2.0x Daily ATR
    3. Regime break: ADX Daily crosses 30 → exit immediately
    4. Time stop: 7 days max hold
    5. Friday 16:50 ET flatten all

    RISK:
    - 1.5% per trade (fixed fractional, ATR-based sizing)
    - Max 4 concurrent positions
    - Max 3 positions same currency exposure
    - Daily DD limit: 3% | Weekly DD limit: 5%
    - DD throttle: >4% rolling 20-day DD → reduce to 0.75%

    PAIRS: AUDCAD, NZDCAD, AUDNZD, EURGBP
    TIMEFRAME: H4 for signals/Z-score, Daily for regime/HV/ADX/ATR
    PARAMETERS: 5 (zscore_entry, lookback, hv_percentile_max, adx_max, risk_per_trade)
    """

    VERSION = "VRMR-V1.0"

    def Initialize(self):
        # ── Backtest window ──
        start_year = int(self.GetParameter("start_year", 2010))
        end_year = int(self.GetParameter("end_year", 2020))
        end_month = int(self.GetParameter("end_month", 12))
        self.SetStartDate(start_year, 1, 1)
        self.SetEndDate(end_year, end_month, 28)
        self.SetCash(10000)
        self.SetBrokerageModel(BrokerageName.OandaBrokerage, AccountType.Margin)

        # ══════════════════════════════════════════════
        # PARAMETERS (5 max per contract §7)
        # ══════════════════════════════════════════════
        self.zscore_entry = float(self.GetParameter("zscore_entry", 1.5))
        self.lookback = int(self.GetParameter("lookback", 50))
        self.hv_percentile_max = float(self.GetParameter("hv_pctl_max", 75))
        self.adx_max = int(self.GetParameter("adx_max", 25))
        self.risk_per_trade = float(self.GetParameter("risk_per_trade", 0.015))

        # ── Fixed config (not counted as free params) ──
        self.zscore_exit = 0.0
        self.rsi_ob = 70
        self.rsi_os = 30
        self.hard_stop_atr = 2.0
        self.max_hold_days = 7
        self.risk_reduced = self.risk_per_trade * 0.5
        self.max_positions = 4
        self.max_cluster = 3
        self.max_daily_risk = 0.03
        self.max_weekly_risk = 0.05
        self.dd_threshold = 0.04
        self.adx_exit_threshold = 30
        self.hv_period = 20  # 20-day historical volatility
        self.hv_lookback = 252  # 1 year of daily bars for percentile

        # ── Pair universe (4 structurally mean-reverting pairs) ──
        self.pair_tickers = ["AUDCAD", "NZDCAD", "AUDNZD", "EURGBP"]
        self.symbols = {}
        self.pairs_data = {}

        for ticker in self.pair_tickers:
            forex = self.AddForex(ticker, Resolution.Hour, Market.Oanda)
            forex.SetLeverage(10)
            sym = forex.Symbol
            self.symbols[ticker] = sym

            self.pairs_data[ticker] = {
                # H4 indicators
                "rsi_h": self.RSI(sym, 14, MovingAverageType.Simple, Resolution.Hour),
                # Daily indicators for regime and sizing
                "adx_d": self.ADX(sym, 14, Resolution.Daily),
                "atr_d": self.ATR(sym, 14, MovingAverageType.Simple, Resolution.Daily),
                # Price history for Z-score calculation (H4 closes)
                "close_history": [],
                "last_h4_bar": None,
                # Daily close history for HV calculation
                "daily_closes": [],
                "last_daily_bar": None,
                # HV percentile tracking
                "hv_history": [],  # Rolling HV values for percentile calc
                # Position tracking
                "entry_price": 0.0,
                "entry_direction": 0,  # 1=long, -1=short
                "entry_date": None,
                "hard_stop": 0.0,
                "entry_zscore": 0.0,
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

        # ── Warmup: 400 days for EMA/HV history + indicators ──
        self.SetWarmUp(timedelta(days=400))

        self.Log(f"[VRMR] {self.VERSION} | Pairs: {self.pair_tickers}")
        self.Log(f"[VRMR] Z-score: entry={self.zscore_entry}, exit={self.zscore_exit}, lookback={self.lookback}")
        self.Log(f"[VRMR] HV filter: period={self.hv_period}, percentile_max={self.hv_percentile_max}")
        self.Log(f"[VRMR] Regime: ADX max={self.adx_max}, ADX exit={self.adx_exit_threshold}")
        self.Log(f"[VRMR] Stop: {self.hard_stop_atr}x ATR | Max hold: {self.max_hold_days}d")
        self.Log(f"[VRMR] Risk: {self.risk_per_trade*100}%/trade")

    # ═══════════════════════════════════════════════════════════
    #  HISTORICAL VOLATILITY CALCULATION
    # ═══════════════════════════════════════════════════════════

    def _calc_hv(self, daily_closes):
        """Calculate annualized historical volatility from daily closes."""
        if len(daily_closes) < self.hv_period + 1:
            return None
        # Log returns over hv_period
        recent = daily_closes[-(self.hv_period + 1):]
        log_returns = []
        for i in range(1, len(recent)):
            if recent[i-1] > 0 and recent[i] > 0:
                log_returns.append(np.log(recent[i] / recent[i-1]))
        if len(log_returns) < self.hv_period:
            return None
        hv = np.std(log_returns) * np.sqrt(252)
        return float(hv)

    def _get_hv_percentile(self, ticker):
        """Get current HV percentile rank within its rolling history."""
        pd = self.pairs_data[ticker]
        hv_hist = pd["hv_history"]
        if len(hv_hist) < 60:  # Need at least 60 days of HV history
            return None
        current_hv = hv_hist[-1]
        count_below = sum(1 for h in hv_hist if h <= current_hv)
        percentile = (count_below / len(hv_hist)) * 100.0
        return percentile

    # ═══════════════════════════════════════════════════════════
    #  Z-SCORE CALCULATION
    # ═══════════════════════════════════════════════════════════

    def _calc_zscore(self, ticker):
        """Calculate Z-score of current price vs SMA/StdDev of H4 closes."""
        pd = self.pairs_data[ticker]
        history = pd["close_history"]

        if len(history) < self.lookback:
            return None

        window = history[-self.lookback:]
        mean = sum(window) / len(window)
        variance = sum((x - mean) ** 2 for x in window) / len(window)
        if variance <= 0:
            return None
        std = variance ** 0.5
        if std <= 0:
            return None

        current = history[-1]
        zscore = (current - mean) / std
        return zscore

    # ═══════════════════════════════════════════════════════════
    #  MAIN DATA HANDLER
    # ═══════════════════════════════════════════════════════════

    def OnData(self, data: Slice):
        if self.IsWarmingUp:
            # Still collect daily closes during warmup for HV history
            self._collect_warmup_data(data)
            return

        hour_et = self.Time.hour

        # ── Daily reset + collect daily closes ──
        if self.last_trade_date is None or self.Time.date() != self.last_trade_date:
            self.day_start_equity = float(self.Portfolio.TotalPortfolioValue)
            self.last_trade_date = self.Time.date()
            for t in self.pair_tickers:
                self.pairs_data[t]["traded_today"] = False
            self.equity_history.append(self.day_start_equity)
            if len(self.equity_history) > 30:
                self.equity_history = self.equity_history[-30:]

            # Collect daily close for HV calculation
            for ticker in self.pair_tickers:
                sym = self.symbols[ticker]
                if data.ContainsKey(sym):
                    bar = data[sym]
                    if bar is not None:
                        price = float(bar.Close) if hasattr(bar, 'Close') else float(bar.Value)
                        pd = self.pairs_data[ticker]
                        day_key = self.Time.strftime("%Y-%m-%d")
                        if pd["last_daily_bar"] != day_key:
                            pd["last_daily_bar"] = day_key
                            pd["daily_closes"].append(price)
                            if len(pd["daily_closes"]) > self.hv_lookback + 50:
                                pd["daily_closes"] = pd["daily_closes"][-(self.hv_lookback + 50):]
                            # Calculate and store HV
                            hv = self._calc_hv(pd["daily_closes"])
                            if hv is not None:
                                pd["hv_history"].append(hv)
                                if len(pd["hv_history"]) > self.hv_lookback:
                                    pd["hv_history"] = pd["hv_history"][-self.hv_lookback:]

        # ── Collect H4 closes (every 4 hours: 0, 4, 8, 12, 16, 20 ET) ──
        if hour_et in [0, 4, 8, 12, 16, 20]:
            for ticker in self.pair_tickers:
                sym = self.symbols[ticker]
                if not data.ContainsKey(sym):
                    continue
                bar = data[sym]
                if bar is None:
                    continue
                price = float(bar.Close) if hasattr(bar, 'Close') else float(bar.Value)

                pd = self.pairs_data[ticker]
                h4_key = f"{self.Time.date()}_{hour_et}"
                if pd["last_h4_bar"] != h4_key:
                    pd["last_h4_bar"] = h4_key
                    pd["close_history"].append(price)
                    if len(pd["close_history"]) > self.lookback + 50:
                        pd["close_history"] = pd["close_history"][-(self.lookback + 50):]

        # ── Manage open positions (every hour) ──
        for ticker in self.pair_tickers:
            sym = self.symbols[ticker]
            if not data.ContainsKey(sym):
                continue
            if self.Portfolio[sym].Invested:
                self._manage_position(ticker, data)

        # ── Entry checks only at H4 boundaries during London+NY ──
        if hour_et not in [4, 8, 12, 16]:
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
            self._check_mr_entry(ticker, data)

    def _collect_warmup_data(self, data):
        """Collect daily close data during warmup for HV history building."""
        if self.last_trade_date is None or self.Time.date() != self.last_trade_date:
            self.last_trade_date = self.Time.date()
            for ticker in self.pair_tickers:
                sym = self.symbols[ticker]
                if data.ContainsKey(sym):
                    bar = data[sym]
                    if bar is not None:
                        price = float(bar.Close) if hasattr(bar, 'Close') else float(bar.Value)
                        pd = self.pairs_data[ticker]
                        day_key = self.Time.strftime("%Y-%m-%d")
                        if pd["last_daily_bar"] != day_key:
                            pd["last_daily_bar"] = day_key
                            pd["daily_closes"].append(price)
                            if len(pd["daily_closes"]) > self.hv_lookback + 50:
                                pd["daily_closes"] = pd["daily_closes"][-(self.hv_lookback + 50):]
                            hv = self._calc_hv(pd["daily_closes"])
                            if hv is not None:
                                pd["hv_history"].append(hv)
                                if len(pd["hv_history"]) > self.hv_lookback:
                                    pd["hv_history"] = pd["hv_history"][-self.hv_lookback:]

        # Also collect H4 data during warmup
        hour_et = self.Time.hour
        if hour_et in [0, 4, 8, 12, 16, 20]:
            for ticker in self.pair_tickers:
                sym = self.symbols[ticker]
                if not data.ContainsKey(sym):
                    continue
                bar = data[sym]
                if bar is None:
                    continue
                price = float(bar.Close) if hasattr(bar, 'Close') else float(bar.Value)
                pd = self.pairs_data[ticker]
                h4_key = f"{self.Time.date()}_{hour_et}"
                if pd["last_h4_bar"] != h4_key:
                    pd["last_h4_bar"] = h4_key
                    pd["close_history"].append(price)
                    if len(pd["close_history"]) > self.lookback + 50:
                        pd["close_history"] = pd["close_history"][-(self.lookback + 50):]

    # ═══════════════════════════════════════════════════════════
    #  ENTRY: MEAN REVERSION WITH VOL-REGIME FILTER
    # ═══════════════════════════════════════════════════════════

    def _check_mr_entry(self, ticker, data):
        """Enter when Z-score extreme, regime range-bound, HV low, and RSI confirms."""
        pd = self.pairs_data[ticker]
        sym = self.symbols[ticker]

        # ── HV percentile filter (KEY INNOVATION) ──
        hv_pctl = self._get_hv_percentile(ticker)
        if hv_pctl is None:
            return
        if hv_pctl > self.hv_percentile_max:
            return  # High volatility regime — MR is dangerous

        # ── Z-score must be extreme ──
        zscore = self._calc_zscore(ticker)
        if zscore is None:
            return

        # ── Regime filter: ADX must be LOW (range-bound market) ──
        if not pd["adx_d"].IsReady:
            return
        adx = float(pd["adx_d"].Current.Value)
        if adx >= self.adx_max:
            return  # Trending — MR is dangerous

        # ── RSI confirmation ──
        if not pd["rsi_h"].IsReady:
            return
        rsi = float(pd["rsi_h"].Current.Value)

        # ── Determine direction ──
        rsi_long_ok = (self.rsi_os <= 0) or (rsi <= self.rsi_os)
        rsi_short_ok = (self.rsi_ob >= 100) or (rsi >= self.rsi_ob)

        direction = 0
        if zscore <= -self.zscore_entry and rsi_long_ok:
            direction = 1  # Oversold → go long
        elif zscore >= self.zscore_entry and rsi_short_ok:
            direction = -1  # Overbought → go short

        if direction == 0:
            return

        # ── Daily ATR for stop ──
        if not pd["atr_d"].IsReady:
            return
        atr_d = float(pd["atr_d"].Current.Value)
        if atr_d <= 0:
            return

        bar = data[sym]
        if bar is None:
            return
        price = float(bar.Close) if hasattr(bar, 'Close') else float(bar.Value)

        # ── Hard stop ──
        if direction == 1:
            stop_price = price - self.hard_stop_atr * atr_d
        else:
            stop_price = price + self.hard_stop_atr * atr_d

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

        self.Log(f"[ENTRY-VRMR {side}] {ticker} @ {price:.5f} | "
                 f"Z={zscore:.2f} | RSI={rsi:.1f} | ADX={adx:.1f} | "
                 f"HV_pctl={hv_pctl:.0f}% | "
                 f"Stop={stop_price:.5f} | ATR={atr_d:.5f} | Risk={current_risk*100:.1f}%")

        pd["entry_direction"] = direction
        pd["entry_price"] = price
        pd["entry_date"] = self.Time
        pd["hard_stop"] = stop_price
        pd["entry_zscore"] = zscore
        pd["traded_today"] = True

    # ═══════════════════════════════════════════════════════════
    #  POSITION MANAGEMENT
    # ═══════════════════════════════════════════════════════════

    def _manage_position(self, ticker, data):
        """Exit on: hard stop, regime break, Z-score reversion, or time stop."""
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

        # ── EXIT 1: Hard stop ──
        if direction == 1 and price_low <= pd["hard_stop"]:
            self.Liquidate(sym)
            pnl_pct = (price - pd["entry_price"]) / pd["entry_price"] * 100
            self.Log(f"[EXIT STOP LONG] {ticker} @ {price:.5f} | "
                     f"Entry={pd['entry_price']:.5f} | PnL={pnl_pct:.2f}%")
            self._reset_pair_state(ticker)
            return

        if direction == -1 and price_high >= pd["hard_stop"]:
            self.Liquidate(sym)
            pnl_pct = (pd["entry_price"] - price) / pd["entry_price"] * 100
            self.Log(f"[EXIT STOP SHORT] {ticker} @ {price:.5f} | "
                     f"Entry={pd['entry_price']:.5f} | PnL={pnl_pct:.2f}%")
            self._reset_pair_state(ticker)
            return

        # ── EXIT 2: Regime break — ADX crosses above threshold ──
        if pd["adx_d"].IsReady:
            adx = float(pd["adx_d"].Current.Value)
            if adx >= self.adx_exit_threshold:
                self.Liquidate(sym)
                pnl_pct = (price - pd["entry_price"]) / pd["entry_price"] * 100 if direction == 1 else \
                           (pd["entry_price"] - price) / pd["entry_price"] * 100
                self.Log(f"[EXIT REGIME] {ticker} @ {price:.5f} | ADX={adx:.1f}>={self.adx_exit_threshold} | "
                         f"Entry={pd['entry_price']:.5f} | PnL={pnl_pct:.2f}%")
                self._reset_pair_state(ticker)
                return

        # ── EXIT 3: Z-score reversion to mean (TP) ──
        zscore = self._calc_zscore(ticker)
        if zscore is not None:
            if direction == 1 and zscore >= self.zscore_exit:
                self.Liquidate(sym)
                pnl_pct = (price - pd["entry_price"]) / pd["entry_price"] * 100
                self.Log(f"[EXIT TP LONG] {ticker} @ {price:.5f} | Z={zscore:.2f} | "
                         f"Entry={pd['entry_price']:.5f} | PnL={pnl_pct:.2f}%")
                self._reset_pair_state(ticker)
                return

            if direction == -1 and zscore <= self.zscore_exit:
                self.Liquidate(sym)
                pnl_pct = (pd["entry_price"] - price) / pd["entry_price"] * 100
                self.Log(f"[EXIT TP SHORT] {ticker} @ {price:.5f} | Z={zscore:.2f} | "
                         f"Entry={pd['entry_price']:.5f} | PnL={pnl_pct:.2f}%")
                self._reset_pair_state(ticker)
                return

        # ── EXIT 4: Time stop ──
        if pd["entry_date"] is not None:
            days_held = (self.Time - pd["entry_date"]).days
            if days_held >= self.max_hold_days:
                self.Liquidate(sym)
                pnl_pct = (price - pd["entry_price"]) / pd["entry_price"] * 100 if direction == 1 else \
                           (pd["entry_price"] - price) / pd["entry_price"] * 100
                self.Log(f"[EXIT TIME] {ticker} @ {price:.5f} | Days={days_held} | "
                         f"Entry={pd['entry_price']:.5f} | PnL={pnl_pct:.2f}%")
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
                zscore = self._calc_zscore(ticker) or 0
                hv_pctl = self._get_hv_percentile(ticker) or 0
                positions.append(f"{ticker}={'L' if h.IsLong else 'S'}(Z={zscore:.1f},HV={hv_pctl:.0f}%)")
        pos_str = ", ".join(positions) if positions else "FLAT"
        self.Log(f"[EOD] Equity=${equity:.2f} | DailyPnL=${daily_pnl:.2f} | {pos_str}")

    def _reset_pair_state(self, ticker):
        pd = self.pairs_data[ticker]
        pd["entry_direction"] = 0
        pd["entry_price"] = 0.0
        pd["entry_date"] = None
        pd["hard_stop"] = 0.0
        pd["entry_zscore"] = 0.0

    # ═══════════════════════════════════════════════════════════
    #  MACRO EVENT FILTER
    # ═══════════════════════════════════════════════════════════

    def _is_macro_day(self):
        return self.Time.date() in self.macro_blackout_dates

    def _build_macro_calendar(self):
        """FOMC + RBA + RBNZ + BoC + ECB + BoE rate decision dates 2010-2024."""
        dates = set()
        # FOMC dates 2010-2024
        fomc = [
            # 2010
            "2010-01-27", "2010-03-16", "2010-04-28", "2010-06-23",
            "2010-08-10", "2010-09-21", "2010-11-03", "2010-12-14",
            # 2011
            "2011-01-26", "2011-03-15", "2011-04-27", "2011-06-22",
            "2011-08-09", "2011-09-21", "2011-11-02", "2011-12-13",
            # 2012
            "2012-01-25", "2012-03-13", "2012-04-25", "2012-06-20",
            "2012-08-01", "2012-09-13", "2012-10-24", "2012-12-12",
            # 2013
            "2013-01-30", "2013-03-20", "2013-05-01", "2013-06-19",
            "2013-07-31", "2013-09-18", "2013-10-30", "2013-12-18",
            # 2014
            "2014-01-29", "2014-03-19", "2014-04-30", "2014-06-18",
            "2014-07-30", "2014-09-17", "2014-10-29", "2014-12-17",
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
        # ECB major dates
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
        # RBA
        rba = [
            "2020-02-04", "2020-03-03", "2020-04-07", "2020-05-05", "2020-06-02",
            "2020-07-07", "2020-08-04", "2020-09-01", "2020-10-06", "2020-11-03", "2020-12-01",
            "2021-02-02", "2021-03-02", "2021-04-06", "2021-05-04", "2021-06-01",
            "2021-07-06", "2021-08-03", "2021-09-07", "2021-10-05", "2021-11-02", "2021-12-07",
            "2022-02-01", "2022-03-01", "2022-04-05", "2022-05-03", "2022-06-07",
            "2022-07-05", "2022-08-02", "2022-09-06", "2022-10-04", "2022-11-01", "2022-12-06",
            "2023-02-07", "2023-03-07", "2023-04-04", "2023-05-02", "2023-06-06",
            "2023-07-04", "2023-08-01", "2023-09-05", "2023-10-03", "2023-11-07", "2023-12-05",
            "2024-02-06", "2024-03-19", "2024-05-07", "2024-06-18", "2024-08-06",
            "2024-09-24", "2024-11-05", "2024-12-10",
        ]
        # BoC
        boc = [
            "2020-01-22", "2020-03-04", "2020-03-27", "2020-04-15", "2020-06-03",
            "2020-07-15", "2020-09-09", "2020-10-28", "2020-12-09",
            "2021-01-20", "2021-03-10", "2021-04-21", "2021-06-09",
            "2021-07-14", "2021-09-08", "2021-10-27", "2021-12-08",
            "2022-01-26", "2022-03-02", "2022-04-13", "2022-06-01",
            "2022-07-13", "2022-09-07", "2022-10-26", "2022-12-07",
            "2023-01-25", "2023-03-08", "2023-04-12", "2023-06-07",
            "2023-07-12", "2023-09-06", "2023-10-25", "2023-12-06",
            "2024-01-24", "2024-03-06", "2024-04-10", "2024-06-05",
            "2024-07-24", "2024-09-04", "2024-10-23", "2024-12-11",
        ]
        # BoE
        boe = [
            "2015-01-08", "2015-02-05", "2015-03-05", "2015-05-07", "2015-06-04",
            "2015-08-06", "2015-09-10", "2015-11-05", "2015-12-10",
            "2016-01-14", "2016-03-17", "2016-05-12", "2016-06-16",
            "2016-08-04", "2016-09-15", "2016-11-03", "2016-12-15",
            "2017-02-02", "2017-03-16", "2017-05-11", "2017-06-15",
            "2017-08-03", "2017-09-14", "2017-11-02", "2017-12-14",
            "2018-02-08", "2018-03-22", "2018-05-10", "2018-06-21",
            "2018-08-02", "2018-09-13", "2018-11-01", "2018-12-20",
            "2019-02-07", "2019-03-21", "2019-05-02", "2019-06-20",
            "2019-08-01", "2019-09-19", "2019-11-07", "2019-12-19",
            "2020-01-30", "2020-03-11", "2020-03-19", "2020-05-07", "2020-06-18",
            "2020-08-06", "2020-09-17", "2020-11-05", "2020-12-17",
            "2021-02-04", "2021-03-18", "2021-05-06", "2021-06-24",
            "2021-08-05", "2021-09-23", "2021-11-04", "2021-12-16",
            "2022-02-03", "2022-03-17", "2022-05-05", "2022-06-16",
            "2022-08-04", "2022-09-22", "2022-11-03", "2022-12-15",
            "2023-02-02", "2023-03-23", "2023-05-11", "2023-06-22",
            "2023-08-03", "2023-09-21", "2023-11-02", "2023-12-14",
            "2024-02-01", "2024-03-21", "2024-05-09", "2024-06-20",
            "2024-08-01", "2024-09-19", "2024-11-07", "2024-12-19",
        ]

        for d_str in fomc + ecb + rba + boc + boe:
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
