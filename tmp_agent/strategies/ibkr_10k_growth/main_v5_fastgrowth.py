# region imports
from AlgorithmImports import *
from datetime import timedelta
# endregion


class IBKR10KFastGrowthV5(QCAlgorithm):
    """
    IBKR 10K Fast Growth V5
    -----------------------
    Tactical long/short rotation on leveraged ETFs with crash filter.
    Designed to push monthly returns higher than core TSMOM while keeping
    a basic risk circuit.
    """

    def Initialize(self):
        self.SetStartDate(
            int(self.GetParameter("start_year") or 2018),
            int(self.GetParameter("start_month") or 1),
            int(self.GetParameter("start_day") or 1),
        )
        self.SetEndDate(
            int(self.GetParameter("end_year") or 2026),
            int(self.GetParameter("end_month") or 3),
            int(self.GetParameter("end_day") or 31),
        )
        self.SetTimeZone(TimeZones.NewYork)

        self.initial_cash = float(self.GetParameter("initial_cash") or 10000)
        self.SetCash(self.initial_cash)
        self.SetBrokerageModel(BrokerageName.InteractiveBrokersBrokerage, AccountType.Margin)

        # Universe
        self.long_assets = ["TQQQ", "SOXL", "TECL", "UPRO"]
        self.short_assets = ["SQQQ", "SOXS", "TECS", "SPXU"]
        self.safe_assets = ["SHY", "IEF", "GLD"]
        self.benchmark_ticker = "SPY"
        self.vixy_ticker = "VIXY"

        # Signals
        self.lookback_fast = int(self.GetParameter("lookback_fast") or 21)
        self.lookback_slow = int(self.GetParameter("lookback_slow") or 63)
        self.sma_filter_period = int(self.GetParameter("sma_filter_period") or 200)
        self.atr_period = int(self.GetParameter("atr_period") or 14)
        self.vixy_sma_period = int(self.GetParameter("vixy_sma_period") or 20)
        self.w_fast = float(self.GetParameter("w_fast") or 0.65)
        self.w_slow = float(self.GetParameter("w_slow") or 0.35)
        self.vol_penalty = float(self.GetParameter("vol_penalty") or 0.15)
        self.min_signal = float(self.GetParameter("min_signal") or 0.01)

        # Exposure
        self.gross_long = float(self.GetParameter("gross_long") or 2.4)
        self.gross_short = float(self.GetParameter("gross_short") or 1.8)
        self.max_active_long = int(self.GetParameter("max_active_long") or 1)
        self.max_active_short = int(self.GetParameter("max_active_short") or 1)
        self.max_single_weight = float(self.GetParameter("max_single_weight") or 1.55)
        self.max_total_gross = float(self.GetParameter("max_total_gross") or 2.8)
        self.rebalance_buffer = float(self.GetParameter("rebalance_buffer") or 0.04)
        self.vol_target_atr_pct = float(self.GetParameter("vol_target_atr_pct") or 0.045)

        # Regime / risk
        self.vixy_ratio_riskoff = float(self.GetParameter("vixy_ratio_riskoff") or 1.08)
        self.vixy_ratio_crash = float(self.GetParameter("vixy_ratio_crash") or 1.18)
        self.benchmark_sma_crash_mult = float(self.GetParameter("benchmark_sma_crash_mult") or 0.95)
        self.short_mode_enabled = (self.GetParameter("short_mode_enabled") or "1").strip().lower() not in (
            "0",
            "false",
            "no",
        )
        self.circuit_dd_pct = float(self.GetParameter("circuit_dd_pct") or 0.48)
        self.cooldown_days = int(self.GetParameter("cooldown_days") or 20)

        # Frequency
        self.rebalance_weekly = (self.GetParameter("rebalance_weekly") or "0").strip().lower() not in (
            "0",
            "false",
            "no",
        )

        self.symbols = {}
        self.ind = {}

        all_tickers = list(
            dict.fromkeys(
                [self.benchmark_ticker, self.vixy_ticker] + self.long_assets + self.short_assets + self.safe_assets
            )
        )
        for t in all_tickers:
            eq = self.AddEquity(t, Resolution.Daily)
            eq.SetDataNormalizationMode(DataNormalizationMode.Adjusted)
            sym = eq.Symbol
            self.symbols[t] = sym
            self.ind[t] = {
                "roc_fast": self.ROC(sym, self.lookback_fast, Resolution.Daily),
                "roc_slow": self.ROC(sym, self.lookback_slow, Resolution.Daily),
                "atr": self.ATR(sym, self.atr_period, MovingAverageType.Simple, Resolution.Daily),
                "sma": self.SMA(sym, self.sma_filter_period, Resolution.Daily),
            }

        self.vixy_sma = self.SMA(self.symbols[self.vixy_ticker], self.vixy_sma_period, Resolution.Daily)
        self.SetWarmUp(max(self.lookback_slow, self.sma_filter_period, self.vixy_sma_period) + 10, Resolution.Daily)

        self.peak_equity = self.initial_cash
        self.cooldown_until = None
        self.current_targets = {}

        if self.rebalance_weekly:
            self.Schedule.On(
                self.DateRules.Every(DayOfWeek.Monday),
                self.TimeRules.AfterMarketOpen(self.benchmark_ticker, 35),
                self.Rebalance,
            )
        else:
            self.Schedule.On(
                self.DateRules.EveryDay(self.benchmark_ticker),
                self.TimeRules.AfterMarketOpen(self.benchmark_ticker, 35),
                self.Rebalance,
            )

    def OnData(self, data: Slice):
        if self.IsWarmingUp:
            return
        eq = self.Portfolio.TotalPortfolioValue
        if eq > self.peak_equity:
            self.peak_equity = eq
        dd = (self.peak_equity - eq) / self.peak_equity if self.peak_equity > 0 else 0.0
        if dd >= self.circuit_dd_pct:
            if self.cooldown_until is None or self.Time > self.cooldown_until:
                self.Liquidate(tag="V5_CIRCUIT_BREAK")
                self.cooldown_until = self.Time + timedelta(days=self.cooldown_days)
                self.current_targets = {}

    def _ready(self, ticker):
        i = self.ind[ticker]
        return i["roc_fast"].IsReady and i["roc_slow"].IsReady and i["atr"].IsReady and i["sma"].IsReady

    def _signal(self, ticker):
        sym = self.symbols[ticker]
        px = self.Securities[sym].Price
        if px is None or px <= 0:
            return None
        roc_fast = float(self.ind[ticker]["roc_fast"].Current.Value)
        roc_slow = float(self.ind[ticker]["roc_slow"].Current.Value)
        atr = float(self.ind[ticker]["atr"].Current.Value)
        atr_pct = atr / px if px > 0 else 0.0
        return self.w_fast * roc_fast + self.w_slow * roc_slow - self.vol_penalty * atr_pct

    def _gross_scale(self):
        b_sym = self.symbols[self.benchmark_ticker]
        b_px = self.Securities[b_sym].Price
        if b_px is None or b_px <= 0:
            return 1.0
        atr = float(self.ind[self.benchmark_ticker]["atr"].Current.Value)
        atr_pct = atr / b_px if b_px > 0 else 0.0
        if atr_pct <= 0:
            return 1.0
        return min(1.25, max(0.35, self.vol_target_atr_pct / atr_pct))

    def Rebalance(self):
        if self.IsWarmingUp:
            return
        if self.cooldown_until is not None and self.Time < self.cooldown_until:
            return
        if self.cooldown_until is not None and self.Time >= self.cooldown_until:
            self.cooldown_until = None

        needed = list(
            dict.fromkeys(
                [self.benchmark_ticker, self.vixy_ticker] + self.long_assets + self.short_assets + self.safe_assets
            )
        )
        for t in needed:
            if not self._ready(t):
                return
        if not self.vixy_sma.IsReady:
            return

        b_sym = self.symbols[self.benchmark_ticker]
        b_px = self.Securities[b_sym].Price
        b_sma = float(self.ind[self.benchmark_ticker]["sma"].Current.Value)
        b_mom = float(self.ind[self.benchmark_ticker]["roc_slow"].Current.Value)

        vixy_px = self.Securities[self.symbols[self.vixy_ticker]].Price
        vixy_sma = float(self.vixy_sma.Current.Value) if self.vixy_sma.Current.Value else 0.0
        vixy_ratio = (vixy_px / vixy_sma) if (vixy_px and vixy_sma > 0) else 1.0

        risk_off = bool(vixy_ratio >= self.vixy_ratio_riskoff or b_px < b_sma or b_mom < 0.0)
        crash = bool(vixy_ratio >= self.vixy_ratio_crash or b_px < b_sma * self.benchmark_sma_crash_mult)

        scale = self._gross_scale()
        target = {}

        if crash and self.short_mode_enabled:
            scores = {}
            for t in self.short_assets:
                s = self._signal(t)
                if s is None:
                    return
                scores[t] = s
            ranked = sorted(self.short_assets, key=lambda t: scores[t], reverse=True)
            selected = [t for t in ranked if scores[t] >= self.min_signal][: self.max_active_short]
            if len(selected) > 0:
                w = min(self.max_single_weight, (self.gross_short * scale) / len(selected))
                for t in selected:
                    target[t] = w
        elif not risk_off:
            scores = {}
            for t in self.long_assets:
                s = self._signal(t)
                if s is None:
                    return
                scores[t] = s
            ranked = sorted(self.long_assets, key=lambda t: scores[t], reverse=True)
            selected = [t for t in ranked if scores[t] >= self.min_signal][: self.max_active_long]
            if len(selected) == 0:
                selected = [ranked[0]]
            w = min(self.max_single_weight, (self.gross_long * scale) / len(selected))
            for t in selected:
                target[t] = w
        else:
            safe_scores = {}
            for t in self.safe_assets:
                s = self._signal(t)
                if s is None:
                    return
                safe_scores[t] = s
            best = max(self.safe_assets, key=lambda t: safe_scores[t])
            target[best] = 1.0

        gross = sum(abs(v) for v in target.values())
        if gross > self.max_total_gross and gross > 0:
            k = self.max_total_gross / gross
            for t in list(target.keys()):
                target[t] *= k

        all_assets = list(dict.fromkeys(self.long_assets + self.short_assets + self.safe_assets))
        eq = self.Portfolio.TotalPortfolioValue
        for t in all_assets:
            sym = self.symbols[t]
            desired = float(target.get(t, 0.0))
            current = self.Portfolio[sym].HoldingsValue / eq if eq > 0 else 0.0
            if abs(desired - current) > self.rebalance_buffer:
                self.SetHoldings(sym, desired, tag=f"V5_REB {t}")

        self.current_targets = target

    def OnEndOfAlgorithm(self):
        eq = self.Portfolio.TotalPortfolioValue
        ret = (eq - self.initial_cash) / self.initial_cash if self.initial_cash else 0.0
        dd = (self.peak_equity - eq) / self.peak_equity if self.peak_equity > 0 else 0.0
        self.Log(f"FINAL v5 equity={eq:.2f} return_pct={ret*100:.2f} dd_pct={dd*100:.2f}")

