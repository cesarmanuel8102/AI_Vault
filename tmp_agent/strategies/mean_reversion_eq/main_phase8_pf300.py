from AlgorithmImports import *
from datetime import datetime, timedelta


class PF300CrossAsset(QCAlgorithm):
    """
    PF300 - Cross-asset multi-motor portfolio
    - Index block (MES/MNQ): MR normal + ORB normal + trend in stress
    - Alt block (GC/CL): breakout-trend only
    - Intraday only, EOD flatten, account-level locks
    """

    def Initialize(self):
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

        self.initial_cash = float(self.GetParameter("initial_cash") or 50000)
        self.SetCash(self.initial_cash)
        self.SetBrokerageModel(BrokerageName.InteractiveBrokersBrokerage, AccountType.Margin)

        self.trade_mes = (self.GetParameter("trade_mes") or "1").strip().lower() not in ("0", "false", "no")
        self.trade_mnq = (self.GetParameter("trade_mnq") or "1").strip().lower() not in ("0", "false", "no")
        self.trade_gc = (self.GetParameter("trade_gc") or "0").strip().lower() not in ("0", "false", "no")
        self.trade_cl = (self.GetParameter("trade_cl") or "0").strip().lower() not in ("0", "false", "no")
        self.allow_shorts = (self.GetParameter("allow_shorts") or "1").strip().lower() not in ("0", "false", "no")

        self.atr_period = int(self.GetParameter("atr_period") or 14)
        self.trend_period = int(self.GetParameter("trend_period") or 55)

        # Regime detector
        self.ext_vixy_ratio_threshold = float(self.GetParameter("ext_vixy_ratio_threshold") or 1.03)
        self.ext_vixy_sma_period = int(self.GetParameter("ext_vixy_sma_period") or 5)
        self.ext_rv_threshold = float(self.GetParameter("ext_rv_threshold") or 1.0)
        self.ext_gap_abs_threshold = float(self.GetParameter("ext_gap_abs_threshold") or 1.0)

        # Index motors
        self.idx_mr_gap_atr_mult = float(self.GetParameter("idx_mr_gap_atr_mult") or 0.20)
        self.idx_mr_stop_atr_mult = float(self.GetParameter("idx_mr_stop_atr_mult") or 0.58)
        self.idx_mr_fill_frac = float(self.GetParameter("idx_mr_fill_frac") or 0.75)
        self.idx_mr_max_gap_pct = float(self.GetParameter("idx_mr_max_gap_pct") or 0.008)
        self.idx_mr_risk = float(self.GetParameter("idx_mr_risk") or 0.009)

        self.idx_or_minutes = int(self.GetParameter("idx_or_minutes") or 10)
        self.idx_or_buffer_pct = float(self.GetParameter("idx_or_buffer_pct") or 0.0003)
        self.idx_or_stop_atr_mult = float(self.GetParameter("idx_or_stop_atr_mult") or 0.75)
        self.idx_or_target_atr_mult = float(self.GetParameter("idx_or_target_atr_mult") or 1.55)
        self.idx_or_risk = float(self.GetParameter("idx_or_risk") or 0.008)

        self.idx_stress_min_gap_pct = float(self.GetParameter("idx_stress_min_gap_pct") or 0.007)
        self.idx_stress_stop_atr_mult = float(self.GetParameter("idx_stress_stop_atr_mult") or 0.90)
        self.idx_stress_target_atr_mult = float(self.GetParameter("idx_stress_target_atr_mult") or 1.80)
        self.idx_stress_risk = float(self.GetParameter("idx_stress_risk") or 0.003)
        self.idx_stress_intraday_mom_pct = float(self.GetParameter("idx_stress_intraday_mom_pct") or 0.001)

        # Alt motor
        self.alt_break_buffer_pct = float(self.GetParameter("alt_break_buffer_pct") or 0.0005)
        self.alt_stop_atr_mult = float(self.GetParameter("alt_stop_atr_mult") or 0.85)
        self.alt_target_atr_mult = float(self.GetParameter("alt_target_atr_mult") or 1.70)
        self.alt_risk = float(self.GetParameter("alt_risk") or 0.0025)
        self.alt_use_only_normal = (self.GetParameter("alt_use_only_normal") or "1").strip().lower() not in (
            "0",
            "false",
            "no",
        )

        # Account guardrails
        self.max_contracts_per_trade = int(self.GetParameter("max_contracts_per_trade") or 10)
        self.max_open_positions = int(self.GetParameter("max_open_positions") or 3)
        self.max_trades_per_symbol_day = int(self.GetParameter("max_trades_per_symbol_day") or 2)
        self.daily_loss_limit_pct = float(self.GetParameter("daily_loss_limit_pct") or 0.018)
        self.daily_profit_lock_pct = float(self.GetParameter("daily_profit_lock_pct") or 0.040)
        self.trailing_dd_limit_pct = float(self.GetParameter("trailing_dd_limit_pct") or 0.035)
        self.trailing_lock_mode = (self.GetParameter("trailing_lock_mode") or "EOD").strip().upper()
        if self.trailing_lock_mode not in ("INTRADAY", "EOD"):
            self.trailing_lock_mode = "EOD"

        self.flatten_h = int(self.GetParameter("flatten_hour") or 15)
        self.flatten_m = int(self.GetParameter("flatten_min") or 58)
        self.max_hold_hours = int(self.GetParameter("max_hold_hours") or 6)

        self.instruments = {}
        if self.trade_mes:
            self._add_future(Futures.Indices.MicroSP500EMini, "MES", "IDX")
        if self.trade_mnq:
            self._add_future(Futures.Indices.MicroNASDAQ100EMini, "MNQ", "IDX")
        if self.trade_gc:
            self._add_future(Futures.Metals.Gold, "GC", "ALT")
        if self.trade_cl:
            self._add_future(Futures.Energies.CrudeOilWTI, "CL", "ALT")

        self.spy = self.AddEquity("SPY", Resolution.Minute).Symbol
        self.vixy = self.AddEquity("VIXY", Resolution.Minute).Symbol
        self.vixy_sma = self.SMA(self.vixy, self.ext_vixy_sma_period, Resolution.Daily)

        self.spy_prev_close = None
        self.spy_ret_window = RollingWindow[float](25)
        self.spy_gap_window = RollingWindow[float](25)
        spy_cons = TradeBarConsolidator(timedelta(days=1))

        def on_spy_daily(_, bar):
            if self.spy_prev_close is not None and self.spy_prev_close > 0:
                ret = (float(bar.Close) - self.spy_prev_close) / self.spy_prev_close
                gap = (float(bar.Open) - self.spy_prev_close) / self.spy_prev_close
                self.spy_ret_window.Add(float(ret))
                self.spy_gap_window.Add(float(gap))
            self.spy_prev_close = float(bar.Close)

        spy_cons.DataConsolidated += on_spy_daily
        self.SubscriptionManager.AddConsolidator(self.spy, spy_cons)

        warmup = max(self.atr_period, self.trend_period, self.ext_vixy_sma_period) + 8
        self.SetWarmUp(warmup, Resolution.Daily)

        self.peak_equity = self.initial_cash
        self.trailing_lock = False
        self.day_key = None
        self.day_start_equity = 0.0
        self.day_locked = False
        self.day_best_pnl_usd = 0.0
        self.day_worst_pnl_usd = 0.0
        self.best_day_profit_usd = 0.0
        self.worst_day_loss_usd = 0.0
        self.daily_loss_breaches = 0
        self.trailing_breaches = 0
        self.daily_profit_locks = 0
        self.external_stress_days = 0
        self.external_stress_last_day = None
        self.external_stress_active = False
        self.last_equity_snapshot = self.initial_cash

        self.Schedule.On(self.DateRules.EveryDay(), self.TimeRules.At(9, 40), self._entry_index_mr)
        self.Schedule.On(self.DateRules.EveryDay(), self.TimeRules.At(10, 5), self._entry_index_stress)
        self.Schedule.On(self.DateRules.EveryDay(), self.TimeRules.At(10, 15), self._entry_index_orb)
        self.Schedule.On(self.DateRules.EveryDay(), self.TimeRules.At(10, 20), self._entry_alt_breakout)
        self.Schedule.On(self.DateRules.EveryDay(), self.TimeRules.At(self.flatten_h, self.flatten_m), self._flatten_eod)

    def _add_future(self, future_type, name, group):
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
            "group": group,
            "future": fut,
            "atr": self.ATR(sym, self.atr_period, MovingAverageType.Simple, Resolution.Daily),
            "trend": self.EMA(sym, self.trend_period, Resolution.Daily),
            "daily_closes": RollingWindow[float](3),
            "daily_bars": RollingWindow[TradeBar](3),
            "direction": 0,
            "entry_price": 0.0,
            "entry_time": None,
            "entry_qty": 0,
            "stop_price": 0.0,
            "target_price": 0.0,
            "trades_today": 0,
            "alpha": "NONE",
        }
        self.instruments[sym] = info

        daily_cons = TradeBarConsolidator(timedelta(days=1))

        def on_daily(_, bar):
            info["daily_closes"].Add(float(bar.Close))
            info["daily_bars"].Add(bar)

        daily_cons.DataConsolidated += on_daily
        self.SubscriptionManager.AddConsolidator(sym, daily_cons)

    def OnData(self, data):
        self._handle_rolls(data)
        if self.IsWarmingUp:
            return

        equity = self.Portfolio.TotalPortfolioValue
        self._roll_day_if_needed(equity)
        self._update_day_extremes(equity)

        if self.trailing_lock_mode == "INTRADAY" and equity > self.peak_equity:
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
        elif day_pnl >= self.day_start_equity * self.daily_profit_lock_pct and not self.day_locked:
            self.daily_profit_locks += 1
            self.day_locked = True
            self._liquidate_all("DAILY_PROFIT_LOCK")

        self._process_exits()
        self._publish_runtime(equity, dd)

    def _compute_external_stress(self):
        vixy_flag = False
        if self.vixy_sma.IsReady:
            px = self.Securities[self.vixy].Price
            sma = self.vixy_sma.Current.Value
            if px is not None and px > 0 and sma is not None and sma > 0:
                vixy_flag = (float(px) / float(sma)) >= self.ext_vixy_ratio_threshold

        rv_flag = False
        gap_flag = False
        if self.spy_ret_window.Count >= 5:
            rets = [float(self.spy_ret_window[i]) for i in range(self.spy_ret_window.Count)]
            m = sum(rets) / len(rets)
            v = sum((x - m) * (x - m) for x in rets) / max(1, len(rets) - 1)
            rv20 = (v ** 0.5) * (252.0 ** 0.5)
            rv_flag = rv20 >= self.ext_rv_threshold

        if self.spy_prev_close is not None and self.spy_prev_close > 0:
            spy_px = self.Securities[self.spy].Price
            if spy_px is not None and spy_px > 0:
                cur_gap = abs((float(spy_px) - self.spy_prev_close) / self.spy_prev_close)
                gap_flag = cur_gap >= self.ext_gap_abs_threshold

        return vixy_flag or rv_flag or gap_flag

    def _entry_index_mr(self):
        if self.IsWarmingUp or self.trailing_lock or self.day_locked:
            return
        if self._open_positions_count() >= self.max_open_positions:
            return

        stress = self._compute_external_stress()
        self._mark_stress_day(stress)
        self.external_stress_active = stress
        if stress:
            return

        for sym, info in self.instruments.items():
            if info["group"] != "IDX":
                continue
            if not self._can_enter_symbol(sym, info):
                continue

            mapped = info["future"].Mapped
            atr = info["atr"]
            if not atr.IsReady or info["daily_closes"].Count < 1:
                continue
            prev_close = float(info["daily_closes"][0])
            if prev_close <= 0:
                continue

            px = float(self.Securities[mapped].Price)
            atr_points = float(atr.Current.Value)
            if px <= 0 or atr_points <= 0:
                continue

            atr_pct = atr_points / prev_close
            gap_pct = (px - prev_close) / prev_close
            gap_th = self.idx_mr_gap_atr_mult * atr_pct
            if abs(gap_pct) > self.idx_mr_max_gap_pct:
                continue

            go_long = gap_pct <= -gap_th
            go_short = self.allow_shorts and gap_pct >= gap_th
            if not (go_long or go_short):
                continue

            stop_dist = atr_points * self.idx_mr_stop_atr_mult
            qty = self._position_size(mapped, stop_dist, self.idx_mr_risk)
            if qty < 1:
                continue

            if go_long:
                target = px + self.idx_mr_fill_frac * (prev_close - px)
                self.MarketOrder(mapped, qty, tag=f"IDX_MR_LONG {info['name']}")
                self._set_position(info, 1, px, qty, px - stop_dist, target, "IDX_MR")
            else:
                target = px - self.idx_mr_fill_frac * (px - prev_close)
                self.MarketOrder(mapped, -qty, tag=f"IDX_MR_SHORT {info['name']}")
                self._set_position(info, -1, px, qty, px + stop_dist, target, "IDX_MR")

    def _entry_index_stress(self):
        if self.IsWarmingUp or self.trailing_lock or self.day_locked:
            return
        if self._open_positions_count() >= self.max_open_positions:
            return

        stress = self._compute_external_stress()
        self._mark_stress_day(stress)
        self.external_stress_active = stress
        if not stress:
            return

        for sym, info in self.instruments.items():
            if info["group"] != "IDX":
                continue
            if not self._can_enter_symbol(sym, info):
                continue

            mapped = info["future"].Mapped
            atr = info["atr"]
            trend = info["trend"]
            if not (atr.IsReady and trend.IsReady) or info["daily_closes"].Count < 1:
                continue

            prev_close = float(info["daily_closes"][0])
            px = float(self.Securities[mapped].Price)
            opn = float(self.Securities[mapped].Open) if self.Securities[mapped].Open else 0.0
            if prev_close <= 0 or px <= 0 or opn <= 0:
                continue

            gap_pct = (px - prev_close) / prev_close
            if abs(gap_pct) < self.idx_stress_min_gap_pct:
                continue

            intraday_mom = (px - opn) / opn
            trend_val = float(trend.Current.Value)
            uptrend = px > trend_val
            downtrend = px < trend_val

            go_long = gap_pct > 0 and intraday_mom >= self.idx_stress_intraday_mom_pct and uptrend
            go_short = self.allow_shorts and gap_pct < 0 and intraday_mom <= -self.idx_stress_intraday_mom_pct and downtrend
            if not (go_long or go_short):
                continue

            atr_points = float(atr.Current.Value)
            if atr_points <= 0:
                continue
            stop_dist = atr_points * self.idx_stress_stop_atr_mult
            target_dist = atr_points * self.idx_stress_target_atr_mult
            qty = self._position_size(mapped, stop_dist, self.idx_stress_risk)
            if qty < 1:
                continue

            if go_long:
                self.MarketOrder(mapped, qty, tag=f"IDX_STRESS_LONG {info['name']}")
                self._set_position(info, 1, px, qty, px - stop_dist, px + target_dist, "IDX_STRESS")
            else:
                self.MarketOrder(mapped, -qty, tag=f"IDX_STRESS_SHORT {info['name']}")
                self._set_position(info, -1, px, qty, px + stop_dist, px - target_dist, "IDX_STRESS")

    def _entry_index_orb(self):
        if self.IsWarmingUp or self.trailing_lock or self.day_locked:
            return
        if self._open_positions_count() >= self.max_open_positions:
            return

        stress = self._compute_external_stress()
        self._mark_stress_day(stress)
        self.external_stress_active = stress
        if stress:
            return

        start = datetime(self.Time.year, self.Time.month, self.Time.day, 9, 30)
        end = start + timedelta(minutes=self.idx_or_minutes)

        for sym, info in self.instruments.items():
            if info["group"] != "IDX":
                continue
            if not self._can_enter_symbol(sym, info):
                continue

            mapped = info["future"].Mapped
            hist = self.History[TradeBar](mapped, start, end, Resolution.Minute)
            bars = list(hist) if hist is not None else []
            if len(bars) < 3:
                continue

            or_high = max(float(b.High) for b in bars)
            or_low = min(float(b.Low) for b in bars)
            if or_high <= or_low:
                continue

            atr = info["atr"]
            trend = info["trend"]
            if not (atr.IsReady and trend.IsReady):
                continue

            px = float(self.Securities[mapped].Price)
            if px <= 0:
                continue
            trend_val = float(trend.Current.Value)
            uptrend = px > trend_val
            downtrend = px < trend_val

            long_break = px > or_high * (1.0 + self.idx_or_buffer_pct)
            short_break = px < or_low * (1.0 - self.idx_or_buffer_pct)

            go_long = long_break and uptrend
            go_short = short_break and self.allow_shorts and downtrend
            if not (go_long or go_short):
                continue

            atr_points = float(atr.Current.Value)
            if atr_points <= 0:
                continue
            stop_dist = atr_points * self.idx_or_stop_atr_mult
            target_dist = atr_points * self.idx_or_target_atr_mult
            qty = self._position_size(mapped, stop_dist, self.idx_or_risk)
            if qty < 1:
                continue

            if go_long:
                self.MarketOrder(mapped, qty, tag=f"IDX_ORB_LONG {info['name']}")
                self._set_position(info, 1, px, qty, px - stop_dist, px + target_dist, "IDX_ORB")
            else:
                self.MarketOrder(mapped, -qty, tag=f"IDX_ORB_SHORT {info['name']}")
                self._set_position(info, -1, px, qty, px + stop_dist, px - target_dist, "IDX_ORB")

    def _entry_alt_breakout(self):
        if self.IsWarmingUp or self.trailing_lock or self.day_locked:
            return
        if self._open_positions_count() >= self.max_open_positions:
            return

        stress = self._compute_external_stress()
        self._mark_stress_day(stress)
        self.external_stress_active = stress
        if stress and self.alt_use_only_normal:
            return

        for sym, info in self.instruments.items():
            if info["group"] != "ALT":
                continue
            if not self._can_enter_symbol(sym, info):
                continue
            if info["daily_bars"].Count < 1:
                continue

            mapped = info["future"].Mapped
            atr = info["atr"]
            trend = info["trend"]
            if not (atr.IsReady and trend.IsReady):
                continue

            prev_bar = info["daily_bars"][0]
            prev_high = float(prev_bar.High)
            prev_low = float(prev_bar.Low)
            if prev_high <= 0 or prev_low <= 0 or prev_high <= prev_low:
                continue

            px = float(self.Securities[mapped].Price)
            trend_val = float(trend.Current.Value)
            if px <= 0 or trend_val <= 0:
                continue

            long_break = px > prev_high * (1.0 + self.alt_break_buffer_pct)
            short_break = px < prev_low * (1.0 - self.alt_break_buffer_pct)
            go_long = long_break and px > trend_val
            go_short = short_break and self.allow_shorts and px < trend_val
            if not (go_long or go_short):
                continue

            atr_points = float(atr.Current.Value)
            if atr_points <= 0:
                continue
            stop_dist = atr_points * self.alt_stop_atr_mult
            target_dist = atr_points * self.alt_target_atr_mult
            qty = self._position_size(mapped, stop_dist, self.alt_risk)
            if qty < 1:
                continue

            if go_long:
                self.MarketOrder(mapped, qty, tag=f"ALT_LONG {info['name']}")
                self._set_position(info, 1, px, qty, px - stop_dist, px + target_dist, "ALT")
            else:
                self.MarketOrder(mapped, -qty, tag=f"ALT_SHORT {info['name']}")
                self._set_position(info, -1, px, qty, px + stop_dist, px - target_dist, "ALT")

    def _can_enter_symbol(self, sym, info):
        mapped = info["future"].Mapped
        if mapped is None:
            return False
        if self._open_positions_count() >= self.max_open_positions:
            return False
        if self.Portfolio[mapped].Quantity != 0:
            return False
        if info["trades_today"] >= self.max_trades_per_symbol_day:
            return False
        if not self._has_fresh_price(mapped):
            return False
        return True

    def _set_position(self, info, direction, entry, qty, stop, target, alpha):
        info["direction"] = int(direction)
        info["entry_price"] = float(entry)
        info["entry_time"] = self.Time
        info["entry_qty"] = int(qty)
        info["stop_price"] = float(stop)
        info["target_price"] = float(target)
        info["alpha"] = alpha
        info["trades_today"] += 1

    def _process_exits(self):
        for _, info in self.instruments.items():
            mapped = info["future"].Mapped
            if mapped is None:
                continue
            qty = self.Portfolio[mapped].Quantity
            direction = int(info["direction"])
            if qty == 0 or direction == 0:
                continue
            if not self._has_fresh_price(mapped):
                continue

            px = float(self.Securities[mapped].Price)
            if px <= 0:
                continue

            hit_stop = (direction == 1 and px <= info["stop_price"]) or (direction == -1 and px >= info["stop_price"])
            hit_target = (direction == 1 and px >= info["target_price"]) or (direction == -1 and px <= info["target_price"])
            held = int((self.Time - info["entry_time"]).total_seconds() / 3600.0) if info["entry_time"] else 0
            hit_time = held >= self.max_hold_hours

            if hit_stop or hit_target or hit_time:
                reason = "STOP" if hit_stop else ("TARGET" if hit_target else "TIME")
                self.Liquidate(mapped, tag=f"{reason}_EXIT {info['name']}_{info['alpha']}")
                self._reset_position(info)

    def _has_fresh_price(self, symbol):
        if symbol is None or (not self.Securities.ContainsKey(symbol)):
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
        return last.EndTime >= self.Time - timedelta(minutes=15)

    def _position_size(self, mapped, stop_distance_points, risk_pct):
        if stop_distance_points <= 0:
            return 0
        mult = float(self.Securities[mapped].SymbolProperties.ContractMultiplier)
        if mult <= 0:
            return 0
        risk_per_contract = stop_distance_points * mult
        risk_budget = self.Portfolio.TotalPortfolioValue * max(0.0002, float(risk_pct))
        qty = int(risk_budget / risk_per_contract)
        if qty < 1:
            return 0
        return min(qty, self.max_contracts_per_trade)

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
                    self.Liquidate(old_sym, tag=f"ROLL_OUT {info['name']}")
                    if self._has_fresh_price(new_sym):
                        self.MarketOrder(new_sym, qty, tag=f"ROLL_IN {info['name']}")

    def _open_positions_count(self):
        n = 0
        for _, info in self.instruments.items():
            mapped = info["future"].Mapped
            if mapped is not None and self.Portfolio[mapped].Quantity != 0:
                n += 1
        return n

    def _reset_position(self, info):
        info["direction"] = 0
        info["entry_price"] = 0.0
        info["entry_time"] = None
        info["entry_qty"] = 0
        info["stop_price"] = 0.0
        info["target_price"] = 0.0
        info["alpha"] = "NONE"

    def _liquidate_all(self, reason):
        for _, info in self.instruments.items():
            mapped = info["future"].Mapped
            if mapped is not None and self.Portfolio[mapped].Quantity != 0:
                self.Liquidate(mapped, tag=reason)
            self._reset_position(info)

    def _flatten_eod(self):
        if self.IsWarmingUp:
            return
        self._liquidate_all("EOD_FLAT")
        self.day_locked = True

    def _roll_day_if_needed(self, equity):
        cur = self.Time.date()
        if self.day_key is None:
            self.day_key = cur
            self.day_start_equity = equity
            self.day_locked = False
            self.day_best_pnl_usd = 0.0
            self.day_worst_pnl_usd = 0.0
            for _, info in self.instruments.items():
                info["trades_today"] = 0
            self.last_equity_snapshot = equity
            return
        if cur != self.day_key:
            if self.trailing_lock_mode == "EOD":
                self.peak_equity = max(self.peak_equity, self.last_equity_snapshot)
            self._finalize_day_extremes()
            self.day_key = cur
            self.day_start_equity = equity
            self.day_locked = False
            self.day_best_pnl_usd = 0.0
            self.day_worst_pnl_usd = 0.0
            for _, info in self.instruments.items():
                info["trades_today"] = 0
        self.last_equity_snapshot = equity

    def _update_day_extremes(self, equity):
        pnl = equity - self.day_start_equity
        if pnl > self.day_best_pnl_usd:
            self.day_best_pnl_usd = pnl
        if pnl < self.day_worst_pnl_usd:
            self.day_worst_pnl_usd = pnl

    def _finalize_day_extremes(self):
        if self.day_best_pnl_usd > self.best_day_profit_usd:
            self.best_day_profit_usd = self.day_best_pnl_usd
        if self.day_worst_pnl_usd < self.worst_day_loss_usd:
            self.worst_day_loss_usd = self.day_worst_pnl_usd

    def _mark_stress_day(self, stress):
        if not stress:
            return
        if self.external_stress_last_day != self.Time.date():
            self.external_stress_days += 1
            self.external_stress_last_day = self.Time.date()

    def _publish_runtime(self, equity, dd):
        total_profit = equity - self.initial_cash
        consistency = 999.0 if total_profit <= 0 else 100.0 * self.best_day_profit_usd / total_profit
        self.SetRuntimeStatistic("Mode", "PF300")
        self.SetRuntimeStatistic("TrailingMode", self.trailing_lock_mode)
        self.SetRuntimeStatistic("ExternalStress", "1" if self.external_stress_active else "0")
        self.SetRuntimeStatistic("ExternalStressDays", str(self.external_stress_days))
        self.SetRuntimeStatistic("DailyLossBreaches", str(self.daily_loss_breaches))
        self.SetRuntimeStatistic("TrailingBreaches", str(self.trailing_breaches))
        self.SetRuntimeStatistic("BestDayUSD", f"{self.best_day_profit_usd:.2f}")
        self.SetRuntimeStatistic("WorstDayUSD", f"{self.worst_day_loss_usd:.2f}")
        self.SetRuntimeStatistic("ConsistencyPct", f"{consistency:.2f}")
        self.SetRuntimeStatistic("DrawdownPct", f"{dd * 100.0:.2f}")

    def OnEndOfAlgorithm(self):
        equity = self.Portfolio.TotalPortfolioValue
        self._finalize_day_extremes()
        dd = (self.peak_equity - equity) / self.peak_equity if self.peak_equity > 0 else 0.0
        self._publish_runtime(equity, dd)
        ret = (equity - self.initial_cash) / self.initial_cash if self.initial_cash else 0.0
        self.Log(
            f"FINAL mode=PF300 equity={equity:.2f} return_pct={ret*100.0:.2f} drawdown_pct={dd*100.0:.2f} "
            f"dbr={self.daily_loss_breaches} tbr={self.trailing_breaches} stress_days={self.external_stress_days}"
        )
