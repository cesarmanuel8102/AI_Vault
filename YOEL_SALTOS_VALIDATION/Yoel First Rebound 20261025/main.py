from AlgorithmImports import *
from collections import deque
from datetime import timedelta
from math import sqrt

from first_rebound_core import select_first_rebound


class YoelFirstRebound20261025(QCAlgorithm):
    TICKERS = [
        "AAPL", "AMZN", "COIN", "DIA", "GLD", "IWM", "META", "NFLX",
        "NIO", "QQQ", "SPY", "TSLA", "USO", "XPEV", "LI",
    ]

    def initialize(self):
        self.set_start_date(int(self.get_parameter("start_year") or 2020), 1, 1)
        self.set_end_date(int(self.get_parameter("end_year") or 2025), int(self.get_parameter("end_month") or 12), 31)
        self.set_cash(100000)
        self.set_time_zone("America/New_York")
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.MARGIN)
        self.set_benchmark("SPY")

        self.symbols = {}
        self.hourly = {}
        self.daily = {}
        self.regimes = {}
        self.used_levels = {}
        self.pending_entries = {}
        self.positions = {}
        self.exit_in_progress = set()
        self.signals = 0
        self.entries = 0
        self.closed = 0
        self.target_exits = 0
        self.stop_exits = 0
        self.time_exits = 0
        self.period_signals = {20: 0, 40: 0, 100: 0, 200: 0}

        for ticker in self.TICKERS:
            security = self.add_equity(ticker, Resolution.MINUTE, data_normalization_mode=DataNormalizationMode.RAW)
            security.set_fee_model(InteractiveBrokersFeeModel())
            security.set_slippage_model(ConstantSlippageModel(0.0005))
            symbol = security.symbol
            self.symbols[ticker] = symbol
            self.hourly[symbol] = deque(maxlen=220)
            self.daily[symbol] = deque(maxlen=50)
            self.regimes[symbol] = 0
            self.used_levels[symbol] = set()

            hourly = TradeBarConsolidator(timedelta(hours=1), start_time=timedelta(hours=9, minutes=30))
            hourly.data_consolidated += lambda sender, bar, selected=symbol: self._on_hourly(selected, bar)
            self.subscription_manager.add_consolidator(symbol, hourly)
            self.consolidate(symbol, Resolution.DAILY, lambda bar, selected=symbol: self._on_daily(selected, bar))

        self.set_warm_up(timedelta(days=120))
        self.schedule.on(self.date_rules.every_day("SPY"), self.time_rules.before_market_close("SPY", 5), self._time_exits)

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
        ranges = []
        for index in range(len(bars) - period, len(bars)):
            bar = bars[index]
            previous_close = float(bars[index - 1].close)
            ranges.append(max(float(bar.high - bar.low), abs(float(bar.high) - previous_close), abs(float(bar.low) - previous_close)))
        return sum(ranges) / len(ranges)

    def _on_daily(self, symbol, bar):
        self.daily[symbol].append(bar)

    def _daily_direction(self, symbol):
        bars = self.daily[symbol]
        if len(bars) < 40:
            return 0
        closes = [float(item.close) for item in bars]
        sma20 = self._sma(closes, 20)
        sma40 = self._sma(closes, 40)
        close = closes[-1]
        if close > sma20 > sma40:
            return 1
        if close < sma20 < sma40:
            return -1
        return 0

    def _on_hourly(self, symbol, bar):
        bars = self.hourly[symbol]
        bars.append(bar)
        if self.is_warming_up or len(bars) < 202 or len(self.daily[symbol]) < 40:
            return
        closes = [float(item.close) for item in bars]
        levels = {period: self._sma(closes, period) for period in (20, 40, 100, 200)}
        close = closes[-1]
        if close > levels[20] > levels[40] > levels[100] > levels[200]:
            direction = 1
        elif close < levels[20] < levels[40] < levels[100] < levels[200]:
            direction = -1
        else:
            direction = 0
        if direction != self.regimes[symbol]:
            self.regimes[symbol] = direction
            self.used_levels[symbol].clear()
        if direction == 0 or self.portfolio[symbol].invested or symbol in self.pending_entries:
            return
        if len(self.positions) + len(self.pending_entries) >= 10:
            return

        atr = self._atr(list(bars))
        bb_mid = levels[20]
        bb_mid_previous = self._sma(closes[:-1], 20)
        bb_width = 4 * self._std(closes, 20)
        bb_width_previous = 4 * self._std(closes[:-1], 20)
        previous = bars[-2]
        avg_volume = sum(float(item.volume) for item in list(bars)[-21:-1]) / 20
        relative_volume = float(bar.volume) / avg_volume if avg_volume else 0
        signal = select_first_rebound(
            direction=direction,
            daily_direction=self._daily_direction(symbol),
            open=float(bar.open), high=float(bar.high), low=float(bar.low), close=close,
            previous_low=float(previous.low), previous_high=float(previous.high),
            atr=atr, bb_mid=bb_mid, bb_mid_previous=bb_mid_previous,
            bb_width=bb_width, bb_width_previous=bb_width_previous,
            relative_volume=relative_volume, levels=levels,
            used_levels=self.used_levels[symbol],
        )
        if signal is None:
            return
        period = signal["period"]
        level = signal["level"]
        stop_price = level - direction * 0.5 * atr
        risk_per_share = abs(close - stop_price)
        risk_quantity = int((self.portfolio.total_portfolio_value * 0.005) // risk_per_share) if risk_per_share > 0 else 0
        notional_quantity = int((self.portfolio.total_portfolio_value * 0.10) // close)
        quantity = min(risk_quantity, notional_quantity)
        self.used_levels[symbol].add(period)
        self.signals += 1
        self.period_signals[period] += 1
        if quantity < 1:
            return
        self.pending_entries[symbol] = {
            "order_id": None,
            "stop": stop_price,
            "direction": direction,
            "period": period,
        }
        ticket = self.market_order(symbol, direction * quantity, tag=f"ENTRY|{symbol.value}|{direction}|MA{period}")
        if symbol in self.pending_entries:
            self.pending_entries[symbol]["order_id"] = ticket.order_id

    def on_data(self, data):
        for split in data.splits.values():
            symbol = split.symbol
            if symbol in self.hourly and split.split_factor != 1:
                self.hourly[symbol].clear()
                self.daily[symbol].clear()
                self.regimes[symbol] = 0
                self.used_levels[symbol].clear()

    def on_order_event(self, event):
        if event.status != OrderStatus.FILLED:
            return
        symbol = event.symbol
        order = self.transactions.get_order_by_id(event.order_id)
        tag = order.tag or ""
        kind = tag.split("|")[0]
        if kind == "ENTRY":
            pending = self.pending_entries.pop(symbol, None)
            if pending is None:
                return
            direction = pending["direction"]
            quantity = int(event.fill_quantity)
            risk = abs(float(event.fill_price) - pending["stop"])
            target_price = float(event.fill_price) + direction * 2.0 * risk
            stop_ticket = self.stop_market_order(symbol, -quantity, pending["stop"], tag=f"STOP|{symbol.value}|MA{pending['period']}")
            target_ticket = self.limit_order(symbol, -quantity, target_price, tag=f"TARGET|{symbol.value}|MA{pending['period']}")
            self.positions[symbol] = {
                "stop_id": stop_ticket.order_id, "target_id": target_ticket.order_id,
                "sessions": 0, "period": pending["period"], "direction": direction,
            }
            self.entries += 1
            return
        if kind in {"STOP", "TARGET", "TIME_EXIT"} and symbol in self.positions:
            if self.portfolio[symbol].quantity != 0:
                return
            self.transactions.cancel_open_orders(symbol)
            self.positions.pop(symbol, None)
            self.exit_in_progress.discard(symbol)
            self.closed += 1
            if kind == "STOP":
                self.stop_exits += 1
            elif kind == "TARGET":
                self.target_exits += 1
            else:
                self.time_exits += 1

    def _time_exits(self):
        if self.is_warming_up:
            return
        for symbol, position in list(self.positions.items()):
            if symbol in self.exit_in_progress or not self.portfolio[symbol].invested:
                continue
            position["sessions"] += 1
            if position["sessions"] < 5:
                continue
            self.exit_in_progress.add(symbol)
            self.transactions.cancel_open_orders(symbol)
            quantity = int(self.portfolio[symbol].quantity)
            if quantity:
                self.market_order(symbol, -quantity, tag=f"TIME_EXIT|{symbol.value}|MA{position['period']}")

    def on_end_of_algorithm(self):
        self.set_runtime_statistic("Vehicle", "STOCK")
        self.set_runtime_statistic("Signals", str(self.signals))
        self.set_runtime_statistic("Entries", str(self.entries))
        self.set_runtime_statistic("Closed", str(self.closed))
        self.set_runtime_statistic("Target Exits", str(self.target_exits))
        self.set_runtime_statistic("Stop Exits", str(self.stop_exits))
        self.set_runtime_statistic("Time Exits", str(self.time_exits))
        for period, count in self.period_signals.items():
            self.set_runtime_statistic(f"MA{period} Signals", str(count))

