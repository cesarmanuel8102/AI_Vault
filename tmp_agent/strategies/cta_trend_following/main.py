# region imports
from AlgorithmImports import *
# endregion


class CTATrendFollowingV1(QCAlgorithm):
    """
    CTA Trend Following V1.8 - IB Futures - All 18 Markets
    ========================================================
    Based on working 5-market version.
    Added: portfolio sanity check, emergency liquidation, per-market notional cap.
    """

    def Initialize(self):
        self.start_year = int(self.GetParameter("start_year", 2010))
        self.end_year = int(self.GetParameter("end_year", 2020))
        end_month = int(self.GetParameter("end_month", 12))

        self.SetStartDate(self.start_year, 1, 1)
        self.SetEndDate(self.end_year, end_month, 28)
        self.SetCash(1000000)

        self.SetBrokerageModel(BrokerageName.InteractiveBrokersBrokerage, AccountType.Margin)

        self.fast_period = int(self.GetParameter("fast_period", 50))
        self.slow_period = int(self.GetParameter("slow_period", 200))
        self.atr_period = int(self.GetParameter("atr_period", 20))
        self.stop_atr_mult = float(self.GetParameter("stop_atr_mult", 2.0))
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

        self.futures = {}
        self.indicators = {}

        for ticker in self.future_tickers:
            future = self.AddFuture(ticker, Resolution.Daily,
                                     dataMappingMode=DataMappingMode.OpenInterest,
                                     dataNormalizationMode=DataNormalizationMode.BackwardsRatio,
                                     contractDepthOffset=0)
            future.SetFilter(lambda u: u.FrontMonth())
            self.futures[ticker] = future

            sym = future.Symbol
            self.indicators[sym] = {
                "ema": self.EMA(sym, self.fast_period, Resolution.Daily),
                "sma": self.SMA(sym, self.slow_period, Resolution.Daily),
                "atr": self.ATR(sym, self.atr_period, MovingAverageType.Simple, Resolution.Daily),
            }

        self.SetWarmUp(timedelta(days=self.slow_period * 2))
        self._initial_cash = 1000000
        self._emergency_triggered = False

    def OnData(self, slice):
        if self.IsWarmingUp:
            return

        equity = self.Portfolio.TotalPortfolioValue

        # EMERGENCY: If equity drops below 50% of initial, liquidate everything
        if equity < self._initial_cash * 0.50 and not self._emergency_triggered:
            self._emergency_triggered = True
            self.Liquidate(tag="EMERGENCY LIQUIDATE")
            self.Debug(f"EMERGENCY: equity=${equity:,.0f} < 50% of initial. All positions closed.")
            return

        if self._emergency_triggered:
            return  # Stay flat after emergency

        # Handle rollovers
        for symbol, changed_event in slice.SymbolChangedEvents.items():
            old_s = changed_event.OldSymbol
            new_s = changed_event.NewSymbol
            qty = self.Portfolio[old_s].Quantity
            if qty != 0:
                self.Liquidate(old_s, tag="Roll out")
                self.MarketOrder(new_s, qty, tag="Roll in")

        if equity <= 0:
            return

        # SANITY CHECK: Count total absolute holdings value
        total_holdings = 0
        for kvp in self.Portfolio:
            h = kvp.Value
            if h.Invested:
                total_holdings += abs(h.HoldingsValue)

        # If gross exposure > 300% of equity, something is wrong - liquidate all
        if total_holdings > equity * 3.0 and equity > 0:
            self.Liquidate(tag="EXPOSURE LIMIT")
            self.Debug(f"EXPOSURE LIMIT: holdings=${total_holdings:,.0f} > 3x equity=${equity:,.0f}")
            return

        for ticker in self.future_tickers:
            future = self.futures[ticker]
            sym = future.Symbol
            mapped = future.Mapped

            if mapped is None:
                continue
            if mapped not in self.Securities:
                continue

            price = self.Securities[mapped].Price
            if price <= 0:
                continue

            inds = self.indicators[sym]
            if not all(inds[k].IsReady for k in ["ema", "sma", "atr"]):
                continue

            ema_val = inds["ema"].Current.Value
            sma_val = inds["sma"].Current.Value
            atr_val = inds["atr"].Current.Value

            if atr_val <= 0 or sma_val <= 0:
                continue

            desired = 0
            if ema_val > sma_val:
                desired = 1
            elif ema_val < sma_val:
                desired = -1

            current_qty = self.Portfolio[mapped].Quantity
            current_dir = 1 if current_qty > 0 else (-1 if current_qty < 0 else 0)

            if desired != current_dir:
                if current_dir != 0:
                    self.Liquidate(mapped, tag=f"Exit {ticker}")

                if desired != 0:
                    multiplier = self.Securities[mapped].SymbolProperties.ContractMultiplier
                    if multiplier <= 0:
                        continue

                    stop_distance = atr_val * self.stop_atr_mult
                    dollar_risk = stop_distance * multiplier
                    if dollar_risk <= 0:
                        continue

                    budget = equity * self.risk_per_market
                    contracts = int(budget / dollar_risk)
                    contracts = min(contracts, 10)

                    # Skip if sizing is 0
                    if contracts <= 0:
                        continue

                    # Per-market notional cap: max 15% of equity
                    notional = contracts * price * multiplier
                    if notional > equity * 0.15:
                        contracts = max(1, int(equity * 0.15 / (price * multiplier)))
                        if contracts <= 0:
                            continue

                    qty = contracts * desired
                    self.MarketOrder(mapped, qty, tag=f"{'L' if desired>0 else 'S'} {ticker} x{contracts}")
