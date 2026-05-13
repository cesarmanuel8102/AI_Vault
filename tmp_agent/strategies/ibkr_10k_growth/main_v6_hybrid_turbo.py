# region imports
from AlgorithmImports import *
from datetime import timedelta
# endregion


class IBKR10KHybridTurboV6(QCAlgorithm):
    """
    IBKR 10K Hybrid Turbo V6
    ------------------------
    - Core sleeve: diversified long-only momentum.
    - Turbo sleeve: leveraged long ETFs only in strong bull regime.
    - Risk-off: move mostly to defensive assets.
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

        self.benchmark_ticker = "SPY"
        self.vixy_ticker = "VIXY"

        self.core_assets = ["SPY", "QQQ", "IWM", "EFA", "EEM", "TLT", "IEF", "GLD", "DBC", "UUP"]
        self.safe_assets = ["SHY", "IEF", "GLD", "TLT"]
        self.turbo_assets = ["TQQQ", "SOXL", "UPRO", "TECL"]
        self.bear_assets = ["SH", "PSQ"]

        self.lookback_fast = int(self.GetParameter("lookback_fast") or 63)
        self.lookback_slow = int(self.GetParameter("lookback_slow") or 252)
        self.atr_period = int(self.GetParameter("atr_period") or 20)
        self.sma_filter_period = int(self.GetParameter("sma_filter_period") or 200)
        self.vixy_sma_period = int(self.GetParameter("vixy_sma_period") or 20)

        self.w_fast = float(self.GetParameter("w_fast") or 0.35)
        self.w_slow = float(self.GetParameter("w_slow") or 0.65)
        self.vol_penalty = float(self.GetParameter("vol_penalty") or 0.65)
        self.min_core_signal = float(self.GetParameter("min_core_signal") or 0.0)
        self.min_turbo_signal = float(self.GetParameter("min_turbo_signal") or 0.02)

        self.core_gross_risk_on = float(self.GetParameter("core_gross_risk_on") or 1.35)
        self.core_gross_risk_off = float(self.GetParameter("core_gross_risk_off") or 0.70)
        self.turbo_gross = float(self.GetParameter("turbo_gross") or 0.85)
        self.max_total_gross = float(self.GetParameter("max_total_gross") or 2.20)
        self.max_single_weight = float(self.GetParameter("max_single_weight") or 0.55)
        self.max_core_active = int(self.GetParameter("max_core_active") or 5)
        self.max_turbo_active = int(self.GetParameter("max_turbo_active") or 1)

        self.vixy_ratio_riskoff = float(self.GetParameter("vixy_ratio_riskoff") or 1.07)
        self.vixy_ratio_bull = float(self.GetParameter("vixy_ratio_bull") or 1.02)
        self.bull_sma_buffer = float(self.GetParameter("bull_sma_buffer") or 1.01)
        self.bull_mom_threshold = float(self.GetParameter("bull_mom_threshold") or 4.0)
        self.rebalance_buffer = float(self.GetParameter("rebalance_buffer") or 0.03)

        self.bear_hedge_enabled = (self.GetParameter("bear_hedge_enabled") or "0").strip().lower() not in (
            "0",
            "false",
            "no",
        )
        self.bear_hedge_weight = float(self.GetParameter("bear_hedge_weight") or 0.35)
        self.bear_trigger_mom = float(self.GetParameter("bear_trigger_mom") or -2.0)
        self.bear_sma_mult = float(self.GetParameter("bear_sma_mult") or 0.985)

        self.circuit_dd_pct = float(self.GetParameter("circuit_dd_pct") or 0.30)
        self.cooldown_days = int(self.GetParameter("cooldown_days") or 20)
        self.rebalance_daily = (self.GetParameter("rebalance_daily") or "0").strip().lower() not in (
            "0",
            "false",
            "no",
        )

        self.symbols = {}
        self.ind = {}
        all_tickers = list(
            dict.fromkeys(
                [self.benchmark_ticker, self.vixy_ticker]
                + self.core_assets
                + self.safe_assets
                + self.turbo_assets
                + self.bear_assets
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

        if self.rebalance_daily:
            self.Schedule.On(
                self.DateRules.EveryDay(self.benchmark_ticker),
                self.TimeRules.AfterMarketOpen(self.benchmark_ticker, 35),
                self.Rebalance,
            )
        else:
            self.Schedule.On(
                self.DateRules.Every(DayOfWeek.Monday),
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
                self.Liquidate(tag="V6_CIRCUIT_BREAK")
                self.cooldown_until = self.Time + timedelta(days=self.cooldown_days)
                self.current_targets = {}

    def _ready(self, ticker):
        i = self.ind[ticker]
        return i["roc_fast"].IsReady and i["roc_slow"].IsReady and i["atr"].IsReady and i["sma"].IsReady

    def _score(self, ticker):
        sym = self.symbols[ticker]
        px = self.Securities[sym].Price
        if px is None or px <= 0:
            return None
        roc_fast = float(self.ind[ticker]["roc_fast"].Current.Value)
        roc_slow = float(self.ind[ticker]["roc_slow"].Current.Value)
        atr = float(self.ind[ticker]["atr"].Current.Value)
        atr_pct = atr / px if px > 0 else 0.0
        return self.w_fast * roc_fast + self.w_slow * roc_slow - self.vol_penalty * atr_pct

    def _normalize_and_cap(self, target):
        gross = sum(abs(v) for v in target.values())
        if gross > self.max_total_gross and gross > 0:
            k = self.max_total_gross / gross
            for t in list(target.keys()):
                target[t] *= k
        for t in list(target.keys()):
            target[t] = max(-self.max_single_weight, min(self.max_single_weight, target[t]))
        return target

    def Rebalance(self):
        if self.IsWarmingUp:
            return
        if self.cooldown_until is not None and self.Time < self.cooldown_until:
            return
        if self.cooldown_until is not None and self.Time >= self.cooldown_until:
            self.cooldown_until = None

        needed = list(
            dict.fromkeys(
                [self.benchmark_ticker, self.vixy_ticker]
                + self.core_assets
                + self.safe_assets
                + self.turbo_assets
                + self.bear_assets
            )
        )
        for t in needed:
            if not self._ready(t):
                return
        if not self.vixy_sma.IsReady:
            return

        b_px = self.Securities[self.symbols[self.benchmark_ticker]].Price
        b_sma = float(self.ind[self.benchmark_ticker]["sma"].Current.Value)
        b_mom = float(self.ind[self.benchmark_ticker]["roc_fast"].Current.Value)

        vixy_px = self.Securities[self.symbols[self.vixy_ticker]].Price
        vixy_sma = float(self.vixy_sma.Current.Value) if self.vixy_sma.Current.Value else 0.0
        vixy_ratio = (vixy_px / vixy_sma) if (vixy_px and vixy_sma > 0) else 1.0

        risk_off = bool(vixy_ratio >= self.vixy_ratio_riskoff or b_px < b_sma)
        strong_bull = bool(
            (not risk_off)
            and b_px > b_sma * self.bull_sma_buffer
            and b_mom >= self.bull_mom_threshold
            and vixy_ratio <= self.vixy_ratio_bull
        )

        target = {}

        if risk_off:
            safe_scores = {}
            for t in self.safe_assets:
                s = self._score(t)
                if s is None:
                    return
                safe_scores[t] = s
            best = max(self.safe_assets, key=lambda x: safe_scores[x])
            safe_weight = 1.0

            bear_now = bool(b_mom <= self.bear_trigger_mom or b_px < b_sma * self.bear_sma_mult)
            if self.bear_hedge_enabled and bear_now:
                bear_scores = {}
                for t in self.bear_assets:
                    s = self._score(t)
                    if s is None:
                        return
                    bear_scores[t] = s
                best_bear = max(self.bear_assets, key=lambda x: bear_scores[x])
                hedge_w = max(0.0, min(0.8, self.bear_hedge_weight))
                target[best_bear] = hedge_w
                safe_weight = max(0.2, 1.0 - hedge_w)

            target[best] = target.get(best, 0.0) + safe_weight
        else:
            core_scores = {}
            for t in self.core_assets:
                s = self._score(t)
                if s is None:
                    return
                core_scores[t] = s

            ranked = sorted(self.core_assets, key=lambda x: core_scores[x], reverse=True)
            selected_core = [t for t in ranked if core_scores[t] >= self.min_core_signal][: self.max_core_active]
            if len(selected_core) == 0:
                selected_core = [ranked[0]]

            core_weight = self.core_gross_risk_on / len(selected_core)
            for t in selected_core:
                target[t] = core_weight

            if strong_bull:
                turbo_scores = {}
                for t in self.turbo_assets:
                    s = self._score(t)
                    if s is None:
                        return
                    turbo_scores[t] = s
                turbo_rank = sorted(self.turbo_assets, key=lambda x: turbo_scores[x], reverse=True)
                selected_turbo = [t for t in turbo_rank if turbo_scores[t] >= self.min_turbo_signal][: self.max_turbo_active]
                if len(selected_turbo) > 0:
                    turbo_weight = self.turbo_gross / len(selected_turbo)
                    for t in selected_turbo:
                        target[t] = target.get(t, 0.0) + turbo_weight

        target = self._normalize_and_cap(target)

        all_assets = list(dict.fromkeys(self.core_assets + self.safe_assets + self.turbo_assets + self.bear_assets))
        eq = self.Portfolio.TotalPortfolioValue
        for t in all_assets:
            sym = self.symbols[t]
            desired = float(target.get(t, 0.0))
            current = self.Portfolio[sym].HoldingsValue / eq if eq > 0 else 0.0
            if abs(desired - current) > self.rebalance_buffer:
                self.SetHoldings(sym, desired, tag=f"V6_REB {t}")

        self.current_targets = target

    def OnEndOfAlgorithm(self):
        eq = self.Portfolio.TotalPortfolioValue
        ret = (eq - self.initial_cash) / self.initial_cash if self.initial_cash else 0.0
        dd = (self.peak_equity - eq) / self.peak_equity if self.peak_equity > 0 else 0.0
        self.Log(f"FINAL v6 equity={eq:.2f} return_pct={ret*100:.2f} dd_pct={dd*100:.2f}")
