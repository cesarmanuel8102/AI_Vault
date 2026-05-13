# region imports
from AlgorithmImports import *
# endregion

class SectorMomentumLeveraged(QCAlgorithm):
    """
    TAC-MOM V1.2 "Fenix Sector Momentum"
    ======================================
    UPGRADE from V1.1: Sector ETFs + leverage
    
    V1.1 DIAGNOSIS:
    - CAGR 7.93% with SPY/QQQ/IWM/EFA/EEM → too correlated, 
      momentum signals don't differentiate enough
    - Sector ETFs have MORE DISPERSION → better momentum signal
    - When XLK is up 20% and XLE is down 15%, there's a strong signal
    - Broad ETFs (SPY vs QQQ) rarely diverge that much
    
    CHANGES:
    - Universe: 9 sectors + TLT + GLD + SHY (12 assets total)
    - Hold top 3 at 40% each (120% total = mild leverage via margin)
    - Shorter lookback option: test 1-month, 3-month, 6-month
    - Momentum ranking: pure price return over lookback
    - Absolute momentum filter: skip assets with negative returns
    
    INSTRUMENTS:
    - XLK (Technology), XLF (Financials), XLE (Energy), XLV (Healthcare)
    - XLI (Industrials), XLU (Utilities), XLP (Staples), XLY (Discretionary)
    - XLB (Materials)
    - TLT (Long Bonds), GLD (Gold), SHY (Cash proxy)
    
    FREE PARAMETERS: 1 (lookback_months)
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
        self.WEIGHT_EACH    = 0.40   # 40% each → 120% total (mild leverage)
        
        # Universe: 9 sectors + 3 defensive
        self.tickers = [
            "XLK", "XLF", "XLE", "XLV", "XLI", "XLU", "XLP", "XLY", "XLB",
            "TLT", "GLD", "SHY"
        ]
        
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
            self.TimeRules.AfterMarketOpen("XLK", 30),
            self.Rebalance
        )
        
        self.Schedule.On(
            self.DateRules.MonthEnd("XLK"),
            self.TimeRules.BeforeMarketClose("XLK", 5),
            self.MonthlyReport
        )

    def OnData(self, data):
        for ticker, sym in self.symbols.items():
            if data.Bars.ContainsKey(sym):
                self.windows[ticker].Add(float(data.Bars[sym].Close))

    def Rebalance(self):
        if self.IsWarmingUp:
            return
        
        # Verify data sufficiency
        for ticker in self.tickers:
            if self.windows[ticker].Count < self.LOOKBACK_DAYS:
                return
        
        equity = self.Portfolio.TotalPortfolioValue
        if equity <= 0:
            return
        if equity > self.peak_equity:
            self.peak_equity = equity
        
        # Calculate momentum
        momentums = {}
        for ticker in self.tickers:
            current = self.windows[ticker][0]
            past    = self.windows[ticker][self.LOOKBACK_DAYS - 1]
            if past > 0:
                momentums[ticker] = (current / past) - 1.0
        
        if len(momentums) < len(self.tickers):
            return
        
        # Rank by momentum
        ranked = sorted(momentums.items(), key=lambda x: x[1], reverse=True)
        
        # Select top N with positive momentum
        selected = []
        for ticker, mom in ranked:
            if mom > 0 and len(selected) < self.TOP_N:
                selected.append(ticker)
        
        # Fill with SHY if not enough positive-momentum assets
        while len(selected) < self.TOP_N:
            if "SHY" not in selected:
                selected.append("SHY")
            elif "TLT" not in selected:
                selected.append("TLT")
            else:
                break
        
        target_set = set(selected)
        
        # Sell everything not in target
        for ticker in self.tickers:
            sym = self.symbols[ticker]
            if ticker not in target_set and self.Portfolio[sym].Invested:
                self.Liquidate(sym, tag=f"SELL {ticker}")
        
        # Set target holdings (leveraged: 3 * 40% = 120%)
        for ticker in selected:
            sym = self.symbols[ticker]
            self.SetHoldings(sym, self.WEIGHT_EACH,
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
