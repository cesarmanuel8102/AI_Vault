# region imports
from AlgorithmImports import *
from datetime import datetime, timedelta
import numpy as np
# endregion


class CommodityCrossMR(QCAlgorithm):
    """
    Brain V9 — Commodity Cross Mean Reversion V1.0

    HYPOTHESIS: AUDCAD, NZDCAD, AUDNZD are structurally mean-reverting because
    Australia, New Zealand, and Canada are correlated commodity-exporting economies.
    Deviations >2 sigma from the 50-period mean on H4, filtered by range-bound regime,
    should revert with sufficient frequency to generate net edge.

    FAMILY: Mean Reversion Conditioned by Regime (Contract Section 5.1)

    ENTRY:
    1. Z-score of H4 close vs SMA(50) / StdDev(50) crosses -2.0 (long) or +2.0 (short)
    2. Regime filter: Daily ADX < 25 (no strong trend)
    3. Confirmation: RSI(14) H4 < 30 (long) or > 70 (short)

    EXIT:
    1. Z-score crosses 0 (return to mean) → TP
    2. Time stop: 10 days max hold
    3. Regime break: ADX Daily crosses 30 → exit immediately
    4. Hard stop: 2.5x Daily ATR

    RISK:
    - 1% per trade, max 3 positions, max 2% daily / 4% weekly
    - Reduce to 0.5% if rolling 20-day DD > 5%

    PAIRS: AUDCAD, NZDCAD, AUDNZD
    TIMEFRAME: H4 for signals, Daily for regime/ATR
    PARENT: None (new line of research)
    BASELINE: V4.0b Squeeze (+6.32%, 104 trades, P/L 1.07, DD 8.8%)
    """

    VERSION = "CMR-V1.0"

    def Initialize(self):
        # ── Backtest window (parameterized for IS/OOS splits) ──
        start_year = int(self.GetParameter("start_year", 2020))
        end_year = int(self.GetParameter("end_year", 2024))
        end_month = int(self.GetParameter("end_month", 12))
        self.SetStartDate(start_year, 1, 1)
        self.SetEndDate(end_year, end_month, 28)
        self.SetCash(10000)
        self.SetBrokerageModel(BrokerageName.OandaBrokerage, AccountType.Margin)

        # ── Parameters ──
        self.risk_per_trade = float(self.GetParameter("risk_per_trade", 0.01))
        self.risk_reduced = float(self.GetParameter("risk_reduced", 0.005))  # Reduced risk during DD
        self.max_daily_risk = float(self.GetParameter("max_daily_risk", 0.02))
        self.max_weekly_risk = float(self.GetParameter("max_weekly_risk", 0.04))
        self.max_positions = int(self.GetParameter("max_positions", 3))
        self.max_cluster = int(self.GetParameter("max_cluster", 2))

        # Mean Reversion parameters
        self.zscore_entry = float(self.GetParameter("zscore_entry", 2.0))
        self.zscore_exit = float(self.GetParameter("zscore_exit", 0.0))  # Exit at mean
        self.lookback = int(self.GetParameter("lookback", 50))  # SMA/StdDev lookback on H4
        self.rsi_ob = float(self.GetParameter("rsi_ob", 70))  # RSI overbought threshold
        self.rsi_os = float(self.GetParameter("rsi_os", 30))  # RSI oversold threshold
        self.hard_stop_atr = float(self.GetParameter("hard_stop_atr", 2.5))  # Stop in ATR units
        self.max_hold_days = int(self.GetParameter("max_hold_days", 10))

        # Regime filter parameters
        self.adx_max = int(self.GetParameter("adx_max", 25))  # Max ADX for entry (range-bound)
        self.adx_exit_threshold = int(self.GetParameter("adx_exit", 30))  # ADX above this = regime break exit

        # DD throttling
        self.dd_threshold = float(self.GetParameter("dd_threshold", 0.05))  # 5% rolling DD → reduce risk

        # ── Pair universe (parameterized) ──
        # Group A: Commodity crosses (AUD/NZD/CAD)
        # Group B: European crosses (EURGBP, EURCHF, GBPCHF)
        # Group C: Commodity-Safe haven (AUDCHF, NZDCHF)
        use_eurgbp = int(self.GetParameter("use_eurgbp", 0))
        use_chf = int(self.GetParameter("use_chf", 0))  # EURCHF, GBPCHF
        use_comchf = int(self.GetParameter("use_comchf", 0))  # AUDCHF, NZDCHF
        self.pair_tickers = ["AUDCAD", "NZDCAD", "AUDNZD"]
        if use_eurgbp:
            self.pair_tickers.append("EURGBP")
        if use_chf:
            self.pair_tickers.extend(["EURCHF", "GBPCHF"])
        if use_comchf:
            self.pair_tickers.extend(["AUDCHF", "NZDCHF"])
        self.symbols = {}
        self.pairs_data = {}

        for ticker in self.pair_tickers:
            forex = self.AddForex(ticker, Resolution.Hour, Market.Oanda)
            forex.SetLeverage(10)
            sym = forex.Symbol
            self.symbols[ticker] = sym

            self.pairs_data[ticker] = {
                # H4 indicators (we'll use hourly and sample every 4 hours)
                "rsi_h": self.RSI(sym, 14, MovingAverageType.Simple, Resolution.Hour),
                # Daily indicators for regime and sizing
                "adx_d": self.ADX(sym, 14, Resolution.Daily),
                "atr_d": self.ATR(sym, 14, MovingAverageType.Simple, Resolution.Daily),
                # Price history for Z-score calculation (H4 closes)
                "close_history": [],
                "last_h4_bar": None,  # Track which 4H bar we last processed
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
        self.equity_history = []  # For rolling DD calculation
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

        # ── Warmup: 250 days for daily indicators + H4 history ──
        self.SetWarmUp(timedelta(days=250))

        self.Log(f"[CMR] {self.VERSION} | Pairs: {self.pair_tickers}")
        self.Log(f"[CMR] Z-score: entry={self.zscore_entry}, exit={self.zscore_exit}, lookback={self.lookback}")
        self.Log(f"[CMR] RSI: OS={self.rsi_os}, OB={self.rsi_ob}")
        self.Log(f"[CMR] Regime: ADX max={self.adx_max}, ADX exit={self.adx_exit_threshold}")
        self.Log(f"[CMR] Stop: {self.hard_stop_atr}x ATR | Max hold: {self.max_hold_days}d")
        self.Log(f"[CMR] Risk: {self.risk_per_trade*100}%/trade (reduced={self.risk_reduced*100}%)")

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
            # Track equity for rolling DD
            self.equity_history.append(self.day_start_equity)
            if len(self.equity_history) > 30:
                self.equity_history = self.equity_history[-30:]

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
    #  ENTRY: MEAN REVERSION ON COMMODITY CROSSES
    # ═══════════════════════════════════════════════════════════

    def _check_mr_entry(self, ticker, data):
        """Enter when Z-score is extreme AND regime is range-bound AND RSI confirms."""
        pd = self.pairs_data[ticker]
        sym = self.symbols[ticker]

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
        # RSI filter: disabled when rsi_os=0 and rsi_ob=100
        rsi_long_ok = (self.rsi_os <= 0) or (rsi <= self.rsi_os)
        rsi_short_ok = (self.rsi_ob >= 100) or (rsi >= self.rsi_ob)

        direction = 0
        if zscore <= -self.zscore_entry and rsi_long_ok:
            direction = 1  # Price oversold → go long for mean reversion
        elif zscore >= self.zscore_entry and rsi_short_ok:
            direction = -1  # Price overbought → go short for mean reversion

        if direction == 0:
            return

        # ── Daily ATR for stop calculation ──
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

        # ── Position size (with DD throttling) ──
        current_risk = self._get_current_risk_pct()
        qty = self._calculate_position_size(ticker, price, risk_distance, current_risk)
        if qty <= 0:
            return

        if not self.Securities[sym].Exchange.ExchangeOpen:
            return

        # ── Execute ──
        side = "LONG" if direction == 1 else "SHORT"
        self.MarketOrder(sym, qty if direction == 1 else -qty)

        self.Log(f"[ENTRY-MR {side}] {ticker} @ {price:.5f} | "
                 f"Z={zscore:.2f} | RSI={rsi:.1f} | ADX={adx:.1f} | "
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
        """Exit on: Z-score reversion, time stop, regime break, or hard stop."""
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
            self.Log(f"[DD THROTTLE] Rolling DD={dd*100:.1f}% >= {self.dd_threshold*100}% → risk reduced to {self.risk_reduced*100:.1f}%")
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
        """Monday 00:00 — Reset weekly equity tracking."""
        self.week_start_equity = float(self.Portfolio.TotalPortfolioValue)

    def _eod_log(self):
        """16:55 ET — Daily summary."""
        equity = float(self.Portfolio.TotalPortfolioValue)
        daily_pnl = equity - self.day_start_equity
        positions = []
        for ticker in self.pair_tickers:
            sym = self.symbols[ticker]
            if self.Portfolio[sym].Invested:
                h = self.Portfolio[sym]
                zscore = self._calc_zscore(ticker) or 0
                positions.append(f"{ticker}={'L' if h.IsLong else 'S'}(Z={zscore:.1f})")
        pos_str = ", ".join(positions) if positions else "FLAT"
        self.Log(f"[EOD] Equity=${equity:.2f} | DailyPnL=${daily_pnl:.2f} | {pos_str}")

    def _reset_pair_state(self, ticker):
        """Clear position tracking after exit."""
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
        """No new entries on FOMC/RBA/RBNZ/BoC days."""
        return self.Time.date() in self.macro_blackout_dates

    def _build_macro_calendar(self):
        """FOMC + RBA + RBNZ + BoC rate decision dates 2020-2024."""
        dates = set()
        # FOMC dates
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
        # RBA (Reserve Bank of Australia) — first Tuesday of each month (approx)
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
        # BoC (Bank of Canada) — 8 meetings/year
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
        # RBNZ (Reserve Bank of New Zealand) — 7 meetings/year
        rbnz = [
            "2020-02-12", "2020-03-16", "2020-03-25", "2020-05-13", "2020-06-24",
            "2020-08-12", "2020-09-23", "2020-11-11",
            "2021-02-24", "2021-04-14", "2021-05-26", "2021-07-14",
            "2021-08-18", "2021-10-06", "2021-11-24",
            "2022-02-23", "2022-04-13", "2022-05-25", "2022-07-13",
            "2022-08-17", "2022-10-05", "2022-11-23",
            "2023-02-22", "2023-04-05", "2023-05-24", "2023-07-12",
            "2023-08-16", "2023-10-04", "2023-11-29",
            "2024-02-28", "2024-04-10", "2024-05-22", "2024-07-10",
            "2024-08-14", "2024-10-09", "2024-11-27",
        ]

        for d_str in fomc + rba + boc + rbnz:
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
