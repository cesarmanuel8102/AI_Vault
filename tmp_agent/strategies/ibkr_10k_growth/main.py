# region imports
from AlgorithmImports import *
from datetime import timedelta
# endregion


class IBKR10KGrowthMomentum(QCAlgorithm):
    """
    IBKR 10K - Growth Momentum (medium/high risk)
    ----------------------------------------------
    - Tactical momentum rotation on leveraged ETFs.
    - Weekly rebalance.
    - Regime filter + drawdown circuit breaker.
    - Designed for own-capital growth, not prop constraints.
    """

    def Initialize(self):
        self.SetStartDate(
            int(self.GetParameter("start_year") or 2016),
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
        self.risk_assets = ["TQQQ", "UPRO", "SOXL", "UDOW"]
        self.safe_assets = ["TLT", "GLD", "SHY"]
        self.spy_ticker = "SPY"

        # Parameters
        self.lookback_fast = int(self.GetParameter("lookback_fast") or 63)
        self.lookback_slow = int(self.GetParameter("lookback_slow") or 126)
        self.atr_period = int(self.GetParameter("atr_period") or 20)
        self.sma_filter_period = int(self.GetParameter("sma_filter_period") or 200)
        self.top_n = int(self.GetParameter("top_n") or 2)
        self.score_min = float(self.GetParameter("score_min") or 0.02)

        self.w_fast = float(self.GetParameter("w_fast") or 0.65)
        self.w_slow = float(self.GetParameter("w_slow") or 0.35)
        self.vol_penalty = float(self.GetParameter("vol_penalty") or 2.4)
        self.target_atr_pct = float(self.GetParameter("target_atr_pct") or 0.04)
        self.base_gross = float(self.GetParameter("base_gross") or 1.40)
        self.max_gross = float(self.GetParameter("max_gross") or 1.60)
        self.max_single_weight = float(self.GetParameter("max_single_weight") or 0.80)

        self.rebalance_buffer = float(self.GetParameter("rebalance_buffer") or 0.03)
        self.circuit_dd_pct = float(self.GetParameter("circuit_dd_pct") or 0.20)
        self.cooldown_days = int(self.GetParameter("cooldown_days") or 20)

        self.symbols = {}
        self.ind = {}

        tickers = [self.spy_ticker] + self.risk_assets + self.safe_assets
        for t in tickers:
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

        self.SetWarmUp(max(self.lookback_slow, self.sma_filter_period) + 10, Resolution.Daily)

        self.peak_equity = self.initial_cash
        self.cooldown_until = None
        self.current_targets = {}

        self.Schedule.On(
            self.DateRules.Every(DayOfWeek.Monday),
            self.TimeRules.AfterMarketOpen(self.spy_ticker, 45),
            self.Rebalance,
        )
        self.Schedule.On(
            self.DateRules.MonthEnd(self.spy_ticker),
            self.TimeRules.BeforeMarketClose(self.spy_ticker, 5),
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
                self.Liquidate(tag="CIRCUIT_BREAKER")
                self.cooldown_until = self.Time + timedelta(days=self.cooldown_days)
                self.current_targets = {}

    def _is_ready(self, ticker):
        i = self.ind[ticker]
        return i["roc_fast"].IsReady and i["roc_slow"].IsReady and i["atr"].IsReady and i["sma"].IsReady

    def _score(self, ticker):
        sym = self.symbols[ticker]
        px = self.Securities[sym].Price
        if px is None or px <= 0:
            return None, None

        roc_fast = float(self.ind[ticker]["roc_fast"].Current.Value)
        roc_slow = float(self.ind[ticker]["roc_slow"].Current.Value)
        atr = float(self.ind[ticker]["atr"].Current.Value)
        atr_pct = atr / px if px > 0 else 0.0

        score = self.w_fast * roc_fast + self.w_slow * roc_slow - self.vol_penalty * atr_pct
        return score, atr_pct

    def Rebalance(self):
        if self.IsWarmingUp:
            return

        if self.cooldown_until is not None and self.Time < self.cooldown_until:
            return
        if self.cooldown_until is not None and self.Time >= self.cooldown_until:
            self.cooldown_until = None

        # Validate indicators
        all_tickers = [self.spy_ticker] + self.risk_assets + self.safe_assets
        for t in all_tickers:
            if not self._is_ready(t):
                return

        # Regime filter
        spy_sym = self.symbols[self.spy_ticker]
        spy_px = self.Securities[spy_sym].Price
        spy_sma = float(self.ind[self.spy_ticker]["sma"].Current.Value)
        spy_roc_slow = float(self.ind[self.spy_ticker]["roc_slow"].Current.Value)
        risk_on = bool(spy_px > spy_sma and spy_roc_slow > 0)

        scores = {}
        atr_pcts = {}
        for t in self.risk_assets + self.safe_assets:
            s, a = self._score(t)
            if s is None:
                return
            scores[t] = s
            atr_pcts[t] = a

        target = {}

        if risk_on:
            ranked = sorted(self.risk_assets, key=lambda t: scores[t], reverse=True)
            selected = [t for t in ranked if scores[t] >= self.score_min][: self.top_n]

            if len(selected) == 0:
                # No clean momentum -> defensive fallback
                safe_best = max(self.safe_assets, key=lambda t: scores[t])
                target[safe_best] = 1.0
            else:
                avg_atr = sum(atr_pcts[t] for t in selected) / max(1, len(selected))
                vol_scale = 1.0
                if avg_atr > 0:
                    vol_scale = min(1.0, self.target_atr_pct / avg_atr)

                gross = min(self.max_gross, self.base_gross * vol_scale)
                w = min(self.max_single_weight, gross / len(selected))
                for t in selected:
                    target[t] = w
        else:
            defensive_ranked = sorted(self.safe_assets, key=lambda t: scores[t], reverse=True)
            # Use two defensive assets when possible
            first = defensive_ranked[0]
            second = defensive_ranked[1]
            target[first] = 0.70
            target[second] = 0.30

        # Apply target weights
        for t in self.risk_assets + self.safe_assets:
            sym = self.symbols[t]
            desired = float(target.get(t, 0.0))
            current = 0.0
            eq = self.Portfolio.TotalPortfolioValue
            if eq > 0:
                current = self.Portfolio[sym].HoldingsValue / eq
            if abs(desired - current) > self.rebalance_buffer:
                self.SetHoldings(sym, desired, tag=f"REB {t} score={scores[t]:.4f}")

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
        self.Log(f"FINAL equity={eq:.2f} return_pct={ret*100:.2f} dd_pct={dd*100:.2f}")
