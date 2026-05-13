# region imports
from AlgorithmImports import *
from datetime import datetime, timedelta
# endregion


class TimeSeriesMomentumFX(QCAlgorithm):
    """
    Brain V9 — Time-Series Momentum V1.5

    PARENT: TSM-V1.1 (+2.04%, DD 15.7%, WR 40%, P/L 1.40, 297 orders) — STILL CHAMPION

    V1.3 FAILED: no stop + vol 6.5% = -2.68%, WR 35%.
    V1.4 PARTIALLY WORKED: ADX entry+exit = -1.90%, DD 11% (best DD yet), WR 44%,
    BUT P/L crashed to 1.00 because ADX exit was cutting winners during trend pauses.

    CHANGES FROM V1.4:
    1. KEEP ADX entry gate (ADX > 20 to open new positions) — improved WR from 40→44%
    2. REMOVE ADX exit — let positions ride through trend pauses (V1.4's killer)
    3. MONTHLY rebalance (rebal_freq:4 = every 4 weeks) — academic TSM rebalances monthly
       This reduces turnover further and lets winners run longer
    4. Keep emergency stop at 2% (V1.1's value — confirmed load-bearing)
    5. Keep vol target at 5%, signal threshold 0.15 (V1.1 base)

    HYPOTHESIS: ADX entry gate filters bad entries (proven by V1.4's improved WR/DD).
    ADX exit killed P/L by cutting winners. Monthly rebalance aligns with academic
    evidence (Moskowitz: momentum profits peak at 12-month horizon with monthly rebal).
    """

    VERSION = "TSM-V1.5"

    def Initialize(self):
        # ── Backtest window ──
        start_year = int(self.GetParameter("start_year", 2020))
        end_year = int(self.GetParameter("end_year", 2024))
        end_month = int(self.GetParameter("end_month", 12))
        self.SetStartDate(start_year, 1, 1)
        self.SetEndDate(end_year, end_month, 28)
        self.SetCash(10000)
        self.SetBrokerageModel(BrokerageName.OandaBrokerage, AccountType.Margin)

        # ── Parameters (V1.1 base) ──
        self.mom_fast = int(self.GetParameter("mom_fast", 63))
        self.mom_med = int(self.GetParameter("mom_med", 126))
        self.mom_slow = int(self.GetParameter("mom_slow", 252))
        self.vol_lookback = int(self.GetParameter("vol_lookback", 63))
        self.vol_target = float(self.GetParameter("vol_target", 0.05))  # Back to 5% (V1.1)
        self.port_vol_target = float(self.GetParameter("port_vol_target", 0.10))
        self.emergency_stop = float(self.GetParameter("emergency_stop", 0.02))  # Back to 2% (V1.1)
        self.max_positions = int(self.GetParameter("max_positions", 6))
        self.signal_threshold = float(self.GetParameter("signal_threshold", 0.15))
        self.rebal_freq = int(self.GetParameter("rebal_freq", 2))

        # ── ADX Regime Filter (NEW in V1.4) ──
        self.adx_min = float(self.GetParameter("adx_min", 20))      # Only trade when ADX > 20
        self.adx_exit = float(self.GetParameter("adx_exit", 15))    # Exit when ADX < 15

        # ── FX Majors ──
        self.pair_tickers = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "USDCAD", "NZDUSD"]
        self.symbols = {}
        self.pairs_data = {}
        self.adx_indicators = {}

        for ticker in self.pair_tickers:
            forex = self.AddForex(ticker, Resolution.Daily, Market.Oanda)
            forex.SetLeverage(10)
            sym = forex.Symbol
            self.symbols[ticker] = sym

            # ADX indicator (14-period on Daily)
            self.adx_indicators[ticker] = self.ADX(sym, 14, Resolution.Daily)

            self.pairs_data[ticker] = {
                "close_history": [],
                "entry_direction": 0,
                "entry_price": 0.0,
                "last_signal": 0,
            }

        # ── Risk tracking ──
        self.last_rebalance = None
        self.rebal_count = 0

        # ── Macro blackout ──
        self.macro_blackout_dates = self._build_macro_calendar()

        # ── Biweekly rebalance on Monday 10:00 ET ──
        self.Schedule.On(
            self.DateRules.Every(DayOfWeek.Monday),
            self.TimeRules.At(10, 0),
            self._maybe_rebalance
        )

        # ── Daily emergency check ──
        self.Schedule.On(
            self.DateRules.EveryDay(),
            self.TimeRules.At(16, 0),
            self._check_emergency_exits
        )

        # ── ADX exit DISABLED in V1.5 — V1.4 showed it kills P/L by cutting winners ──
        # self.Schedule.On(
        #     self.DateRules.EveryDay(),
        #     self.TimeRules.At(16, 30),
        #     self._check_adx_exits
        # )

        self.Schedule.On(
            self.DateRules.EveryDay(),
            self.TimeRules.At(16, 55),
            self._eod_log
        )

        # ── Warmup ──
        self.SetWarmUp(timedelta(days=400))

        self.Log(f"[TSM] {self.VERSION} | Pairs: {self.pair_tickers}")
        self.Log(f"[TSM] Momentum: fast={self.mom_fast}d, med={self.mom_med}d, slow={self.mom_slow}d")
        self.Log(f"[TSM] Vol target: {self.vol_target*100}% per pos, {self.port_vol_target*100}% portfolio")
        self.Log(f"[TSM] ADX regime: entry>{self.adx_min}, exit<{self.adx_exit}")
        self.Log(f"[TSM] Emergency stop: {self.emergency_stop*100}%")

    # ═══════════════════════════════════════════════════════════
    #  DAILY DATA COLLECTION
    # ═══════════════════════════════════════════════════════════

    def OnData(self, data: Slice):
        if self.IsWarmingUp:
            return

        for ticker in self.pair_tickers:
            sym = self.symbols[ticker]
            if not data.ContainsKey(sym):
                continue
            bar = data[sym]
            if bar is None:
                continue
            price = float(bar.Close) if hasattr(bar, 'Close') else float(bar.Value)
            pd = self.pairs_data[ticker]
            pd["close_history"].append(price)
            if len(pd["close_history"]) > 500:
                pd["close_history"] = pd["close_history"][-500:]

    # ═══════════════════════════════════════════════════════════
    #  ADX REGIME CHECK
    # ═══════════════════════════════════════════════════════════

    def _get_adx(self, ticker):
        """Get current ADX value for a pair. Returns None if not ready."""
        adx = self.adx_indicators[ticker]
        if adx is not None and adx.IsReady:
            return float(adx.Current.Value)
        return None

    def _check_adx_exits(self):
        """Daily check: exit positions when ADX drops below exit threshold.
        This catches dying trends between rebalance dates.
        """
        if self.IsWarmingUp:
            return

        for ticker in self.pair_tickers:
            sym = self.symbols[ticker]
            if not self.Portfolio[sym].Invested:
                continue

            adx_val = self._get_adx(ticker)
            if adx_val is None:
                continue

            if adx_val < self.adx_exit:
                if self.Securities[sym].Exchange.ExchangeOpen:
                    self.Liquidate(sym)
                    self.Log(f"[TSM ADX EXIT] {ticker} | ADX={adx_val:.1f} < {self.adx_exit} | Trend died")
                    self.pairs_data[ticker]["entry_direction"] = 0

    # ═══════════════════════════════════════════════════════════
    #  SIGNAL CALCULATION — MULTI-SPEED 2-OF-3 + ADX GATE
    # ═══════════════════════════════════════════════════════════

    def _calc_tsm_signal(self, ticker):
        """Multi-speed time-series momentum with 2-of-3 agreement filter.
        Now includes ADX regime gate — no signal if market isn't trending.
        """
        # ADX regime gate
        adx_val = self._get_adx(ticker)
        if adx_val is not None and adx_val < self.adx_min:
            return 0.0  # Market not trending — no momentum signal

        pd = self.pairs_data[ticker]
        history = pd["close_history"]

        if len(history) < self.mom_slow + 5:
            return 0.0

        current = history[-1]

        # Calculate returns at each speed
        speeds = [self.mom_fast, self.mom_med, self.mom_slow]
        returns = {}
        directions = {}

        for speed in speeds:
            if len(history) < speed + 5:
                continue
            past = history[-speed]
            if past <= 0:
                continue
            ret = current / past - 1
            returns[speed] = ret
            directions[speed] = 1 if ret > 0 else (-1 if ret < 0 else 0)

        if len(directions) < 2:
            return 0.0

        # Count votes
        long_votes = sum(1 for d in directions.values() if d > 0)
        short_votes = sum(1 for d in directions.values() if d < 0)

        # 2-of-3 agreement required
        if long_votes >= 2:
            consensus_dir = 1
        elif short_votes >= 2:
            consensus_dir = -1
        else:
            return 0.0

        # Conviction: average magnitude of agreeing speeds, normalized by vol
        vol = self._calc_position_vol(ticker)
        if vol is None or vol < 0.001:
            return float(consensus_dir) * 0.5

        agreeing_returns = []
        for speed, direction in directions.items():
            if direction == consensus_dir:
                holding_vol = vol * ((speed / 252) ** 0.5) if speed > 0 else vol
                if holding_vol > 0:
                    normalized = abs(returns[speed]) / holding_vol
                    agreeing_returns.append(normalized)

        if not agreeing_returns:
            return float(consensus_dir) * 0.5

        avg_conviction = min(sum(agreeing_returns) / len(agreeing_returns), 3.0) / 3.0
        magnitude = 0.3 + 0.7 * avg_conviction

        return consensus_dir * magnitude

    def _calc_position_vol(self, ticker):
        """Calculate annualized volatility for vol-targeting."""
        pd = self.pairs_data[ticker]
        history = pd["close_history"]

        if len(history) < self.vol_lookback + 1:
            return None

        recent = history[-self.vol_lookback:]
        daily_returns = [(recent[i] / recent[i-1] - 1) for i in range(1, len(recent))]
        if len(daily_returns) < 5:
            return None

        mean_ret = sum(daily_returns) / len(daily_returns)
        var = sum((r - mean_ret) ** 2 for r in daily_returns) / len(daily_returns)
        daily_vol = var ** 0.5
        ann_vol = daily_vol * (252 ** 0.5)

        return ann_vol if ann_vol > 0.001 else None

    # ═══════════════════════════════════════════════════════════
    #  REBALANCE FREQUENCY CONTROL
    # ═══════════════════════════════════════════════════════════

    def _maybe_rebalance(self):
        """Biweekly rebalance gate."""
        if self.IsWarmingUp:
            return
        self.rebal_count += 1
        if self.rebal_count % self.rebal_freq != 0:
            return
        self._rebalance()

    # ═══════════════════════════════════════════════════════════
    #  REBALANCE LOGIC
    # ═══════════════════════════════════════════════════════════

    def _rebalance(self):
        """Rebalance: recalculate signals and adjust positions."""
        if self.IsWarmingUp:
            return

        # Macro blackout
        if self.Time.date() in self.macro_blackout_dates:
            self.Log(f"[TSM] Macro blackout — skip rebalance")
            return

        equity = float(self.Portfolio.TotalPortfolioValue)
        signals = {}
        vols = {}

        for ticker in self.pair_tickers:
            signal = self._calc_tsm_signal(ticker)
            vol = self._calc_position_vol(ticker)

            if vol is not None and abs(signal) > self.signal_threshold:
                signals[ticker] = signal
                vols[ticker] = vol

        if not signals:
            # If no signals but we have positions, close them
            for ticker in self.pair_tickers:
                sym = self.symbols[ticker]
                if self.Portfolio[sym].Invested and self.Securities[sym].Exchange.ExchangeOpen:
                    self.Liquidate(sym)
                    self.Log(f"[TSM EXIT] {ticker} | No qualifying signals at rebalance")
                    self.pairs_data[ticker]["entry_direction"] = 0
            return

        # Vol-targeted position sizing with conviction weighting
        target_notionals = {}
        for ticker in signals:
            if vols[ticker] <= 0:
                continue
            direction = 1.0 if signals[ticker] > 0 else -1.0
            magnitude = abs(signals[ticker])

            notional = equity * (self.vol_target / vols[ticker]) * magnitude * direction
            target_notionals[ticker] = notional

        # Cap to max positions
        n_active = len(target_notionals)
        if n_active > self.max_positions:
            sorted_by_strength = sorted(target_notionals.items(),
                                        key=lambda x: abs(signals[x[0]]), reverse=True)
            target_notionals = dict(sorted_by_strength[:self.max_positions])
            n_active = self.max_positions

        # Portfolio vol scaling (correlation-aware, rho=0.5)
        if n_active > 1:
            avg_rho = 0.5
            port_vol_est = self.vol_target * (n_active * (1 + (n_active - 1) * avg_rho)) ** 0.5
            if port_vol_est > self.port_vol_target:
                scale = self.port_vol_target / port_vol_est
                target_notionals = {t: n * scale for t, n in target_notionals.items()}

        # Execute
        for ticker in self.pair_tickers:
            sym = self.symbols[ticker]
            current_qty = self.Portfolio[sym].Quantity

            if ticker not in target_notionals:
                if current_qty != 0:
                    if self.Securities[sym].Exchange.ExchangeOpen:
                        self.Liquidate(sym)
                        self.Log(f"[TSM EXIT] {ticker} | Signal gone/below threshold | Qty was {current_qty}")
                        self.pairs_data[ticker]["entry_direction"] = 0
                continue

            price = float(self.Securities[sym].Price)
            if price <= 0:
                continue

            target_qty = int(target_notionals[ticker] / price)
            target_qty = (target_qty // 1000) * 1000

            if target_qty == 0:
                if current_qty != 0 and self.Securities[sym].Exchange.ExchangeOpen:
                    self.Liquidate(sym)
                    self.Log(f"[TSM EXIT] {ticker} | Target qty 0")
                    self.pairs_data[ticker]["entry_direction"] = 0
                continue

            # Only rebalance if difference is significant (>20% of target)
            diff = target_qty - current_qty
            if abs(diff) < abs(target_qty) * 0.20 and current_qty != 0:
                continue

            if not self.Securities[sym].Exchange.ExchangeOpen:
                continue

            order_qty = target_qty - current_qty
            if abs(order_qty) >= 1000:
                self.MarketOrder(sym, order_qty)
                direction = 1 if target_qty > 0 else -1
                side = "LONG" if direction == 1 else "SHORT"
                adx_val = self._get_adx(ticker)
                adx_str = f"{adx_val:.1f}" if adx_val else "N/A"
                self.Log(f"[TSM REBAL {side}] {ticker} | Signal={signals[ticker]:.3f} | "
                         f"Vol={vols[ticker]*100:.1f}% | ADX={adx_str} | "
                         f"Qty: {current_qty}->{target_qty} | d={order_qty}")
                self.pairs_data[ticker]["entry_direction"] = direction
                self.pairs_data[ticker]["entry_price"] = price

        self.last_rebalance = self.Time.date()

    # ═══════════════════════════════════════════════════════════
    #  EMERGENCY EXIT
    # ═══════════════════════════════════════════════════════════

    def _check_emergency_exits(self):
        """Daily check: exit if any position loses > emergency_stop % of equity."""
        if self.IsWarmingUp:
            return

        if self.emergency_stop <= 0:
            return

        equity = float(self.Portfolio.TotalPortfolioValue)
        for ticker in self.pair_tickers:
            sym = self.symbols[ticker]
            if not self.Portfolio[sym].Invested:
                continue

            unrealized = float(self.Portfolio[sym].UnrealizedProfit)
            if unrealized < -(equity * self.emergency_stop):
                if self.Securities[sym].Exchange.ExchangeOpen:
                    self.Liquidate(sym)
                    self.Log(f"[TSM EMERGENCY] {ticker} | Loss=${unrealized:.2f} > "
                             f"{self.emergency_stop*100}% equity")
                    self.pairs_data[ticker]["entry_direction"] = 0

    # ═══════════════════════════════════════════════════════════
    #  LOGGING
    # ═══════════════════════════════════════════════════════════

    def _eod_log(self):
        """16:55 ET daily summary."""
        equity = float(self.Portfolio.TotalPortfolioValue)
        positions = []
        for ticker in self.pair_tickers:
            sym = self.symbols[ticker]
            if self.Portfolio[sym].Invested:
                h = self.Portfolio[sym]
                pnl = float(h.UnrealizedProfit)
                adx_val = self._get_adx(ticker)
                adx_str = f"ADX={adx_val:.0f}" if adx_val else ""
                positions.append(f"{ticker}={'L' if h.IsLong else 'S'}(${pnl:.0f},{adx_str})")
        pos_str = ", ".join(positions) if positions else "FLAT"
        self.Log(f"[EOD] Equity=${equity:.2f} | {pos_str}")

    # ═══════════════════════════════════════════════════════════
    #  MACRO CALENDAR
    # ═══════════════════════════════════════════════════════════

    def _is_macro_day(self):
        return self.Time.date() in self.macro_blackout_dates

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
