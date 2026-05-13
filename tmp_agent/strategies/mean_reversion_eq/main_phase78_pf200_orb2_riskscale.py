from AlgorithmImports import *
from datetime import datetime, timedelta
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline

class PF200MultiAlpha(QCAlgorithm):

    def Initialize(self):
        self.SetStartDate(int(self.GetParameter('start_year') or 2022), int(self.GetParameter('start_month') or 1), int(self.GetParameter('start_day') or 1))
        self.SetEndDate(int(self.GetParameter('end_year') or 2026), int(self.GetParameter('end_month') or 3), int(self.GetParameter('end_day') or 31))
        self.SetTimeZone(TimeZones.NewYork)
        self.initial_cash = float(self.GetParameter('initial_cash') or 50000)
        self.SetCash(self.initial_cash)
        self.SetBrokerageModel(BrokerageName.InteractiveBrokersBrokerage, AccountType.Margin)
        self.trade_mnq = (self.GetParameter('trade_mnq') or '1').strip().lower() not in ('0', 'false', 'no')
        self.trade_mes = (self.GetParameter('trade_mes') or '1').strip().lower() not in ('0', 'false', 'no')
        self.allow_shorts = (self.GetParameter('allow_shorts') or '1').strip().lower() not in ('0', 'false', 'no')
        self.alpha_mr_enabled = (self.GetParameter('alpha_mr_enabled') or '1').strip().lower() not in ('0', 'false', 'no')
        self.alpha_orb_enabled = (self.GetParameter('alpha_orb_enabled') or '1').strip().lower() not in ('0', 'false', 'no')
        self.alpha_stress_enabled = (self.GetParameter('alpha_stress_enabled') or '1').strip().lower() not in ('0', 'false', 'no')
        self.atr_period = int(self.GetParameter('atr_period') or 14)
        self.trend_period = int(self.GetParameter('trend_period') or 55)
        self.ext_vixy_ratio_threshold = float(self.GetParameter('ext_vixy_ratio_threshold') or 1.03)
        self.ext_vixy_sma_period = int(self.GetParameter('ext_vixy_sma_period') or 5)
        self.ext_rv_threshold = float(self.GetParameter('ext_rv_threshold') or 1.0)
        self.ext_gap_abs_threshold = float(self.GetParameter('ext_gap_abs_threshold') or 1.0)
        self.n_gap_atr_mult = float(self.GetParameter('n_gap_atr_mult') or 0.2)
        self.n_stop_atr_mult = float(self.GetParameter('n_stop_atr_mult') or 0.58)
        self.n_fill_frac = float(self.GetParameter('n_fill_frac') or 0.75)
        self.n_max_gap_pct = float(self.GetParameter('n_max_gap_pct') or 0.008)
        self.n_risk = float(self.GetParameter('n_risk') or 0.009)
        self.or_minutes = int(self.GetParameter('or_minutes') or 15)
        self.or_breakout_buffer_pct = float(self.GetParameter('or_breakout_buffer_pct') or 0.0004)
        self.or_stop_atr_mult = float(self.GetParameter('or_stop_atr_mult') or 0.72)
        self.or_target_atr_mult = float(self.GetParameter('or_target_atr_mult') or 1.35)
        self.or_risk = float(self.GetParameter('or_risk') or 0.004)
        self.or_min_gap_pct = float(self.GetParameter('or_min_gap_pct') or 0.0)
        self.or_mom_entry_pct = float(self.GetParameter('or_mom_entry_pct') or 0.0)
        self.or_min_width_atr = float(self.GetParameter('or_min_width_atr') or 0.0)
        self.or_max_width_atr = float(self.GetParameter('or_max_width_atr') or 99.0)
        self.or_require_gap_alignment = (self.GetParameter('or_require_gap_alignment') or '0').strip().lower() not in ('0', 'false', 'no')
        self.or_slot2_enabled = (self.GetParameter('or_slot2_enabled') or '0').strip().lower() not in ('0', 'false', 'no')
        self.or_slot2_hour = int(self.GetParameter('or_slot2_hour') or 11)
        self.or_slot2_min = int(self.GetParameter('or_slot2_min') or 0)
        self.or_slot2_risk_mult = float(self.GetParameter('or_slot2_risk_mult') or 1.0)
        self.or_slot2_min_gap_pct = float(self.GetParameter('or_slot2_min_gap_pct') or self.or_min_gap_pct)
        self.or_slot2_mom_entry_pct = float(self.GetParameter('or_slot2_mom_entry_pct') or self.or_mom_entry_pct)
        self.or_slot2_require_gap_alignment = (self.GetParameter('or_slot2_require_gap_alignment') or ('1' if self.or_require_gap_alignment else '0')).strip().lower() not in ('0', 'false', 'no')
        self.or_slot2_min_width_atr = float(self.GetParameter('or_slot2_min_width_atr') or self.or_min_width_atr)
        self.or_slot2_max_width_atr = float(self.GetParameter('or_slot2_max_width_atr') or self.or_max_width_atr)
        self.ml_orb2_enabled = (self.GetParameter('ml_orb2_enabled') or '0').strip().lower() not in ('0', 'false', 'no')
        self.ml_orb2_min_train_rows = int(self.GetParameter('ml_orb2_min_train_rows') or 500)
        self.ml_orb2_min_pos = int(self.GetParameter('ml_orb2_min_pos') or 20)
        self.ml_orb2_target_atr = float(self.GetParameter('ml_orb2_target_atr') or 0.6)
        self.ml_orb2_signal_min = float(self.GetParameter('ml_orb2_signal_min') or 0.03)
        self.ml_orb2_signal_max = float(self.GetParameter('ml_orb2_signal_max') or 0.35)
        self.ml_orb2_pass_risk_mult = float(self.GetParameter('ml_orb2_pass_risk_mult') or 1.0)
        self.ml_orb2_manual_thr_long = float(self.GetParameter('ml_orb2_manual_thr_long') or 0.0)
        self.ml_orb2_manual_thr_short = float(self.GetParameter('ml_orb2_manual_thr_short') or 0.0)
        self.ml_orb2_scale_low_thr = float(self.GetParameter('ml_orb2_scale_low_thr') or 0.06)
        self.ml_orb2_scale_high_thr = float(self.GetParameter('ml_orb2_scale_high_thr') or 0.12)
        self.ml_orb2_scale_low_mult = float(self.GetParameter('ml_orb2_scale_low_mult') or 0.85)
        self.ml_orb2_scale_mid_mult = float(self.GetParameter('ml_orb2_scale_mid_mult') or 1.00)
        self.ml_orb2_scale_high_mult = float(self.GetParameter('ml_orb2_scale_high_mult') or 1.15)
        self.ml_orb2_threshold_grid = [0.02, 0.03, 0.05, 0.08, 0.1, 0.15, 0.2, 0.25, 0.3, 0.35, 0.4]
        self.or_slot3_enabled = (self.GetParameter('or_slot3_enabled') or '0').strip().lower() not in ('0', 'false', 'no')
        self.or_slot3_hour = int(self.GetParameter('or_slot3_hour') or 13)
        self.or_slot3_min = int(self.GetParameter('or_slot3_min') or 30)
        self.s_min_gap_pct = float(self.GetParameter('s_min_gap_pct') or 0.007)
        self.s_stop_atr_mult = float(self.GetParameter('s_stop_atr_mult') or 0.9)
        self.s_target_atr_mult = float(self.GetParameter('s_target_atr_mult') or 1.8)
        self.s_risk = float(self.GetParameter('s_risk') or 0.003)
        self.s_intraday_mom_pct = float(self.GetParameter('s_intraday_mom_pct') or 0.001)
        self.max_contracts_per_trade = int(self.GetParameter('max_contracts_per_trade') or 8)
        self.max_open_positions = int(self.GetParameter('max_open_positions') or 3)
        self.max_trades_per_symbol_day = int(self.GetParameter('max_trades_per_symbol_day') or 2)
        self.daily_loss_limit_pct = float(self.GetParameter('daily_loss_limit_pct') or 0.018)
        self.daily_profit_lock_pct = float(self.GetParameter('daily_profit_lock_pct') or 0.04)
        self.trailing_dd_limit_pct = float(self.GetParameter('trailing_dd_limit_pct') or 0.035)
        self.trailing_lock_mode = (self.GetParameter('trailing_lock_mode') or 'INTRADAY').strip().upper()
        if self.trailing_lock_mode not in ('INTRADAY', 'EOD'):
            self.trailing_lock_mode = 'INTRADAY'
        self.dynamic_risk_enabled = (self.GetParameter('dynamic_risk_enabled') or '0').strip().lower() not in ('0', 'false', 'no')
        self.dynamic_risk_soft_dd_frac = float(self.GetParameter('dynamic_risk_soft_dd_frac') or 0.6)
        self.dynamic_risk_hard_dd_frac = float(self.GetParameter('dynamic_risk_hard_dd_frac') or 0.8)
        self.dynamic_risk_soft_mult = float(self.GetParameter('dynamic_risk_soft_mult') or 0.8)
        self.dynamic_risk_hard_mult = float(self.GetParameter('dynamic_risk_hard_mult') or 0.6)
        self.dynamic_risk_red_day_mult = float(self.GetParameter('dynamic_risk_red_day_mult') or 0.85)
        self.guard_enabled = (self.GetParameter('guard_enabled') or '0').strip().lower() not in ('0', 'false', 'no')
        self.guard_block_entry_cushion_pct = float(self.GetParameter('guard_block_entry_cushion_pct') or 0.0045)
        self.guard_soft_cushion_pct = float(self.GetParameter('guard_soft_cushion_pct') or 0.008)
        self.guard_hard_cushion_pct = float(self.GetParameter('guard_hard_cushion_pct') or 0.0055)
        self.guard_soft_mult = float(self.GetParameter('guard_soft_mult') or 0.82)
        self.guard_hard_mult = float(self.GetParameter('guard_hard_mult') or 0.65)
        self.guard_day_lock_enabled = (self.GetParameter('guard_day_lock_enabled') or '1').strip().lower() not in ('0', 'false', 'no')
        self.guard_day_lock_red_zone_pnl_pct = float(self.GetParameter('guard_red_pnl_lock_pct') or self.GetParameter('guard_day_lock_red_zone_pnl_pct') or -0.0015)
        self.consistency_guard_enabled = (self.GetParameter('consistency_guard_enabled') or '0').strip().lower() not in ('0', 'false', 'no')
        self.consistency_soft_cap_pct = float(self.GetParameter('consistency_soft_cap_pct') or 50.0)
        self.consistency_hard_cap_pct = float(self.GetParameter('consistency_hard_cap_pct') or 58.0)
        self.consistency_soft_risk_mult = float(self.GetParameter('consistency_soft_risk_mult') or 0.8)
        self.consistency_min_profit_pct = float(self.GetParameter('consistency_min_profit_pct') or 0.05)
        self.consistency_activation_multiple = float(self.GetParameter('cons_act_mult') or self.GetParameter('consistency_activation_multiple') or 1.8)
        self.flatten_h = int(self.GetParameter('flatten_hour') or 15)
        self.flatten_m = int(self.GetParameter('flatten_min') or 58)
        self.max_hold_hours = int(self.GetParameter('max_hold_hours') or 6)
        self.instruments = {}
        if self.trade_mes:
            self._add_future(Futures.Indices.MicroSP500EMini, 'MES')
        if self.trade_mnq:
            self._add_future(Futures.Indices.MicroNASDAQ100EMini, 'MNQ')
        self.spy = self.AddEquity('SPY', Resolution.Minute).Symbol
        self.vixy = self.AddEquity('VIXY', Resolution.Minute).Symbol
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
        self.stress_cache_minute = None
        self.stress_cache_value = False
        self.entry_order_to_symbol = {}
        self.exit_order_to_symbol = {}
        self.guard_entry_block_active = False
        self.consistency_ratio_pct = 0.0
        self.consistency_risk_mult = 1.0
        self.alpha_realized_pnl_usd = {'MR': 0.0, 'ORB': 0.0, 'STRESS': 0.0, 'OTHER': 0.0}
        self.alpha_closed_trades = {'MR': 0, 'ORB': 0, 'STRESS': 0, 'OTHER': 0}
        self.alpha_wins = {'MR': 0, 'ORB': 0, 'STRESS': 0, 'OTHER': 0}
        self.alpha_losses = {'MR': 0, 'ORB': 0, 'STRESS': 0, 'OTHER': 0}
        self.orb_slot_fills = {'ORB1': 0, 'ORB2': 0, 'ORB3': 0}
        self.ml_orb2_examples = []
        self.ml_orb2_last_train_date = None
        self.ml_orb2_models = {'LONG': None, 'SHORT': None}
        self.ml_orb2_thresholds = {'LONG': None, 'SHORT': None}
        self.ml_orb2_ready = False
        self.ml_orb2_blocks = 0
        self.ml_orb2_passes = 0
        self.ml_orb2_last_long_prob = None
        self.ml_orb2_last_short_prob = None
        self.Schedule.On(self.DateRules.EveryDay(), self.TimeRules.At(9, 40), self._entry_mr)
        self.Schedule.On(self.DateRules.EveryDay(), self.TimeRules.At(10, 5), self._entry_stress_trend)
        self.Schedule.On(self.DateRules.EveryDay(), self.TimeRules.At(10, 15), self._entry_orb_slot1)
        if self.or_slot2_enabled:
            self.Schedule.On(self.DateRules.EveryDay(), self.TimeRules.At(self.or_slot2_hour, self.or_slot2_min), self._entry_orb_slot2)
        if self.or_slot3_enabled:
            self.Schedule.On(self.DateRules.EveryDay(), self.TimeRules.At(self.or_slot3_hour, self.or_slot3_min), self._entry_orb_slot3)
        self.Schedule.On(self.DateRules.EveryDay(), self.TimeRules.At(self.flatten_h, self.flatten_m), self._flatten_eod)

    def _add_future(self, future_type, name):
        fut = self.AddFuture(future_type, Resolution.Minute, dataMappingMode=DataMappingMode.OpenInterest, dataNormalizationMode=DataNormalizationMode.BackwardsRatio, contractDepthOffset=0)
        fut.SetFilter(lambda u: u.FrontMonth())
        sym = fut.Symbol
        info = {'symbol': sym, 'name': name, 'future': fut, 'atr': self.ATR(sym, self.atr_period, MovingAverageType.Simple, Resolution.Daily), 'trend': self.EMA(sym, self.trend_period, Resolution.Daily), 'daily_closes': RollingWindow[float](3), 'daily_ret_window': RollingWindow[float](25), 'rv20': np.nan, 'prev_range_pct': np.nan, 'last_orb2_example_date': None, 'orb2_pending_example': None, 'direction': 0, 'entry_price': 0.0, 'entry_time': None, 'entry_qty': 0, 'stop_price': 0.0, 'target_price': 0.0, 'trades_today': 0, 'or_high': None, 'or_low': None, 'session_open': None, 'alpha': 'NONE', 'stop_order_id': None, 'target_order_id': None, 'pending_entry_order_id': None, 'pending_direction': 0, 'pending_qty': 0, 'pending_stop_dist': 0.0, 'pending_target_dist': 0.0, 'pending_alpha': 'NONE', 'trade_realized_pnl_usd': 0.0}
        self.instruments[sym] = info
        daily_cons = TradeBarConsolidator(timedelta(days=1))

        def on_daily(_, bar):
            close = float(bar.Close)
            high = float(bar.High)
            low = float(bar.Low)
            if info['daily_closes'].Count >= 1:
                prev_close = float(info['daily_closes'][0])
                if prev_close > 0:
                    info['daily_ret_window'].Add((close - prev_close) / prev_close)
                    info['prev_range_pct'] = (high - low) / prev_close
                    if info['daily_ret_window'].Count >= 20:
                        vals = [float(info['daily_ret_window'][i]) for i in range(info['daily_ret_window'].Count)]
                        if len(vals) >= 20:
                            info['rv20'] = float(np.std(vals[:20], ddof=1) * np.sqrt(252))
            info['daily_closes'].Add(float(bar.Close))
        daily_cons.DataConsolidated += on_daily
        self.SubscriptionManager.AddConsolidator(sym, daily_cons)

    def OnData(self, data):
        self._handle_rolls(data)
        if self.IsWarmingUp:
            return
        equity = self.Portfolio.TotalPortfolioValue
        self._roll_day_if_needed(equity)
        self._update_day_extremes(equity)
        if self.trailing_lock_mode == 'INTRADAY' and equity > self.peak_equity:
            self.peak_equity = equity
        dd = (self.peak_equity - equity) / self.peak_equity if self.peak_equity > 0 else 0.0
        if dd >= self.trailing_dd_limit_pct and (not self.trailing_lock):
            self.trailing_lock = True
            self.trailing_breaches += 1
            self._liquidate_all('TRAILING_DD_LOCK')
        if self.trailing_lock:
            self._publish_runtime(equity, dd)
            return
        day_pnl = equity - self.day_start_equity
        if day_pnl <= -(self.day_start_equity * self.daily_loss_limit_pct) and (not self.day_locked):
            self.daily_loss_breaches += 1
            self.day_locked = True
            self._liquidate_all('DAILY_LOSS_LOCK')
        elif day_pnl >= self.day_start_equity * self.daily_profit_lock_pct and (not self.day_locked):
            self.daily_profit_locks += 1
            self.day_locked = True
            self._liquidate_all('DAILY_PROFIT_LOCK')
        self._apply_guard_day_lock(equity)
        self._apply_consistency_guard(equity)
        self._update_ml_orb2_pending(data)
        self._process_exits()
        self._publish_runtime(equity, dd)

    def OnOrderEvent(self, orderEvent):
        if orderEvent is None:
            return
        order_id = int(orderEvent.OrderId)
        status = orderEvent.Status
        if order_id in self.entry_order_to_symbol:
            sym = self.entry_order_to_symbol.get(order_id)
            info = self.instruments.get(sym)
            if info is None:
                self.entry_order_to_symbol.pop(order_id, None)
                return
            if status in (OrderStatus.Canceled, OrderStatus.Invalid):
                if info['pending_entry_order_id'] == order_id:
                    info['pending_entry_order_id'] = None
                self.entry_order_to_symbol.pop(order_id, None)
                return
            if status != OrderStatus.Filled:
                return
            mapped = info['future'].Mapped
            if mapped is None:
                self.entry_order_to_symbol.pop(order_id, None)
                info['pending_entry_order_id'] = None
                return
            fill_price = float(orderEvent.FillPrice) if orderEvent.FillPrice and orderEvent.FillPrice > 0 else float(self.Securities[mapped].Price)
            if fill_price <= 0:
                self.entry_order_to_symbol.pop(order_id, None)
                info['pending_entry_order_id'] = None
                return
            direction = int(info['pending_direction'])
            qty = abs(int(orderEvent.FillQuantity)) if orderEvent.FillQuantity else int(info['pending_qty'])
            if qty < 1:
                qty = abs(int(self.Portfolio[mapped].Quantity))
            stop_dist = float(info['pending_stop_dist'])
            target_dist = float(info['pending_target_dist'])
            alpha = info['pending_alpha'] or 'UNKNOWN'
            if direction == 0 or qty < 1 or stop_dist <= 0 or (target_dist <= 0):
                self.entry_order_to_symbol.pop(order_id, None)
                info['pending_entry_order_id'] = None
                return
            if direction == 1:
                stop_price = fill_price - stop_dist
                target_price = fill_price + target_dist
                stop_qty = -qty
                target_qty = -qty
            else:
                stop_price = fill_price + stop_dist
                target_price = fill_price - target_dist
                stop_qty = qty
                target_qty = qty
            stop_ticket = self.StopMarketOrder(mapped, stop_qty, stop_price, tag=f"{alpha}_STOP {info['name']}")
            target_ticket = self.LimitOrder(mapped, target_qty, target_price, tag=f"{alpha}_TARGET {info['name']}")
            stop_id = stop_ticket.OrderId if stop_ticket is not None else None
            target_id = target_ticket.OrderId if target_ticket is not None else None
            if stop_id is not None:
                self.exit_order_to_symbol[int(stop_id)] = (sym, 'STOP')
            if target_id is not None:
                self.exit_order_to_symbol[int(target_id)] = (sym, 'TARGET')
            self._set_position(info, direction, fill_price, qty, stop_price, target_price, alpha, stop_id, target_id)
            info['pending_entry_order_id'] = None
            info['pending_direction'] = 0
            info['pending_qty'] = 0
            info['pending_stop_dist'] = 0.0
            info['pending_target_dist'] = 0.0
            info['pending_alpha'] = 'NONE'
            self.entry_order_to_symbol.pop(order_id, None)
            return
        if order_id in self.exit_order_to_symbol:
            sym, which = self.exit_order_to_symbol.get(order_id, (None, None))
            info = self.instruments.get(sym) if sym is not None else None
            if info is None:
                self.exit_order_to_symbol.pop(order_id, None)
                return
            if status == OrderStatus.Filled:
                fq = abs(int(orderEvent.FillQuantity)) if orderEvent.FillQuantity else abs(int(info.get('entry_qty') or 0))
                fp = float(orderEvent.FillPrice) if orderEvent.FillPrice and orderEvent.FillPrice > 0 else None
                self._realize_exit_fill(info, fp, fq)
                sibling_id = info['target_order_id'] if which == 'STOP' else info['stop_order_id']
                if sibling_id is not None:
                    ticket = self.Transactions.GetOrderTicket(int(sibling_id))
                    if ticket is not None:
                        try:
                            ticket.Cancel('OCO sibling canceled')
                        except Exception:
                            pass
                    self.exit_order_to_symbol.pop(int(sibling_id), None)
                self._finalize_trade(info)
                self._reset_position(info)
            if status in (OrderStatus.Filled, OrderStatus.Canceled, OrderStatus.Invalid):
                self.exit_order_to_symbol.pop(order_id, None)

    def _compute_external_stress(self):
        vixy_flag = False
        if self.vixy_sma.IsReady:
            px = self.Securities[self.vixy].Price
            sma = self.vixy_sma.Current.Value
            if px is not None and px > 0 and (sma is not None) and (sma > 0):
                vixy_flag = float(px) / float(sma) >= self.ext_vixy_ratio_threshold
        rv_flag = False
        gap_flag = False
        if self.spy_ret_window.Count >= 5:
            rets = [float(self.spy_ret_window[i]) for i in range(self.spy_ret_window.Count)]
            m = sum(rets) / len(rets)
            v = sum(((x - m) * (x - m) for x in rets)) / max(1, len(rets) - 1)
            rv20 = v ** 0.5 * 252.0 ** 0.5
            rv_flag = rv20 >= self.ext_rv_threshold
        if self.spy_prev_close is not None and self.spy_prev_close > 0:
            spy_px = self.Securities[self.spy].Price
            if spy_px is not None and spy_px > 0:
                cur_gap = abs((float(spy_px) - self.spy_prev_close) / self.spy_prev_close)
                gap_flag = cur_gap >= self.ext_gap_abs_threshold
        return vixy_flag or rv_flag or gap_flag

    def _get_external_stress_cached(self):
        minute_key = self.Time.replace(second=0, microsecond=0)
        if self.stress_cache_minute == minute_key:
            return self.stress_cache_value
        self.stress_cache_value = self._compute_external_stress()
        self.stress_cache_minute = minute_key
        return self.stress_cache_value

    def _entry_mr(self):
        if not self.alpha_mr_enabled:
            return
        if self.IsWarmingUp or self.trailing_lock or self.day_locked:
            return
        if self._open_positions_count() >= self.max_open_positions:
            return
        stress = self._get_external_stress_cached()
        self._mark_stress_day(stress)
        self.external_stress_active = stress
        if stress:
            return
        for sym, info in self.instruments.items():
            if not self._can_enter_symbol(sym, info):
                continue
            mapped = info['future'].Mapped
            atr = info['atr']
            trend = info['trend']
            if not (atr.IsReady and trend.IsReady):
                continue
            if info['daily_closes'].Count < 1:
                continue
            prev_close = float(info['daily_closes'][0])
            if prev_close <= 0:
                continue
            px = float(self.Securities[mapped].Price)
            if px <= 0:
                continue
            atr_points = float(atr.Current.Value)
            if atr_points <= 0:
                continue
            atr_pct = atr_points / prev_close
            gap_pct = (px - prev_close) / prev_close
            gap_th = self.n_gap_atr_mult * atr_pct
            if abs(gap_pct) > self.n_max_gap_pct:
                continue
            go_long = gap_pct <= -gap_th
            go_short = self.allow_shorts and gap_pct >= gap_th
            if not (go_long or go_short):
                continue
            stop_dist = atr_points * self.n_stop_atr_mult
            qty = self._position_size(mapped, stop_dist, self.n_risk)
            if qty < 1:
                continue
            if go_long:
                target = px + self.n_fill_frac * (prev_close - px)
                target_dist = max(0.0, target - px)
                self._submit_entry_with_brackets(info, mapped, 1, qty, px, stop_dist, target_dist, 'MR', f"MR_LONG {info['name']}")
            elif go_short:
                target = px - self.n_fill_frac * (px - prev_close)
                target_dist = max(0.0, px - target)
                self._submit_entry_with_brackets(info, mapped, -1, qty, px, stop_dist, target_dist, 'MR', f"MR_SHORT {info['name']}")

    def _entry_stress_trend(self):
        if not self.alpha_stress_enabled:
            return
        if self.IsWarmingUp or self.trailing_lock or self.day_locked:
            return
        if self._open_positions_count() >= self.max_open_positions:
            return
        stress = self._get_external_stress_cached()
        self._mark_stress_day(stress)
        self.external_stress_active = stress
        if not stress:
            return
        for sym, info in self.instruments.items():
            if not self._can_enter_symbol(sym, info):
                continue
            mapped = info['future'].Mapped
            atr = info['atr']
            trend = info['trend']
            if not (atr.IsReady and trend.IsReady):
                continue
            if info['daily_closes'].Count < 1:
                continue
            prev_close = float(info['daily_closes'][0])
            if prev_close <= 0:
                continue
            px = float(self.Securities[mapped].Price)
            if px <= 0:
                continue
            day_start = datetime(self.Time.year, self.Time.month, self.Time.day, 9, 30)
            day_end = day_start + timedelta(minutes=2)
            hist = self.History[TradeBar](mapped, day_start, day_end, Resolution.Minute)
            bars = list(hist) if hist is not None else []
            if len(bars) < 1:
                continue
            opn = float(bars[0].Open)
            if opn <= 0:
                continue
            gap_pct = (opn - prev_close) / prev_close
            if abs(gap_pct) < self.s_min_gap_pct:
                continue
            intraday_mom = (px - opn) / opn
            uptrend = px > float(trend.Current.Value)
            downtrend = px < float(trend.Current.Value)
            go_long = gap_pct > 0 and intraday_mom >= self.s_intraday_mom_pct and uptrend
            go_short = self.allow_shorts and gap_pct < 0 and (intraday_mom <= -self.s_intraday_mom_pct) and downtrend
            if not (go_long or go_short):
                continue
            atr_points = float(atr.Current.Value)
            if atr_points <= 0:
                continue
            stop_dist = atr_points * self.s_stop_atr_mult
            target_dist = atr_points * self.s_target_atr_mult
            qty = self._position_size(mapped, stop_dist, self.s_risk)
            if qty < 1:
                continue
            if go_long:
                self._submit_entry_with_brackets(info, mapped, 1, qty, px, stop_dist, target_dist, 'STRESS', f"STRESS_LONG {info['name']}")
            else:
                self._submit_entry_with_brackets(info, mapped, -1, qty, px, stop_dist, target_dist, 'STRESS', f"STRESS_SHORT {info['name']}")

    def _entry_orb_slot1(self):
        self._entry_orb('ORB1')

    def _entry_orb_slot2(self):
        self._entry_orb('ORB2')

    def _entry_orb_slot3(self):
        self._entry_orb('ORB3')

    def _orb_slot_params(self, slot_label):
        if slot_label == 'ORB2':
            return {'risk': self.or_risk * self.or_slot2_risk_mult, 'min_gap_pct': self.or_slot2_min_gap_pct, 'mom_entry_pct': self.or_slot2_mom_entry_pct, 'require_gap_alignment': self.or_slot2_require_gap_alignment, 'min_width_atr': self.or_slot2_min_width_atr, 'max_width_atr': self.or_slot2_max_width_atr}
        return {'risk': self.or_risk, 'min_gap_pct': self.or_min_gap_pct, 'mom_entry_pct': self.or_mom_entry_pct, 'require_gap_alignment': self.or_require_gap_alignment, 'min_width_atr': self.or_min_width_atr, 'max_width_atr': self.or_max_width_atr}

    def _entry_orb(self, slot_label='ORB1'):
        if not self.alpha_orb_enabled:
            return
        if self.IsWarmingUp or self.trailing_lock or self.day_locked:
            return
        if self._open_positions_count() >= self.max_open_positions:
            return
        stress = self._get_external_stress_cached()
        self._mark_stress_day(stress)
        self.external_stress_active = stress
        if stress:
            return
        if slot_label == 'ORB2':
            self._train_ml_orb2_if_needed()
        slot_params = self._orb_slot_params(slot_label)
        start = datetime(self.Time.year, self.Time.month, self.Time.day, 9, 30)
        end = start + timedelta(minutes=self.or_minutes)
        for sym, info in self.instruments.items():
            if not self._can_enter_symbol(sym, info):
                continue
            mapped = info['future'].Mapped
            if mapped is None:
                continue
            hist = self.History[TradeBar](mapped, start, end, Resolution.Minute)
            bars = list(hist) if hist is not None else []
            if len(bars) < 3:
                continue
            or_high = max((float(b.High) for b in bars))
            or_low = min((float(b.Low) for b in bars))
            session_open = float(bars[0].Open)
            if or_high <= or_low or session_open <= 0:
                continue
            atr = info['atr']
            trend = info['trend']
            if not (atr.IsReady and trend.IsReady):
                continue
            if info['daily_closes'].Count < 1:
                continue
            prev_close = float(info['daily_closes'][0])
            if prev_close <= 0:
                continue
            px = float(self.Securities[mapped].Price)
            if px <= 0:
                continue
            trend_val = float(trend.Current.Value)
            uptrend = px > trend_val
            downtrend = px < trend_val
            gap_pct = (session_open - prev_close) / prev_close
            long_break = px > or_high * (1.0 + self.or_breakout_buffer_pct)
            short_break = px < or_low * (1.0 - self.or_breakout_buffer_pct)
            intraday_mom = (px - session_open) / session_open
            if slot_label == 'ORB2':
                self._track_ml_orb2_candidate(info, session_open, or_high, or_low, atr.Current.Value, px, gap_pct, intraday_mom, trend_val, self.Time)
            go_long = long_break and uptrend
            go_short = short_break and self.allow_shorts and downtrend
            if abs(gap_pct) < slot_params['min_gap_pct']:
                go_long = False
                go_short = False
            if slot_params['mom_entry_pct'] > 0:
                if go_long and intraday_mom < slot_params['mom_entry_pct']:
                    go_long = False
                if go_short and intraday_mom > -slot_params['mom_entry_pct']:
                    go_short = False
            if slot_params['require_gap_alignment']:
                if go_long and gap_pct < 0:
                    go_long = False
                if go_short and gap_pct > 0:
                    go_short = False
            if not (go_long or go_short):
                continue
            atr_points = float(atr.Current.Value)
            if atr_points <= 0:
                continue
            or_width_atr = (or_high - or_low) / atr_points
            if or_width_atr < slot_params['min_width_atr'] or or_width_atr > slot_params['max_width_atr']:
                continue
            stop_dist = atr_points * self.or_stop_atr_mult
            target_dist = atr_points * self.or_target_atr_mult
            eff_risk = slot_params['risk']
            if slot_label == 'ORB2' and self.ml_orb2_enabled:
                ml_row = self._make_ml_orb2_row(info, session_open, or_high, or_low, atr_points, px, gap_pct, intraday_mom, trend_val)
                if go_long:
                    prob = self._ml_orb2_prob('LONG', ml_row)
                    self.ml_orb2_last_long_prob = prob
                if go_short:
                    prob = self._ml_orb2_prob('SHORT', ml_row)
                    self.ml_orb2_last_short_prob = prob
                scale_prob = self.ml_orb2_last_long_prob if go_long else self.ml_orb2_last_short_prob
                eff_risk *= self._ml_orb2_risk_mult(scale_prob)
                self.ml_orb2_passes += 1
            qty = self._position_size(mapped, stop_dist, eff_risk)
            if qty < 1:
                continue
            if go_long:
                ok = self._submit_entry_with_brackets(info, mapped, 1, qty, px, stop_dist, target_dist, 'ORB', f"{slot_label}_LONG {info['name']}")
                if ok:
                    self.orb_slot_fills[slot_label] = int(self.orb_slot_fills.get(slot_label, 0)) + 1
            else:
                ok = self._submit_entry_with_brackets(info, mapped, -1, qty, px, stop_dist, target_dist, 'ORB', f"{slot_label}_SHORT {info['name']}")
                if ok:
                    self.orb_slot_fills[slot_label] = int(self.orb_slot_fills.get(slot_label, 0)) + 1

    def _make_ml_orb2_row(self, info, session_open, or_high, or_low, atr_points, px, gap_pct, intraday_mom, trend_val):
        day_high = max(float(info.get('session_high_for_ml') or px), px)
        day_low = min(float(info.get('session_low_for_ml') or px), px)
        return {'gap_pct': float(gap_pct), 'or_width_atr': float((or_high - or_low) / atr_points) if atr_points > 0 else 0.0, 'day_range_atr': float((day_high - day_low) / atr_points) if atr_points > 0 else 0.0, 'intraday_mom': float(intraday_mom), 'long_break': float(px > or_high * (1.0 + self.or_breakout_buffer_pct)), 'short_break': float(px < or_low * (1.0 - self.or_breakout_buffer_pct)), 'uptrend': float(px > trend_val), 'downtrend': float(px < trend_val), 'rv20': float(info.get('rv20')) if info.get('rv20') is not None and np.isfinite(info.get('rv20')) else np.nan, 'prev_range_pct': float(info.get('prev_range_pct')) if info.get('prev_range_pct') is not None and np.isfinite(info.get('prev_range_pct')) else np.nan}

    def _track_ml_orb2_candidate(self, info, session_open, or_high, or_low, atr_points, px, gap_pct, intraday_mom, trend_val, now):
        if not self.ml_orb2_enabled or atr_points <= 0:
            return
        if info.get('last_orb2_example_date') == now.date():
            return
        info['last_orb2_example_date'] = now.date()
        info['session_high_for_ml'] = float(px)
        info['session_low_for_ml'] = float(px)
        row = self._make_ml_orb2_row(info, session_open, or_high, or_low, float(atr_points), float(px), float(gap_pct), float(intraday_mom), float(trend_val))
        row.update({'date': now.date(), 'symbol': info['name'], 'y_long': 0, 'y_short': 0, 'long_target_px': float(px + self.ml_orb2_target_atr * atr_points), 'short_target_px': float(px - self.ml_orb2_target_atr * atr_points), 'expiry': now + timedelta(minutes=120)})
        info['orb2_pending_example'] = row

    def _update_ml_orb2_pending(self, data):
        if not self.ml_orb2_enabled:
            return
        for _, info in self.instruments.items():
            pending = info.get('orb2_pending_example')
            mapped = info['future'].Mapped
            if pending is None or mapped is None:
                continue
            bar = data.Bars.get(mapped)
            if bar is None:
                continue
            info['session_high_for_ml'] = max(float(info.get('session_high_for_ml') or bar.High), float(bar.High))
            info['session_low_for_ml'] = min(float(info.get('session_low_for_ml') or bar.Low), float(bar.Low))
            if int(pending['y_long']) == 0 and float(bar.High) >= float(pending['long_target_px']):
                pending['y_long'] = 1
            if int(pending['y_short']) == 0 and float(bar.Low) <= float(pending['short_target_px']):
                pending['y_short'] = 1
            if self.Time >= pending['expiry'] or (self.Time.hour > self.flatten_h or (self.Time.hour == self.flatten_h and self.Time.minute >= self.flatten_m)):
                self._finalize_ml_orb2_pending(info)

    def _finalize_ml_orb2_pending(self, info):
        pending = info.get('orb2_pending_example')
        if pending is None:
            return
        self.ml_orb2_examples.append(dict(pending))
        info['orb2_pending_example'] = None
        info['session_high_for_ml'] = None
        info['session_low_for_ml'] = None

    def _pick_ml_model(self):
        model = HistGradientBoostingClassifier(learning_rate=0.05, max_depth=3, max_iter=250, min_samples_leaf=20, l2_regularization=0.1, random_state=42)
        return Pipeline([('imputer', SimpleImputer(strategy='median')), ('model', model)])

    def _eval_ml_threshold(self, y_true, probs):
        best = None
        base_rate = float(np.mean(y_true)) if len(y_true) else 0.0
        for thr in self.ml_orb2_threshold_grid:
            pred = (probs >= thr).astype(int)
            signal_rate = float(pred.mean())
            precision = float(np.logical_and(pred == 1, y_true == 1).sum() / max(int((pred == 1).sum()), 1)) if len(pred) else 0.0
            if signal_rate < self.ml_orb2_signal_min or signal_rate > self.ml_orb2_signal_max:
                score = -1.0
            else:
                lift = precision / base_rate if base_rate > 0 else 0.0
                score = lift * signal_rate
            row = {'threshold': float(thr), 'precision': float(precision), 'signal_rate': float(signal_rate), 'base_rate': float(base_rate), 'score': float(score)}
            if best is None or row['score'] > best['score']:
                best = row
        return best

    def _train_ml_orb2_if_needed(self):
        if not self.ml_orb2_enabled:
            return
        day = self.Time.date()
        if self.ml_orb2_last_train_date == day:
            return
        self.ml_orb2_last_train_date = day
        if len(self.ml_orb2_examples) < self.ml_orb2_min_train_rows:
            self.ml_orb2_models = {'LONG': None, 'SHORT': None}
            self.ml_orb2_thresholds = {'LONG': None, 'SHORT': None}
            self.ml_orb2_ready = False
            return
        df = pd.DataFrame(self.ml_orb2_examples)
        df = df[df['date'] < day].copy()
        if len(df) < self.ml_orb2_min_train_rows:
            self.ml_orb2_models = {'LONG': None, 'SHORT': None}
            self.ml_orb2_thresholds = {'LONG': None, 'SHORT': None}
            self.ml_orb2_ready = False
            return
        self.ml_orb2_ready = True
        for side, target_col in (('LONG', 'y_long'), ('SHORT', 'y_short')):
            y = df[target_col].astype(int)
            if int(y.sum()) < self.ml_orb2_min_pos or y.nunique() < 2:
                self.ml_orb2_models[side] = None
                self.ml_orb2_thresholds[side] = None
                self.ml_orb2_ready = False
                continue
            pipe = self._pick_ml_model()
            X = df[['gap_pct', 'or_width_atr', 'day_range_atr', 'intraday_mom', 'long_break', 'short_break', 'uptrend', 'downtrend', 'rv20', 'prev_range_pct']]
            pos = max(int(y.sum()), 1)
            neg = max(len(y) - pos, 1)
            pos_weight = min(10.0, max(1.0, neg / pos))
            sample_weight = np.where(y.values == 1, pos_weight, 1.0)
            pipe.fit(X, y, model__sample_weight=sample_weight)
            probs = pipe.predict_proba(X)[:, 1]
            picked = self._eval_ml_threshold(y.values, probs)
            manual_thr = self.ml_orb2_manual_thr_long if side == 'LONG' else self.ml_orb2_manual_thr_short
            if manual_thr > 0:
                picked['threshold'] = float(manual_thr)
            self.ml_orb2_models[side] = pipe
            self.ml_orb2_thresholds[side] = picked
        self.ml_orb2_ready = self.ml_orb2_models['LONG'] is not None or self.ml_orb2_models['SHORT'] is not None

    def _ml_orb2_prob(self, side, row):
        model = self.ml_orb2_models.get(side)
        if model is None:
            return None
        X = pd.DataFrame([row])[['gap_pct', 'or_width_atr', 'day_range_atr', 'intraday_mom', 'long_break', 'short_break', 'uptrend', 'downtrend', 'rv20', 'prev_range_pct']]
        return float(model.predict_proba(X)[:, 1][0])

    def _ml_orb2_risk_mult(self, prob):
        if prob is None:
            return self.ml_orb2_scale_mid_mult
        if prob >= self.ml_orb2_scale_high_thr:
            return self.ml_orb2_scale_high_mult
        if prob < self.ml_orb2_scale_low_thr:
            return self.ml_orb2_scale_low_mult
        return self.ml_orb2_scale_mid_mult

    def _can_enter_symbol(self, sym, info):
        mapped = info['future'].Mapped
        if mapped is None:
            return False
        if not self._allow_new_entries():
            return False
        if self._open_positions_count() >= self.max_open_positions:
            return False
        if self.Portfolio[mapped].Quantity != 0:
            return False
        if info['pending_entry_order_id'] is not None:
            return False
        if info['trades_today'] >= self.max_trades_per_symbol_day:
            return False
        if not self._has_fresh_price(mapped):
            return False
        return True

    def _submit_entry_with_brackets(self, info, mapped, direction, qty, entry_ref_px, stop_dist, target_dist, alpha, tag):
        if qty < 1 or stop_dist <= 0 or target_dist <= 0:
            return False
        signed_qty = int(qty) if int(direction) == 1 else -int(qty)
        ticket = self.MarketOrder(mapped, signed_qty, tag=tag)
        if ticket is None:
            return False
        oid = int(ticket.OrderId)
        if ticket.Status == OrderStatus.Filled and ticket.AverageFillPrice and (ticket.AverageFillPrice > 0):
            fill_price = float(ticket.AverageFillPrice)
            if int(direction) == 1:
                stop_price = fill_price - float(stop_dist)
                target_price = fill_price + float(target_dist)
                stop_qty = -int(qty)
                target_qty = -int(qty)
            else:
                stop_price = fill_price + float(stop_dist)
                target_price = fill_price - float(target_dist)
                stop_qty = int(qty)
                target_qty = int(qty)
            stop_ticket = self.StopMarketOrder(mapped, stop_qty, stop_price, tag=f"{alpha}_STOP {info['name']}")
            target_ticket = self.LimitOrder(mapped, target_qty, target_price, tag=f"{alpha}_TARGET {info['name']}")
            stop_id = stop_ticket.OrderId if stop_ticket is not None else None
            target_id = target_ticket.OrderId if target_ticket is not None else None
            if stop_id is not None:
                self.exit_order_to_symbol[int(stop_id)] = (info['symbol'], 'STOP')
            if target_id is not None:
                self.exit_order_to_symbol[int(target_id)] = (info['symbol'], 'TARGET')
            info['trades_today'] += 1
            self._set_position(info, int(direction), fill_price, int(qty), stop_price, target_price, alpha, stop_id, target_id)
            return True
        info['trades_today'] += 1
        info['pending_entry_order_id'] = oid
        info['pending_direction'] = int(direction)
        info['pending_qty'] = int(qty)
        info['pending_stop_dist'] = float(stop_dist)
        info['pending_target_dist'] = float(target_dist)
        info['pending_alpha'] = alpha
        self.entry_order_to_symbol[oid] = info['symbol']
        return True

    def _set_position(self, info, direction, entry, qty, stop, target, alpha, stop_order_id=None, target_order_id=None):
        info['direction'] = int(direction)
        info['entry_price'] = float(entry)
        info['entry_time'] = self.Time
        info['entry_qty'] = int(qty)
        info['stop_price'] = float(stop)
        info['target_price'] = float(target)
        info['alpha'] = alpha
        info['stop_order_id'] = int(stop_order_id) if stop_order_id is not None else None
        info['target_order_id'] = int(target_order_id) if target_order_id is not None else None
        info['trade_realized_pnl_usd'] = 0.0

    def _process_exits(self):
        for _, info in self.instruments.items():
            mapped = info['future'].Mapped
            if mapped is None:
                continue
            qty = self.Portfolio[mapped].Quantity
            direction = int(info['direction'])
            if qty == 0:
                if direction != 0:
                    self._cancel_attached_orders(info)
                    self._reset_position(info)
                continue
            if direction == 0:
                continue
            if not self._has_fresh_price(mapped):
                continue
            held = int((self.Time - info['entry_time']).total_seconds() / 3600.0) if info['entry_time'] else 0
            hit_time = held >= self.max_hold_hours
            if hit_time:
                self._realize_mark_to_market(info, mapped, abs(int(qty)))
                self._finalize_trade(info)
                self._cancel_attached_orders(info)
                self.Liquidate(mapped, tag=f"TIME_EXIT {info['name']}_{info['alpha']}")
                self._reset_position(info)

    def _alpha_key(self, alpha):
        a = str(alpha or '').upper()
        if a.startswith('MR'):
            return 'MR'
        if a.startswith('ORB'):
            return 'ORB'
        if a.startswith('STRESS'):
            return 'STRESS'
        return 'OTHER'

    def _contract_multiplier(self, info):
        mapped = info['future'].Mapped
        try:
            if mapped is not None and self.Securities.ContainsKey(mapped):
                m = float(self.Securities[mapped].SymbolProperties.ContractMultiplier)
                if m > 0:
                    return m
        except Exception:
            pass
        try:
            sym = info.get('symbol')
            if sym is not None and self.Securities.ContainsKey(sym):
                m = float(self.Securities[sym].SymbolProperties.ContractMultiplier)
                if m > 0:
                    return m
        except Exception:
            pass
        return 1.0

    def _accumulate_alpha_pnl(self, info, pnl_usd):
        if pnl_usd == 0:
            return
        key = self._alpha_key(info.get('alpha'))
        self.alpha_realized_pnl_usd[key] += float(pnl_usd)
        info['trade_realized_pnl_usd'] = float(info.get('trade_realized_pnl_usd') or 0.0) + float(pnl_usd)

    def _realize_exit_fill(self, info, fill_price, fill_qty):
        direction = int(info.get('direction') or 0)
        entry_price = float(info.get('entry_price') or 0.0)
        q = abs(int(fill_qty or 0))
        if direction == 0 or q < 1 or entry_price <= 0:
            return
        if fill_price is None or fill_price <= 0:
            mapped = info['future'].Mapped
            if mapped is None or not self._has_fresh_price(mapped):
                return
            fill_price = float(self.Securities[mapped].Price)
        mult = self._contract_multiplier(info)
        pnl = direction * (float(fill_price) - entry_price) * q * mult
        self._accumulate_alpha_pnl(info, pnl)

    def _realize_mark_to_market(self, info, mapped, qty_abs):
        direction = int(info.get('direction') or 0)
        entry_price = float(info.get('entry_price') or 0.0)
        q = abs(int(qty_abs or 0))
        if direction == 0 or q < 1 or entry_price <= 0:
            return
        if mapped is None or not self._has_fresh_price(mapped):
            return
        px = float(self.Securities[mapped].Price)
        if px <= 0:
            return
        mult = self._contract_multiplier(info)
        pnl = direction * (px - entry_price) * q * mult
        self._accumulate_alpha_pnl(info, pnl)

    def _finalize_trade(self, info):
        direction = int(info.get('direction') or 0)
        if direction == 0:
            return
        key = self._alpha_key(info.get('alpha'))
        pnl = float(info.get('trade_realized_pnl_usd') or 0.0)
        self.alpha_closed_trades[key] += 1
        if pnl >= 0:
            self.alpha_wins[key] += 1
        else:
            self.alpha_losses[key] += 1

    def _has_fresh_price(self, symbol):
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

    def _position_size(self, mapped, stop_distance_points, risk_pct):
        if stop_distance_points <= 0:
            return 0
        mult = float(self.Securities[mapped].SymbolProperties.ContractMultiplier)
        if mult <= 0:
            return 0
        risk_per_contract = stop_distance_points * mult
        risk_budget = self.Portfolio.TotalPortfolioValue * max(0.0002, float(risk_pct)) * self._risk_multiplier()
        qty = int(risk_budget / risk_per_contract)
        if qty < 1:
            return 0
        return min(qty, self.max_contracts_per_trade)

    def _risk_multiplier(self):
        mult = 1.0
        equity = self.Portfolio.TotalPortfolioValue
        if self.dynamic_risk_enabled:
            dd = (self.peak_equity - equity) / self.peak_equity if self.peak_equity > 0 else 0.0
            hard_cut = self.trailing_dd_limit_pct * self.dynamic_risk_hard_dd_frac
            soft_cut = self.trailing_dd_limit_pct * self.dynamic_risk_soft_dd_frac
            if dd >= hard_cut:
                mult *= self.dynamic_risk_hard_mult
            elif dd >= soft_cut:
                mult *= self.dynamic_risk_soft_mult
            if self.day_start_equity > 0:
                day_pnl_pct = (equity - self.day_start_equity) / self.day_start_equity
                if day_pnl_pct < 0:
                    mult *= self.dynamic_risk_red_day_mult
        if self.guard_enabled:
            cushion_pct = self._cushion_to_trailing_pct(equity)
            if cushion_pct <= self.guard_hard_cushion_pct:
                mult *= self.guard_hard_mult
            elif cushion_pct <= self.guard_soft_cushion_pct:
                mult *= self.guard_soft_mult
        mult *= self.consistency_risk_mult
        return max(0.2, min(1.2, float(mult)))

    def _trailing_floor_equity(self):
        if self.peak_equity <= 0:
            return 0.0
        return self.peak_equity * (1.0 - self.trailing_dd_limit_pct)

    def _cushion_to_trailing_pct(self, equity=None):
        eq = float(equity if equity is not None else self.Portfolio.TotalPortfolioValue)
        floor = self._trailing_floor_equity()
        if self.initial_cash <= 0:
            return 0.0
        return (eq - floor) / self.initial_cash

    def _allow_new_entries(self):
        if not self.guard_enabled:
            self.guard_entry_block_active = False
            return True
        cushion_pct = self._cushion_to_trailing_pct()
        blocked = cushion_pct <= self.guard_block_entry_cushion_pct
        self.guard_entry_block_active = blocked
        return not blocked

    def _apply_guard_day_lock(self, equity):
        if not self.guard_enabled or not self.guard_day_lock_enabled or self.day_locked:
            return
        cushion_pct = self._cushion_to_trailing_pct(equity)
        if cushion_pct > self.guard_hard_cushion_pct:
            return
        if self.day_start_equity <= 0:
            return
        day_pnl_pct = (equity - self.day_start_equity) / self.day_start_equity
        if day_pnl_pct <= self.guard_day_lock_red_zone_pnl_pct:
            self.day_locked = True
            self._liquidate_all('GUARD_RED_ZONE_DAY_LOCK')

    def _apply_consistency_guard(self, equity):
        self.consistency_risk_mult = 1.0
        total_profit = float(equity - self.initial_cash)
        if total_profit <= 0:
            self.consistency_ratio_pct = 0.0
            return
        projected_best = max(float(self.best_day_profit_usd), float(self.day_best_pnl_usd))
        ratio_pct = 100.0 * projected_best / total_profit
        self.consistency_ratio_pct = ratio_pct
        if not self.consistency_guard_enabled:
            return
        min_profit_usd = self.initial_cash * self.consistency_min_profit_pct
        activation_profit = max(min_profit_usd, projected_best * self.consistency_activation_multiple)
        if total_profit < activation_profit:
            return
        if ratio_pct >= self.consistency_hard_cap_pct and (not self.day_locked):
            self.day_locked = True
            self._liquidate_all('CONSISTENCY_HARD_LOCK')
            return
        if ratio_pct >= self.consistency_soft_cap_pct:
            self.consistency_risk_mult = max(0.2, min(1.0, self.consistency_soft_risk_mult))

    def _handle_rolls(self, data):
        if not data.SymbolChangedEvents:
            return
        for changed in data.SymbolChangedEvents.Values:
            old_sym = changed.OldSymbol
            for _, info in self.instruments.items():
                mapped = info['future'].Mapped
                if mapped != old_sym:
                    continue
                qty = self.Portfolio[old_sym].Quantity
                if qty != 0:
                    self._realize_mark_to_market(info, old_sym, abs(int(qty)))
                    self._finalize_trade(info)
                    self._cancel_attached_orders(info)
                    self.Liquidate(old_sym, tag=f"ROLL_OUT {info['name']}")
                    self._reset_position(info)

    def _open_positions_count(self):
        n = 0
        for _, info in self.instruments.items():
            mapped = info['future'].Mapped
            if mapped is not None and self.Portfolio[mapped].Quantity != 0:
                n += 1
        return n

    def _reset_position(self, info):
        if info['pending_entry_order_id'] is not None:
            self.entry_order_to_symbol.pop(int(info['pending_entry_order_id']), None)
        if info['stop_order_id'] is not None:
            self.exit_order_to_symbol.pop(int(info['stop_order_id']), None)
        if info['target_order_id'] is not None:
            self.exit_order_to_symbol.pop(int(info['target_order_id']), None)
        info['direction'] = 0
        info['entry_price'] = 0.0
        info['entry_time'] = None
        info['entry_qty'] = 0
        info['stop_price'] = 0.0
        info['target_price'] = 0.0
        info['alpha'] = 'NONE'
        info['stop_order_id'] = None
        info['target_order_id'] = None
        info['pending_entry_order_id'] = None
        info['pending_direction'] = 0
        info['pending_qty'] = 0
        info['pending_stop_dist'] = 0.0
        info['pending_target_dist'] = 0.0
        info['pending_alpha'] = 'NONE'
        info['trade_realized_pnl_usd'] = 0.0

    def _cancel_attached_orders(self, info):
        for oid in (info['stop_order_id'], info['target_order_id']):
            if oid is None:
                continue
            ticket = self.Transactions.GetOrderTicket(int(oid))
            if ticket is not None:
                try:
                    ticket.Cancel('Attached order canceled')
                except Exception:
                    pass
            self.exit_order_to_symbol.pop(int(oid), None)
        info['stop_order_id'] = None
        info['target_order_id'] = None

    def _liquidate_all(self, reason):
        for _, info in self.instruments.items():
            self._finalize_ml_orb2_pending(info)
            mapped = info['future'].Mapped
            if info['pending_entry_order_id'] is not None:
                t = self.Transactions.GetOrderTicket(int(info['pending_entry_order_id']))
                if t is not None:
                    try:
                        t.Cancel('Pending entry canceled')
                    except Exception:
                        pass
                self.entry_order_to_symbol.pop(int(info['pending_entry_order_id']), None)
            self._cancel_attached_orders(info)
            if mapped is not None and self.Portfolio[mapped].Quantity != 0:
                qty = abs(int(self.Portfolio[mapped].Quantity))
                self._realize_mark_to_market(info, mapped, qty)
                self._finalize_trade(info)
                self.Liquidate(mapped, tag=reason)
            self._reset_position(info)

    def _flatten_eod(self):
        if self.IsWarmingUp:
            return
        self._liquidate_all('EOD_FLAT')
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
                info['trades_today'] = 0
            self.last_equity_snapshot = equity
            return
        if cur != self.day_key:
            if self.trailing_lock_mode == 'EOD':
                self.peak_equity = max(self.peak_equity, self.last_equity_snapshot)
            self._finalize_day_extremes()
            self.day_key = cur
            self.day_start_equity = equity
            self.day_locked = False
            self.day_best_pnl_usd = 0.0
            self.day_worst_pnl_usd = 0.0
            for _, info in self.instruments.items():
                self._finalize_ml_orb2_pending(info)
                info['trades_today'] = 0
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
        self.SetRuntimeStatistic('Mode', 'PF200')
        self.SetRuntimeStatistic('ExternalStress', '1' if self.external_stress_active else '0')
        self.SetRuntimeStatistic('ExternalStressDays', str(self.external_stress_days))
        self.SetRuntimeStatistic('DailyLossBreaches', str(self.daily_loss_breaches))
        self.SetRuntimeStatistic('TrailingBreaches', str(self.trailing_breaches))
        self.SetRuntimeStatistic('BestDayUSD', f'{self.best_day_profit_usd:.2f}')
        self.SetRuntimeStatistic('WorstDayUSD', f'{self.worst_day_loss_usd:.2f}')
        self.SetRuntimeStatistic('ConsistencyPct', f'{consistency:.2f}')
        self.SetRuntimeStatistic('ConsistencyRatioPct', f'{self.consistency_ratio_pct:.2f}')
        self.SetRuntimeStatistic('DrawdownPct', f'{dd * 100.0:.2f}')
        self.SetRuntimeStatistic('GuardBlock', '1' if self.guard_entry_block_active else '0')
        self.SetRuntimeStatistic('CushionPct', f'{self._cushion_to_trailing_pct(equity) * 100.0:.3f}')
        self.SetRuntimeStatistic('PnlMR', f"{self.alpha_realized_pnl_usd['MR']:.2f}")
        self.SetRuntimeStatistic('PnlORB', f"{self.alpha_realized_pnl_usd['ORB']:.2f}")
        self.SetRuntimeStatistic('PnlST', f"{self.alpha_realized_pnl_usd['STRESS']:.2f}")
        self.SetRuntimeStatistic('TrMR', str(self.alpha_closed_trades['MR']))
        self.SetRuntimeStatistic('TrORB', str(self.alpha_closed_trades['ORB']))
        self.SetRuntimeStatistic('TrST', str(self.alpha_closed_trades['STRESS']))
        self.SetRuntimeStatistic('Orb1Fills', str(self.orb_slot_fills['ORB1']))
        self.SetRuntimeStatistic('Orb2Fills', str(self.orb_slot_fills['ORB2']))
        self.SetRuntimeStatistic('Orb3Fills', str(self.orb_slot_fills['ORB3']))
        self.SetRuntimeStatistic('MLOrb2Ready', '1' if self.ml_orb2_ready else '0')
        self.SetRuntimeStatistic('MLOrb2Blocks', str(self.ml_orb2_blocks))
        self.SetRuntimeStatistic('MLOrb2Passes', str(self.ml_orb2_passes))
        self.SetRuntimeStatistic('MLOrb2Rows', str(len(self.ml_orb2_examples)))
        self.SetRuntimeStatistic('MLProbL', '' if self.ml_orb2_last_long_prob is None else f'{self.ml_orb2_last_long_prob:.3f}')
        self.SetRuntimeStatistic('MLProbS', '' if self.ml_orb2_last_short_prob is None else f'{self.ml_orb2_last_short_prob:.3f}')

    def OnEndOfAlgorithm(self):
        equity = self.Portfolio.TotalPortfolioValue
        self._finalize_day_extremes()
        dd = (self.peak_equity - equity) / self.peak_equity if self.peak_equity > 0 else 0.0
        self._publish_runtime(equity, dd)
        ret = (equity - self.initial_cash) / self.initial_cash if self.initial_cash else 0.0
        self.Log(f"FINAL mode=PF200 equity={equity:.2f} return_pct={ret * 100.0:.2f} drawdown_pct={dd * 100.0:.2f} dbr={self.daily_loss_breaches} tbr={self.trailing_breaches} stress_days={self.external_stress_days} alpha_pnl_mr={self.alpha_realized_pnl_usd['MR']:.2f} alpha_pnl_orb={self.alpha_realized_pnl_usd['ORB']:.2f} alpha_pnl_stress={self.alpha_realized_pnl_usd['STRESS']:.2f} alpha_tr_mr={self.alpha_closed_trades['MR']} alpha_tr_orb={self.alpha_closed_trades['ORB']} alpha_tr_stress={self.alpha_closed_trades['STRESS']} orb1_fills={self.orb_slot_fills['ORB1']} orb2_fills={self.orb_slot_fills['ORB2']} orb3_fills={self.orb_slot_fills['ORB3']}")
