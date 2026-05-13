# region imports
from AlgorithmImports import *
from datetime import datetime, timedelta
import math
# endregion


class LondonBreakoutFX(QCAlgorithm):
    """
    Brain V9 — London Breakout V1.0

    HYPOTHESIS: The London session open (07:00-10:00 GMT / 02:00-05:00 ET) generates
    the highest-probability breakouts in FX majors because:
    1. London is the deepest FX liquidity pool (~43% of global turnover)
    2. Asian session builds a range (consolidation) that London breaks
    3. Volatility contraction (narrow Asian range) precedes expansion (London move)

    MECHANISM:
    - Calculate Asian session range (21:00 ET prev day to 01:30 ET = 02:00-06:30 GMT)
    - At London open (02:30 ET = 07:30 GMT), set breakout levels above/below Asian high/low
    - Breakout trigger: price exceeds Asian high + buffer OR drops below Asian low - buffer
    - Direction filter: Daily EMA(50) — only long above EMA, short below
    - Volatility gate: Asian range must be < X percentile of recent ranges (narrow = good)
    - Exit: Chandelier trailing stop (ATR-based) OR end-of-London session (10:00 ET = 15:00 GMT)
    - Risk: fixed fractional, 2% per trade

    PAIRS: EURUSD, GBPUSD, USDJPY, EURGBP (most active in London)
    TIMEFRAME: Hourly bars for signal, Daily for trend filter

    RESEARCH BASIS:
    - London breakout is one of the allowed families in the Master Contract
    - MQL5 live signals show London session strategies among the most consistent
    - Quantpedia: session breakout documented as persistent anomaly
    """

    VERSION = "LB-V1.0"

    def Initialize(self):
        # ── Backtest window ──
        start_year = int(self.GetParameter("start_year", 2020))
        end_year = int(self.GetParameter("end_year", 2024))
        end_month = int(self.GetParameter("end_month", 12))
        self.SetStartDate(start_year, 1, 1)
        self.SetEndDate(end_year, end_month, 28)
        self.SetCash(10000)
        self.SetBrokerageModel(BrokerageName.OandaBrokerage, AccountType.Margin)
        self.SetTimeZone("America/New_York")

        # ── Parameters ──
        self.risk_per_trade = float(self.GetParameter("risk_per_trade", 0.02))
        self.max_positions = int(self.GetParameter("max_positions", 3))
        self.breakout_buffer_atr = float(self.GetParameter("breakout_buffer_atr", 0.1))  # buffer as fraction of ATR
        self.chandelier_mult = float(self.GetParameter("chandelier_mult", 2.5))  # trailing stop ATR multiplier
        self.ema_period = int(self.GetParameter("ema_period", 50))  # daily EMA for trend filter
        self.atr_period = int(self.GetParameter("atr_period", 14))
        self.range_lookback = int(self.GetParameter("range_lookback", 20))  # days to calculate range percentile
        self.range_pct_max = float(self.GetParameter("range_pct_max", 60))  # max percentile of Asian range (lower = more selective)
        self.session_close_hour = int(self.GetParameter("session_close_hour", 10))  # ET hour to close positions (10 ET = 15 GMT)
        self.max_daily_risk = float(self.GetParameter("max_daily_risk", 0.04))

        # ── Asian session window (ET times) ──
        # Asian session: ~21:00 ET prev day to 01:30 ET (= 02:00-06:30 GMT)
        # We track high/low from 21:00 to 01:30 ET
        self.asian_start_hour = 21  # ET (previous day)
        self.asian_end_hour = 1    # ET (current day), at :30
        # London breakout window: 02:30 - 05:00 ET (07:30 - 10:00 GMT)
        self.london_start_hour = 2  # ET, at :30
        self.london_end_hour = 5    # ET

        # ── Pairs ──
        self.pair_tickers = ["EURUSD", "GBPUSD", "USDJPY", "EURGBP"]
        self.symbols = {}
        self.pairs_data = {}
        self.ema_indicators = {}
        self.atr_indicators = {}

        for ticker in self.pair_tickers:
            # Hourly bars for intraday breakout detection
            forex_h = self.AddForex(ticker, Resolution.Hour, Market.Oanda)
            forex_h.SetLeverage(10)
            sym = forex_h.Symbol
            self.symbols[ticker] = sym

            # EMA on daily for trend filter
            self.ema_indicators[ticker] = self.EMA(sym, self.ema_period, Resolution.Daily)
            # ATR on daily for stop sizing and range comparison
            self.atr_indicators[ticker] = self.ATR(sym, self.atr_period, MovingAverageType.Simple, Resolution.Daily)

            self.pairs_data[ticker] = {
                "asian_high": None,
                "asian_low": None,
                "asian_tracking": False,   # True during Asian session collection
                "asian_range_history": [],  # Recent Asian ranges for percentile calc
                "breakout_ready": False,    # True when Asian range calculated, waiting for breakout
                "breakout_direction": 0,    # +1 long, -1 short, 0 none
                "entry_price": 0.0,
                "stop_price": 0.0,
                "highest_since_entry": 0.0,
                "lowest_since_entry": 999.0,
                "traded_today": False,      # One trade per pair per day
            }

        # ── Daily risk tracking ──
        self.daily_loss = 0.0
        self.last_day = None

        # ── Macro blackout ──
        self.macro_blackout_dates = self._build_macro_calendar()

        # ── Scheduled events ──
        # Start Asian range tracking at 21:00 ET
        self.Schedule.On(
            self.DateRules.EveryDay(),
            self.TimeRules.At(21, 0),
            self._start_asian_tracking
        )

        # Finalize Asian range at 01:30 ET and prepare breakout levels
        self.Schedule.On(
            self.DateRules.EveryDay(),
            self.TimeRules.At(1, 30),
            self._finalize_asian_range
        )

        # Session close — CONFIGURABLE: set session_close_hour to 0 to disable
        if self.session_close_hour > 0:
            self.Schedule.On(
                self.DateRules.EveryDay(),
                self.TimeRules.At(self.session_close_hour, 0),
                self._session_close
            )

        # Friday early close at 16:50 ET (before forex market closes)
        self.Schedule.On(
            self.DateRules.Every(DayOfWeek.Friday),
            self.TimeRules.At(16, 50),
            self._friday_flatten
        )

        # Daily reset
        self.Schedule.On(
            self.DateRules.EveryDay(),
            self.TimeRules.At(16, 55),
            self._eod_log
        )

        # ── Warmup ──
        self.SetWarmUp(timedelta(days=70))

        self.Log(f"[LB] {self.VERSION} | Pairs: {self.pair_tickers}")
        self.Log(f"[LB] Risk: {self.risk_per_trade*100}% per trade | Chandelier: {self.chandelier_mult}x ATR")
        self.Log(f"[LB] Range filter: Asian range < {self.range_pct_max}th percentile")
        self.Log(f"[LB] EMA trend filter: {self.ema_period}d | Session close: {self.session_close_hour}:00 ET")

    # ═══════════════════════════════════════════════════════════
    #  ASIAN RANGE TRACKING
    # ═══════════════════════════════════════════════════════════

    def _start_asian_tracking(self):
        """21:00 ET: Start tracking Asian session high/low."""
        if self.IsWarmingUp:
            return

        for ticker in self.pair_tickers:
            pd = self.pairs_data[ticker]
            pd["asian_high"] = None
            pd["asian_low"] = None
            pd["asian_tracking"] = True
            pd["breakout_ready"] = False
            pd["breakout_direction"] = 0
            pd["traded_today"] = False

    def _finalize_asian_range(self):
        """01:30 ET: Finalize Asian range and prepare breakout levels."""
        if self.IsWarmingUp:
            return

        for ticker in self.pair_tickers:
            pd = self.pairs_data[ticker]
            pd["asian_tracking"] = False

            if pd["asian_high"] is None or pd["asian_low"] is None:
                pd["breakout_ready"] = False
                continue

            asian_range = pd["asian_high"] - pd["asian_low"]
            if asian_range <= 0:
                pd["breakout_ready"] = False
                continue

            # Store range for percentile calculation
            pd["asian_range_history"].append(asian_range)
            if len(pd["asian_range_history"]) > self.range_lookback * 2:
                pd["asian_range_history"] = pd["asian_range_history"][-self.range_lookback * 2:]

            # Check volatility gate: is today's Asian range narrow enough?
            if len(pd["asian_range_history"]) >= self.range_lookback:
                recent_ranges = sorted(pd["asian_range_history"][-self.range_lookback:])
                pct_rank = sum(1 for r in recent_ranges if r <= asian_range) / len(recent_ranges) * 100

                if pct_rank > self.range_pct_max:
                    self.Log(f"[LB SKIP] {ticker} | Asian range {asian_range:.5f} too wide "
                             f"(pct={pct_rank:.0f}% > {self.range_pct_max}%)")
                    pd["breakout_ready"] = False
                    continue
                else:
                    self.Log(f"[LB READY] {ticker} | Asian H={pd['asian_high']:.5f} L={pd['asian_low']:.5f} "
                             f"Range={asian_range:.5f} (pct={pct_rank:.0f}%)")

            pd["breakout_ready"] = True

    # ═══════════════════════════════════════════════════════════
    #  HOURLY DATA — RANGE TRACKING + BREAKOUT DETECTION
    # ═══════════════════════════════════════════════════════════

    def OnData(self, data: Slice):
        if self.IsWarmingUp:
            return

        # Daily risk reset
        current_day = self.Time.date()
        if self.last_day != current_day:
            self.daily_loss = 0.0
            self.last_day = current_day

        # Macro blackout
        if current_day in self.macro_blackout_dates:
            return

        hour = self.Time.hour
        minute = self.Time.minute

        for ticker in self.pair_tickers:
            sym = self.symbols[ticker]
            if not data.ContainsKey(sym):
                continue
            bar = data[sym]
            if bar is None:
                continue

            price = float(bar.Close) if hasattr(bar, 'Close') else float(bar.Value)
            high = float(bar.High) if hasattr(bar, 'High') else price
            low = float(bar.Low) if hasattr(bar, 'Low') else price
            pd = self.pairs_data[ticker]

            # ── Track Asian range ──
            if pd["asian_tracking"]:
                if pd["asian_high"] is None or high > pd["asian_high"]:
                    pd["asian_high"] = high
                if pd["asian_low"] is None or low < pd["asian_low"]:
                    pd["asian_low"] = low

            # ── Check for breakout during London window (02:30 - 05:00 ET) ──
            if pd["breakout_ready"] and not pd["traded_today"]:
                if hour >= self.london_start_hour and hour <= self.london_end_hour:
                    self._check_breakout(ticker, price, high, low)

            # ── Update trailing stop for open positions ──
            if self.Portfolio[sym].Invested:
                self._update_trailing_stop(ticker, price, high, low)

    # ═══════════════════════════════════════════════════════════
    #  BREAKOUT DETECTION & ENTRY
    # ═══════════════════════════════════════════════════════════

    def _check_breakout(self, ticker, price, high, low):
        """Check if price breaks above Asian high or below Asian low."""
        pd = self.pairs_data[ticker]
        sym = self.symbols[ticker]

        if self.Portfolio[sym].Invested:
            return

        # Daily risk check
        equity = float(self.Portfolio.TotalPortfolioValue)
        if self.daily_loss >= equity * self.max_daily_risk:
            return

        # Count current positions
        open_count = sum(1 for t in self.pair_tickers if self.Portfolio[self.symbols[t]].Invested)
        if open_count >= self.max_positions:
            return

        # Get ATR for stop sizing and buffer
        atr = self.atr_indicators[ticker]
        if atr is None or not atr.IsReady:
            return
        atr_val = float(atr.Current.Value)
        if atr_val <= 0:
            return

        # Get EMA for trend filter
        ema = self.ema_indicators[ticker]
        if ema is None or not ema.IsReady:
            return
        ema_val = float(ema.Current.Value)

        asian_high = pd["asian_high"]
        asian_low = pd["asian_low"]
        buffer = atr_val * self.breakout_buffer_atr

        # ── Long breakout ──
        if high > asian_high + buffer and price > ema_val:
            # Price broke above Asian high AND is above daily EMA (uptrend)
            stop_distance = atr_val * self.chandelier_mult
            entry_price = asian_high + buffer  # Approximate entry at breakout level
            stop_price = entry_price - stop_distance

            qty = self._calc_position_size(equity, entry_price, stop_price, ticker)
            if qty >= 1000:
                if self.Securities[sym].Exchange.ExchangeOpen:
                    self.MarketOrder(sym, qty)
                    pd["entry_price"] = entry_price
                    pd["stop_price"] = stop_price
                    pd["highest_since_entry"] = high
                    pd["breakout_direction"] = 1
                    pd["traded_today"] = True
                    pd["breakout_ready"] = False
                    self.Log(f"[LB LONG] {ticker} | Entry~{entry_price:.5f} | "
                             f"AH={asian_high:.5f} | EMA={ema_val:.5f} | "
                             f"Stop={stop_price:.5f} | Qty={qty} | ATR={atr_val:.5f}")

        # ── Short breakout ──
        elif low < asian_low - buffer and price < ema_val:
            # Price broke below Asian low AND is below daily EMA (downtrend)
            stop_distance = atr_val * self.chandelier_mult
            entry_price = asian_low - buffer
            stop_price = entry_price + stop_distance

            qty = self._calc_position_size(equity, entry_price, stop_price, ticker)
            if qty >= 1000:
                if self.Securities[sym].Exchange.ExchangeOpen:
                    self.MarketOrder(sym, -qty)
                    pd["entry_price"] = entry_price
                    pd["stop_price"] = stop_price
                    pd["lowest_since_entry"] = low
                    pd["breakout_direction"] = -1
                    pd["traded_today"] = True
                    pd["breakout_ready"] = False
                    self.Log(f"[LB SHORT] {ticker} | Entry~{entry_price:.5f} | "
                             f"AL={asian_low:.5f} | EMA={ema_val:.5f} | "
                             f"Stop={stop_price:.5f} | Qty={qty} | ATR={atr_val:.5f}")

    # ═══════════════════════════════════════════════════════════
    #  POSITION SIZING
    # ═══════════════════════════════════════════════════════════

    def _calc_position_size(self, equity, entry_price, stop_price, ticker):
        """Calculate position size based on risk per trade and stop distance."""
        risk_amount = equity * self.risk_per_trade
        stop_distance = abs(entry_price - stop_price)

        if stop_distance <= 0 or entry_price <= 0:
            return 0

        # For JPY pairs, pip value is different
        if "JPY" in ticker:
            # USDJPY: 1 pip = 0.01, value per lot varies
            qty = risk_amount / stop_distance
        else:
            # Standard pairs: stop distance is in price units
            qty = risk_amount / stop_distance

        qty = int(qty)
        qty = (qty // 1000) * 1000  # Round to lots
        return qty

    # ═══════════════════════════════════════════════════════════
    #  TRAILING STOP (CHANDELIER EXIT)
    # ═══════════════════════════════════════════════════════════

    def _update_trailing_stop(self, ticker, price, high, low):
        """Update chandelier trailing stop."""
        pd = self.pairs_data[ticker]
        sym = self.symbols[ticker]

        atr = self.atr_indicators[ticker]
        if atr is None or not atr.IsReady:
            return
        atr_val = float(atr.Current.Value)

        if pd["breakout_direction"] == 1:
            # Long position — trail stop below highest high
            if high > pd["highest_since_entry"]:
                pd["highest_since_entry"] = high
            new_stop = pd["highest_since_entry"] - atr_val * self.chandelier_mult
            if new_stop > pd["stop_price"]:
                pd["stop_price"] = new_stop

            # Check if stopped out
            if low <= pd["stop_price"]:
                if self.Securities[sym].Exchange.ExchangeOpen:
                    pnl = float(self.Portfolio[sym].UnrealizedProfit)
                    self.Liquidate(sym)
                    if pnl < 0:
                        self.daily_loss += abs(pnl)
                    self.Log(f"[LB STOP LONG] {ticker} | Stop={pd['stop_price']:.5f} | "
                             f"PnL=${pnl:.2f} | HH={pd['highest_since_entry']:.5f}")
                    pd["breakout_direction"] = 0

        elif pd["breakout_direction"] == -1:
            # Short position — trail stop above lowest low
            if low < pd["lowest_since_entry"]:
                pd["lowest_since_entry"] = low
            new_stop = pd["lowest_since_entry"] + atr_val * self.chandelier_mult
            if new_stop < pd["stop_price"]:
                pd["stop_price"] = new_stop

            # Check if stopped out
            if high >= pd["stop_price"]:
                if self.Securities[sym].Exchange.ExchangeOpen:
                    pnl = float(self.Portfolio[sym].UnrealizedProfit)
                    self.Liquidate(sym)
                    if pnl < 0:
                        self.daily_loss += abs(pnl)
                    self.Log(f"[LB STOP SHORT] {ticker} | Stop={pd['stop_price']:.5f} | "
                             f"PnL=${pnl:.2f} | LL={pd['lowest_since_entry']:.5f}")
                    pd["breakout_direction"] = 0

    # ═══════════════════════════════════════════════════════════
    #  SESSION CLOSE
    # ═══════════════════════════════════════════════════════════

    def _session_close(self):
        """Close all positions at end of London/NY overlap session."""
        if self.IsWarmingUp:
            return

        for ticker in self.pair_tickers:
            sym = self.symbols[ticker]
            if self.Portfolio[sym].Invested:
                if self.Securities[sym].Exchange.ExchangeOpen:
                    pnl = float(self.Portfolio[sym].UnrealizedProfit)
                    self.Liquidate(sym)
                    if pnl < 0:
                        self.daily_loss += abs(pnl)
                    self.Log(f"[LB SESSION CLOSE] {ticker} | PnL=${pnl:.2f}")
                    self.pairs_data[ticker]["breakout_direction"] = 0

    def _friday_flatten(self):
        """Flatten all positions before weekend (16:50 ET Friday)."""
        if self.IsWarmingUp:
            return

        for ticker in self.pair_tickers:
            sym = self.symbols[ticker]
            if self.Portfolio[sym].Invested:
                if self.Securities[sym].Exchange.ExchangeOpen:
                    pnl = float(self.Portfolio[sym].UnrealizedProfit)
                    self.Liquidate(sym)
                    self.Log(f"[LB FRIDAY FLAT] {ticker} | PnL=${pnl:.2f}")
                    self.pairs_data[ticker]["breakout_direction"] = 0

    # ═══════════════════════════════════════════════════════════
    #  LOGGING
    # ═══════════════════════════════════════════════════════════

    def _eod_log(self):
        """16:55 ET daily summary."""
        equity = float(self.Portfolio.TotalPortfolioValue)
        positions = []
        for ticker in self.pair_tickers:
            sym = self.symbols[ticker]
            if self.Portfolio[sym].Invested:
                h = self.Portfolio[sym]
                pnl = float(h.UnrealizedProfit)
                positions.append(f"{ticker}={'L' if h.IsLong else 'S'}(${pnl:.0f})")
        pos_str = ", ".join(positions) if positions else "FLAT"
        self.Log(f"[EOD] Equity=${equity:.2f} | DayLoss=${self.daily_loss:.2f} | {pos_str}")

    # ═══════════════════════════════════════════════════════════
    #  MACRO CALENDAR
    # ═══════════════════════════════════════════════════════════

    def _build_macro_calendar(self):
        """FOMC + NFP dates 2020-2024."""
        dates = set()
        fomc = [
            "2020-01-29", "2020-03-03", "2020-03-15", "2020-04-29", "2020-06-10",
            "2020-07-29", "2020-09-16", "2020-11-05", "2020-12-16",
            "2021-01-27", "2021-03-17", "2021-04-28", "2021-06-16",
            "2021-07-28", "2021-09-22", "2021-11-03", "2021-12-15",
            "2022-01-26", "2022-03-16", "2022-05-04", "2022-06-15",
            "2022-07-27", "2022-09-21", "2022-11-02", "2022-12-14",
            "2023-02-01", "2023-03-22", "2023-05-03", "2023-06-14",
            "2023-07-26", "2023-09-20", "2023-11-01", "2023-12-13",
            "2024-01-31", "2024-03-20", "2024-05-01", "2024-06-12",
            "2024-07-31", "2024-09-18", "2024-11-07", "2024-12-18",
        ]
        nfp = []
        for year in range(2020, 2025):
            for month in range(1, 13):
                d = datetime(year, month, 1)
                days_until_fri = (4 - d.weekday()) % 7
                first_friday = d + timedelta(days=days_until_fri)
                nfp.append(first_friday.strftime("%Y-%m-%d"))
        for d_str in fomc + nfp:
            try:
                dates.add(datetime.strptime(d_str, "%Y-%m-%d").date())
            except ValueError:
                pass
        return dates

    # ═══════════════════════════════════════════════════════════
    #  EVENT HANDLERS
    # ═══════════════════════════════════════════════════════════

    def OnOrderEvent(self, orderEvent):
        if orderEvent.Status == OrderStatus.Filled:
            sym = orderEvent.Symbol
            ticker = str(sym).split(" ")[0] if " " in str(sym) else str(sym)
            self.Log(f"[ORDER] {ticker} | Qty={orderEvent.FillQuantity} @ "
                     f"{orderEvent.FillPrice:.5f} | Fee={orderEvent.OrderFee}")

    def OnEndOfAlgorithm(self):
        equity = float(self.Portfolio.TotalPortfolioValue)
        total_return = (equity - 10000) / 10000 * 100
        self.Log(f"[FINAL] {self.VERSION} | Equity=${equity:.2f} | Return={total_return:.2f}%")
