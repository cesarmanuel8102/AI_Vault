# V10_15_QQQ_SIGNATURE_20260408
# region imports
from AlgorithmImports import *
from datetime import timedelta
import numpy as np
# endregion


class BrainV10RegimeAdaptive(QCAlgorithm):
    """
    Brain V10.15 — Regime-Adaptive with EMA20 Sell-Only Gate (CHAMPION)
    ====================================================================

    CHAMPION METRICS:
      Sharpe 0.90, CAGR 26.5%, DD 16.6%, Net $11,617, WR 69%, Alpha 0.124
      Overall GOOD (VG:9 G:2 P:4 B:1) — only BELOW is Sortino 0.91 (needs 1.0)
      EMA20 sell-only gate: 2d below EMA20 → sell QQQ, immediate re-entry above

    Capital: $10K | Period: 2023-01-01 to 2026-03-23
    """

    # ===========================================================================
    # CONFIGURATION — V10.15 CHAMPION
    # ===========================================================================

    BT_START = (2023, 1, 1)
    BT_END   = (2026, 4, 7)
    CASH     = 10000

    # -- Regime Detection --
    HMM_LOOKBACK_DAYS   = 504
    HMM_N_COMPONENTS    = 3
    HMM_RETRAIN_DAYS    = 5
    REGIME_CONFIRM_DAYS = 5
    FEATURE_WINDOW      = 20

    # -- BULL Strategy --
    BULL_EQUITY_ALLOC     = 0.65
    BULL_REBAL_THRESHOLD  = 0.10
    BULL_EQUITY_WEIGHTS   = {"QQQ": 1.0}

    # [V10.15] EMA20 SELL-ONLY Gate para QQQ equity
    EQ_EMA_PERIOD         = 20
    EQ_EMA_DAYS_BELOW     = 2
    EQ_EMA_REQUIRE_SLOPE  = False

    # -- BEAR Strategy --
    BEAR_CAPITAL_PER_TRADE = 0.05
    BEAR_MAX_POSITIONS     = 2
    BEAR_TP_MULT           = 2.0
    BEAR_SL_MULT           = 0.50
    BEAR_DTE_MIN           = 14
    BEAR_DTE_MAX           = 30
    BEAR_PUT_DELTA_TARGET  = 0.30
    BEAR_TRAILING_ACTIVATE = 0.80
    BEAR_TRAILING_STOP_PCT = 0.50

    # -- Credit Spread Parameters --
    SHORT_DELTA_TARGET = 0.10
    SHORT_DELTA_MIN    = 0.06
    SHORT_DELTA_MAX    = 0.15
    SPREAD_WIDTH       = 5
    MIN_DTE            = 30
    MAX_DTE            = 45
    MIN_CREDIT         = 0.20
    MIN_SHORT_OI       = 100

    # -- Position Management (PCS) --
    PROFIT_TARGET_PCT  = 0.50
    LOSS_LIMIT_MULT    = 2.0
    DTE_EXIT           = 21
    DTE_FORCE_CLOSE    = 3

    # -- Sizing (PCS) --
    MAX_RISK_PER_TRADE = 0.04
    MAX_TOTAL_RISK     = 0.12
    MAX_CONCURRENT_PCS = 3
    PCS_WEEKLY_LOSS_LIMIT = 999
    PCS_MIN_EXPIRY_GAP    = 0

    # -- VIX Regime --
    VIX_FLOOR          = 14
    VIX_FULL_SIZE      = 25
    VIX_HALF_SIZE      = 35
    VIX_CALL_BUDGET    = 0.01

    # -- Entry Schedule --
    PCS_ENTRY_DAYS     = [0, 1, 2]
    PCS_ENTRY_HOUR     = 11
    BEAR_ENTRY_HOUR    = 10

    # -- VIX Extreme --
    VIX_EXTREME_EXIT   = 45
    VIX_REENTRY        = 30

    # ===========================================================================
    # INITIALIZATION
    # ===========================================================================

    def Initialize(self):
        start_year = self._param_int("start_year", self.BT_START[0])
        end_year = self._param_int("end_year", self.BT_END[0])

        if start_year > self.BT_START[0]:
            start_month, start_day = 1, 1
        else:
            start_month, start_day = self.BT_START[1], self.BT_START[2]

        if end_year < self.BT_END[0]:
            end_month, end_day = 12, 31
        else:
            end_month, end_day = self.BT_END[1], self.BT_END[2]

        self.SetStartDate(start_year, start_month, start_day)
        self.SetEndDate(end_year, end_month, end_day)
        self.SetCash(self.CASH)
        self.SetBrokerageModel(InteractiveBrokersBrokerageModel(AccountType.Margin))
        self.SetBenchmark("SPY")

        # -- SPY equity + options --
        eq = self.AddEquity("SPY", Resolution.Minute)
        eq.SetDataNormalizationMode(DataNormalizationMode.Raw)
        self.spy = eq.Symbol

        # -- QQQ equity --
        equity_leg = self.AddEquity("QQQ", Resolution.Minute)
        equity_leg.SetDataNormalizationMode(DataNormalizationMode.Raw)
        self.eq_symbol = equity_leg.Symbol

        self.equity_symbols = {"QQQ": self.eq_symbol}

        opt = self.AddOption("SPY", Resolution.Minute)
        opt.SetFilter(lambda u: u.Strikes(-30, 10)
                     .Expiration(self.BEAR_DTE_MIN, self.MAX_DTE + 10))
        self.opt_symbol = opt.Symbol

        # -- VIX --
        vix = self.AddData(CBOE, "VIX", Resolution.Daily)
        self.vix_symbol = vix.Symbol
        self.current_vix = 18.0

        # -- Indicators SPY (regime) --
        self.sma50  = self.SMA("SPY", 50,  Resolution.Daily)
        self.sma200 = self.SMA("SPY", 200, Resolution.Daily)
        self.ema10  = self.EMA("SPY", 10,  Resolution.Daily)  # BEAR gate

        # [V10.15] EMA20 para QQQ equity gate
        self.eq_ema20        = self.EMA("QQQ", self.EQ_EMA_PERIOD, Resolution.Daily)
        self.eq_ema20_prev   = None
        self.eq_days_below   = 0
        self.eq_gate_blocked = False
        self.eq_gate_log     = []

        # -- Rolling windows --
        self.daily_returns = RollingWindow[float](self.HMM_LOOKBACK_DAYS + 50)
        self.daily_vix     = RollingWindow[float](self.HMM_LOOKBACK_DAYS + 50)
        self.daily_close   = RollingWindow[float](self.HMM_LOOKBACK_DAYS + 50)
        self.prev_close    = None

        # -- HMM State --
        self.hmm_model           = None
        self.current_regime      = "SIDEWAYS"
        self.regime_raw          = "SIDEWAYS"
        self.regime_confirm_count = 0
        self.last_train_day      = -999
        self.regime_history      = []
        self.hmm_ready           = False
        self.hmm_state_map       = {}

        # -- PCS State --
        self.spreads              = {}
        self.closed_trades        = []
        self.entry_seq            = 0
        self.last_pcs_entry_date  = None
        self.current_week         = -1
        self.pcs_entries_this_week = 0
        self.cooldown_until       = None
        self.pcs_losses_this_week = 0

        # -- BEAR puts state --
        self.bear_positions      = {}
        self.last_bear_entry_date = None

        # -- Equity state --
        self.equity_target_shares = {"QQQ": 0}
        self.equity_initialized   = False
        self.target_equity_alloc  = 0.0
        self.transition_step      = 0.05

        # -- Portfolio tracking --
        self.peak_equity         = float(self.CASH)
        self.cached_chain        = None
        self.monthly_pnl_log     = {}
        self.monthly_start_equity = float(self.CASH)
        self.current_month       = 0

        self.SetWarmUp(timedelta(days=560))

        # -- Schedules --
        self.Schedule.On(self.DateRules.EveryDay("SPY"),
                        self.TimeRules.AfterMarketOpen("SPY", 5),
                        self._on_market_open)
        self.Schedule.On(self.DateRules.EveryDay("SPY"),
                        self.TimeRules.BeforeMarketClose("SPY", 5),
                        self._on_market_close)
        self.Schedule.On(self.DateRules.EveryDay("SPY"),
                        self.TimeRules.Every(timedelta(minutes=30)),
                        self._check_phantom_equities)
        self.Schedule.On(self.DateRules.EveryDay("SPY"),
                        self.TimeRules.AfterMarketOpen("SPY", 2),
                        self._force_close_expiring)
        self.Schedule.On(self.DateRules.EveryDay("SPY"),
                        self.TimeRules.AfterMarketOpen("SPY", 10),
                        self._daily_regime_update)

        # [V10.15] EMA20 gate at 15 min post-open
        self.Schedule.On(self.DateRules.EveryDay("QQQ"),
                        self.TimeRules.AfterMarketOpen("QQQ", 15),
                        self._update_eq_ema_gate)

        self.Schedule.On(self.DateRules.MonthStart("SPY"),
                        self.TimeRules.AfterMarketOpen("SPY", 30),
                        self._monthly_rebalance)

        self.Consolidate("SPY", Resolution.Daily, self._on_daily_bar)

    # ===========================================================================
    # DAILY BAR — FEATURE COLLECTION
    # ===========================================================================

    def _on_daily_bar(self, bar):
        close = bar.Close
        self.daily_close.Add(close)
        if self.prev_close is not None and self.prev_close > 0:
            ret = (close - self.prev_close) / self.prev_close
            self.daily_returns.Add(ret)
        self.prev_close = close

    # ===========================================================================
    # [V10.15] EMA20 GATE — QQQ EQUITY MOMENTUM FILTER
    # ===========================================================================

    def _update_eq_ema_gate(self):
        """
        [V10.15] EMA20 SELL-ONLY gate — basado en análisis empírico de 92 cruces.

        Lógica corregida vs V10.13:
          - NUNCA bloquea acumulación inicial (error de V10.13)
          - 2 días consecutivos bajo EMA20 → liquidar QQQ (sell trigger)
          - Re-entrada: primer día sobre EMA20 → reactivar acumulación (sin buffer)
          - eq_gate_blocked solo controla si hubo una venta reciente esperando re-entrada

        """
        if self.IsWarmingUp:
            return

        if not self.eq_ema20.IsReady:
            return

        eq_price = self.Securities[self.eq_symbol].Price
        if eq_price <= 0:
            return

        ema_val = self.eq_ema20.Current.Value

        # Slope del EMA20 (solo para logging)
        ema_slope = 0.0
        if self.eq_ema20_prev is not None and self.eq_ema20_prev > 0:
            ema_slope = (ema_val - self.eq_ema20_prev) / self.eq_ema20_prev
        self.eq_ema20_prev = ema_val

        # ── Precio BAJO EMA20 ──────────────────────────────────────────────────
        if eq_price < ema_val:
            self.eq_days_below += 1

            # Sell trigger: 2 días consecutivos bajo EMA20 y aún tenemos acciones
            if (self.eq_days_below >= self.EQ_EMA_DAYS_BELOW
                    and not self.eq_gate_blocked
                    and int(self.Portfolio[self.eq_symbol].Quantity) > 0):

                self.eq_gate_blocked = True
                self.eq_gate_log.append({
                    "date"      : self.Time.strftime("%Y-%m-%d"),
                    "action"    : "SELL",
                    "price"     : eq_price,
                    "ema20"     : ema_val,
                    "days_below": self.eq_days_below,
                })
                self.Log(f"[EMA20-GATE] SELL TRIGGER: QQQ ${eq_price:.2f} < EMA20 ${ema_val:.2f} "
                         f"({self.eq_days_below} días) → liquidando posición")
                self._liquidate_equity_leg("EMA20_SELL_TRIGGER")

        # ── Precio SOBRE EMA20 ─────────────────────────────────────────────────
        else:
            self.eq_days_below = 0  # resetear contador siempre

            # Re-entrada inmediata (sin buffer) cuando veníamos de una venta
            if self.eq_gate_blocked:
                self.eq_gate_blocked = False
                self.eq_gate_log.append({
                    "date"      : self.Time.strftime("%Y-%m-%d"),
                    "action"    : "REENTRY",
                    "price"     : eq_price,
                    "ema20"     : ema_val,
                    "ema_slope" : ema_slope,
                })
                self.Log(f"[EMA20-GATE] RE-ENTRY: QQQ ${eq_price:.2f} > EMA20 ${ema_val:.2f} "
                         f"slope={ema_slope:+.4f} → reacumulando QQQ")

    def _liquidate_equity_leg(self, reason):
        """
        [V10.15] Vende acciones QQQ pero NO resetea target_equity_alloc.
        El target se mantiene para re-acumular cuando EMA20 gate se desactiva.
        """
        eq_shares = int(self.Portfolio[self.eq_symbol].Quantity)
        if eq_shares > 0:
            self.MarketOrder(self.eq_symbol, -eq_shares)
            self.equity_target_shares["QQQ"] = 0
            eq_price = self.Securities[self.eq_symbol].Price
            value = eq_shares * eq_price
            self.Log(f"[EMA20-GATE] SOLD QQQ: {eq_shares} shares "
                     f"@ ${eq_price:.2f} = ${value:,.0f} | reason={reason}")
        else:
            self.Log(f"[EMA20-GATE] QQQ sell requested but 0 shares held | reason={reason}")

    # ===========================================================================
    # DATA FLOW
    # ===========================================================================

    def OnData(self, data):
        if self.IsWarmingUp:
            return

        if data.ContainsKey(self.vix_symbol):
            vix_val = data[self.vix_symbol].Value
            if vix_val > 0:
                self.current_vix = vix_val
                self.daily_vix.Add(vix_val)

        for kvp in data.OptionChains:
            if kvp.Key == self.opt_symbol:
                self.cached_chain = kvp.Value

        if self.current_regime in ("BULL", "SIDEWAYS"):
            if self.Time.hour == self.PCS_ENTRY_HOUR and self.Time.minute == 0:
                self._check_pcs_entry()

        if self.current_regime == "BEAR":
            if self.Time.hour == self.BEAR_ENTRY_HOUR and self.Time.minute == 0:
                self._check_bear_entry()

        if self.Time.minute in (0, 30) and self.Time.second < 5:
            self._manage_pcs_positions()
            self._manage_bear_positions()

    # ===========================================================================
    # REGIME DETECTION (HMM) — sin cambios vs V10.15
    # ===========================================================================

    def _daily_regime_update(self):
        if self.IsWarmingUp:
            return

        n_returns = self.daily_returns.Count
        n_vix     = self.daily_vix.Count

        if n_returns < self.HMM_LOOKBACK_DAYS or n_vix < self.FEATURE_WINDOW:
            self._fallback_regime()
            return

        trading_day = int((self.Time - self.StartDate).days)
        if trading_day - self.last_train_day >= self.HMM_RETRAIN_DAYS:
            self._train_hmm()
            self.last_train_day = trading_day

        if self.hmm_model is not None:
            self._predict_regime()
        else:
            self._fallback_regime()

        self._apply_regime()

    def _build_features(self, n_days):
        if self.daily_returns.Count < n_days or self.daily_vix.Count < n_days:
            return None

        returns  = [self.daily_returns[i] for i in range(min(n_days, self.daily_returns.Count))]
        returns.reverse()
        vix_vals = [self.daily_vix[i] for i in range(min(n_days, self.daily_vix.Count))]
        vix_vals.reverse()

        min_len = min(len(returns), len(vix_vals))
        if min_len < self.FEATURE_WINDOW + 10:
            return None
        returns  = returns[-min_len:]
        vix_vals = vix_vals[-min_len:]

        features = []
        for i in range(self.FEATURE_WINDOW, min_len):
            ret          = returns[i]
            vix          = vix_vals[i] / 100.0 if i < len(vix_vals) else 0.20
            window_rets  = returns[i - self.FEATURE_WINDOW:i]
            real_vol     = np.std(window_rets) * np.sqrt(252) if len(window_rets) > 1 else 0.15
            cum_ret      = sum(window_rets)
            vix_change   = ((vix_vals[i] - vix_vals[i - self.FEATURE_WINDOW]) /
                            max(vix_vals[i - self.FEATURE_WINDOW], 1)
                            if i >= self.FEATURE_WINDOW else 0)
            features.append([ret, vix, real_vol, cum_ret, vix_change])

        return np.array(features) if features else None

    def _train_hmm(self):
        try:
            from hmmlearn.hmm import GaussianHMM

            X = self._build_features(self.HMM_LOOKBACK_DAYS)
            if X is None or len(X) < 100:
                self.Log("HMM_TRAIN: Not enough features, skipping")
                return

            model = GaussianHMM(n_components=self.HMM_N_COMPONENTS,
                                covariance_type="full", n_iter=100,
                                random_state=42, tol=0.01)
            model.fit(X)

            state_means = model.means_
            regime_scores = []
            for s in range(self.HMM_N_COMPONENTS):
                score = state_means[s][0] * 0.5 + state_means[s][3] * 0.5
                regime_scores.append((s, score, state_means[s][2]))
            regime_scores.sort(key=lambda x: x[1])

            state_map = {}
            state_map[regime_scores[0][0]] = "BEAR"
            state_map[regime_scores[2][0]] = "BULL"
            state_map[regime_scores[1][0]] = "SIDEWAYS"

            self.hmm_model     = model
            self.hmm_state_map = state_map
            self.hmm_ready     = True

            self.Log(f"HMM_TRAIN: Trained on {len(X)} samples. "
                     f"State mapping: {state_map}. "
                     f"Means: {[f'{s[1]:.4f}' for s in regime_scores]}")

        except Exception as e:
            self.Log(f"HMM_TRAIN_ERROR: {str(e)[:200]}")
            self.hmm_ready = False

    def _predict_regime(self):
        try:
            X = self._build_features(self.FEATURE_WINDOW * 3)
            if X is None or len(X) < 5:
                return

            states          = self.hmm_model.predict(X)
            current_state   = states[-1]
            predicted_regime = self.hmm_state_map.get(current_state, "SIDEWAYS")

            if predicted_regime == self.regime_raw:
                self.regime_confirm_count += 1
            else:
                self.regime_raw           = predicted_regime
                self.regime_confirm_count = 1

            if self.regime_confirm_count >= self.REGIME_CONFIRM_DAYS:
                if predicted_regime != self.current_regime:
                    old                  = self.current_regime
                    self.current_regime  = predicted_regime
                    self.regime_history.append((self.Time, old, predicted_regime))
                    self.Log(f"REGIME_SWITCH: {old} -> {predicted_regime} "
                             f"(confirmed {self.regime_confirm_count} days)")

        except Exception as e:
            self.Log(f"HMM_PREDICT_ERROR: {str(e)[:200]}")

    def _fallback_regime(self):
        if not self.sma50.IsReady or not self.sma200.IsReady:
            return

        sma50  = self.sma50.Current.Value
        sma200 = self.sma200.Current.Value
        price  = self.Securities[self.spy].Price
        if price <= 0:
            return

        if sma50 > sma200 and price > sma50:
            new_regime = "BULL"
        elif sma50 < sma200 and price < sma50:
            new_regime = "BEAR"
        else:
            new_regime = "SIDEWAYS"

        if new_regime == self.regime_raw:
            self.regime_confirm_count += 1
        else:
            self.regime_raw           = new_regime
            self.regime_confirm_count = 1

        if self.regime_confirm_count >= self.REGIME_CONFIRM_DAYS:
            if new_regime != self.current_regime:
                old                 = self.current_regime
                self.current_regime = new_regime
                self.regime_history.append((self.Time, old, new_regime))
                self.Log(f"REGIME_SWITCH_FALLBACK: {old} -> {new_regime}")

    def _apply_regime(self):
        """
        [V10.15] EMA20 gate controla re-entrada en BULL.
        """
        if self.current_regime == "BULL":
            if not self.eq_gate_blocked:
                if self.target_equity_alloc < self.BULL_EQUITY_ALLOC:
                    self.target_equity_alloc = min(
                        self.BULL_EQUITY_ALLOC,
                        self.target_equity_alloc + self.transition_step
                    )
                    self._adjust_equity()
            else:
                self.Log(f"[EMA20-GATE] BULL but blocked by EMA20 gate")

        elif self.current_regime == "BEAR":
            if self.target_equity_alloc > 0:
                self.target_equity_alloc = max(
                    0.0,
                    self.target_equity_alloc - self.transition_step
                )
                self._adjust_equity()

        elif self.current_regime == "SIDEWAYS":
            if self.target_equity_alloc > 0:
                self.target_equity_alloc = max(
                    0.0,
                    self.target_equity_alloc - self.transition_step
                )
                self._adjust_equity()

    # ===========================================================================
    # EQUITY MANAGEMENT
    # ===========================================================================

    def _adjust_equity(self):
        eq = self.Portfolio.TotalPortfolioValue
        if eq <= 0:
            return

        for ticker, weight in self.BULL_EQUITY_WEIGHTS.items():
            sym   = self.equity_symbols[ticker]
            price = self.Securities[sym].Price
            if price <= 0:
                continue

            target_value  = eq * self.target_equity_alloc * weight
            target_shares = int(target_value / price)
            current_shares = int(self.Portfolio[sym].Quantity)
            diff = target_shares - current_shares

            if abs(diff) < 1:
                self.equity_target_shares[ticker] = current_shares
                continue

            if diff > 0:
                cost = diff * price
                margin_per_ticker = 0.70 / len(self.BULL_EQUITY_WEIGHTS)
                if cost > self.Portfolio.MarginRemaining * margin_per_ticker:
                    diff = max(1, int(self.Portfolio.MarginRemaining * margin_per_ticker / price))
                    if diff <= 0:
                        continue

            self.MarketOrder(sym, int(diff))
            self.equity_target_shares[ticker] = target_shares

            self.Log(f"EQUITY_ADJUST: {diff:+d} {ticker} (target_alloc={self.target_equity_alloc:.1%}, "
                      f"gate_blocked={self.eq_gate_blocked}, regime={self.current_regime})")

    def _monthly_rebalance(self):
        """[V10.15] Skip rebalance si EMA20 gate está bloqueado."""
        if self.eq_gate_blocked:
            self.Log(f"[EMA20-GATE] Monthly rebalance skipped — gate bloqueado")
            return

        if self.target_equity_alloc <= 0:
            return

        eq = self.Portfolio.TotalPortfolioValue
        if eq <= 0:
            return

        total_equity_value = 0
        for ticker, sym in self.equity_symbols.items():
            price = self.Securities[sym].Price
            if price > 0:
                total_equity_value += int(self.Portfolio[sym].Quantity) * price
        current_alloc = total_equity_value / eq if eq > 0 else 0

        if abs(current_alloc - self.target_equity_alloc) < self.BULL_REBAL_THRESHOLD:
            return

        for ticker, weight in self.BULL_EQUITY_WEIGHTS.items():
            sym   = self.equity_symbols[ticker]
            price = self.Securities[sym].Price
            if price <= 0:
                continue

            current_shares = int(self.Portfolio[sym].Quantity)
            target_value   = eq * self.target_equity_alloc * weight
            target_shares  = int(target_value / price)
            diff           = target_shares - current_shares

            if abs(diff) >= 1:
                margin_per_ticker = 0.70 / len(self.BULL_EQUITY_WEIGHTS)
                if diff > 0 and diff * price > self.Portfolio.MarginRemaining * margin_per_ticker:
                    diff = max(1, int(self.Portfolio.MarginRemaining * margin_per_ticker / price))
                self.MarketOrder(sym, int(diff))
                self.equity_target_shares[ticker] = target_shares
                self.Log(f"EQUITY_REBAL: {diff:+d} {ticker} (alloc={target_shares * price / eq:.1%})")

    def _check_phantom_equities(self):
        for ticker, sym in self.equity_symbols.items():
            current_shares = int(self.Portfolio[sym].Quantity)
            expected_shares = self.equity_target_shares.get(ticker, 0)
            excess = current_shares - expected_shares
            if abs(excess) >= 50:
                self.MarketOrder(sym, -int(excess))
                self.Log(f"PHANTOM_FIX: corrected {excess} excess {ticker} shares")

    # ===========================================================================
    # PCS ENTRY — sin cambios vs V10.15
    # ===========================================================================

    def _check_pcs_entry(self):
        if self.Time.weekday() not in self.PCS_ENTRY_DAYS:
            return

        today = self.Time.date()
        if self.last_pcs_entry_date == today:
            return

        if self.pcs_losses_this_week >= self.PCS_WEEKLY_LOSS_LIMIT:
            return

        if self.cooldown_until and self.Time < self.cooldown_until:
            return

        week = self.Time.isocalendar()[1]
        if week != self.current_week:
            self.current_week          = week
            self.pcs_entries_this_week = 0

        if self.pcs_entries_this_week >= len(self.PCS_ENTRY_DAYS):
            return

        if len(self.spreads) >= self.MAX_CONCURRENT_PCS:
            return

        eq         = self.Portfolio.TotalPortfolioValue
        total_risk = self._total_risk_deployed()
        if total_risk >= eq * self.MAX_TOTAL_RISK:
            return

        if self._current_dd() > 0.12:
            return

        vix = self.current_vix
        if vix < self.VIX_FLOOR:
            return

        if vix > self.VIX_HALF_SIZE:
            self._open_contrarian_call(eq)
            self.last_pcs_entry_date   = today
            self.pcs_entries_this_week += 1
            return

        size_mult = 0.5 if vix > self.VIX_FULL_SIZE else 1.0
        self._open_credit_spread(eq, size_mult)
        self.last_pcs_entry_date   = today
        self.pcs_entries_this_week += 1

    # ===========================================================================
    # BEAR ENTRY — sin cambios vs V10.15
    # ===========================================================================

    def _check_bear_entry(self):
        today = self.Time.date()
        if self.last_bear_entry_date == today:
            return

        if len(self.bear_positions) >= self.BEAR_MAX_POSITIONS:
            return

        if self.cached_chain is None:
            return

        if self.sma50.IsReady:
            price = self.Securities[self.spy].Price
            if price <= 0:
                return
            if price > self.sma50.Current.Value:
                return

        if self.ema10.IsReady:
            price = self.Securities[self.spy].Price
            if price > self.ema10.Current.Value:
                self.Log(f"BEAR_ENTRY_BLOCKED: price ${price:.2f} > EMA10 ${self.ema10.Current.Value:.2f}")
                return

        if self.current_vix > 40:
            return

        eq   = self.Portfolio.TotalPortfolioValue
        puts = []
        for c in self.cached_chain:
            if c.Right != OptionRight.Put:
                continue
            dte = (c.Expiry - self.Time).days
            if dte < self.BEAR_DTE_MIN or dte > self.BEAR_DTE_MAX:
                continue
            if c.AskPrice <= 0 or c.BidPrice <= 0:
                continue
            if c.Greeks and abs(c.Greeks.Delta) > 0:
                puts.append(c)

        if not puts:
            return

        target_puts = [c for c in puts
                      if c.Greeks and 0.20 <= abs(c.Greeks.Delta) <= 0.45]

        if target_puts:
            best_put = min(target_puts,
                          key=lambda c: abs(abs(c.Greeks.Delta) - self.BEAR_PUT_DELTA_TARGET))
        else:
            price        = self.Securities[self.spy].Price
            target_strike = price * 0.97
            best_put     = min(puts, key=lambda c: abs(c.Strike - target_strike))

        ask = best_put.AskPrice
        if ask <= 0:
            return

        budget = eq * self.BEAR_CAPITAL_PER_TRADE
        n      = max(1, int(budget / (ask * 100)))

        cost = n * ask * 100
        if cost > self.Portfolio.MarginRemaining * 0.20:
            n = max(1, int(self.Portfolio.MarginRemaining * 0.20 / (ask * 100)))
        if n <= 0:
            return

        self.MarketOrder(best_put.Symbol, n)

        self.entry_seq += 1
        tag = f"BEAR_PUT_{self.Time.strftime('%y%m%d')}_{self.entry_seq}"
        dte   = (best_put.Expiry - self.Time).days
        delta = abs(best_put.Greeks.Delta) if best_put.Greeks else 0

        self.bear_positions[tag] = dict(
            sym          = best_put.Symbol,
            strike       = float(best_put.Strike),
            expiry       = best_put.Expiry,
            n            = n,
            entry_price  = ask,
            t0           = self.Time,
            vix_at_entry = self.current_vix,
            spy_at_entry = self.Securities[self.spy].Price,
            max_risk_dollar = ask * n * 100,
            tp_price     = ask * self.BEAR_TP_MULT,
            sl_price     = ask * self.BEAR_SL_MULT,
        )

        self.last_bear_entry_date = today
        self.Log(f"OPEN {tag}: BUY {best_put.Strike:.0f}P x{n} ask=${ask:.2f} "
                 f"DTE={dte} delta={delta:.2f} VIX={self.current_vix:.1f} "
                 f"regime={self.current_regime}")

    # ===========================================================================
    # CREDIT SPREAD EXECUTION — sin cambios vs V10.15
    # ===========================================================================

    def _open_credit_spread(self, equity, size_mult):
        if self.cached_chain is None:
            return

        price = self.Securities[self.spy].Price
        if price <= 0:
            return

        puts = []
        for c in self.cached_chain:
            if c.Right != OptionRight.Put:
                continue
            dte = (c.Expiry - self.Time).days
            if dte < self.MIN_DTE or dte > self.MAX_DTE:
                continue
            if c.BidPrice <= 0 or c.AskPrice <= 0:
                continue
            puts.append(c)

        if not puts:
            return

        expiries = sorted(set(c.Expiry for c in puts))
        if not expiries:
            return

        existing_expiries = [s["expiry"] for s in self.spreads.values() if "expiry" in s]
        target_expiry     = None
        for candidate_exp in expiries:
            too_close = False
            for ex_exp in existing_expiries:
                gap = abs((candidate_exp - ex_exp).days)
                if gap < self.PCS_MIN_EXPIRY_GAP and gap > 0:
                    too_close = True
                    break
            if not too_close:
                target_expiry = candidate_exp
                break
        if target_expiry is None:
            return

        exp_puts  = [c for c in puts if c.Expiry == target_expiry]
        short_put = self._find_short_put(exp_puts, price)
        if short_put is None:
            return

        long_put = self._find_long_put(exp_puts, short_put)
        if long_put is None:
            return

        credit = short_put.BidPrice - long_put.AskPrice
        if credit < self.MIN_CREDIT:
            return

        actual_width           = float(short_put.Strike - long_put.Strike)
        max_risk_per_contract  = (actual_width - credit) * 100
        if max_risk_per_contract <= 0:
            return

        max_risk_budget  = equity * self.MAX_RISK_PER_TRADE * size_mult
        n                = max(1, int(max_risk_budget / max_risk_per_contract))
        remaining_budget = equity * self.MAX_TOTAL_RISK - self._total_risk_deployed()

        if max_risk_per_contract > remaining_budget:
            return

        n = min(n, max(1, int(remaining_budget / max_risk_per_contract)))

        bp              = self.Portfolio.MarginRemaining
        total_bp_needed = (long_put.AskPrice * 100 + max_risk_per_contract) * n
        if total_bp_needed > bp * 0.50:
            n = max(1, int(bp * 0.50 / (long_put.AskPrice * 100 + max_risk_per_contract)))

        if n <= 0:
            return

        self.MarketOrder(long_put.Symbol, n)
        self.MarketOrder(short_put.Symbol, -n)

        self.entry_seq += 1
        tag         = f"PCS_{self.Time.strftime('%y%m%d')}_{self.entry_seq}"
        dte         = (target_expiry - self.Time).days
        short_delta = abs(short_put.Greeks.Delta) if short_put.Greeks else 0

        self.spreads[tag] = dict(
            type            = "CREDIT_SPREAD",
            short_sym       = short_put.Symbol,
            long_sym        = long_put.Symbol,
            short_strike    = float(short_put.Strike),
            long_strike     = float(long_put.Strike),
            expiry          = target_expiry,
            n               = n,
            credit          = credit,
            max_profit      = credit * n * 100,
            max_risk_dollar = max_risk_per_contract * n,
            width           = actual_width,
            t0              = self.Time,
            vix_at_entry    = self.current_vix,
            spy_at_entry    = price,
            short_delta     = short_delta,
            regime_at_entry = self.current_regime,
        )

        self.Log(f"OPEN {tag}: SELL {short_put.Strike:.0f}P / BUY {long_put.Strike:.0f}P "
                 f"x{n} credit=${credit:.2f} DTE={dte} delta={short_delta:.2f} "
                 f"regime={self.current_regime}")

    def _find_short_put(self, puts, price):
        delta_candidates = [c for c in puts
                            if c.Greeks and self.SHORT_DELTA_MIN <= abs(c.Greeks.Delta) <= self.SHORT_DELTA_MAX]

        if delta_candidates:
            return min(delta_candidates,
                      key=lambda c: abs(abs(c.Greeks.Delta) - self.SHORT_DELTA_TARGET))

        with_delta = [c for c in puts
                     if c.Greeks and 0.04 < abs(c.Greeks.Delta) < 0.20]
        if with_delta:
            return min(with_delta,
                      key=lambda c: abs(abs(c.Greeks.Delta) - self.SHORT_DELTA_TARGET))

        target_strike = price * 0.94
        otm_puts = [c for c in puts if c.Strike < price and c.BidPrice > 0.05]
        if otm_puts:
            return min(otm_puts, key=lambda c: abs(c.Strike - target_strike))
        return None

    def _find_long_put(self, puts, short_put):
        target_long_strike = short_put.Strike - self.SPREAD_WIDTH
        for c in puts:
            if c.Strike == target_long_strike:
                return c

        lower = [c for c in puts if c.Strike < short_put.Strike]
        if not lower:
            return None

        candidates = [c for c in lower
                     if 3 <= float(short_put.Strike - c.Strike) <= 10]
        if candidates:
            return min(candidates,
                      key=lambda c: abs(float(short_put.Strike - c.Strike) - self.SPREAD_WIDTH))

        return max(lower, key=lambda c: c.Strike)

    # ===========================================================================
    # CONTRARIAN CALL — sin cambios vs V10.15
    # ===========================================================================

    def _open_contrarian_call(self, equity):
        if self.cached_chain is None:
            return

        price = self.Securities[self.spy].Price
        if price <= 0:
            return

        calls = [c for c in self.cached_chain
                if c.Right == OptionRight.Call
                and 30 <= (c.Expiry - self.Time).days <= 60
                and c.BidPrice > 0 and c.AskPrice > 0]

        if not calls:
            return

        target_strike = price * 1.02
        best = min(calls, key=lambda c: abs(c.Strike - target_strike))
        ask  = best.AskPrice
        if ask <= 0:
            return

        budget = equity * self.VIX_CALL_BUDGET
        n      = max(1, int(budget / (ask * 100)))
        cost   = ask * n * 100
        if cost > self.Portfolio.MarginRemaining * 0.3:
            n = max(1, int(self.Portfolio.MarginRemaining * 0.3 / (ask * 100)))
        if n <= 0:
            return

        self.MarketOrder(best.Symbol, n)
        self.entry_seq += 1
        tag = f"VIX_CALL_{self.Time.strftime('%y%m%d')}_{self.entry_seq}"

        self.spreads[tag] = dict(
            type            = "LONG_CALL",
            sym             = best.Symbol,
            strike          = float(best.Strike),
            expiry          = best.Expiry,
            n               = n,
            entry_price     = ask,
            t0              = self.Time,
            vix_at_entry    = self.current_vix,
            spy_at_entry    = price,
            max_risk_dollar = ask * n * 100,
            credit          = 0,
            max_profit      = 0,
            mfe             = 0.0,
            regime_at_entry = self.current_regime,
        )

        self.Log(f"OPEN {tag}: BUY {best.Strike:.0f}C x{n} ask=${ask:.2f} "
                 f"VIX={self.current_vix:.1f} regime={self.current_regime}")

    # ===========================================================================
    # POSITION MANAGEMENT — PCS — sin cambios vs V10.15
    # ===========================================================================

    def _manage_pcs_positions(self):
        if not self.spreads:
            return

        to_close = []
        for tag, pos in self.spreads.items():
            if pos.get("type") == "LONG_CALL":
                close, reason = self._should_close_call(pos)
            else:
                close, reason = self._should_close_spread(pos)
            if close:
                to_close.append((tag, reason))

        for tag, reason in to_close:
            self._close_pcs(tag, reason)

    def _should_close_spread(self, pos):
        dte = (pos["expiry"] - self.Time).days
        if dte <= self.DTE_EXIT:
            return True, f"DTE={dte}"

        short_mid = self._get_mid(pos["short_sym"])
        long_mid  = self._get_mid(pos["long_sym"])
        if short_mid is None or long_mid is None:
            return False, ""

        current_spread_value = short_mid - long_mid
        credit               = pos["credit"]
        current_profit       = credit - current_spread_value

        if credit > 0:
            profit_pct = current_profit / credit
            if profit_pct >= self.PROFIT_TARGET_PCT:
                return True, f"TP={profit_pct:.0%}"

        if current_profit < 0:
            loss = abs(current_profit)
            if loss >= credit * self.LOSS_LIMIT_MULT:
                return True, f"SL=loss_{loss:.2f}_vs_credit_{credit:.2f}"

        return False, ""

    def _should_close_call(self, pos):
        dte = (pos["expiry"] - self.Time).days
        if dte <= 5:
            return True, f"DTE={dte}"

        mid   = self._get_mid(pos.get("sym"))
        entry = pos["entry_price"]
        if mid is None or entry <= 0:
            return False, ""

        pnl_pct = (mid - entry) / entry
        if pnl_pct > pos.get("mfe", 0):
            pos["mfe"] = pnl_pct

        if pnl_pct >= 0.80:
            return True, f"TP_CALL={pnl_pct:+.0%}"
        if pnl_pct <= -0.60:
            return True, f"SL_CALL={pnl_pct:+.0%}"

        held = (self.Time - pos["t0"]).days
        if held >= 15 and abs(pnl_pct) < 0.10:
            return True, f"TIME_CALL={held}d"

        return False, ""

    # ===========================================================================
    # POSITION MANAGEMENT — BEAR PUTS — sin cambios vs V10.15
    # ===========================================================================

    def _manage_bear_positions(self):
        if not self.bear_positions:
            return

        to_close = []
        for tag, pos in self.bear_positions.items():
            sym = pos["sym"]
            if sym not in self.Securities:
                to_close.append((tag, "expired"))
                continue

            current_price = self.Securities[sym].Price
            if current_price <= 0:
                continue

            entry    = pos["entry_price"]
            dte      = (pos["expiry"] - self.Time).days
            gain_pct = (current_price - entry) / entry if entry > 0 else 0.0

            if "mfe_pct" not in pos:
                pos["mfe_pct"] = 0.0
            if gain_pct > pos["mfe_pct"]:
                pos["mfe_pct"] = gain_pct

            if current_price >= pos["tp_price"]:
                to_close.append((tag, f"TP_PUT={current_price/entry:.0%}"))
                continue

            if pos["mfe_pct"] >= self.BEAR_TRAILING_ACTIVATE:
                trail_floor = pos["mfe_pct"] * self.BEAR_TRAILING_STOP_PCT
                if gain_pct <= trail_floor:
                    to_close.append((tag, f"TRAIL_PUT=mfe_{pos['mfe_pct']:.0%}_now_{gain_pct:.0%}"))
                    continue

            if current_price <= pos["sl_price"]:
                to_close.append((tag, f"SL_PUT={current_price/entry:.0%}"))
                continue

            if dte <= 2:
                to_close.append((tag, f"DTE={dte}"))
                continue

            if self.current_regime != "BEAR":
                held = (self.Time - pos["t0"]).days
                if held >= 3:
                    if current_price >= entry or held >= 10:
                        to_close.append((tag, f"REGIME_EXIT_{self.current_regime}"))

        for tag, reason in to_close:
            self._close_bear(tag, reason)

    def _close_bear(self, tag, reason):
        pos = self.bear_positions.get(tag)
        if pos is None:
            return

        n   = pos["n"]
        sym = pos["sym"]
        mid = self._get_mid(sym)

        if mid and mid > 0:
            self.MarketOrder(sym, -n)
            pnl_dollar = (mid - pos["entry_price"]) * n * 100
        else:
            try:
                self.MarketOrder(sym, -n)
            except:
                pass
            pnl_dollar = -pos["entry_price"] * n * 100

        held = (self.Time - pos["t0"]).days

        self.closed_trades.append(dict(
            tag         = tag,
            type        = "BEAR_PUT",
            pnl_dollar  = pnl_dollar,
            held_days   = held,
            reason      = reason,
            vix_at_entry = pos.get("vix_at_entry", 0),
            spy_at_entry = pos.get("spy_at_entry", 0),
            n           = n,
            credit      = 0,
            max_risk    = pos.get("max_risk_dollar", 0),
            entry_date  = pos["t0"].strftime("%Y-%m-%d"),
            regime      = "BEAR",
        ))

        self.Log(f"CLOSE {tag}: {reason} | PnL=${pnl_dollar:+,.0f} held={held}d")
        del self.bear_positions[tag]

    # ===========================================================================
    # PCS CLOSE — sin cambios vs V10.15
    # ===========================================================================

    def _close_pcs(self, tag, reason):
        pos = self.spreads.get(tag)
        if pos is None:
            return

        n          = pos["n"]
        pnl_dollar = 0.0

        if pos.get("type") == "LONG_CALL":
            try:
                self.MarketOrder(pos["sym"], -n)
            except Exception as e:
                self.Log(f"ERROR closing {tag}: {e}")
            mid   = self._get_mid(pos.get("sym"))
            entry = pos["entry_price"]
            pnl_dollar = (mid - entry) * n * 100 if mid else -entry * n * 100
        else:
            try:
                self.MarketOrder(pos["short_sym"], n)
                self.MarketOrder(pos["long_sym"], -n)
            except Exception as e:
                self.Log(f"ERROR closing {tag}: {e}")

            short_mid = self._get_mid(pos["short_sym"])
            long_mid  = self._get_mid(pos["long_sym"])
            if short_mid is not None and long_mid is not None:
                close_cost  = short_mid - long_mid
                pnl_dollar  = (pos["credit"] - close_cost) * n * 100
            else:
                pnl_dollar = 0

        held = (self.Time - pos["t0"]).days

        self.closed_trades.append(dict(
            tag         = tag,
            type        = pos.get("type", "CREDIT_SPREAD"),
            pnl_dollar  = pnl_dollar,
            held_days   = held,
            reason      = reason,
            vix_at_entry = pos.get("vix_at_entry", 0),
            spy_at_entry = pos.get("spy_at_entry", 0),
            n           = n,
            credit      = pos.get("credit", 0),
            max_risk    = pos.get("max_risk_dollar", 0),
            entry_date  = pos["t0"].strftime("%Y-%m-%d"),
            regime      = pos.get("regime_at_entry", "?"),
        ))

        self.Log(f"CLOSE {tag}: {reason} | PnL=${pnl_dollar:+,.0f} held={held}d "
                 f"regime={pos.get('regime_at_entry', '?')}")

        if pnl_dollar < 0 and pos.get("type") != "LONG_CALL":
            self.cooldown_until       = self.Time + timedelta(days=3)
            self.pcs_losses_this_week += 1
            self.Log(f"COOLDOWN: 3-day block until {self.cooldown_until.strftime('%Y-%m-%d')}")

        del self.spreads[tag]

    # ===========================================================================
    # SCHEDULED EVENTS
    # ===========================================================================

    def _on_market_open(self):
        eq             = self.Portfolio.TotalPortfolioValue
        self.peak_equity = max(self.peak_equity, eq)

        week = self.Time.isocalendar()[1]
        if week != self.current_week:
            self.current_week          = week
            self.pcs_entries_this_week = 0
            self.pcs_losses_this_week  = 0

        m = self.Time.month
        if m != self.current_month:
            if self.current_month != 0:
                monthly_pnl = eq - self.monthly_start_equity
                key         = (self.Time.year, self.current_month)
                self.monthly_pnl_log[key] = monthly_pnl
            self.current_month        = m
            self.monthly_start_equity = eq

    def _on_market_close(self):
        eq = self.Portfolio.TotalPortfolioValue
        self.peak_equity = max(self.peak_equity, eq)
        dd = self._current_dd()

        eq_parts = []
        for ticker, sym in self.equity_symbols.items():
            shares = int(self.Portfolio[sym].Quantity)
            val    = shares * self.Securities[sym].Price
            eq_parts.append(f"{ticker}={shares}sh(${val:,.0f})")
        eq_str = " ".join(eq_parts)

        gate_str = (f"EMA20={'BLOCKED' if self.eq_gate_blocked else 'open'} "
                    f"days_below={self.eq_days_below}")

        self.Log(f"EOD eq=${eq:,.0f} dd={dd:.1%} regime={self.current_regime} "
                 f"{eq_str} {gate_str} "
                 f"PCS={len(self.spreads)} bears={len(self.bear_positions)} VIX={self.current_vix:.1f}")

    def _force_close_expiring(self):
        for holding in self.Portfolio.Values:
            if not holding.Invested:
                continue
            sym = holding.Symbol
            if sym.SecurityType != SecurityType.Option:
                continue
            dte = (sym.ID.Date - self.Time).days
            if dte <= self.DTE_FORCE_CLOSE:
                qty = holding.Quantity
                self.MarketOrder(sym, -qty)

                tags_to_close = []
                for tag, pos in self.spreads.items():
                    if pos.get("short_sym") == sym or pos.get("long_sym") == sym or pos.get("sym") == sym:
                        tags_to_close.append(tag)
                for tag in tags_to_close:
                    if tag in self.spreads:
                        self._close_pcs(tag, f"FORCE_EXPIRE_DTE={dte}")

                bear_to_close = []
                for tag, pos in self.bear_positions.items():
                    if pos.get("sym") == sym:
                        bear_to_close.append(tag)
                for tag in bear_to_close:
                    if tag in self.bear_positions:
                        self._close_bear(tag, f"FORCE_EXPIRE_DTE={dte}")

    # ===========================================================================
    # HELPERS
    # ===========================================================================

    def _param_int(self, name, default):
        raw = self.GetParameter(name)
        if raw is None or raw == "":
            return default
        try:
            return int(raw)
        except Exception:
            self.Log(f"PARAM_WARN: invalid {name}={raw}; using default {default}")
            return default

    def _current_dd(self):
        eq = self.Portfolio.TotalPortfolioValue
        if self.peak_equity <= 0:
            return 0.0
        return max(0.0, 1.0 - eq / self.peak_equity)

    def _total_risk_deployed(self):
        return sum(s.get("max_risk_dollar", 0) for s in self.spreads.values())

    def _get_mid(self, sym):
        if sym is None:
            return None
        try:
            sec = self.Securities[sym]
            if sec.BidPrice > 0 and sec.AskPrice > 0:
                return (sec.BidPrice + sec.AskPrice) * 0.5
            if sec.Price > 0:
                return sec.Price
        except Exception:
            pass
        return None

    # ===========================================================================
    # END-OF-ALGORITHM REPORT — V10.15 CHAMPION
    # ===========================================================================

    def OnEndOfAlgorithm(self):
        self.Liquidate()

        for tag in list(self.spreads.keys()):
            self._close_pcs(tag, "EOA")

        for tag in list(self.bear_positions.keys()):
            self._close_bear(tag, "EOA")

        for ticker, sym in self.equity_symbols.items():
            shares = int(self.Portfolio[sym].Quantity)
            if shares != 0:
                self.MarketOrder(sym, -shares)

        self.Log("=" * 70)
        self.Log("BRAIN V10.15 — EMA20 SELL-ONLY GATE — FINAL REPORT (CHAMPION)")
        self.Log("=" * 70)

        eq      = self.Portfolio.TotalPortfolioValue
        trades  = self.closed_trades
        n_trades = len(trades)
        if n_trades == 0:
            self.Log("NO TRADES EXECUTED")
            return

        wins      = sum(1 for t in trades if t["pnl_dollar"] > 0)
        total_pnl = sum(t["pnl_dollar"] for t in trades)
        wr        = wins / n_trades * 100

        gross_win = sum(t["pnl_dollar"] for t in trades if t["pnl_dollar"] > 0)
        gross_loss = abs(sum(t["pnl_dollar"] for t in trades if t["pnl_dollar"] < 0))
        pf         = gross_win / gross_loss if gross_loss > 0 else 999

        self.Log(f"  Trades: {n_trades} | Wins: {wins} | WR: {wr:.1f}%")
        self.Log(f"  Total PnL: ${total_pnl:+,.0f} | PF: {pf:.2f}")

        ret = eq / self.CASH - 1
        self.Log(f"  Equity: ${eq:,.0f} | Return: {ret:+.2%} | Peak: ${self.peak_equity:,.0f}")

        # Por tipo
        for t_type in ("CREDIT_SPREAD", "LONG_CALL", "BEAR_PUT"):
            type_trades = [t for t in trades if t["type"] == t_type]
            if not type_trades:
                continue
            tw  = sum(1 for t in type_trades if t["pnl_dollar"] > 0)
            tp  = sum(t["pnl_dollar"] for t in type_trades)
            twr = tw / len(type_trades) * 100
            self.Log(f"  {t_type}: {len(type_trades)} trades WR={twr:.0f}% PnL=${tp:+,.0f}")

        # Por régimen
        self.Log("--- BY REGIME AT ENTRY ---")
        for regime in ("BULL", "BEAR", "SIDEWAYS", "?"):
            rtrades = [t for t in trades if t.get("regime", "?") == regime]
            if not rtrades:
                continue
            rw  = sum(1 for t in rtrades if t["pnl_dollar"] > 0)
            rp  = sum(t["pnl_dollar"] for t in rtrades)
            rwr = rw / len(rtrades) * 100
            self.Log(f"  {regime}: {len(rtrades)} trades WR={rwr:.0f}% PnL=${rp:+,.0f}")

        # EMA20 Gate stats
        self.Log("--- EMA20 SELL-ONLY GATE ACTIVATIONS ---")
        self.Log(f"  Total eventos: {len(self.eq_gate_log)}")
        for event in self.eq_gate_log:
            action = event["action"]
            date   = event["date"]
            price  = event.get("price", 0)
            ema    = event.get("ema20", 0)
            if action == "SELL":
                days = event.get("days_below", 0)
                self.Log(f"  SELL    {date}: QQQ ${price:.2f} < EMA20 ${ema:.2f} ({days}d bajo)")
            else:
                slope = event.get("ema_slope", 0)
                self.Log(f"  REENTRY {date}: QQQ ${price:.2f} > EMA20 ${ema:.2f} slope={slope:+.4f}")

        # Historial de regímenes
        self.Log("--- REGIME HISTORY ---")
        for ts, old, new in self.regime_history:
            self.Log(f"  {ts.strftime('%Y-%m-%d')}: {old} -> {new}")

        # PnL mensual
        self.Log("--- MONTHLY PnL ---")
        if self.current_month != 0:
            key = (self.Time.year, self.current_month)
            if key not in self.monthly_pnl_log:
                self.monthly_pnl_log[key] = eq - self.monthly_start_equity
        for key in sorted(self.monthly_pnl_log.keys()):
            pnl    = self.monthly_pnl_log[key]
            marker = ">>>" if pnl < -500 else ("+++" if pnl > 500 else "   ")
            self.Log(f"  {marker} {key[0]}-{key[1]:02d}: ${pnl:+,.0f}")

        self.Log("=" * 70)
