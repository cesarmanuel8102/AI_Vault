# region imports
from AlgorithmImports import *
from datetime import timedelta
# endregion


class IBKR10KTurboV3(QCAlgorithm):
    """
    IBKR 10K Turbo V3
    -----------------
    Aggressive tactical momentum with leveraged ETFs.
    Objective: maximize growth, accepting high drawdowns.
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

        # Turbo universe
        self.risk_assets = ["TQQQ", "SOXL", "UPRO", "TECL"]
        self.safe_assets = ["SHY", "IEF", "GLD"]
        self.benchmark_ticker = "SPY"
        self.vix_ticker = "VIXY"

        self.lookback_fast = int(self.GetParameter("lookback_fast") or 21)
        self.lookback_slow = int(self.GetParameter("lookback_slow") or 63)
        self.sma_filter_period = int(self.GetParameter("sma_filter_period") or 200)
        self.atr_period = int(self.GetParameter("atr_period") or 14)
        self.vixy_sma_period = int(self.GetParameter("vixy_sma_period") or 20)

        self.w_fast = float(self.GetParameter("w_fast") or 0.65)
        self.w_slow = float(self.GetParameter("w_slow") or 0.35)
        self.min_signal = float(self.GetParameter("min_signal") or 0.0)

        self.gross_risk_on = float(self.GetParameter("gross_risk_on") or 3.2)
        self.gross_risk_off = float(self.GetParameter("gross_risk_off") or 0.6)
        self.max_single_weight = float(self.GetParameter("max_single_weight") or 1.35)
        self.max_active = int(self.GetParameter("max_active") or 2)

        self.vixy_ratio_block = float(self.GetParameter("vixy_ratio_block") or 1.12)
        self.vol_target_atr_pct = float(self.GetParameter("vol_target_atr_pct") or 0.06)
        self.rebalance_buffer = float(self.GetParameter("rebalance_buffer") or 0.05)

        self.circuit_dd_pct = float(self.GetParameter("circuit_dd_pct") or 0.35)
        self.cooldown_days = int(self.GetParameter("cooldown_days") or 20)

        self.symbols = {}
        self.ind = {}

        all_tickers = [self.benchmark_ticker, self.vix_ticker] + self.risk_assets + self.safe_assets
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
        equity = self.Portfolio.TotalPortfolioValue
        if equity > self.peak_equity:
            self.peak_equity = equity
        dd = (self.peak_equity - equity) / self.peak_equity if self.peak_equity > 0 else 0.0
        if dd >= self.circuit_dd_pct:
            if self.cooldown_until is None or self.Time > self.cooldown_until:
                self.Liquidate(tag="TURBO_CIRCUIT_BREAK")
                self.cooldown_until = self.Time + timedelta(days=self.cooldown_days)
                self.current_targets = {}

    def _ready(self, ticker):
        i = self.ind[ticker]
        return i["roc_fast"].IsReady and i["roc_slow"].IsReady and i["atr"].IsReady and i["sma"].IsReady

    def _signal(self, ticker):
        s = self.w_fast * float(self.ind[ticker]["roc_fast"].Current.Value) + self.w_slow * float(self.ind[ticker]["roc_slow"].Current.Value)
        return s

    def Rebalance(self):
        if self.IsWarmingUp:
            return
        if self.cooldown_until is not None and self.Time < self.cooldown_until:
            return
        if self.cooldown_until is not None and self.Time >= self.cooldown_until:
            self.cooldown_until = None

        for t in [self.benchmark_ticker, self.vix_ticker] + self.risk_assets + self.safe_assets:
            if not self._ready(t):
                return
        if not self.vixy_sma.IsReady:
            return

        # Regime gates
        b = self.benchmark_ticker
        b_px = self.Securities[self.symbols[b]].Price
        b_sma = float(self.ind[b]["sma"].Current.Value)
        b_mom = float(self.ind[b]["roc_slow"].Current.Value)

        vixy_px = self.Securities[self.symbols[self.vix_ticker]].Price
        vixy_sma = float(self.vixy_sma.Current.Value) if self.vixy_sma.Current.Value else 0.0
        vixy_ratio = (vixy_px / vixy_sma) if (vixy_px and vixy_sma > 0) else 1.0

        risk_on = bool(b_px > b_sma and b_mom > 0 and vixy_ratio < self.vixy_ratio_block)

        target = {}

        if risk_on:
            scores = {t: self._signal(t) for t in self.risk_assets}
            ranked = sorted(self.risk_assets, key=lambda t: scores[t], reverse=True)
            selected = [t for t in ranked if scores[t] >= self.min_signal][: self.max_active]
            if len(selected) == 0:
                selected = [ranked[0]]

            # Dynamic gross throttle by benchmark ATR%
            atr_b = float(self.ind[b]["atr"].Current.Value)
            atr_b_pct = atr_b / b_px if b_px > 0 else 0.0
            gross = self.gross_risk_on
            if atr_b_pct > 0:
                vol_scale = min(1.0, self.vol_target_atr_pct / max(1e-6, atr_b_pct))
                gross = max(self.gross_risk_off, self.gross_risk_on * vol_scale)

            w = min(self.max_single_weight, gross / len(selected))
            for t in selected:
                target[t] = w
        else:
            safe_scores = {t: self._signal(t) for t in self.safe_assets}
            best_safe = max(self.safe_assets, key=lambda t: safe_scores[t])
            target[best_safe] = min(1.0, max(0.0, self.gross_risk_off))

        # apply
        all_assets = self.risk_assets + self.safe_assets
        eq = self.Portfolio.TotalPortfolioValue
        for t in all_assets:
            sym = self.symbols[t]
            desired = float(target.get(t, 0.0))
            current = self.Portfolio[sym].HoldingsValue / eq if eq > 0 else 0.0
            if abs(desired - current) > self.rebalance_buffer:
                self.SetHoldings(sym, desired, tag=f"TURBO_REB {t}")

        self.current_targets = target

    def MonthlyReport(self):
        eq = self.Portfolio.TotalPortfolioValue
        dd = (self.peak_equity - eq) / self.peak_equity if self.peak_equity > 0 else 0.0
        gross = 0.0
        for t in self.risk_assets + self.safe_assets:
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
        self.Log(f"FINAL turbo equity={eq:.2f} return_pct={ret*100:.2f} dd_pct={dd*100:.2f}")
