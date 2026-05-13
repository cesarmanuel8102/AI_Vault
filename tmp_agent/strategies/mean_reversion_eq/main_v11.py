# region imports
from AlgorithmImports import *
# endregion

class MeanReversionRSI2v11(QCAlgorithm):
    """
    MR-EQ V1.1 "Fenix Corregido" - Pure Connors RSI(2) Mean Reversion
    ===================================================================
    CHANGES FROM V1.0:
    - REMOVED stop loss (Connors original has none; MR needs room to breathe)
    - Added TIME EXIT: force close after max_hold_days (prevents indefinite holds)
    - RSI threshold lowered to 5 (more extreme oversold = higher edge per trade)
    - Max allocation increased to 50% per position (was 30%, was strangling returns)
    - Max 3 concurrent positions (more concentrated)
    
    V1.0 DIAGNOSIS:
    - 66% win rate proved the edge EXISTS
    - P/L ratio 0.61 killed returns: avg loss (-0.61%) >> avg win (0.37%)
    - The 2xATR stop was cutting trades during normal vol before reversion
    - With 848 trades, statistical significance is high
    
    RULES:
    - LONG:  RSI(2) < 5  AND  Close > SMA(200)  [deep oversold in uptrend]
    - SHORT: RSI(2) > 95  AND  Close < SMA(200)  [deep overbought in downtrend]
    - EXIT LONG:  Close > SMA(5)  [mean reversion complete]
    - EXIT SHORT: Close < SMA(5)  [mean reversion complete]
    - TIME EXIT: Close after max_hold_days if neither signal nor stop triggered
    - NO stop loss (portfolio-level DD throttle + circuit breaker provide protection)
    
    FREE PARAMETERS: 1  (rsi_entry=5)
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
        
        # ── FREE PARAMETER (only 1) ────────────────────────────────
        self.rsi_entry = int(self.GetParameter("rsi_entry") or 5)
        
        # ── Canonical / fixed parameters ────────────────────────────
        self.RSI_PERIOD        = 2
        self.SMA_EXIT_PERIOD   = 5
        self.SMA_FILTER_PERIOD = 200
        self.MAX_HOLD_DAYS     = 7      # Force exit after 7 days
        self.RISK_PER_TRADE    = 0.02   # 2% risk per trade (for sizing reference)
        self.MAX_POSITIONS     = 3
        self.MAX_ALLOC_PCT     = 0.50   # Up to 50% equity per position
        self.DD_THROTTLE_PCT   = 0.10
        self.DD_CIRCUIT_PCT    = 0.15
        
        # ── Instruments ─────────────────────────────────────────────
        tickers = ["SPY", "QQQ", "IWM", "DIA"]
        self.instruments = {}
        
        for ticker in tickers:
            eq = self.AddEquity(ticker, Resolution.Daily)
            eq.SetDataNormalizationMode(DataNormalizationMode.Adjusted)
            sym = eq.Symbol
            
            self.instruments[sym] = {
                "ticker":      ticker,
                "rsi":         self.RSI(sym, self.RSI_PERIOD, MovingAverageType.Wilders, Resolution.Daily),
                "sma_exit":    self.SMA(sym, self.SMA_EXIT_PERIOD, Resolution.Daily),
                "sma_filter":  self.SMA(sym, self.SMA_FILTER_PERIOD, Resolution.Daily),
                "entry_price": 0.0,
                "entry_date":  None,
                "direction":   0,       # 1=long, -1=short, 0=flat
            }
        
        # ── Portfolio tracking ──────────────────────────────────────
        self.peak_equity   = 100000
        self.cooldown_until = None
        
        # ── Warmup ──────────────────────────────────────────────────
        self.SetWarmUp(self.SMA_FILTER_PERIOD + 10, Resolution.Daily)
        
        # ── Reporting ───────────────────────────────────────────────
        self.Schedule.On(
            self.DateRules.MonthEnd("SPY"),
            self.TimeRules.BeforeMarketClose("SPY", 5),
            self.MonthlyReport
        )

    # ═════════════════════════════════════════════════════════════════
    def OnData(self, data):
        if self.IsWarmingUp:
            return
        
        equity = self.Portfolio.TotalPortfolioValue
        
        # ── Peak & drawdown tracking ────────────────────────────────
        if equity > self.peak_equity:
            self.peak_equity = equity
        current_dd = (self.peak_equity - equity) / self.peak_equity if self.peak_equity > 0 else 0
        
        # ── Circuit breaker ─────────────────────────────────────────
        if current_dd >= self.DD_CIRCUIT_PCT:
            if self.cooldown_until is None:
                self.cooldown_until = self.Time + timedelta(days=10)
                for sym in self.instruments:
                    if self.Portfolio[sym].Invested:
                        self.Liquidate(sym, tag="CIRCUIT-BREAK")
                        self.instruments[sym]["direction"] = 0
                        self.instruments[sym]["entry_date"] = None
            return
        
        if self.cooldown_until:
            if self.Time < self.cooldown_until:
                return
            self.cooldown_until = None
        
        # ── DD throttle ─────────────────────────────────────────────
        size_mult = 0.5 if current_dd >= self.DD_THROTTLE_PCT else 1.0
        
        # ── Process each instrument ─────────────────────────────────
        for sym, info in self.instruments.items():
            if not data.Bars.ContainsKey(sym):
                continue
            
            rsi_ind  = info["rsi"]
            sma_exit = info["sma_exit"]
            sma_filt = info["sma_filter"]
            
            if not all([rsi_ind.IsReady, sma_exit.IsReady, sma_filt.IsReady]):
                continue
            
            price      = data.Bars[sym].Close
            rsi_val    = rsi_ind.Current.Value
            sma5_val   = sma_exit.Current.Value
            sma200_val = sma_filt.Current.Value
            
            holdings = self.Portfolio[sym]
            
            # ── EXIT LOGIC ──────────────────────────────────────────
            if holdings.Invested and info["direction"] != 0:
                direction = info["direction"]
                days_held = (self.Time - info["entry_date"]).days if info["entry_date"] else 999
                
                # Mean reversion exit
                hit_mr_exit = False
                if direction == 1 and price > sma5_val:
                    hit_mr_exit = True
                elif direction == -1 and price < sma5_val:
                    hit_mr_exit = True
                
                # Time exit
                hit_time_exit = days_held >= self.MAX_HOLD_DAYS
                
                if hit_mr_exit or hit_time_exit:
                    tag = f"{'MR-Exit' if hit_mr_exit else 'TIME-Exit'} {info['ticker']} d={days_held}"
                    self.Liquidate(sym, tag=tag)
                    info["direction"]   = 0
                    info["entry_price"] = 0.0
                    info["entry_date"]  = None
                    continue
            
            # ── ENTRY LOGIC ─────────────────────────────────────────
            if not holdings.Invested:
                num_open = sum(1 for s in self.instruments if self.Portfolio[s].Invested)
                if num_open >= self.MAX_POSITIONS:
                    continue
                
                if price <= 0:
                    continue
                
                # Position size: fraction of equity, capped at MAX_ALLOC_PCT
                alloc = self.MAX_ALLOC_PCT * size_mult
                shares = int((equity * alloc) / price)
                
                if shares <= 0:
                    continue
                
                # ── LONG: deep oversold in uptrend ──────────────────
                if rsi_val < self.rsi_entry and price > sma200_val:
                    self.MarketOrder(sym, shares,
                        tag=f"LONG {info['ticker']} RSI={rsi_val:.1f}")
                    info["entry_price"] = price
                    info["entry_date"]  = self.Time
                    info["direction"]   = 1
                
                # ── SHORT: deep overbought in downtrend ─────────────
                elif rsi_val > (100 - self.rsi_entry) and price < sma200_val:
                    self.MarketOrder(sym, -shares,
                        tag=f"SHORT {info['ticker']} RSI={rsi_val:.1f}")
                    info["entry_price"] = price
                    info["entry_date"]  = self.Time
                    info["direction"]   = -1

    # ═════════════════════════════════════════════════════════════════
    def MonthlyReport(self):
        equity = self.Portfolio.TotalPortfolioValue
        dd = (self.peak_equity - equity) / self.peak_equity if self.peak_equity > 0 else 0
        self.Plot("Strategy", "Equity", equity)
        self.Plot("Strategy", "DD%", dd * 100)

    def OnEndOfAlgorithm(self):
        equity = self.Portfolio.TotalPortfolioValue
        ret = (equity - 100000) / 100000
        self.Log(f"FINAL: Equity=${equity:,.0f} Return={ret:.2%} Peak=${self.peak_equity:,.0f}")
