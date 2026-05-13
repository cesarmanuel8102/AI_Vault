# region imports
from AlgorithmImports import *
# endregion


class CTATrendFollowingV2_4(QCAlgorithm):
    """
    CTA Trend Following V2.4 - Trailing Stop Only Exit + 18 Markets
    =================================================================
    V2.3 showed 39% win rate but P/L ratio of only 1.09 (needs ~2.5).
    Diagnosis: Donchian 20d exit cuts winners too early.
    
    Fix: Exit ONLY via ATR trailing stop (no Donchian exit).
    This lets trends run much longer, increasing profit/loss ratio.
    
    Also: wider stop (4x ATR) to give trends more room.
    """

    def Initialize(self):
        self.start_year = int(self.GetParameter("start_year", 2010))
        self.end_year = int(self.GetParameter("end_year", 2020))
        end_month = int(self.GetParameter("end_month", 12))

        self.SetStartDate(self.start_year, 1, 1)
        self.SetEndDate(self.end_year, end_month, 28)
        self.SetCash(1000000)

        self.SetBrokerageModel(BrokerageName.InteractiveBrokersBrokerage, AccountType.Margin)

        self.entry_period = int(self.GetParameter("entry_period", 55))
        self.atr_period = int(self.GetParameter("atr_period", 20))
        self.stop_atr_mult = float(self.GetParameter("stop_atr_mult", 4.0))
        self.risk_per_market = float(self.GetParameter("risk_per_market", 0.005))

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
        self.high_windows = {}
        self.low_windows = {}
        self.trailing_stops = {}

        window_size = self.entry_period + 1

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
            self.high_windows[sym] = RollingWindow[float](window_size)
            self.low_windows[sym] = RollingWindow[float](window_size)
            self.trailing_stops[sym] = None

        self.SetWarmUp(timedelta(days=int(self.entry_period * 2.5)))

    def _get_entry_channel(self, sym):
        """Get highest high and lowest low of PREVIOUS entry_period bars."""
        hw = self.high_windows[sym]
        lw = self.low_windows[sym]
        if hw.Count < self.entry_period + 1 or lw.Count < self.entry_period + 1:
            return None, None
        highest = max(hw[i] for i in range(1, self.entry_period + 1))
        lowest = min(lw[i] for i in range(1, self.entry_period + 1))
        return highest, lowest

    def OnData(self, slice):
        if self.IsWarmingUp:
            return

        equity = self.Portfolio.TotalPortfolioValue
        if equity <= 0:
            return

        # Rollovers
        for symbol, changed_event in slice.SymbolChangedEvents.items():
            old_s = changed_event.OldSymbol
            new_s = changed_event.NewSymbol
            qty = self.Portfolio[old_s].Quantity
            if qty != 0:
                self.Liquidate(old_s, tag="Roll out")
                self.MarketOrder(new_s, qty, tag="Roll in")

        # Update rolling windows
        for ticker in self.future_tickers:
            sym = self.futures[ticker].Symbol
            if sym in self.Securities:
                bar = self.Securities[sym]
                if bar.Price > 0:
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
            h = kvp.Value
            if h.Invested and str(h.Symbol) not in active_mapped and h.Symbol.SecurityType == SecurityType.Future:
                self.Liquidate(h.Symbol, tag="Orphan")

        # Sector counts
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

            real_price = self.Securities[mapped].Price
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

            current_qty = self.Portfolio[mapped].Quantity
            is_long = current_qty > 0
            is_short = current_qty < 0
            is_flat = current_qty == 0

            multiplier = self.Securities[mapped].SymbolProperties.ContractMultiplier
            if multiplier <= 0:
                continue

            atr_pct = atr_val / cont_price
            real_atr_dollar = atr_pct * real_price * multiplier

            # ===== EXIT: TRAILING STOP ONLY =====
            if is_long:
                stop = self.trailing_stops.get(sym)
                if stop is not None and cont_price <= stop:
                    self.Liquidate(mapped, tag=f"Stop L {ticker}")
                    self.trailing_stops[sym] = None
                    continue
                else:
                    new_stop = cont_price - atr_val * self.stop_atr_mult
                    if stop is None or new_stop > stop:
                        self.trailing_stops[sym] = new_stop

            elif is_short:
                stop = self.trailing_stops.get(sym)
                if stop is not None and cont_price >= stop:
                    self.Liquidate(mapped, tag=f"Stop S {ticker}")
                    self.trailing_stops[sym] = None
                    continue
                else:
                    new_stop = cont_price + atr_val * self.stop_atr_mult
                    if stop is None or new_stop < stop:
                        self.trailing_stops[sym] = new_stop

            # ===== ENTRY: DONCHIAN BREAKOUT =====
            if is_flat:
                entry_high, entry_low = self._get_entry_channel(sym)
                if entry_high is None:
                    continue

                go_long = cont_price > entry_high
                go_short = cont_price < entry_low

                if not go_long and not go_short:
                    continue

                direction = 1 if go_long else -1

                sector = self.ticker_sector.get(ticker, "unknown")
                if sector_risk.get(sector, 0) >= 3:
                    continue
                if total_positions >= 12:
                    continue

                stop_distance_dollar = real_atr_dollar * self.stop_atr_mult
                if stop_distance_dollar <= 0:
                    continue

                budget = equity * self.risk_per_market
                contracts = int(budget / stop_distance_dollar)
                contracts = min(contracts, 5)

                if contracts <= 0:
                    if real_atr_dollar * self.stop_atr_mult <= budget * 2.0:
                        contracts = 1
                    else:
                        continue

                qty = contracts * direction
                self.MarketOrder(mapped, qty, tag=f"{'L' if direction>0 else 'S'} {ticker} x{contracts}")

                if direction == 1:
                    self.trailing_stops[sym] = cont_price - atr_val * self.stop_atr_mult
                else:
                    self.trailing_stops[sym] = cont_price + atr_val * self.stop_atr_mult
                sector_risk[sector] = sector_risk.get(sector, 0) + 1
                total_positions += 1
