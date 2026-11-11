from AlgorithmImports import *
from collections import deque


class YoelShockOperability20261025(QCAlgorithm):
    """OOS reproduction of the pre-selected post-shock continuation rule."""

    def initialize(self):
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2025, 12, 31)
        self.set_cash(100000)
        self.set_time_zone("America/New_York")
        self.set_brokerage_model(
            BrokerageName.INTERACTIVE_BROKERS_BROKERAGE,
            AccountType.MARGIN,
        )
        self.set_benchmark("SPY")

        tickers = {
            "TSLA", "AAPL", "AMZN", "NFLX", "META", "COIN", "NIO", "XPEV", "LI",
            "SPY", "IWM", "QQQ", "DIA", "GLD", "USO", "MSFT", "GOOG", "NVDA",
            "AMD", "AVGO", "JPM", "BAC", "WMT", "COST", "HD", "UNH", "JNJ",
            "XOM", "CVX", "CAT", "BA", "DIS", "TLT", "XLF", "XLE", "XBI",
            "XLK", "XLV", "EEM", "SMH",
        }
        self.symbols = []
        self.bars = {}
        self.shock_history = {}
        self.pending_entries = {}
        self.protective_orders = {}
        self.held_sessions = {}
        self.exit_in_progress = set()
        self.signal_count = 0
        self.entry_count = 0
        self.closed_count = 0

        for ticker in sorted(tickers):
            security = self.add_equity(
                ticker,
                Resolution.MINUTE,
                data_normalization_mode=DataNormalizationMode.ADJUSTED,
            )
            security.set_fee_model(InteractiveBrokersFeeModel())
            security.set_slippage_model(ConstantSlippageModel(0.0005))
            symbol = security.symbol
            self.symbols.append(symbol)
            self.bars[symbol] = deque(maxlen=60)
            self.shock_history[symbol] = deque(maxlen=5)
            self.consolidate(
                symbol,
                Resolution.DAILY,
                lambda bar, selected=symbol: self._on_daily_bar(selected, bar),
            )

        self.set_warm_up(60, Resolution.DAILY)
        self.schedule.on(
            self.date_rules.every_day("SPY"),
            self.time_rules.before_market_close("SPY", 5),
            self._time_exits,
        )

    @staticmethod
    def _true_range(bar, previous_close):
        return max(
            float(bar.high - bar.low),
            abs(float(bar.high) - previous_close),
            abs(float(bar.low) - previous_close),
        )

    def _on_daily_bar(self, symbol, bar):
        history = self.bars[symbol]
        if len(history) >= 40:
            prior_closes = [float(item.close) for item in history]
            previous_close = prior_closes[-1]
            true_ranges = []
            for index in range(len(history) - 14, len(history)):
                item = history[index]
                item_previous_close = float(history[index - 1].close)
                true_ranges.append(self._true_range(item, item_previous_close))
            atr = sum(true_ranges) / len(true_ranges)
            gap = float(bar.open) - previous_close
            gap_atr = gap / atr if atr > 0 else 0.0
            gap_pct = float(bar.open) / previous_close - 1.0
            shock_direction = 1 if gap > 0 else -1
            sma20 = sum(prior_closes[-20:]) / 20
            sma40 = sum(prior_closes[-40:]) / 40
            average_volume = sum(float(item.volume) for item in list(history)[-20:]) / 20
            average_dollar_volume = sum(
                float(item.close) * float(item.volume) for item in list(history)[-20:]
            ) / 20
            trend_ok = (
                sma20 > sma40 and previous_close > sma40
                if shock_direction == 1
                else sma20 < sma40 and previous_close < sma40
            )
            relative_volume = float(bar.volume) / average_volume if average_volume > 0 else 0
            directional_close = shock_direction * (float(bar.close) / float(bar.open) - 1.0)
            no_recent_shock = all(abs(value) < 1.25 for value in self.shock_history[symbol])
            liquid = previous_close >= 5 and average_dollar_volume >= 20_000_000

            if (
                not self.is_warming_up
                and liquid
                and abs(gap_pct) >= 0.005
                and abs(gap_atr) >= 1.25
                and no_recent_shock
                and trend_ok
                and relative_volume >= 1.20
                and directional_close > 0
                and not self.portfolio[symbol].invested
                and symbol not in self.pending_entries
                and len(self.pending_entries) + len(self.held_sessions) < 10
            ):
                risk_quantity = int((self.portfolio.total_portfolio_value * 0.005) // atr)
                notional_quantity = int((self.portfolio.total_portfolio_value * 0.10) // float(bar.close))
                quantity = max(0, min(risk_quantity, notional_quantity)) * shock_direction
                if quantity:
                    ticket = self.market_order(symbol, quantity, tag="ENTRY_NEXT_OPEN")
                    self.pending_entries[symbol] = {
                        "order_id": ticket.order_id,
                        "atr": atr,
                    }
                    self.signal_count += 1

            self.shock_history[symbol].append(gap_atr)
        history.append(bar)

    def _time_exits(self):
        if self.is_warming_up:
            return
        for symbol in list(self.held_sessions):
            if not self.portfolio[symbol].invested:
                continue
            self.held_sessions[symbol] += 1
            if self.held_sessions[symbol] >= 3 and symbol not in self.exit_in_progress:
                self.transactions.cancel_open_orders(symbol)
                quantity = -self.portfolio[symbol].quantity
                if quantity:
                    self.exit_in_progress.add(symbol)
                    self.market_order(symbol, quantity, tag="TIME_EXIT_3_SESSIONS")

    def on_order_event(self, order_event):
        symbol = order_event.symbol
        if order_event.status in (OrderStatus.INVALID, OrderStatus.CANCELED):
            pending = self.pending_entries.get(symbol)
            if pending and pending["order_id"] == order_event.order_id:
                self.pending_entries.pop(symbol, None)
            return
        if order_event.status != OrderStatus.FILLED:
            return

        order = self.transactions.get_order_by_id(order_event.order_id)
        tag = order.tag or ""
        if tag == "ENTRY_NEXT_OPEN":
            pending = self.pending_entries.pop(symbol)
            atr = pending["atr"]
            quantity = order_event.fill_quantity
            direction = 1 if quantity > 0 else -1
            stop_price = order_event.fill_price - direction * atr
            target_price = order_event.fill_price + direction * 2.0 * atr
            stop = self.stop_market_order(symbol, -quantity, stop_price, tag="STOP_1_ATR")
            target = self.limit_order(symbol, -quantity, target_price, tag="TARGET_2_ATR")
            self.protective_orders[symbol] = (stop.order_id, target.order_id)
            self.held_sessions[symbol] = 0
            self.entry_count += 1
            return

        if tag in ("STOP_1_ATR", "TARGET_2_ATR", "TIME_EXIT_3_SESSIONS"):
            self.transactions.cancel_open_orders(symbol)
            self.protective_orders.pop(symbol, None)
            self.held_sessions.pop(symbol, None)
            self.exit_in_progress.discard(symbol)
            self.closed_count += 1

    def on_end_of_algorithm(self):
        self.set_runtime_statistic("Yoel Family", "CLOSE_CONTINUATION")
        self.set_runtime_statistic("Yoel Threshold ATR", "1.25")
        self.set_runtime_statistic("Yoel Hold Sessions", "3")
        self.set_runtime_statistic("Yoel Signals", str(self.signal_count))
        self.set_runtime_statistic("Yoel Entries", str(self.entry_count))
        self.set_runtime_statistic("Yoel Closed", str(self.closed_count))
