# region imports
from AlgorithmImports import *
# endregion


class CTATrendFollowingV2(QCAlgorithm):
    """
    CTA Trend Following V2.0 - Donchian Channel Breakout (Turtle Trading)
    ======================================================================
    Entry: Price breaks above/below Donchian Channel (entry_period highs/lows)
    Exit: Price breaks opposite Donchian Channel (exit_period) OR ATR trailing stop
    Markets: 5 working futures (ES, GC, ZN, ZC, 6E)
    
    Parameters (5 max per contract):
    1. entry_period (20) - Donchian entry channel lookback
    2. exit_period (10) - Donchian exit channel lookback  
    3. atr_period (20) - ATR lookback for sizing & stops
    4. stop_atr_mult (2.0) - ATR multiplier for trailing stop
    5. risk_per_market (0.01) - Fraction of equity risked per market
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
        self.entry_period = int(self.GetParameter("entry_period", 20))
        self.exit_period = int(self.GetParameter("exit_period", 10))
        self.atr_period = int(self.GetParameter("atr_period", 20))
        self.stop_atr_mult = float(self.GetParameter("stop_atr_mult", 2.0))
        self.risk_per_market = float(self.GetParameter("risk_per_market", 0.01))

        # Only the 5 markets that work correctly
        self.future_tickers = [
            Futures.Indices.SP500EMini,      # ES - $50/pt
            Futures.Metals.Gold,             # GC - $100/pt
            Futures.Financials.Y10TreasuryNote,  # ZN - $1000/pt
            Futures.Grains.Corn,             # ZC - $50/pt
            Futures.Currencies.EUR,          # 6E - $125,000/pt
        ]

        self.futures = {}
        self.indicators = {}
        self.trailing_stops = {}  # sym -> stop price

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

        warmup_days = int(self.entry_period * 2.5)
        self.SetWarmUp(timedelta(days=warmup_days))

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

            multiplier = self.Securities[mapped].SymbolProperties.ContractMultiplier
            if multiplier <= 0:
                continue

            # ===== EXIT LOGIC =====
            if is_long:
                # Exit long: price drops below exit_low OR trailing stop hit
                stop = self.trailing_stops.get(sym)
                exit_signal = price <= exit_low
                stop_hit = stop is not None and price <= stop

                if exit_signal or stop_hit:
                    self.Liquidate(mapped, tag=f"Exit L {ticker}")
                    self.trailing_stops[sym] = None
                    continue
                else:
                    # Update trailing stop: highest close - ATR * mult
                    new_stop = price - atr_val * self.stop_atr_mult
                    if stop is None or new_stop > stop:
                        self.trailing_stops[sym] = new_stop

            elif is_short:
                # Exit short: price rises above exit_high OR trailing stop hit
                stop = self.trailing_stops.get(sym)
                exit_signal = price >= exit_high
                stop_hit = stop is not None and price >= stop

                if exit_signal or stop_hit:
                    self.Liquidate(mapped, tag=f"Exit S {ticker}")
                    self.trailing_stops[sym] = None
                    continue
                else:
                    # Update trailing stop: lowest close + ATR * mult
                    new_stop = price + atr_val * self.stop_atr_mult
                    if stop is None or new_stop < stop:
                        self.trailing_stops[sym] = new_stop

            # ===== ENTRY LOGIC =====
            if is_flat:
                # Donchian breakout entry
                go_long = price >= entry_high
                go_short = price <= entry_low

                if not go_long and not go_short:
                    continue

                direction = 1 if go_long else -1

                # Position sizing: risk 1% of equity per market
                stop_distance = atr_val * self.stop_atr_mult
                dollar_risk_per_contract = stop_distance * multiplier

                if dollar_risk_per_contract <= 0:
                    continue

                budget = equity * self.risk_per_market
                contracts = int(budget / dollar_risk_per_contract)

                # Cap at 10 contracts per market
                contracts = min(contracts, 10)

                if contracts <= 0:
                    continue

                # Notional cap: max 20% of equity per market
                notional = contracts * price * multiplier
                if notional > equity * 0.20:
                    contracts = max(1, int(equity * 0.20 / (price * multiplier)))
                    if contracts <= 0:
                        continue

                qty = contracts * direction
                self.MarketOrder(mapped, qty, tag=f"{'L' if direction>0 else 'S'} {ticker} x{contracts}")

                # Set initial trailing stop
                if direction == 1:
                    self.trailing_stops[sym] = price - stop_distance
                else:
                    self.trailing_stops[sym] = price + stop_distance
