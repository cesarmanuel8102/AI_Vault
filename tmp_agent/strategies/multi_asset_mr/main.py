# region imports
from AlgorithmImports import *
from datetime import datetime, timedelta
import numpy as np
# endregion


class MultiAssetMeanReversion(QCAlgorithm):
    """
    Brain V9 — Multi-Asset Mean Reversion V1.0

    POST-CEILING PIVOT: Applying Vol-Regime MR to commodities + bonds + FX
    crosses where mean-reversion is structurally stronger than in FX majors.

    HYPOTHESIS: Commodities (XAUUSD, XAGUSD, WTICOUSD), bond CFDs, and
    commodity-currency crosses exhibit stronger mean-reversion when in
    low-volatility regimes. Z-score deviations from a rolling mean,
    filtered by ADX (range-bound) and RSI confirmation, should revert
    with positive expectancy.

    FAMILY: Multi-Asset Portfolio (Contract §4, Priority 1 post-ceiling)
    MODE: A (Discovery)

    UNIVERSE (Oanda CFDs confirmed available):
    - Commodities: XAUUSD, XAGUSD, WTICOUSD, NATGASUSD, CORNUSD, SOYBNUSD
    - FX Commodity Crosses: AUDCAD, NZDCAD, AUDNZD (proven MR from CMR)
    - Bonds: USB10YUSD, DE10YBEUR (rate-space MR)

    ENTRY:
    1. Z-score(50 Daily) crosses ±2.0 threshold
    2. ADX(14) Daily < 25 (range-bound regime)
    3. RSI(14) Daily < 30 (long) or > 70 (short) confirmation
    4. No entry on macro blackout days

    EXIT:
    1. Z-score crosses 0 (return to mean) → TP
    2. Hard stop: 2.0x ATR(14) Daily
    3. Time stop: 15 daily bars (~3 weeks)
    4. Regime break: ADX crosses 30 → exit
    5. Friday 16:50 ET flatten

    RISK:
    - 1.0% per trade (fixed fractional)
    - Max 5 concurrent positions
    - Max 3 per category
    - Daily DD < 3%, Weekly DD < 5%
    - DD throttle at 4%

    PARAMETERS: 5 (zscore_entry, lookback, adx_max, hard_stop_atr, risk_per_trade)
    """

    VERSION = "MA-MR-V1.0"

    def Initialize(self):
        start_year = int(self.GetParameter("start_year", 2010))
        end_year = int(self.GetParameter("end_year", 2020))
        end_month = int(self.GetParameter("end_month", 12))
        self.SetStartDate(start_year, 1, 1)
        self.SetEndDate(end_year, end_month, 28)
        self.SetCash(10000)
        self.SetBrokerageModel(BrokerageName.OandaBrokerage, AccountType.Margin)

        # ══════════════════════════════════════════════
        # PARAMETERS (5 max per contract §7)
        # ══════════════════════════════════════════════
        self.zscore_entry = float(self.GetParameter("zscore_entry", 2.0))
        self.lookback = int(self.GetParameter("lookback", 50))
        self.adx_max = int(self.GetParameter("adx_max", 25))
        self.hard_stop_atr = float(self.GetParameter("hard_stop_atr", 2.0))
        self.risk_per_trade = float(self.GetParameter("risk_per_trade", 0.010))

        # Fixed config
        self.zscore_exit = 0.0
        self.rsi_ob = 70
        self.rsi_os = 30
        self.adx_exit_threshold = 30
        self.max_hold_days = 15
        self.risk_reduced = self.risk_per_trade * 0.5
        self.max_positions = 5
        self.max_per_category = 3
        self.max_daily_risk = 0.03
        self.max_weekly_risk = 0.05
        self.dd_threshold = 0.04

        # ══════════════════════════════════════════════
        # ASSET UNIVERSE
        # ══════════════════════════════════════════════
        self.commodity_cfd_tickers = [
            "XAUUSD", "XAGUSD", "WTICOUSD",
            "NATGASUSD", "CORNUSD", "SOYBNUSD"
        ]
        self.fx_cross_tickers = [
            "AUDCAD", "NZDCAD", "AUDNZD"
        ]
        self.bond_tickers = [
            "USB10YUSD", "DE10YBEUR"
        ]

        self.all_tickers = self.commodity_cfd_tickers + self.fx_cross_tickers + self.bond_tickers

        self.category = {}
        for t in self.commodity_cfd_tickers:
            self.category[t] = "COMMODITY"
        for t in self.fx_cross_tickers:
            self.category[t] = "FX_CROSS"
        for t in self.bond_tickers:
            self.category[t] = "BOND"

        self.symbols = {}
        self.pairs_data = {}

        for ticker in self.all_tickers:
            # Add as CFD or Forex depending on type
            if ticker in self.fx_cross_tickers:
                asset = self.AddForex(ticker, Resolution.Hour, Market.Oanda)
            else:
                asset = self.AddCfd(ticker, Resolution.Hour, Market.Oanda)
            asset.SetLeverage(10)
            sym = asset.Symbol
            self.symbols[ticker] = sym

            # Daily consolidator (QuoteBar for both CFD and Forex on Oanda)
            daily_consolidator = QuoteBarConsolidator(timedelta(days=1))
            daily_consolidator.DataConsolidated += self._on_daily_bar
            self.SubscriptionManager.AddConsolidator(sym, daily_consolidator)

            self.pairs_data[ticker] = {
                "adx_d": self.ADX(sym, 14, Resolution.Daily),
                "atr_d": self.ATR(sym, 14, MovingAverageType.Simple, Resolution.Daily),
                "rsi_d": self.RSI(sym, 14, MovingAverageType.Simple, Resolution.Daily),
                "daily_closes": [],
                # Position tracking
                "entry_price": 0.0,
                "entry_direction": 0,
                "entry_date": None,
                "entry_bar_count": 0,
                "hard_stop": 0.0,
                "traded_today": False,
            }

        # Risk tracking
        self.day_start_equity = 10000.0
        self.last_trade_date = None
        self.week_start_equity = 10000.0
        self.equity_history = []
        self.open_position_count = 0

        # Macro blackout
        self.macro_blackout_dates = self._build_macro_calendar()

        # Schedules
        self.Schedule.On(
            self.DateRules.Every(DayOfWeek.Friday),
            self.TimeRules.At(16, 50),
            self._flatten_all
        )
        self.Schedule.On(
            self.DateRules.Every(DayOfWeek.Monday),
            self.TimeRules.At(0, 0),
            self._reset_weekly
        )

        self.SetWarmUp(timedelta(days=100))

        self.Log(f"[MA-MR] {self.VERSION} | Assets: {len(self.all_tickers)}")
        self.Log(f"[MA-MR] Z-score={self.zscore_entry} | LB={self.lookback} | ADX<{self.adx_max}")

    # ═══════════════════════════════════════════════════════════
    def _on_daily_bar(self, sender, bar):
        ticker = str(bar.Symbol.Value)
        if ticker not in self.pairs_data:
            return
        pd = self.pairs_data[ticker]
        pd["daily_closes"].append(float(bar.Close))
        max_hist = self.lookback + 20
        if len(pd["daily_closes"]) > max_hist:
            pd["daily_closes"] = pd["daily_closes"][-max_hist:]

    # ═══════════════════════════════════════════════════════════
    def _calc_zscore(self, closes, lookback):
        """Calculate Z-score of latest close vs rolling mean/std."""
        if len(closes) < lookback:
            return None
        window = closes[-lookback:]
        mean = sum(window) / len(window)
        variance = sum((x - mean) ** 2 for x in window) / len(window)
        std = variance ** 0.5
        if std <= 0:
            return None
        return (closes[-1] - mean) / std

    # ═══════════════════════════════════════════════════════════
    def OnData(self, data: Slice):
        if self.IsWarmingUp:
            return

        if self.last_trade_date is None or self.Time.date() != self.last_trade_date:
            self.day_start_equity = float(self.Portfolio.TotalPortfolioValue)
            self.last_trade_date = self.Time.date()
            for t in self.all_tickers:
                self.pairs_data[t]["traded_today"] = False
            self.equity_history.append(self.day_start_equity)
            if len(self.equity_history) > 30:
                self.equity_history = self.equity_history[-30:]

        # Manage open positions every hour
        for ticker in self.all_tickers:
            sym = self.symbols[ticker]
            if not data.ContainsKey(sym):
                continue
            if self.Portfolio[sym].Invested:
                self._manage_position(ticker, data)

        # Entry at 12:00 ET only
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
            if self.pairs_data[ticker]["traded_today"]:
                continue
            if not self._pass_risk_gates():
                continue
            if not self._pass_cluster_risk(ticker):
                continue
            self._check_mr_entry(ticker, data)

    # ═══════════════════════════════════════════════════════════
    def _check_mr_entry(self, ticker, data):
        pd = self.pairs_data[ticker]
        sym = self.symbols[ticker]

        if len(pd["daily_closes"]) < self.lookback:
            return

        # ADX must be below threshold (range-bound)
        if not pd["adx_d"].IsReady:
            return
        adx = float(pd["adx_d"].Current.Value)
        if adx > self.adx_max:
            return

        # ATR for stops
        if not pd["atr_d"].IsReady:
            return
        atr_d = float(pd["atr_d"].Current.Value)
        if atr_d <= 0:
            return

        # RSI for confirmation
        if not pd["rsi_d"].IsReady:
            return
        rsi = float(pd["rsi_d"].Current.Value)

        # Z-score
        zscore = self._calc_zscore(pd["daily_closes"], self.lookback)
        if zscore is None:
            return

        bar = data[sym]
        if bar is None:
            return
        price = float(bar.Close) if hasattr(bar, 'Close') else float(bar.Value)
        if price <= 0:
            return

        # Determine direction
        direction = 0
        if zscore <= -self.zscore_entry and rsi < self.rsi_os:
            direction = 1  # Oversold → buy
        elif zscore >= self.zscore_entry and rsi > self.rsi_ob:
            direction = -1  # Overbought → sell

        if direction == 0:
            return

        # Hard stop
        if direction == 1:
            stop_price = price - self.hard_stop_atr * atr_d
        else:
            stop_price = price + self.hard_stop_atr * atr_d

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

        self.Log(f"[ENTRY {side}] {ticker} @ {price:.4f} | "
                 f"Z={zscore:.2f} | RSI={rsi:.1f} | ADX={adx:.1f} | Qty={qty}")

        pd["entry_direction"] = direction
        pd["entry_price"] = price
        pd["entry_date"] = self.Time
        pd["entry_bar_count"] = 0
        pd["hard_stop"] = stop_price
        pd["traded_today"] = True

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

        if self.Time.hour == 12:
            pd["entry_bar_count"] += 1

        # EXIT 1: Hard stop
        if direction == 1 and price_low <= pd["hard_stop"]:
            self.Liquidate(sym)
            self.Log(f"[EXIT STOP L] {ticker} @ {price:.4f}")
            self._reset_pair_state(ticker)
            return
        if direction == -1 and price_high >= pd["hard_stop"]:
            self.Liquidate(sym)
            self.Log(f"[EXIT STOP S] {ticker} @ {price:.4f}")
            self._reset_pair_state(ticker)
            return

        # EXIT 2: Z-score mean reversion (check once per day)
        if self.Time.hour == 12 and len(pd["daily_closes"]) >= self.lookback:
            zscore = self._calc_zscore(pd["daily_closes"], self.lookback)
            if zscore is not None:
                if direction == 1 and zscore >= self.zscore_exit:
                    self.Liquidate(sym)
                    pnl = price - pd["entry_price"]
                    self.Log(f"[EXIT MR L] {ticker} @ {price:.4f} | Z={zscore:.2f} | PnL={pnl:.4f}")
                    self._reset_pair_state(ticker)
                    return
                if direction == -1 and zscore <= self.zscore_exit:
                    self.Liquidate(sym)
                    pnl = pd["entry_price"] - price
                    self.Log(f"[EXIT MR S] {ticker} @ {price:.4f} | Z={zscore:.2f} | PnL={pnl:.4f}")
                    self._reset_pair_state(ticker)
                    return

        # EXIT 3: Regime break (ADX > 30)
        if self.Time.hour == 12 and pd["adx_d"].IsReady:
            adx = float(pd["adx_d"].Current.Value)
            if adx > self.adx_exit_threshold:
                self.Liquidate(sym)
                self.Log(f"[EXIT REGIME] {ticker} @ {price:.4f} | ADX={adx:.1f}")
                self._reset_pair_state(ticker)
                return

        # EXIT 4: Time stop
        if pd["entry_bar_count"] >= self.max_hold_days:
            self.Liquidate(sym)
            self.Log(f"[EXIT TIME] {ticker} @ {price:.4f} | Days={pd['entry_bar_count']}")
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
        risk_amount = equity * risk_pct
        if risk_distance <= 0 or price <= 0:
            return 0
        qty = int(risk_amount / risk_distance)
        if qty < 1:
            return 0
        # For FX crosses, enforce minimum lot size
        if ticker in self.fx_cross_tickers:
            if qty < 1000:
                return 0
            qty = (qty // 1000) * 1000
        # Cap at 2x equity
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

    def _reset_pair_state(self, ticker):
        pd = self.pairs_data[ticker]
        pd["entry_direction"] = 0
        pd["entry_price"] = 0.0
        pd["entry_date"] = None
        pd["entry_bar_count"] = 0
        pd["hard_stop"] = 0.0

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
                     f"{orderEvent.FillPrice:.4f}")

    def OnEndOfAlgorithm(self):
        equity = float(self.Portfolio.TotalPortfolioValue)
        total_return = (equity - 10000) / 10000 * 100
        self.Log(f"[FINAL] {self.VERSION} | Equity=${equity:.2f} | Return={total_return:.2f}%")
