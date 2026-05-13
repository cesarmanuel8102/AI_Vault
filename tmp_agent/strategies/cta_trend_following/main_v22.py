# region imports
from AlgorithmImports import *
# endregion


class CTATrendFollowingV2_2(QCAlgorithm):
    """
    CTA Trend Following V2.2 - Full Turtle + 18 Markets + ATR% Fix
    ================================================================
    CORE HYPOTHESIS: CTA needs 15-20+ diversified markets to work.
    5 markets is insufficient for trend following.
    
    BUG FIX ATTEMPT: Use ATR as percentage of price for position sizing.
    This avoids the BackwardsRatio normalization distortion that caused
    the position explosion in V1.1-V1.8.
    
    Signal: Donchian 55d breakout entry, 20d exit
    Sizing: ATR%-based (ATR/Price * multiplier * price = dollar risk)
    Risk: 0.5% per market (conservative), max 2% sector, 6% total
    Markets: All 18 futures
    """

    def Initialize(self):
        self.start_year = int(self.GetParameter("start_year", 2010))
        self.end_year = int(self.GetParameter("end_year", 2020))
        end_month = int(self.GetParameter("end_month", 12))

        self.SetStartDate(self.start_year, 1, 1)
        self.SetEndDate(self.end_year, end_month, 28)
        self.SetCash(1000000)

        self.SetBrokerageModel(BrokerageName.InteractiveBrokersBrokerage, AccountType.Margin)

        # Parameters
        self.entry_period = int(self.GetParameter("entry_period", 55))
        self.exit_period = int(self.GetParameter("exit_period", 20))
        self.atr_period = int(self.GetParameter("atr_period", 20))
        self.stop_atr_mult = float(self.GetParameter("stop_atr_mult", 3.0))
        self.risk_per_market = float(self.GetParameter("risk_per_market", 0.005))

        # ALL 18 markets - bug fix via ATR% sizing
        self.future_tickers = [
            Futures.Indices.SP500EMini,
            Futures.Indices.NASDAQ100EMini,
            Futures.Indices.Dow30EMini,
            Futures.Energies.CrudeOilWTI,
            Futures.Energies.NaturalGas,
            Futures.Metals.Gold,
            Futures.Metals.Silver,
            Futures.Metals.Copper,
            Futures.Grains.Corn,
            Futures.Grains.Soybeans,
            Futures.Grains.Wheat,
            Futures.Financials.Y10TreasuryNote,
            Futures.Financials.Y30TreasuryBond,
            Futures.Currencies.EUR,
            Futures.Currencies.JPY,
            Futures.Currencies.GBP,
            Futures.Currencies.AUD,
            Futures.Currencies.CAD,
        ]

        # Sector groupings for correlation-based risk limits
        self.sectors = {
            "indices": [Futures.Indices.SP500EMini, Futures.Indices.NASDAQ100EMini, Futures.Indices.Dow30EMini],
            "energy": [Futures.Energies.CrudeOilWTI, Futures.Energies.NaturalGas],
            "metals": [Futures.Metals.Gold, Futures.Metals.Silver, Futures.Metals.Copper],
            "grains": [Futures.Grains.Corn, Futures.Grains.Soybeans, Futures.Grains.Wheat],
            "rates": [Futures.Financials.Y10TreasuryNote, Futures.Financials.Y30TreasuryBond],
            "fx": [Futures.Currencies.EUR, Futures.Currencies.JPY, Futures.Currencies.GBP,
                   Futures.Currencies.AUD, Futures.Currencies.CAD],
        }
        # Reverse lookup: ticker -> sector
        self.ticker_sector = {}
        for sector, tickers in self.sectors.items():
            for t in tickers:
                self.ticker_sector[t] = sector

        self.futures = {}
        self.indicators = {}
        self.trailing_stops = {}
        self.position_directions = {}  # sym -> +1/-1/0 (track our intended direction)

        for ticker in self.future_tickers:
            future = self.AddFuture(ticker, Resolution.Daily,
                                     dataMappingMode=DataMappingMode.OpenInterest,
                                     dataNormalizationMode=DataNormalizationMode.BackwardsRatio,
                                     contractDepthOffset=0)
            future.SetFilter(lambda u: u.FrontMonth())
            self.futures[ticker] = future

            sym = future.Symbol
            self.indicators[sym] = {
                "entry_high": self.MAX(sym, self.entry_period, Resolution.Daily),
                "entry_low": self.MIN(sym, self.entry_period, Resolution.Daily),
                "exit_high": self.MAX(sym, self.exit_period, Resolution.Daily),
                "exit_low": self.MIN(sym, self.exit_period, Resolution.Daily),
                "atr": self.ATR(sym, self.atr_period, MovingAverageType.Simple, Resolution.Daily),
            }
            self.trailing_stops[sym] = None
            self.position_directions[sym] = 0

        self.SetWarmUp(timedelta(days=int(self.entry_period * 2.5)))

    def OnData(self, slice):
        if self.IsWarmingUp:
            return

        equity = self.Portfolio.TotalPortfolioValue
        if equity <= 0:
            return

        # Handle rollovers FIRST
        for symbol, changed_event in slice.SymbolChangedEvents.items():
            old_s = changed_event.OldSymbol
            new_s = changed_event.NewSymbol
            qty = self.Portfolio[old_s].Quantity
            if qty != 0:
                self.Liquidate(old_s, tag="Roll out")
                self.MarketOrder(new_s, qty, tag="Roll in")

        # --- ORPHAN CLEANUP ---
        # Scan portfolio for positions not in any current mapped contract
        active_mapped = set()
        for ticker in self.future_tickers:
            m = self.futures[ticker].Mapped
            if m is not None:
                active_mapped.add(str(m))

        for kvp in self.Portfolio:
            holding = kvp.Value
            if holding.Invested:
                sym_str = str(holding.Symbol)
                if sym_str not in active_mapped and holding.Symbol.SecurityType == SecurityType.Future:
                    self.Liquidate(holding.Symbol, tag="Orphan cleanup")

        # Count current risk allocation by sector
        sector_risk = {s: 0 for s in self.sectors}
        total_positions = 0
        for ticker in self.future_tickers:
            future = self.futures[ticker]
            sym = future.Symbol
            mapped = future.Mapped
            if mapped is not None and self.Portfolio[mapped].Invested:
                sector = self.ticker_sector.get(ticker, "unknown")
                sector_risk[sector] = sector_risk.get(sector, 0) + 1
                total_positions += 1

        for ticker in self.future_tickers:
            future = self.futures[ticker]
            sym = future.Symbol
            mapped = future.Mapped

            if mapped is None:
                continue
            if mapped not in self.Securities:
                continue

            sec = self.Securities[mapped]
            real_price = sec.Price  # Actual contract price (for sizing/orders)
            if real_price <= 0:
                continue

            # Continuous contract price (BackwardsRatio adjusted - same scale as indicators)
            cont_price = self.Securities[sym].Price if sym in self.Securities else 0
            if cont_price <= 0:
                continue

            inds = self.indicators[sym]
            required_keys = ["entry_high", "entry_low", "exit_high", "exit_low", "atr"]
            if not all(inds[k].IsReady for k in required_keys):
                continue

            entry_high = inds["entry_high"].Current.Value
            entry_low = inds["entry_low"].Current.Value
            exit_high = inds["exit_high"].Current.Value
            exit_low = inds["exit_low"].Current.Value
            atr_val = inds["atr"].Current.Value

            if atr_val <= 0:
                continue

            current_qty = self.Portfolio[mapped].Quantity
            is_long = current_qty > 0
            is_short = current_qty < 0
            is_flat = current_qty == 0

            multiplier = sec.SymbolProperties.ContractMultiplier
            if multiplier <= 0:
                continue

            # ===== BUG FIX: ATR% sizing =====
            # ATR and Donchian are on BackwardsRatio scale (cont_price).
            # For dollar risk sizing, convert ATR to percentage, apply to real_price.
            atr_pct = atr_val / cont_price  # ATR as fraction of continuous price
            real_atr_dollar = atr_pct * real_price * multiplier  # Dollar ATR on real price

            # ===== EXIT LOGIC =====
            # All signal comparisons use cont_price vs indicators (same BackwardsRatio scale)
            # Trailing stops also in continuous scale
            if is_long:
                stop = self.trailing_stops.get(sym)
                exit_signal = cont_price <= exit_low
                stop_hit = stop is not None and cont_price <= stop

                if exit_signal or stop_hit:
                    self.Liquidate(mapped, tag=f"Exit L {ticker}")
                    self.trailing_stops[sym] = None
                    self.position_directions[sym] = 0
                    continue
                else:
                    new_stop = cont_price - atr_val * self.stop_atr_mult
                    if stop is None or new_stop > stop:
                        self.trailing_stops[sym] = new_stop

            elif is_short:
                stop = self.trailing_stops.get(sym)
                exit_signal = cont_price >= exit_high
                stop_hit = stop is not None and cont_price >= stop

                if exit_signal or stop_hit:
                    self.Liquidate(mapped, tag=f"Exit S {ticker}")
                    self.trailing_stops[sym] = None
                    self.position_directions[sym] = 0
                    continue
                else:
                    new_stop = cont_price + atr_val * self.stop_atr_mult
                    if stop is None or new_stop < stop:
                        self.trailing_stops[sym] = new_stop

            # ===== ENTRY LOGIC =====
            if is_flat:
                go_long = cont_price >= entry_high
                go_short = cont_price <= entry_low

                if not go_long and not go_short:
                    continue

                direction = 1 if go_long else -1

                # --- Risk limits ---
                sector = self.ticker_sector.get(ticker, "unknown")
                # Max 3 positions per sector
                if sector_risk.get(sector, 0) >= 3:
                    continue
                # Max 12 total positions (out of 18 markets)
                if total_positions >= 12:
                    continue

                # --- Position sizing using ATR% method ---
                stop_distance_dollar = real_atr_dollar * self.stop_atr_mult
                if stop_distance_dollar <= 0:
                    continue

                budget = equity * self.risk_per_market
                contracts = int(budget / stop_distance_dollar)

                # Hard cap: max 5 contracts per market
                contracts = min(contracts, 5)

                if contracts <= 0:
                    # Even 1 contract may be too risky based on ATR - allow if budget is close
                    # Try 1 contract with a relaxed check
                    one_contract_risk = real_atr_dollar * self.stop_atr_mult
                    if one_contract_risk <= equity * self.risk_per_market * 2.0:
                        contracts = 1
                    else:
                        continue

                qty = contracts * direction
                self.MarketOrder(mapped, qty, tag=f"{'L' if direction>0 else 'S'} {ticker} x{contracts}")

                # Update tracking (stops in continuous scale)
                if direction == 1:
                    self.trailing_stops[sym] = cont_price - atr_val * self.stop_atr_mult
                else:
                    self.trailing_stops[sym] = cont_price + atr_val * self.stop_atr_mult
                self.position_directions[sym] = direction
                sector_risk[sector] = sector_risk.get(sector, 0) + 1
                total_positions += 1
