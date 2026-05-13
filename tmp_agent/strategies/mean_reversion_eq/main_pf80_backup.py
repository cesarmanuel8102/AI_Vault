# region imports
from AlgorithmImports import *
# endregion


class PropFundingMicroFuturesV1(QCAlgorithm):
    """
    Prop-ready micro futures intraday gap reversion.

    Key constraints:
    - Futures-only (MES/MNQ)
    - Single intraday entry per symbol/day
    - Mandatory end-of-day flatten
    - Daily loss lock + trailing drawdown lock
    """

    def Initialize(self):
        # --- Dates ---
        start_year = int(self.GetParameter("start_year") or 2022)
        start_month = int(self.GetParameter("start_month") or 1)
        start_day = int(self.GetParameter("start_day") or 1)
        end_year = int(self.GetParameter("end_year") or 2026)
        end_month = int(self.GetParameter("end_month") or 3)
        end_day = int(self.GetParameter("end_day") or 31)
        self.SetStartDate(start_year, start_month, start_day)
        self.SetEndDate(end_year, end_month, end_day)
        self.SetTimeZone(TimeZones.NewYork)

        # --- Capital & broker ---
        self.initial_cash = float(self.GetParameter("initial_cash") or 50000)
        self.SetCash(self.initial_cash)
        self.SetBrokerageModel(BrokerageName.InteractiveBrokersBrokerage, AccountType.Margin)

        # --- Strategy params ---
        self.allow_shorts = (self.GetParameter("allow_shorts") or "1").strip().lower() not in ("0", "false", "no")
        self.trade_nq = (self.GetParameter("trade_nq") or "1").strip().lower() not in ("0", "false", "no")
        self.trade_m2k = (self.GetParameter("trade_m2k") or "0").strip().lower() not in ("0", "false", "no")
        self.trade_mym = (self.GetParameter("trade_mym") or "0").strip().lower() not in ("0", "false", "no")
        self.use_trend_filter = (self.GetParameter("use_trend_filter") or "0").strip().lower() not in ("0", "false", "no")
        self.regime_mode = (self.GetParameter("regime_mode") or "BASE").strip().upper()
        if self.regime_mode not in ("BASE", "PF70", "PF71", "PF80"):
            self.regime_mode = "BASE"

        self.atr_period = int(self.GetParameter("atr_period") or 14)
        self.trend_period = int(self.GetParameter("trend_period") or 80)
        self.gap_atr_mult = float(self.GetParameter("gap_atr_mult") or 0.22)
        self.stop_atr_mult = float(self.GetParameter("stop_atr_mult") or 0.60)
        self.gap_fill_fraction = float(self.GetParameter("gap_fill_fraction") or 0.70)
        self.min_gap_entry_pct = float(self.GetParameter("min_gap_entry_pct") or 0.0)
        self.max_gap_entry_pct = float(self.GetParameter("max_gap_entry_pct") or 0.0065)
        self.max_hold_hours = int(self.GetParameter("max_hold_hours") or 7)
        self.max_atr_pct = float(self.GetParameter("max_atr_pct") or 0.013)
        self.high_vol_atr_pct = float(self.GetParameter("high_vol_atr_pct") or 0.009)
        self.high_vol_risk_mult = float(self.GetParameter("high_vol_risk_mult") or 0.30)
        self.skip_high_vol_entries = (self.GetParameter("skip_high_vol_entries") or "0").strip().lower() not in ("0", "false", "no")
        self.high_vol_trend_mode = (self.GetParameter("high_vol_trend_mode") or "0").strip().lower() not in ("0", "false", "no")
        self.high_vol_stop_atr_mult = float(self.GetParameter("high_vol_stop_atr_mult") or 0.70)
        self.high_vol_target_atr_mult = float(self.GetParameter("high_vol_target_atr_mult") or 1.00)
        self.max_trend_dev_pct = float(self.GetParameter("max_trend_dev_pct") or 1.00)
        # Stress overlay: optional defensive layer, activated only in extreme regime.
        self.stress_overlay_enabled = (self.GetParameter("stress_overlay_enabled") or "0").strip().lower() not in ("0", "false", "no")
        self.stress_atr_pct = float(self.GetParameter("stress_atr_pct") or 0.0115)
        self.stress_gap_pct = float(self.GetParameter("stress_gap_pct") or 0.0100)
        self.stress_trend_dev_pct = float(self.GetParameter("stress_trend_dev_pct") or 0.08)
        self.stress_min_gap_entry_pct = float(self.GetParameter("stress_min_gap_entry_pct") or 0.0080)
        self.stress_max_gap_entry_pct = float(self.GetParameter("stress_max_gap_entry_pct") or 0.0300)
        self.stress_use_trend_mode = (self.GetParameter("stress_use_trend_mode") or "1").strip().lower() not in ("0", "false", "no")
        self.stress_stop_atr_mult = float(self.GetParameter("stress_stop_atr_mult") or 0.80)
        self.stress_target_atr_mult = float(self.GetParameter("stress_target_atr_mult") or 1.20)
        self.stress_risk_mult = float(self.GetParameter("stress_risk_mult") or 0.30)
        self.stress_skip_entries = (self.GetParameter("stress_skip_entries") or "0").strip().lower() not in ("0", "false", "no")
        self.stress_disable_shorts = (self.GetParameter("stress_disable_shorts") or "0").strip().lower() not in ("0", "false", "no")
        self.stress_max_hold_hours = int(self.GetParameter("stress_max_hold_hours") or 3)
        self.stress_override_core_filters = (self.GetParameter("stress_override_core_filters") or "1").strip().lower() not in ("0", "false", "no")
        # External regime gate (PF80): market-state detector exogenous to MR alpha.
        self.ext_rv_lookback = int(self.GetParameter("ext_rv_lookback") or 20)
        self.ext_rv_threshold = float(self.GetParameter("ext_rv_threshold") or 0.26)
        self.ext_gap_lookback = int(self.GetParameter("ext_gap_lookback") or 60)
        self.ext_gap_z_threshold = float(self.GetParameter("ext_gap_z_threshold") or 1.80)
        self.ext_gap_abs_threshold = float(self.GetParameter("ext_gap_abs_threshold") or 0.009)
        self.ext_use_vix = (self.GetParameter("ext_use_vix") or "1").strip().lower() not in ("0", "false", "no")
        self.ext_vix_threshold = float(self.GetParameter("ext_vix_threshold") or 26.0)

        # --- Risk params ---
        self.risk_per_trade = float(self.GetParameter("risk_per_trade") or 0.0095)
        self.max_contracts_per_trade = int(self.GetParameter("max_contracts_per_trade") or 2)
        self.max_open_positions = int(self.GetParameter("max_open_positions") or 2)
        self.daily_loss_limit_pct = float(self.GetParameter("daily_loss_limit_pct") or 0.018)
        self.daily_profit_lock_pct = float(self.GetParameter("daily_profit_lock_pct") or 0.030)
        self.trailing_dd_limit_pct = float(self.GetParameter("trailing_dd_limit_pct") or 0.035)

        # --- Schedule / session ---
        self.entry_h = int(self.GetParameter("entry_hour") or 10)
        self.entry_m = int(self.GetParameter("entry_min") or 5)
        self.flatten_h = int(self.GetParameter("flatten_hour") or 15)
        self.flatten_m = int(self.GetParameter("flatten_min") or 58)

        self.instruments = {}
        self._add_future(Futures.Indices.MicroSP500EMini, "MES")
        if self.trade_nq:
            self._add_future(Futures.Indices.MicroNASDAQ100EMini, "MNQ")
        if self.trade_m2k:
            self._add_future(Futures.Indices.MicroRussell2000EMini, "M2K")
        if self.trade_mym:
            self._add_future(Futures.Indices.MicroDow30EMini, "MYM")

        warmup_bars = max(self.atr_period, self.trend_period) + 5
        self.SetWarmUp(warmup_bars, Resolution.Daily)

        # --- Portfolio / risk state ---
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

        # External market regime proxy: SPY daily returns and overnight gaps.
        self.spy = self.AddEquity("SPY", Resolution.Minute).Symbol
        self.vix = None
        if self.ext_use_vix:
            try:
                self.vix = self.AddIndex("VIX", Resolution.Minute, Market.USA).Symbol
            except Exception:
                self.vix = None
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
            "daily_closes": RollingWindow[float](3),
            "direction": 0,
            "entry_price": 0.0,
            "entry_time": None,
            "stop_price": 0.0,
            "target_price": 0.0,
            "trades_today": 0,
            "hold_hours_limit": self.max_hold_hours,
        }
        self.instruments[sym] = info

        consolidator = TradeBarConsolidator(timedelta(days=1))

        def on_daily_bar(_, bar):
            info["daily_closes"].Add(float(bar.Close))

        consolidator.DataConsolidated += on_daily_bar
        self.SubscriptionManager.AddConsolidator(sym, consolidator)

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
        external_stress_now = self._is_external_stress()
        self.external_stress_active = external_stress_now
        if external_stress_now and self.external_stress_last_day != self.Time.date():
            self.external_stress_days += 1
            self.external_stress_last_day = self.Time.date()
        if self.regime_mode == "PF80" and external_stress_now:
            # PF80: regime avoidance based on exogenous state variables.
            return

        for sym, info in self.instruments.items():
            mapped = info["future"].Mapped
            if mapped is None:
                continue
            if self.Portfolio[mapped].Quantity != 0:
                continue
            if info["trades_today"] >= 1:
                continue
            if self._open_positions_count() >= self.max_open_positions:
                break

            atr = info["atr"]
            trend = info["trend"]
            if not (atr.IsReady and trend.IsReady):
                continue
            if info["daily_closes"].Count < 1:
                continue

            prev_close = info["daily_closes"][0]
            if prev_close <= 0:
                continue

            cont_price = self.Securities[sym].Price
            if cont_price <= 0:
                continue

            atr_points = atr.Current.Value
            if atr_points <= 0:
                continue

            gap_pct = (cont_price - prev_close) / prev_close
            atr_pct = atr_points / prev_close
            if atr_pct <= 0:
                continue

            gap_threshold = self.gap_atr_mult * atr_pct
            trend_val = trend.Current.Value
            if trend_val <= 0:
                continue
            trend_dev = abs((cont_price - trend_val) / trend_val)

            stress_mode = self._is_stress_mode(atr_pct, gap_pct, trend_dev)
            if self.regime_mode == "PF80":
                stress_mode = False
            if stress_mode and self.regime_mode == "PF70":
                # PF70: hard kill in stress regime.
                continue
            bypass_core_filters = stress_mode and self.stress_override_core_filters
            if atr_pct > self.max_atr_pct and not bypass_core_filters:
                continue
            if trend_dev > self.max_trend_dev_pct and not bypass_core_filters:
                continue
            high_vol = atr_pct >= self.high_vol_atr_pct
            if self.skip_high_vol_entries and high_vol and not bypass_core_filters:
                continue
            if stress_mode and self.stress_skip_entries and self.regime_mode != "PF71":
                continue

            if stress_mode:
                if abs(gap_pct) < self.stress_min_gap_entry_pct:
                    continue
                if abs(gap_pct) > self.stress_max_gap_entry_pct:
                    continue
            else:
                if abs(gap_pct) < self.min_gap_entry_pct:
                    continue
                if abs(gap_pct) > self.max_gap_entry_pct:
                    continue

            allow_shorts_now = self.allow_shorts and (not (stress_mode and self.stress_disable_shorts))
            hold_limit = self.stress_max_hold_hours if stress_mode else self.max_hold_hours

            uptrend = cont_price > trend_val
            downtrend = cont_price < trend_val

            if stress_mode and self.regime_mode == "PF71" and self.stress_use_trend_mode:
                go_long = gap_pct >= self.stress_min_gap_entry_pct and (not self.use_trend_filter or uptrend)
                go_short = allow_shorts_now and gap_pct <= -self.stress_min_gap_entry_pct and (not self.use_trend_filter or downtrend)
                stop_dist = atr_points * self.stress_stop_atr_mult
                target_dist = atr_points * self.stress_target_atr_mult
            elif high_vol and self.high_vol_trend_mode:
                # In high-volatility regime, follow directional impulse with trend.
                go_long = gap_pct >= gap_threshold and (not self.use_trend_filter or uptrend)
                go_short = allow_shorts_now and gap_pct <= -gap_threshold and (not self.use_trend_filter or downtrend)
                stop_dist = atr_points * self.high_vol_stop_atr_mult
                target_dist = atr_points * self.high_vol_target_atr_mult
            else:
                go_long = gap_pct <= -gap_threshold and (not self.use_trend_filter or uptrend)
                go_short = allow_shorts_now and gap_pct >= gap_threshold and (not self.use_trend_filter or downtrend)
                stop_dist = atr_points * self.stop_atr_mult
                target_dist = None
            if not (go_long or go_short):
                continue

            risk_mult = self.high_vol_risk_mult if atr_pct >= self.high_vol_atr_pct else 1.0
            if stress_mode:
                risk_mult *= self.stress_risk_mult
            qty = self._position_size(mapped, stop_dist, risk_mult)
            if qty < 1:
                continue

            if go_long:
                tag_mode = f"{self.regime_mode}_{'STRESS' if stress_mode else 'NORM'}"
                self.MarketOrder(mapped, qty, tag=f"L_{tag_mode} {info['name']} gap={gap_pct:.3%}")
                info["direction"] = 1
                info["entry_price"] = cont_price
                info["entry_time"] = self.Time
                info["stop_price"] = cont_price - stop_dist
                if target_dist is None:
                    info["target_price"] = cont_price + self.gap_fill_fraction * (prev_close - cont_price)
                else:
                    info["target_price"] = cont_price + target_dist
                info["hold_hours_limit"] = hold_limit
            elif go_short:
                tag_mode = f"{self.regime_mode}_{'STRESS' if stress_mode else 'NORM'}"
                self.MarketOrder(mapped, -qty, tag=f"S_{tag_mode} {info['name']} gap={gap_pct:.3%}")
                info["direction"] = -1
                info["entry_price"] = cont_price
                info["entry_time"] = self.Time
                info["stop_price"] = cont_price + stop_dist
                if target_dist is None:
                    info["target_price"] = cont_price - self.gap_fill_fraction * (cont_price - prev_close)
                else:
                    info["target_price"] = cont_price - target_dist
                info["hold_hours_limit"] = hold_limit

            info["trades_today"] += 1

    def _is_stress_mode(self, atr_pct, gap_pct, trend_dev):
        if not self.stress_overlay_enabled:
            return False
        return (
            atr_pct >= self.stress_atr_pct
            or abs(gap_pct) >= self.stress_gap_pct
            or trend_dev >= self.stress_trend_dev_pct
        )

    def _is_external_stress(self):
        vix_flag = False
        if self.vix is not None:
            vix_px = self.Securities[self.vix].Price
            if vix_px is not None and vix_px > 0:
                vix_flag = float(vix_px) >= self.ext_vix_threshold

        if self.spy_prev_close is None or self.spy_prev_close <= 0:
            return vix_flag
        if self.spy_ret_window.Count < max(5, self.ext_rv_lookback - 1):
            return vix_flag
        if self.spy_gap_window.Count < max(10, self.ext_gap_lookback - 1):
            return vix_flag
        spy_px = self.Securities[self.spy].Price
        if spy_px is None or spy_px <= 0:
            return vix_flag

        rets = [float(self.spy_ret_window[i]) for i in range(self.spy_ret_window.Count)]
        gaps = [float(self.spy_gap_window[i]) for i in range(self.spy_gap_window.Count)]
        if len(rets) < 2 or len(gaps) < 2:
            return False

        mean_ret = sum(rets) / len(rets)
        var_ret = sum((r - mean_ret) * (r - mean_ret) for r in rets) / (len(rets) - 1)
        rv20 = (var_ret ** 0.5) * (252.0 ** 0.5)

        cur_gap = (float(spy_px) - self.spy_prev_close) / self.spy_prev_close
        mean_gap = sum(gaps) / len(gaps)
        var_gap = sum((g - mean_gap) * (g - mean_gap) for g in gaps) / (len(gaps) - 1)
        std_gap = var_gap ** 0.5
        gap_z = 0.0 if std_gap <= 1e-12 else (cur_gap - mean_gap) / std_gap

        return vix_flag or (rv20 >= self.ext_rv_threshold) or (abs(gap_z) >= self.ext_gap_z_threshold) or (abs(cur_gap) >= self.ext_gap_abs_threshold)

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
            hold_limit = int(info.get("hold_hours_limit", self.max_hold_hours) or self.max_hold_hours)
            hit_time = held_hours >= hold_limit

            if hit_stop or hit_target or hit_time:
                reason = "STOP" if hit_stop else ("TARGET" if hit_target else "TIME")
                self.Liquidate(mapped, tag=f"{reason}_EXIT {info['name']}")
                info["direction"] = 0
                info["entry_price"] = 0.0
                info["entry_time"] = None
                info["stop_price"] = 0.0
                info["target_price"] = 0.0
                info["hold_hours_limit"] = self.max_hold_hours

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
                    self.MarketOrder(new_sym, qty, tag=f"ROLL_IN {info['name']}")

    def _position_size(self, mapped, stop_distance_points, risk_mult=1.0):
        if stop_distance_points <= 0:
            return 0
        multiplier = float(self.Securities[mapped].SymbolProperties.ContractMultiplier)
        if multiplier <= 0:
            return 0
        risk_per_contract = stop_distance_points * multiplier
        risk_budget = self.Portfolio.TotalPortfolioValue * self.risk_per_trade * max(0.1, float(risk_mult))
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
            info["direction"] = 0
            info["entry_price"] = 0.0
            info["entry_time"] = None
            info["stop_price"] = 0.0
            info["target_price"] = 0.0
            info["hold_hours_limit"] = self.max_hold_hours

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
        self.SetRuntimeStatistic("Mode", self.regime_mode)
        self.SetRuntimeStatistic("ExternalStress", "1" if self.external_stress_active else "0")
        self.SetRuntimeStatistic("ExternalStressDays", str(self.external_stress_days))
        self.SetRuntimeStatistic("DailyLossBreaches", str(self.daily_loss_breaches))
        self.SetRuntimeStatistic("TrailingBreaches", str(self.trailing_breaches))
        self.SetRuntimeStatistic("BestDayUSD", f"{self.best_day_profit_usd:.2f}")
        self.SetRuntimeStatistic("WorstDayUSD", f"{self.worst_day_loss_usd:.2f}")
        self.SetRuntimeStatistic("ConsistencyPct", f"{consistency_pct:.2f}")
        self.SetRuntimeStatistic("DrawdownPct", f"{dd * 100.0:.2f}")

    def OnEndOfAlgorithm(self):
        equity = self.Portfolio.TotalPortfolioValue
        self._finalize_day_extremes()
        total_profit = equity - self.initial_cash
        ret = total_profit / self.initial_cash if self.initial_cash else 0.0
        dd = (self.peak_equity - equity) / self.peak_equity if self.peak_equity > 0 else 0.0
        consistency_pct = 999.0 if total_profit <= 0 else 100.0 * self.best_day_profit_usd / total_profit

        self.SetRuntimeStatistic("Mode", self.regime_mode)
        self.SetRuntimeStatistic("ExternalStress", "1" if self.external_stress_active else "0")
        self.SetRuntimeStatistic("ExternalStressDays", str(self.external_stress_days))
        self.SetRuntimeStatistic("DailyLossBreaches", str(self.daily_loss_breaches))
        self.SetRuntimeStatistic("TrailingBreaches", str(self.trailing_breaches))
        self.SetRuntimeStatistic("BestDayUSD", f"{self.best_day_profit_usd:.2f}")
        self.SetRuntimeStatistic("WorstDayUSD", f"{self.worst_day_loss_usd:.2f}")
        self.SetRuntimeStatistic("ConsistencyPct", f"{consistency_pct:.2f}")
        self.SetRuntimeStatistic("DrawdownPct", f"{dd * 100.0:.2f}")

        self.Log(
            "FINAL "
            f"mode={self.regime_mode} "
            f"external_stress_days={self.external_stress_days} "
            f"equity={equity:.2f} return_pct={ret * 100.0:.2f} drawdown_pct={dd * 100.0:.2f} "
            f"daily_loss_breaches={self.daily_loss_breaches} trailing_breaches={self.trailing_breaches} "
            f"best_day_usd={self.best_day_profit_usd:.2f} worst_day_usd={self.worst_day_loss_usd:.2f} "
            f"consistency_pct={consistency_pct:.2f}"
        )
