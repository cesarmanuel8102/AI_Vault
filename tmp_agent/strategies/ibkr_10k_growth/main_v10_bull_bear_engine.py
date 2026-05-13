# region imports
from AlgorithmImports import *
from datetime import timedelta
# endregion


class IBKR10KBullBearEngineV10(QCAlgorithm):
    """
    IBKR 10K Bull/Bear Engine V10
    -----------------------------
    Goal:
    - Keep high upside in bull periods.
    - Switch to inverse ETFs in bear periods (not only hedge).
    - Maintain explicit stress behavior.
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

        self.core_long_assets = ["SPY", "QQQ", "IWM", "EFA", "EEM", "TLT", "IEF", "GLD", "DBC", "UUP"]
        self.turbo_long_assets = ["TQQQ", "SOXL", "UPRO", "TECL"]
        self.bear_assets = ["SQQQ", "SOXS", "SPXU", "PSQ", "SH"]
        self.safe_assets = ["SHY", "IEF", "TLT", "GLD"]

        self.lookback_fast = int(self.GetParameter("lookback_fast") or 21)
        self.lookback_slow = int(self.GetParameter("lookback_slow") or 126)
        self.sma_filter_period = int(self.GetParameter("sma_filter_period") or 200)
        self.atr_period = int(self.GetParameter("atr_period") or 20)
        self.vixy_sma_period = int(self.GetParameter("vixy_sma_period") or 20)

        self.w_fast = float(self.GetParameter("w_fast") or 0.65)
        self.w_slow = float(self.GetParameter("w_slow") or 0.35)
        self.vol_penalty = float(self.GetParameter("vol_penalty") or 0.60)
        self.turbo_vol_penalty = float(self.GetParameter("turbo_vol_penalty") or self.vol_penalty)
        self.bear_vol_penalty = float(self.GetParameter("bear_vol_penalty") or 0.10)
        self.min_long_signal = float(self.GetParameter("min_long_signal") or 0.0)
        self.min_bear_signal = float(self.GetParameter("min_bear_signal") or 0.0)

        self.bull_core_gross = float(self.GetParameter("bull_core_gross") or 2.0)
        self.bull_turbo_gross = float(self.GetParameter("bull_turbo_gross") or 2.2)
        self.neutral_core_gross = float(self.GetParameter("neutral_core_gross") or 1.0)
        self.bear_gross = float(self.GetParameter("bear_gross") or 3.0)
        self.stress_bear_gross = float(self.GetParameter("stress_bear_gross") or 2.0)
        self.stress_safe_gross = float(self.GetParameter("stress_safe_gross") or 0.6)

        self.max_total_gross = float(self.GetParameter("max_total_gross") or 6.0)
        self.max_single_weight = float(self.GetParameter("max_single_weight") or 2.0)
        self.max_core_active = int(self.GetParameter("max_core_active") or 2)
        self.max_turbo_active = int(self.GetParameter("max_turbo_active") or 1)
        self.max_bear_active = int(self.GetParameter("max_bear_active") or 2)

        self.bull_sma_mult = float(self.GetParameter("bull_sma_mult") or 1.0)
        self.bull_mom_min = float(self.GetParameter("bull_mom_min") or -1.0)
        self.bull_vixy_max = float(self.GetParameter("bull_vixy_max") or 1.20)

        self.bear_sma_mult = float(self.GetParameter("bear_sma_mult") or 1.0)
        self.bear_mom_max = float(self.GetParameter("bear_mom_max") or -1.0)
        self.bear_vixy_min = float(self.GetParameter("bear_vixy_min") or 1.05)

        self.stress_vixy = float(self.GetParameter("stress_vixy") or 1.22)
        self.stress_atr_pct = float(self.GetParameter("stress_atr_pct") or 0.03)
        self.use_fixed_bear = (self.GetParameter("use_fixed_bear") or "0").strip().lower() not in (
            "0",
            "false",
            "no",
        )
        self.bear_primary = (self.GetParameter("bear_primary") or "SQQQ").strip().upper()
        self.bear_secondary = (self.GetParameter("bear_secondary") or "SPXU").strip().upper()
        self.bear_primary_split = float(self.GetParameter("bear_primary_split") or 0.70)
        self.stress_secondary_split = float(self.GetParameter("stress_secondary_split") or 0.25)

        self.state_hold_days = int(self.GetParameter("state_hold_days") or 2)
        self.rebalance_daily = (self.GetParameter("rebalance_daily") or "1").strip().lower() not in (
            "0",
            "false",
            "no",
        )
        self.rebalance_buffer = float(self.GetParameter("rebalance_buffer") or 0.015)

        self.circuit_dd_pct = float(self.GetParameter("circuit_dd_pct") or 0.85)
        self.cooldown_days = int(self.GetParameter("cooldown_days") or 20)

        self.symbols = {}
        self.ind = {}
        all_tickers = list(
            dict.fromkeys(
                [self.benchmark_ticker, self.vixy_ticker]
                + self.core_long_assets
                + self.turbo_long_assets
                + self.bear_assets
                + self.safe_assets
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

        if self.bear_primary not in self.bear_assets:
            self.bear_primary = self.bear_assets[0]
        if self.bear_secondary not in self.bear_assets:
            self.bear_secondary = self.bear_assets[1] if len(self.bear_assets) > 1 else self.bear_assets[0]

        self.peak_equity = self.initial_cash
        self.cooldown_until = None
        self.state = "NEUTRAL"
        self.state_age = 0

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
                self.Liquidate(tag="V10_CIRCUIT_BREAK")
                self.cooldown_until = self.Time + timedelta(days=self.cooldown_days)
                self.state = "COOLDOWN"
                self.state_age = 0
        self.SetRuntimeStatistic("State", self.state)

    def _ready(self, ticker):
        i = self.ind[ticker]
        return i["roc_fast"].IsReady and i["roc_slow"].IsReady and i["atr"].IsReady and i["sma"].IsReady

    def _score(self, ticker):
        return self._score_penalized(ticker, self.vol_penalty)

    def _score_penalized(self, ticker, penalty):
        sym = self.symbols[ticker]
        px = self.Securities[sym].Price
        if px is None or px <= 0:
            return None
        roc_f = float(self.ind[ticker]["roc_fast"].Current.Value)
        roc_s = float(self.ind[ticker]["roc_slow"].Current.Value)
        atr = float(self.ind[ticker]["atr"].Current.Value)
        atr_pct = atr / px if px > 0 else 0.0
        return self.w_fast * roc_f + self.w_slow * roc_s - penalty * atr_pct

    def _normalize_and_cap(self, target):
        gross = sum(abs(v) for v in target.values())
        if gross > self.max_total_gross and gross > 0:
            k = self.max_total_gross / gross
            for t in list(target.keys()):
                target[t] *= k
        for t in list(target.keys()):
            target[t] = max(-self.max_single_weight, min(self.max_single_weight, target[t]))
        return target

    def _candidate_state(self):
        b = self.benchmark_ticker
        b_sym = self.symbols[b]
        b_px = self.Securities[b_sym].Price
        b_sma = float(self.ind[b]["sma"].Current.Value)
        b_mom = float(self.ind[b]["roc_fast"].Current.Value)
        b_atr = float(self.ind[b]["atr"].Current.Value)
        b_atr_pct = b_atr / b_px if b_px and b_px > 0 else 0.0

        vixy_px = self.Securities[self.symbols[self.vixy_ticker]].Price
        vixy_sma = float(self.vixy_sma.Current.Value) if self.vixy_sma.Current.Value else 0.0
        vixy_ratio = (vixy_px / vixy_sma) if (vixy_px and vixy_sma > 0) else 1.0

        if vixy_ratio >= self.stress_vixy or b_atr_pct >= self.stress_atr_pct:
            return "STRESS"
        if b_px < b_sma * self.bear_sma_mult and b_mom <= self.bear_mom_max and vixy_ratio >= self.bear_vixy_min:
            return "BEAR"
        if b_px > b_sma * self.bull_sma_mult and b_mom >= self.bull_mom_min and vixy_ratio <= self.bull_vixy_max:
            return "BULL"
        return "NEUTRAL"

    def _maybe_switch_state(self, cand_state):
        if cand_state == self.state:
            self.state_age += 1
            return
        if self.state_age < self.state_hold_days and self.state != "COOLDOWN":
            self.state_age += 1
            return
        self.state = cand_state
        self.state_age = 0

    def Rebalance(self):
        if self.IsWarmingUp:
            return
        if self.cooldown_until is not None and self.Time < self.cooldown_until:
            return
        if self.cooldown_until is not None and self.Time >= self.cooldown_until:
            self.cooldown_until = None
            self.state = "NEUTRAL"
            self.state_age = 0

        needed = list(
            dict.fromkeys(
                [self.benchmark_ticker, self.vixy_ticker]
                + self.core_long_assets
                + self.turbo_long_assets
                + self.bear_assets
                + self.safe_assets
            )
        )
        for t in needed:
            if not self._ready(t):
                return
        if not self.vixy_sma.IsReady:
            return

        self._maybe_switch_state(self._candidate_state())

        target = {}

        core_scores = {}
        for t in self.core_long_assets:
            s = self._score(t)
            if s is None:
                return
            core_scores[t] = s
        core_rank = sorted(self.core_long_assets, key=lambda x: core_scores[x], reverse=True)
        sel_core = [t for t in core_rank if core_scores[t] >= self.min_long_signal][: self.max_core_active]
        if len(sel_core) == 0:
            sel_core = [core_rank[0]]

        if self.state == "BULL":
            cw = self.bull_core_gross / len(sel_core)
            for t in sel_core:
                target[t] = cw

            turbo_scores = {}
            for t in self.turbo_long_assets:
                s = self._score_penalized(t, self.turbo_vol_penalty)
                if s is None:
                    return
                turbo_scores[t] = s
            turbo_rank = sorted(self.turbo_long_assets, key=lambda x: turbo_scores[x], reverse=True)
            sel_turbo = [t for t in turbo_rank if turbo_scores[t] >= self.min_long_signal][: self.max_turbo_active]
            if len(sel_turbo) > 0:
                tw = self.bull_turbo_gross / len(sel_turbo)
                for t in sel_turbo:
                    target[t] = target.get(t, 0.0) + tw

        elif self.state == "BEAR":
            if self.use_fixed_bear:
                split = max(0.0, min(1.0, self.bear_primary_split))
                p = self.bear_primary
                s = self.bear_secondary
                target[p] = self.bear_gross * split
                rest = self.bear_gross * (1.0 - split)
                if rest > 0:
                    if s == p:
                        target[p] += rest
                    else:
                        target[s] = rest
            else:
                bear_scores = {}
                for t in self.bear_assets:
                    s = self._score_penalized(t, self.bear_vol_penalty)
                    if s is None:
                        return
                    bear_scores[t] = s
                bear_rank = sorted(self.bear_assets, key=lambda x: bear_scores[x], reverse=True)
                sel_bear = [t for t in bear_rank if bear_scores[t] >= self.min_bear_signal][: self.max_bear_active]
                if len(sel_bear) == 0:
                    sel_bear = [bear_rank[0]]
                bw = self.bear_gross / len(sel_bear)
                for t in sel_bear:
                    target[t] = bw

        elif self.state == "STRESS":
            if self.use_fixed_bear:
                p = self.bear_primary
                s = self.bear_secondary
                split2 = max(0.0, min(1.0, 1.0 - self.stress_secondary_split))
                target[p] = self.stress_bear_gross * split2
                rest2 = self.stress_bear_gross * (1.0 - split2)
                if rest2 > 0:
                    if s == p:
                        target[p] += rest2
                    else:
                        target[s] = rest2
            else:
                bear_scores = {}
                for t in self.bear_assets:
                    s = self._score_penalized(t, self.bear_vol_penalty)
                    if s is None:
                        return
                    bear_scores[t] = s
                best_bear = max(self.bear_assets, key=lambda x: bear_scores[x])
                target[best_bear] = self.stress_bear_gross

            safe_scores = {}
            for t in self.safe_assets:
                s = self._score(t)
                if s is None:
                    return
                safe_scores[t] = s
            best_safe = max(self.safe_assets, key=lambda x: safe_scores[x])
            target[best_safe] = target.get(best_safe, 0.0) + self.stress_safe_gross

        else:
            nw = self.neutral_core_gross / len(sel_core)
            for t in sel_core:
                target[t] = nw

        target = self._normalize_and_cap(target)

        all_assets = list(
            dict.fromkeys(self.core_long_assets + self.turbo_long_assets + self.bear_assets + self.safe_assets)
        )
        eq = self.Portfolio.TotalPortfolioValue
        for t in all_assets:
            sym = self.symbols[t]
            desired = float(target.get(t, 0.0))
            current = self.Portfolio[sym].HoldingsValue / eq if eq > 0 else 0.0
            if abs(desired - current) > self.rebalance_buffer:
                self.SetHoldings(sym, desired, tag=f"V10_REB {self.state} {t}")

    def OnEndOfAlgorithm(self):
        eq = self.Portfolio.TotalPortfolioValue
        ret = (eq - self.initial_cash) / self.initial_cash if self.initial_cash else 0.0
        dd = (self.peak_equity - eq) / self.peak_equity if self.peak_equity > 0 else 0.0
        self.Log(f"FINAL v10 equity={eq:.2f} return_pct={ret*100:.2f} dd_pct={dd*100:.2f} state={self.state}")
