# region imports
from AlgorithmImports import *
from datetime import timedelta, datetime
# endregion


class MFFUFastPassV1(QCAlgorithm):
    """
    Fast-pass strategy (separate from PF100 baseline).
    Goal: pass MFFU-style 50k eval faster while respecting risk/consistency.
    """

    def Initialize(self):
        # Dates
        self.SetStartDate(
            int(self.GetParameter("start_year") or 2022),
            int(self.GetParameter("start_month") or 1),
            int(self.GetParameter("start_day") or 1),
        )
        self.SetEndDate(
            int(self.GetParameter("end_year") or 2026),
            int(self.GetParameter("end_month") or 3),
            int(self.GetParameter("end_day") or 31),
        )
        self.SetTimeZone(TimeZones.NewYork)

        # Capital
        self.initial_cash = float(self.GetParameter("initial_cash") or 50000)
        self.SetCash(self.initial_cash)
        self.SetBrokerageModel(BrokerageName.InteractiveBrokersBrokerage, AccountType.Margin)

        # Instruments
        self.trade_mnq = (self.GetParameter("trade_mnq") or "1").strip().lower() not in ("0", "false", "no")
        self.trade_mes = (self.GetParameter("trade_mes") or "1").strip().lower() not in ("0", "false", "no")
        self.trade_m2k = (self.GetParameter("trade_m2k") or "0").strip().lower() not in ("0", "false", "no")
        self.allow_shorts = (self.GetParameter("allow_shorts") or "1").strip().lower() not in ("0", "false", "no")

        # Signal params
        self.atr_period = int(self.GetParameter("atr_period") or 14)
        self.trend_period = int(self.GetParameter("trend_period") or 50)
        self.or_minutes = int(self.GetParameter("or_minutes") or 5)
        self.breakout_buffer_pct = float(self.GetParameter("breakout_buffer_pct") or 0.0005)
        self.min_gap_pct = float(self.GetParameter("min_gap_pct") or 0.0010)
        self.max_gap_pct = float(self.GetParameter("max_gap_pct") or 0.0150)
        self.min_or_width_pct = float(self.GetParameter("min_or_width_pct") or 0.0010)
        self.max_or_width_pct = float(self.GetParameter("max_or_width_pct") or 0.0100)
        self.min_atr_pct = float(self.GetParameter("min_atr_pct") or 0.0040)
        self.max_atr_pct = float(self.GetParameter("max_atr_pct") or 0.0300)
        self.use_or_filter = (self.GetParameter("use_or_filter") or "0").strip().lower() not in ("0", "false", "no")
        self.min_intraday_mom_pct = float(self.GetParameter("min_intraday_mom_pct") or 0.0010)
        self.require_trend_alignment = (self.GetParameter("require_trend_alignment") or "1").strip().lower() not in (
            "0",
            "false",
            "no",
        )
        self.require_gap_alignment = (self.GetParameter("require_gap_alignment") or "1").strip().lower() not in (
            "0",
            "false",
            "no",
        )

        # Risk params
        self.risk_per_trade = float(self.GetParameter("risk_per_trade") or 0.0120)
        self.stop_atr_mult = float(self.GetParameter("stop_atr_mult") or 0.90)
        self.target_atr_mult = float(self.GetParameter("target_atr_mult") or 1.90)
        self.trail_after_r_mult = float(self.GetParameter("trail_after_r_mult") or 1.0)
        self.trail_atr_mult = float(self.GetParameter("trail_atr_mult") or 0.80)
        self.max_contracts_per_trade = int(self.GetParameter("max_contracts_per_trade") or 5)
        self.max_open_positions = int(self.GetParameter("max_open_positions") or 2)
        self.max_trades_per_symbol_day = int(self.GetParameter("max_trades_per_symbol_day") or 1)
        self.max_hold_hours = int(self.GetParameter("max_hold_hours") or 6)

        # MFFU-style pass constraints
        self.evaluation_profit_target_usd = float(self.GetParameter("evaluation_profit_target_usd") or 3000)
        self.consistency_pct_limit = float(self.GetParameter("consistency_pct_limit") or 0.50)
        self.consistency_day_profit_cap_usd = float(self.GetParameter("consistency_day_profit_cap_usd") or 1200)
        self.daily_loss_limit_pct = float(self.GetParameter("daily_loss_limit_pct") or 0.018)
        self.trailing_dd_limit_pct = float(self.GetParameter("trailing_dd_limit_pct") or 0.035)
        self.daily_profit_lock_usd = float(self.GetParameter("daily_profit_lock_usd") or 1200)

        # Session
        self.entry_start_h = int(self.GetParameter("entry_start_hour") or 9)
        self.entry_start_m = int(self.GetParameter("entry_start_min") or 36)
        self.entry_end_h = int(self.GetParameter("entry_end_hour") or 11)
        self.entry_end_m = int(self.GetParameter("entry_end_min") or 30)
        self.flatten_h = int(self.GetParameter("flatten_hour") or 15)
        self.flatten_m = int(self.GetParameter("flatten_min") or 58)

        self.instruments = {}
        if self.trade_mes:
            self._add_future(Futures.Indices.MicroSP500EMini, "MES")
        if self.trade_mnq:
            self._add_future(Futures.Indices.MicroNASDAQ100EMini, "MNQ")
        if self.trade_m2k:
            self._add_future(Futures.Indices.MicroRussell2000EMini, "M2K")

        warmup = max(self.atr_period, self.trend_period) + 8
        self.SetWarmUp(warmup, Resolution.Daily)

        # State
        self.entry_window_open = False
        self.trailing_lock = False
        self.peak_equity = self.initial_cash
        self.day_key = None
        self.day_start_equity = 0.0
        self.day_locked = False
        self.day_best_pnl_usd = 0.0
        self.day_worst_pnl_usd = 0.0
        self.best_day_profit_usd = 0.0
        self.worst_day_loss_usd = 0.0
        self.daily_loss_breaches = 0
        self.trailing_breaches = 0
        self.consistency_locks = 0
        self.price_guard_skips = 0

        # Schedules
        self.Schedule.On(self.DateRules.EveryDay(), self.TimeRules.At(self.entry_start_h, self.entry_start_m), self._open_entry_window)
        or_minutes_from_open = 30 + self.or_minutes
        or_h = 9 + (or_minutes_from_open // 60)
        or_m = or_minutes_from_open % 60
        self.Schedule.On(self.DateRules.EveryDay(), self.TimeRules.At(or_h, or_m), self._capture_opening_range)
        self.Schedule.On(self.DateRules.EveryDay(), self.TimeRules.At(self.entry_end_h, self.entry_end_m), self._close_entry_window)
        self.Schedule.On(self.DateRules.EveryDay(), self.TimeRules.At(self.flatten_h, self.flatten_m), self._flatten_eod)

    def _add_future(self, future_type, name):
        fut = self.AddFuture(
            future_type,
            Resolution.Minute,
            dataMappingMode=DataMappingMode.OpenInterest,
            dataNormalizationMode=DataNormalizationMode.BackwardsRatio,
            contractDepthOffset=0,
        )
        fut.SetFilter(lambda u: u.FrontMonth())
        sym = fut.Symbol

        info = {
            "name": name,
            "future": fut,
            "atr": self.ATR(sym, self.atr_period, MovingAverageType.Simple, Resolution.Daily),
            "trend": self.EMA(sym, self.trend_period, Resolution.Daily),
            "daily_closes": RollingWindow[float](3),
            "direction": 0,
            "entry_price": 0.0,
            "entry_time": None,
            "stop_price": 0.0,
            "target_price": 0.0,
            "initial_r": 0.0,
            "or_high": None,
            "or_low": None,
            "or_ready": False,
            "session_open_price": None,
            "trades_today": 0,
        }
        self.instruments[sym] = info

        day_cons = TradeBarConsolidator(timedelta(days=1))

        def on_daily(_, bar):
            info["daily_closes"].Add(float(bar.Close))

        day_cons.DataConsolidated += on_daily
        self.SubscriptionManager.AddConsolidator(sym, day_cons)

    def _capture_opening_range(self):
        if self.IsWarmingUp:
            return
        start = datetime(self.Time.year, self.Time.month, self.Time.day, 9, 30)
        end = start + timedelta(minutes=self.or_minutes)
        for _, info in self.instruments.items():
            mapped = info["future"].Mapped
            if mapped is None:
                continue
            hist = self.History[TradeBar](mapped, start, end, Resolution.Minute)
            if hist is None:
                continue
            bars = list(hist)
            if len(bars) < 1:
                continue
            info["or_high"] = max(float(b.High) for b in bars)
            info["or_low"] = min(float(b.Low) for b in bars)
            info["or_ready"] = info["or_high"] > info["or_low"]
            info["session_open_price"] = float(bars[0].Open)

    def OnData(self, data):
        self._handle_rolls(data)
        if self.IsWarmingUp:
            return

        equity = self.Portfolio.TotalPortfolioValue
        self._roll_day_if_needed(equity)
        self._update_day_extremes(equity)

        if equity > self.peak_equity:
            self.peak_equity = equity
        dd = (self.peak_equity - equity) / self.peak_equity if self.peak_equity > 0 else 0.0
        if dd >= self.trailing_dd_limit_pct and not self.trailing_lock:
            self.trailing_lock = True
            self.trailing_breaches += 1
            self._liquidate_all("TRAILING_DD_LOCK")
        if self.trailing_lock:
            self._publish_runtime(equity, dd)
            return

        day_pnl = equity - self.day_start_equity
        if day_pnl <= -(self.day_start_equity * self.daily_loss_limit_pct) and not self.day_locked:
            self.daily_loss_breaches += 1
            self.day_locked = True
            self._liquidate_all("DAILY_LOSS_LOCK")
        elif day_pnl >= self.daily_profit_lock_usd and not self.day_locked:
            self.day_locked = True
            self._liquidate_all("DAILY_PROFIT_LOCK")
        elif day_pnl >= self.consistency_day_profit_cap_usd and not self.day_locked:
            self.consistency_locks += 1
            self.day_locked = True
            self._liquidate_all("CONSISTENCY_DAY_CAP")

        self._process_exits()
        self._process_entries()
        self._publish_runtime(equity, dd)

    def _process_entries(self):
        if self.day_locked or self.trailing_lock or not self.entry_window_open:
            return
        if self._open_positions_count() >= self.max_open_positions:
            return

        for sym, info in self.instruments.items():
            mapped = info["future"].Mapped
            if mapped is None:
                continue
            if not self._security_has_fresh_price(mapped):
                self.price_guard_skips += 1
                continue
            if self.Portfolio[mapped].Quantity != 0:
                continue
            if info["trades_today"] >= self.max_trades_per_symbol_day:
                continue
            if info["daily_closes"].Count < 1:
                continue
            if self._open_positions_count() >= self.max_open_positions:
                break

            cont_price = self.Securities[sym].Price
            if cont_price <= 0:
                continue
            prev_close = info["daily_closes"][0]
            if prev_close <= 0:
                continue
            atr = info["atr"]
            trend = info["trend"]
            if not atr.IsReady or not trend.IsReady:
                continue
            atr_points = atr.Current.Value
            if atr_points <= 0:
                continue
            atr_pct = atr_points / prev_close
            if atr_pct < self.min_atr_pct or atr_pct > self.max_atr_pct:
                continue

            session_open = info["session_open_price"] or (self.Securities[mapped].Open if self.Securities[mapped].Open else cont_price)
            gap_pct = (session_open - prev_close) / prev_close
            if abs(gap_pct) < self.min_gap_pct or abs(gap_pct) > self.max_gap_pct:
                continue

            trend_val = trend.Current.Value
            uptrend = cont_price > trend_val
            downtrend = cont_price < trend_val

            if self.use_or_filter:
                or_high = info["or_high"]
                or_low = info["or_low"]
                if or_high is None or or_low is None or or_high <= or_low:
                    continue
                or_w = (or_high - or_low) / prev_close
                if or_w < self.min_or_width_pct or or_w > self.max_or_width_pct:
                    continue
                long_signal = cont_price > or_high * (1.0 + self.breakout_buffer_pct)
                short_signal = cont_price < or_low * (1.0 - self.breakout_buffer_pct)
            else:
                intraday_mom = (cont_price - session_open) / session_open if session_open > 0 else 0.0
                if abs(intraday_mom) < self.min_intraday_mom_pct:
                    continue
                long_signal = intraday_mom > 0
                short_signal = intraday_mom < 0

            go_long = long_signal
            go_short = short_signal and self.allow_shorts
            if self.require_trend_alignment:
                if go_long and not uptrend:
                    go_long = False
                if go_short and not downtrend:
                    go_short = False
            if self.require_gap_alignment:
                if go_long and gap_pct <= 0:
                    go_long = False
                if go_short and gap_pct >= 0:
                    go_short = False
            if not go_long and not go_short:
                continue

            stop_dist = atr_points * self.stop_atr_mult
            qty = self._position_size(mapped, stop_dist)
            if qty < 1:
                continue

            target_dist = atr_points * self.target_atr_mult
            if go_long:
                self.MarketOrder(mapped, qty, tag=f"FASTPASS_LONG_{info['name']}")
                info["direction"] = 1
                info["entry_price"] = cont_price
                info["entry_time"] = self.Time
                info["stop_price"] = cont_price - stop_dist
                info["target_price"] = cont_price + target_dist
                info["initial_r"] = stop_dist
            else:
                self.MarketOrder(mapped, -qty, tag=f"FASTPASS_SHORT_{info['name']}")
                info["direction"] = -1
                info["entry_price"] = cont_price
                info["entry_time"] = self.Time
                info["stop_price"] = cont_price + stop_dist
                info["target_price"] = cont_price - target_dist
                info["initial_r"] = stop_dist
            info["trades_today"] += 1

    def _process_exits(self):
        for sym, info in self.instruments.items():
            mapped = info["future"].Mapped
            if mapped is None:
                continue
            qty = self.Portfolio[mapped].Quantity
            direction = info["direction"]
            if qty == 0 or direction == 0:
                continue

            cont_price = self.Securities[sym].Price
            if cont_price <= 0:
                continue

            # trailing stop after >= trail_after_r_mult * initial_r
            initial_r = float(info["initial_r"] or 0.0)
            if initial_r > 0:
                atr = info["atr"]
                atr_points = atr.Current.Value if atr.IsReady else 0.0
                if atr_points > 0:
                    if direction == 1:
                        open_pnl_pts = cont_price - float(info["entry_price"])
                        if open_pnl_pts >= initial_r * self.trail_after_r_mult:
                            new_stop = cont_price - atr_points * self.trail_atr_mult
                            if new_stop > float(info["stop_price"]):
                                info["stop_price"] = new_stop
                    else:
                        open_pnl_pts = float(info["entry_price"]) - cont_price
                        if open_pnl_pts >= initial_r * self.trail_after_r_mult:
                            new_stop = cont_price + atr_points * self.trail_atr_mult
                            if new_stop < float(info["stop_price"]):
                                info["stop_price"] = new_stop

            hit_stop = (direction == 1 and cont_price <= info["stop_price"]) or (
                direction == -1 and cont_price >= info["stop_price"]
            )
            hit_target = (direction == 1 and cont_price >= info["target_price"]) or (
                direction == -1 and cont_price <= info["target_price"]
            )
            held_hours = int((self.Time - info["entry_time"]).total_seconds() / 3600.0) if info["entry_time"] else 0
            hit_time = held_hours >= self.max_hold_hours
            if hit_stop or hit_target or hit_time:
                reason = "STOP" if hit_stop else ("TARGET" if hit_target else "TIME")
                self.Liquidate(mapped, tag=f"{reason}_EXIT_{info['name']}")
                self._reset_position_state(info)

    def _handle_rolls(self, data):
        if not data.SymbolChangedEvents:
            return
        for changed in data.SymbolChangedEvents.Values:
            old_sym = changed.OldSymbol
            new_sym = changed.NewSymbol
            for _, info in self.instruments.items():
                mapped = info["future"].Mapped
                if mapped != old_sym:
                    continue
                qty = self.Portfolio[old_sym].Quantity
                if qty != 0:
                    self.Liquidate(old_sym, tag=f"ROLL_OUT_{info['name']}")
                    if self._security_has_fresh_price(new_sym):
                        self.MarketOrder(new_sym, qty, tag=f"ROLL_IN_{info['name']}")

    def _security_has_fresh_price(self, symbol):
        if symbol is None or not self.Securities.ContainsKey(symbol):
            return False
        sec = self.Securities[symbol]
        if not sec.IsTradable or not sec.HasData:
            return False
        px = sec.Price
        if px is None or px <= 0:
            return False
        last = sec.GetLastData()
        if last is None:
            return False
        return last.EndTime >= self.Time - timedelta(minutes=10)

    def _position_size(self, mapped, stop_dist_points):
        if stop_dist_points <= 0:
            return 0
        mult = float(self.Securities[mapped].SymbolProperties.ContractMultiplier)
        if mult <= 0:
            return 0
        risk_per_contract = stop_dist_points * mult
        risk_budget = self.Portfolio.TotalPortfolioValue * self.risk_per_trade
        qty = int(risk_budget / risk_per_contract)
        if qty < 1:
            return 0
        return min(qty, self.max_contracts_per_trade)

    def _open_positions_count(self):
        n = 0
        for _, info in self.instruments.items():
            mapped = info["future"].Mapped
            if mapped is not None and self.Portfolio[mapped].Quantity != 0:
                n += 1
        return n

    def _liquidate_all(self, reason):
        for _, info in self.instruments.items():
            mapped = info["future"].Mapped
            if mapped is not None and self.Portfolio[mapped].Quantity != 0:
                self.Liquidate(mapped, tag=reason)
            self._reset_position_state(info)

    def _reset_position_state(self, info):
        info["direction"] = 0
        info["entry_price"] = 0.0
        info["entry_time"] = None
        info["stop_price"] = 0.0
        info["target_price"] = 0.0
        info["initial_r"] = 0.0

    def _open_entry_window(self):
        self.entry_window_open = True

    def _close_entry_window(self):
        self.entry_window_open = False

    def _flatten_eod(self):
        if self.IsWarmingUp:
            return
        self._liquidate_all("EOD_FLAT")
        self.day_locked = True
        self.entry_window_open = False

    def _roll_day_if_needed(self, equity):
        current_day = self.Time.date()
        if self.day_key is None:
            self.day_key = current_day
            self.day_start_equity = equity
            self.day_locked = False
            self.day_best_pnl_usd = 0.0
            self.day_worst_pnl_usd = 0.0
            for _, info in self.instruments.items():
                info["trades_today"] = 0
                info["or_high"] = None
                info["or_low"] = None
                info["or_ready"] = False
                info["session_open_price"] = None
            return

        if current_day != self.day_key:
            self._finalize_day_extremes()
            self.day_key = current_day
            self.day_start_equity = equity
            self.day_locked = False
            self.day_best_pnl_usd = 0.0
            self.day_worst_pnl_usd = 0.0
            self.entry_window_open = False
            for _, info in self.instruments.items():
                info["trades_today"] = 0
                info["or_high"] = None
                info["or_low"] = None
                info["or_ready"] = False
                info["session_open_price"] = None

    def _update_day_extremes(self, equity):
        day_pnl = equity - self.day_start_equity
        if day_pnl > self.day_best_pnl_usd:
            self.day_best_pnl_usd = day_pnl
        if day_pnl < self.day_worst_pnl_usd:
            self.day_worst_pnl_usd = day_pnl

    def _finalize_day_extremes(self):
        if self.day_best_pnl_usd > self.best_day_profit_usd:
            self.best_day_profit_usd = self.day_best_pnl_usd
        if self.day_worst_pnl_usd < self.worst_day_loss_usd:
            self.worst_day_loss_usd = self.day_worst_pnl_usd

    def _publish_runtime(self, equity, dd):
        total_profit = equity - self.initial_cash
        best_day_over_target_pct = 0.0
        if self.evaluation_profit_target_usd > 0:
            best_day_over_target_pct = 100.0 * self.best_day_profit_usd / self.evaluation_profit_target_usd

        self.SetRuntimeStatistic("DailyLossBreaches", str(self.daily_loss_breaches))
        self.SetRuntimeStatistic("TrailingBreaches", str(self.trailing_breaches))
        self.SetRuntimeStatistic("ConsistencyLocks", str(self.consistency_locks))
        self.SetRuntimeStatistic("PriceGuardSkips", str(self.price_guard_skips))
        self.SetRuntimeStatistic("BestDayUSD", f"{self.best_day_profit_usd:.2f}")
        self.SetRuntimeStatistic("WorstDayUSD", f"{self.worst_day_loss_usd:.2f}")
        self.SetRuntimeStatistic("TotalProfitUSD", f"{total_profit:.2f}")
        self.SetRuntimeStatistic("BestDayOfTargetPct", f"{best_day_over_target_pct:.2f}")
        self.SetRuntimeStatistic("DrawdownPct", f"{dd * 100.0:.2f}")

    def OnEndOfAlgorithm(self):
        equity = self.Portfolio.TotalPortfolioValue
        self._finalize_day_extremes()
        total_profit = equity - self.initial_cash
        ret = total_profit / self.initial_cash if self.initial_cash else 0.0
        dd = (self.peak_equity - equity) / self.peak_equity if self.peak_equity > 0 else 0.0
        self._publish_runtime(equity, dd)
        self.Log(
            "FINAL "
            f"equity={equity:.2f} return_pct={ret*100.0:.2f} dd_pct={dd*100.0:.2f} "
            f"daily_loss_breaches={self.daily_loss_breaches} trailing_breaches={self.trailing_breaches} "
            f"consistency_locks={self.consistency_locks} best_day_usd={self.best_day_profit_usd:.2f}"
        )
