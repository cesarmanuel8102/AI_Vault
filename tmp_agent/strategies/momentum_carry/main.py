# region imports
from AlgorithmImports import *
from datetime import datetime, timedelta
import numpy as np
# endregion


class FxMomentumCarry(QCAlgorithm):
    """
    Brain V9 — FX Momentum + Carry with Crash Filter V1.0

    THESIS:
    Cross-sectional FX momentum and carry are the two most robust academic
    anomalies in currency markets (Asness/Moskowitz/Pedersen, BIS).
    This strategy ranks G10 currencies by recent momentum, goes long the
    top performers and short the bottom performers, with a volatility
    regime filter to avoid carry crashes.

    MECHANICS:
    - Universe: 8 G10 forex pairs vs USD on Oanda
    - Signal: Composite of momentum (63-day return) and carry proxy (21-day return spread)
    - Ranking: Weekly, long top N, short bottom N
    - Crash filter: Rolling 20-day realized vol of portfolio; if vol spikes above
      threshold (2x its own 60-day average), reduce position size by 50%
    - Rebalance: Every Monday at market open
    - Risk: Equal-weight positions, 2% equity risk per position, max 4 positions
    - Hold: ~1 week per rebalance cycle

    KEY DIFFERENCES FROM SQUEEZE STRATEGY:
    - More trades (~200-260/year from weekly rebalancing)
    - Momentum factor has decades of academic evidence
    - Cross-sectional (relative ranking) not absolute signals
    - Naturally hedged (always long+short = market neutral-ish)

    Pairs: EURUSD, GBPUSD, USDJPY, AUDUSD, NZDUSD, USDCAD, USDCHF, GBPJPY
    Timeframe: Daily data for signals, Weekly rebalance
    """

    VERSION = "MC-V1.1"

    def Initialize(self):
        # -- Backtest window --
        self.SetStartDate(2020, 1, 1)
        self.SetEndDate(2024, 12, 31)
        self.SetCash(10000)
        self.SetBrokerageModel(BrokerageName.OandaBrokerage, AccountType.Margin)

        # -- Parameters --
        self.momentum_window = int(self.GetParameter("mom_window", 63))       # ~3 months lookback
        self.short_mom_window = int(self.GetParameter("short_mom", 21))       # ~1 month for carry proxy
        self.num_long = int(self.GetParameter("num_long", 2))                 # Top N to go long
        self.num_short = int(self.GetParameter("num_short", 2))               # Bottom N to go short
        self.risk_per_position = float(self.GetParameter("risk_pos", 0.02))   # 2% equity per position
        self.vol_crash_mult = float(self.GetParameter("vol_crash", 2.0))      # Vol spike = Nx avg vol
        self.vol_lookback = int(self.GetParameter("vol_lookback", 60))        # Days for avg vol baseline
        self.rebalance_day = int(self.GetParameter("rebal_day", 0))           # 0=Monday
        self.atr_stop_mult = float(self.GetParameter("atr_stop", 2.0))       # Stop loss in ATR units
        self.mom_weight = float(self.GetParameter("mom_weight", 0.7))         # Weight for momentum signal
        self.carry_weight = float(self.GetParameter("carry_weight", 0.3))     # Weight for carry proxy signal

        # -- Forex Pairs: G10 vs USD + GBPJPY cross --
        self.pair_tickers = [
            "EURUSD", "GBPUSD", "USDJPY", "AUDUSD",
            "NZDUSD", "USDCAD", "USDCHF", "GBPJPY"
        ]
        # Which pairs are "USD quoted" (XXXUSD) vs "USD base" (USDXXX)
        # For XXXUSD: rising price = XXX strengthening = long XXX
        # For USDXXX: rising price = USD strengthening = short XXX
        # For GBPJPY: special case (no USD), track as momentum of GBP vs JPY
        self.usd_quote_pairs = {"EURUSD", "GBPUSD", "AUDUSD", "NZDUSD"}  # Long pair = long base ccy
        self.usd_base_pairs = {"USDJPY", "USDCAD", "USDCHF"}             # Long pair = long USD (short base)

        self.symbols = {}
        self.pairs_data = {}

        for ticker in self.pair_tickers:
            forex = self.AddForex(ticker, Resolution.Daily, Market.Oanda)
            forex.SetLeverage(10)
            sym = forex.Symbol
            self.symbols[ticker] = sym

            self.pairs_data[ticker] = {
                "atr_d": self.ATR(sym, 14, MovingAverageType.Simple, Resolution.Daily),
                "price_history": [],   # Rolling daily closes for momentum calc
                "current_direction": 0,  # 1=long, -1=short, 0=flat
                "entry_price": 0.0,
                "stop_price": 0.0,
            }

        # -- Volatility tracking for crash filter --
        self.portfolio_returns = []  # Daily portfolio returns for vol calc
        self.prev_equity = 10000.0
        self.rebalance_count = 0  # Counter for biweekly rebalancing
        self.rebalance_freq = int(self.GetParameter("rebal_freq", 2))  # Rebalance every N weeks

        # -- Rebalance schedule: Monday 10:00 ET (London+NY overlap) --
        self.Schedule.On(
            self.DateRules.Every(DayOfWeek.Monday),
            self.TimeRules.At(10, 0),
            self._rebalance
        )

        # -- Friday flatten REMOVED for MC strategy --
        # Momentum+carry positions should hold multi-week.
        # Weekly rebalance naturally rotates positions.
        # Only flatten if we want to avoid specific weekend risk (disabled for now).

        # -- Daily: track portfolio vol + manage stops --
        self.Schedule.On(
            self.DateRules.EveryDay(),
            self.TimeRules.At(17, 0),
            self._daily_update
        )

        # -- EOD logging --
        self.Schedule.On(
            self.DateRules.EveryDay(),
            self.TimeRules.At(16, 55),
            self._eod_log
        )

        # -- Warmup --
        self.SetWarmUp(timedelta(days=self.momentum_window + 30))

        self.Log(f"[MC] {self.VERSION} | Pairs: {self.pair_tickers}")
        self.Log(f"[MC] Momentum: {self.momentum_window}d | Carry proxy: {self.short_mom_window}d")
        self.Log(f"[MC] Long top {self.num_long}, Short bottom {self.num_short}")
        self.Log(f"[MC] Crash filter: {self.vol_crash_mult}x {self.vol_lookback}d avg vol")
        self.Log(f"[MC] Signal weights: mom={self.mom_weight}, carry={self.carry_weight}")

    # =================================================================
    #  DAILY PRICE TRACKING
    # =================================================================

    def OnData(self, data: Slice):
        if self.IsWarmingUp:
            return

        # Track daily closes for momentum calculation
        for ticker in self.pair_tickers:
            sym = self.symbols[ticker]
            if data.ContainsKey(sym) and data[sym] is not None:
                bar = data[sym]
                price = float(bar.Close) if hasattr(bar, 'Close') else float(bar.Value)
                hist = self.pairs_data[ticker]["price_history"]
                hist.append(price)
                # Keep enough history for momentum + some buffer
                max_hist = self.momentum_window + 20
                if len(hist) > max_hist:
                    self.pairs_data[ticker]["price_history"] = hist[-max_hist:]

    # =================================================================
    #  DAILY UPDATE: VOL TRACKING + STOP MANAGEMENT
    # =================================================================

    def _daily_update(self):
        """Track portfolio volatility for crash filter + check stops."""
        equity = float(self.Portfolio.TotalPortfolioValue)
        if self.prev_equity > 0:
            daily_ret = (equity - self.prev_equity) / self.prev_equity
            self.portfolio_returns.append(daily_ret)
            if len(self.portfolio_returns) > self.vol_lookback + 30:
                self.portfolio_returns = self.portfolio_returns[-(self.vol_lookback + 30):]
        self.prev_equity = equity

        # -- Check stops on open positions (only if stops enabled) --
        if self.atr_stop_mult <= 0:
            return
        for ticker in self.pair_tickers:
            sym = self.symbols[ticker]
            pd = self.pairs_data[ticker]
            if not self.Portfolio[sym].Invested:
                continue
            if pd["stop_price"] <= 0:
                continue

            price = float(self.Securities[sym].Price)
            direction = pd["current_direction"]

            hit_stop = False
            if direction == 1 and price <= pd["stop_price"]:
                hit_stop = True
            elif direction == -1 and price >= pd["stop_price"]:
                hit_stop = True

            if hit_stop:
                if self.Securities[sym].Exchange.ExchangeOpen:
                    self.Liquidate(sym)
                    pnl = (price - pd["entry_price"]) / pd["entry_price"] * 100 * direction
                    self.Log(f"[STOP {ticker}] @ {price:.5f} | Entry={pd['entry_price']:.5f} | PnL={pnl:.2f}%")
                    pd["current_direction"] = 0
                    pd["entry_price"] = 0.0
                    pd["stop_price"] = 0.0

    # =================================================================
    #  CRASH FILTER
    # =================================================================

    def _is_crash_regime(self):
        """Detect elevated volatility regime (carry crash risk).

        Uses recent portfolio realized vol vs its own longer-term average.
        If recent vol > threshold * avg vol, we're in crash regime.
        """
        if len(self.portfolio_returns) < self.vol_lookback:
            return False  # Not enough data yet, assume normal

        recent_rets = self.portfolio_returns[-20:]  # Last 20 days
        if len(recent_rets) < 10:
            return False

        recent_vol = float(np.std(recent_rets)) * (252 ** 0.5)  # Annualized

        # Long-term avg vol
        long_rets = self.portfolio_returns[-self.vol_lookback:]
        long_vol = float(np.std(long_rets)) * (252 ** 0.5)

        if long_vol <= 0:
            return False

        vol_ratio = recent_vol / long_vol
        if vol_ratio > self.vol_crash_mult:
            self.Log(f"[CRASH FILTER] Vol ratio={vol_ratio:.2f} > {self.vol_crash_mult} | "
                     f"Recent={recent_vol:.4f} Avg={long_vol:.4f}")
            return True

        return False

    # =================================================================
    #  MOMENTUM + CARRY SIGNAL
    # =================================================================

    def _compute_signals(self):
        """Compute momentum and carry-proxy scores for all pairs.

        Momentum: 63-day log return (medium-term trend)
        Carry proxy: 21-day return minus 63-day return, normalized.
                     High-carry pairs tend to have positive short-term returns
                     relative to their medium-term trend (carry accrual).

        Returns dict: {ticker: composite_score}
        """
        scores = {}

        for ticker in self.pair_tickers:
            hist = self.pairs_data[ticker]["price_history"]
            if len(hist) < self.momentum_window + 1:
                continue

            current = hist[-1]
            past_long = hist[-(self.momentum_window + 1)]
            past_short = hist[-(self.short_mom_window + 1)]

            if past_long <= 0 or past_short <= 0 or current <= 0:
                continue

            # Momentum: 63-day return
            mom_return = (current - past_long) / past_long

            # Carry proxy: 21-day return (short-term outperformance captures carry accrual)
            carry_return = (current - past_short) / past_short

            # For USD-base pairs (USDXXX), INVERT the signal
            # Rising USDCAD = USD strengthening = CAD weakening
            # We want to rank the NON-USD currency strength
            if ticker in self.usd_base_pairs:
                mom_return = -mom_return
                carry_return = -carry_return

            # GBPJPY: keep as-is (momentum of GBP vs JPY)

            # Composite score
            composite = self.mom_weight * mom_return + self.carry_weight * carry_return
            scores[ticker] = composite

        return scores

    # =================================================================
    #  WEEKLY REBALANCE
    # =================================================================

    def _rebalance(self):
        """Periodic rebalance: rank pairs by momentum+carry, go long top N, short bottom N."""
        if self.IsWarmingUp:
            return

        # Biweekly gate: only rebalance every N weeks
        self.rebalance_count += 1
        if self.rebalance_count % self.rebalance_freq != 0:
            return

        scores = self._compute_signals()
        if len(scores) < self.num_long + self.num_short:
            self.Log(f"[REBAL SKIP] Only {len(scores)} pairs with signals")
            return

        # Sort by composite score: highest = strongest momentum+carry
        ranked = sorted(scores.items(), key=lambda x: x[1], reverse=True)

        # Select long (top N) and short (bottom N) candidates
        long_tickers = [t for t, s in ranked[:self.num_long]]
        short_tickers = [t for t, s in ranked[-self.num_short:]]

        # Crash filter: reduce sizing if in elevated vol regime
        crash_mode = self._is_crash_regime()
        size_mult = 0.5 if crash_mode else 1.0

        # Log the ranking
        rank_str = " | ".join([f"{t}:{s:.4f}" for t, s in ranked])
        self.Log(f"[REBAL] Ranking: {rank_str}")
        self.Log(f"[REBAL] Long: {long_tickers} | Short: {short_tickers} | Crash={crash_mode}")

        # Close positions that are no longer in the target portfolio
        for ticker in self.pair_tickers:
            sym = self.symbols[ticker]
            pd = self.pairs_data[ticker]
            if not self.Portfolio[sym].Invested:
                continue

            should_be_long = ticker in long_tickers
            should_be_short = ticker in short_tickers
            currently_long = pd["current_direction"] == 1
            currently_short = pd["current_direction"] == -1

            # Close if direction changed or pair dropped out
            need_close = False
            if currently_long and not should_be_long:
                need_close = True
            elif currently_short and not should_be_short:
                need_close = True

            if need_close:
                if self.Securities[sym].Exchange.ExchangeOpen:
                    price = float(self.Securities[sym].Price)
                    pnl = (price - pd["entry_price"]) / pd["entry_price"] * 100 * pd["current_direction"]
                    self.Liquidate(sym)
                    self.Log(f"[CLOSE {ticker}] Direction change | PnL={pnl:.2f}%")
                    pd["current_direction"] = 0
                    pd["entry_price"] = 0.0
                    pd["stop_price"] = 0.0

        # Open/maintain long positions
        for ticker in long_tickers:
            self._enter_or_maintain(ticker, 1, size_mult)

        # Open/maintain short positions
        for ticker in short_tickers:
            self._enter_or_maintain(ticker, -1, size_mult)

    def _enter_or_maintain(self, ticker, direction, size_mult):
        """Enter a new position or maintain existing one in the right direction."""
        sym = self.symbols[ticker]
        pd = self.pairs_data[ticker]

        # Already in correct direction? Just update stop (if stops enabled).
        if pd["current_direction"] == direction and self.Portfolio[sym].Invested:
            if self.atr_stop_mult > 0 and pd["atr_d"].IsReady:
                atr = float(pd["atr_d"].Current.Value)
                price = float(self.Securities[sym].Price)
                if direction == 1:
                    new_stop = price - self.atr_stop_mult * atr
                    if new_stop > pd["stop_price"]:
                        pd["stop_price"] = new_stop
                elif direction == -1:
                    new_stop = price + self.atr_stop_mult * atr
                    if new_stop < pd["stop_price"] or pd["stop_price"] <= 0:
                        pd["stop_price"] = new_stop
            return

        # Need to enter new position
        if not self.Securities[sym].Exchange.ExchangeOpen:
            return
        if not pd["atr_d"].IsReady:
            return

        price = float(self.Securities[sym].Price)
        atr = float(pd["atr_d"].Current.Value)
        if atr <= 0 or price <= 0:
            return

        # Position sizing
        equity = float(self.Portfolio.TotalPortfolioValue)
        risk_amount = equity * self.risk_per_position * size_mult

        if self.atr_stop_mult > 0:
            # Risk-based sizing: equity_at_risk / stop_distance
            stop_distance = self.atr_stop_mult * atr
            if stop_distance <= 0:
                return
            qty = int(risk_amount / stop_distance)
        else:
            # No stop: fixed allocation sizing (risk_per_position % of equity in notional)
            qty = int((risk_amount * 10) / price)  # ~10x the "risk" as notional allocation

        if qty < 1000:
            return
        qty = (qty // 1000) * 1000

        # For USD-base pairs, the direction logic needs adjustment:
        # "long momentum" for USDCAD means SHORT the pair (because we inverted the signal)
        actual_direction = direction
        if ticker in self.usd_base_pairs:
            actual_direction = -direction  # Invert: long signal = short pair = short USD

        # Execute
        order_qty = qty if actual_direction == 1 else -qty
        self.MarketOrder(sym, order_qty)

        stop_price = 0.0
        if self.atr_stop_mult > 0:
            sd = self.atr_stop_mult * atr
            stop_price = price - sd if actual_direction == 1 else price + sd
        side = "LONG" if actual_direction == 1 else "SHORT"
        self.Log(f"[ENTRY-MC {side}] {ticker} @ {price:.5f} | Qty={order_qty} | "
                 f"ATR={atr:.5f} | Stop={'NONE' if stop_price == 0 else f'{stop_price:.5f}'} | SizeMult={size_mult}")

        pd["current_direction"] = actual_direction
        pd["entry_price"] = price
        pd["stop_price"] = stop_price

    # =================================================================
    #  SCHEDULING
    # =================================================================

    def _flatten_all(self):
        """Friday 16:50 ET -- Close all before weekend."""
        for ticker in self.pair_tickers:
            sym = self.symbols[ticker]
            pd = self.pairs_data[ticker]
            if self.Portfolio[sym].Invested:
                if self.Securities[sym].Exchange.ExchangeOpen:
                    self.Liquidate(sym)
                    self.Log(f"[FLATTEN FRI] {ticker} closed")
                    pd["current_direction"] = 0
                    pd["entry_price"] = 0.0
                    pd["stop_price"] = 0.0

    def _eod_log(self):
        """16:55 ET -- Daily summary."""
        equity = float(self.Portfolio.TotalPortfolioValue)
        positions = []
        for ticker in self.pair_tickers:
            sym = self.symbols[ticker]
            if self.Portfolio[sym].Invested:
                h = self.Portfolio[sym]
                positions.append(f"{ticker}={'L' if h.IsLong else 'S'}({h.Quantity})")
        pos_str = ", ".join(positions) if positions else "FLAT"
        self.Log(f"[EOD] Equity=${equity:.2f} | Positions: {pos_str}")

    # =================================================================
    #  EVENT HANDLERS
    # =================================================================

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
