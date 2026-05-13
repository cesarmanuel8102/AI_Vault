# region imports
from AlgorithmImports import *
# endregion

class MeanReversionFutures(QCAlgorithm):
    """
    MR-FUT V1.0 "Fenix Futures" - RSI(2) Mean Reversion on Futures
    ================================================================
    THESIS: RSI(2) edge confirmed on equities (68% WR, 0.62% avg win).
    Futures have INHERENT LEVERAGE: 1 ES contract = ~$150K notional.
    The small % edge becomes meaningful $ P&L per trade.
    
    PROP FIRM COMPATIBLE: TopStep / Apex (futures only).
    
    MARKETS: ES (S&P 500), NQ (NASDAQ), GC (Gold), ZN (10Y Treasury)
    - 2 equity index + 2 uncorrelated (gold, bonds) = diversification
    
    RULES:
    - LONG:  RSI(2) < rsi_entry  AND  cont_price > SMA(200)
    - SHORT: RSI(2) > (100-rsi_entry) AND cont_price < SMA(200)
    - EXIT:  cont_price crosses SMA(5) OR held > max_hold_days
    - NO stop loss (time exit + portfolio DD protection instead)
    - Sizing: 1 contract per market, max 2 concurrent positions
    - DD circuit breaker at -10% (prop firm safe: 5% daily DD * 2 = 10%)
    
    KEY FIXES from CTA discoveries:
    - Indicators on continuous contract (BackwardsRatio adjusted)
    - Orders on mapped contract
    - All signal comparisons use cont_price (same scale as indicators)
    - Contract rolling on SymbolChangedEvents
    
    FREE PARAMETERS: 1 (rsi_entry)
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
        self.rsi_entry = int(self.GetParameter("rsi_entry") or 10)
        
        # ── Fixed parameters ────────────────────────────────────────
        self.RSI_PERIOD        = 2
        self.SMA_EXIT_PERIOD   = 5
        self.SMA_FILTER_PERIOD = 200
        self.MAX_HOLD_DAYS     = 7
        self.MAX_POSITIONS     = 2       # Max 2 concurrent (prop firm safe)
        self.CONTRACTS_PER     = 1       # 1 contract per trade
        self.DD_THROTTLE_PCT   = 0.07    # Reduce at -7%
        self.DD_CIRCUIT_PCT    = 0.10    # Stop at -10% (prop firm protection)
        
        # ── Futures setup ───────────────────────────────────────────
        futures_config = [
            (Futures.Indices.SP500EMini,     "ES"),
            (Futures.Indices.NASDAQ100EMini, "NQ"),
            (Futures.Metals.Gold,            "GC"),
            (Futures.Financials.Y10TreasuryNote, "ZN"),
        ]
        
        self.instruments = {}
        self.sym_to_canonical = {}   # mapped_sym -> canonical_sym lookup
        
        for fut_type, name in futures_config:
            future = self.AddFuture(fut_type, Resolution.Daily,
                                    dataMappingMode=DataMappingMode.OpenInterest,
                                    dataNormalizationMode=DataNormalizationMode.BackwardsRatio,
                                    contractDepthOffset=0)
            future.SetFilter(lambda u: u.FrontMonth())
            sym = future.Symbol
            
            self.instruments[sym] = {
                "name":       name,
                "future":     future,
                "rsi":        self.RSI(sym, self.RSI_PERIOD, MovingAverageType.Wilders, Resolution.Daily),
                "sma_exit":   self.SMA(sym, self.SMA_EXIT_PERIOD, Resolution.Daily),
                "sma_filter": self.SMA(sym, self.SMA_FILTER_PERIOD, Resolution.Daily),
                "entry_date": None,
                "direction":  0,
            }
        
        # ── Portfolio tracking ──────────────────────────────────────
        self.peak_equity    = 100000
        self.cooldown_until = None
        
        # ── Warmup ──────────────────────────────────────────────────
        self.SetWarmUp(self.SMA_FILTER_PERIOD + 10, Resolution.Daily)
        
        # ── Reporting ───────────────────────────────────────────────
        self.Schedule.On(
            self.DateRules.MonthEnd(),
            self.TimeRules.At(15, 50),
            self.MonthlyReport
        )

    # ═════════════════════════════════════════════════════════════════
    #  CONTRACT ROLLING
    # ═════════════════════════════════════════════════════════════════
    
    def OnData(self, data):
        # ── Handle contract rolls ───────────────────────────────────
        for symbol, changed_event in data.SymbolChangedEvents.items():
            old_sym = changed_event.OldSymbol
            new_sym = changed_event.NewSymbol
            qty = self.Portfolio[old_sym].Quantity
            if qty != 0:
                self.Liquidate(old_sym, tag=f"Roll out {old_sym}")
                self.MarketOrder(new_sym, qty, tag=f"Roll in {new_sym}")
        
        if self.IsWarmingUp:
            return
        
        equity = self.Portfolio.TotalPortfolioValue
        
        # ── Peak & DD tracking ──────────────────────────────────────
        if equity > self.peak_equity:
            self.peak_equity = equity
        current_dd = (self.peak_equity - equity) / self.peak_equity if self.peak_equity > 0 else 0
        
        # ── Circuit breaker ─────────────────────────────────────────
        if current_dd >= self.DD_CIRCUIT_PCT:
            if self.cooldown_until is None:
                self.cooldown_until = self.Time + timedelta(days=10)
                for sym, info in self.instruments.items():
                    mapped = info["future"].Mapped
                    if mapped and self.Portfolio[mapped].Invested:
                        self.Liquidate(mapped, tag="CIRCUIT-BREAK")
                    info["direction"] = 0
                    info["entry_date"] = None
            return
        
        if self.cooldown_until:
            if self.Time < self.cooldown_until:
                return
            self.cooldown_until = None
        
        # ── DD throttle ─────────────────────────────────────────────
        size_mult = 0.5 if current_dd >= self.DD_THROTTLE_PCT else 1.0
        contracts_per = max(1, int(self.CONTRACTS_PER * size_mult))
        
        # ── Count open positions ────────────────────────────────────
        def count_open():
            n = 0
            for s, inf in self.instruments.items():
                m = inf["future"].Mapped
                if m and self.Portfolio[m].Quantity != 0:
                    n += 1
            return n
        
        # ── Process each instrument ─────────────────────────────────
        for sym, info in self.instruments.items():
            future = info["future"]
            mapped = future.Mapped
            
            if mapped is None:
                continue
            
            rsi_ind  = info["rsi"]
            sma_exit = info["sma_exit"]
            sma_filt = info["sma_filter"]
            
            if not all([rsi_ind.IsReady, sma_exit.IsReady, sma_filt.IsReady]):
                continue
            
            # Use CONTINUOUS price for all signal comparisons
            cont_price = self.Securities[sym].Price
            if cont_price <= 0:
                continue
            
            rsi_val    = rsi_ind.Current.Value
            sma5_val   = sma_exit.Current.Value
            sma200_val = sma_filt.Current.Value
            
            # Check position on MAPPED contract
            mapped_qty = self.Portfolio[mapped].Quantity
            has_position = mapped_qty != 0
            
            # ── EXIT ────────────────────────────────────────────────
            if has_position and info["direction"] != 0:
                direction = info["direction"]
                days_held = (self.Time - info["entry_date"]).days if info["entry_date"] else 999
                
                # Mean reversion exit (compare continuous prices)
                hit_mr = (direction == 1 and cont_price > sma5_val) or \
                         (direction == -1 and cont_price < sma5_val)
                hit_time = days_held >= self.MAX_HOLD_DAYS
                
                if hit_mr or hit_time:
                    tag_type = "MR-Exit" if hit_mr else "TIME-Exit"
                    self.Liquidate(mapped, tag=f"{tag_type} {info['name']} d={days_held}")
                    info["direction"]  = 0
                    info["entry_date"] = None
                    continue
            
            # ── ENTRY ───────────────────────────────────────────────
            if not has_position:
                if count_open() >= self.MAX_POSITIONS:
                    continue
                
                # LONG: deep oversold in uptrend
                if rsi_val < self.rsi_entry and cont_price > sma200_val:
                    self.MarketOrder(mapped, contracts_per,
                        tag=f"LONG {info['name']} RSI={rsi_val:.1f}")
                    info["entry_date"] = self.Time
                    info["direction"]  = 1
                
                # SHORT: deep overbought in downtrend
                elif rsi_val > (100 - self.rsi_entry) and cont_price < sma200_val:
                    self.MarketOrder(mapped, -contracts_per,
                        tag=f"SHORT {info['name']} RSI={rsi_val:.1f}")
                    info["entry_date"] = self.Time
                    info["direction"]  = -1

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
