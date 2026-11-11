from AlgorithmImports import *
from collections import deque
from datetime import timedelta


class YoelOptionsDirect20261025(QCAlgorithm):
    """Direct option expression of the frozen close-continuation signal."""

    TICKERS = [
        "AAPL", "AMZN", "COIN", "DIA", "GLD", "IWM", "META", "NFLX",
        "NIO", "QQQ", "SPY", "TSLA", "USO", "XPEV", "LI",
    ]

    def initialize(self):
        self.set_start_date(int(self.get_parameter("start_year") or 2022), 1, 1)
        self.set_end_date(int(self.get_parameter("end_year") or 2025), int(self.get_parameter("end_month") or 12), 31)
        self.set_cash(100000)
        self.set_time_zone("America/New_York")
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.MARGIN)
        self.set_benchmark("SPY")
        self.default_order_properties.time_in_force = TimeInForce.GOOD_TIL_CANCELED

        self.use_reinforcement = str(self.get_parameter("reinforcement") or "false").lower() == "true"
        self.equities = {}
        self.bars = {}
        self.shock_history = {}
        self.pending_signals = {}
        self.pending_contracts = {}
        self.positions = {}
        self.order_context = {}
        self.signal_count = 0
        self.selection_skips = 0
        self.quote_skips = 0
        self.entry_count = 0
        self.target_exits = 0
        self.time_exits = 0
        self.reinforcement_count = 0
        self.closed_count = 0

        for ticker in self.TICKERS:
            security = self.add_equity(ticker, Resolution.MINUTE, data_normalization_mode=DataNormalizationMode.RAW)
            security.set_fee_model(InteractiveBrokersFeeModel())
            symbol = security.symbol
            self.equities[ticker] = symbol
            self.bars[symbol] = deque(maxlen=60)
            self.shock_history[symbol] = deque(maxlen=5)
            self.consolidate(symbol, Resolution.DAILY, lambda bar, selected=symbol: self._on_daily_bar(selected, bar))

        self.set_warm_up(60, Resolution.DAILY)
        self.schedule.on(self.date_rules.every_day("SPY"), self.time_rules.before_market_close("SPY", 5), self._manage_session_age)

    @staticmethod
    def _true_range(bar, previous_close):
        return max(float(bar.high - bar.low), abs(float(bar.high) - previous_close), abs(float(bar.low) - previous_close))

    def _on_daily_bar(self, symbol, bar):
        history = self.bars[symbol]
        if len(history) >= 40:
            prior_closes = [float(item.close) for item in history]
            previous_close = prior_closes[-1]
            true_ranges = []
            for index in range(len(history) - 14, len(history)):
                item = history[index]
                true_ranges.append(self._true_range(item, float(history[index - 1].close)))
            atr = sum(true_ranges) / len(true_ranges)
            gap = float(bar.open) - previous_close
            gap_atr = gap / atr if atr > 0 else 0.0
            gap_pct = float(bar.open) / previous_close - 1.0
            direction = 1 if gap > 0 else -1
            sma20 = sum(prior_closes[-20:]) / 20
            sma40 = sum(prior_closes[-40:]) / 40
            recent = list(history)[-20:]
            average_volume = sum(float(item.volume) for item in recent) / 20
            average_dollar_volume = sum(float(item.close) * float(item.volume) for item in recent) / 20
            trend_ok = sma20 > sma40 and previous_close > sma40 if direction == 1 else sma20 < sma40 and previous_close < sma40
            relative_volume = float(bar.volume) / average_volume if average_volume else 0
            directional_close = direction * (float(bar.close) / float(bar.open) - 1)
            no_recent_shock = all(abs(value) < 1.25 for value in self.shock_history[symbol])
            liquid = previous_close >= 5 and average_dollar_volume >= 20_000_000
            ticker = symbol.value
            no_exposure = not any(position["ticker"] == ticker for position in self.positions.values())

            if (not self.is_warming_up and liquid and abs(gap_pct) >= 0.005 and abs(gap_atr) >= 1.25
                    and no_recent_shock and trend_ok and relative_volume >= 1.20 and directional_close > 0
                    and no_exposure and ticker not in self.pending_signals and ticker not in self.pending_contracts
                    and len(self.positions) < 10):
                self.pending_signals[ticker] = {"direction": direction, "signal_date": self.time.date()}
                self.signal_count += 1
            self.shock_history[symbol].append(gap_atr)
        history.append(bar)

    def on_data(self, data):
        for split in data.splits.values():
            symbol = split.symbol
            if symbol in self.bars and split.split_factor != 1:
                self.bars[symbol].clear()
                self.shock_history[symbol].clear()
        if self.is_warming_up:
            return
        self._subscribe_pending_signals()
        self._enter_quoted_contracts()
        self._consider_reinforcements()

    def _subscribe_pending_signals(self):
        for ticker, signal in list(self.pending_signals.items()):
            if self.time.date() <= signal["signal_date"]:
                continue
            underlying = self.equities[ticker]
            if not self.is_market_open(underlying):
                continue
            contracts = self.option_chain_provider.get_option_contract_list(underlying, self.time)
            desired_right = OptionRight.CALL if signal["direction"] > 0 else OptionRight.PUT
            spot = float(self.securities[underlying].price)
            eligible = []
            for contract in contracts:
                dte = (contract.id.date.date() - self.time.date()).days
                strike = float(contract.id.strike_price)
                otm = strike > spot if desired_right == OptionRight.CALL else strike < spot
                if contract.id.option_right == desired_right and 2 <= dte <= 10 and otm:
                    eligible.append(contract)
            if not eligible:
                self.selection_skips += 1
                self.pending_signals.pop(ticker, None)
                continue
            if desired_right == OptionRight.CALL:
                selected = min(eligible, key=lambda item: (item.id.date, float(item.id.strike_price)))
            else:
                selected = min(eligible, key=lambda item: (item.id.date, -float(item.id.strike_price)))
            security = self.add_option_contract(selected, Resolution.MINUTE)
            security.set_fee_model(InteractiveBrokersFeeModel())
            security.set_slippage_model(ConstantSlippageModel(0.01))
            self.pending_contracts[selected] = {
                "ticker": ticker,
                "direction": signal["direction"],
                "subscribed_at": self.time,
            }
            self.pending_signals.pop(ticker, None)

    def _enter_quoted_contracts(self):
        for contract, context in list(self.pending_contracts.items()):
            security = self.securities[contract]
            ask = float(security.ask_price)
            bid = float(security.bid_price)
            if ask <= 0 or bid < 0 or ask < bid:
                if self.time - context["subscribed_at"] > timedelta(minutes=30):
                    self.quote_skips += 1
                    self.pending_contracts.pop(contract, None)
                continue
            quantity = int((self.portfolio.total_portfolio_value * 0.02) // (ask * 100))
            if quantity < 1:
                self.quote_skips += 1
                self.pending_contracts.pop(contract, None)
                continue
            tag = f"ENTRY|{context['ticker']}|{context['direction']}"
            ticket = self.market_order(contract, quantity, tag=tag)
            self.order_context[ticket.order_id] = {"kind": "ENTRY", "contract": contract, **context}
            self.pending_contracts.pop(contract, None)

    def _place_target(self, contract, position):
        target = round(position["average_price"] * 1.35, 2)
        ticket = self.limit_order(contract, -position["quantity"], target, tag=f"TARGET|{position['ticker']}|{target:.2f}")
        position["target_order_id"] = ticket.order_id
        self.order_context[ticket.order_id] = {"kind": "TARGET", "contract": contract}

    def _consider_reinforcements(self):
        if not self.use_reinforcement:
            return
        for contract, position in list(self.positions.items()):
            if position["reinforced"] or position["closing"]:
                continue
            ask = float(self.securities[contract].ask_price)
            if ask <= 0 or ask > position["initial_price"] * 0.20:
                continue
            original_outlay = position["initial_quantity"] * position["initial_price"] * 100
            quantity = int(original_outlay // (ask * 100))
            if quantity < 1:
                continue
            position["reinforced"] = True
            self.transactions.cancel_order(position["target_order_id"])
            ticket = self.market_order(contract, quantity, tag=f"REINFORCE|{position['ticker']}")
            self.order_context[ticket.order_id] = {"kind": "REINFORCE", "contract": contract}

    def _manage_session_age(self):
        for contract, position in list(self.positions.items()):
            if position["closing"]:
                continue
            position["sessions"] += 1
            dte = (contract.id.date.date() - self.time.date()).days
            if position["sessions"] < 3 and dte > 1:
                continue
            position["closing"] = True
            self.transactions.cancel_order(position["target_order_id"])
            quantity = int(self.portfolio[contract].quantity)
            if quantity <= 0:
                continue
            ticket = self.market_order(contract, -quantity, tag=f"TIME_EXIT|{position['ticker']}|S{position['sessions']}|DTE{dte}")
            self.order_context[ticket.order_id] = {"kind": "TIME_EXIT", "contract": contract}

    def on_order_event(self, order_event):
        if order_event.status != OrderStatus.FILLED:
            return
        context = self.order_context.get(order_event.order_id)
        if context is None:
            order = self.transactions.get_order_by_id(order_event.order_id)
            parts = (order.tag or "").split("|")
            context = {"kind": parts[0], "contract": order_event.symbol}
            if len(parts) > 1:
                context["ticker"] = parts[1]
            if len(parts) > 2 and parts[0] == "ENTRY":
                context["direction"] = int(parts[2])
        contract = context["contract"]
        kind = context["kind"]
        fill_quantity = int(order_event.fill_quantity)
        fill_price = float(order_event.fill_price)

        if kind == "ENTRY" and fill_quantity > 0:
            ticker = context.get("ticker", contract.underlying.value)
            self.positions[contract] = {
                "ticker": ticker, "direction": context.get("direction", 1),
                "initial_quantity": fill_quantity, "initial_price": fill_price,
                "quantity": fill_quantity, "average_price": fill_price,
                "sessions": 0, "reinforced": False, "closing": False,
                "target_order_id": None,
            }
            self.entry_count += 1
            self._place_target(contract, self.positions[contract])
            return

        if kind == "REINFORCE" and fill_quantity > 0 and contract in self.positions:
            position = self.positions[contract]
            old_cost = position["quantity"] * position["average_price"]
            new_quantity = position["quantity"] + fill_quantity
            position["average_price"] = (old_cost + fill_quantity * fill_price) / new_quantity
            position["quantity"] = new_quantity
            self.reinforcement_count += 1
            self._place_target(contract, position)
            return

        if fill_quantity < 0 and kind in {"TARGET", "TIME_EXIT"} and self.portfolio[contract].quantity == 0:
            if kind == "TARGET":
                self.target_exits += 1
            else:
                self.time_exits += 1
            self.closed_count += 1
            position = self.positions.pop(contract, None)
            ticker = position["ticker"] if position else contract.underlying.value
            self.debug(f"TRADE_CLOSED|{ticker}|{contract}|{kind}|{fill_price:.4f}|{self.time}")

    def on_end_of_algorithm(self):
        self.set_runtime_statistic("Variant", "REINFORCEMENT" if self.use_reinforcement else "BASE")
        self.set_runtime_statistic("Signals", str(self.signal_count))
        self.set_runtime_statistic("Selection Skips", str(self.selection_skips))
        self.set_runtime_statistic("Quote Skips", str(self.quote_skips))
        self.set_runtime_statistic("Entries", str(self.entry_count))
        self.set_runtime_statistic("Closed", str(self.closed_count))
        self.set_runtime_statistic("Target Exits", str(self.target_exits))
        self.set_runtime_statistic("Time Exits", str(self.time_exits))
        self.set_runtime_statistic("Reinforcements", str(self.reinforcement_count))

