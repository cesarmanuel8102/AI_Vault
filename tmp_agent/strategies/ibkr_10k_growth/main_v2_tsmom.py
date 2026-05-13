# region imports
from AlgorithmImports import *
from datetime import timedelta
# endregion


class IBKR10KTSMOMV2(QCAlgorithm):
    """
    IBKR 10K - TSMOM V2 (cross-asset, medium/high risk)
    ----------------------------------------------------
    - Time-series momentum (12m + 3m blend) on diversified ETFs.
    - Volatility-scaled weights with configurable gross leverage.
    - Weekly rebalance + drawdown circuit breaker.
    """

    def Initialize(self):
        self.SetStartDate(
            int(self.GetParameter("start_year") or 2010),
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

        self.assets = [
            "SPY", "QQQ", "IWM", "EFA", "EEM",  # equities
            "TLT", "IEF",                        # rates
            "GLD", "DBC",                        # commodities
            "UUP",                               # dollar
        ]
        self.benchmark_ticker = "SPY"

        self.lookback_fast = int(self.GetParameter("lookback_fast") or 63)     # 3m
        self.lookback_slow = int(self.GetParameter("lookback_slow") or 252)    # 12m
        self.atr_period = int(self.GetParameter("atr_period") or 20)
        self.sma_filter_period = int(self.GetParameter("sma_filter_period") or 200)

        self.w_fast = float(self.GetParameter("w_fast") or 0.35)
        self.w_slow = float(self.GetParameter("w_slow") or 0.65)
        self.vol_penalty = float(self.GetParameter("vol_penalty") or 1.2)
        self.min_abs_signal = float(self.GetParameter("min_abs_signal") or 0.01)
        self.max_active = int(self.GetParameter("max_active") or 6)

        self.gross_risk_on = float(self.GetParameter("gross_risk_on") or 1.50)
        self.gross_risk_off = float(self.GetParameter("gross_risk_off") or 0.85)
        self.max_single_weight = float(self.GetParameter("max_single_weight") or 0.35)
        self.rebalance_buffer = float(self.GetParameter("rebalance_buffer") or 0.03)

        self.circuit_dd_pct = float(self.GetParameter("circuit_dd_pct") or 0.20)
        self.cooldown_days = int(self.GetParameter("cooldown_days") or 20)

        self.symbols = {}
        self.ind = {}
        for t in self.assets:
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
                self.Liquidate(tag="CIRCUIT_BREAKER")
                self.cooldown_until = self.Time + timedelta(days=self.cooldown_days)
                self.current_targets = {}

    def _ready(self, ticker):
        i = self.ind[ticker]
        return i["roc_fast"].IsReady and i["roc_slow"].IsReady and i["atr"].IsReady and i["sma"].IsReady

    def _signal_and_vol(self, ticker):
        sym = self.symbols[ticker]
        px = self.Securities[sym].Price
        if px is None or px <= 0:
            return None, None
        roc_fast = float(self.ind[ticker]["roc_fast"].Current.Value)
        roc_slow = float(self.ind[ticker]["roc_slow"].Current.Value)
        atr = float(self.ind[ticker]["atr"].Current.Value)
        atr_pct = atr / px if px > 0 else 0.0
        signal = self.w_fast * roc_fast + self.w_slow * roc_slow - self.vol_penalty * atr_pct
        return signal, max(1e-6, atr_pct)

    def Rebalance(self):
        if self.IsWarmingUp:
            return
        if self.cooldown_until is not None and self.Time < self.cooldown_until:
            return
        if self.cooldown_until is not None and self.Time >= self.cooldown_until:
            self.cooldown_until = None

        for t in self.assets:
            if not self._ready(t):
                return

        # Regime: SPY trend filter
        b = self.benchmark_ticker
        b_sym = self.symbols[b]
        b_px = self.Securities[b_sym].Price
        b_sma = float(self.ind[b]["sma"].Current.Value)
        b_roc = float(self.ind[b]["roc_slow"].Current.Value)
        risk_on = bool(b_px > b_sma and b_roc > 0)
        gross_target = self.gross_risk_on if risk_on else self.gross_risk_off

        sig = {}
        vol = {}
        for t in self.assets:
            s, v = self._signal_and_vol(t)
            if s is None:
                return
            sig[t] = s
            vol[t] = v

        # Keep strongest absolute signals
        ranked = sorted(self.assets, key=lambda t: abs(sig[t]), reverse=True)
        candidates = [t for t in ranked if abs(sig[t]) >= self.min_abs_signal][: self.max_active]
        if len(candidates) == 0:
            # Cash-ish fallback
            candidates = ["SHY"] if "SHY" in self.assets else [self.assets[0]]

        # Volatility-scaled raw weights (inverse vol * sign(signal))
        raw = {}
        for t in candidates:
            direction = 1.0 if sig[t] > 0 else -1.0
            raw[t] = direction * (1.0 / vol[t])

        gross_raw = sum(abs(w) for w in raw.values())
        target = {}
        if gross_raw > 0:
            scale = gross_target / gross_raw
            for t, w in raw.items():
                tw = w * scale
                tw = max(-self.max_single_weight, min(self.max_single_weight, tw))
                target[t] = tw

        # Apply holdings
        for t in self.assets:
            sym = self.symbols[t]
            desired = float(target.get(t, 0.0))
            eq = self.Portfolio.TotalPortfolioValue
            current = self.Portfolio[sym].HoldingsValue / eq if eq > 0 else 0.0
            if abs(desired - current) > self.rebalance_buffer:
                self.SetHoldings(sym, desired, tag=f"REB {t} sig={sig[t]:.4f}")

        self.current_targets = target

    def MonthlyReport(self):
        eq = self.Portfolio.TotalPortfolioValue
        dd = (self.peak_equity - eq) / self.peak_equity if self.peak_equity > 0 else 0.0
        gross = 0.0
        for t in self.assets:
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
