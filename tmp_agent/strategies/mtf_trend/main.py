"""
MTF Trend Pullback V3.4 — EOD Time Stop
========================================
Change from V3.3:
  - Time stop extended from 3 hours to END OF DAY (3:55 PM)
  - Forensic evidence across V1.0-V3.3 (3000+ trades) shows BB pullback
    edge unfolds over DAYS, not hours. 3h window = ~45% WR, negative EV.
    EOD is the first step; if profitable → V3.5 tests multi-day holds.

All V3.3 fixes retained:
  Fix 1: OnEndOfAlgorithm → Liquidate all
  Fix 2: LONG ONLY
  Fix 3: Entry delayed to 9:35 AM
  Fix 4: MAE hard cut removed
  Fix 5: 30-min losing rule removed
  Fix 6: Orphan position safety net
  Fix 7: Daily symbol lockout

Architecture:
  9:00 AM  — Morning scan: History() snapshot, filter setups, rank top 10
  9:35 AM  — Execute top 1-3 valid LONG setups
  9:36+ AM — Minute-by-minute management: SL + trailing (NO intraday time stop)
  3:55 PM  — EOD scheduled close: liquidate all open positions

Parameters (5 max, unchanged):
  1. risk_per_trade = 0.015
  2. atr_stop_mult = 1.5
  3. trail_atr_mult = 1.5
  4. max_positions = 3
  5. adx_threshold = 25
"""

from AlgorithmImports import *
import numpy as np


class MTFTrendScanner(QCAlgorithm):

    def Initialize(self):
        start_year = int(self.GetParameter("start_year") or 2022)
        end_year = int(self.GetParameter("end_year") or 2024)
        end_month = int(self.GetParameter("end_month") or 12)

        self.SetStartDate(start_year, 1, 1)
        self.SetEndDate(end_year, end_month, 28)
        self.SetCash(100000)
        self.SetBrokerageModel(BrokerageName.InteractiveBrokersBrokerage, AccountType.Margin)

        # Parameters (5 tunable)
        self.risk_per_trade = float(self.GetParameter("risk_per_trade") or 0.015)
        self.atr_stop_mult = float(self.GetParameter("atr_stop_mult") or 1.5)
        self.trail_atr_mult = float(self.GetParameter("trail_atr_mult") or 1.5)
        self.max_positions = int(self.GetParameter("max_positions") or 3)
        self.adx_threshold = float(self.GetParameter("adx_threshold") or 25)

        # Universe: top 50 liquid, monthly rebalance
        self._last_rebalance = None
        self.AddUniverse(self.CoarseSelection)
        self.UniverseSettings.Resolution = Resolution.Minute

        self.active_symbols = set()

        # Daily watchlist (top 10) and their data
        self.watchlist = []
        self._scanned_today = None
        self._executed_today = None

        # FIX 7: Daily lockout — symbols that already traded today cannot re-enter
        self._traded_today = set()
        self._traded_today_date = None

        # Trade management
        self.trades = {}

        # Schedule
        self.Schedule.On(self.DateRules.EveryDay(),
                         self.TimeRules.At(9, 0),
                         self.MorningScan)

        # FIX 3: Delay entry to 9:35 AM (was 9:30)
        self.Schedule.On(self.DateRules.EveryDay(),
                         self.TimeRules.At(9, 35),
                         self.ExecuteAtOpen)

        # V3.4: EOD close at 3:55 PM (replaces 3h time stop)
        self.Schedule.On(self.DateRules.EveryDay(),
                         self.TimeRules.At(15, 55),
                         self.CloseAllPositionsEOD)

    # ===================== FIX 1: CLEAN EXIT =====================

    def OnEndOfAlgorithm(self):
        """Liquidate all positions at backtest end for clean measurement."""
        self.Liquidate()

    # ===================== V3.4: EOD CLOSE (3:55 PM) =====================

    def CloseAllPositionsEOD(self):
        """Close all open positions at end of day (3:55 PM).
        Replaces the 3h time stop from V3.3. Gives trades the full
        trading session to play out the BB pullback edge."""
        for sym in list(self.trades.keys()):
            if self.Portfolio[sym].Invested:
                self.Liquidate(sym, "EOD Close 3:55PM")
            self.trades.pop(sym, None)

        # Safety: liquidate any invested position not in self.trades
        for sym in list(self.active_symbols):
            if self.Portfolio[sym].Invested:
                self.Liquidate(sym, "EOD Orphan Close")

    # ===================== UNIVERSE =====================

    def CoarseSelection(self, coarse):
        month_key = (self.Time.year, self.Time.month)
        if self._last_rebalance == month_key:
            return Universe.Unchanged
        self._last_rebalance = month_key

        filtered = [x for x in coarse
                    if x.Price > 10
                    and x.DollarVolume > 20_000_000
                    and x.HasFundamentalData]

        by_volume = sorted(filtered, key=lambda x: x.DollarVolume, reverse=True)
        return [x.Symbol for x in by_volume[:50]]

    def OnSecuritiesChanged(self, changes):
        for sec in changes.RemovedSecurities:
            sym = sec.Symbol
            if self.Portfolio[sym].Invested:
                self.Liquidate(sym, "Universe Removed")
            self.trades.pop(sym, None)
            self.active_symbols.discard(sym)
        for sec in changes.AddedSecurities:
            self.active_symbols.add(sec.Symbol)

    # ===================== MORNING SCAN (9:00 AM) =====================

    def MorningScan(self):
        """Pre-market scan: snapshot de cierre de ayer, calcula indicadores, top 10."""
        today_key = self.Time.date()
        if self._scanned_today == today_key:
            return
        self._scanned_today = today_key
        self.watchlist = []

        # FIX 7: Reset daily lockout
        if self._traded_today_date != today_key:
            self._traded_today = set()
            self._traded_today_date = today_key

        symbols = list(self.active_symbols)
        if not symbols:
            return

        try:
            history = self.History(symbols, 100, Resolution.Daily)
        except Exception:
            return

        if history.empty:
            return

        candidates = []

        for sym in symbols:
            try:
                if sym not in history.index.get_level_values(0):
                    continue
                df = history.loc[sym]
                if len(df) < 60:
                    continue

                close = df["close"].values
                high = df["high"].values
                low = df["low"].values

                price = close[-1]  # cierre de ayer
                if price <= 0:
                    continue

                # Real volatility = std of log returns
                log_returns = np.diff(np.log(close[-21:]))
                realized_vol = float(np.std(log_returns)) if len(log_returns) > 5 else 0
                if realized_vol <= 0:
                    continue

                # Bollinger Bands (20, 2)
                sma20 = float(np.mean(close[-20:]))
                std20 = float(np.std(close[-20:]))
                bb_upper = sma20 + 2.0 * std20
                bb_lower = sma20 - 2.0 * std20

                # EMAs
                ema50 = self._ema(close, 50)
                ema20 = self._ema(close, 20)

                # RSI, ATR, ADX
                rsi = self._rsi(close, 14)
                atr = self._atr(high, low, close, 14)
                adx = self._adx_wilder(high, low, close, 14)
                atr_pct = atr / price

                direction = 0
                score = 0
                setup_type = ""

                # FIX 2: LONG ONLY — shorts removed entirely

                # STRATEGY 7: LONG pullback in uptrend (price near BB middle/lower)
                if (price > ema50 and ema20 > ema50 and adx > self.adx_threshold
                        and price < sma20 and price > bb_lower
                        and 35 < rsi < 55):
                    direction = 1
                    score = realized_vol * adx
                    setup_type = "pullback_long"

                # STRATEGY 5: Gap BELOW BB lower in uptrend (mean reversion long)
                elif (price > ema50 and ema20 > ema50 and adx > self.adx_threshold
                      and price <= bb_lower
                      and rsi < 35):
                    direction = 1
                    score = realized_vol * adx * 0.8
                    setup_type = "gap_bb_long"

                if direction != 0:
                    candidates.append((sym, direction, atr_pct, score, price,
                                       sma20, std20, bb_upper, bb_lower, setup_type))

            except Exception:
                continue

        # Top 10 by score
        candidates.sort(key=lambda x: x[3], reverse=True)
        self.watchlist = candidates[:10]

    # ===================== EXECUTE AT 9:35 AM =====================

    def ExecuteAtOpen(self):
        """Recorre top 10, revalida zona BB, ejecuta 1-3 valid LONG setups."""
        today_key = self.Time.date()
        if self._executed_today == today_key:
            return
        self._executed_today = today_key

        if not self.watchlist:
            return

        entered = 0

        for item in self.watchlist:
            sym, direction, atr_pct, score, prev_close, sma20, std20, bb_upper, bb_lower, setup_type = item

            if entered >= self.max_positions:
                break

            # FIX 7: Skip if already traded this symbol today
            if sym in self._traded_today:
                continue

            # Skip if already in a position on this symbol
            if sym in self.trades or self.Portfolio[sym].Invested:
                continue

            # Get current price (now at 9:35, not 9:30)
            security = self.Securities.get(sym)
            if security is None or security.Price <= 0:
                continue

            open_price = security.Price

            # Validate: gap > 2% AGAINST direction = skip
            gap_pct = (open_price - prev_close) / prev_close if prev_close > 0 else 0

            if gap_pct < -0.02:
                continue  # gapped down >2% against long

            # Revalidate BB zone with current price
            if setup_type == "pullback_long":
                if not (bb_lower <= open_price <= sma20 * 1.005):
                    continue
            elif setup_type == "gap_bb_long":
                if open_price > bb_lower * 1.01:
                    continue

            # Position sizing uses ATR%
            if atr_pct <= 0:
                continue
            stop_distance_pct = self.atr_stop_mult * atr_pct
            stop_distance_dollars = stop_distance_pct * open_price
            equity = self.Portfolio.TotalPortfolioValue
            risk_dollars = equity * self.risk_per_trade
            shares = int(risk_dollars / stop_distance_dollars)
            if shares <= 0:
                continue

            # Cap at 20% equity
            max_shares = int(0.20 * equity / open_price)
            shares = min(shares, max_shares)
            if shares <= 0:
                continue

            # Execute LONG only
            self.MarketOrder(sym, shares)
            stop_loss = open_price * (1 - stop_distance_pct)

            self.trades[sym] = {
                "entry_price": open_price,
                "stop_loss": stop_loss,
                "direction": 1,
                "entry_time": self.Time,
                "highest": open_price,
                "lowest": open_price,
                "atr_pct": atr_pct,
                "setup_type": setup_type,
            }

            # FIX 7: Mark symbol as traded today
            self._traded_today.add(sym)
            entered += 1

    # ===================== POSITION MANAGEMENT (every minute) =====================

    def OnData(self, data):
        # FIX 6: Safety net — detect orphan positions (invested but not tracked)
        for sym in list(self.active_symbols):
            if self.Portfolio[sym].Invested and sym not in self.trades:
                self.Liquidate(sym, "Orphan Liquidation")

        for sym in list(self.trades.keys()):
            if not self.Portfolio[sym].Invested:
                self.trades.pop(sym, None)
                continue

            if not data.Bars.ContainsKey(sym):
                continue

            bar = data.Bars[sym]
            td = self.trades[sym]
            entry = td["entry_price"]

            # Update extremes
            td["highest"] = max(td["highest"], bar.High)

            # --- HARD STOP LOSS ---
            if bar.Low <= td["stop_loss"]:
                self.Liquidate(sym, "SL Hit")
                self.trades.pop(sym, None)
                continue

            # FIX 4: MAE hard cut REMOVED — SL already handles protection
            # FIX 5: 30-min losing rule REMOVED — was killing recovering trades
            # V3.4: 3h time stop REMOVED — replaced by scheduled EOD close at 3:55 PM

            # --- TRAILING STOP (ATR%) ---
            atr_pct = td["atr_pct"]
            trail_dist_pct = self.trail_atr_mult * atr_pct
            new_stop = td["highest"] * (1 - trail_dist_pct)
            if new_stop > td["stop_loss"]:
                td["stop_loss"] = new_stop

    # ===================== INDICATOR HELPERS (stateless) =====================

    @staticmethod
    def _ema(data, period):
        if len(data) < period:
            return data[-1]
        k = 2 / (period + 1)
        ema = float(np.mean(data[:period]))
        for val in data[period:]:
            ema = float(val) * k + ema * (1 - k)
        return ema

    @staticmethod
    def _rsi(close, period=14):
        if len(close) < period + 1:
            return 50
        deltas = np.diff(close[-(period + 1):])
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        avg_gain = float(np.mean(gains))
        avg_loss = float(np.mean(losses))
        if avg_loss == 0:
            return 100
        rs = avg_gain / avg_loss
        return 100 - 100 / (1 + rs)

    @staticmethod
    def _atr(high, low, close, period=14):
        if len(high) < period + 1:
            return float(high[-1] - low[-1])
        trs = []
        for i in range(1, len(high)):
            tr = max(float(high[i] - low[i]),
                     abs(float(high[i] - close[i - 1])),
                     abs(float(low[i] - close[i - 1])))
            trs.append(tr)
        return float(np.mean(trs[-period:]))

    @staticmethod
    def _adx_wilder(high, low, close, period=14):
        """ADX with proper Wilder smoothing."""
        n = len(high)
        if n < period * 2:
            return 0

        plus_dm = np.zeros(n - 1)
        minus_dm = np.zeros(n - 1)
        tr_arr = np.zeros(n - 1)

        for i in range(1, n):
            idx = i - 1
            up = float(high[i] - high[i - 1])
            down = float(low[i - 1] - low[i])
            plus_dm[idx] = up if (up > down and up > 0) else 0
            minus_dm[idx] = down if (down > up and down > 0) else 0
            tr_arr[idx] = max(float(high[i] - low[i]),
                              abs(float(high[i] - close[i - 1])),
                              abs(float(low[i] - close[i - 1])))

        if len(tr_arr) < period:
            return 0

        smoothed_tr = float(np.sum(tr_arr[:period]))
        smoothed_plus = float(np.sum(plus_dm[:period]))
        smoothed_minus = float(np.sum(minus_dm[:period]))

        dx_values = []

        for i in range(period, len(tr_arr)):
            smoothed_tr = smoothed_tr - (smoothed_tr / period) + tr_arr[i]
            smoothed_plus = smoothed_plus - (smoothed_plus / period) + plus_dm[i]
            smoothed_minus = smoothed_minus - (smoothed_minus / period) + minus_dm[i]

            if smoothed_tr == 0:
                continue

            plus_di = 100.0 * smoothed_plus / smoothed_tr
            minus_di = 100.0 * smoothed_minus / smoothed_tr
            di_sum = plus_di + minus_di

            if di_sum == 0:
                dx_values.append(0)
            else:
                dx_values.append(100.0 * abs(plus_di - minus_di) / di_sum)

        if len(dx_values) < period:
            return float(np.mean(dx_values)) if dx_values else 0

        adx = float(np.mean(dx_values[:period]))
        for i in range(period, len(dx_values)):
            adx = (adx * (period - 1) + dx_values[i]) / period

        return adx
