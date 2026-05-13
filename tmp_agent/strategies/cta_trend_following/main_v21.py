# region imports
from AlgorithmImports import *
# endregion


class CTATrendFollowingV2_1(QCAlgorithm):
    """
    CTA Trend Following V2.1 - Donchian 55/20 + SMA200 Trend Filter
    =================================================================
    Entry: Price breaks Donchian 55-day channel AND price is on the right side of SMA200
    Exit: Price breaks opposite Donchian 20-day channel OR ATR trailing stop (3x ATR)
    Markets: 5 working futures (ES, GC, ZN, ZC, 6E)
    
    Key improvements over V2.0:
    - Longer entry channel (55d vs 20d) reduces whipsaws
    - SMA200 trend filter eliminates counter-trend entries
    - Wider trailing stop (3x ATR vs 2x) gives trends room to breathe
    
    Parameters (5 max per contract):
    1. entry_period (55) - Donchian entry channel
    2. exit_period (20) - Donchian exit channel
    3. atr_period (20) - ATR for sizing & stops
    4. stop_atr_mult (3.0) - ATR trailing stop multiplier
    5. risk_per_market (0.01) - Risk fraction per market
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
        self.risk_per_market = float(self.GetParameter("risk_per_market", 0.01))

        # Only the 5 markets that work correctly
        self.future_tickers = [
            Futures.Indices.SP500EMini,          # ES - $50/pt
            Futures.Metals.Gold,                 # GC - $100/pt
            Futures.Financials.Y10TreasuryNote,  # ZN - $1000/pt
            Futures.Grains.Corn,                 # ZC - $50/pt
            Futures.Currencies.EUR,              # 6E - $125,000/pt
        ]

        self.futures = {}
        self.indicators = {}
        self.trailing_stops = {}  # sym -> stop price
        self.entry_prices = {}   # sym -> entry price (for tracking)

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
                "sma200": self.SMA(sym, 200, Resolution.Daily),
            }
            self.trailing_stops[sym] = None
            self.entry_prices[sym] = None

        warmup_days = 250  # Need 200 for SMA200 + buffer
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
            required_keys = ["entry_high", "entry_low", "exit_high", "exit_low", "atr", "sma200"]
            if not all(inds[k].IsReady for k in required_keys):
                continue

            entry_high = inds["entry_high"].Current.Value
            entry_low = inds["entry_low"].Current.Value
            exit_high = inds["exit_high"].Current.Value
            exit_low = inds["exit_low"].Current.Value
            atr_val = inds["atr"].Current.Value
            sma200 = inds["sma200"].Current.Value

            if atr_val <= 0 or sma200 <= 0:
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
                stop = self.trailing_stops.get(sym)
                exit_signal = price <= exit_low
                stop_hit = stop is not None and price <= stop

                if exit_signal or stop_hit:
                    self.Liquidate(mapped, tag=f"Exit L {ticker}")
                    self.trailing_stops[sym] = None
                    self.entry_prices[sym] = None
                    continue
                else:
                    # Update trailing stop (only ratchets up)
                    new_stop = price - atr_val * self.stop_atr_mult
                    if stop is None or new_stop > stop:
                        self.trailing_stops[sym] = new_stop

            elif is_short:
                stop = self.trailing_stops.get(sym)
                exit_signal = price >= exit_high
                stop_hit = stop is not None and price >= stop

                if exit_signal or stop_hit:
                    self.Liquidate(mapped, tag=f"Exit S {ticker}")
                    self.trailing_stops[sym] = None
                    self.entry_prices[sym] = None
                    continue
                else:
                    # Update trailing stop (only ratchets down)
                    new_stop = price + atr_val * self.stop_atr_mult
                    if stop is None or new_stop < stop:
                        self.trailing_stops[sym] = new_stop

            # ===== ENTRY LOGIC (with trend filter) =====
            if is_flat:
                # Trend filter: only go long above SMA200, only go short below SMA200
                go_long = price >= entry_high and price > sma200
                go_short = price <= entry_low and price < sma200

                if not go_long and not go_short:
                    continue

                direction = 1 if go_long else -1

                # Position sizing
                stop_distance = atr_val * self.stop_atr_mult
                dollar_risk_per_contract = stop_distance * multiplier

                if dollar_risk_per_contract <= 0:
                    continue

                budget = equity * self.risk_per_market
                contracts = int(budget / dollar_risk_per_contract)
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

                # Set initial trailing stop and record entry
                if direction == 1:
                    self.trailing_stops[sym] = price - stop_distance
                else:
                    self.trailing_stops[sym] = price + stop_distance
                self.entry_prices[sym] = price
