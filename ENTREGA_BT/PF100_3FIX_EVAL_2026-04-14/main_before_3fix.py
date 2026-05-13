from AlgorithmImports import *

class PropFundingMicroFuturesV1(QCAlgorithm):
    def Initialize(self):
        start_year = int(self.GetParameter("start_year") or 2022)
        start_month = int(self.GetParameter("start_month") or 1)
        start_day = int(self.GetParameter("start_day") or 1)
        end_year = int(self.GetParameter("end_year") or 2026)
        end_month = int(self.GetParameter("end_month") or 3)
        end_day = int(self.GetParameter("end_day") or 31)
        self.SetStartDate(start_year, start_month, start_day)
        self.SetEndDate(end_year, end_month, end_day)
        self.SetTimeZone(TimeZones.NewYork)

        self.initial_cash = float(self.GetParameter("initial_cash") or 50000)
        self.SetCash(self.initial_cash)
        self.SetBrokerageModel(BrokerageName.InteractiveBrokersBrokerage, AccountType.Margin)

        self.allow_shorts = (self.GetParameter("allow_shorts") or "1").strip().lower() not in ("0", "false", "no")
        self.trade_nq = (self.GetParameter("trade_nq") or "1").strip().lower() not in ("0", "false", "no")
        self.trade_m2k = (self.GetParameter("trade_m2k") or "0").strip().lower() not in ("0", "false", "no")
        self.trade_mym = (self.GetParameter("trade_mym") or "0").strip().lower() not in ("0", "false", "no")
        self.use_trend_filter = (self.GetParameter("use_trend_filter") or "0").strip().lower() not in ("0", "false", "no")
        self.regime_mode = (self.GetParameter("regime_mode") or "BASE").strip().upper()
        if self.regime_mode not in ("BASE", "PF70", "PF71", "PF80", "PF81", "PF100"):
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
        self.ext_rv_lookback = int(self.GetParameter("ext_rv_lookback") or 20)
        self.ext_rv_threshold = float(self.GetParameter("ext_rv_threshold") or 0.26)
        self.ext_gap_lookback = int(self.GetParameter("ext_gap_lookback") or 60)
        self.ext_gap_z_threshold = float(self.GetParameter("ext_gap_z_threshold") or 1.80)
        self.ext_gap_abs_threshold = float(self.GetParameter("ext_gap_abs_threshold") or 0.009)
        self.ext_use_vix = (self.GetParameter("ext_use_vix") or "1").strip().lower() not in ("0", "false", "no")
        self.ext_vix_threshold = float(self.GetParameter("ext_vix_threshold") or 26.0)
        self.ext_use_vixy = (self.GetParameter("ext_use_vixy") or "0").strip().lower() not in ("0", "false", "no")
        self.ext_vixy_ratio_threshold = float(self.GetParameter("ext_vixy_ratio_threshold") or 1.12)
        self.ext_vixy_sma_period = int(self.GetParameter("ext_vixy_sma_period") or 20)
        self.ext_min_signals = int(self.GetParameter("ext_min_signals") or 1)
        if self.ext_min_signals < 1:
            self.ext_min_signals = 1

        self.pf81_stress_min_gap_entry_pct = float(self.GetParameter("pf81_stress_min_gap_entry_pct") or 0.0075)
        self.pf81_stress_max_gap_entry_pct = float(self.GetParameter("pf81_stress_max_gap_entry_pct") or 0.0350)
        self.pf81_stress_stop_atr_mult = float(self.GetParameter("pf81_stress_stop_atr_mult") or 0.90)
        self.pf81_stress_target_atr_mult = float(self.GetParameter("pf81_stress_target_atr_mult") or 1.45)
        self.pf81_stress_risk_mult = float(self.GetParameter("pf81_stress_risk_mult") or 0.35)
        self.pf81_stress_max_hold_hours = int(self.GetParameter("pf81_stress_max_hold_hours") or 6)
        self.pf81_stress_intraday_confirm = (
            (self.GetParameter("pf81_stress_intraday_confirm") or "1").strip().lower() not in ("0", "false", "no")
        )
        self.pf81_stress_intraday_mom_pct = float(self.GetParameter("pf81_stress_intraday_mom_pct") or 0.0012)
        self.pf81_stress_use_trend_filter = (
            (self.GetParameter("pf81_stress_use_trend_filter") or "1").strip().lower() not in ("0", "false", "no")
        )
        self.pf81_stress_disable_shorts = (
            (self.GetParameter("pf81_stress_disable_shorts") or "0").strip().lower() not in ("0", "false", "no")
        )
        self.pf100_stress_risk_per_trade = float(
            self.GetParameter("pf1_risk") or self.GetParameter("pf100_stress_risk_per_trade") or 0.0025
        )
        self.pf100_stress_atr_stop = float(
            self.GetParameter("pf1_stop") or self.GetParameter("pf100_stress_atr_stop") or 1.20
        )
        self.pf100_stress_atr_target = float(
            self.GetParameter("pf1_tgt") or self.GetParameter("pf100_stress_atr_target") or 2.50
        )
        self.pf100_stress_min_range_pct = float(
            self.GetParameter("pf1_rng") or self.GetParameter("pf100_stress_min_range_pct") or 0.010
        )
        self.pf100_stress_breakout_buffer = float(
            self.GetParameter("pf1_buf") or self.GetParameter("pf100_stress_breakout_buffer") or 0.001
        )
        self.pf100_stress_gap_fallback = (
            (self.GetParameter("pf1_gap_fb") or self.GetParameter("pf100_stress_gap_fallback") or "1")
            .strip()
            .lower()
            not in ("0", "false", "no")
        )
        self.pf100_stress_min_gap_pct = float(
            self.GetParameter("pf1_gap_thr") or self.GetParameter("pf100_stress_min_gap_pct") or 0.004
        )
        self.pf100_stress_max_trades_per_day = int(
            self.GetParameter("pf1_tpd") or self.GetParameter("pf100_stress_max_trades_per_day") or 1
        )
        self.pf100_stress_intraday_confirm = (
            (self.GetParameter("pf1_mom_on") or self.GetParameter("pf100_stress_intraday_confirm") or "1")
            .strip()
            .lower()
            not in ("0", "false", "no")
        )
        self.pf100_stress_intraday_mom_pct = float(
            self.GetParameter("pf1_mom") or self.GetParameter("pf100_stress_intraday_mom_pct") or 0.001
        )
        self.pf100_stress_disable_shorts = (
            (self.GetParameter("pf1_no_shorts") or self.GetParameter("pf100_stress_disable_shorts") or "0")
            .strip()
            .lower()
            not in ("0", "false", "no")
        )
        self.pf100_stress_max_hold_hours = int(
            self.GetParameter("pf1_hold") or self.GetParameter("pf100_stress_max_hold_hours") or 8
        )
        self.pf100_second_trade_requires_win = (
            (self.GetParameter("pf1_w2win") or self.GetParameter("pf100_second_trade_requires_win") or "1")
            .strip()
            .lower()
            not in ("0", "false", "no")
        )
        self.pf100_partial_enabled = (
            (self.GetParameter("pf1_pt_on") or self.GetParameter("pf100_partial_enabled") or "0")
            .strip()
            .lower()
            not in ("0", "false", "no")
        )
        self.pf100_partial_fraction = float(
            self.GetParameter("pf1_ptf") or self.GetParameter("pf100_partial_fraction") or 0.50
        )
        self.pf100_partial_tp_r = float(
            self.GetParameter("pf1_t1r") or self.GetParameter("pf100_partial_tp_r") or 1.50
        )
        self.pf100_runner_trail_enabled = (
            (self.GetParameter("pf1_tr_on") or self.GetParameter("pf100_runner_trail_enabled") or "0")
            .strip()
            .lower()
            not in ("0", "false", "no")
        )
        self.pf100_runner_trail_start_r = float(
            self.GetParameter("pf1_trr") or self.GetParameter("pf100_runner_trail_start_r") or 1.00
        )
        self.pf100_runner_trail_atr_mult = float(
            self.GetParameter("pf1_tra") or self.GetParameter("pf100_runner_trail_atr_mult") or 0.90
        )
        self.pf100_disable_target_after_partial = (
            (self.GetParameter("pf1_toff") or self.GetParameter("pf100_disable_target_after_partial") or "1")
            .strip()
            .lower()
            not in ("0", "false", "no")
        )
        self.pf100_quality_filter_enabled = (
            (self.GetParameter("pf1_q_on") or self.GetParameter("pf100_quality_filter_enabled") or "0")
            .strip()
            .lower()
            not in ("0", "false", "no")
        )
        self.pf100_quality_range_exp_mult = float(
            self.GetParameter("pf1_qm") or self.GetParameter("pf100_quality_range_exp_mult") or 1.20
        )
        self.pf100_quality_min_prev_range_pct = float(
            self.GetParameter("pf1_qmin") or self.GetParameter("pf100_quality_min_prev_range_pct") or 0.0030
        )
        self.pf100_max_contracts_per_trade = int(
            self.GetParameter("pf1_maxc")
            or self.GetParameter("pf100_max_contracts_per_trade")
            or self.GetParameter("max_contracts_per_trade")
            or 5
        )

        self.profile_mode = (self.GetParameter("profile_mode") or "PASS").strip().upper()
        if self.profile_mode not in ("PASS", "PAYOUT_SAFE", "PAYOUT_AGGR"):
            self.profile_mode = "PASS"
        self.risk_per_trade = float(self.GetParameter("risk_per_trade") or 0.0095)
        self.max_contracts_per_trade = int(self.GetParameter("max_contracts_per_trade") or 2)
        self.max_open_positions = int(self.GetParameter("max_open_positions") or 2)
        self.max_trades_per_symbol_day = max(1, int(self.GetParameter("max_trades_per_symbol_day") or 1))
        self.daily_loss_limit_pct = float(self.GetParameter("daily_loss_limit_pct") or 0.018)
        self.daily_profit_lock_pct = float(self.GetParameter("daily_profit_lock_pct") or 0.030)
        self.trailing_dd_limit_pct = float(self.GetParameter("trailing_dd_limit_pct") or 0.035)
        self.trailing_lock_mode = (self.GetParameter("trailing_lock_mode") or "INTRADAY").strip().upper()
        if self.trailing_lock_mode not in ("INTRADAY", "EOD"):
            self.trailing_lock_mode = "INTRADAY"
        self.dynamic_risk_enabled = (self.GetParameter("dynamic_risk_enabled") or "0").strip().lower() not in (
            "0",
            "false",
            "no",
        )
        self.dynamic_risk_floor_mult = float(self.GetParameter("dynamic_risk_floor_mult") or 0.65)
        self.dynamic_risk_ceiling_mult = float(self.GetParameter("dynamic_risk_ceiling_mult") or 1.35)
        self.dynamic_risk_soft_dd_pct = float(self.GetParameter("dynamic_risk_soft_dd_pct") or 0.010)
        self.dynamic_risk_hard_dd_pct = float(self.GetParameter("dynamic_risk_hard_dd_pct") or 0.028)
        self.dynamic_risk_profit_boost_pct = float(self.GetParameter("dynamic_risk_profit_boost_pct") or 0.006)
        self.dynamic_risk_profit_boost_mult = float(self.GetParameter("dynamic_risk_profit_boost_mult") or 1.10)

        self.entry_h = int(self.GetParameter("entry_hour") or 10)
        self.entry_m = int(self.GetParameter("entry_min") or 5)
        self.second_entry_enabled = (self.GetParameter("second_entry_enabled") or "0").strip().lower() not in (
            "0",
            "false",
            "no",
        )
        self.second_entry_h = int(self.GetParameter("second_entry_hour") or 11)
        self.second_entry_m = int(self.GetParameter("second_entry_min") or 20)
        self.second_entry_breakout_enabled = (
            (self.GetParameter("second_entry_breakout_enabled") or "1").strip().lower() not in ("0", "false", "no")
        )
        self.second_mom_entry_pct = float(self.GetParameter("second_mom_entry_pct") or 0.0035)
        self.second_stop_atr_mult = float(self.GetParameter("second_stop_atr_mult") or 0.65)
        self.second_target_atr_mult = float(self.GetParameter("second_target_atr_mult") or 1.10)
        self.second_risk_mult = float(self.GetParameter("second_risk_mult") or 0.60)
        self.second_max_hold_hours = int(self.GetParameter("second_max_hold_hours") or 4)
        self.second_use_trend_filter = (
            (self.GetParameter("second_use_trend_filter") or "1").strip().lower() not in ("0", "false", "no")
        )
        self.second_max_atr_pct = float(self.GetParameter("second_max_atr_pct") or 0.020)
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
        self.price_guard_skips = 0
        self.last_dynamic_risk_mult = 1.0
        self.last_equity_snapshot = self.initial_cash
        self.stress_trades_today = 0
        self.pf100_trades_total = 0
        self.pf100_second_trade_entries = 0
        self.pf100_second_trade_blocked = 0
        self.pf100_partial_fills = 0
        self.pf100_runner_trail_updates = 0
        self.pf100_quality_blocked = 0

        self.spy = self.AddEquity("SPY", Resolution.Minute).Symbol
        self.vix = None
        if self.ext_use_vix:
            try:
                self.vix = self.AddIndex("VIX", Resolution.Minute, Market.USA).Symbol
            except Exception:
                self.vix = None
        self.vixy = None
        self.vixy_sma = None
        if self.ext_use_vixy:
            try:
                self.vixy = self.AddEquity("VIXY", Resolution.Minute).Symbol
                self.vixy_sma = self.SMA(self.vixy, self.ext_vixy_sma_period, Resolution.Daily)
            except Exception:
                self.vixy = None
                self.vixy_sma = None
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
        if self.second_entry_enabled:
            self.Schedule.On(
                self.DateRules.EveryDay(),
                self.TimeRules.At(self.second_entry_h, self.second_entry_m),
                self._daily_entry_secondary,
            )
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
            "daily_bars": RollingWindow[TradeBar](3),
            "direction": 0,
            "entry_price": 0.0,
            "entry_time": None,
            "entry_qty": 0,
            "stop_price": 0.0,
            "target_price": 0.0,
            "initial_stop_dist": 0.0,
            "partial_done": False,
            "trades_today": 0,
            "first_trade_closed_today": False,
            "first_trade_won_today": False,
            "hold_hours_limit": self.max_hold_hours,
            "active_alpha": "NONE",
        }
        self.instruments[sym] = info

        consolidator = TradeBarConsolidator(timedelta(days=1))

        def on_daily_bar(_, bar):
            info["daily_closes"].Add(float(bar.Close))
            info["daily_bars"].Add(bar)

        consolidator.DataConsolidated += on_daily_bar
        self.SubscriptionManager.AddConsolidator(sym, consolidator)

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
        external_stress_now = self._is_external_stress()
        self.external_stress_active = external_stress_now
        if external_stress_now and self.external_stress_last_day != self.Time.date():
            self.external_stress_days += 1
            self.external_stress_last_day = self.Time.date()
        if self.regime_mode == "PF80" and external_stress_now:
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
            if not self._can_take_trade(info):
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

            if self.regime_mode == "PF100" and (not external_stress_now):
                if not self._pf100_pass_quality(info):
                    self.pf100_quality_blocked += 1
                    continue

            if self.regime_mode == "PF100" and external_stress_now:
                signal = self._check_pf100_signal(sym, info, atr_points)
                if signal is None:
                    continue
                qty = self._position_size_risk_pct(
                    mapped,
                    signal["stop_dist"],
                    self.pf100_stress_risk_per_trade,
                    self.pf100_max_contracts_per_trade,
                )
                if qty < 1:
                    continue
                if signal["direction"] == 1:
                    self.MarketOrder(mapped, qty, tag=f"L_PF100_STRESS {info['name']}")
                else:
                    self.MarketOrder(mapped, -qty, tag=f"S_PF100_STRESS {info['name']}")
                info["direction"] = signal["direction"]
                info["entry_price"] = signal["entry"]
                info["entry_time"] = self.Time
                info["entry_qty"] = int(qty)
                info["stop_price"] = signal["stop"]
                info["target_price"] = signal["target"]
                info["initial_stop_dist"] = float(signal["stop_dist"])
                info["partial_done"] = False
                info["hold_hours_limit"] = signal["hold_hours_limit"]
                info["active_alpha"] = "PF100_STRESS"
                if self.regime_mode == "PF100" and info["trades_today"] == 1:
                    self.pf100_second_trade_entries += 1
                info["trades_today"] += 1
                self.stress_trades_today += 1
                self.pf100_trades_total += 1
                continue

            if self.regime_mode == "PF81" and external_stress_now:
                trend_val = trend.Current.Value
                if trend_val <= 0:
                    continue
                uptrend = cont_price > trend_val
                downtrend = cont_price < trend_val

                if abs(gap_pct) < self.pf81_stress_min_gap_entry_pct:
                    continue
                if abs(gap_pct) > self.pf81_stress_max_gap_entry_pct:
                    continue

                sec_mapped = self.Securities[mapped]
                open_price = sec_mapped.Open
                if open_price is None or open_price <= 0:
                    continue
                intraday_mom = (cont_price - float(open_price)) / float(open_price)

                go_long = gap_pct > 0
                go_short = gap_pct < 0 and self.allow_shorts and (not self.pf81_stress_disable_shorts)
                if self.pf81_stress_use_trend_filter:
                    if go_long and not uptrend:
                        go_long = False
                    if go_short and not downtrend:
                        go_short = False
                if self.pf81_stress_intraday_confirm:
                    if go_long and intraday_mom < self.pf81_stress_intraday_mom_pct:
                        go_long = False
                    if go_short and intraday_mom > -self.pf81_stress_intraday_mom_pct:
                        go_short = False
                if not (go_long or go_short):
                    continue

                stop_dist = atr_points * self.pf81_stress_stop_atr_mult
                target_dist = atr_points * self.pf81_stress_target_atr_mult
                risk_mult = self.pf81_stress_risk_mult
                qty = self._position_size(mapped, stop_dist, risk_mult)
                if qty < 1:
                    continue

                if go_long:
                    self.MarketOrder(mapped, qty, tag=f"L_PF81_STRESS {info['name']} gap={gap_pct:.3%}")
                    info["direction"] = 1
                    info["entry_price"] = cont_price
                    info["entry_time"] = self.Time
                    info["entry_qty"] = int(qty)
                    info["stop_price"] = cont_price - stop_dist
                    info["target_price"] = cont_price + target_dist
                    info["initial_stop_dist"] = float(stop_dist)
                    info["partial_done"] = False
                    info["hold_hours_limit"] = self.pf81_stress_max_hold_hours
                    info["active_alpha"] = "PF81_STRESS"
                elif go_short:
                    self.MarketOrder(mapped, -qty, tag=f"S_PF81_STRESS {info['name']} gap={gap_pct:.3%}")
                    info["direction"] = -1
                    info["entry_price"] = cont_price
                    info["entry_time"] = self.Time
                    info["entry_qty"] = int(qty)
                    info["stop_price"] = cont_price + stop_dist
                    info["target_price"] = cont_price - target_dist
                    info["initial_stop_dist"] = float(stop_dist)
                    info["partial_done"] = False
                    info["hold_hours_limit"] = self.pf81_stress_max_hold_hours
                    info["active_alpha"] = "PF81_STRESS"

                info["trades_today"] += 1
                continue

            gap_threshold = self.gap_atr_mult * atr_pct
            trend_val = trend.Current.Value
            if trend_val <= 0:
                continue
            trend_dev = abs((cont_price - trend_val) / trend_val)

            stress_mode = self._is_stress_mode(atr_pct, gap_pct, trend_dev)
            if self.regime_mode == "PF80":
                stress_mode = False
            if self.regime_mode in ("PF81", "PF100"):
                stress_mode = False
            if stress_mode and self.regime_mode == "PF70":
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
                info["entry_qty"] = int(qty)
                info["stop_price"] = cont_price - stop_dist
                if target_dist is None:
                    info["target_price"] = cont_price + self.gap_fill_fraction * (prev_close - cont_price)
                else:
                    info["target_price"] = cont_price + target_dist
                info["initial_stop_dist"] = float(stop_dist)
                info["partial_done"] = False
                info["hold_hours_limit"] = hold_limit
                info["active_alpha"] = "MR"
            elif go_short:
                tag_mode = f"{self.regime_mode}_{'STRESS' if stress_mode else 'NORM'}"
                self.MarketOrder(mapped, -qty, tag=f"S_{tag_mode} {info['name']} gap={gap_pct:.3%}")
                info["direction"] = -1
                info["entry_price"] = cont_price
                info["entry_time"] = self.Time
                info["entry_qty"] = int(qty)
                info["stop_price"] = cont_price + stop_dist
                if target_dist is None:
                    info["target_price"] = cont_price - self.gap_fill_fraction * (cont_price - prev_close)
                else:
                    info["target_price"] = cont_price - target_dist
                info["initial_stop_dist"] = float(stop_dist)
                info["partial_done"] = False
                info["hold_hours_limit"] = hold_limit
                info["active_alpha"] = "MR"

            info["trades_today"] += 1
            if self.regime_mode == "PF100" and info["trades_today"] == 2:
                self.pf100_second_trade_entries += 1

    def _daily_entry_secondary(self):
        if not self.second_entry_enabled:
            return
        if self.regime_mode == "PF100" and self._is_external_stress():
            return
        if self.second_entry_breakout_enabled:
            self._second_entry_breakout()
            return
        self._daily_entry()

    def _second_entry_breakout(self):
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
            if not self._can_take_trade(info):
                continue
            if self._open_positions_count() >= self.max_open_positions:
                break

            atr = info["atr"]
            trend = info["trend"]
            if not (atr.IsReady and trend.IsReady):
                continue
            if info["daily_closes"].Count < 1:
                continue

            sec = self.Securities[mapped]
            cont_price = sec.Price
            if cont_price <= 0:
                continue
            open_price = sec.Open
            if open_price is None or open_price <= 0:
                continue

            prev_close = info["daily_closes"][0]
            if prev_close <= 0:
                continue
            atr_points = atr.Current.Value
            if atr_points <= 0:
                continue

            atr_pct = atr_points / prev_close
            if atr_pct <= 0 or atr_pct > self.second_max_atr_pct:
                continue

            if self.regime_mode == "PF100" and (not external_stress_now):
                if not self._pf100_pass_quality(info):
                    self.pf100_quality_blocked += 1
                    continue

            intraday_move_pct = (cont_price - open_price) / open_price
            if abs(intraday_move_pct) < self.second_mom_entry_pct:
                continue

            trend_val = trend.Current.Value
            if trend_val <= 0:
                continue
            uptrend = cont_price > trend_val
            downtrend = cont_price < trend_val

            go_long = intraday_move_pct > 0
            go_short = intraday_move_pct < 0 and self.allow_shorts
            if self.second_use_trend_filter:
                if go_long and not uptrend:
                    go_long = False
                if go_short and not downtrend:
                    go_short = False
            if not (go_long or go_short):
                continue

            stop_dist = atr_points * self.second_stop_atr_mult
            target_dist = atr_points * self.second_target_atr_mult
            risk_mult = self.second_risk_mult * (self.high_vol_risk_mult if atr_pct >= self.high_vol_atr_pct else 1.0)
            qty = self._position_size(mapped, stop_dist, risk_mult)
            if qty < 1:
                continue

            if go_long:
                self.MarketOrder(mapped, qty, tag=f"L2_{self.regime_mode}_BRK {info['name']} mom={intraday_move_pct:.3%}")
                info["direction"] = 1
                info["entry_price"] = cont_price
                info["entry_time"] = self.Time
                info["entry_qty"] = int(qty)
                info["stop_price"] = cont_price - stop_dist
                info["target_price"] = cont_price + target_dist
                info["initial_stop_dist"] = float(stop_dist)
                info["partial_done"] = False
                info["hold_hours_limit"] = self.second_max_hold_hours
                info["active_alpha"] = "L2_BRK"
            elif go_short:
                self.MarketOrder(mapped, -qty, tag=f"S2_{self.regime_mode}_BRK {info['name']} mom={intraday_move_pct:.3%}")
                info["direction"] = -1
                info["entry_price"] = cont_price
                info["entry_time"] = self.Time
                info["entry_qty"] = int(qty)
                info["stop_price"] = cont_price + stop_dist
                info["target_price"] = cont_price - target_dist
                info["initial_stop_dist"] = float(stop_dist)
                info["partial_done"] = False
                info["hold_hours_limit"] = self.second_max_hold_hours
                info["active_alpha"] = "L2_BRK"

            info["trades_today"] += 1
            if self.regime_mode == "PF100" and info["trades_today"] == 2:
                self.pf100_second_trade_entries += 1

    def _can_take_trade(self, info):
        if info["trades_today"] >= self.max_trades_per_symbol_day:
            return False
        if self.regime_mode != "PF100" or not self.pf100_second_trade_requires_win:
            return True
        if info["trades_today"] == 0:
            return True
        if info["trades_today"] == 1:
            if not info.get("first_trade_closed_today", False):
                return False
            ok = bool(info.get("first_trade_won_today", False))
            if not ok:
                self.pf100_second_trade_blocked += 1
            return ok
        return True

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
        vixy_flag = False
        if self.vixy is not None and self.vixy_sma is not None and self.vixy_sma.IsReady:
            vixy_px = self.Securities[self.vixy].Price
            vixy_sma = self.vixy_sma.Current.Value
            if vixy_px is not None and vixy_px > 0 and vixy_sma is not None and vixy_sma > 0:
                vixy_flag = (float(vixy_px) / float(vixy_sma)) >= self.ext_vixy_ratio_threshold

        base_signals = 0
        if vix_flag:
            base_signals += 1
        if vixy_flag:
            base_signals += 1

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
            return False

        mean_ret = sum(rets) / len(rets)
        var_ret = sum((r - mean_ret) * (r - mean_ret) for r in rets) / (len(rets) - 1)
        rv20 = (var_ret ** 0.5) * (252.0 ** 0.5)

        cur_gap = (float(spy_px) - self.spy_prev_close) / self.spy_prev_close
        mean_gap = sum(gaps) / len(gaps)
        var_gap = sum((g - mean_gap) * (g - mean_gap) for g in gaps) / (len(gaps) - 1)
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

    def _check_pf100_signal(self, sym, info, atr_points):
        if self.stress_trades_today >= self.pf100_stress_max_trades_per_day:
            return None
        if info["daily_bars"].Count < 1 or info["daily_closes"].Count < 1:
            return None
        prev_bar = info["daily_bars"][0]
        prev_close = float(info["daily_closes"][0])
        prev_high = float(prev_bar.High)
        prev_low = float(prev_bar.Low)
        if prev_close <= 0 or prev_high <= 0 or prev_low <= 0 or prev_high <= prev_low:
            return None
        range_pct = (prev_high - prev_low) / prev_close
        if range_pct < self.pf100_stress_min_range_pct:
            return None
        sec = self.Securities[sym]
        current_price = float(sec.Price)
        if current_price <= 0:
            return None
        open_price = float(sec.Open) if sec.Open is not None else 0.0
        if open_price <= 0:
            return None
        intraday_mom = (current_price - open_price) / open_price

        long_break = current_price > prev_high * (1.0 + self.pf100_stress_breakout_buffer)
        short_break = current_price < prev_low * (1.0 - self.pf100_stress_breakout_buffer)
        if self.pf100_stress_gap_fallback and not (long_break or short_break):
            gap_pct = (current_price - prev_close) / prev_close
            long_break = gap_pct >= self.pf100_stress_min_gap_pct
            short_break = gap_pct <= -self.pf100_stress_min_gap_pct
        if self.pf100_stress_disable_shorts:
            short_break = False
        if self.pf100_stress_intraday_confirm:
            if long_break and intraday_mom < self.pf100_stress_intraday_mom_pct:
                long_break = False
            if short_break and intraday_mom > -self.pf100_stress_intraday_mom_pct:
                short_break = False
        if not (long_break or short_break):
            return None
        stop_dist = atr_points * self.pf100_stress_atr_stop
        if stop_dist <= 0:
            return None
        target_dist = atr_points * self.pf100_stress_atr_target
        if long_break:
            return {
                "direction": 1,
                "entry": current_price,
                "stop_dist": stop_dist,
                "stop": current_price - stop_dist,
                "target": current_price + target_dist,
                "hold_hours_limit": self.pf100_stress_max_hold_hours,
            }
        return {
            "direction": -1,
            "entry": current_price,
            "stop_dist": stop_dist,
            "stop": current_price + stop_dist,
            "target": current_price - target_dist,
            "hold_hours_limit": self.pf100_stress_max_hold_hours,
        }

    def _pf100_try_partial(self, mapped, info, qty, cont_price):
        if not self.pf100_partial_enabled:
            return
        if info.get("partial_done", False):
            return
        if info.get("entry_qty", 0) < 2 or abs(qty) < 2:
            return
        direction = int(info.get("direction", 0))
        if direction == 0:
            return
        entry = float(info.get("entry_price", 0.0) or 0.0)
        r = float(info.get("initial_stop_dist", 0.0) or 0.0)
        if entry <= 0 or r <= 0:
            return

        tp_r = max(0.1, float(self.pf100_partial_tp_r))
        tp_price = entry + direction * tp_r * r
        reached = (direction == 1 and cont_price >= tp_price) or (direction == -1 and cont_price <= tp_price)
        if not reached:
            return

        frac = min(0.9, max(0.1, float(self.pf100_partial_fraction)))
        close_qty = int(round(info["entry_qty"] * frac))
        close_qty = max(1, close_qty)
        close_qty = min(close_qty, abs(qty) - 1)
        if close_qty < 1:
            return
        if not self._security_has_fresh_price(mapped):
            self.price_guard_skips += 1
            return

        if direction == 1:
            self.MarketOrder(mapped, -close_qty, tag="PF100_PARTIAL")
            info["stop_price"] = max(float(info["stop_price"]), entry)
        else:
            self.MarketOrder(mapped, close_qty, tag="PF100_PARTIAL")
            info["stop_price"] = min(float(info["stop_price"]), entry)

        info["partial_done"] = True
        self.pf100_partial_fills += 1

        if self.pf100_disable_target_after_partial:
            info["target_price"] = 1e30 if direction == 1 else -1e30

    def _pf100_update_runner_trail(self, info, cont_price):
        if not self.pf100_runner_trail_enabled:
            return
        direction = int(info.get("direction", 0))
        if direction == 0:
            return
        entry = float(info.get("entry_price", 0.0) or 0.0)
        r = float(info.get("initial_stop_dist", 0.0) or 0.0)
        if entry <= 0 or r <= 0:
            return

        open_r = (cont_price - entry) / r if direction == 1 else (entry - cont_price) / r
        if open_r < max(0.1, float(self.pf100_runner_trail_start_r)):
            return

        atr = info.get("atr")
        atr_points = atr.Current.Value if atr is not None and atr.IsReady else 0.0
        if atr_points <= 0:
            return
        trail_dist = atr_points * max(0.1, float(self.pf100_runner_trail_atr_mult))

        if direction == 1:
            new_stop = cont_price - trail_dist
            if new_stop > float(info["stop_price"]):
                info["stop_price"] = new_stop
                self.pf100_runner_trail_updates += 1
        else:
            new_stop = cont_price + trail_dist
            if new_stop < float(info["stop_price"]):
                info["stop_price"] = new_stop
                self.pf100_runner_trail_updates += 1

    def _pf100_pass_quality(self, info):
        if not self.pf100_quality_filter_enabled:
            return True
        if info["daily_bars"].Count < 2 or info["daily_closes"].Count < 2:
            return False

        prev_bar = info["daily_bars"][0]
        prev2_bar = info["daily_bars"][1]
        prev_close = float(info["daily_closes"][0]) if info["daily_closes"][0] is not None else 0.0
        prev2_close = float(info["daily_closes"][1]) if info["daily_closes"][1] is not None else 0.0
        if prev_close <= 0 or prev2_close <= 0:
            return False

        prev_range_pct = (float(prev_bar.High) - float(prev_bar.Low)) / prev_close
        prev2_range_pct = (float(prev2_bar.High) - float(prev2_bar.Low)) / prev2_close
        if prev_range_pct <= 0 or prev2_range_pct <= 0:
            return False
        if prev_range_pct < max(0.0005, float(self.pf100_quality_min_prev_range_pct)):
            return False
        return prev_range_pct >= prev2_range_pct * max(1.0, float(self.pf100_quality_range_exp_mult))

    def _process_exits(self):
        for sym, info in self.instruments.items():
            mapped = info["future"].Mapped
            if mapped is None:
                continue
            qty = self.Portfolio[mapped].Quantity
            direction = info["direction"]
            if qty == 0 or direction == 0:
                continue

            if not self._security_has_fresh_price(mapped):
                self.price_guard_skips += 1
                continue

            cont_price = self.Securities[sym].Price
            if cont_price <= 0:
                continue

            if self.regime_mode == "PF100":
                self._pf100_try_partial(mapped, info, qty, cont_price)
                self._pf100_update_runner_trail(info, cont_price)

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
                realized_win = (direction == 1 and cont_price >= info["entry_price"]) or (
                    direction == -1 and cont_price <= info["entry_price"]
                )
                self.Liquidate(mapped, tag=f"{reason}_EXIT {info['name']}")
                if info["trades_today"] == 1 and not info["first_trade_closed_today"]:
                    info["first_trade_closed_today"] = True
                    info["first_trade_won_today"] = bool(realized_win)
                info["direction"] = 0
                info["entry_price"] = 0.0
                info["entry_time"] = None
                info["entry_qty"] = 0
                info["stop_price"] = 0.0
                info["target_price"] = 0.0
                info["initial_stop_dist"] = 0.0
                info["partial_done"] = False
                info["hold_hours_limit"] = self.max_hold_hours
                info["active_alpha"] = "NONE"

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
                    if self._security_has_fresh_price(new_sym):
                        self.MarketOrder(new_sym, qty, tag=f"ROLL_IN {info['name']}")
                    else:
                        self.price_guard_skips += 1

    def _security_has_fresh_price(self, symbol):
        if symbol is None:
            return False
        if not self.Securities.ContainsKey(symbol):
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

    def _position_size(self, mapped, stop_distance_points, risk_mult=1.0):
        if stop_distance_points <= 0:
            return 0
        multiplier = float(self.Securities[mapped].SymbolProperties.ContractMultiplier)
        if multiplier <= 0:
            return 0
        risk_per_contract = stop_distance_points * multiplier
        dyn_mult = self._dynamic_risk_multiplier()
        self.last_dynamic_risk_mult = dyn_mult
        risk_budget = (
            self.Portfolio.TotalPortfolioValue
            * self.risk_per_trade
            * max(0.1, float(risk_mult))
            * max(0.2, float(dyn_mult))
        )
        qty = int(risk_budget / risk_per_contract)
        if qty < 1:
            return 0
        return min(qty, self.max_contracts_per_trade)

    def _position_size_risk_pct(self, mapped, stop_distance_points, risk_pct, max_contracts):
        if stop_distance_points <= 0:
            return 0
        multiplier = float(self.Securities[mapped].SymbolProperties.ContractMultiplier)
        if multiplier <= 0:
            return 0
        risk_per_contract = stop_distance_points * multiplier
        dyn_mult = self._dynamic_risk_multiplier()
        self.last_dynamic_risk_mult = dyn_mult
        rpct = max(0.0001, float(risk_pct))
        risk_budget = self.Portfolio.TotalPortfolioValue * rpct * max(0.2, float(dyn_mult))
        qty = int(risk_budget / risk_per_contract)
        if qty < 1:
            return 0
        cap = max(1, int(max_contracts))
        return min(qty, cap)

    def _dynamic_risk_multiplier(self):
        if not self.dynamic_risk_enabled or self.peak_equity <= 0:
            return 1.0

        equity = self.Portfolio.TotalPortfolioValue
        dd = (self.peak_equity - equity) / self.peak_equity if self.peak_equity > 0 else 0.0
        floor_mult = max(0.20, float(self.dynamic_risk_floor_mult))
        ceil_mult = max(floor_mult, float(self.dynamic_risk_ceiling_mult))
        soft_dd = max(0.0, float(self.dynamic_risk_soft_dd_pct))
        hard_dd = max(soft_dd + 1e-6, float(self.dynamic_risk_hard_dd_pct))

        if dd <= soft_dd:
            dd_mult = ceil_mult
        elif dd >= hard_dd:
            dd_mult = floor_mult
        else:
            mix = (dd - soft_dd) / (hard_dd - soft_dd)
            dd_mult = ceil_mult + (floor_mult - ceil_mult) * mix

        profit_mult = 1.0
        if self.day_start_equity > 0 and self.day_key == self.Time.date():
            day_pnl_pct = (equity - self.day_start_equity) / self.day_start_equity
            if day_pnl_pct >= self.dynamic_risk_profit_boost_pct:
                profit_mult = max(1.0, float(self.dynamic_risk_profit_boost_mult))

        return min(ceil_mult * 1.25, max(floor_mult * 0.80, dd_mult * profit_mult))

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
            info["entry_qty"] = 0
            info["stop_price"] = 0.0
            info["target_price"] = 0.0
            info["initial_stop_dist"] = 0.0
            info["partial_done"] = False
            info["hold_hours_limit"] = self.max_hold_hours
            info["active_alpha"] = "NONE"

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
                info["first_trade_closed_today"] = False
                info["first_trade_won_today"] = False
            self.stress_trades_today = 0
            self.last_equity_snapshot = equity
            return

        if current_day != self.day_key:
            if self.trailing_lock_mode == "EOD":
                self.peak_equity = max(self.peak_equity, self.last_equity_snapshot)
            self._finalize_day_extremes()
            self.day_key = current_day
            self.day_start_equity = equity
            self.day_locked = False
            self.day_best_pnl_usd = 0.0
            self.day_worst_pnl_usd = 0.0
            for _, info in self.instruments.items():
                info["trades_today"] = 0
                info["first_trade_closed_today"] = False
                info["first_trade_won_today"] = False
            self.stress_trades_today = 0
        self.last_equity_snapshot = equity

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
        self.SetRuntimeStatistic("Profile", self.profile_mode)
        self.SetRuntimeStatistic("TrailingMode", self.trailing_lock_mode)
        self.SetRuntimeStatistic("ExternalStress", "1" if self.external_stress_active else "0")
        self.SetRuntimeStatistic("ExternalStressDays", str(self.external_stress_days))
        self.SetRuntimeStatistic("PF100StressTrades", str(self.stress_trades_today))
        self.SetRuntimeStatistic("PF100TradesTotal", str(self.pf100_trades_total))
        self.SetRuntimeStatistic("PF100SecondEntries", str(self.pf100_second_trade_entries))
        self.SetRuntimeStatistic("PF100SecondBlocked", str(self.pf100_second_trade_blocked))
        self.SetRuntimeStatistic("PF100PartialFills", str(self.pf100_partial_fills))
        self.SetRuntimeStatistic("PF100TrailUpdates", str(self.pf100_runner_trail_updates))
        self.SetRuntimeStatistic("PF100QualityBlocked", str(self.pf100_quality_blocked))
        self.SetRuntimeStatistic("PriceGuardSkips", str(self.price_guard_skips))
        self.SetRuntimeStatistic("DynRiskMult", f"{self.last_dynamic_risk_mult:.2f}")
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
        self.SetRuntimeStatistic("Profile", self.profile_mode)
        self.SetRuntimeStatistic("TrailingMode", self.trailing_lock_mode)
        self.SetRuntimeStatistic("ExternalStress", "1" if self.external_stress_active else "0")
        self.SetRuntimeStatistic("ExternalStressDays", str(self.external_stress_days))
        self.SetRuntimeStatistic("PF100StressTrades", str(self.stress_trades_today))
        self.SetRuntimeStatistic("PF100TradesTotal", str(self.pf100_trades_total))
        self.SetRuntimeStatistic("PF100SecondEntries", str(self.pf100_second_trade_entries))
        self.SetRuntimeStatistic("PF100SecondBlocked", str(self.pf100_second_trade_blocked))
        self.SetRuntimeStatistic("PF100PartialFills", str(self.pf100_partial_fills))
        self.SetRuntimeStatistic("PF100TrailUpdates", str(self.pf100_runner_trail_updates))
        self.SetRuntimeStatistic("PF100QualityBlocked", str(self.pf100_quality_blocked))
        self.SetRuntimeStatistic("PriceGuardSkips", str(self.price_guard_skips))
        self.SetRuntimeStatistic("DynRiskMult", f"{self.last_dynamic_risk_mult:.2f}")
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
