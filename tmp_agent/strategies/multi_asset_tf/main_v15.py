# region imports
from AlgorithmImports import *
from datetime import datetime, timedelta
import math
# endregion


class MultiAssetTrendFollowingV15(QCAlgorithm):
    """
    Brain V9 — Multi-Asset Trend Following V1.5

    BASE: V1.2 (best QC Sharpe 0.462, CAGR 6.31%, Return/DD 0.47)

    V1.2 → V1.5 CHANGES:
    - DONCHIAN 35 (from 30): Slightly slower signal to reduce false breakouts
      while keeping faster than V1.1's 40.
    - VOL SCALAR MAX 2.0 (from 2.5): Moderate vol targeting, avoid oversizing
      low-vol assets that caused capacity issues.
    - REMOVED SUGARUSD: Lowest capacity asset in V1.2 ($0). Keep WHEATUSD/XCUUSD.
    - MAX POSITIONS 8 (from 10): More concentrated portfolio = less noise.
    - ADX 20 (from 18): Slightly stricter trend filter.

    GOAL: Push Sharpe from 0.462 past 0.5 (§3.1 gate)

    PARAMETERS: 5 (donchian_period, ema_trend, adx_min, chandelier_mult, risk_per_trade)
    """

    VERSION = "MA-TF-V1.5"

    def Initialize(self):
        start_year = int(self.GetParameter("start_year", 2010))
        end_year = int(self.GetParameter("end_year", 2020))
        end_month = int(self.GetParameter("end_month", 12))
        self.SetStartDate(start_year, 1, 1)
        self.SetEndDate(end_year, end_month, 28)
        self.SetCash(10000)
        self.SetBrokerageModel(BrokerageName.OandaBrokerage, AccountType.Margin)

        # ══════════════════════════════════════════════
        # PARAMETERS
        # ══════════════════════════════════════════════
        self.donchian_period = int(self.GetParameter("donchian_period", 35))
        self.ema_trend = int(self.GetParameter("ema_trend", 200))
        self.adx_min = int(self.GetParameter("adx_min", 20))
        self.chandelier_mult = float(self.GetParameter("chandelier_mult", 2.5))
        self.risk_per_trade = float(self.GetParameter("risk_per_trade", 0.010))

        # ── Fixed config ──
        self.risk_reduced = self.risk_per_trade * 0.5
        self.max_positions = 8
        self.max_per_category = 4
        self.max_hold_bars = 45
        self.max_daily_risk = 0.03
        self.max_weekly_risk = 0.05
        self.dd_threshold = 0.04

        # ── Profit-locking ──
        self.breakeven_mult = 1.5
        self.profit_lock_mult = 3.0
        self.profit_lock_pct = 0.50

        # ── Volatility targeting ──
        self.vol_target = 0.10
        self.vol_lookback = 60
        self.vol_scalar_max = 2.0  # Reduced from V1.2's 2.5

        # ══════════════════════════════════════════════
        # ASSET UNIVERSE
        # Removed SUGARUSD (capacity $0 in V1.2)
        # ══════════════════════════════════════════════
        self.index_tickers = [
            "SPX500USD", "US30USD", "NAS100USD", "DE30EUR",
            "JP225USD", "UK100GBP", "AU200AUD"
        ]
        self.commodity_tickers = [
            "XAUUSD", "XAGUSD", "WTICOUSD", "BCOUSD",
            "NATGASUSD", "CORNUSD", "SOYBNUSD",
            "WHEATUSD", "XCUUSD"  # Kept from V1.2, removed SUGARUSD
        ]
        self.bond_tickers = [
            "USB10YUSD", "DE10YBEUR"
        ]
        self.all_tickers = self.index_tickers + self.commodity_tickers + self.bond_tickers

        self.category = {}
        self.long_only = set()

        for t in self.index_tickers:
            self.category[t] = "INDEX"
            self.long_only.add(t)
        for t in self.commodity_tickers:
            self.category[t] = "COMMODITY"
        for t in self.bond_tickers:
            self.category[t] = "BOND"

        self.symbols = {}
        self.pairs_data = {}

        for ticker in self.all_tickers:
            cfd = self.AddCfd(ticker, Resolution.Hour, Market.Oanda)
            cfd.SetLeverage(10)
            sym = cfd.Symbol
            self.symbols[ticker] = sym

            daily_consolidator = QuoteBarConsolidator(timedelta(days=1))
            daily_consolidator.DataConsolidated += self._on_daily_bar
            self.SubscriptionManager.AddConsolidator(sym, daily_consolidator)

            self.pairs_data[ticker] = {
                "adx_d": self.ADX(sym, 14, Resolution.Daily),
                "atr_d": self.ATR(sym, 14, MovingAverageType.Simple, Resolution.Daily),
                "daily_highs": [],
                "daily_lows": [],
                "daily_closes": [],
                "daily_returns": [],
                "entry_price": 0.0,
                "entry_direction": 0,
                "entry_date": None,
                "entry_bar_count": 0,
                "entry_atr": 0.0,
                "highest_since_entry": 0.0,
                "lowest_since_entry": float('inf'),
                "max_favorable_excursion": 0.0,
                "trailing_stop": 0.0,
                "breakeven_triggered": False,
                "profit_lock_triggered": False,
            }

        self.day_start_equity = 10000.0
        self.last_trade_date = None
        self.week_start_equity = 10000.0
        self.equity_history = []
        self.open_position_count = 0

        self.macro_blackout_dates = self._build_macro_calendar()

        self.Schedule.On(
            self.DateRules.Every(DayOfWeek.Friday),
            self.TimeRules.At(16, 50),
            self._flatten_all
        )
        self.Schedule.On(
            self.DateRules.EveryDay(),
            self.TimeRules.At(16, 55),
            self._eod_log
        )
        self.Schedule.On(
            self.DateRules.Every(DayOfWeek.Monday),
            self.TimeRules.At(0, 0),
            self._reset_weekly
        )

        self.SetWarmUp(timedelta(days=300))

        self.Log(f"[MA-TF] {self.VERSION} | Assets: {len(self.all_tickers)}")
        self.Log(f"[MA-TF] Donchian={self.donchian_period} | EMA={self.ema_trend} | ADX>={self.adx_min}")
        self.Log(f"[MA-TF] Chandelier={self.chandelier_mult}x | Risk={self.risk_per_trade*100}%")
        self.Log(f"[MA-TF] Vol target={self.vol_target}, scalar max={self.vol_scalar_max}")

    # ═══════════════════════════════════════════════════════════
    def _calc_ema(self, closes, period):
        if len(closes) < period:
            return None
        sma = sum(closes[:period]) / period
        mult = 2.0 / (period + 1)
        ema = sma
        for price in closes[period:]:
            ema = (price - ema) * mult + ema
        return ema

    def _calc_annualized_vol(self, ticker):
        pd = self.pairs_data[ticker]
        returns = pd["daily_returns"]
        if len(returns) < 30:
            return None
        recent = returns[-self.vol_lookback:] if len(returns) >= self.vol_lookback else returns
        n = len(recent)
        mean = sum(recent) / n
        variance = sum((r - mean) ** 2 for r in recent) / n
        std = math.sqrt(variance)
        return std * math.sqrt(252)

    # ═══════════════════════════════════════════════════════════
    def _on_daily_bar(self, sender, bar):
        ticker = str(bar.Symbol.Value)
        if ticker not in self.pairs_data:
            return
        pd = self.pairs_data[ticker]
        close = float(bar.Close)
        pd["daily_highs"].append(float(bar.High))
        pd["daily_lows"].append(float(bar.Low))
        pd["daily_closes"].append(close)

        if len(pd["daily_closes"]) >= 2:
            prev_close = pd["daily_closes"][-2]
            if prev_close > 0:
                ret = (close - prev_close) / prev_close
                pd["daily_returns"].append(ret)

        max_hist = max(self.donchian_period + 10, self.ema_trend + 50, self.vol_lookback + 10)
        if len(pd["daily_highs"]) > max_hist:
            pd["daily_highs"] = pd["daily_highs"][-max_hist:]
            pd["daily_lows"] = pd["daily_lows"][-max_hist:]
            pd["daily_closes"] = pd["daily_closes"][-max_hist:]
        if len(pd["daily_returns"]) > max_hist:
            pd["daily_returns"] = pd["daily_returns"][-max_hist:]

    # ═══════════════════════════════════════════════════════════
    def OnData(self, data: Slice):
        if self.IsWarmingUp:
            return

        if self.last_trade_date is None or self.Time.date() != self.last_trade_date:
            self.day_start_equity = float(self.Portfolio.TotalPortfolioValue)
            self.last_trade_date = self.Time.date()
            self.equity_history.append(self.day_start_equity)
            if len(self.equity_history) > 30:
                self.equity_history = self.equity_history[-30:]

        for ticker in self.all_tickers:
            sym = self.symbols[ticker]
            if not data.ContainsKey(sym):
                continue
            if self.Portfolio[sym].Invested:
                self._manage_position(ticker, data)

        if self.Time.hour != 12:
            return
        if self._is_macro_day():
            return

        self.open_position_count = sum(
            1 for t in self.all_tickers
            if self.Portfolio[self.symbols[t]].Invested
        )

        for ticker in self.all_tickers:
            sym = self.symbols[ticker]
            if not data.ContainsKey(sym):
                continue
            if self.Portfolio[sym].Invested:
                continue
            if not self._pass_risk_gates():
                continue
            if not self._pass_cluster_risk(ticker):
                continue
            self._check_tf_entry(ticker, data)

    # ═══════════════════════════════════════════════════════════
    def _check_tf_entry(self, ticker, data):
        pd = self.pairs_data[ticker]
        sym = self.symbols[ticker]

        if len(pd["daily_highs"]) < self.donchian_period + 1:
            return
        if len(pd["daily_closes"]) < self.ema_trend:
            return
        if not pd["adx_d"].IsReady:
            return
        adx = float(pd["adx_d"].Current.Value)
        if adx < self.adx_min:
            return
        if not pd["atr_d"].IsReady:
            return
        atr_d = float(pd["atr_d"].Current.Value)
        if atr_d <= 0:
            return

        bar = data[sym]
        if bar is None:
            return
        price = float(bar.Close) if hasattr(bar, 'Close') else float(bar.Value)
        if price <= 0:
            return

        ema_val = self._calc_ema(pd["daily_closes"], self.ema_trend)
        if ema_val is None:
            return

        lookback_highs = pd["daily_highs"][-(self.donchian_period + 1):-1]
        lookback_lows = pd["daily_lows"][-(self.donchian_period + 1):-1]
        if len(lookback_highs) < self.donchian_period:
            return

        donchian_high = max(lookback_highs)
        donchian_low = min(lookback_lows)

        direction = 0
        if price > ema_val and price > donchian_high:
            direction = 1
        elif price < ema_val and price < donchian_low:
            if ticker in self.long_only:
                return
            direction = -1

        if direction == 0:
            return

        if direction == 1:
            stop_price = price - self.chandelier_mult * atr_d
        else:
            stop_price = price + self.chandelier_mult * atr_d

        risk_distance = abs(price - stop_price)
        if risk_distance <= 0:
            return

        current_risk = self._get_current_risk_pct()
        qty = self._calculate_position_size(ticker, price, risk_distance, current_risk)
        if qty <= 0:
            return

        if not self.Securities[sym].Exchange.ExchangeOpen:
            return

        side = "LONG" if direction == 1 else "SHORT"
        self.MarketOrder(sym, qty if direction == 1 else -qty)

        self.Log(f"[ENTRY {side}] {ticker} @ {price:.2f} | "
                 f"DC H={donchian_high:.2f} L={donchian_low:.2f} | "
                 f"EMA={ema_val:.2f} | ADX={adx:.1f} | Qty={qty}")

        pd["entry_direction"] = direction
        pd["entry_price"] = price
        pd["entry_date"] = self.Time
        pd["entry_bar_count"] = 0
        pd["entry_atr"] = atr_d
        pd["highest_since_entry"] = price
        pd["lowest_since_entry"] = price
        pd["max_favorable_excursion"] = 0.0
        pd["trailing_stop"] = stop_price
        pd["breakeven_triggered"] = False
        pd["profit_lock_triggered"] = False

    # ═══════════════════════════════════════════════════════════
    def _manage_position(self, ticker, data):
        sym = self.symbols[ticker]
        pd = self.pairs_data[ticker]
        if not data.ContainsKey(sym):
            return
        bar = data[sym]
        if bar is None:
            return

        price = float(bar.Close) if hasattr(bar, 'Close') else float(bar.Value)
        price_high = float(bar.High) if hasattr(bar, 'High') else price
        price_low = float(bar.Low) if hasattr(bar, 'Low') else price
        direction = pd["entry_direction"]
        if direction == 0:
            return
        if not self.Securities[sym].Exchange.ExchangeOpen:
            return

        pd["highest_since_entry"] = max(pd["highest_since_entry"], price_high)
        pd["lowest_since_entry"] = min(pd["lowest_since_entry"], price_low)

        if direction == 1:
            mfe = pd["highest_since_entry"] - pd["entry_price"]
        else:
            mfe = pd["entry_price"] - pd["lowest_since_entry"]
        pd["max_favorable_excursion"] = max(pd["max_favorable_excursion"], mfe)

        entry_atr = pd["entry_atr"]
        atr_d = float(pd["atr_d"].Current.Value) if pd["atr_d"].IsReady else entry_atr
        if atr_d <= 0:
            atr_d = entry_atr
        if atr_d <= 0:
            return

        # ── PROFIT LOCKING ──
        current_profit = mfe

        if not pd["breakeven_triggered"] and entry_atr > 0:
            if current_profit >= self.breakeven_mult * entry_atr:
                if direction == 1:
                    new_stop = pd["entry_price"] + entry_atr * 0.1
                    pd["trailing_stop"] = max(pd["trailing_stop"], new_stop)
                else:
                    new_stop = pd["entry_price"] - entry_atr * 0.1
                    pd["trailing_stop"] = min(pd["trailing_stop"], new_stop)
                pd["breakeven_triggered"] = True

        if not pd["profit_lock_triggered"] and entry_atr > 0:
            if current_profit >= self.profit_lock_mult * entry_atr:
                lock_amount = current_profit * self.profit_lock_pct
                if direction == 1:
                    new_stop = pd["entry_price"] + lock_amount
                    pd["trailing_stop"] = max(pd["trailing_stop"], new_stop)
                else:
                    new_stop = pd["entry_price"] - lock_amount
                    pd["trailing_stop"] = min(pd["trailing_stop"], new_stop)
                pd["profit_lock_triggered"] = True

        # ── Chandelier trailing stop ──
        if direction == 1:
            new_stop = pd["highest_since_entry"] - self.chandelier_mult * atr_d
            pd["trailing_stop"] = max(pd["trailing_stop"], new_stop)
        else:
            new_stop = pd["lowest_since_entry"] + self.chandelier_mult * atr_d
            pd["trailing_stop"] = min(pd["trailing_stop"], new_stop)

        if self.Time.hour == 12:
            pd["entry_bar_count"] += 1

        # EXIT 1: Trailing stop
        if direction == 1 and price_low <= pd["trailing_stop"]:
            self.Liquidate(sym)
            pnl = price - pd["entry_price"]
            self.Log(f"[EXIT TRAIL L] {ticker} @ {price:.2f} | PnL={pnl:.2f}")
            self._reset_pair_state(ticker)
            return
        if direction == -1 and price_high >= pd["trailing_stop"]:
            self.Liquidate(sym)
            pnl = pd["entry_price"] - price
            self.Log(f"[EXIT TRAIL S] {ticker} @ {price:.2f} | PnL={pnl:.2f}")
            self._reset_pair_state(ticker)
            return

        # EXIT 2: EMA reversal
        if self.Time.hour == 12 and len(pd["daily_closes"]) >= self.ema_trend:
            ema_val = self._calc_ema(pd["daily_closes"], self.ema_trend)
            if ema_val is not None:
                if direction == 1 and price < ema_val:
                    self.Liquidate(sym)
                    self.Log(f"[EXIT EMA L] {ticker} @ {price:.2f}")
                    self._reset_pair_state(ticker)
                    return
                if direction == -1 and price > ema_val:
                    self.Liquidate(sym)
                    self.Log(f"[EXIT EMA S] {ticker} @ {price:.2f}")
                    self._reset_pair_state(ticker)
                    return

        # EXIT 3: Time stop
        if pd["entry_bar_count"] >= self.max_hold_bars:
            self.Liquidate(sym)
            self.Log(f"[EXIT TIME] {ticker} @ {price:.2f} | Days={pd['entry_bar_count']}")
            self._reset_pair_state(ticker)
            return

    # ═══════════════════════════════════════════════════════════
    def _get_current_risk_pct(self):
        if len(self.equity_history) < 5:
            return self.risk_per_trade
        peak = max(self.equity_history[-20:]) if len(self.equity_history) >= 20 else max(self.equity_history)
        current = float(self.Portfolio.TotalPortfolioValue)
        dd = (peak - current) / peak if peak > 0 else 0
        if dd >= self.dd_threshold:
            return self.risk_reduced
        return self.risk_per_trade

    def _calculate_position_size(self, ticker, price, risk_distance, risk_pct):
        equity = float(self.Portfolio.TotalPortfolioValue)

        ann_vol = self._calc_annualized_vol(ticker)
        if ann_vol is not None and ann_vol > 0:
            vol_scalar = self.vol_target / ann_vol
            vol_scalar = max(0.3, min(vol_scalar, self.vol_scalar_max))
        else:
            vol_scalar = 1.0

        risk_amount = equity * risk_pct * vol_scalar
        if risk_distance <= 0 or price <= 0:
            return 0
        qty = int(risk_amount / risk_distance)
        if qty < 1:
            return 0

        position_value = qty * price
        max_value = equity * 2.0
        if position_value > max_value:
            qty = int(max_value / price)
        return max(qty, 0)

    # ═══════════════════════════════════════════════════════════
    def _pass_risk_gates(self):
        equity = float(self.Portfolio.TotalPortfolioValue)
        if self.open_position_count >= self.max_positions:
            return False
        daily_pnl = equity - self.day_start_equity
        if daily_pnl < -(self.day_start_equity * self.max_daily_risk):
            return False
        weekly_change = equity - self.week_start_equity
        if weekly_change < -(self.week_start_equity * self.max_weekly_risk):
            return False
        return True

    def _pass_cluster_risk(self, ticker):
        cat = self.category.get(ticker, "UNKNOWN")
        count = 0
        for t in self.all_tickers:
            if self.category.get(t) == cat and self.Portfolio[self.symbols[t]].Invested:
                count += 1
        return count < self.max_per_category

    # ═══════════════════════════════════════════════════════════
    def _flatten_all(self):
        for ticker in self.all_tickers:
            sym = self.symbols[ticker]
            if self.Portfolio[sym].Invested:
                if self.Securities[sym].Exchange.ExchangeOpen:
                    self.Liquidate(sym)
                    self._reset_pair_state(ticker)

    def _reset_weekly(self):
        self.week_start_equity = float(self.Portfolio.TotalPortfolioValue)

    def _eod_log(self):
        equity = float(self.Portfolio.TotalPortfolioValue)
        daily_pnl = equity - self.day_start_equity
        if abs(daily_pnl) > 0.01:
            positions = []
            for ticker in self.all_tickers:
                sym = self.symbols[ticker]
                if self.Portfolio[sym].Invested:
                    h = self.Portfolio[sym]
                    positions.append(f"{ticker}={'L' if h.IsLong else 'S'}")
            pos_str = ", ".join(positions) if positions else "FLAT"
            self.Log(f"[EOD] Eq=${equity:.2f} | PnL=${daily_pnl:.2f} | {pos_str}")

    def _reset_pair_state(self, ticker):
        pd = self.pairs_data[ticker]
        pd["entry_direction"] = 0
        pd["entry_price"] = 0.0
        pd["entry_date"] = None
        pd["entry_bar_count"] = 0
        pd["entry_atr"] = 0.0
        pd["highest_since_entry"] = 0.0
        pd["lowest_since_entry"] = float('inf')
        pd["max_favorable_excursion"] = 0.0
        pd["trailing_stop"] = 0.0
        pd["breakeven_triggered"] = False
        pd["profit_lock_triggered"] = False

    # ═══════════════════════════════════════════════════════════
    def _is_macro_day(self):
        return self.Time.date() in self.macro_blackout_dates

    def _build_macro_calendar(self):
        dates = set()
        fomc = [
            "2010-01-27", "2010-03-16", "2010-04-28", "2010-06-23",
            "2010-08-10", "2010-09-21", "2010-11-03", "2010-12-14",
            "2011-01-26", "2011-03-15", "2011-04-27", "2011-06-22",
            "2011-08-09", "2011-09-21", "2011-11-02", "2011-12-13",
            "2012-01-25", "2012-03-13", "2012-04-25", "2012-06-20",
            "2012-08-01", "2012-09-13", "2012-10-24", "2012-12-12",
            "2013-01-30", "2013-03-20", "2013-05-01", "2013-06-19",
            "2013-07-31", "2013-09-18", "2013-10-30", "2013-12-18",
            "2014-01-29", "2014-03-19", "2014-04-30", "2014-06-18",
            "2014-07-30", "2014-09-17", "2014-10-29", "2014-12-17",
            "2015-01-28", "2015-03-18", "2015-04-29", "2015-06-17",
            "2015-07-29", "2015-09-17", "2015-10-28", "2015-12-16",
            "2016-01-27", "2016-03-16", "2016-04-27", "2016-06-15",
            "2016-07-27", "2016-09-21", "2016-11-02", "2016-12-14",
            "2017-02-01", "2017-03-15", "2017-05-03", "2017-06-14",
            "2017-07-26", "2017-09-20", "2017-11-01", "2017-12-13",
            "2018-01-31", "2018-03-21", "2018-05-02", "2018-06-13",
            "2018-08-01", "2018-09-26", "2018-11-08", "2018-12-19",
            "2019-01-30", "2019-03-20", "2019-05-01", "2019-06-19",
            "2019-07-31", "2019-09-18", "2019-10-30", "2019-12-11",
            "2020-01-29", "2020-03-03", "2020-03-15", "2020-04-29", "2020-06-10",
            "2020-07-29", "2020-09-16", "2020-11-05", "2020-12-16",
        ]
        ecb = [
            "2010-01-14", "2010-03-04", "2010-06-10", "2010-09-02", "2010-12-02",
            "2011-01-13", "2011-03-03", "2011-04-07", "2011-06-09", "2011-07-07",
            "2011-09-08", "2011-11-03", "2011-12-08",
            "2012-01-12", "2012-03-08", "2012-06-06", "2012-07-05", "2012-09-06", "2012-12-06",
            "2013-01-10", "2013-05-02", "2013-06-06", "2013-09-05", "2013-11-07",
            "2014-01-09", "2014-03-06", "2014-06-05", "2014-09-04", "2014-12-04",
            "2015-01-22", "2015-03-05", "2015-06-03", "2015-09-03", "2015-12-03",
            "2016-03-10", "2016-06-02", "2016-09-08", "2016-12-08",
            "2017-01-19", "2017-04-27", "2017-06-08", "2017-09-07", "2017-12-14",
            "2018-01-25", "2018-04-26", "2018-06-14", "2018-09-13", "2018-12-13",
            "2019-01-24", "2019-04-10", "2019-06-06", "2019-09-12", "2019-12-12",
            "2020-01-23", "2020-03-12", "2020-04-30", "2020-06-04", "2020-09-10", "2020-12-10",
        ]
        for d_str in fomc + ecb:
            try:
                dates.add(datetime.strptime(d_str, "%Y-%m-%d").date())
            except ValueError:
                pass
        return dates

    # ═══════════════════════════════════════════════════════════
    def OnOrderEvent(self, orderEvent):
        if orderEvent.Status == OrderStatus.Filled:
            ticker = str(orderEvent.Symbol.Value)
            self.Log(f"[ORDER] {ticker} | Qty={orderEvent.FillQuantity} @ "
                     f"{orderEvent.FillPrice:.2f}")

    def OnEndOfAlgorithm(self):
        equity = float(self.Portfolio.TotalPortfolioValue)
        total_return = (equity - 10000) / 10000 * 100
        self.Log(f"[FINAL] {self.VERSION} | Equity=${equity:.2f} | Return={total_return:.2f}%")
