from AlgorithmImports import *
from collections import deque
from datetime import timedelta
import json
from math import sqrt

from first_rebound_core import select_first_rebound
from zero_dte_core import (
    adaptive_allocation_fraction,
    adverse_failure_to_launch_due,
    contract_quantity,
    contract_quantity_for_allocation,
    checkpoint_snapshot,
    entry_before_cutoff,
    failure_to_launch_due,
    friction_within_target,
    passes_causal_quality_gate,
    quality_signal,
    rank_daily_candidates,
    scale_out_quantity,
    select_contract_by_delta,
    select_expiry,
    trailing_profit_exit_due,
)


class YoelZeroDteFirstRebound20261025(QCAlgorithm):
    TICKERS = ["AAPL", "AMZN", "COIN", "DIA", "GLD", "IWM", "META", "NFLX", "NIO", "QQQ", "SPY", "TSLA", "USO", "XPEV", "LI"]

    def initialize(self):
        self.start_year = int(self.get_parameter("start_year") or 2025)
        self.end_year = int(self.get_parameter("end_year") or 2026)
        end_month, end_day = (10, 25) if self.end_year == 2026 else (12, 31)
        self.set_start_date(self.start_year, 1, 1)
        self.set_end_date(self.end_year, end_month, end_day)
        self.starting_cash = float(self.get_parameter("starting_cash") or 100000)
        self.capital_fraction = float(self.get_parameter("capital_fraction") or 0.10)
        self.adaptive_allocation = str(self.get_parameter("adaptive_allocation") or "false").lower() == "true"
        self.max_entries_per_day = int(self.get_parameter("max_entries_per_day") or 0)
        self.opening_signal_hour = int(self.get_parameter("opening_signal_hour") or -1)
        self.set_cash(self.starting_cash)
        self.set_time_zone("America/New_York")
        self.set_brokerage_model(BrokerageName.INTERACTIVE_BROKERS_BROKERAGE, AccountType.MARGIN)
        self.set_benchmark("SPY")
        self.target_delta = float(self.get_parameter("target_delta") or 0.50)
        self.target_dte = int(self.get_parameter("target_dte") or 0)
        self.entry_cutoff_hour = int(self.get_parameter("entry_cutoff_hour") or 24)
        self.candidate_limit = 20
        self.take_profit = float(self.get_parameter("take_profit") or 0.35)
        self.trailing_activation = float(self.get_parameter("trailing_activation") or 0)
        self.trailing_distance = float(self.get_parameter("trailing_distance") or 0)
        self.trailing_enabled = self.trailing_activation > 0 and self.trailing_distance > 0
        self.scale_out_fraction = float(self.get_parameter("scale_out_fraction") or 0)
        self.runner_target = float(self.get_parameter("runner_target") or 0)
        self.scale_out_trigger = float(self.get_parameter("scale_out_trigger") or 0)
        if self.scale_out_trigger <= 0:
            self.scale_out_trigger = self.take_profit
        self.scale_out_enabled = self.scale_out_fraction > 0 and self.runner_target > 0
        self.entry_profit_hurdle = (
            self.trailing_activation - self.trailing_distance
            if self.trailing_enabled
            else self.take_profit
        )
        self.max_hold_minutes = int(self.get_parameter("max_hold_minutes") or 0)
        self.failure_minutes = int(self.get_parameter("failure_minutes") or 0)
        self.failure_min_pnl = float(self.get_parameter("failure_min_pnl") or 0)
        self.failure_underlying_adverse = str(self.get_parameter("failure_underlying_adverse") or "false").lower() == "true"
        self.failure_repeat = str(self.get_parameter("failure_repeat") or "false").lower() == "true"
        self.economics_gate = str(self.get_parameter("economics_gate") or "false").lower() == "true"
        self.quality_filter = str(self.get_parameter("quality_filter") or "false").lower() == "true"
        self.causal_selector = str(self.get_parameter("causal_selector") or "false").lower() == "true"
        self.causal_thresholds = {
            "relative_volume_min": float(self.get_parameter("quality_relative_volume_min") or 0.8),
            "close_location_min": float(self.get_parameter("quality_close_location_min") or 0.0),
            "body_strength_min": float(self.get_parameter("quality_body_strength_min") or 0.0),
            "range_atr_min": float(self.get_parameter("quality_range_atr_min") or 0.0),
            "range_atr_max": float(self.get_parameter("quality_range_atr_max") or 10.0),
            "level_rejection_atr_min": float(self.get_parameter("quality_level_rejection_atr_min") or 0.0),
            "friction_max": float(self.get_parameter("quality_friction_max") or self.take_profit),
        }
        self.trace_mode = str(self.get_parameter("trace_mode") or "false").lower() == "true"
        self.trace_checkpoints = (3, 5, 10, 15, 30)
        if not 0 < self.target_delta < 1:
            raise ValueError("target_delta must be between zero and one")
        if self.target_dte < 0:
            raise ValueError("target_dte must be non-negative")
        if not 0 < self.entry_cutoff_hour <= 24:
            raise ValueError("entry_cutoff_hour must be between 1 and 24")
        if not 0 < self.capital_fraction <= 1:
            raise ValueError("capital_fraction must be between zero and one")
        if self.max_entries_per_day not in (0, 1, 2, 3):
            raise ValueError("max_entries_per_day must be between zero and three")
        if self.opening_signal_hour not in range(-1, 24):
            raise ValueError("opening_signal_hour must be -1 or an exchange hour")
        if self.take_profit <= 0:
            raise ValueError("take_profit must be positive")
        if self.trailing_enabled and self.entry_profit_hurdle <= 0:
            raise ValueError("trailing activation must exceed trailing distance")
        if self.scale_out_enabled and not 0 < self.scale_out_fraction < 1:
            raise ValueError("scale_out_fraction must be between zero and one")
        if self.scale_out_enabled and self.runner_target <= self.take_profit:
            raise ValueError("runner_target must exceed take_profit")
        if self.scale_out_enabled and self.scale_out_trigger < self.take_profit:
            raise ValueError("scale_out_trigger cannot be below take_profit")
        if self.scale_out_enabled and self.runner_target <= self.scale_out_trigger:
            raise ValueError("runner_target must exceed scale_out_trigger")
        if self.scale_out_enabled and self.trailing_enabled:
            raise ValueError("profit ladder and whole-position trailing are mutually exclusive")

        self.hourly = {}
        self.daily = {}
        self.regimes = {}
        self.used_levels = {}
        self.pending_signals = {}
        self.pending_contracts = {}
        self.positions = {}
        self.entry_dates = set()
        self.daily_entry_counts = {}
        self.daily_allocation_equity = {}
        self.signals = self.entries = self.closed = 0
        self.target_exits = self.trailing_exits = self.runner_target_exits = 0
        self.scale_outs = self.time_exits = self.failure_exits = 0
        self.quality_skips = 0
        self.causal_quality_skips = 0
        self.no_expiry_skips = self.quote_skips = 0
        self.entry_rejects = self.close_rejects = 0
        self.economics_skips = 0
        self.entry_deltas = []
        self.entry_dtes = []
        self.period_signals = {20: 0, 40: 0, 100: 0, 200: 0}

        for ticker in self.TICKERS:
            security = self.add_equity(ticker, Resolution.MINUTE, data_normalization_mode=DataNormalizationMode.RAW)
            security.set_fee_model(InteractiveBrokersFeeModel())
            symbol = security.symbol
            self.hourly[symbol] = deque(maxlen=220)
            self.daily[symbol] = deque(maxlen=50)
            self.regimes[symbol] = 0
            self.used_levels[symbol] = set()
            consolidator = TradeBarConsolidator(timedelta(hours=1), start_time=timedelta(hours=9, minutes=30))
            consolidator.data_consolidated += lambda sender, bar, selected=symbol: self._on_hourly(selected, bar)
            self.subscription_manager.add_consolidator(symbol, consolidator)
            self.consolidate(symbol, Resolution.DAILY, lambda bar, selected=symbol: self.daily[selected].append(bar))

        self.set_warm_up(timedelta(days=120))
        self.schedule.on(self.date_rules.every_day("SPY"), self.time_rules.before_market_close("SPY", 5), self._close_all)

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
        if self.is_warming_up or len(bars) < 202 or len(self.daily[symbol]) < 40:
            return
        if self.opening_signal_hour >= 0 and self.time.hour != self.opening_signal_hour:
            return
        if self.max_entries_per_day > 0 and self.daily_entry_counts.get(self.time.date(), 0) >= self.max_entries_per_day:
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
        relative_volume = float(bar.volume) / avg_volume if avg_volume else 0
        signal = select_first_rebound(
            direction=direction, daily_direction=self._daily_direction(symbol),
            open=float(bar.open), high=float(bar.high), low=float(bar.low), close=close,
            previous_low=float(previous.low), previous_high=float(previous.high), atr=atr,
            bb_mid=levels[20], bb_mid_previous=self._sma(closes[:-1], 20),
            bb_width=4 * self._std(closes, 20), bb_width_previous=4 * self._std(closes[:-1], 20),
            relative_volume=relative_volume,
            levels=levels, used_levels=self.used_levels[symbol],
        )
        if signal is None:
            return
        close_location = (
            (close - float(bar.low)) / float(bar.high - bar.low)
            if direction > 0 and bar.high > bar.low
            else (float(bar.high) - close) / float(bar.high - bar.low)
            if direction < 0 and bar.high > bar.low
            else 0
        )
        if self.quality_filter and not quality_signal(
            direction, float(bar.open), float(bar.high), float(bar.low), close, relative_volume
        ):
            self.quality_skips += 1
            return
        period = signal["period"]
        bar_range = float(bar.high - bar.low)
        body_strength = direction * (close - float(bar.open)) / bar_range if bar_range > 0 else 0
        range_atr = bar_range / atr if atr > 0 else 0
        level_rejection_atr = direction * (close - float(levels[period])) / atr if atr > 0 else 0
        self.used_levels[symbol].add(period)
        self.signals += 1
        self.period_signals[period] += 1
        self.pending_signals[ticker] = {
            "underlying": symbol,
            "direction": direction,
            "period": period,
            "created": self.time,
            "relative_volume": relative_volume,
            "close_location": close_location,
            "body_strength": body_strength,
            "range_atr": range_atr,
            "level_rejection_atr": level_rejection_atr,
            "level_price": float(levels[period]),
            "signal_low": float(bar.low),
            "signal_high": float(bar.high),
        }

    def on_data(self, data):
        for split in data.splits.values():
            symbol = split.symbol
            if symbol in self.hourly and split.split_factor != 1:
                self.hourly[symbol].clear()
                self.daily[symbol].clear()
                self.used_levels[symbol].clear()
                self.regimes[symbol] = 0
        if self.is_warming_up:
            return
        self._subscribe_contracts()
        self._enter_ready_contracts(data)
        self._manage_positions()

    def _subscribe_contracts(self):
        for ticker, signal in list(self.pending_signals.items()):
            underlying = signal["underlying"]
            spot = float(self.securities[underlying].price)
            if spot <= 0 or not self.is_market_open(underlying):
                continue
            right = OptionRight.CALL if signal["direction"] > 0 else OptionRight.PUT
            contracts = self.option_chain_provider.get_option_contract_list(underlying, self.time)
            directional = [item for item in contracts if item.id.option_right == right]
            expiry = select_expiry([item.id.date.date() for item in directional], self.time.date(), self.target_dte)
            if expiry is None:
                self.no_expiry_skips += 1
                self.pending_signals.pop(ticker, None)
                continue
            expiry_contracts = [item for item in directional if item.id.date.date() == expiry]
            candidates = sorted(
                expiry_contracts,
                key=lambda item: abs(float(item.id.strike_price) - spot),
            )[:self.candidate_limit]
            for contract in candidates:
                security = self.add_option_contract(contract, Resolution.MINUTE)
                security.set_fee_model(InteractiveBrokersFeeModel())
                security.set_slippage_model(ConstantSlippageModel(0.01))
                security.price_model = OptionPriceModels.QuantLib.crank_nicolson_fd()
            self.pending_contracts[ticker] = {**signal, "contracts": candidates, "subscribed": self.time}
            self.pending_signals.pop(ticker, None)

    def _enter_ready_contracts(self, data):
        if self.max_entries_per_day > 0 and self.daily_entry_counts.get(self.time.date(), 0) >= self.max_entries_per_day:
            for context in self.pending_contracts.values():
                self._remove_candidates(context["contracts"])
            self.pending_contracts.clear()
            self.pending_signals.clear()
            return
        contract_data_by_symbol = {
            contract_data.symbol: contract_data
            for chain in data.option_chains.values()
            for contract_data in chain
        }
        ranking_candidates = [
            {
                "ticker": ticker,
                "relative_volume": context["relative_volume"],
                "close_location": context["close_location"],
                "body_strength": context["body_strength"],
                "range_atr": context["range_atr"],
                "level_rejection_atr": context["level_rejection_atr"],
                "friction": 0.0,
            }
            for ticker, context in self.pending_contracts.items()
        ]
        ranked = rank_daily_candidates(ranking_candidates)
        for candidate_index, candidate in enumerate(ranked):
            ticker = candidate["ticker"]
            context = self.pending_contracts.get(ticker)
            if context is None:
                continue
            if not entry_before_cutoff(self.time.hour, self.entry_cutoff_hour):
                self._remove_candidates(context["contracts"])
                self.pending_contracts.pop(ticker, None)
                continue
            candidates = []
            for contract in context["contracts"]:
                contract_data = contract_data_by_symbol.get(contract)
                delta = float(contract_data.greeks.delta) if contract_data is not None else None
                candidates.append({
                    "symbol": contract,
                    "delta": delta,
                    "bid": float(contract_data.bid_price) if contract_data is not None else 0,
                    "ask": float(contract_data.ask_price) if contract_data is not None else 0,
                })
            selected = select_contract_by_delta(candidates, self.target_delta)
            if selected is None:
                if self.time - context["subscribed"] > timedelta(minutes=30):
                    self.quote_skips += 1
                    self._remove_candidates(context["contracts"])
                    self.pending_contracts.pop(ticker, None)
                continue
            contract = selected["symbol"]
            ask, bid = float(selected["ask"]), float(selected["bid"])
            quality_candidate = {
                "ticker": ticker,
                "relative_volume": context["relative_volume"],
                "close_location": context["close_location"],
                "body_strength": context["body_strength"],
                "range_atr": context["range_atr"],
                "level_rejection_atr": context["level_rejection_atr"],
                "friction": 0.033 / ask if ask > 0 else float("inf"),
            }
            if self.causal_selector and not passes_causal_quality_gate(
                quality_candidate, self.causal_thresholds
            ):
                self.causal_quality_skips += 1
                self._remove_candidates(context["contracts"])
                self.pending_contracts.pop(ticker, None)
                continue
            if self.economics_gate and not friction_within_target(ask, self.entry_profit_hurdle):
                self.economics_skips += 1
                self._remove_candidates(context["contracts"])
                self.pending_contracts.pop(ticker, None)
                continue
            if self.max_entries_per_day > 0:
                equity_base = self.daily_allocation_equity.setdefault(
                    self.time.date(), float(self.portfolio.total_portfolio_value)
                )
                allocation_fraction = self.capital_fraction
                if self.adaptive_allocation:
                    allocation_fraction = adaptive_allocation_fraction(
                        len(ranked) - candidate_index,
                        self.max_entries_per_day - self.daily_entry_counts.get(self.time.date(), 0),
                    )
                quantity = contract_quantity_for_allocation(
                    float(self.portfolio.cash), equity_base, ask, allocation_fraction
                )
            else:
                quantity = contract_quantity(
                    float(self.portfolio.cash),
                    float(self.portfolio.total_portfolio_value),
                    ask,
                    capital_fraction=self.capital_fraction,
                )
            if quantity < 1:
                self.quote_skips += 1
                self._remove_candidates(context["contracts"])
                self.pending_contracts.pop(ticker, None)
                continue
            entry_dte = (contract.id.date.date() - self.time.date()).days
            tag = (
                f"ENTRY|{ticker}|D{self.target_delta:.2f}|DTE{entry_dte}|MA{context['period']}"
                f"|RV{context['relative_volume']:.2f}|CL{context['close_location']:.2f}"
            )
            ticket = self.market_order(contract, quantity, tag=tag)
            if ticket.status != OrderStatus.FILLED:
                self.entry_rejects += 1
                if ticket.status not in (OrderStatus.CANCELED, OrderStatus.INVALID):
                    ticket.cancel("ENTRY_NOT_FILLED")
                self._remove_candidates(context["contracts"])
                self.pending_contracts.pop(ticker, None)
                continue
            self._remove_candidates(context["contracts"], keep=contract)
            self.positions[ticker] = {
                **context,
                "contract": contract,
                "quantity": int(ticket.quantity_filled),
                "entry_price": float(ticket.average_fill_price),
                "entry_delta": abs(float(selected["delta"])),
                "entry_dte": entry_dte,
                "entry_time": self.time,
                "entry_date": self.time.date(),
                "peak_pnl": 0.0,
                "scaled_out": False,
                "underlying_entry": float(self.securities[context["underlying"]].price),
                "traced_checkpoints": set(),
                "failure_checked": False,
                "closing": False,
            }
            self.entry_deltas.append(abs(float(selected["delta"])))
            self.entry_dtes.append(entry_dte)
            self.entries += 1
            self.entry_dates.add(self.time.date())
            self.daily_entry_counts[self.time.date()] = self.daily_entry_counts.get(self.time.date(), 0) + 1
            if self.trace_mode:
                self.debug("TRACE|" + json.dumps({
                    "type": "entry",
                    "ticker": ticker,
                    "time": self.time.isoformat(),
                    "direction": context["direction"],
                    "period": context["period"],
                    "entry_price": float(ticket.average_fill_price),
                    "entry_delta": abs(float(selected["delta"])),
                    "entry_dte": entry_dte,
                    "quantity": int(ticket.quantity_filled),
                    "relative_volume": round(context["relative_volume"], 6),
                    "close_location": round(context["close_location"], 6),
                    "body_strength": round(context["body_strength"], 6),
                    "range_atr": round(context["range_atr"], 6),
                    "level_rejection_atr": round(context["level_rejection_atr"], 6),
                    "level_price": context["level_price"],
                    "signal_low": context["signal_low"],
                    "signal_high": context["signal_high"],
                    "underlying_entry": self.positions[ticker]["underlying_entry"],
                    "estimated_roundtrip_friction": round(0.033 / float(ticket.average_fill_price), 6),
                }, separators=(",", ":")))
            self.pending_contracts.pop(ticker, None)
            if self.max_entries_per_day > 0 and self.daily_entry_counts[self.time.date()] >= self.max_entries_per_day:
                break

    def _remove_candidates(self, contracts, keep=None):
        for contract in contracts:
            if contract != keep and contract in self.securities:
                self.remove_security(contract)

    def _manage_positions(self):
        for ticker, position in list(self.positions.items()):
            if position["closing"]:
                continue
            bid = float(self.securities[position["contract"]].bid_price)
            if bid <= 0 or position["entry_price"] <= 0:
                continue
            self._trace_position(ticker, position, bid)
            pnl = bid / position["entry_price"] - 1
            position["peak_pnl"] = max(position["peak_pnl"], pnl)
            underlying_now = float(self.securities[position["underlying"]].price)
            directional_underlying_return = position["direction"] * (underlying_now / position["underlying_entry"] - 1)
            minutes_held = (self.time - position["entry_time"]).total_seconds() / 60
            failure_checkpoint_due = (
                self.failure_minutes > 0
                and not position["failure_checked"]
                and minutes_held >= self.failure_minutes
            )
            if self.scale_out_enabled and not position["scaled_out"] and pnl >= self.scale_out_trigger:
                if self._scale_out(ticker) != "scaled":
                    continue
            if position["scaled_out"] and self.runner_target > 0 and pnl >= self.runner_target:
                self._close(ticker, "RUNNER_TARGET")
            elif self.trailing_enabled and trailing_profit_exit_due(
                pnl,
                position["peak_pnl"],
                self.trailing_activation,
                self.trailing_distance,
            ):
                self._close(ticker, "TRAILING_EXIT")
            elif not position["scaled_out"] and not self.trailing_enabled and pnl >= self.take_profit:
                self._close(ticker, "TARGET")
            else:
                failure_condition = failure_checkpoint_due and (
                    adverse_failure_to_launch_due(
                        minutes_held,
                        pnl,
                        directional_underlying_return,
                        self.failure_minutes,
                        self.failure_min_pnl,
                    )
                    if self.failure_underlying_adverse
                    else failure_to_launch_due(
                        minutes_held,
                        pnl,
                        self.failure_minutes,
                        self.failure_min_pnl,
                    )
                )
                if failure_checkpoint_due and failure_condition:
                    position["failure_checked"] = True
                    self._close(ticker, "FAILURE_EXIT")
                elif failure_checkpoint_due and not self.failure_repeat:
                    position["failure_checked"] = True
                elif self.max_hold_minutes > 0 and self.time - position["entry_time"] >= timedelta(minutes=self.max_hold_minutes):
                    self._close(ticker, "TIME_EXIT")
                elif self.time.date() > position["entry_date"] or (self.time.hour == 15 and self.time.minute >= 55):
                    self._close(ticker, "TIME_EXIT")

    def _trace_position(self, ticker, position, bid):
        if not self.trace_mode:
            return
        elapsed = (self.time - position["entry_time"]).total_seconds() / 60
        option = self.securities[position["contract"]]
        underlying_now = float(self.securities[position["underlying"]].price)
        invalidation = position["signal_low"] if position["direction"] > 0 else position["signal_high"]
        snapshot = checkpoint_snapshot(
            position["entry_price"], bid, float(option.ask_price),
            position["underlying_entry"], underlying_now, position["direction"],
            position["level_price"], invalidation,
        )
        if snapshot is None:
            return
        for checkpoint in self.trace_checkpoints:
            if elapsed < checkpoint or checkpoint in position["traced_checkpoints"]:
                continue
            position["traced_checkpoints"].add(checkpoint)
            record = {
                "type": "checkpoint",
                "ticker": ticker,
                "entry_time": position["entry_time"].isoformat(),
                "time": self.time.isoformat(),
                "checkpoint": checkpoint,
                **snapshot,
            }
            self.debug("TRACE|" + json.dumps(record, separators=(",", ":")))

    def _scale_out(self, ticker):
        position = self.positions.get(ticker)
        if position is None or position["closing"]:
            return "failed"
        quantity = scale_out_quantity(position["quantity"], self.scale_out_fraction)
        if quantity < 1:
            self._close(ticker, "TARGET")
            return "closed"
        ticket = self.market_order(
            position["contract"],
            -quantity,
            tag=f"SCALE_OUT|{ticker}|F{self.scale_out_fraction:.2f}",
        )
        if ticket.status != OrderStatus.FILLED:
            self.close_rejects += 1
            return "failed"
        position["quantity"] -= abs(int(ticket.quantity_filled))
        position["scaled_out"] = True
        self.scale_outs += 1
        return "scaled"

    def _close(self, ticker, reason):
        position = self.positions.get(ticker)
        if position is None or position["closing"]:
            return
        position["closing"] = True
        ticket = self.market_order(position["contract"], -position["quantity"], tag=f"{reason}|{ticker}|D{position['entry_delta']:.2f}|DTE{position['entry_dte']}|MA{position['period']}")
        if ticket.status != OrderStatus.FILLED:
            self.close_rejects += 1
            position["closing"] = False
            return
        if self.trace_mode:
            self.debug("TRACE|" + json.dumps({
                "type": "exit", "ticker": ticker,
                "entry_time": position["entry_time"].isoformat(),
                "time": self.time.isoformat(), "reason": reason,
                "exit_price": float(ticket.average_fill_price),
            }, separators=(",", ":")))
        self.positions.pop(ticker, None)
        self.remove_security(position["contract"])
        self.closed += 1
        if reason == "TARGET":
            self.target_exits += 1
        elif reason == "TRAILING_EXIT":
            self.trailing_exits += 1
        elif reason == "RUNNER_TARGET":
            self.runner_target_exits += 1
        elif reason == "FAILURE_EXIT":
            self.failure_exits += 1
        else:
            self.time_exits += 1

    def _close_all(self):
        self.pending_signals.clear()
        for context in self.pending_contracts.values():
            self._remove_candidates(context["contracts"])
        self.pending_contracts.clear()
        for ticker in list(self.positions):
            self._close(ticker, "TIME_EXIT")

    def on_end_of_algorithm(self):
        self.set_runtime_statistic("Target Delta", f"{self.target_delta:.2f}")
        self.set_runtime_statistic("Target DTE", str(self.target_dte))
        self.set_runtime_statistic("Entry Cutoff Hour", str(self.entry_cutoff_hour))
        self.set_runtime_statistic("Starting Cash", f"{self.starting_cash:.2f}")
        self.set_runtime_statistic("Capital Fraction", f"{self.capital_fraction:.2%}")
        self.set_runtime_statistic("Adaptive Allocation", str(self.adaptive_allocation))
        self.set_runtime_statistic("Max Entries Per Day", str(self.max_entries_per_day))
        self.set_runtime_statistic("Opening Signal Hour", str(self.opening_signal_hour))
        average_delta = sum(self.entry_deltas) / len(self.entry_deltas) if self.entry_deltas else 0
        average_dte = sum(self.entry_dtes) / len(self.entry_dtes) if self.entry_dtes else 0
        self.set_runtime_statistic("Average Entry Delta", f"{average_delta:.4f}")
        self.set_runtime_statistic("Average Entry DTE", f"{average_dte:.2f}")
        self.set_runtime_statistic("Take Profit", f"{self.take_profit:.2%}")
        self.set_runtime_statistic("Trailing Activation", f"{self.trailing_activation:.2%}")
        self.set_runtime_statistic("Trailing Distance", f"{self.trailing_distance:.2%}")
        self.set_runtime_statistic("Scale Out Fraction", f"{self.scale_out_fraction:.2%}")
        self.set_runtime_statistic("Scale Out Trigger", f"{self.scale_out_trigger:.2%}")
        self.set_runtime_statistic("Runner Target", f"{self.runner_target:.2%}")
        self.set_runtime_statistic("Max Hold Minutes", str(self.max_hold_minutes))
        self.set_runtime_statistic("Failure Minutes", str(self.failure_minutes))
        self.set_runtime_statistic("Failure Minimum PnL", f"{self.failure_min_pnl:.2%}")
        self.set_runtime_statistic("Failure Underlying Adverse", str(self.failure_underlying_adverse))
        self.set_runtime_statistic("Failure Repeat", str(self.failure_repeat))
        self.set_runtime_statistic("Economics Gate", str(self.economics_gate))
        self.set_runtime_statistic("Economics Skips", str(self.economics_skips))
        self.set_runtime_statistic("Quality Filter", str(self.quality_filter))
        self.set_runtime_statistic("Causal Selector", str(self.causal_selector))
        self.set_runtime_statistic("Causal Quality Skips", str(self.causal_quality_skips))
        self.set_runtime_statistic("Trace Mode", str(self.trace_mode))
        self.set_runtime_statistic("Signals", str(self.signals))
        self.set_runtime_statistic("Entries", str(self.entries))
        self.set_runtime_statistic("Closed", str(self.closed))
        self.set_runtime_statistic("Target Exits", str(self.target_exits))
        self.set_runtime_statistic("Trailing Exits", str(self.trailing_exits))
        self.set_runtime_statistic("Scale Outs", str(self.scale_outs))
        self.set_runtime_statistic("Runner Target Exits", str(self.runner_target_exits))
        self.set_runtime_statistic("Time Exits", str(self.time_exits))
        self.set_runtime_statistic("Failure Exits", str(self.failure_exits))
        self.set_runtime_statistic("Quality Skips", str(self.quality_skips))
        self.set_runtime_statistic("No 0DTE Skips", str(self.no_expiry_skips))
        self.set_runtime_statistic("Quote Skips", str(self.quote_skips))
        self.set_runtime_statistic("Entry Rejects", str(self.entry_rejects))
        self.set_runtime_statistic("Close Rejects", str(self.close_rejects))
        for period, count in self.period_signals.items():
            self.set_runtime_statistic(f"MA{period} Signals", str(count))
