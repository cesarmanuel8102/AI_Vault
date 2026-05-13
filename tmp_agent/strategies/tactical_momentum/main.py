# region imports
from AlgorithmImports import *
import numpy as np
# endregion

class TacticalMomentumRotation(QCAlgorithm):
    """
    TAC-MOM V1.0 "Fenix Momentum" - Tactical Momentum Rotation
    =============================================================
    THESIS: Antonacci's Dual Momentum + Faber's Timing = 12-18% CAGR 
    historically across decades. Completely different approach from 
    mean reversion or trend following on single instruments.
    
    CONCEPT:
    - Universe of 8 asset classes (equities, international, bonds, gold, cash)
    - WEEKLY: rank by 6-month total return (absolute momentum)
    - Hold TOP 3 assets by momentum
    - CRASH FILTER: if SPY < SMA(200), shift allocation toward TLT/SHY
    - Equal weight among selected assets
    
    ACADEMIC BASIS:
    - Jegadeesh & Titman (1993): Cross-sectional momentum
    - Antonacci (2014): "Dual Momentum Investing"
    - Faber (2007): "A Quantitative Approach to Tactical Asset Allocation"
    
    INSTRUMENTS:
    - SPY  (US Large Cap)
    - QQQ  (US Tech/Growth)
    - IWM  (US Small Cap)
    - EFA  (International Developed)
    - EEM  (Emerging Markets)
    - TLT  (Long-Term US Bonds)
    - GLD  (Gold)
    - SHY  (Short-Term Bonds / Cash proxy)
    
    FREE PARAMETERS: 1 (lookback_months = 6, canonical from Antonacci)
    REBALANCE: Weekly (generates 6-10 trades/month, passes kill gate)
    """

    def Initialize(self):
        # ── Date range ──────────────────────────────────────────────
        start_year  = int(self.GetParameter("start_year")  or 2010)
        end_year    = int(self.GetParameter("end_year")    or 2020)
        end_month   = int(self.GetParameter("end_month")   or 12)
        self.SetStartDate(start_year, 1, 1)
        self.SetEndDate(end_year, end_month, 28)
        
        # ── Capital & broker ────────────────────────────────────────
        self.SetCash(100000)
        self.SetBrokerageModel(BrokerageName.InteractiveBrokersBrokerage, AccountType.Margin)
        
        # ── FREE PARAMETER ──────────────────────────────────────────
        self.lookback_months = int(self.GetParameter("lookback_months") or 6)
        
        # ── Fixed parameters ────────────────────────────────────────
        self.LOOKBACK_DAYS     = self.lookback_months * 21   # ~126 trading days
        self.TOP_N             = 3       # Hold top 3 assets
        self.SMA_FILTER_PERIOD = 200     # Crash filter
        self.TARGET_WEIGHT     = 1.0 / self.TOP_N  # Equal weight = ~33%
        self.REBALANCE_BUFFER  = 0.03    # 3% tolerance before rebalancing
        self.DD_CIRCUIT_PCT    = 0.15    # Circuit breaker
        
        # ── Universe ────────────────────────────────────────────────
        self.tickers = ["SPY", "QQQ", "IWM", "EFA", "EEM", "TLT", "GLD", "SHY"]
        self.risky_assets = ["SPY", "QQQ", "IWM", "EFA", "EEM"]  # Equity-like
        self.safe_assets   = ["TLT", "SHY"]                       # Defensive
        
        self.symbols = {}
        self.history_windows = {}  # RollingWindow for momentum calculation
        
        for ticker in self.tickers:
            eq = self.AddEquity(ticker, Resolution.Daily)
            eq.SetDataNormalizationMode(DataNormalizationMode.Adjusted)
            sym = eq.Symbol
            self.symbols[ticker] = sym
            # Rolling window of closes for momentum calculation
            self.history_windows[ticker] = RollingWindow[float](self.LOOKBACK_DAYS + 5)
        
        # SMA(200) on SPY for crash filter
        self.spy_sma200 = self.SMA(self.symbols["SPY"], self.SMA_FILTER_PERIOD, Resolution.Daily)
        
        # ── Portfolio tracking ──────────────────────────────────────
        self.peak_equity    = 100000
        self.cooldown_until = None
        self.current_holdings = set()   # Tickers currently held
        
        # ── Warmup ──────────────────────────────────────────────────
        self.SetWarmUp(max(self.LOOKBACK_DAYS, self.SMA_FILTER_PERIOD) + 10, Resolution.Daily)
        
        # ── Weekly rebalance ────────────────────────────────────────
        self.Schedule.On(
            self.DateRules.Every(DayOfWeek.Monday),
            self.TimeRules.AfterMarketOpen("SPY", 30),
            self.Rebalance
        )
        
        # ── Monthly report ──────────────────────────────────────────
        self.Schedule.On(
            self.DateRules.MonthEnd("SPY"),
            self.TimeRules.BeforeMarketClose("SPY", 5),
            self.MonthlyReport
        )

    # ═════════════════════════════════════════════════════════════════
    #  DATA COLLECTION
    # ═════════════════════════════════════════════════════════════════

    def OnData(self, data):
        # Collect daily closes into rolling windows
        for ticker, sym in self.symbols.items():
            if data.Bars.ContainsKey(sym):
                self.history_windows[ticker].Add(float(data.Bars[sym].Close))

    # ═════════════════════════════════════════════════════════════════
    #  WEEKLY REBALANCE
    # ═════════════════════════════════════════════════════════════════

    def Rebalance(self):
        if self.IsWarmingUp:
            return
        
        equity = self.Portfolio.TotalPortfolioValue
        
        # ── DD Protection ───────────────────────────────────────────
        if equity > self.peak_equity:
            self.peak_equity = equity
        current_dd = (self.peak_equity - equity) / self.peak_equity if self.peak_equity > 0 else 0
        
        if current_dd >= self.DD_CIRCUIT_PCT:
            if self.cooldown_until is None:
                self.cooldown_until = self.Time + timedelta(days=20)
                self.Liquidate(tag="CIRCUIT-BREAK")
                self.current_holdings = set()
            return
        
        if self.cooldown_until:
            if self.Time < self.cooldown_until:
                return
            self.cooldown_until = None
        
        # ── Check SMA filter readiness ──────────────────────────────
        if not self.spy_sma200.IsReady:
            return
        
        # ── Calculate momentum for each asset ───────────────────────
        momentums = {}
        for ticker in self.tickers:
            window = self.history_windows[ticker]
            if window.Count < self.LOOKBACK_DAYS:
                return  # Not enough data yet, skip rebalance
            
            current_price = window[0]
            past_price    = window[self.LOOKBACK_DAYS - 1]
            
            if past_price > 0:
                momentum = (current_price / past_price) - 1.0
                momentums[ticker] = momentum
        
        if len(momentums) < len(self.tickers):
            return
        
        # ── Crash filter: is SPY in uptrend? ────────────────────────
        spy_price   = self.history_windows["SPY"][0]
        spy_sma_val = self.spy_sma200.Current.Value
        market_bullish = spy_price > spy_sma_val
        
        # ── Select top N assets ─────────────────────────────────────
        if market_bullish:
            # Full universe, rank by momentum
            ranked = sorted(momentums.items(), key=lambda x: x[1], reverse=True)
            # Only select assets with POSITIVE momentum (absolute momentum filter)
            selected = [t for t, m in ranked if m > 0][:self.TOP_N]
            # If fewer than TOP_N have positive momentum, fill with safe assets
            while len(selected) < self.TOP_N:
                for safe in self.safe_assets:
                    if safe not in selected:
                        selected.append(safe)
                        if len(selected) >= self.TOP_N:
                            break
                break
        else:
            # Bear market: shift to defensive assets
            # Rank only safe + gold assets
            defensive = {t: m for t, m in momentums.items() 
                        if t in self.safe_assets or t == "GLD"}
            ranked_def = sorted(defensive.items(), key=lambda x: x[1], reverse=True)
            selected = [t for t, m in ranked_def][:self.TOP_N]
            # Fill remainder with SHY (cash)
            while len(selected) < self.TOP_N:
                if "SHY" not in selected:
                    selected.append("SHY")
                else:
                    break
        
        # ── Execute rebalance ───────────────────────────────────────
        target_tickers = set(selected)
        
        # Sell holdings not in target
        for ticker in list(self.current_holdings):
            if ticker not in target_tickers:
                sym = self.symbols[ticker]
                if self.Portfolio[sym].Invested:
                    self.Liquidate(sym, tag=f"SELL {ticker} (rotation)")
                self.current_holdings.discard(ticker)
        
        # Buy/adjust target holdings
        for ticker in selected:
            sym = self.symbols[ticker]
            current_weight = self.Portfolio[sym].HoldingsValue / equity if equity > 0 else 0
            target_weight = self.TARGET_WEIGHT
            
            # Only rebalance if weight drifted beyond buffer
            if abs(current_weight - target_weight) > self.REBALANCE_BUFFER:
                self.SetHoldings(sym, target_weight, tag=f"BUY {ticker} mom={momentums.get(ticker, 0):.2%}")
            
            self.current_holdings.add(ticker)

    # ═════════════════════════════════════════════════════════════════
    def MonthlyReport(self):
        equity = self.Portfolio.TotalPortfolioValue
        dd = (self.peak_equity - equity) / self.peak_equity if self.peak_equity > 0 else 0
        self.Plot("Strategy", "Equity", equity)
        self.Plot("Strategy", "DD%", dd * 100)
        self.Plot("Strategy", "Holdings", len(self.current_holdings))

    def OnEndOfAlgorithm(self):
        equity = self.Portfolio.TotalPortfolioValue
        ret = (equity - 100000) / 100000
        self.Log(f"FINAL: Equity=${equity:,.0f} Return={ret:.2%} Peak=${self.peak_equity:,.0f}")
        self.Log(f"Current holdings: {self.current_holdings}")
