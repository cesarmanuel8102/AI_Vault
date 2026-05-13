# region imports
from AlgorithmImports import *
from datetime import datetime, timedelta
import math
# endregion


class IntradayMomentumSessionOpen(QCAlgorithm):
    """
    Brain V9 — Intraday Momentum / Session Open V1.0

    HYPOTHESIS: The first hour of major trading sessions (London 03:00 ET,
    New York 08:00 ET) establishes a range that, when broken, predicts
    directional momentum for the remainder of the session. This pattern
    exists because institutional order flow concentrates at session opens,
    creating genuine price discovery.

    FAMILY: Intraday Momentum / Session Open (Contract §4, Family #5)

    ENTRY:
    1. Calculate H/L range of first hour after session open
    2. Breakout above high → LONG, breakout below low → SHORT
    3. Breakout must exceed ATR_MULT * ATR(14) to filter noise
    4. Trend filter: price above/below SMA(TREND_PERIOD) on daily for direction confirmation

    EXIT:
    1. Take Profit: TP_RR_RATIO x risk distance
    2. Stop Loss: SL_ATR_MULT x ATR(14) from entry (or opposite side of range)
    3. Session timeout: close all positions 1 hour before session end
    4. Friday 16:50 ET: flatten all

    RISK:
    - 1% per trade, max 4 positions, max 2.5% daily DD
    - DD throttle: reduce to 0.5% if rolling 20-day DD > 5%

    INSTRUMENTS: SPX500USD, NAS100USD, DE30EUR, JP225USD, XAUUSD, WTICOUSD (Oanda CFDs)
    TIMEFRAME: Hourly bars, daily for trend filter
    PARENT: None (new archetype)
    """

    VERSION = "IM-V1.0"

    def Initialize(self):
        # ── Backtest window (parameterized for IS/OOS splits) ──
        start_year = int(self.GetParameter("start_year", 2010))
        end_year = int(self.GetParameter("end_year", 2020))
        end_month = int(self.GetParameter("end_month", 12))
        self.SetStartDate(start_year, 1, 1)
        self.SetEndDate(end_year, end_month, 28)
        self.SetCash(10000)
        self.SetBrokerageModel(BrokerageName.OandaBrokerage, AccountType.Margin)

        # ── Strategy Parameters (max 5 free) ──
        # 1. Breakout filter: minimum breakout size as fraction of ATR
        self.breakout_atr_mult = float(self.GetParameter("breakout_atr_mult", 0.3))
        # 2. Stop loss in ATR multiples
        self.sl_atr_mult = float(self.GetParameter("sl_atr_mult", 1.5))
        # 3. Take profit as risk:reward ratio
        self.tp_rr_ratio = float(self.GetParameter("tp_rr_ratio", 2.0))
        # 4. Trend filter SMA period (daily)
        self.trend_period = int(self.GetParameter("trend_period", 20))
        # 5. Range calculation hours (how many hours after open to define range)
        self.range_hours = int(self.GetParameter("range_hours", 1))

        # ── Fixed parameters (not optimized) ──
        self.risk_per_trade = 0.01  # 1% per trade
        self.risk_reduced = 0.005   # Reduced during DD
        self.max_daily_dd = 0.025   # 2.5% max daily DD
        self.max_positions = 4
        self.dd_threshold = 0.05    # 5% rolling DD → reduce risk

        # ── Session definitions (in ET / Eastern Time, QC default) ──
        # London Open: 03:00 ET (= 08:00 UTC)
        # NY Open: 08:00 ET (= 13:00 UTC)
        # London Close: ~12:00 ET
        # NY Close: ~17:00 ET
        self.sessions = {
            "LONDON": {"open_hour": 3, "close_hour": 11},
            "NEWYORK": {"open_hour": 8, "close_hour": 16},
        }

        # ── Instrument universe ──
        self.tickers = ["SPX500USD", "NAS100USD", "DE30EUR", "JP225USD", "XAUUSD", "WTICOUSD"]
        self.symbols = {}
        self.instrument_data = {}

        for ticker in self.tickers:
            cfd = self.AddCfd(ticker, Resolution.Hour, Market.Oanda)
            cfd.SetLeverage(10)
            sym = cfd.Symbol
            self.symbols[ticker] = sym

            self.instrument_data[ticker] = {
                # Daily indicators
                "atr_d": self.ATR(sym, 14, MovingAverageType.Simple, Resolution.Daily),
                "sma_d": self.SMA(sym, self.trend_period, Resolution.Daily),
                # Session range tracking
                "london_range": {"high": 0.0, "low": 999999.0, "ready": False, "date": None},
                "newyork_range": {"high": 0.0, "low": 999999.0, "ready": False, "date": None},
                # Trade tracking per session
                "london_traded": False,
                "newyork_traded": False,
                # Position state
                "entry_price": 0.0,
                "entry_direction": 0,  # 1=long, -1=short
                "entry_session": None,
                "stop_loss": 0.0,
                "take_profit": 0.0,
            }

        # ── Risk tracking ──
        self.day_start_equity = 10000.0
        self.last_trade_date = None
        self.equity_history = []

        # ── Schedules ──
        # London range capture: at 04:00 ET (after 1 hour of London)
        self.Schedule.On(
            self.DateRules.EveryDay(),
            self.TimeRules.At(4, 0),
            self._finalize_london_range
        )
        # NY range capture: at 09:00 ET (after 1 hour of NY)
        self.Schedule.On(
            self.DateRules.EveryDay(),
            self.TimeRules.At(9, 0),
            self._finalize_newyork_range
        )
        # Session close exits
        self.Schedule.On(
            self.DateRules.EveryDay(),
            self.TimeRules.At(11, 0),
            self._close_london_positions
        )
        self.Schedule.On(
            self.DateRules.EveryDay(),
            self.TimeRules.At(16, 0),
            self._close_newyork_positions
        )
        # Friday flatten
        self.Schedule.On(
            self.DateRules.Every(DayOfWeek.Friday),
            self.TimeRules.At(16, 50),
            self._flatten_all
        )
        # EOD log
        self.Schedule.On(
            self.DateRules.EveryDay(),
            self.TimeRules.At(16, 55),
            self._eod_log
        )

        # ── Warmup ──
        self.SetWarmUp(timedelta(days=60))

        self.Log(f"[IM] {self.VERSION} | Instruments: {self.tickers}")
        self.Log(f"[IM] Breakout ATR mult={self.breakout_atr_mult} | SL ATR={self.sl_atr_mult} | TP R:R={self.tp_rr_ratio}")
        self.Log(f"[IM] Trend SMA period={self.trend_period} | Range hours={self.range_hours}")

    # ═══════════════════════════════════════════════════════════
    #  MAIN DATA HANDLER
    # ═══════════════════════════════════════════════════════════

    def OnData(self, data: Slice):
        if self.IsWarmingUp:
            return

        hour_et = self.Time.hour

        # ── Daily reset ──
        if self.last_trade_date is None or self.Time.date() != self.last_trade_date:
            self.day_start_equity = float(self.Portfolio.TotalPortfolioValue)
            self.last_trade_date = self.Time.date()
            self.equity_history.append(self.day_start_equity)
            if len(self.equity_history) > 30:
                self.equity_history = self.equity_history[-30:]
            # Reset daily session tracking
            for ticker in self.tickers:
                idata = self.instrument_data[ticker]
                idata["london_traded"] = False
                idata["newyork_traded"] = False
                idata["london_range"] = {"high": 0.0, "low": 999999.0, "ready": False, "date": self.Time.date()}
                idata["newyork_range"] = {"high": 0.0, "low": 999999.0, "ready": False, "date": self.Time.date()}

        # ── Build session ranges from hourly bars ──
        self._update_session_ranges(data, hour_et)

        # ── Manage open positions (check SL/TP every hour) ──
        for ticker in self.tickers:
            sym = self.symbols[ticker]
            if not data.ContainsKey(sym):
                continue
            if self.Portfolio[sym].Invested:
                self._manage_position(ticker, data)

        # ── Check for breakout entries ──
        # London breakout: check hours 4-10 ET
        if 4 <= hour_et <= 10:
            self._scan_entries("LONDON", data)
        # NY breakout: check hours 9-15 ET
        if 9 <= hour_et <= 15:
            self._scan_entries("NEWYORK", data)

    # ═══════════════════════════════════════════════════════════
    #  SESSION RANGE TRACKING
    # ═══════════════════════════════════════════════════════════

    def _update_session_ranges(self, data, hour_et):
        """Collect H/L during the opening hour of each session."""
        for ticker in self.tickers:
            sym = self.symbols[ticker]
            if not data.ContainsKey(sym):
                continue

            bar = data[sym]
            if bar is None:
                continue

            # Get high/low from QuoteBar (CFDs use QuoteBar)
            bar_high = self._get_high(bar)
            bar_low = self._get_low(bar)
            if bar_high <= 0 or bar_low <= 0:
                continue

            idata = self.instrument_data[ticker]

            # London opening hour: 03:00 ET bar (3:00-4:00 ET)
            if hour_et == 3:
                rng = idata["london_range"]
                if not rng["ready"]:
                    if bar_high > rng["high"]:
                        rng["high"] = bar_high
                    if bar_low < rng["low"]:
                        rng["low"] = bar_low

            # NY opening hour: 08:00 ET bar (8:00-9:00 ET)
            if hour_et == 8:
                rng = idata["newyork_range"]
                if not rng["ready"]:
                    if bar_high > rng["high"]:
                        rng["high"] = bar_high
                    if bar_low < rng["low"]:
                        rng["low"] = bar_low

    def _finalize_london_range(self):
        """Mark London opening range as complete at 04:00 ET."""
        for ticker in self.tickers:
            idata = self.instrument_data[ticker]
            rng = idata["london_range"]
            if rng["high"] > 0 and rng["low"] < 999999.0:
                rng["ready"] = True
                range_size = rng["high"] - rng["low"]
                self.Log(f"[RANGE LON] {ticker} H={rng['high']:.2f} L={rng['low']:.2f} Size={range_size:.2f}")

    def _finalize_newyork_range(self):
        """Mark NY opening range as complete at 09:00 ET."""
        for ticker in self.tickers:
            idata = self.instrument_data[ticker]
            rng = idata["newyork_range"]
            if rng["high"] > 0 and rng["low"] < 999999.0:
                rng["ready"] = True
                range_size = rng["high"] - rng["low"]
                self.Log(f"[RANGE NY] {ticker} H={rng['high']:.2f} L={rng['low']:.2f} Size={range_size:.2f}")

    # ═══════════════════════════════════════════════════════════
    #  ENTRY: BREAKOUT OF SESSION OPENING RANGE
    # ═══════════════════════════════════════════════════════════

    def _scan_entries(self, session_name, data):
        """Scan for breakout entries for a given session."""
        for ticker in self.tickers:
            sym = self.symbols[ticker]
            if not data.ContainsKey(sym):
                continue
            if self.Portfolio[sym].Invested:
                continue

            idata = self.instrument_data[ticker]

            # Check if already traded this session today
            traded_key = f"{session_name.lower()}_traded"
            if idata[traded_key]:
                continue

            # Get session range
            range_key = f"{session_name.lower()}_range"
            rng = idata[range_key]
            if not rng["ready"]:
                continue

            # Risk gate
            if not self._pass_risk_gates():
                continue

            # Max positions check
            open_count = sum(1 for t in self.tickers if self.Portfolio[self.symbols[t]].Invested)
            if open_count >= self.max_positions:
                continue

            # Get current price
            bar = data[sym]
            if bar is None:
                continue
            price = self._get_close(bar)
            if price <= 0:
                continue

            # ATR filter
            if not idata["atr_d"].IsReady:
                continue
            atr = float(idata["atr_d"].Current.Value)
            if atr <= 0:
                continue

            # Minimum breakout size
            min_breakout = self.breakout_atr_mult * atr

            # Trend filter (daily SMA)
            if not idata["sma_d"].IsReady:
                continue
            sma = float(idata["sma_d"].Current.Value)

            # Determine direction
            direction = 0
            range_high = rng["high"]
            range_low = rng["low"]
            range_size = range_high - range_low

            if range_size <= 0:
                continue

            # LONG: price breaks above range high + min breakout, AND above daily SMA
            if price > range_high + min_breakout and price > sma:
                direction = 1
            # SHORT: price breaks below range low - min breakout, AND below daily SMA
            elif price < range_low - min_breakout and price < sma:
                direction = -1

            if direction == 0:
                continue

            # Exchange must be open
            if not self.Securities[sym].Exchange.ExchangeOpen:
                continue

            # ── Calculate stop loss and take profit ──
            if direction == 1:
                sl_price = price - self.sl_atr_mult * atr
                # Also don't let SL be above range low (use the worse of the two)
                alt_sl = range_low
                sl_price = min(sl_price, alt_sl)
                risk_distance = price - sl_price
                tp_price = price + risk_distance * self.tp_rr_ratio
            else:
                sl_price = price + self.sl_atr_mult * atr
                alt_sl = range_high
                sl_price = max(sl_price, alt_sl)
                risk_distance = sl_price - price
                tp_price = price - risk_distance * self.tp_rr_ratio

            if risk_distance <= 0:
                continue

            # ── Position size ──
            risk_pct = self._get_current_risk_pct()
            qty = self._calculate_position_size(ticker, price, risk_distance, risk_pct)
            if qty <= 0:
                continue

            # ── Execute ──
            order_qty = qty if direction == 1 else -qty
            self.MarketOrder(sym, order_qty)

            side = "LONG" if direction == 1 else "SHORT"
            self.Log(f"[ENTRY {side}] {ticker} @ {price:.2f} | Session={session_name} | "
                     f"Range=[{range_low:.2f}, {range_high:.2f}] | "
                     f"SL={sl_price:.2f} | TP={tp_price:.2f} | ATR={atr:.2f} | SMA={sma:.2f}")

            idata["entry_price"] = price
            idata["entry_direction"] = direction
            idata["entry_session"] = session_name
            idata["stop_loss"] = sl_price
            idata["take_profit"] = tp_price
            idata[traded_key] = True

    # ═══════════════════════════════════════════════════════════
    #  POSITION MANAGEMENT
    # ═══════════════════════════════════════════════════════════

    def _manage_position(self, ticker, data):
        """Check SL/TP on every hourly bar."""
        sym = self.symbols[ticker]
        idata = self.instrument_data[ticker]
        direction = idata["entry_direction"]
        if direction == 0:
            return

        bar = data[sym]
        if bar is None:
            return

        price = self._get_close(bar)
        price_high = self._get_high(bar)
        price_low = self._get_low(bar)

        if not self.Securities[sym].Exchange.ExchangeOpen:
            return

        # ── STOP LOSS ──
        if direction == 1 and price_low <= idata["stop_loss"]:
            self.Liquidate(sym)
            pnl_pct = (price - idata["entry_price"]) / idata["entry_price"] * 100
            self.Log(f"[EXIT SL LONG] {ticker} @ {price:.2f} | Entry={idata['entry_price']:.2f} | PnL={pnl_pct:.2f}%")
            self._reset_instrument_state(ticker)
            return

        if direction == -1 and price_high >= idata["stop_loss"]:
            self.Liquidate(sym)
            pnl_pct = (idata["entry_price"] - price) / idata["entry_price"] * 100
            self.Log(f"[EXIT SL SHORT] {ticker} @ {price:.2f} | Entry={idata['entry_price']:.2f} | PnL={pnl_pct:.2f}%")
            self._reset_instrument_state(ticker)
            return

        # ── TAKE PROFIT ──
        if direction == 1 and price_high >= idata["take_profit"]:
            self.Liquidate(sym)
            pnl_pct = (price - idata["entry_price"]) / idata["entry_price"] * 100
            self.Log(f"[EXIT TP LONG] {ticker} @ {price:.2f} | Entry={idata['entry_price']:.2f} | PnL={pnl_pct:.2f}%")
            self._reset_instrument_state(ticker)
            return

        if direction == -1 and price_low <= idata["take_profit"]:
            self.Liquidate(sym)
            pnl_pct = (idata["entry_price"] - price) / idata["entry_price"] * 100
            self.Log(f"[EXIT TP SHORT] {ticker} @ {price:.2f} | Entry={idata['entry_price']:.2f} | PnL={pnl_pct:.2f}%")
            self._reset_instrument_state(ticker)
            return

    # ═══════════════════════════════════════════════════════════
    #  SESSION CLOSE EXITS
    # ═══════════════════════════════════════════════════════════

    def _close_london_positions(self):
        """Close all London-session positions at 11:00 ET."""
        for ticker in self.tickers:
            sym = self.symbols[ticker]
            idata = self.instrument_data[ticker]
            if self.Portfolio[sym].Invested and idata["entry_session"] == "LONDON":
                if self.Securities[sym].Exchange.ExchangeOpen:
                    price = float(self.Securities[sym].Price)
                    direction = idata["entry_direction"]
                    if direction == 1:
                        pnl_pct = (price - idata["entry_price"]) / idata["entry_price"] * 100
                    else:
                        pnl_pct = (idata["entry_price"] - price) / idata["entry_price"] * 100
                    self.Liquidate(sym)
                    self.Log(f"[EXIT SESSION LON] {ticker} @ {price:.2f} | PnL={pnl_pct:.2f}%")
                    self._reset_instrument_state(ticker)

    def _close_newyork_positions(self):
        """Close all NY-session positions at 16:00 ET."""
        for ticker in self.tickers:
            sym = self.symbols[ticker]
            idata = self.instrument_data[ticker]
            if self.Portfolio[sym].Invested and idata["entry_session"] == "NEWYORK":
                if self.Securities[sym].Exchange.ExchangeOpen:
                    price = float(self.Securities[sym].Price)
                    direction = idata["entry_direction"]
                    if direction == 1:
                        pnl_pct = (price - idata["entry_price"]) / idata["entry_price"] * 100
                    else:
                        pnl_pct = (idata["entry_price"] - price) / idata["entry_price"] * 100
                    self.Liquidate(sym)
                    self.Log(f"[EXIT SESSION NY] {ticker} @ {price:.2f} | PnL={pnl_pct:.2f}%")
                    self._reset_instrument_state(ticker)

    def _flatten_all(self):
        """Friday 16:50 ET — Close all positions before weekend."""
        for ticker in self.tickers:
            sym = self.symbols[ticker]
            if self.Portfolio[sym].Invested:
                if self.Securities[sym].Exchange.ExchangeOpen:
                    self.Liquidate(sym)
                    self.Log(f"[FLATTEN FRI] {ticker} closed")
                    self._reset_instrument_state(ticker)

    # ═══════════════════════════════════════════════════════════
    #  POSITION SIZING
    # ═══════════════════════════════════════════════════════════

    def _get_current_risk_pct(self):
        """Get risk per trade, reduced if in drawdown."""
        if len(self.equity_history) < 5:
            return self.risk_per_trade

        window = self.equity_history[-20:] if len(self.equity_history) >= 20 else self.equity_history
        peak = max(window)
        current = float(self.Portfolio.TotalPortfolioValue)
        dd = (peak - current) / peak if peak > 0 else 0

        if dd >= self.dd_threshold:
            return self.risk_reduced
        return self.risk_per_trade

    def _calculate_position_size(self, ticker, price, risk_distance, risk_pct):
        """Fixed fractional position sizing."""
        equity = float(self.Portfolio.TotalPortfolioValue)
        risk_amount = equity * risk_pct

        if risk_distance <= 0 or price <= 0:
            return 0

        # For CFDs, quantity is in units of the base asset
        # Risk amount / risk per unit = quantity
        qty = risk_amount / risk_distance

        # Round to reasonable lot size
        qty = int(qty)
        if qty < 1:
            return 0
        return qty

    # ═══════════════════════════════════════════════════════════
    #  RISK MANAGEMENT
    # ═══════════════════════════════════════════════════════════

    def _pass_risk_gates(self):
        """Daily DD limit check."""
        equity = float(self.Portfolio.TotalPortfolioValue)
        daily_pnl = equity - self.day_start_equity
        if daily_pnl < -(self.day_start_equity * self.max_daily_dd):
            return False
        return True

    # ═══════════════════════════════════════════════════════════
    #  HELPERS
    # ═══════════════════════════════════════════════════════════

    def _get_close(self, bar):
        """Get close price from TradeBar or QuoteBar."""
        if hasattr(bar, 'Close') and bar.Close is not None:
            val = float(bar.Close)
            if val > 0:
                return val
        if hasattr(bar, 'Value'):
            return float(bar.Value)
        return 0.0

    def _get_high(self, bar):
        """Get high price from TradeBar or QuoteBar."""
        if hasattr(bar, 'High') and bar.High is not None:
            val = float(bar.High)
            if val > 0:
                return val
        return self._get_close(bar)

    def _get_low(self, bar):
        """Get low price from TradeBar or QuoteBar."""
        if hasattr(bar, 'Low') and bar.Low is not None:
            val = float(bar.Low)
            if val > 0:
                return val
        return self._get_close(bar)

    def _reset_instrument_state(self, ticker):
        """Clear position tracking after exit."""
        idata = self.instrument_data[ticker]
        idata["entry_price"] = 0.0
        idata["entry_direction"] = 0
        idata["entry_session"] = None
        idata["stop_loss"] = 0.0
        idata["take_profit"] = 0.0

    # ═══════════════════════════════════════════════════════════
    #  LOGGING
    # ═══════════════════════════════════════════════════════════

    def _eod_log(self):
        """16:55 ET — Daily summary."""
        equity = float(self.Portfolio.TotalPortfolioValue)
        daily_pnl = equity - self.day_start_equity
        positions = []
        for ticker in self.tickers:
            sym = self.symbols[ticker]
            if self.Portfolio[sym].Invested:
                h = self.Portfolio[sym]
                side = "L" if h.IsLong else "S"
                positions.append(f"{ticker}={side}")
        pos_str = ", ".join(positions) if positions else "FLAT"
        self.Log(f"[EOD] Equity=${equity:.2f} | DailyPnL=${daily_pnl:.2f} | {pos_str}")

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
