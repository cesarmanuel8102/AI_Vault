# region imports
from AlgorithmImports import *
# endregion

class TacticalMomentumV11(QCAlgorithm):
    """
    TAC-MOM V1.1 "Fenix Momentum Corregido"
    =========================================
    FIXES from V1.0:
    - REMOVED circuit breaker (was killing COVID recovery)
    - REMOVED rebalance buffer (was suppressing trades)
    - Shorter lookback: 3 months (more reactive to regime changes)
    - Simplified crash filter: momentum-based only (no SMA200)
    - If asset has negative 3-month momentum, replaced with SHY
    - Always rebalance to target weights (no tolerance band)
    
    V1.0 POSTMORTEM:
    - 42 orders in 11 years (should be 500+)
    - Circuit breaker fired during COVID, missed the V-recovery
    - $0 strategy capacity indicated execution issues
    
    CONCEPT: Dual Momentum (Antonacci) + weekly frequency
    - 8 assets: SPY, QQQ, IWM, EFA, EEM, TLT, GLD, SHY
    - Weekly: rank by 3-month total return
    - Hold top 3 with POSITIVE momentum
    - Replace negative-momentum assets with SHY
    - Equal weight (~33% each)
    
    FREE PARAMETERS: 1 (lookback_months = 3)
    """

    def Initialize(self):
        start_year  = int(self.GetParameter("start_year")  or 2010)
        end_year    = int(self.GetParameter("end_year")    or 2020)
        end_month   = int(self.GetParameter("end_month")   or 12)
        self.SetStartDate(start_year, 1, 1)
        self.SetEndDate(end_year, end_month, 28)
        self.SetCash(100000)
        self.SetBrokerageModel(BrokerageName.InteractiveBrokersBrokerage, AccountType.Margin)
        
        # FREE PARAMETER
        self.lookback_months = int(self.GetParameter("lookback_months") or 3)
        self.LOOKBACK_DAYS   = self.lookback_months * 21
        
        # Fixed
        self.TOP_N          = 3
        self.TARGET_WEIGHT  = 1.0 / self.TOP_N
        
        # Universe
        self.tickers = ["SPY", "QQQ", "IWM", "EFA", "EEM", "TLT", "GLD", "SHY"]
        self.symbols = {}
        self.windows = {}
        
        for ticker in self.tickers:
            eq = self.AddEquity(ticker, Resolution.Daily)
            eq.SetDataNormalizationMode(DataNormalizationMode.Adjusted)
            self.symbols[ticker] = eq.Symbol
            self.windows[ticker] = RollingWindow[float](self.LOOKBACK_DAYS + 5)
        
        self.peak_equity = 100000
        self.SetWarmUp(self.LOOKBACK_DAYS + 10, Resolution.Daily)
        
        # Weekly rebalance
        self.Schedule.On(
            self.DateRules.Every(DayOfWeek.Monday),
            self.TimeRules.AfterMarketOpen("SPY", 30),
            self.Rebalance
        )
        
        self.Schedule.On(
            self.DateRules.MonthEnd("SPY"),
            self.TimeRules.BeforeMarketClose("SPY", 5),
            self.MonthlyReport
        )

    def OnData(self, data):
        for ticker, sym in self.symbols.items():
            if data.Bars.ContainsKey(sym):
                self.windows[ticker].Add(float(data.Bars[sym].Close))

    def Rebalance(self):
        if self.IsWarmingUp:
            return
        
        # Check all windows have enough data
        for ticker in self.tickers:
            if self.windows[ticker].Count < self.LOOKBACK_DAYS:
                return
        
        equity = self.Portfolio.TotalPortfolioValue
        if equity <= 0:
            return
        
        if equity > self.peak_equity:
            self.peak_equity = equity
        
        # Calculate momentum for each asset
        momentums = {}
        for ticker in self.tickers:
            current = self.windows[ticker][0]
            past    = self.windows[ticker][self.LOOKBACK_DAYS - 1]
            if past > 0:
                momentums[ticker] = (current / past) - 1.0
        
        if len(momentums) < len(self.tickers):
            return
        
        # Rank by momentum (highest first)
        ranked = sorted(momentums.items(), key=lambda x: x[1], reverse=True)
        
        # Select top N with POSITIVE momentum
        selected = []
        for ticker, mom in ranked:
            if mom > 0 and len(selected) < self.TOP_N:
                selected.append(ticker)
        
        # Fill remaining slots with SHY (cash proxy)
        while len(selected) < self.TOP_N:
            if "SHY" not in selected:
                selected.append("SHY")
            elif "TLT" not in selected:
                selected.append("TLT")
            else:
                break
        
        target_set = set(selected)
        
        # First: sell everything NOT in target
        for ticker in self.tickers:
            sym = self.symbols[ticker]
            if ticker not in target_set and self.Portfolio[sym].Invested:
                self.Liquidate(sym, tag=f"SELL {ticker}")
        
        # Then: set target holdings for selected assets
        for ticker in selected:
            sym = self.symbols[ticker]
            self.SetHoldings(sym, self.TARGET_WEIGHT,
                tag=f"HOLD {ticker} mom={momentums.get(ticker, 0):.1%}")

    def MonthlyReport(self):
        equity = self.Portfolio.TotalPortfolioValue
        dd = (self.peak_equity - equity) / self.peak_equity if self.peak_equity > 0 else 0
        self.Plot("Strategy", "Equity", equity)
        self.Plot("Strategy", "DD%", dd * 100)

    def OnEndOfAlgorithm(self):
        equity = self.Portfolio.TotalPortfolioValue
        ret = (equity - 100000) / 100000
        self.Log(f"FINAL: Equity=${equity:,.0f} Return={ret:.2%}")
