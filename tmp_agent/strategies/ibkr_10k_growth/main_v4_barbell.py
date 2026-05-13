# region imports
from AlgorithmImports import *
from datetime import timedelta
# endregion


class IBKR10KBarbellV4(QCAlgorithm):
    """
    IBKR 10K Barbell V4
    -------------------
    Core TSMOM diversified sleeve + conditional turbo sleeve.
    Goal: better long-horizon robustness than pure turbo, with higher upside than pure core.
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
        self.vix_ticker = "VIXY"

        # Core sleeve (diversified)
        self.core_assets = ["SPY", "QQQ", "IWM", "EFA", "EEM", "TLT", "IEF", "GLD", "DBC", "UUP"]
        # Turbo sleeve (concentrated)
        self.turbo_assets = ["TQQQ", "SOXL", "UPRO", "TECL"]
        self.cash_proxy = "SHY"

        self.lookback_fast = int(self.GetParameter("lookback_fast") or 63)
        self.lookback_slow = int(self.GetParameter("lookback_slow") or 252)
        self.atr_period = int(self.GetParameter("atr_period") or 20)
        self.sma_filter_period = int(self.GetParameter("sma_filter_period") or 200)
        self.vixy_sma_period = int(self.GetParameter("vixy_sma_period") or 20)

        self.w_fast = float(self.GetParameter("w_fast") or 0.0)
        self.w_slow = float(self.GetParameter("w_slow") or 1.0)
        self.vol_penalty = float(self.GetParameter("vol_penalty") or 0.8)
        self.min_signal = float(self.GetParameter("min_signal") or 0.0)

        # Gross exposures
        self.core_gross = float(self.GetParameter("core_gross") or 1.25)
        self.turbo_gross = float(self.GetParameter("turbo_gross") or 0.90)
        self.max_total_gross = float(self.GetParameter("max_total_gross") or 2.20)
        self.max_single_weight = float(self.GetParameter("max_single_weight") or 0.80)
        self.max_core_active = int(self.GetParameter("max_core_active") or 6)
        self.max_turbo_active = int(self.GetParameter("max_turbo_active") or 1)

        self.turbo_trigger_signal = float(self.GetParameter("turbo_trigger_signal") or 0.10)
        self.vixy_ratio_block = float(self.GetParameter("vixy_ratio_block") or 1.10)
        self.rebalance_buffer = float(self.GetParameter("rebalance_buffer") or 0.03)

        self.circuit_dd_pct = float(self.GetParameter("circuit_dd_pct") or 0.28)
        self.cooldown_days = int(self.GetParameter("cooldown_days") or 20)

        self.symbols = {}
        self.ind = {}

        all_tickers = list(dict.fromkeys([self.benchmark_ticker, self.vix_ticker, self.cash_proxy] + self.core_assets + self.turbo_assets))
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

        self.vixy_sma = self.SMA(self.symbols[self.vix_ticker], self.vixy_sma_period, Resolution.Daily)
        self.SetWarmUp(max(self.lookback_slow, self.sma_filter_period, self.vixy_sma_period) + 10, Resolution.Daily)

        self.peak_equity = self.initial_cash
        self.cooldown_until = None
        self.current_targets = {}

        self.Schedule.On(
            self.DateRules.Every(DayOfWeek.Monday),
            self.TimeRules.AfterMarketOpen(self.benchmark_ticker, 45),
            self.Rebalance,
        )
        self.Schedule.On(
            self.DateRules.MonthEnd(self.benchmark_ticker),
            self.TimeRules.BeforeMarketClose(self.benchmark_ticker, 5),
            self.MonthlyReport,
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
                self.Liquidate(tag="BARBELL_CIRCUIT_BREAK")
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

    def Rebalance(self):
        if self.IsWarmingUp:
            return
        if self.cooldown_until is not None and self.Time < self.cooldown_until:
            return
        if self.cooldown_until is not None and self.Time >= self.cooldown_until:
            self.cooldown_until = None

        needed = list(dict.fromkeys([self.benchmark_ticker, self.vix_ticker, self.cash_proxy] + self.core_assets + self.turbo_assets))
        for t in needed:
            if not self._ready(t):
                return
        if not self.vixy_sma.IsReady:
            return

        b = self.benchmark_ticker
        b_px = self.Securities[self.symbols[b]].Price
        b_sma = float(self.ind[b]["sma"].Current.Value)
        b_mom = float(self.ind[b]["roc_slow"].Current.Value)
        vixy_px = self.Securities[self.symbols[self.vix_ticker]].Price
        vixy_sma = float(self.vixy_sma.Current.Value) if self.vixy_sma.Current.Value else 0.0
        vixy_ratio = (vixy_px / vixy_sma) if (vixy_px and vixy_sma > 0) else 1.0

        risk_on = bool(b_px > b_sma and b_mom > 0 and vixy_ratio < self.vixy_ratio_block)

        target = {}

        # Core sleeve
        core_scores = {}
        for t in self.core_assets:
            s = self._signal(t)
            if s is None:
                return
            core_scores[t] = s
        ranked_core = sorted(self.core_assets, key=lambda t: abs(core_scores[t]), reverse=True)
        core_sel = [t for t in ranked_core if abs(core_scores[t]) >= self.min_signal][: self.max_core_active]
        if len(core_sel) == 0:
            core_sel = [self.cash_proxy]

        core_raw = {}
        for t in core_sel:
            direction = 1.0 if core_scores[t] >= 0 else -1.0
            core_raw[t] = direction * abs(core_scores[t] if core_scores[t] != 0 else 1e-6)
        core_gross_raw = sum(abs(x) for x in core_raw.values())
        if core_gross_raw > 0:
            for t, w in core_raw.items():
                target[t] = target.get(t, 0.0) + (w / core_gross_raw) * self.core_gross

        # Turbo sleeve only in strong risk-on
        if risk_on:
            turbo_scores = {}
            for t in self.turbo_assets:
                s = self._signal(t)
                if s is None:
                    return
                turbo_scores[t] = s
            turbo_rank = sorted(self.turbo_assets, key=lambda t: turbo_scores[t], reverse=True)
            turbo_sel = [t for t in turbo_rank if turbo_scores[t] >= self.turbo_trigger_signal][: self.max_turbo_active]
            if len(turbo_sel) > 0:
                per = self.turbo_gross / len(turbo_sel)
                for t in turbo_sel:
                    target[t] = target.get(t, 0.0) + per

        # Normalize/clamp total gross
        gross = sum(abs(v) for v in target.values())
        if gross > self.max_total_gross and gross > 0:
            scale = self.max_total_gross / gross
            for k in list(target.keys()):
                target[k] *= scale
        for k in list(target.keys()):
            target[k] = max(-self.max_single_weight, min(self.max_single_weight, target[k]))

        # Apply
        all_assets = list(dict.fromkeys(self.core_assets + self.turbo_assets + [self.cash_proxy]))
        eq = self.Portfolio.TotalPortfolioValue
        for t in all_assets:
            sym = self.symbols[t]
            desired = float(target.get(t, 0.0))
            current = self.Portfolio[sym].HoldingsValue / eq if eq > 0 else 0.0
            if abs(desired - current) > self.rebalance_buffer:
                self.SetHoldings(sym, desired, tag=f"BARBELL_REB {t}")

        self.current_targets = target

    def MonthlyReport(self):
        eq = self.Portfolio.TotalPortfolioValue
        dd = (self.peak_equity - eq) / self.peak_equity if self.peak_equity > 0 else 0.0
        gross = 0.0
        for t in list(dict.fromkeys(self.core_assets + self.turbo_assets + [self.cash_proxy])):
            sym = self.symbols[t]
            if self.Portfolio[sym].Invested:
                gross += abs(self.Portfolio[sym].HoldingsValue) / max(1e-9, eq)
        self.Plot("Strategy", "Equity", eq)
        self.Plot("Strategy", "DrawdownPct", dd * 100.0)
        self.Plot("Strategy", "GrossLeverage", gross)

    def OnEndOfAlgorithm(self):
        eq = self.Portfolio.TotalPortfolioValue
        ret = (eq - self.initial_cash) / self.initial_cash if self.initial_cash else 0.0
        dd = (self.peak_equity - eq) / self.peak_equity if self.peak_equity > 0 else 0.0
        self.Log(f"FINAL barbell equity={eq:.2f} return_pct={ret*100:.2f} dd_pct={dd*100:.2f}")
