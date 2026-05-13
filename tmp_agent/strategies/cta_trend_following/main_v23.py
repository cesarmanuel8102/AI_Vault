# region imports
from AlgorithmImports import *
# endregion


class CTATrendFollowingV2_3(QCAlgorithm):
    """
    CTA Trend Following V2.3 - Donchian Breakout Fixed + 18 Markets
    =================================================================
    FIX: Use RollingWindow for Donchian channels to exclude current bar.
    The MAX/MIN indicators include today's price, so "breakout" was always true
    on new highs/lows. This caused 87% loss rate in V2.2.
    
    Now: channel = highest high / lowest low of PREVIOUS N bars (excluding today).
    Entry: today's close > previous N-bar high = genuine breakout.
    Exit: today's close < previous M-bar low (for longs).
    
    ATR% sizing fix from V2.2 retained (no position explosion).
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

        # All 18 markets
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

        # Sector groupings for risk limits
        self.sectors = {
            "indices": [Futures.Indices.SP500EMini, Futures.Indices.NASDAQ100EMini, Futures.Indices.Dow30EMini],
            "energy": [Futures.Energies.CrudeOilWTI, Futures.Energies.NaturalGas],
            "metals": [Futures.Metals.Gold, Futures.Metals.Silver, Futures.Metals.Copper],
            "grains": [Futures.Grains.Corn, Futures.Grains.Soybeans, Futures.Grains.Wheat],
            "rates": [Futures.Financials.Y10TreasuryNote, Futures.Financials.Y30TreasuryBond],
            "fx": [Futures.Currencies.EUR, Futures.Currencies.JPY, Futures.Currencies.GBP,
                   Futures.Currencies.AUD, Futures.Currencies.CAD],
        }
        self.ticker_sector = {}
        for sector, tickers in self.sectors.items():
            for t in tickers:
                self.ticker_sector[t] = sector

        self.futures = {}
        self.indicators = {}
        self.price_windows = {}  # sym -> RollingWindow of closes
        self.high_windows = {}   # sym -> RollingWindow of highs
        self.low_windows = {}    # sym -> RollingWindow of lows
        self.trailing_stops = {}
        self.position_directions = {}

        window_size = self.entry_period + 1  # +1 so we have entry_period bars EXCLUDING today

        for ticker in self.future_tickers:
            future = self.AddFuture(ticker, Resolution.Daily,
                                     dataMappingMode=DataMappingMode.OpenInterest,
                                     dataNormalizationMode=DataNormalizationMode.BackwardsRatio,
                                     contractDepthOffset=0)
            future.SetFilter(lambda u: u.FrontMonth())
            self.futures[ticker] = future

            sym = future.Symbol
            self.indicators[sym] = {
                "atr": self.ATR(sym, self.atr_period, MovingAverageType.Simple, Resolution.Daily),
            }
            # RollingWindows to compute Donchian excluding current bar
            self.high_windows[sym] = RollingWindow[float](window_size)
            self.low_windows[sym] = RollingWindow[float](window_size)
            self.trailing_stops[sym] = None
            self.position_directions[sym] = 0

        self.SetWarmUp(timedelta(days=int(self.entry_period * 2.5)))

    def _get_channel(self, sym, period):
        """Get highest high and lowest low of the PREVIOUS 'period' bars (excluding today)."""
        hw = self.high_windows[sym]
        lw = self.low_windows[sym]
        if hw.Count < period + 1 or lw.Count < period + 1:
            return None, None
        # Index 0 = today (most recent), so previous bars are 1..period
        highest = max(hw[i] for i in range(1, period + 1))
        lowest = min(lw[i] for i in range(1, period + 1))
        return highest, lowest

    def OnData(self, slice):
        if self.IsWarmingUp:
            return

        equity = self.Portfolio.TotalPortfolioValue
        if equity <= 0:
            return

        # Handle rollovers
        for symbol, changed_event in slice.SymbolChangedEvents.items():
            old_s = changed_event.OldSymbol
            new_s = changed_event.NewSymbol
            qty = self.Portfolio[old_s].Quantity
            if qty != 0:
                self.Liquidate(old_s, tag="Roll out")
                self.MarketOrder(new_s, qty, tag="Roll in")

        # Update rolling windows with today's data from continuous contracts
        for ticker in self.future_tickers:
            sym = self.futures[ticker].Symbol
            if sym in self.Securities:
                bar = self.Securities[sym]
                if bar.Price > 0:
                    # For continuous contracts, High/Low may not be directly available
                    # Use Close as proxy for the rolling window
                    # Actually, TradeBar has High and Low
                    if hasattr(bar, 'High') and bar.High > 0:
                        self.high_windows[sym].Add(bar.High)
                        self.low_windows[sym].Add(bar.Low)
                    else:
                        self.high_windows[sym].Add(bar.Price)
                        self.low_windows[sym].Add(bar.Price)

        # Orphan cleanup
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

        # Count sector allocation
        sector_risk = {s: 0 for s in self.sectors}
        total_positions = 0
        for ticker in self.future_tickers:
            mapped = self.futures[ticker].Mapped
            if mapped is not None and self.Portfolio[mapped].Invested:
                sector = self.ticker_sector.get(ticker, "unknown")
                sector_risk[sector] = sector_risk.get(sector, 0) + 1
                total_positions += 1

        for ticker in self.future_tickers:
            future = self.futures[ticker]
            sym = future.Symbol
            mapped = future.Mapped

            if mapped is None or mapped not in self.Securities:
                continue

            sec = self.Securities[mapped]
            real_price = sec.Price
            if real_price <= 0:
                continue

            cont_price = self.Securities[sym].Price if sym in self.Securities else 0
            if cont_price <= 0:
                continue

            atr_ind = self.indicators[sym]["atr"]
            if not atr_ind.IsReady:
                continue
            atr_val = atr_ind.Current.Value
            if atr_val <= 0:
                continue

            # Donchian channels excluding current bar
            entry_high, entry_low = self._get_channel(sym, self.entry_period)
            exit_high, exit_low = self._get_channel(sym, self.exit_period)

            if entry_high is None or exit_high is None:
                continue

            current_qty = self.Portfolio[mapped].Quantity
            is_long = current_qty > 0
            is_short = current_qty < 0
            is_flat = current_qty == 0

            multiplier = sec.SymbolProperties.ContractMultiplier
            if multiplier <= 0:
                continue

            # ATR% sizing
            atr_pct = atr_val / cont_price
            real_atr_dollar = atr_pct * real_price * multiplier

            # ===== EXIT LOGIC =====
            if is_long:
                stop = self.trailing_stops.get(sym)
                exit_signal = cont_price < exit_low  # Close below previous N-bar low
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
                exit_signal = cont_price > exit_high  # Close above previous N-bar high
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
                # Genuine breakout: close > previous N-bar high (not including today)
                go_long = cont_price > entry_high
                go_short = cont_price < entry_low

                if not go_long and not go_short:
                    continue

                direction = 1 if go_long else -1

                # Risk limits
                sector = self.ticker_sector.get(ticker, "unknown")
                if sector_risk.get(sector, 0) >= 3:
                    continue
                if total_positions >= 12:
                    continue

                # Position sizing
                stop_distance_dollar = real_atr_dollar * self.stop_atr_mult
                if stop_distance_dollar <= 0:
                    continue

                budget = equity * self.risk_per_market
                contracts = int(budget / stop_distance_dollar)
                contracts = min(contracts, 5)

                if contracts <= 0:
                    # Allow 1 contract if risk is within 2x budget
                    one_risk = real_atr_dollar * self.stop_atr_mult
                    if one_risk <= budget * 2.0:
                        contracts = 1
                    else:
                        continue

                qty = contracts * direction
                self.MarketOrder(mapped, qty, tag=f"{'L' if direction>0 else 'S'} {ticker} x{contracts}")

                if direction == 1:
                    self.trailing_stops[sym] = cont_price - atr_val * self.stop_atr_mult
                else:
                    self.trailing_stops[sym] = cont_price + atr_val * self.stop_atr_mult
                self.position_directions[sym] = direction
                sector_risk[sector] = sector_risk.get(sector, 0) + 1
                total_positions += 1
