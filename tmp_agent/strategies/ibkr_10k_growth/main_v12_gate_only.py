# region imports
from AlgorithmImports import *
from datetime import timedelta
# endregion


class IBKR10KGateOnlyV12(QCAlgorithm):
    """
    IBKR 10K Gate-Only V12
    ----------------------
    Multi-regime version with explicit exposure gating:
    - BULL_TREND: full risk
    - STRESS_UPTREND: reduced risk, turbo throttled/off
    - CHOP: minimal exposure
    - BEAR: zero long exposure (cash by default)
    """

    def Initialize(self):
        self.SetStartDate(
            int(self.GetParameter("start_year") or 2018),
            int(self.GetParameter("start_month") or 1),
            int(self.GetParameter("start_day") or 1),
        )
        self.SetEndDate(
            int(self.GetParameter("end_year") or 2026),
            int(self.GetParameter("end_month") or 3),
            int(self.GetParameter("end_day") or 31),
        )
        self.SetTimeZone(TimeZones.NewYork)

        self.initial_cash = float(self.GetParameter("initial_cash") or 10000)
        self.SetCash(self.initial_cash)
        self.SetBrokerageModel(BrokerageName.InteractiveBrokersBrokerage, AccountType.Margin)

        self.spy_ticker = "SPY"
        self.qqq_ticker = "QQQ"
        self.vixy_ticker = "VIXY"

        self.core_assets = ["SPY", "QQQ", "IWM", "EFA", "EEM", "TLT", "IEF", "GLD", "DBC", "UUP"]
        self.safe_assets = ["SHY", "IEF", "GLD", "TLT"]
        self.turbo_assets = ["TQQQ", "SOXL", "UPRO", "TECL"]

        self.lookback_fast = int(self.GetParameter("lookback_fast") or 63)
        self.lookback_slow = int(self.GetParameter("lookback_slow") or 252)
        self.atr_period = int(self.GetParameter("atr_period") or 20)
        self.sma_filter_period = int(self.GetParameter("sma_filter_period") or 200)
        self.vixy_sma_period = int(self.GetParameter("vixy_sma_period") or 20)

        self.w_fast = float(self.GetParameter("w_fast") or 0.35)
        self.w_slow = float(self.GetParameter("w_slow") or 0.65)
        self.vol_penalty = float(self.GetParameter("vol_penalty") or 0.65)
        self.min_core_signal = float(self.GetParameter("min_core_signal") or 0.0)
        self.min_turbo_signal = float(self.GetParameter("min_turbo_signal") or 0.02)

        self.core_gross_base = float(self.GetParameter("core_gross_base") or 3.8)
        self.turbo_gross_base = float(self.GetParameter("turbo_gross_base") or 5.2)
        self.max_total_gross = float(self.GetParameter("max_total_gross") or 8.8)
        self.max_single_weight = float(self.GetParameter("max_single_weight") or 3.2)
        self.max_core_active = int(self.GetParameter("max_core_active") or 2)
        self.max_turbo_active = int(self.GetParameter("max_turbo_active") or 1)
        self.rebalance_buffer = float(self.GetParameter("rebalance_buffer") or 0.015)
        self.rebalance_daily = (self.GetParameter("rebalance_daily") or "1").strip().lower() not in (
            "0",
            "false",
            "no",
        )

        # Regime classifier thresholds
        self.bull_sma_mult = float(self.GetParameter("bull_sma_mult") or 1.0)
        self.bull_mom_min = float(self.GetParameter("bull_mom_min") or -2.0)
        self.bull_vixy_max = float(self.GetParameter("bull_vixy_max") or 1.20)

        self.stress_vixy_min = float(self.GetParameter("stress_vixy_min") or 1.12)
        self.stress_vixy_max = float(self.GetParameter("stress_vixy_max") or 1.25)

        self.chop_band_pct = float(self.GetParameter("chop_band_pct") or 0.03)
        self.chop_mom_abs = float(self.GetParameter("chop_mom_abs") or 2.0)

        self.bear_sma_mult = float(self.GetParameter("bear_sma_mult") or 1.0)
        self.bear_vixy_min = float(self.GetParameter("bear_vixy_min") or 1.15)

        self.state_hold_days = int(self.GetParameter("state_hold_days") or 2)
        self.use_qqq_confirm = (self.GetParameter("use_qqq_confirm") or "1").strip().lower() not in (
            "0",
            "false",
            "no",
        )

        # Exposure map by regime
        self.exp_bull = float(self.GetParameter("exp_bull") or 1.00)
        self.exp_stress_up = float(self.GetParameter("exp_stress_up") or 0.60)
        self.exp_chop = float(self.GetParameter("exp_chop") or 0.20)
        self.exp_neutral = float(self.GetParameter("exp_neutral") or 0.35)
        self.exp_bear = float(self.GetParameter("exp_bear") or 0.00)

        # Turbo multipliers by regime
        self.turbo_mult_bull = float(self.GetParameter("turbo_mult_bull") or 1.00)
        self.turbo_mult_stress = float(self.GetParameter("turbo_mult_stress") or 0.00)
        self.turbo_mult_chop = float(self.GetParameter("turbo_mult_chop") or 0.00)
        self.turbo_mult_neutral = float(self.GetParameter("turbo_mult_neutral") or 0.25)
        self.turbo_mult_bear = float(self.GetParameter("turbo_mult_bear") or 0.00)

        # Safe overlays
        self.safe_overlay_stress = float(self.GetParameter("safe_overlay_stress") or 0.20)
        self.safe_overlay_chop = float(self.GetParameter("safe_overlay_chop") or 0.20)
        self.safe_overlay_neutral = float(self.GetParameter("safe_overlay_neutral") or 0.10)
        self.safe_overlay_bear = float(self.GetParameter("safe_overlay_bear") or 0.00)

        # Circuit-breaker (supports legacy mis-specified values like 0.935 -> 6.5% DD)
        raw_circuit = float(self.GetParameter("circuit_dd_pct") or 0.12)
        self.circuit_dd_pct = (1.0 - raw_circuit) if raw_circuit > 0.5 else raw_circuit
        self.circuit_dd_pct = max(0.02, min(0.50, self.circuit_dd_pct))
        self.cooldown_days = int(self.GetParameter("cooldown_days") or 20)

        # Daily risk lock
        self.daily_loss_limit_pct = float(self.GetParameter("daily_loss_limit_pct") or 0.02)
        self.daily_loss_limit_bull = float(self.GetParameter("dll_bull") or self.daily_loss_limit_pct)
        self.daily_loss_limit_stress = float(self.GetParameter("dll_str") or self.daily_loss_limit_pct)
        self.daily_loss_limit_chop = float(self.GetParameter("dll_chop") or self.daily_loss_limit_pct)
        self.daily_loss_limit_neutral = float(self.GetParameter("dll_neu") or self.daily_loss_limit_pct)
        self.daily_loss_limit_bear = float(self.GetParameter("dll_bear") or self.daily_loss_limit_pct)

        # Monthly drawdown throttle
        self.monthly_dd_throttle_trigger = float(self.GetParameter("monthly_dd_throttle_trigger") or 0.08)
        self.monthly_dd_throttle_mult = float(self.GetParameter("monthly_dd_throttle_mult") or 0.50)
        self.monthly_dd_trigger_bull = float(self.GetParameter("mtr_bull") or self.monthly_dd_throttle_trigger)
        self.monthly_dd_trigger_stress = float(self.GetParameter("mtr_str") or self.monthly_dd_throttle_trigger)
        self.monthly_dd_trigger_chop = float(self.GetParameter("mtr_chop") or self.monthly_dd_throttle_trigger)
        self.monthly_dd_trigger_neutral = float(self.GetParameter("mtr_neu") or self.monthly_dd_throttle_trigger)
        self.monthly_dd_trigger_bear = float(self.GetParameter("mtr_bear") or self.monthly_dd_throttle_trigger)
        self.monthly_dd_mult_bull = float(self.GetParameter("mtm_bull") or self.monthly_dd_throttle_mult)
        self.monthly_dd_mult_stress = float(self.GetParameter("mtm_str") or self.monthly_dd_throttle_mult)
        self.monthly_dd_mult_chop = float(self.GetParameter("mtm_chop") or self.monthly_dd_throttle_mult)
        self.monthly_dd_mult_neutral = float(self.GetParameter("mtm_neu") or self.monthly_dd_throttle_mult)
        self.monthly_dd_mult_bear = float(self.GetParameter("mtm_bear") or self.monthly_dd_throttle_mult)

        # Friction stress controls
        self.friction_mode = (self.GetParameter("friction_mode") or "0").strip().lower() not in ("0", "false", "no")
        self.friction_slippage_abs = float(self.GetParameter("friction_slippage_abs") or 0.0)
        self.friction_exposure_haircut = float(self.GetParameter("friction_exposure_haircut") or 0.0)
        self.max_weight_change_per_rebalance = float(
            self.GetParameter("max_wchg_per_reb") or self.GetParameter("max_weight_change_per_rebalance") or 1.0
        )

        self.symbols = {}
        self.ind = {}
        all_tickers = list(dict.fromkeys([self.spy_ticker, self.qqq_ticker, self.vixy_ticker] + self.core_assets + self.safe_assets + self.turbo_assets))
        for t in all_tickers:
            eq = self.AddEquity(t, Resolution.Daily)
            eq.SetDataNormalizationMode(DataNormalizationMode.Adjusted)
            if self.friction_mode and self.friction_slippage_abs > 0:
                eq.SetSlippageModel(ConstantSlippageModel(self.friction_slippage_abs))
            sym = eq.Symbol
            self.symbols[t] = sym
            self.ind[t] = {
                "roc_fast": self.ROC(sym, self.lookback_fast, Resolution.Daily),
                "roc_slow": self.ROC(sym, self.lookback_slow, Resolution.Daily),
                "atr": self.ATR(sym, self.atr_period, MovingAverageType.Simple, Resolution.Daily),
                "sma": self.SMA(sym, self.sma_filter_period, Resolution.Daily),
            }

        self.vixy_sma = self.SMA(self.symbols[self.vixy_ticker], self.vixy_sma_period, Resolution.Daily)
        self.SetWarmUp(max(self.lookback_slow, self.sma_filter_period, self.vixy_sma_period) + 10, Resolution.Daily)

        self.peak_equity = self.initial_cash
        self.cooldown_until = None
        self.regime = "NEUTRAL"
        self.regime_age = 0
        self.current_targets = {}
        self.last_turnover = 0.0

        self.day_key = None
        self.day_start_equity = self.initial_cash
        self.day_locked = False

        self.month_key = None
        self.month_peak_equity = self.initial_cash
        self.monthly_throttle_factor = 1.0

        if self.rebalance_daily:
            self.Schedule.On(
                self.DateRules.EveryDay(self.spy_ticker),
                self.TimeRules.AfterMarketOpen(self.spy_ticker, 35),
                self.Rebalance,
            )
        else:
            self.Schedule.On(
                self.DateRules.Every(DayOfWeek.Monday),
                self.TimeRules.AfterMarketOpen(self.spy_ticker, 35),
                self.Rebalance,
            )

    def OnData(self, data: Slice):
        if self.IsWarmingUp:
            return
        eq = self.Portfolio.TotalPortfolioValue

        self._roll_day_if_needed(eq)
        self._roll_month_if_needed(eq)

        if eq > self.peak_equity:
            self.peak_equity = eq
        if eq > self.month_peak_equity:
            self.month_peak_equity = eq

        day_pnl = eq - self.day_start_equity
        regime_daily_limit = self._regime_daily_limit()
        if day_pnl <= -(self.day_start_equity * regime_daily_limit) and not self.day_locked:
            self.day_locked = True
            self.Liquidate(tag="V12_DAILY_LOSS_LOCK")

        dd = (self.peak_equity - eq) / self.peak_equity if self.peak_equity > 0 else 0.0
        if dd >= self.circuit_dd_pct:
            if self.cooldown_until is None or self.Time > self.cooldown_until:
                self.Liquidate(tag="V12_CIRCUIT_BREAK")
                self.cooldown_until = self.Time + timedelta(days=self.cooldown_days)
                self.current_targets = {}
                self.regime = "COOLDOWN"
                self.regime_age = 0

        month_dd = (self.month_peak_equity - eq) / self.month_peak_equity if self.month_peak_equity > 0 else 0.0
        regime_trigger, regime_mult = self._regime_month_throttle()
        self.monthly_throttle_factor = regime_mult if month_dd >= regime_trigger else 1.0

        self.SetRuntimeStatistic("Regime", self.regime)
        self.SetRuntimeStatistic("DayLocked", "1" if self.day_locked else "0")
        self.SetRuntimeStatistic("DailyLimitPct", f"{regime_daily_limit*100.0:.2f}")
        self.SetRuntimeStatistic("MonthTrigPct", f"{regime_trigger*100.0:.2f}")
        self.SetRuntimeStatistic("MonthThrottle", f"{self.monthly_throttle_factor:.2f}")
        self.SetRuntimeStatistic("LastTurnoverPct", f"{self.last_turnover * 100.0:.2f}")

    def _regime_daily_limit(self):
        if self.regime == "BULL_TREND":
            return self.daily_loss_limit_bull
        if self.regime == "STRESS_UPTREND":
            return self.daily_loss_limit_stress
        if self.regime == "CHOP":
            return self.daily_loss_limit_chop
        if self.regime == "BEAR":
            return self.daily_loss_limit_bear
        return self.daily_loss_limit_neutral

    def _regime_month_throttle(self):
        if self.regime == "BULL_TREND":
            return self.monthly_dd_trigger_bull, self.monthly_dd_mult_bull
        if self.regime == "STRESS_UPTREND":
            return self.monthly_dd_trigger_stress, self.monthly_dd_mult_stress
        if self.regime == "CHOP":
            return self.monthly_dd_trigger_chop, self.monthly_dd_mult_chop
        if self.regime == "BEAR":
            return self.monthly_dd_trigger_bear, self.monthly_dd_mult_bear
        return self.monthly_dd_trigger_neutral, self.monthly_dd_mult_neutral

    def _roll_day_if_needed(self, eq):
        d = self.Time.date()
        if self.day_key is None:
            self.day_key = d
            self.day_start_equity = eq
            self.day_locked = False
            return
        if d != self.day_key:
            self.day_key = d
            self.day_start_equity = eq
            self.day_locked = False

    def _roll_month_if_needed(self, eq):
        m = (self.Time.year, self.Time.month)
        if self.month_key is None:
            self.month_key = m
            self.month_peak_equity = eq
            self.monthly_throttle_factor = 1.0
            return
        if m != self.month_key:
            self.month_key = m
            self.month_peak_equity = eq
            self.monthly_throttle_factor = 1.0

    def _ready(self, ticker):
        i = self.ind[ticker]
        return i["roc_fast"].IsReady and i["roc_slow"].IsReady and i["atr"].IsReady and i["sma"].IsReady

    def _score(self, ticker):
        sym = self.symbols[ticker]
        px = self.Securities[sym].Price
        if px is None or px <= 0:
            return None
        roc_f = float(self.ind[ticker]["roc_fast"].Current.Value)
        roc_s = float(self.ind[ticker]["roc_slow"].Current.Value)
        atr = float(self.ind[ticker]["atr"].Current.Value)
        atr_pct = atr / px if px > 0 else 0.0
        return self.w_fast * roc_f + self.w_slow * roc_s - self.vol_penalty * atr_pct

    def _normalize_and_cap(self, target):
        gross = sum(abs(v) for v in target.values())
        if gross > self.max_total_gross and gross > 0:
            k = self.max_total_gross / gross
            for t in list(target.keys()):
                target[t] *= k
        for t in list(target.keys()):
            target[t] = max(-self.max_single_weight, min(self.max_single_weight, target[t]))
        return target

    def _candidate_regime(self):
        spy_px = self.Securities[self.symbols[self.spy_ticker]].Price
        qqq_px = self.Securities[self.symbols[self.qqq_ticker]].Price
        spy_sma = float(self.ind[self.spy_ticker]["sma"].Current.Value)
        qqq_sma = float(self.ind[self.qqq_ticker]["sma"].Current.Value)
        spy_mom = float(self.ind[self.spy_ticker]["roc_fast"].Current.Value)

        vixy_px = self.Securities[self.symbols[self.vixy_ticker]].Price
        vixy_sma = float(self.vixy_sma.Current.Value) if self.vixy_sma.Current.Value else 0.0
        vixy_ratio = (vixy_px / vixy_sma) if (vixy_px and vixy_sma > 0) else 1.0

        up_spy = bool(spy_px > spy_sma * self.bull_sma_mult)
        dn_spy = bool(spy_px < spy_sma * self.bear_sma_mult)
        up_qqq = bool(qqq_px > qqq_sma * self.bull_sma_mult)
        dn_qqq = bool(qqq_px < qqq_sma * self.bear_sma_mult)
        qqq_bull_ok = (not self.use_qqq_confirm) or up_qqq
        qqq_bear_ok = (not self.use_qqq_confirm) or dn_qqq

        near_sma = abs((spy_px / spy_sma) - 1.0) <= self.chop_band_pct if spy_sma > 0 else False
        weak_mom = abs(spy_mom) <= self.chop_mom_abs

        if dn_spy and qqq_bear_ok and vixy_ratio >= self.bear_vixy_min:
            return "BEAR", vixy_ratio
        if up_spy and qqq_bull_ok and self.stress_vixy_min <= vixy_ratio <= self.stress_vixy_max:
            return "STRESS_UPTREND", vixy_ratio
        if near_sma and weak_mom:
            return "CHOP", vixy_ratio
        if up_spy and qqq_bull_ok and spy_mom >= self.bull_mom_min and vixy_ratio <= self.bull_vixy_max:
            return "BULL_TREND", vixy_ratio
        return "NEUTRAL", vixy_ratio

    def _update_regime(self, cand):
        if cand == self.regime:
            self.regime_age += 1
            return
        if self.regime not in ("COOLDOWN",) and self.regime_age < self.state_hold_days:
            self.regime_age += 1
            return
        self.regime = cand
        self.regime_age = 0

    def _regime_map(self):
        if self.regime == "BULL_TREND":
            expo, turbo, safe = self.exp_bull, self.turbo_mult_bull, 0.0
        elif self.regime == "STRESS_UPTREND":
            expo, turbo, safe = self.exp_stress_up, self.turbo_mult_stress, self.safe_overlay_stress
        elif self.regime == "CHOP":
            expo, turbo, safe = self.exp_chop, self.turbo_mult_chop, self.safe_overlay_chop
        elif self.regime == "BEAR":
            expo, turbo, safe = self.exp_bear, self.turbo_mult_bear, self.safe_overlay_bear
        else:
            expo, turbo, safe = self.exp_neutral, self.turbo_mult_neutral, self.safe_overlay_neutral

        # Apply monthly throttle + optional friction haircut.
        expo *= self.monthly_throttle_factor
        if self.friction_mode and self.friction_exposure_haircut > 0:
            expo *= max(0.0, 1.0 - self.friction_exposure_haircut)
            turbo *= max(0.0, 1.0 - self.friction_exposure_haircut)
        return expo, turbo, safe

    def Rebalance(self):
        if self.IsWarmingUp:
            return
        if self.day_locked:
            return
        if self.cooldown_until is not None and self.Time < self.cooldown_until:
            return
        if self.cooldown_until is not None and self.Time >= self.cooldown_until:
            self.cooldown_until = None
            self.regime = "NEUTRAL"
            self.regime_age = 0

        needed = list(dict.fromkeys([self.spy_ticker, self.qqq_ticker, self.vixy_ticker] + self.core_assets + self.safe_assets + self.turbo_assets))
        for t in needed:
            if not self._ready(t):
                return
        if not self.vixy_sma.IsReady:
            return

        cand, vixy_ratio = self._candidate_regime()
        self._update_regime(cand)
        self.SetRuntimeStatistic("VIXYRatio", f"{vixy_ratio:.3f}")

        expo_mult, turbo_mult, safe_overlay = self._regime_map()
        target = {}

        if expo_mult > 0:
            core_scores = {}
            for t in self.core_assets:
                s = self._score(t)
                if s is None:
                    return
                core_scores[t] = s
            core_rank = sorted(self.core_assets, key=lambda x: core_scores[x], reverse=True)
            selected_core = [t for t in core_rank if core_scores[t] >= self.min_core_signal][: self.max_core_active]
            if len(selected_core) == 0:
                selected_core = [core_rank[0]]
            core_gross = self.core_gross_base * max(0.0, expo_mult)
            cw = core_gross / len(selected_core)
            for t in selected_core:
                target[t] = cw

            tg = self.turbo_gross_base * max(0.0, expo_mult) * max(0.0, turbo_mult)
            if tg > 0:
                turbo_scores = {}
                for t in self.turbo_assets:
                    s = self._score(t)
                    if s is None:
                        return
                    turbo_scores[t] = s
                turbo_rank = sorted(self.turbo_assets, key=lambda x: turbo_scores[x], reverse=True)
                selected_turbo = [t for t in turbo_rank if turbo_scores[t] >= self.min_turbo_signal][: self.max_turbo_active]
                if len(selected_turbo) > 0:
                    tw = tg / len(selected_turbo)
                    for t in selected_turbo:
                        target[t] = target.get(t, 0.0) + tw

        if safe_overlay > 0:
            safe_scores = {}
            for t in self.safe_assets:
                s = self._score(t)
                if s is None:
                    return
                safe_scores[t] = s
            best_safe = max(self.safe_assets, key=lambda x: safe_scores[x])
            target[best_safe] = target.get(best_safe, 0.0) + safe_overlay

        target = self._normalize_and_cap(target)

        all_assets = list(dict.fromkeys(self.core_assets + self.safe_assets + self.turbo_assets))
        eq = self.Portfolio.TotalPortfolioValue
        turnover = 0.0
        for t in all_assets:
            sym = self.symbols[t]
            desired = float(target.get(t, 0.0))
            current = self.Portfolio[sym].HoldingsValue / eq if eq > 0 else 0.0
            delta = desired - current
            if abs(delta) > self.rebalance_buffer:
                if self.max_weight_change_per_rebalance < 1.0:
                    cap = max(0.01, self.max_weight_change_per_rebalance)
                    desired = current + max(-cap, min(cap, delta))
                self.SetHoldings(sym, desired, tag=f"V12_REB {self.regime} {t}")
                turnover += abs(desired - current)

        self.current_targets = target
        self.last_turnover = turnover

    def OnEndOfAlgorithm(self):
        eq = self.Portfolio.TotalPortfolioValue
        ret = (eq - self.initial_cash) / self.initial_cash if self.initial_cash else 0.0
        dd = (self.peak_equity - eq) / self.peak_equity if self.peak_equity > 0 else 0.0
        self.Log(f"FINAL v12 equity={eq:.2f} return_pct={ret*100:.2f} dd_pct={dd*100:.2f} regime={self.regime}")
