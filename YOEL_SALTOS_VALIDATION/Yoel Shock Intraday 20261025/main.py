from AlgorithmImports import *
from collections import deque
from datetime import time


class YoelShockIntraday20261025(QCAlgorithm):
    """Frozen OOS test of 30-minute confirmation or rejection after a gap shock."""

    def initialize(self):
        self.set_start_date(2022, 1, 1)
        self.set_end_date(2025, 12, 31)
        self.set_cash(100000)
        self.set_time_zone("America/New_York")
        self.set_brokerage_model(
            BrokerageName.INTERACTIVE_BROKERS_BROKERAGE,
            AccountType.MARGIN,
        )
        self.family = (self.get_parameter("family") or "OPENING_CONTINUATION").upper()
        if self.family not in ("OPENING_CONTINUATION", "OPENING_FADE"):
            raise ValueError("family must be OPENING_CONTINUATION or OPENING_FADE")
        self.set_benchmark("SPY")

        tickers = {
            "TSLA", "AAPL", "AMZN", "NFLX", "META", "COIN", "NIO", "XPEV", "LI",
            "SPY", "IWM", "QQQ", "DIA", "GLD", "USO", "MSFT", "GOOG", "NVDA",
            "AMD", "AVGO", "JPM", "BAC", "WMT", "COST", "HD", "UNH", "JNJ",
            "XOM", "CVX", "CAT", "BA", "DIS", "TLT", "XLF", "XLE", "XBI",
            "XLK", "XLV", "EEM", "SMH",
        }
        self.symbols = []
        self.daily_bars = {}
        self.shock_history = {}
        self.opening = {}
        self.candidates = {}
        self.pending_entries = {}
        self.active = set()
        self.exit_in_progress = set()
        self.signal_count = 0
        self.confirmed_count = 0
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
            self.daily_bars[symbol] = deque(maxlen=60)
            self.shock_history[symbol] = deque(maxlen=5)
            self.consolidate(
                symbol,
                Resolution.DAILY,
                lambda bar, selected=symbol: self._on_daily_bar(selected, bar),
            )

        self.set_warm_up(60, Resolution.DAILY)
        self.schedule.on(
            self.date_rules.every_day("SPY"),
            self.time_rules.after_market_open("SPY", 31),
            self._evaluate_opening,
        )
        self.schedule.on(
            self.date_rules.every_day("SPY"),
            self.time_rules.before_market_close("SPY", 5),
            self._close_positions,
        )

    @staticmethod
    def _true_range(bar, previous_close):
        return max(
            float(bar.high - bar.low),
            abs(float(bar.high) - previous_close),
            abs(float(bar.low) - previous_close),
        )

    def _context(self, symbol):
        history = self.daily_bars[symbol]
        if len(history) < 40:
            return None
        closes = [float(item.close) for item in history]
        true_ranges = []
        for index in range(len(history) - 14, len(history)):
            true_ranges.append(
                self._true_range(history[index], float(history[index - 1].close))
            )
        return {
            "previous_close": closes[-1],
            "atr": sum(true_ranges) / len(true_ranges),
            "sma20": sum(closes[-20:]) / 20,
            "sma40": sum(closes[-40:]) / 40,
            "average_volume": sum(float(item.volume) for item in list(history)[-20:]) / 20,
            "average_dollar_volume": sum(
                float(item.close) * float(item.volume) for item in list(history)[-20:]
            ) / 20,
        }

    def on_data(self, data):
        if self.is_warming_up:
            return
        for symbol in self.symbols:
            bar = data.bars.get(symbol)
            if not bar:
                continue
            if bar.end_time.hour == 9 and bar.end_time.minute == 31:
                self._capture_open(symbol, bar)
            session = self.opening.get(symbol)
            if session and bar.end_time.date() == session["date"] and bar.end_time.time() <= time(10, 1):
                session["high"] = max(session["high"], float(bar.high))
                session["low"] = min(session["low"], float(bar.low))
                session["last"] = float(bar.close)
                session["volume"] += float(bar.volume)

    def _capture_open(self, symbol, bar):
        context = self._context(symbol)
        if not context or context["atr"] <= 0:
            return
        opening_price = float(bar.open)
        gap = opening_price - context["previous_close"]
        direction = 1 if gap > 0 else -1
        gap_atr = abs(gap) / context["atr"]
        gap_pct = abs(opening_price / context["previous_close"] - 1.0)
        trend_ok = (
            context["sma20"] > context["sma40"] and context["previous_close"] > context["sma40"]
            if direction == 1
            else context["sma20"] < context["sma40"] and context["previous_close"] < context["sma40"]
        )
        valid = (
            context["previous_close"] >= 5
            and context["average_dollar_volume"] >= 20_000_000
            and gap_pct >= 0.005
            and gap_atr >= 1.25
            and trend_ok
            and all(abs(value) < 1.25 for value in self.shock_history[symbol])
        )
        self.opening[symbol] = {
            "date": bar.end_time.date(),
            "open": opening_price,
            "high": float(bar.high),
            "low": float(bar.low),
            "last": float(bar.close),
            "volume": 0.0,
        }
        if valid:
            self.candidates[symbol] = {
                "direction": direction,
                "atr": context["atr"],
                "previous_close": context["previous_close"],
                "average_volume": context["average_volume"],
            }
            self.signal_count += 1

    def _evaluate_opening(self):
        for symbol, candidate in list(self.candidates.items()):
            session = self.opening.get(symbol)
            if not session or session["date"] != self.time.date():
                continue
            opening_range = session["high"] - session["low"]
            if opening_range <= 0:
                continue
            gap_direction = candidate["direction"]
            directional_move = gap_direction * (session["last"] / session["open"] - 1.0)
            close_location = gap_direction * (session["last"] - session["open"]) / opening_range
            volume_ok = session["volume"] >= 0.05 * candidate["average_volume"]
            if self.family == "OPENING_CONTINUATION":
                confirmed = directional_move > 0 and close_location >= 0.25 and volume_ok
                trade_direction = gap_direction
            else:
                confirmed = directional_move < 0 and close_location <= -0.25 and volume_ok
                trade_direction = -gap_direction
            if (
                confirmed
                and not self.portfolio[symbol].invested
                and symbol not in self.pending_entries
                and len(self.pending_entries) + len(self.active) < 10
            ):
                atr = candidate["atr"]
                price = self.securities[symbol].price
                risk_quantity = int((self.portfolio.total_portfolio_value * 0.005) // atr)
                notional_quantity = int((self.portfolio.total_portfolio_value * 0.10) // price)
                quantity = max(0, min(risk_quantity, notional_quantity)) * trade_direction
                if quantity:
                    # Intraday market orders can fill synchronously. Publish the
                    # ATR context before submitting so on_order_event can consume it.
                    self.pending_entries[symbol] = {"order_id": None, "atr": atr}
                    ticket = self.market_order(symbol, quantity, tag="OPENING_ENTRY")
                    if symbol in self.pending_entries:
                        self.pending_entries[symbol]["order_id"] = ticket.order_id
                    self.confirmed_count += 1
        self.candidates.clear()

    def _close_positions(self):
        if self.is_warming_up:
            return
        for symbol in list(self.active):
            if self.portfolio[symbol].invested and symbol not in self.exit_in_progress:
                self.transactions.cancel_open_orders(symbol)
                self.exit_in_progress.add(symbol)
                self.market_order(
                    symbol,
                    -self.portfolio[symbol].quantity,
                    tag="CLOSE_SAME_DAY",
                )

    def _on_daily_bar(self, symbol, bar):
        history = self.daily_bars[symbol]
        if len(history) >= 14:
            previous_close = float(history[-1].close)
            true_ranges = []
            for index in range(len(history) - 14, len(history)):
                true_ranges.append(
                    self._true_range(history[index], float(history[index - 1].close))
                )
            atr = sum(true_ranges) / len(true_ranges)
            gap_atr = (float(bar.open) - previous_close) / atr if atr > 0 else 0.0
            self.shock_history[symbol].append(gap_atr)
        history.append(bar)

    def on_order_event(self, order_event):
        symbol = order_event.symbol
        if order_event.status in (OrderStatus.INVALID, OrderStatus.CANCELED):
            pending = self.pending_entries.get(symbol)
            if pending and pending["order_id"] in (None, order_event.order_id):
                self.pending_entries.pop(symbol, None)
            return
        if order_event.status != OrderStatus.FILLED:
            return
        order = self.transactions.get_order_by_id(order_event.order_id)
        tag = order.tag or ""
        if tag == "OPENING_ENTRY":
            pending = self.pending_entries.pop(symbol, None)
            if pending is None:
                raise RuntimeError(f"missing entry context for {symbol}")
            atr = pending["atr"]
            quantity = order_event.fill_quantity
            direction = 1 if quantity > 0 else -1
            self.active.add(symbol)
            self.stop_market_order(
                symbol, -quantity, order_event.fill_price - direction * atr, tag="STOP_1_ATR"
            )
            self.limit_order(
                symbol, -quantity, order_event.fill_price + direction * 2.0 * atr, tag="TARGET_2_ATR"
            )
            self.entry_count += 1
            return
        if tag in ("STOP_1_ATR", "TARGET_2_ATR", "CLOSE_SAME_DAY"):
            self.transactions.cancel_open_orders(symbol)
            self.active.discard(symbol)
            self.exit_in_progress.discard(symbol)
            self.closed_count += 1

    def on_end_of_algorithm(self):
        self.set_runtime_statistic("Yoel Family", self.family)
        self.set_runtime_statistic("Yoel Threshold ATR", "1.25")
        self.set_runtime_statistic("Yoel Signals", str(self.signal_count))
        self.set_runtime_statistic("Yoel Confirmed", str(self.confirmed_count))
        self.set_runtime_statistic("Yoel Entries", str(self.entry_count))
        self.set_runtime_statistic("Yoel Closed", str(self.closed_count))
