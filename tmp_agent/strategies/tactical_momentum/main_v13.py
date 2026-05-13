# region imports
from AlgorithmImports import *
# endregion

class SectorMomentumConcentrated(QCAlgorithm):
    """
    TAC-MOM V1.3 "Fenix Concentrated"
    ===================================
    CHANGES from V1.2:
    - Top 2 sectors at 60% each (120% total, more concentrated)
    - 1-month lookback (21 trading days - most reactive)
    - Same sector universe + defensive assets
    
    HYPOTHESIS: More concentration in the HOTTEST sectors + faster
    rotation should capture more of the upside moves.
    
    FREE PARAMETERS: 1 (lookback_months=1)
    """

    def Initialize(self):
        start_year  = int(self.GetParameter("start_year")  or 2010)
        end_year    = int(self.GetParameter("end_year")    or 2020)
        end_month   = int(self.GetParameter("end_month")   or 12)
        self.SetStartDate(start_year, 1, 1)
        self.SetEndDate(end_year, end_month, 28)
        self.SetCash(100000)
        self.SetBrokerageModel(BrokerageName.InteractiveBrokersBrokerage, AccountType.Margin)
        
        self.lookback_months = int(self.GetParameter("lookback_months") or 1)
        self.LOOKBACK_DAYS   = max(self.lookback_months * 21, 21)
        self.TOP_N           = 2
        self.WEIGHT_EACH     = 0.60   # 60% each → 120% total
        
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
        
        self.Schedule.On(
            self.DateRules.Every(DayOfWeek.Monday),
            self.TimeRules.AfterMarketOpen("XLK", 30),
            self.Rebalance
        )

    def OnData(self, data):
        for ticker, sym in self.symbols.items():
            if data.Bars.ContainsKey(sym):
                self.windows[ticker].Add(float(data.Bars[sym].Close))

    def Rebalance(self):
        if self.IsWarmingUp:
            return
        for ticker in self.tickers:
            if self.windows[ticker].Count < self.LOOKBACK_DAYS:
                return
        
        equity = self.Portfolio.TotalPortfolioValue
        if equity <= 0:
            return
        if equity > self.peak_equity:
            self.peak_equity = equity
        
        momentums = {}
        for ticker in self.tickers:
            current = self.windows[ticker][0]
            past    = self.windows[ticker][self.LOOKBACK_DAYS - 1]
            if past > 0:
                momentums[ticker] = (current / past) - 1.0
        
        if len(momentums) < len(self.tickers):
            return
        
        ranked = sorted(momentums.items(), key=lambda x: x[1], reverse=True)
        
        selected = []
        for ticker, mom in ranked:
            if mom > 0 and len(selected) < self.TOP_N:
                selected.append(ticker)
        while len(selected) < self.TOP_N:
            if "SHY" not in selected:
                selected.append("SHY")
            elif "TLT" not in selected:
                selected.append("TLT")
            else:
                break
        
        target_set = set(selected)
        
        for ticker in self.tickers:
            sym = self.symbols[ticker]
            if ticker not in target_set and self.Portfolio[sym].Invested:
                self.Liquidate(sym, tag=f"SELL {ticker}")
        
        for ticker in selected:
            sym = self.symbols[ticker]
            self.SetHoldings(sym, self.WEIGHT_EACH,
                tag=f"HOLD {ticker} mom={momentums.get(ticker, 0):.1%}")

    def OnEndOfAlgorithm(self):
        equity = self.Portfolio.TotalPortfolioValue
        self.Log(f"FINAL: Equity=${equity:,.0f} Return={(equity-100000)/1000:.2%}")
