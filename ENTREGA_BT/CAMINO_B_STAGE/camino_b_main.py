# region imports
from AlgorithmImports import *
# endregion


class CaminoBDualRegime(QCAlgorithm):
    """
    Camino B
    - T1_TREND_ONLY: solo alpha trend en stress (validación STRESS-first)
    - T2_DUAL: alpha trend en stress + alpha MR en normal
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

        # Capital / brokerage
        self.initial_cash = float(self.GetParameter("initial_cash") or 50000)
        self.SetCash(self.initial_cash)
        self.SetBrokerageModel(BrokerageName.InteractiveBrokersBrokerage, AccountType.Margin)

        # Mode
        self.phase_mode = (self.GetParameter("phase_mode") or "T1_TREND_ONLY").strip().upper()
        if self.phase_mode not in ("T1_TREND_ONLY", "T2_DUAL"):
            self.phase_mode = "T1_TREND_ONLY"

        # Universe switches
        self.allow_shorts = (self.GetParameter("allow_shorts") or "1").strip().lower() not in ("0", "false", "no")
        self.trade_nq = (self.GetParameter("trade_nq") or "1").strip().lower() not in ("0", "false", "no")
        self.trade_m2k = (self.GetParameter("trade_m2k") or "0").strip().lower() not in ("0", "false", "no")
        self.trade_mym = (self.GetParameter("trade_mym") or "0").strip().lower() not in ("0", "false", "no")

        # Core indicators
        self.atr_period = int(self.GetParameter("atr_period") or 14)
        self.trend_period = int(self.GetParameter("trend_period") or 80)

        # External stress gate
        self.ext_use_vixy = (self.GetParameter("ext_use_vixy") or "1").strip().lower() not in ("0", "false", "no")
        self.ext_vixy_ratio_threshold = float(self.GetParameter("ext_vixy_ratio_threshold") or 1.03)
        self.ext_vixy_sma_period = int(self.GetParameter("ext_vixy_sma_period") or 5)
        self.ext_rv_lookback = int(self.GetParameter("ext_rv_lookback") or 20)
        self.ext_rv_threshold = float(self.GetParameter("ext_rv_threshold") or 1.0)
        self.ext_gap_lookback = int(self.GetParameter("ext_gap_lookback") or 60)
        self.ext_gap_z_threshold = float(self.GetParameter("ext_gap_z_threshold") or 99.0)
        self.ext_gap_abs_threshold = float(self.GetParameter("ext_gap_abs_threshold") or 1.0)
        self.ext_min_signals = int(self.GetParameter("ext_min_signals") or 1)
        if self.ext_min_signals < 1:
            self.ext_min_signals = 1

        # Trend alpha (stress)
        self.stress_risk_per_trade = float(self.GetParameter("stress_risk_per_trade") or 0.0040)
        self.stress_stop_atr_mult = float(self.GetParameter("stress_stop_atr_mult") or 0.80)
        self.stress_target_atr_mult = float(self.GetParameter("stress_target_atr_mult") or 1.80)
        self.stress_breakout_buffer_pct = float(self.GetParameter("stress_breakout_buffer_pct") or 0.0007)
        self.stress_min_atr_pct = float(self.GetParameter("stress_min_atr_pct") or 0.005)
        self.stress_max_atr_pct = float(self.GetParameter("stress_max_atr_pct") or 0.040)
        self.stress_disable_shorts = (self.GetParameter("stress_disable_shorts") or "0").strip().lower() not in (
            "0", "false", "no"
        )
        self.stress_max_hold_hours = int(self.GetParameter("stress_max_hold_hours") or 6)
        self.stress_max_contracts_per_trade = int(self.GetParameter("stress_max_contracts_per_trade") or 2)

        # MR alpha (normal regime)
        self.normal_risk_per_trade = float(self.GetParameter("normal_risk_per_trade") or 0.0090)
        self.normal_gap_atr_mult = float(self.GetParameter("normal_gap_atr_mult") or 0.22)
        self.normal_stop_atr_mult = float(self.GetParameter("normal_stop_atr_mult") or 0.60)
        self.normal_gap_fill_fraction = float(self.GetParameter("normal_gap_fill_fraction") or 0.70)
        self.normal_min_gap_pct = float(self.GetParameter("normal_min_gap_pct") or 0.0)
        self.normal_max_gap_pct = float(self.GetParameter("normal_max_gap_pct") or 0.0070)
        self.normal_max_hold_hours = int(self.GetParameter("normal_max_hold_hours") or 7)
        self.normal_max_atr_pct = float(self.GetParameter("normal_max_atr_pct") or 0.02)
        self.normal_use_trend_filter = (
            (self.GetParameter("normal_use_trend_filter") or "0").strip().lower() not in ("0", "false", "no")
        )
        self.normal_max_contracts_per_trade = int(self.GetParameter("normal_max_contracts_per_trade") or 5)

        # Risk controls
        self.max_open_positions = int(self.GetParameter("max_open_positions") or 3)
        self.max_trades_per_symbol_day = int(self.GetParameter("max_trades_per_symbol_day") or 1)
        self.daily_loss_limit_pct = float(self.GetParameter("daily_loss_limit_pct") or 0.018)
        self.daily_profit_lock_pct = float(self.GetParameter("daily_profit_lock_pct") or 0.040)
        self.trailing_dd_limit_pct = float(self.GetParameter("trailing_dd_limit_pct") or 0.035)
        self.trailing_lock_mode = (self.GetParameter("trailing_lock_mode") or "EOD").strip().upper()
        if self.trailing_lock_mode not in ("INTRADAY", "EOD"):
            self.trailing_lock_mode = "EOD"

        # Session
        self.entry_h = int(self.GetParameter("entry_hour") or 9)
        self.entry_m = int(self.GetParameter("entry_min") or 40)
        self.flatten_h = int(self.GetParameter("flatten_hour") or 15)
        self.flatten_m = int(self.GetParameter("flatten_min") or 58)

        # Regime proxy symbol
        self.vixy = None
        self.vixy_sma = None
        if self.ext_use_vixy:
            try:
                self.vixy = self.AddEquity("VIXY", Resolution.Minute).Symbol
                self.vixy_sma = self.SMA(self.vixy, self.ext_vixy_sma_period, Resolution.Daily)
            except Exception:
                self.vixy = None
                self.vixy_sma = None

        # SPY proxy for realized vol / gap stress flags
        self.spy = self.AddEquity("SPY", Resolution.Minute).Symbol
        rw_len = max(90, self.ext_gap_lookback + 5, self.ext_rv_lookback + 5)
        self.spy_daily = RollingWindow[TradeBar](rw_len)
        self.spy_ret_window = RollingWindow[float](max(5, self.ext_rv_lookback))
        self.spy_gap_window = RollingWindow[float](max(10, self.ext_gap_lookback))
        self.spy_prev_close = None

        spy_cons = TradeBarConsolidator(timedelta(days=1))

        def on_spy_daily(_, bar):
            if self.spy_prev_close is not None and self.spy_prev_close > 0:
                ret = (float(bar.Close) - self.spy_prev_close) / self.spy_prev_close
                gap = (float(bar.Open) - self.spy_prev_close) / self.spy_prev_close
                self.spy_ret_window.Add(float(ret))
                self.spy_gap_window.Add(float(gap))
            self.spy_prev_close = float(bar.Close)
            self.spy_daily.Add(bar)

        spy_cons.DataConsolidated += on_spy_daily
        self.SubscriptionManager.AddConsolidator(self.spy, spy_cons)

        # Instruments
        self.instruments = {}
        self._add_future(Futures.Indices.MicroSP500EMini, "MES")
        if self.trade_nq:
            self._add_future(Futures.Indices.MicroNASDAQ100EMini, "MNQ")
        if self.trade_m2k:
            self._add_future(Futures.Indices.MicroRussell2000EMini, "M2K")
        if self.trade_mym:
            self._add_future(Futures.Indices.MicroDow30EMini, "MYM")

        self.SetWarmUp(max(self.atr_period, self.trend_period, self.ext_vixy_sma_period) + 8, Resolution.Daily)

        # State
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

        self.external_stress_active = False
        self.external_stress_days = 0
        self.external_stress_last_day = None

        self.stress_trades_total = 0
        self.normal_trades_total = 0

        self.Schedule.On(self.DateRules.EveryDay(), self.TimeRules.At(self.entry_h, self.entry_m), self._daily_entry)
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
            "daily_closes": RollingWindow[float](4),
            "daily_bars": RollingWindow[TradeBar](4),
            "direction": 0,
            "entry_price": 0.0,
            "entry_time": None,
            "stop_price": 0.0,
            "target_price": 0.0,
            "hold_hours_limit": 0,
            "trades_today": 0,
            "alpha": "NONE",
        }
        self.instruments[sym] = info

        cons = TradeBarConsolidator(timedelta(days=1))

        def on_daily_bar(_, bar):
            info["daily_closes"].Add(float(bar.Close))
            info["daily_bars"].Add(bar)

        cons.DataConsolidated += on_daily_bar
        self.SubscriptionManager.AddConsolidator(sym, cons)

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
            self._publish_runtime_stats(equity, dd)
            return

        day_pnl = equity - self.day_start_equity
        daily_loss_limit_usd = self.day_start_equity * self.daily_loss_limit_pct
        daily_profit_lock_usd = self.day_start_equity * self.daily_profit_lock_pct

        if day_pnl <= -daily_loss_limit_usd and not self.day_locked:
            self.daily_loss_breaches += 1
            self.day_locked = True
            self._liquidate_all("DAILY_LOSS_LOCK")
        elif day_pnl >= daily_profit_lock_usd and not self.day_locked:
            self.daily_profit_locks += 1
            self.day_locked = True
            self._liquidate_all("DAILY_PROFIT_LOCK")

        self._process_exits()
        self._publish_runtime_stats(equity, dd)

    def _daily_entry(self):
        if self.IsWarmingUp or self.trailing_lock or self.day_locked:
            return
        if self._open_positions_count() >= self.max_open_positions:
            return

        stress_now = self._is_external_stress()
        self.external_stress_active = stress_now
        if stress_now and self.external_stress_last_day != self.Time.date():
            self.external_stress_days += 1
            self.external_stress_last_day = self.Time.date()

        for sym, info in self.instruments.items():
            mapped = info["future"].Mapped
            if mapped is None:
                continue
            if info["trades_today"] >= self.max_trades_per_symbol_day:
                continue
            if self.Portfolio[mapped].Quantity != 0:
                continue
            if not self._security_has_fresh_price(mapped):
                continue
            if self._open_positions_count() >= self.max_open_positions:
                break

            sig = self._build_signal(sym, info, stress_now)
            if sig is None:
                continue

            qty = self._position_size(sig["mapped"], sig["stop_dist"], sig["risk_per_trade"], sig["max_contracts"])
            if qty < 1:
                continue

            if sig["direction"] == 1:
                self.MarketOrder(mapped, qty, tag=f"L_{sig['alpha']}_{info['name']}")
            else:
                self.MarketOrder(mapped, -qty, tag=f"S_{sig['alpha']}_{info['name']}")

            info["direction"] = sig["direction"]
            info["entry_price"] = sig["entry"]
            info["entry_time"] = self.Time
            info["stop_price"] = sig["stop"]
            info["target_price"] = sig["target"]
            info["hold_hours_limit"] = sig["hold_hours"]
            info["trades_today"] += 1
            info["alpha"] = sig["alpha"]

            if sig["alpha"] == "STRESS_TREND":
                self.stress_trades_total += 1
            elif sig["alpha"] == "NORMAL_MR":
                self.normal_trades_total += 1

    def _build_signal(self, sym, info, stress_now):
        mapped = info["future"].Mapped
        atr = info["atr"]
        trend = info["trend"]
        if not (atr.IsReady and trend.IsReady):
            return None
        if info["daily_closes"].Count < 2 or info["daily_bars"].Count < 2:
            return None

        prev_close = float(info["daily_closes"][0])
        prev_bar = info["daily_bars"][0]
        if prev_close <= 0:
            return None

        cont_price = self.Securities[sym].Price
        if cont_price <= 0:
            return None

        atr_points = atr.Current.Value
        if atr_points <= 0:
            return None
        atr_pct = atr_points / prev_close

        # T1/T2 stress branch
        if stress_now:
            if atr_pct < self.stress_min_atr_pct or atr_pct > self.stress_max_atr_pct:
                return None
            prev_high = float(prev_bar.High)
            prev_low = float(prev_bar.Low)
            if prev_high <= prev_low or prev_low <= 0:
                return None

            trend_val = trend.Current.Value
            if trend_val <= 0:
                return None
            uptrend = cont_price > trend_val
            downtrend = cont_price < trend_val

            long_break = cont_price >= prev_high * (1.0 + self.stress_breakout_buffer_pct)
            short_break = cont_price <= prev_low * (1.0 - self.stress_breakout_buffer_pct)

            go_long = long_break and uptrend
            go_short = short_break and downtrend and self.allow_shorts and (not self.stress_disable_shorts)

            if not (go_long or go_short):
                return None

            stop_dist = atr_points * self.stress_stop_atr_mult
            target_dist = atr_points * self.stress_target_atr_mult
            if stop_dist <= 0 or target_dist <= 0:
                return None

            direction = 1 if go_long else -1
            return {
                "alpha": "STRESS_TREND",
                "direction": direction,
                "entry": float(cont_price),
                "stop_dist": float(stop_dist),
                "stop": float(cont_price - stop_dist if direction == 1 else cont_price + stop_dist),
                "target": float(cont_price + target_dist if direction == 1 else cont_price - target_dist),
                "hold_hours": self.stress_max_hold_hours,
                "risk_per_trade": self.stress_risk_per_trade,
                "max_contracts": self.stress_max_contracts_per_trade,
                "mapped": mapped,
            }

        # T1 ends here: no normal trading
        if self.phase_mode == "T1_TREND_ONLY":
            return None

        # T2 normal branch
        if atr_pct > self.normal_max_atr_pct:
            return None

        gap_pct = (cont_price - prev_close) / prev_close
        if abs(gap_pct) < self.normal_min_gap_pct or abs(gap_pct) > self.normal_max_gap_pct:
            return None

        threshold = self.normal_gap_atr_mult * atr_pct
        trend_val = trend.Current.Value
        if trend_val <= 0:
            return None
        uptrend = cont_price > trend_val
        downtrend = cont_price < trend_val

        go_long = gap_pct <= -threshold and ((not self.normal_use_trend_filter) or uptrend)
        go_short = gap_pct >= threshold and ((not self.normal_use_trend_filter) or downtrend) and self.allow_shorts
        if not (go_long or go_short):
            return None

        stop_dist = atr_points * self.normal_stop_atr_mult
        if stop_dist <= 0:
            return None

        direction = 1 if go_long else -1
        if direction == 1:
            target = cont_price + self.normal_gap_fill_fraction * (prev_close - cont_price)
        else:
            target = cont_price - self.normal_gap_fill_fraction * (cont_price - prev_close)

        return {
            "alpha": "NORMAL_MR",
            "direction": direction,
            "entry": float(cont_price),
            "stop_dist": float(stop_dist),
            "stop": float(cont_price - stop_dist if direction == 1 else cont_price + stop_dist),
            "target": float(target),
            "hold_hours": self.normal_max_hold_hours,
            "risk_per_trade": self.normal_risk_per_trade,
            "max_contracts": self.normal_max_contracts_per_trade,
            "mapped": mapped,
        }

    def _is_external_stress(self):
        vixy_flag = False
        if self.vixy is not None and self.vixy_sma is not None and self.vixy_sma.IsReady:
            px = self.Securities[self.vixy].Price
            sma = self.vixy_sma.Current.Value
            if px is not None and px > 0 and sma is not None and sma > 0:
                vixy_flag = (float(px) / float(sma)) >= self.ext_vixy_ratio_threshold

        base_signals = 1 if vixy_flag else 0

        if self.spy_prev_close is None or self.spy_prev_close <= 0:
            return base_signals >= self.ext_min_signals
        if self.spy_ret_window.Count < max(5, self.ext_rv_lookback - 1):
            return base_signals >= self.ext_min_signals
        if self.spy_gap_window.Count < max(10, self.ext_gap_lookback - 1):
            return base_signals >= self.ext_min_signals

        spy_px = self.Securities[self.spy].Price
        if spy_px is None or spy_px <= 0:
            return base_signals >= self.ext_min_signals

        rets = [float(self.spy_ret_window[i]) for i in range(self.spy_ret_window.Count)]
        gaps = [float(self.spy_gap_window[i]) for i in range(self.spy_gap_window.Count)]
        if len(rets) < 2 or len(gaps) < 2:
            return base_signals >= self.ext_min_signals

        mean_ret = sum(rets) / len(rets)
        var_ret = sum((r - mean_ret) * (r - mean_ret) for r in rets) / max(1, (len(rets) - 1))
        rv20 = (var_ret ** 0.5) * (252.0 ** 0.5)

        cur_gap = (float(spy_px) - self.spy_prev_close) / self.spy_prev_close
        mean_gap = sum(gaps) / len(gaps)
        var_gap = sum((g - mean_gap) * (g - mean_gap) for g in gaps) / max(1, (len(gaps) - 1))
        std_gap = var_gap ** 0.5
        gap_z = 0.0 if std_gap <= 1e-12 else (cur_gap - mean_gap) / std_gap

        rv_flag = rv20 >= self.ext_rv_threshold
        gapz_flag = abs(gap_z) >= self.ext_gap_z_threshold
        gapabs_flag = abs(cur_gap) >= self.ext_gap_abs_threshold

        signals = base_signals
        if rv_flag:
            signals += 1
        if gapz_flag:
            signals += 1
        if gapabs_flag:
            signals += 1
        return signals >= self.ext_min_signals

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

            hit_stop = (direction == 1 and cont_price <= info["stop_price"]) or (
                direction == -1 and cont_price >= info["stop_price"]
            )
            hit_target = (direction == 1 and cont_price >= info["target_price"]) or (
                direction == -1 and cont_price <= info["target_price"]
            )
            held_hours = int((self.Time - info["entry_time"]).total_seconds() / 3600.0) if info["entry_time"] else 0
            hit_time = held_hours >= int(info.get("hold_hours_limit") or 6)

            if hit_stop or hit_target or hit_time:
                reason = "STOP" if hit_stop else ("TARGET" if hit_target else "TIME")
                self.Liquidate(mapped, tag=f"{reason}_EXIT_{info['name']}_{info['alpha']}")
                self._reset_position(info)

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
        return last.EndTime >= self.Time - timedelta(minutes=15)

    def _position_size(self, mapped, stop_distance_points, risk_per_trade, max_contracts):
        if stop_distance_points <= 0:
            return 0
        multiplier = float(self.Securities[mapped].SymbolProperties.ContractMultiplier)
        if multiplier <= 0:
            return 0
        risk_per_contract = stop_distance_points * multiplier
        risk_budget = self.Portfolio.TotalPortfolioValue * max(0.0001, float(risk_per_trade))
        qty = int(risk_budget / risk_per_contract)
        if qty < 1:
            return 0
        return min(qty, max(1, int(max_contracts)))

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
            self._reset_position(info)

    def _reset_position(self, info):
        info["direction"] = 0
        info["entry_price"] = 0.0
        info["entry_time"] = None
        info["stop_price"] = 0.0
        info["target_price"] = 0.0
        info["hold_hours_limit"] = 0
        info["alpha"] = "NONE"

    def _flatten_eod(self):
        if self.IsWarmingUp:
            return
        self._liquidate_all("EOD_FLAT")
        self.day_locked = True

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
            return

        if current_day != self.day_key:
            if self.trailing_lock_mode == "EOD":
                self.peak_equity = max(self.peak_equity, equity)
            self._finalize_day_extremes()
            self.day_key = current_day
            self.day_start_equity = equity
            self.day_locked = False
            self.day_best_pnl_usd = 0.0
            self.day_worst_pnl_usd = 0.0
            for _, info in self.instruments.items():
                info["trades_today"] = 0

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

    def _publish_runtime_stats(self, equity, dd):
        total_profit = equity - self.initial_cash
        consistency_pct = 999.0 if total_profit <= 0 else 100.0 * self.best_day_profit_usd / total_profit
        vixy_ready = 0
        vixy_ratio = None
        if self.vixy is not None and self.vixy_sma is not None and self.vixy_sma.IsReady:
            px = self.Securities[self.vixy].Price
            sma = self.vixy_sma.Current.Value
            if px is not None and px > 0 and sma is not None and sma > 0:
                vixy_ready = 1
                vixy_ratio = float(px) / float(sma)
        self.SetRuntimeStatistic("PhaseMode", self.phase_mode)
        self.SetRuntimeStatistic("ExternalStress", "1" if self.external_stress_active else "0")
        self.SetRuntimeStatistic("ExternalStressDays", str(self.external_stress_days))
        self.SetRuntimeStatistic("VIXYReady", str(vixy_ready))
        if vixy_ratio is not None:
            self.SetRuntimeStatistic("VIXYRatio", f"{vixy_ratio:.3f}")
        self.SetRuntimeStatistic("StressTrades", str(self.stress_trades_total))
        self.SetRuntimeStatistic("NormalTrades", str(self.normal_trades_total))
        self.SetRuntimeStatistic("DailyLossBreaches", str(self.daily_loss_breaches))
        self.SetRuntimeStatistic("TrailingBreaches", str(self.trailing_breaches))
        self.SetRuntimeStatistic("BestDayUSD", f"{self.best_day_profit_usd:.2f}")
        self.SetRuntimeStatistic("WorstDayUSD", f"{self.worst_day_loss_usd:.2f}")
        self.SetRuntimeStatistic("ConsistencyPct", f"{consistency_pct:.2f}")
        self.SetRuntimeStatistic("DrawdownPct", f"{dd * 100.0:.2f}")

    def OnEndOfAlgorithm(self):
        equity = self.Portfolio.TotalPortfolioValue
        self._finalize_day_extremes()
        dd = (self.peak_equity - equity) / self.peak_equity if self.peak_equity > 0 else 0.0
        self._publish_runtime_stats(equity, dd)
        ret = (equity - self.initial_cash) / self.initial_cash if self.initial_cash else 0.0
        self.Log(
            f"FINAL mode={self.phase_mode} ret={ret*100.0:.3f}% dd={dd*100.0:.3f}% "
            f"dbr={self.daily_loss_breaches} tbr={self.trailing_breaches} "
            f"stress_trades={self.stress_trades_total} normal_trades={self.normal_trades_total}"
        )
