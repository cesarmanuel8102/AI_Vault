from AlgorithmImports import *
from collections import deque
from datetime import date, timedelta
from math import sqrt

from first_rebound_core import select_first_rebound


class YoelFirstReboundOptions20261025(QCAlgorithm):
    TICKERS = ["AAPL", "AMZN", "COIN", "DIA", "GLD", "IWM", "META", "NFLX", "NIO", "QQQ", "SPY", "TSLA", "USO", "XPEV", "LI"]

    def initialize(self):
        start_year = int(self.get_parameter("start_year") or 2020)
        end_year = int(self.get_parameter("end_year") or 2025)
        self.set_start_date(start_year, 1, 1)
        self.set_end_date(end_year, 12, 31)
        self.set_cash(100000)
        self.set_time_zone("America/New_York")
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.MARGIN)
        self.set_benchmark("SPY")
        self.backtest_cutoff = date(end_year, 12, 29)
        self.vehicle = str(self.get_parameter("vehicle") or "long_option").lower()
        if self.vehicle not in {"long_option", "debit_spread"}:
            raise ValueError("vehicle must be long_option or debit_spread")

        self.symbols = {}
        self.hourly = {}
        self.daily = {}
        self.regimes = {}
        self.used_levels = {}
        self.pending_signals = {}
        self.pending_contracts = {}
        self.positions = {}
        self.signals = self.entries = self.closed = 0
        self.target_exits = self.stop_exits = self.time_exits = 0
        self.selection_skips = self.quote_skips = 0
        self.entry_rejects = self.close_rejects = 0
        self.period_signals = {20: 0, 40: 0, 100: 0, 200: 0}

        for ticker in self.TICKERS:
            security = self.add_equity(ticker, Resolution.MINUTE, data_normalization_mode=DataNormalizationMode.RAW)
            security.set_fee_model(InteractiveBrokersFeeModel())
            symbol = security.symbol
            self.symbols[ticker] = symbol
            self.hourly[symbol] = deque(maxlen=220)
            self.daily[symbol] = deque(maxlen=50)
            self.regimes[symbol] = 0
            self.used_levels[symbol] = set()
            consolidator = TradeBarConsolidator(timedelta(hours=1), start_time=timedelta(hours=9, minutes=30))
            consolidator.data_consolidated += lambda sender, bar, selected=symbol: self._on_hourly(selected, bar)
            self.subscription_manager.add_consolidator(symbol, consolidator)
            self.consolidate(symbol, Resolution.DAILY, lambda bar, selected=symbol: self.daily[selected].append(bar))

        self.set_warm_up(timedelta(days=120))
        self.schedule.on(self.date_rules.every_day("SPY"), self.time_rules.before_market_close("SPY", 5), self._age_positions)
        self.schedule.on(self.date_rules.every_day("SPY"), self.time_rules.before_market_close("SPY", 15), self._flatten_at_backtest_boundary)

    @staticmethod
    def _sma(values, period):
        return sum(values[-period:]) / period

    @staticmethod
    def _std(values, period):
        sample = values[-period:]
        mean = sum(sample) / period
        return sqrt(sum((value - mean) ** 2 for value in sample) / period)

    @staticmethod
    def _atr(bars, period=14):
        values = []
        for index in range(len(bars) - period, len(bars)):
            bar = bars[index]
            previous = float(bars[index - 1].close)
            values.append(max(float(bar.high - bar.low), abs(float(bar.high) - previous), abs(float(bar.low) - previous)))
        return sum(values) / len(values)

    def _daily_direction(self, symbol):
        bars = self.daily[symbol]
        if len(bars) < 40:
            return 0
        closes = [float(item.close) for item in bars]
        sma20, sma40 = self._sma(closes, 20), self._sma(closes, 40)
        return 1 if closes[-1] > sma20 > sma40 else (-1 if closes[-1] < sma20 < sma40 else 0)

    def _on_hourly(self, symbol, bar):
        bars = self.hourly[symbol]
        bars.append(bar)
        if self.is_warming_up or self.time.date() >= self.backtest_cutoff or len(bars) < 202 or len(self.daily[symbol]) < 40:
            return
        closes = [float(item.close) for item in bars]
        levels = {period: self._sma(closes, period) for period in (20, 40, 100, 200)}
        close = closes[-1]
        direction = 1 if close > levels[20] > levels[40] > levels[100] > levels[200] else (-1 if close < levels[20] < levels[40] < levels[100] < levels[200] else 0)
        if direction != self.regimes[symbol]:
            self.regimes[symbol] = direction
            self.used_levels[symbol].clear()
        ticker = symbol.value
        if direction == 0 or ticker in self.positions or ticker in self.pending_signals or ticker in self.pending_contracts:
            return
        if len(self.positions) + len(self.pending_contracts) >= 10:
            return
        atr = self._atr(list(bars))
        previous = bars[-2]
        avg_volume = sum(float(item.volume) for item in list(bars)[-21:-1]) / 20
        signal = select_first_rebound(
            direction=direction, daily_direction=self._daily_direction(symbol),
            open=float(bar.open), high=float(bar.high), low=float(bar.low), close=close,
            previous_low=float(previous.low), previous_high=float(previous.high), atr=atr,
            bb_mid=levels[20], bb_mid_previous=self._sma(closes[:-1], 20),
            bb_width=4 * self._std(closes, 20), bb_width_previous=4 * self._std(closes[:-1], 20),
            relative_volume=float(bar.volume) / avg_volume if avg_volume else 0,
            levels=levels, used_levels=self.used_levels[symbol],
        )
        if signal is None:
            return
        period, level = signal["period"], signal["level"]
        self.used_levels[symbol].add(period)
        self.signals += 1
        self.period_signals[period] += 1
        self.pending_signals[ticker] = {
            "underlying": symbol, "direction": direction, "period": period,
            "stop": level - direction * 0.5 * atr, "created": self.time,
        }

    def on_data(self, data):
        for split in data.splits.values():
            symbol = split.symbol
            if symbol in self.hourly and split.split_factor != 1:
                self.hourly[symbol].clear(); self.daily[symbol].clear(); self.used_levels[symbol].clear(); self.regimes[symbol] = 0
        if self.is_warming_up:
            return
        if self.time.date() >= self.backtest_cutoff:
            self.pending_signals.clear()
            self.pending_contracts.clear()
            self._manage_positions()
            return
        self._subscribe_contracts()
        self._enter_ready_contracts()
        self._manage_positions()

    def _subscribe_contracts(self):
        for ticker, signal in list(self.pending_signals.items()):
            underlying = signal["underlying"]
            spot = float(self.securities[underlying].price)
            if spot <= 0 or not self.is_market_open(underlying):
                continue
            right = OptionRight.CALL if signal["direction"] > 0 else OptionRight.PUT
            contracts = self.option_chain_provider.get_option_contract_list(underlying, self.time)
            eligible = [item for item in contracts if item.id.option_right == right and 21 <= (item.id.date.date() - self.time.date()).days <= 45]
            if not eligible:
                self.selection_skips += 1; self.pending_signals.pop(ticker, None); continue
            expiry = min(item.id.date for item in eligible)
            same_expiry = [item for item in eligible if item.id.date == expiry]
            itm = [item for item in same_expiry if (item.id.strike_price <= spot if right == OptionRight.CALL else item.id.strike_price >= spot)]
            if not itm:
                self.selection_skips += 1; self.pending_signals.pop(ticker, None); continue
            long_leg = max(itm, key=lambda item: item.id.strike_price) if right == OptionRight.CALL else min(itm, key=lambda item: item.id.strike_price)
            short_leg = None
            if self.vehicle == "debit_spread":
                otm = [item for item in same_expiry if (item.id.strike_price > spot if right == OptionRight.CALL else item.id.strike_price < spot)]
                if not otm:
                    self.selection_skips += 1; self.pending_signals.pop(ticker, None); continue
                short_leg = min(otm, key=lambda item: item.id.strike_price) if right == OptionRight.CALL else max(otm, key=lambda item: item.id.strike_price)
            for contract in [long_leg, short_leg]:
                if contract is not None:
                    sec = self.add_option_contract(contract, Resolution.MINUTE)
                    sec.set_fee_model(InteractiveBrokersFeeModel())
                    sec.set_slippage_model(ConstantSlippageModel(0.01))
            self.pending_contracts[ticker] = {**signal, "long": long_leg, "short": short_leg, "subscribed": self.time}
            self.pending_signals.pop(ticker, None)

    def _enter_ready_contracts(self):
        for ticker, context in list(self.pending_contracts.items()):
            long_sec = self.securities[context["long"]]
            long_ask, long_bid = float(long_sec.ask_price), float(long_sec.bid_price)
            if long_ask <= 0 or long_bid < 0:
                if self.time - context["subscribed"] > timedelta(minutes=30):
                    self.quote_skips += 1; self.pending_contracts.pop(ticker, None)
                continue
            short_bid = 0.0
            if context["short"] is not None:
                short_sec = self.securities[context["short"]]
                short_bid = float(short_sec.bid_price)
                if short_bid <= 0 or float(short_sec.ask_price) < short_bid:
                    continue
            debit = long_ask - short_bid
            quantity = int((self.portfolio.total_portfolio_value * 0.01) // (debit * 100)) if debit > 0 else 0
            if quantity < 1:
                self.quote_skips += 1; self.pending_contracts.pop(ticker, None); continue
            if context["short"] is None:
                tickets = [self.market_order(context["long"], quantity, tag=f"ENTRY_LONG|{ticker}|MA{context['period']}")]
            else:
                legs = [Leg.create(context["long"], 1), Leg.create(context["short"], -1)]
                tickets = self.combo_market_order(legs, quantity, tag=f"ENTRY_SPREAD|{ticker}|MA{context['period']}")
            if not tickets or any(ticket.status != OrderStatus.FILLED for ticket in tickets):
                self.entry_rejects += 1
                for ticket in tickets:
                    if ticket.status not in (OrderStatus.FILLED, OrderStatus.CANCELED, OrderStatus.INVALID):
                        ticket.cancel("ENTRY_NOT_ATOMIC")
                self.pending_contracts.pop(ticker, None)
                continue
            fills = {ticket.symbol: float(ticket.average_fill_price) for ticket in tickets}
            long_fill = fills[context["long"]]
            short_fill = fills.get(context["short"], 0.0)
            actual_debit = long_fill - short_fill
            if actual_debit <= 0:
                if context["short"] is None:
                    self.market_order(context["long"], -quantity, tag=f"ENTRY_ABORT|{ticker}")
                else:
                    legs = [Leg.create(context["long"], 1), Leg.create(context["short"], -1)]
                    self.combo_market_order(legs, -quantity, tag=f"ENTRY_ABORT|{ticker}")
                self.quote_skips += 1; self.pending_contracts.pop(ticker, None); continue
            self.positions[ticker] = {**context, "quantity": quantity, "entry_debit": actual_debit, "sessions": 0, "closing": False}
            self.entries += 1
            self.pending_contracts.pop(ticker, None)

    def _manage_positions(self):
        for ticker, position in list(self.positions.items()):
            if position["closing"]:
                continue
            underlying_price = float(self.securities[position["underlying"]].price)
            long_bid = float(self.securities[position["long"]].bid_price)
            if long_bid < 0:
                continue
            liquidation = long_bid
            if position["short"] is not None:
                short_ask = float(self.securities[position["short"]].ask_price)
                if short_ask <= 0:
                    continue
                liquidation -= short_ask
            pnl = liquidation / position["entry_debit"] - 1 if position["entry_debit"] > 0 else -1
            invalid = underlying_price <= position["stop"] if position["direction"] > 0 else underlying_price >= position["stop"]
            dte = (position["long"].id.date.date() - self.time.date()).days
            if pnl >= 0.30:
                self._close(ticker, "TARGET")
            elif invalid:
                self._close(ticker, "STOP")
            elif dte <= 7:
                self._close(ticker, "TIME_EXIT")

    def _close(self, ticker, reason):
        position = self.positions.get(ticker)
        if position is None or position["closing"]:
            return
        position["closing"] = True
        quantity = position["quantity"]
        if position["short"] is None:
            tickets = [self.market_order(position["long"], -quantity, tag=f"{reason}_LONG|{ticker}|MA{position['period']}")]
        else:
            legs = [Leg.create(position["long"], 1), Leg.create(position["short"], -1)]
            tickets = self.combo_market_order(legs, -quantity, tag=f"{reason}_SPREAD|{ticker}|MA{position['period']}")
        if not tickets or any(ticket.status != OrderStatus.FILLED for ticket in tickets):
            self.close_rejects += 1
            position["closing"] = False
            return
        self.positions.pop(ticker, None)
        self.closed += 1
        if reason == "TARGET": self.target_exits += 1
        elif reason == "STOP": self.stop_exits += 1
        else: self.time_exits += 1

    def _age_positions(self):
        for ticker, position in list(self.positions.items()):
            position["sessions"] += 1
            if position["sessions"] >= 5:
                self._close(ticker, "TIME_EXIT")

    def _flatten_at_backtest_boundary(self):
        if self.time.date() < self.backtest_cutoff:
            return
        self.pending_signals.clear()
        self.pending_contracts.clear()
        for ticker in list(self.positions):
            self._close(ticker, "TIME_EXIT")
        self.liquidate(tag="BACKTEST_BOUNDARY_FLATTEN")
        self.positions.clear()

    def on_end_of_algorithm(self):
        self.set_runtime_statistic("Vehicle", self.vehicle.upper())
        self.set_runtime_statistic("Signals", str(self.signals)); self.set_runtime_statistic("Entries", str(self.entries)); self.set_runtime_statistic("Closed", str(self.closed))
        self.set_runtime_statistic("Target Exits", str(self.target_exits)); self.set_runtime_statistic("Stop Exits", str(self.stop_exits)); self.set_runtime_statistic("Time Exits", str(self.time_exits))
        self.set_runtime_statistic("Selection Skips", str(self.selection_skips)); self.set_runtime_statistic("Quote Skips", str(self.quote_skips))
        self.set_runtime_statistic("Entry Rejects", str(self.entry_rejects)); self.set_runtime_statistic("Close Rejects", str(self.close_rejects))
        for period, count in self.period_signals.items(): self.set_runtime_statistic(f"MA{period} Signals", str(count))

