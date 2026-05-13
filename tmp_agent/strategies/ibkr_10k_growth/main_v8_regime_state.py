# region imports
from AlgorithmImports import *
from datetime import timedelta
# endregion


class IBKR10KRegimeStateV8(QCAlgorithm):
    """
    IBKR 10K Regime State V8
    ------------------------
    Regime state machine with persistence:
    - BULL: core + turbo
    - NEUTRAL: core only
    - BEAR: inverse hedge + reduced core
    - STRESS: defensive + inverse
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
        self.turbo_assets = ["TQQQ", "SOXL", "UPRO", "TECL"]
        self.bear_assets = ["SH", "PSQ"]
        self.safe_assets = ["SHY", "IEF", "TLT", "GLD"]

        self.lookback_fast = int(self.GetParameter("lookback_fast") or 21)
        self.lookback_mid = int(self.GetParameter("lookback_mid") or 63)
        self.lookback_slow = int(self.GetParameter("lookback_slow") or 252)
        self.atr_period = int(self.GetParameter("atr_period") or 20)
        self.sma_period = int(self.GetParameter("sma_period") or 200)
        self.vixy_sma_period = int(self.GetParameter("vixy_sma_period") or 20)

        self.w_fast = float(self.GetParameter("w_fast") or 0.55)
        self.w_mid = float(self.GetParameter("w_mid") or 0.30)
        self.w_slow = float(self.GetParameter("w_slow") or 0.15)
        self.vol_penalty = float(self.GetParameter("vol_penalty") or 0.60)
        self.min_core_signal = float(self.GetParameter("min_core_signal") or 0.0)
        self.min_turbo_signal = float(self.GetParameter("min_turbo_signal") or 0.01)

        self.core_gross_bull = float(self.GetParameter("core_gross_bull") or 1.55)
        self.core_gross_neutral = float(self.GetParameter("core_gross_neutral") or 1.05)
        self.core_gross_bear = float(self.GetParameter("core_gross_bear") or 0.35)
        self.turbo_gross_bull = float(self.GetParameter("turbo_gross_bull") or 1.05)
        self.bear_gross_bear = float(self.GetParameter("bear_gross_bear") or 0.65)
        self.bear_gross_stress = float(self.GetParameter("bear_gross_stress") or 0.85)
        self.safe_gross_stress = float(self.GetParameter("safe_gross_stress") or 0.60)

        self.max_total_gross = float(self.GetParameter("max_total_gross") or 2.7)
        self.max_single_weight = float(self.GetParameter("max_single_weight") or 0.9)
        self.max_core_active = int(self.GetParameter("max_core_active") or 4)
        self.max_turbo_active = int(self.GetParameter("max_turbo_active") or 2)
        self.rebalance_buffer = float(self.GetParameter("rebalance_buffer") or 0.02)

        self.bull_sma_mult = float(self.GetParameter("bull_sma_mult") or 1.002)
        self.bull_mid_min = float(self.GetParameter("bull_mid_min") or 1.5)
        self.bull_slow_min = float(self.GetParameter("bull_slow_min") or 3.0)
        self.bull_vixy_max = float(self.GetParameter("bull_vixy_max") or 1.04)

        self.bear_sma_mult = float(self.GetParameter("bear_sma_mult") or 0.998)
        self.bear_mid_max = float(self.GetParameter("bear_mid_max") or -0.5)
        self.bear_slow_max = float(self.GetParameter("bear_slow_max") or 1.5)
        self.bear_vixy_min = float(self.GetParameter("bear_vixy_min") or 1.01)

        self.stress_vixy = float(self.GetParameter("stress_vixy") or 1.10)
        self.stress_atr_pct = float(self.GetParameter("stress_atr_pct") or 0.02)

        self.bull_persist_days = int(self.GetParameter("bull_persist_days") or 3)
        self.bear_persist_days = int(self.GetParameter("bear_persist_days") or 3)
        self.stress_persist_days = int(self.GetParameter("stress_persist_days") or 2)
        self.min_state_days = int(self.GetParameter("min_state_days") or 3)

        self.circuit_dd_pct = float(self.GetParameter("circuit_dd_pct") or 0.38)
        self.cooldown_days = int(self.GetParameter("cooldown_days") or 20)

        self.symbols = {}
        self.ind = {}
        all_tickers = list(
            dict.fromkeys(
                [self.benchmark_ticker, self.vixy_ticker]
                + self.core_assets
                + self.turbo_assets
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
                "roc_mid": self.ROC(sym, self.lookback_mid, Resolution.Daily),
                "roc_slow": self.ROC(sym, self.lookback_slow, Resolution.Daily),
                "atr": self.ATR(sym, self.atr_period, MovingAverageType.Simple, Resolution.Daily),
                "sma": self.SMA(sym, self.sma_period, Resolution.Daily),
            }

        self.vixy_sma = self.SMA(self.symbols[self.vixy_ticker], self.vixy_sma_period, Resolution.Daily)
        self.SetWarmUp(max(self.lookback_slow, self.sma_period, self.vixy_sma_period) + 10, Resolution.Daily)

        self.peak_equity = self.initial_cash
        self.cooldown_until = None

        self.state = "NEUTRAL"
        self.state_days = 0
        self.bull_count = 0
        self.bear_count = 0
        self.stress_count = 0

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
                self.Liquidate(tag="V8_CIRCUIT_BREAK")
                self.cooldown_until = self.Time + timedelta(days=self.cooldown_days)
                self.state = "COOLDOWN"
                self.state_days = 0
                self.bull_count = 0
                self.bear_count = 0
                self.stress_count = 0

        self.SetRuntimeStatistic("State", self.state)

    def _ready(self, ticker):
        i = self.ind[ticker]
        return (
            i["roc_fast"].IsReady
            and i["roc_mid"].IsReady
            and i["roc_slow"].IsReady
            and i["atr"].IsReady
            and i["sma"].IsReady
        )

    def _score(self, ticker):
        sym = self.symbols[ticker]
        px = self.Securities[sym].Price
        if px is None or px <= 0:
            return None
        r1 = float(self.ind[ticker]["roc_fast"].Current.Value)
        r2 = float(self.ind[ticker]["roc_mid"].Current.Value)
        r3 = float(self.ind[ticker]["roc_slow"].Current.Value)
        atr = float(self.ind[ticker]["atr"].Current.Value)
        atr_pct = atr / px if px > 0 else 0.0
        return self.w_fast * r1 + self.w_mid * r2 + self.w_slow * r3 - self.vol_penalty * atr_pct

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
        px = self.Securities[b_sym].Price
        sma = float(self.ind[b]["sma"].Current.Value)
        roc_mid = float(self.ind[b]["roc_mid"].Current.Value)
        roc_slow = float(self.ind[b]["roc_slow"].Current.Value)
        atr = float(self.ind[b]["atr"].Current.Value)
        atr_pct = atr / px if px and px > 0 else 0.0

        vixy_px = self.Securities[self.symbols[self.vixy_ticker]].Price
        vixy_sma = float(self.vixy_sma.Current.Value) if self.vixy_sma.Current.Value else 0.0
        vixy_ratio = (vixy_px / vixy_sma) if (vixy_px and vixy_sma > 0) else 1.0

        is_stress = bool(vixy_ratio >= self.stress_vixy or atr_pct >= self.stress_atr_pct)
        is_bull = bool(
            px > sma * self.bull_sma_mult
            and roc_mid >= self.bull_mid_min
            and roc_slow >= self.bull_slow_min
            and vixy_ratio <= self.bull_vixy_max
        )
        is_bear = bool(
            px < sma * self.bear_sma_mult
            and roc_mid <= self.bear_mid_max
            and roc_slow <= self.bear_slow_max
            and vixy_ratio >= self.bear_vixy_min
        )
        return is_stress, is_bull, is_bear

    def _update_state(self):
        is_stress, is_bull, is_bear = self._candidate_state()

        self.stress_count = self.stress_count + 1 if is_stress else 0
        self.bull_count = self.bull_count + 1 if is_bull else 0
        self.bear_count = self.bear_count + 1 if is_bear else 0
        self.state_days += 1

        next_state = self.state
        if self.stress_count >= self.stress_persist_days:
            next_state = "STRESS"
        elif self.bear_count >= self.bear_persist_days:
            next_state = "BEAR"
        elif self.bull_count >= self.bull_persist_days:
            next_state = "BULL"
        else:
            next_state = "NEUTRAL"

        if next_state != self.state and self.state_days < self.min_state_days:
            return
        if next_state != self.state:
            self.state = next_state
            self.state_days = 0

    def Rebalance(self):
        if self.IsWarmingUp:
            return
        if self.cooldown_until is not None and self.Time < self.cooldown_until:
            return
        if self.cooldown_until is not None and self.Time >= self.cooldown_until:
            self.cooldown_until = None
            self.state = "NEUTRAL"
            self.state_days = 0

        needed = list(
            dict.fromkeys(
                [self.benchmark_ticker, self.vixy_ticker]
                + self.core_assets
                + self.turbo_assets
                + self.bear_assets
                + self.safe_assets
            )
        )
        for t in needed:
            if not self._ready(t):
                return
        if not self.vixy_sma.IsReady:
            return

        self._update_state()

        target = {}

        core_scores = {}
        for t in self.core_assets:
            s = self._score(t)
            if s is None:
                return
            core_scores[t] = s
        core_rank = sorted(self.core_assets, key=lambda x: core_scores[x], reverse=True)
        sel_core = [t for t in core_rank if core_scores[t] >= self.min_core_signal][: self.max_core_active]
        if len(sel_core) == 0:
            sel_core = [core_rank[0]]

        if self.state == "BULL":
            core_w = self.core_gross_bull / len(sel_core)
            for t in sel_core:
                target[t] = core_w

            turbo_scores = {}
            for t in self.turbo_assets:
                s = self._score(t)
                if s is None:
                    return
                turbo_scores[t] = s
            turbo_rank = sorted(self.turbo_assets, key=lambda x: turbo_scores[x], reverse=True)
            sel_turbo = [t for t in turbo_rank if turbo_scores[t] >= self.min_turbo_signal][: self.max_turbo_active]
            if len(sel_turbo) > 0:
                turbo_w = self.turbo_gross_bull / len(sel_turbo)
                for t in sel_turbo:
                    target[t] = target.get(t, 0.0) + turbo_w

        elif self.state == "NEUTRAL":
            core_w = self.core_gross_neutral / len(sel_core)
            for t in sel_core:
                target[t] = core_w

        elif self.state == "BEAR":
            core_w = self.core_gross_bear / len(sel_core)
            for t in sel_core:
                target[t] = core_w

            bear_scores = {}
            for t in self.bear_assets:
                s = self._score(t)
                if s is None:
                    return
                bear_scores[t] = s
            best_bear = max(self.bear_assets, key=lambda x: bear_scores[x])
            target[best_bear] = target.get(best_bear, 0.0) + self.bear_gross_bear

        elif self.state == "STRESS":
            safe_scores = {}
            for t in self.safe_assets:
                s = self._score(t)
                if s is None:
                    return
                safe_scores[t] = s
            best_safe = max(self.safe_assets, key=lambda x: safe_scores[x])
            target[best_safe] = target.get(best_safe, 0.0) + self.safe_gross_stress

            bear_scores = {}
            for t in self.bear_assets:
                s = self._score(t)
                if s is None:
                    return
                bear_scores[t] = s
            best_bear = max(self.bear_assets, key=lambda x: bear_scores[x])
            target[best_bear] = target.get(best_bear, 0.0) + self.bear_gross_stress

        target = self._normalize_and_cap(target)

        all_assets = list(dict.fromkeys(self.core_assets + self.turbo_assets + self.bear_assets + self.safe_assets))
        eq = self.Portfolio.TotalPortfolioValue
        for t in all_assets:
            sym = self.symbols[t]
            desired = float(target.get(t, 0.0))
            current = self.Portfolio[sym].HoldingsValue / eq if eq > 0 else 0.0
            if abs(desired - current) > self.rebalance_buffer:
                self.SetHoldings(sym, desired, tag=f"V8_REB {self.state} {t}")

    def OnEndOfAlgorithm(self):
        eq = self.Portfolio.TotalPortfolioValue
        ret = (eq - self.initial_cash) / self.initial_cash if self.initial_cash else 0.0
        dd = (self.peak_equity - eq) / self.peak_equity if self.peak_equity > 0 else 0.0
        self.Log(f"FINAL v8 equity={eq:.2f} return_pct={ret*100:.2f} dd_pct={dd*100:.2f} state={self.state}")

