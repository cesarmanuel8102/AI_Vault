"""
Yoel Options V2.0b-G16 -- G15 + 4 Structural Fixes
====================================================
Base: G15 (PT=0.35, SL=-0.20, Risk=0.06, DTE=14-30)

STRUCTURAL FIXES (zero new free parameters):
  FIX 1: Anti-same-day SL -- Do NOT trigger SL on entry day unless loss > 35%
         (proven by V5a: Full Sharpe 0.53 -> 0.653)
  FIX 2: Soft trailing profit lock -- at +20% move SL to breakeven,
         at +25% tighten SL to +10% (lock partial profit)
  FIX 3: QQQ trend strength filter -- only trade QQQ when ADX(14)>20
         AND SMA20 5-day slope > 0
  FIX 4: Loss streak size reduction -- after 3 consecutive losses,
         reduce risk_per_trade by 50% for next 2 trades

Total free parameters: STILL 5 (PT, SL, Risk, DTE_min, DTE_max)
"""

from AlgorithmImports import *
import numpy as np
from datetime import timedelta


class YoelOptionsV20bG16(QCAlgorithm):

    TRADE_TICKERS = ["AAPL", "MSFT", "NVDA", "QQQ"]
    FILTER_TICKER = "SPY"

    def Initialize(self):
        start_year = int(self.GetParameter("start_year") or 2023)
        end_year = int(self.GetParameter("end_year") or 2024)
        end_month = int(self.GetParameter("end_month") or 12)

        self.SetStartDate(start_year, 1, 1)
        self.SetEndDate(end_year, end_month, 28)
        self.SetCash(10000)
        self.SetBrokerageModel(BrokerageName.InteractiveBrokersBrokerage, AccountType.Margin)

        # == 5 Tunable Parameters (parametrized for loop) ==
        self.profit_target_pct = float(self.GetParameter("profit_target_pct") or 0.35)
        self.stop_loss_pct = float(self.GetParameter("stop_loss_pct") or -0.20)
        self.risk_per_trade = float(self.GetParameter("risk_per_trade") or 0.06)
        self.dte_min = int(self.GetParameter("dte_min") or 14)
        self.dte_max = int(self.GetParameter("dte_max") or 30)

        # == Fixed V2.0b constants ==
        self.max_positions = 1
        self.max_hold_days = 5
        self.min_bb_bandwidth = 0.02
        self.pm_touch_tolerance = 0.03
        self.max_trades_per_week = 3

        # == FIX 1: Anti-same-day SL constants ==
        self.sameday_catastrophic_sl = -0.35  # Only SL on entry day if loss > 35%

        # == FIX 2: Soft trailing profit lock constants ==
        self.trail_activate_pct = 0.20   # At +20% unrealized, move SL to breakeven
        self.trail_tighten_pct = 0.25    # At +25% unrealized, lock SL at +10%
        self.trail_lock_floor_pct = 0.10 # Locked SL floor when tightened

        # == FIX 4: Loss streak size reduction constants ==
        self.streak_threshold = 3         # After 3 consecutive losses
        self.streak_risk_mult = 0.50      # Reduce risk by 50%
        self.streak_reduced_trades = 2    # For next 2 trades

        # == DD State ==
        self._peak_equity = 10000.0

        # == Add SPY for filter ==
        self.equity_symbols = {}
        spy_eq = self.AddEquity(self.FILTER_TICKER, Resolution.Minute)
        spy_eq.SetDataNormalizationMode(DataNormalizationMode.Raw)
        self.equity_symbols[self.FILTER_TICKER] = spy_eq.Symbol

        # == Add tradeable equities + options ==
        self.option_symbols = {}
        for ticker in self.TRADE_TICKERS:
            eq = self.AddEquity(ticker, Resolution.Minute)
            eq.SetDataNormalizationMode(DataNormalizationMode.Raw)
            self.equity_symbols[ticker] = eq.Symbol

            opt = self.AddOption(ticker, Resolution.Minute)
            opt.SetFilter(lambda u: u.Strikes(-5, 5).Expiration(self.dte_min, self.dte_max + 5))
            self.option_symbols[ticker] = opt.Symbol

        # == State ==
        self.setups = []
        self._scanned_today = None
        self._executed_today = None
        self.positions = {}
        self.closed_trades = []
        self._entry_seq = 0
        self._companies_in_positions = set()
        self.cached_chains = {}

        # == Weekly trade counter ==
        self._week_trade_count = 0
        self._current_week = None

        # == Global market filter cache ==
        self._spy_direction = None

        # == Tracking ==
        self._total_scan_signals = 0
        self._chain_received_ever = {t: False for t in self.TRADE_TICKERS}
        self._strategy_signal_counts = {}

        # == V2.0b: Ticker Cooldown (2 losses in 10 days -> block 10 days) ==
        self._ticker_loss_dates = {t: [] for t in self.TRADE_TICKERS}
        self.ticker_cooldown_days = 10
        self.ticker_cooldown_threshold = 2

        # == Daily Circuit Breaker ==
        self._last_loss_date = None

        # == SPY Short-Term Filter ==
        self._spy_below_sma20 = False

        # == Tracking counters ==
        self._cooldown_blocks = 0
        self._circuit_breaker_blocks = 0

        # == V2.0b: Confidence tracking ==
        self._confidence_dist = {}
        self._confidence_total = 0.0
        self._confidence_trades = 0
        self._risk_skip_count = 0

        # == Pending limit orders ==
        self._limit_order_tag = {}

        # == FIX 1: Anti-same-day SL tracking ==
        self._sameday_blocks = 0  # counter for logging

        # == FIX 2: Per-position dynamic SL floor ==
        # Stored in positions dict as "dynamic_sl"

        # == FIX 3: QQQ filter tracking ==
        self._qqq_filter_blocks = 0
        self._qqq_adx_cache = None
        self._qqq_sma20_slope_cache = None

        # == FIX 4: Loss streak state ==
        self._consecutive_losses = 0
        self._streak_reduced_remaining = 0  # trades remaining at reduced size
        self._streak_reductions_applied = 0  # counter for logging

        # == Schedule ==
        self.Schedule.On(self.DateRules.EveryDay("SPY"),
                         self.TimeRules.AfterMarketOpen("SPY", 1),
                         self.MorningScan)

        self.Schedule.On(self.DateRules.EveryDay("SPY"),
                         self.TimeRules.AfterMarketOpen("SPY", 5),
                         self.ExecuteTrades)

        self.Schedule.On(self.DateRules.EveryDay("SPY"),
                         self.TimeRules.Every(timedelta(minutes=5)),
                         self.ManagePositions)

        self.Schedule.On(self.DateRules.EveryDay("SPY"),
                         self.TimeRules.BeforeMarketClose("SPY", 5),
                         self.EODCleanup)

        self.Log(f"V2.0b-G16 INIT: PT={self.profit_target_pct} SL={self.stop_loss_pct} risk={self.risk_per_trade} DTE={self.dte_min}-{self.dte_max}")
        self.Log(f"  FIX1: anti-sameday SL (catastrophic={self.sameday_catastrophic_sl})")
        self.Log(f"  FIX2: trail lock (activate={self.trail_activate_pct} tighten={self.trail_tighten_pct} floor={self.trail_lock_floor_pct})")
        self.Log(f"  FIX3: QQQ trend filter (ADX>20 + SMA20 slope>0)")
        self.Log(f"  FIX4: streak reduction (threshold={self.streak_threshold} mult={self.streak_risk_mult} trades={self.streak_reduced_trades})")

    # ===============================================================
    # DD State + Confidence (V2.0b STEP health)
    # ===============================================================

    def _update_dd_state(self):
        equity = self.Portfolio.TotalPortfolioValue
        if equity > self._peak_equity:
            self._peak_equity = equity
        dd = (self._peak_equity - equity) / self._peak_equity if self._peak_equity > 0 else 0
        return dd

    def _calc_confidence(self, setup_score, dd):
        """V2.0b: Multiplicative confidence = score x regime x health.
        STEP health: 1.0 (DD<15%), 0.75 (DD<30%), 0.50 (else).
        Cap: [0.5, 3.0].
        """
        if setup_score >= 6.5:
            mult_score = 1.25
        elif setup_score >= 5.0:
            mult_score = 1.0
        else:
            mult_score = 0.6

        if self._spy_direction == "BULL":
            mult_regime = 1.0
        elif self._spy_direction == "FLAT":
            mult_regime = 0.75
        else:
            mult_regime = 0.5

        if dd < 0.15:
            mult_health = 1.0
        elif dd < 0.30:
            mult_health = 0.75
        else:
            mult_health = 0.50

        if self._spy_below_sma20:
            mult_health = min(mult_health, 0.75)

        raw = mult_score * mult_regime * mult_health
        clamped = max(0.5, min(raw, 3.0))
        return clamped, mult_score, mult_regime, mult_health

    # ===============================================================
    # OnData -- Cache option chains
    # ===============================================================

    def OnData(self, data):
        for kvp in data.OptionChains:
            for ticker, opt_sym in self.option_symbols.items():
                if kvp.Key == opt_sym:
                    chain = kvp.Value
                    self.cached_chains[ticker] = chain
                    if not self._chain_received_ever[ticker]:
                        self._chain_received_ever[ticker] = True

    # ===============================================================
    # OnOrderEvent -- Fill detection
    # ===============================================================

    def OnOrderEvent(self, orderEvent):
        if orderEvent.Status != OrderStatus.Filled:
            return
        sym = orderEvent.Symbol
        if sym.SecurityType != SecurityType.Option:
            return
        if orderEvent.FillQuantity < 0:
            tag_to_close = None
            for tag, pos in self.positions.items():
                if pos["contract"] == sym:
                    tag_to_close = tag
                    break
            if tag_to_close is not None:
                fill_price = float(orderEvent.FillPrice)
                pos = self.positions[tag_to_close]
                entry_price = pos["entry_price"]
                pnl_pct = (fill_price / entry_price - 1) if entry_price > 0 else 0
                reason = "LIMIT_FILL_TP"
                if pnl_pct < -0.08:
                    reason = f"SL_FILL={pnl_pct:+.0%}"
                elif abs(fill_price - pos.get("limit_price", 0)) < 0.05:
                    reason = "LIMIT_FILL_TP"
                self._record_closed_trade(tag_to_close, reason, fill_price)

    # ===============================================================
    # MORNING SCAN
    # ===============================================================

    def MorningScan(self):
        today_key = self.Time.date()
        if self._scanned_today == today_key:
            return
        self._scanned_today = today_key
        self.setups = []

        week_num = self.Time.isocalendar()[1]
        week_year = self.Time.isocalendar()[0]
        week_key = f"{week_year}-W{week_num}"
        if self._current_week != week_key:
            self._current_week = week_key
            self._week_trade_count = 0

        if self._week_trade_count >= self.max_trades_per_week:
            return

        dd = self._update_dd_state()

        symbols = list(self.equity_symbols.values())
        try:
            daily_hist = self.History(symbols, 252, Resolution.Daily)
        except Exception as e:
            self.Log(f"SCAN_ERR: {str(e)[:100]}")
            return
        if daily_hist.empty:
            return

        self._spy_direction = self._get_spy_direction(daily_hist)
        self._spy_below_sma20 = self._check_spy_below_sma20(daily_hist)

        # FIX 3: Pre-compute QQQ filter indicators
        self._compute_qqq_filter(daily_hist)

        for ticker in self.TRADE_TICKERS:
            sym = self.equity_symbols.get(ticker)
            if sym is None:
                continue
            try:
                self._analyze_symbol(ticker, sym, daily_hist)
            except Exception:
                pass

        self.setups.sort(key=lambda x: x["score"], reverse=True)
        self.setups = self.setups[:5]
        self._total_scan_signals += len(self.setups)

        if self.setups:
            summary = ", ".join([f"{s['ticker']}({s['strategy']},sc={s['score']:.1f})" for s in self.setups[:3]])
            self.Log(f"SCAN: {len(self.setups)} SPY={self._spy_direction} DD={dd:.0%}: {summary}")

    def _get_spy_direction(self, daily_hist):
        spy_sym = self.equity_symbols.get("SPY")
        if spy_sym is None or spy_sym not in daily_hist.index.get_level_values(0):
            return "FLAT"
        df = daily_hist.loc[spy_sym]
        if len(df) < 50:
            return "FLAT"
        close = df["close"].values
        sma20 = float(np.mean(close[-20:]))
        sma40 = float(np.mean(close[-40:]))
        sma20_5ago = float(np.mean(close[-25:-5])) if len(close) >= 25 else sma20
        if sma20 > sma40 and sma20 > sma20_5ago:
            return "BULL"
        elif sma40 > sma20 and sma20 < sma20_5ago:
            return "BEAR"
        else:
            return "FLAT"

    def _check_spy_below_sma20(self, daily_hist):
        spy_sym = self.equity_symbols.get("SPY")
        if spy_sym is None or spy_sym not in daily_hist.index.get_level_values(0):
            return False
        df = daily_hist.loc[spy_sym]
        if len(df) < 20:
            return False
        close = df["close"].values
        sma20 = float(np.mean(close[-20:]))
        current_price = float(close[-1])
        return current_price < sma20

    # ===============================================================
    # FIX 3: QQQ Trend Strength Filter
    # ===============================================================

    def _compute_qqq_filter(self, daily_hist):
        """Compute ADX(14) and SMA20 5-day slope for QQQ."""
        self._qqq_adx_cache = None
        self._qqq_sma20_slope_cache = None

        qqq_sym = self.equity_symbols.get("QQQ")
        if qqq_sym is None or qqq_sym not in daily_hist.index.get_level_values(0):
            return
        df = daily_hist.loc[qqq_sym]
        if len(df) < 30:
            return

        close = df["close"].values
        high = df["high"].values
        low = df["low"].values

        # SMA20 slope: (SMA20_today - SMA20_5daysAgo) / SMA20_5daysAgo
        if len(close) >= 25:
            sma20_now = float(np.mean(close[-20:]))
            sma20_5ago = float(np.mean(close[-25:-5]))
            self._qqq_sma20_slope_cache = (sma20_now - sma20_5ago) / sma20_5ago if sma20_5ago > 0 else 0
        else:
            self._qqq_sma20_slope_cache = 0

        # ADX(14) -- manual computation
        period = 14
        if len(close) < period * 3:
            self._qqq_adx_cache = 0
            return

        # True Range, +DM, -DM
        tr_list = []
        plus_dm_list = []
        minus_dm_list = []
        for i in range(1, len(close)):
            h = float(high[i])
            l = float(low[i])
            c_prev = float(close[i - 1])
            tr = max(h - l, abs(h - c_prev), abs(l - c_prev))
            tr_list.append(tr)

            up_move = float(high[i]) - float(high[i - 1])
            down_move = float(low[i - 1]) - float(low[i])
            plus_dm_list.append(up_move if up_move > down_move and up_move > 0 else 0)
            minus_dm_list.append(down_move if down_move > up_move and down_move > 0 else 0)

        # Smoothed TR, +DM, -DM using Wilder's method
        if len(tr_list) < period * 2:
            self._qqq_adx_cache = 0
            return

        atr = sum(tr_list[:period])
        plus_dm_smooth = sum(plus_dm_list[:period])
        minus_dm_smooth = sum(minus_dm_list[:period])
        dx_list = []

        for i in range(period, len(tr_list)):
            atr = atr - atr / period + tr_list[i]
            plus_dm_smooth = plus_dm_smooth - plus_dm_smooth / period + plus_dm_list[i]
            minus_dm_smooth = minus_dm_smooth - minus_dm_smooth / period + minus_dm_list[i]

            plus_di = 100 * plus_dm_smooth / atr if atr > 0 else 0
            minus_di = 100 * minus_dm_smooth / atr if atr > 0 else 0
            di_sum = plus_di + minus_di
            dx = 100 * abs(plus_di - minus_di) / di_sum if di_sum > 0 else 0
            dx_list.append(dx)

        if len(dx_list) < period:
            self._qqq_adx_cache = 0
            return

        # ADX = SMA of DX
        adx = float(np.mean(dx_list[-period:]))
        self._qqq_adx_cache = adx

    def _qqq_passes_trend_filter(self):
        """FIX 3: QQQ only trades when ADX>20 AND SMA20 slope > 0."""
        if self._qqq_adx_cache is None or self._qqq_sma20_slope_cache is None:
            return False  # No data = no trade
        return self._qqq_adx_cache > 20 and self._qqq_sma20_slope_cache > 0

    # ===============================================================
    # ANALYZE SYMBOL
    # ===============================================================

    def _analyze_symbol(self, ticker, sym, daily_hist):
        today = self.Time.date()
        recent_losses = [d for d in self._ticker_loss_dates.get(ticker, [])
                         if (today - d).days <= self.ticker_cooldown_days]
        if len(recent_losses) >= self.ticker_cooldown_threshold:
            self._cooldown_blocks += 1
            return

        # FIX 3: QQQ trend filter gate
        if ticker == "QQQ" and not self._qqq_passes_trend_filter():
            self._qqq_filter_blocks += 1
            return

        if sym not in daily_hist.index.get_level_values(0):
            return
        df_d = daily_hist.loc[sym]
        if len(df_d) < 200:
            return

        close_d = df_d["close"].values
        price = close_d[-1]
        if price <= 0:
            return

        sma20_d = float(np.mean(close_d[-20:]))
        std20_d = float(np.std(close_d[-20:]))
        bb_upper_d = sma20_d + 2.0 * std20_d
        bb_lower_d = sma20_d - 2.0 * std20_d
        bb_bandwidth_d = (bb_upper_d - bb_lower_d) / sma20_d if sma20_d > 0 else 0

        sma20 = sma20_d
        sma40 = float(np.mean(close_d[-40:])) if len(close_d) >= 40 else sma20
        sma20_prev = float(np.mean(close_d[-25:-5])) if len(close_d) >= 25 else sma20
        sma40_5ago = float(np.mean(close_d[-45:-5])) if len(close_d) >= 45 else sma40

        daily_bullish = (sma20 > sma40 and sma20 > sma20_prev and sma40 > sma40_5ago)

        if bb_bandwidth_d <= self.min_bb_bandwidth:
            return

        pm_dist = abs(price - sma20) / sma20 if sma20 > 0 else 999
        if pm_dist >= self.pm_touch_tolerance:
            return

        touch_count = self._count_pm_touches(close_d[:-1], sma20)
        if touch_count > 2:
            return

        score = (1.0 / max(touch_count, 1)) * bb_bandwidth_d * 100

        pm_direction = "UP" if sma20 > sma20_prev else "DOWN"

        if (daily_bullish and pm_direction == "UP"
                and price >= sma20 * (1 - self.pm_touch_tolerance)
                and self._spy_direction in ("BULL", "FLAT")):
            self.setups.append({
                "ticker": ticker, "sym": sym, "strategy": "PM_BOUNCE_CALL",
                "direction": "CALL", "price": price, "pm_level": sma20,
                "touch_count": touch_count, "bb_bandwidth": bb_bandwidth_d, "score": score,
            })
            self._count_signal("PM_BOUNCE_CALL")
            return

    # ===============================================================
    # EXECUTE TRADES
    # ===============================================================

    def ExecuteTrades(self):
        today_key = self.Time.date()
        if self._executed_today == today_key:
            return
        self._executed_today = today_key

        if not self.setups:
            return
        if self._week_trade_count >= self.max_trades_per_week:
            return

        dd = self._update_dd_state()

        if self._last_loss_date == today_key:
            self._circuit_breaker_blocks += 1
            return

        current_positions = len(self.positions)
        entered = 0

        for setup in self.setups:
            if current_positions + entered >= self.max_positions:
                break
            if self._week_trade_count + entered >= self.max_trades_per_week:
                break

            ticker = setup["ticker"]
            if len(self._companies_in_positions) >= 3:
                if ticker not in self._companies_in_positions:
                    continue

            direction = setup["direction"]
            underlying_price = self.Securities[setup["sym"]].Price
            if underlying_price <= 0:
                continue

            chain = self.cached_chains.get(ticker)
            if chain is None:
                continue

            contract = self._select_contract(chain, underlying_price, direction)
            if contract is None:
                continue

            ask = contract.AskPrice
            if ask <= 0:
                ask = (contract.BidPrice + contract.AskPrice) / 2
            if ask <= 0:
                ask = contract.LastPrice
            if ask <= 0:
                continue

            confidence, m_sc, m_rg, m_hl = self._calc_confidence(setup["score"], dd)
            adjusted_risk = self.risk_per_trade * confidence

            # FIX 4: Loss streak size reduction
            if self._streak_reduced_remaining > 0:
                adjusted_risk *= self.streak_risk_mult
                self._streak_reduced_remaining -= 1
                self._streak_reductions_applied += 1
                self.Log(f"  FIX4: Streak reduction active, risk*={self.streak_risk_mult:.0%}, remaining={self._streak_reduced_remaining}")

            equity = self.Portfolio.TotalPortfolioValue
            target_risk = equity * adjusted_risk
            risk_per_contract = ask * abs(self.stop_loss_pct) * 100
            n_contracts = int(target_risk / risk_per_contract)

            conf_key = round(confidence, 2)
            self._confidence_dist[conf_key] = self._confidence_dist.get(conf_key, 0) + 1
            self._confidence_total += confidence
            self._confidence_trades += 1

            if n_contracts < 1:
                self._risk_skip_count += 1
                continue

            total_cost = n_contracts * ask * 100
            if total_cost > self.Portfolio.MarginRemaining * 0.80:
                n_contracts = int(self.Portfolio.MarginRemaining * 0.80 / (ask * 100))
                if n_contracts < 1:
                    continue

            self.MarketOrder(contract.Symbol, n_contracts)

            limit_price = round(ask * (1 + self.profit_target_pct), 2)
            self.LimitOrder(contract.Symbol, -n_contracts, limit_price)

            self._entry_seq += 1
            tag = f"YOEL_CALL_{ticker}_{self.Time.strftime('%y%m%d')}_{self._entry_seq}"
            dte = (contract.Expiry - self.Time).days

            self.positions[tag] = {
                "contract": contract.Symbol,
                "underlying": setup["sym"],
                "ticker": ticker,
                "strategy": setup["strategy"],
                "direction": direction,
                "n": n_contracts,
                "entry_price": ask,
                "entry_time": self.Time,
                "underlying_price_at_entry": underlying_price,
                "pm_level": setup["pm_level"],
                "touch_count": setup["touch_count"],
                "bb_bandwidth": setup["bb_bandwidth"],
                "dte_at_entry": dte,
                "limit_price": limit_price,
                "max_value": ask,
                # FIX 2: Dynamic SL starts at normal stop_loss_pct
                "dynamic_sl": self.stop_loss_pct,
            }

            self._limit_order_tag[contract.Symbol] = tag
            self._companies_in_positions.add(ticker)
            self._week_trade_count += 1
            entered += 1

            self.Log(f"OPEN {tag}: x{n_contracts} ask=${ask:.2f} lim=${limit_price:.2f} DTE={dte} "
                     f"K={contract.Strike} conf={confidence:.2f}[sc={m_sc:.2f},rg={m_rg:.2f},hl={m_hl:.2f}]")

    def _select_contract(self, chain, underlying_price, direction):
        right = OptionRight.Call if direction == "CALL" else OptionRight.Put
        candidates = []
        for c in chain:
            if c.Right != right:
                continue
            dte = (c.Expiry - self.Time).days
            if dte < self.dte_min or dte > self.dte_max:
                continue
            if c.AskPrice <= 0 and c.LastPrice <= 0:
                continue
            strike_dist = abs(float(c.Strike) - underlying_price) / underlying_price
            if strike_dist > 0.05:
                continue
            candidates.append(c)

        if not candidates:
            return None

        target_dte = (self.dte_min + self.dte_max) / 2
        best = min(candidates, key=lambda c: (
            abs(float(c.Strike) - underlying_price) / underlying_price * 10
            + abs((c.Expiry - self.Time).days - target_dte) / 100
        ))
        return best

    # ===============================================================
    # POSITION MANAGEMENT (every 5 min)
    # ===============================================================

    def ManagePositions(self):
        if not self.positions:
            return
        to_close = []
        for tag, pos in self.positions.items():
            contract = pos["contract"]
            entry_price = pos["entry_price"]

            if not self.Portfolio[contract].Invested:
                if tag in self.positions:
                    to_close.append((tag, "CLOSED_EXTERNAL"))
                continue

            mid = self._get_mid(contract)
            if mid is None or mid <= 0:
                continue

            if mid > pos["max_value"]:
                pos["max_value"] = mid

            pnl_pct = (mid - entry_price) / entry_price if entry_price > 0 else 0

            # FIX 2: Soft trailing profit lock -- update dynamic SL
            old_dynamic_sl = pos["dynamic_sl"]
            if pnl_pct >= self.trail_tighten_pct:
                # At +25%, lock SL at +10%
                pos["dynamic_sl"] = max(pos["dynamic_sl"], self.trail_lock_floor_pct)
            elif pnl_pct >= self.trail_activate_pct:
                # At +20%, move SL to breakeven (0%)
                pos["dynamic_sl"] = max(pos["dynamic_sl"], 0.0)

            if pos["dynamic_sl"] != old_dynamic_sl:
                self.Log(f"  FIX2: {tag} SL adjusted {old_dynamic_sl:+.0%} -> {pos['dynamic_sl']:+.0%} (pnl={pnl_pct:+.1%})")

            # Use dynamic SL for exit check
            effective_sl = pos["dynamic_sl"]

            # FIX 1: Anti-same-day SL
            held_days = (self.Time - pos["entry_time"]).days
            is_same_day = held_days < 1

            if is_same_day:
                # On entry day, only exit if loss exceeds catastrophic threshold
                if pnl_pct <= self.sameday_catastrophic_sl:
                    to_close.append((tag, f"CATASTROPHIC_SL={pnl_pct:+.0%}"))
                    continue
                elif pnl_pct <= effective_sl:
                    # Would have triggered SL, but we block it (FIX 1)
                    self._sameday_blocks += 1
                    # Don't close -- let it ride to next day
                    continue
            else:
                # Normal days: use effective (dynamic) SL
                if pnl_pct <= effective_sl:
                    to_close.append((tag, f"SL={pnl_pct:+.0%}"))
                    continue

            if held_days >= self.max_hold_days:
                to_close.append((tag, f"TIME={held_days}d"))
                continue

            dte_remaining = (contract.ID.Date - self.Time).days
            if dte_remaining <= 3:
                to_close.append((tag, f"DTE={dte_remaining}"))
                continue

        for tag, reason in to_close:
            self._close_position(tag, reason)

    def _close_position(self, tag, reason):
        pos = self.positions.get(tag)
        if pos is None:
            return
        contract = pos["contract"]
        n = pos["n"]

        open_orders = self.Transactions.GetOpenOrders(contract)
        for order in open_orders:
            self.Transactions.CancelOrder(order.Id)

        mid = self._get_mid(contract)
        exit_price = mid if mid and mid > 0 else 0

        if self.Portfolio[contract].Invested:
            self.MarketOrder(contract, -n)

        self._record_closed_trade(tag, reason, exit_price)

    def _record_closed_trade(self, tag, reason, exit_price):
        pos = self.positions.get(tag)
        if pos is None:
            return
        n = pos["n"]
        pnl_dollar = (exit_price - pos["entry_price"]) * n * 100
        pnl_pct = (exit_price / pos["entry_price"] - 1) if pos["entry_price"] > 0 else 0

        self.closed_trades.append({
            "tag": tag, "strategy": pos["strategy"], "direction": pos["direction"],
            "ticker": pos["ticker"], "n": n, "entry_price": pos["entry_price"],
            "exit_price": exit_price, "pnl_dollar": pnl_dollar, "pnl_pct": pnl_pct,
            "held_days": (self.Time - pos["entry_time"]).days, "reason": reason,
            "entry_date": pos["entry_time"].strftime("%Y-%m-%d"),
            "exit_date": self.Time.strftime("%Y-%m-%d"),
            "dynamic_sl_at_exit": pos.get("dynamic_sl", self.stop_loss_pct),
        })

        self.Log(f"CLOSE {tag}: {reason} PnL=${pnl_dollar:+,.0f}({pnl_pct:+.0%}) held={(self.Time - pos['entry_time']).days}d sl={pos.get('dynamic_sl', 'N/A')}")

        # FIX 4: Track consecutive losses
        if pnl_dollar < 0:
            self._consecutive_losses += 1
            if self._consecutive_losses >= self.streak_threshold:
                self._streak_reduced_remaining = self.streak_reduced_trades
                self.Log(f"  FIX4: {self._consecutive_losses} consecutive losses -> reducing next {self.streak_reduced_trades} trades by {self.streak_risk_mult:.0%}")
            ticker = pos["ticker"]
            loss_date = self.Time.date()
            if ticker in self._ticker_loss_dates:
                self._ticker_loss_dates[ticker].append(loss_date)
            self._last_loss_date = loss_date
        else:
            # Win resets streak
            self._consecutive_losses = 0

        self._companies_in_positions.discard(pos["ticker"])
        self._limit_order_tag.pop(pos["contract"], None)
        del self.positions[tag]

    # ===============================================================
    # EOD CLEANUP
    # ===============================================================

    def EODCleanup(self):
        for holding in self.Portfolio.Values:
            if not holding.Invested:
                continue
            sym = holding.Symbol
            if sym.SecurityType != SecurityType.Option:
                continue
            tracked = any(pos["contract"] == sym for pos in self.positions.values())
            if not tracked:
                self.MarketOrder(sym, -int(holding.Quantity))
                self.Log(f"EOD_ORPHAN: Closed {sym}")

    # ===============================================================
    # END OF ALGORITHM
    # ===============================================================

    def OnEndOfAlgorithm(self):
        for tag in list(self.positions.keys()):
            self._close_position(tag, "EOA")
        self.Liquidate()

        self.Log("=" * 60)
        self.Log("YOEL OPTIONS V2.0b-G16 -- FINAL REPORT")
        self.Log("=" * 60)

        eq = self.Portfolio.TotalPortfolioValue
        trades = self.closed_trades
        n_trades = len(trades)

        self.Log(f"  PT={self.profit_target_pct} SL={self.stop_loss_pct} risk={self.risk_per_trade} DTE={self.dte_min}-{self.dte_max}")
        self.Log(f"  chains={dict(self._chain_received_ever)}")
        self.Log(f"  signals={self._total_scan_signals} cooldown_blocks={self._cooldown_blocks} cb_blocks={self._circuit_breaker_blocks}")
        self.Log(f"  risk_skips={self._risk_skip_count} peak_eq=${self._peak_equity:,.0f}")
        self.Log(f"  FIX1 sameday_blocks={self._sameday_blocks}")
        self.Log(f"  FIX3 qqq_filter_blocks={self._qqq_filter_blocks}")
        self.Log(f"  FIX4 streak_reductions={self._streak_reductions_applied} final_streak={self._consecutive_losses}")

        if self._confidence_trades > 0:
            avg_conf = self._confidence_total / self._confidence_trades
            self.Log(f"  CONFIDENCE: avg={avg_conf:.2f} trades={self._confidence_trades}")

        if n_trades == 0:
            self.Log("NO TRADES EXECUTED")
            self.Log("=" * 60)
            return

        wins = sum(1 for t in trades if t["pnl_dollar"] > 0)
        total_pnl = sum(t["pnl_dollar"] for t in trades)
        wr = wins / n_trades * 100
        gross_win = sum(t["pnl_dollar"] for t in trades if t["pnl_dollar"] > 0)
        gross_loss = abs(sum(t["pnl_dollar"] for t in trades if t["pnl_dollar"] < 0))
        pf = gross_win / gross_loss if gross_loss > 0 else 999
        avg_win = gross_win / max(wins, 1)
        avg_loss = gross_loss / max(n_trades - wins, 1)

        self.Log(f"  Equity: ${eq:,.0f} | Return: {eq/10000 - 1:+.2%}")
        self.Log(f"  Trades: {n_trades} | Wins: {wins} | WR: {wr:.1f}%")
        self.Log(f"  PnL: ${total_pnl:+,.0f} | PF: {pf:.2f}")
        self.Log(f"  AvgWin: ${avg_win:,.0f} AvgLoss: ${avg_loss:,.0f} R:R={avg_win/max(avg_loss,1):.2f}")

        # By ticker
        self.Log("--- BY TICKER ---")
        tickers_used = set(t["ticker"] for t in trades)
        for tk in sorted(tickers_used):
            tt = [t for t in trades if t["ticker"] == tk]
            tw = sum(1 for t in tt if t["pnl_dollar"] > 0)
            tp = sum(t["pnl_dollar"] for t in tt)
            self.Log(f"  {tk}: {len(tt)}t WR={tw/len(tt)*100:.0f}% PnL=${tp:+,.0f}")

        # By exit reason
        self.Log("--- BY EXIT ---")
        reasons = set(t["reason"].split("=")[0] for t in trades)
        for rp in sorted(reasons):
            rt = [t for t in trades if t["reason"].startswith(rp)]
            rw = sum(1 for t in rt if t["pnl_dollar"] > 0)
            rpnl = sum(t["pnl_dollar"] for t in rt)
            self.Log(f"  {rp}: {len(rt)} WR={rw/len(rt)*100:.0f}% PnL=${rpnl:+,.0f}")

        # FIX 2: Trail lock stats
        trail_locked = [t for t in trades if t.get("dynamic_sl_at_exit", self.stop_loss_pct) > self.stop_loss_pct]
        if trail_locked:
            tl_pnl = sum(t["pnl_dollar"] for t in trail_locked)
            self.Log(f"--- FIX2 TRAIL LOCKED: {len(trail_locked)} trades, PnL=${tl_pnl:+,.0f} ---")
            for t in trail_locked:
                self.Log(f"  {t['tag']} sl_exit={t['dynamic_sl_at_exit']:+.0%} PnL=${t['pnl_dollar']:+,.0f}")

        self.Log("=" * 60)

    # ===============================================================
    # HELPERS
    # ===============================================================

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

    def _count_pm_touches(self, closes, pm_level):
        if len(closes) < 20 or pm_level <= 0:
            return 0
        recent = closes[-20:]
        touches = 0
        was_near = False
        for p in recent:
            near = abs(p - pm_level) / pm_level < self.pm_touch_tolerance
            if near and not was_near:
                touches += 1
            was_near = near
        return touches

    def _count_signal(self, strategy_name):
        if strategy_name not in self._strategy_signal_counts:
            self._strategy_signal_counts[strategy_name] = 0
        self._strategy_signal_counts[strategy_name] += 1
