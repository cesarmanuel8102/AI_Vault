# region imports
from AlgorithmImports import *
from datetime import timedelta
# endregion


class IBKR10KRegimeConfidenceV7(QCAlgorithm):
    """
    IBKR 10K Regime Confidence V7
    -----------------------------
    Objective:
    - Increase participation using a confidence-based regime detector.
    - Keep capital protection via stress and drawdown circuit breaker.
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
        self.safe_assets = ["SHY", "IEF", "TLT", "GLD"]
        self.turbo_assets = ["TQQQ", "SOXL", "UPRO", "TECL"]
        self.bear_assets = ["SH", "PSQ"]

        self.lookback_fast = int(self.GetParameter("lookback_fast") or 63)
        self.lookback_slow = int(self.GetParameter("lookback_slow") or 252)
        self.atr_period = int(self.GetParameter("atr_period") or 20)
        self.sma_filter_period = int(self.GetParameter("sma_filter_period") or 200)
        self.vixy_sma_period = int(self.GetParameter("vixy_sma_period") or 20)

        self.w_fast = float(self.GetParameter("w_fast") or 0.4)
        self.w_slow = float(self.GetParameter("w_slow") or 0.6)
        self.vol_penalty = float(self.GetParameter("vol_penalty") or 0.65)
        self.min_core_signal = float(self.GetParameter("min_core_signal") or 0.0)
        self.min_turbo_signal = float(self.GetParameter("min_turbo_signal") or 0.015)

        self.core_gross_low = float(self.GetParameter("core_gross_low") or 0.9)
        self.core_gross_mid = float(self.GetParameter("core_gross_mid") or 1.35)
        self.core_gross_high = float(self.GetParameter("core_gross_high") or 1.75)
        self.turbo_gross_mid = float(self.GetParameter("turbo_gross_mid") or 0.45)
        self.turbo_gross_high = float(self.GetParameter("turbo_gross_high") or 1.20)
        self.bear_gross_mid = float(self.GetParameter("bear_gross_mid") or 0.35)
        self.bear_gross_high = float(self.GetParameter("bear_gross_high") or 0.75)

        self.max_total_gross = float(self.GetParameter("max_total_gross") or 2.85)
        self.max_single_weight = float(self.GetParameter("max_single_weight") or 0.85)
        self.max_core_active = int(self.GetParameter("max_core_active") or 4)
        self.max_turbo_active_mid = int(self.GetParameter("max_turbo_active_mid") or 1)
        self.max_turbo_active_high = int(self.GetParameter("max_turbo_active_high") or 2)

        self.rebalance_buffer = float(self.GetParameter("rebalance_buffer") or 0.02)

        # Regime confidence thresholds
        self.conf_bull_high = float(self.GetParameter("conf_bull_high") or 0.72)
        self.conf_bull_mid = float(self.GetParameter("conf_bull_mid") or 0.56)
        self.conf_bear_high = float(self.GetParameter("conf_bear_high") or 0.68)
        self.conf_bear_mid = float(self.GetParameter("conf_bear_mid") or 0.54)
        self.conf_stress = float(self.GetParameter("conf_stress") or 0.70)

        # Stress inputs
        self.vixy_ratio_stress = float(self.GetParameter("vixy_ratio_stress") or 1.12)
        self.vixy_ratio_riskoff = float(self.GetParameter("vixy_ratio_riskoff") or 1.05)

        self.circuit_dd_pct = float(self.GetParameter("circuit_dd_pct") or 0.42)
        self.cooldown_days = int(self.GetParameter("cooldown_days") or 20)

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
        self.current_regime = "NONE"
        self.current_conf = 0.0

        # Daily rebalance for higher participation
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
                self.Liquidate(tag="V7_CIRCUIT_BREAK")
                self.cooldown_until = self.Time + timedelta(days=self.cooldown_days)
                self.current_targets = {}
                self.current_regime = "COOLDOWN"
                self.current_conf = 0.0

        self.SetRuntimeStatistic("Regime", self.current_regime)
        self.SetRuntimeStatistic("RegimeConf", f"{self.current_conf:.2f}")

    def _ready(self, ticker):
        i = self.ind[ticker]
        return i["roc_fast"].IsReady and i["roc_slow"].IsReady and i["atr"].IsReady and i["sma"].IsReady

    @staticmethod
    def _clamp01(x):
        return max(0.0, min(1.0, x))

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

    def _compute_regime_confidence(self):
        # Core market features
        b_sym = self.symbols[self.benchmark_ticker]
        b_px = self.Securities[b_sym].Price
        b_sma = float(self.ind[self.benchmark_ticker]["sma"].Current.Value)
        b_roc_fast = float(self.ind[self.benchmark_ticker]["roc_fast"].Current.Value)
        b_roc_slow = float(self.ind[self.benchmark_ticker]["roc_slow"].Current.Value)
        b_atr = float(self.ind[self.benchmark_ticker]["atr"].Current.Value)
        b_atr_pct = b_atr / b_px if b_px and b_px > 0 else 0.0

        vixy_px = self.Securities[self.symbols[self.vixy_ticker]].Price
        vixy_sma = float(self.vixy_sma.Current.Value) if self.vixy_sma.Current.Value else 0.0
        vixy_ratio = (vixy_px / vixy_sma) if (vixy_px and vixy_sma > 0) else 1.0

        # Breadth across core assets
        up_count = 0
        down_count = 0
        breadth_pos_mom = 0
        valid = 0
        for t in self.core_assets:
            sym = self.symbols[t]
            px = self.Securities[sym].Price
            sma = float(self.ind[t]["sma"].Current.Value)
            roc_f = float(self.ind[t]["roc_fast"].Current.Value)
            if px and px > 0:
                valid += 1
                if px > sma:
                    up_count += 1
                else:
                    down_count += 1
                if roc_f > 0:
                    breadth_pos_mom += 1

        breadth_up = (up_count / valid) if valid > 0 else 0.5
        breadth_down = (down_count / valid) if valid > 0 else 0.5
        breadth_mom = (breadth_pos_mom / valid) if valid > 0 else 0.5

        # Feature normalization 0..1
        trend_up = self._clamp01(((b_px / b_sma) - 0.985) / 0.06) if b_sma > 0 else 0.5
        trend_dn = self._clamp01((1.015 - (b_px / b_sma)) / 0.06) if b_sma > 0 else 0.5

        mom_up = self._clamp01((b_roc_fast + 2.0) / 10.0) * 0.55 + self._clamp01((b_roc_slow + 3.0) / 16.0) * 0.45
        mom_dn = self._clamp01((2.0 - b_roc_fast) / 10.0) * 0.55 + self._clamp01((3.0 - b_roc_slow) / 16.0) * 0.45

        vol_calm = self._clamp01((0.025 - b_atr_pct) / 0.02)
        vol_stress = self._clamp01((b_atr_pct - 0.015) / 0.02)
        vix_stress = self._clamp01((vixy_ratio - 1.02) / 0.16)
        vix_calm = self._clamp01((1.10 - vixy_ratio) / 0.12)

        bull_conf = (
            0.30 * trend_up
            + 0.25 * mom_up
            + 0.20 * breadth_up
            + 0.15 * breadth_mom
            + 0.10 * vix_calm
        )
        bear_conf = (
            0.30 * trend_dn
            + 0.25 * mom_dn
            + 0.20 * breadth_down
            + 0.15 * (1.0 - breadth_mom)
            + 0.10 * vix_stress
        )
        stress_conf = 0.45 * vix_stress + 0.30 * vol_stress + 0.25 * breadth_down

        regime = "NEUTRAL"
        conf = 0.0
        if stress_conf >= self.conf_stress or vixy_ratio >= self.vixy_ratio_stress:
            regime = "STRESS"
            conf = float(stress_conf)
        elif bull_conf >= self.conf_bull_high and vixy_ratio <= self.vixy_ratio_riskoff:
            regime = "BULL_HIGH"
            conf = float(bull_conf)
        elif bull_conf >= self.conf_bull_mid and vixy_ratio <= self.vixy_ratio_riskoff:
            regime = "BULL_MID"
            conf = float(bull_conf)
        elif bear_conf >= self.conf_bear_high:
            regime = "BEAR_HIGH"
            conf = float(bear_conf)
        elif bear_conf >= self.conf_bear_mid:
            regime = "BEAR_MID"
            conf = float(bear_conf)
        else:
            conf = float(max(bull_conf, bear_conf))

        return regime, self._clamp01(conf)

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

        regime, conf = self._compute_regime_confidence()
        self.current_regime = regime
        self.current_conf = conf

        target = {}

        if regime in ("STRESS", "BEAR_HIGH", "BEAR_MID"):
            safe_scores = {}
            for t in self.safe_assets:
                s = self._score(t)
                if s is None:
                    return
                safe_scores[t] = s
            best_safe = max(self.safe_assets, key=lambda x: safe_scores[x])

            bear_scores = {}
            for t in self.bear_assets:
                s = self._score(t)
                if s is None:
                    return
                bear_scores[t] = s
            best_bear = max(self.bear_assets, key=lambda x: bear_scores[x])

            if regime == "STRESS":
                bear_w = self.bear_gross_high
                safe_w = max(0.25, 1.0 - bear_w)
            elif regime == "BEAR_HIGH":
                bear_w = self.bear_gross_mid
                safe_w = max(0.30, 1.0 - bear_w)
            else:
                bear_w = max(0.15, self.bear_gross_mid * 0.7)
                safe_w = max(0.35, 1.0 - bear_w)

            target[best_bear] = bear_w
            target[best_safe] = target.get(best_safe, 0.0) + safe_w

        else:
            core_scores = {}
            for t in self.core_assets:
                s = self._score(t)
                if s is None:
                    return
                core_scores[t] = s

            ranked_core = sorted(self.core_assets, key=lambda x: core_scores[x], reverse=True)
            selected_core = [t for t in ranked_core if core_scores[t] >= self.min_core_signal][: self.max_core_active]
            if len(selected_core) == 0:
                selected_core = [ranked_core[0]]

            if regime == "BULL_HIGH":
                core_gross = self.core_gross_high
                turbo_gross = self.turbo_gross_high
                max_turbo = self.max_turbo_active_high
            elif regime == "BULL_MID":
                core_gross = self.core_gross_mid
                turbo_gross = self.turbo_gross_mid
                max_turbo = self.max_turbo_active_mid
            else:
                core_gross = self.core_gross_low
                turbo_gross = 0.0
                max_turbo = 0

            core_w = core_gross / len(selected_core)
            for t in selected_core:
                target[t] = core_w

            if turbo_gross > 0 and max_turbo > 0:
                turbo_scores = {}
                for t in self.turbo_assets:
                    s = self._score(t)
                    if s is None:
                        return
                    turbo_scores[t] = s
                ranked_turbo = sorted(self.turbo_assets, key=lambda x: turbo_scores[x], reverse=True)
                selected_turbo = [t for t in ranked_turbo if turbo_scores[t] >= self.min_turbo_signal][:max_turbo]
                if len(selected_turbo) > 0:
                    turbo_w = turbo_gross / len(selected_turbo)
                    for t in selected_turbo:
                        target[t] = target.get(t, 0.0) + turbo_w

        target = self._normalize_and_cap(target)

        all_assets = list(dict.fromkeys(self.core_assets + self.safe_assets + self.turbo_assets + self.bear_assets))
        eq = self.Portfolio.TotalPortfolioValue
        for t in all_assets:
            sym = self.symbols[t]
            desired = float(target.get(t, 0.0))
            current = self.Portfolio[sym].HoldingsValue / eq if eq > 0 else 0.0
            if abs(desired - current) > self.rebalance_buffer:
                self.SetHoldings(sym, desired, tag=f"V7_REB {self.current_regime} {t}")

        self.current_targets = target

    def OnEndOfAlgorithm(self):
        eq = self.Portfolio.TotalPortfolioValue
        ret = (eq - self.initial_cash) / self.initial_cash if self.initial_cash else 0.0
        dd = (self.peak_equity - eq) / self.peak_equity if self.peak_equity > 0 else 0.0
        self.Log(f"FINAL v7 equity={eq:.2f} return_pct={ret*100:.2f} dd_pct={dd*100:.2f} regime={self.current_regime}")

