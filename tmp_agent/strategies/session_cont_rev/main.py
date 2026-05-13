# region imports
from AlgorithmImports import *
# endregion

class FXSessionContRev(QCAlgorithm):
    """
    FX Session Continuation/Reversal Strategy
    
    Hypothesis: The London session establishes the daily directional bias.
    When NY session opens, if price continues in the London direction with
    momentum, ride the continuation. If price reverses against London with
    a strong reversal candle, trade the reversal.
    
    This is structurally different from breakout (we don't trade the breakout
    itself) and from trend following (we use intraday session dynamics, not
    multi-day trends).
    
    Logic:
    - At London close (16:00 UTC), measure London session return
    - If London return > threshold AND NY continues in same direction: CONTINUATION
    - If London return > threshold AND NY reverses against London: REVERSAL
    - Use RSI divergence to confirm reversals
    - ATR-based stops and targets
    
    Pairs: 6 FX majors (EURUSD, GBPUSD, USDJPY, AUDUSD, NZDUSD, USDCAD)
    Timeframe: H1 bars, session-based decision
    
    Contract: Brain V9 Forex | Family: Session Continuation/Reversal | Version: V1.0
    """

    def Initialize(self):
        # ── Period ──
        start_year = int(self.GetParameter("start_year", "2020"))
        end_year   = int(self.GetParameter("end_year",   "2024"))
        end_month  = int(self.GetParameter("end_month",  "12"))
        self.SetStartDate(start_year, 1, 1)
        self.SetEndDate(end_year, end_month, 28)
        self.SetCash(10000)
        self.SetBrokerageModel(BrokerageName.OandaBrokerage, AccountType.Margin)
        self.SetBenchmark("SPY")

        # ── Parameters ──
        self.risk_per_trade   = float(self.GetParameter("risk_per_trade", "0.015"))
        self.max_positions    = int(self.GetParameter("max_positions", "3"))
        self.london_min_move  = float(self.GetParameter("london_min_move", "0.3"))  # min London move in ATR units
        self.cont_confirm_hrs = int(self.GetParameter("cont_confirm_hrs", "2"))  # hours after London close to confirm
        self.rev_rsi_thresh   = int(self.GetParameter("rev_rsi_thresh", "35"))  # RSI threshold for reversal
        self.atr_period       = int(self.GetParameter("atr_period", "14"))
        self.rsi_period       = int(self.GetParameter("rsi_period", "14"))
        self.stop_atr_mult    = float(self.GetParameter("stop_atr_mult", "1.5"))
        self.tp_atr_mult      = float(self.GetParameter("tp_atr_mult", "2.5"))  # take profit in ATR
        self.max_hold_hours   = int(self.GetParameter("max_hold_hours", "24"))
        self.max_daily_risk   = float(self.GetParameter("max_daily_risk", "0.03"))
        self.trail_atr_mult   = float(self.GetParameter("trail_atr_mult", "2.0"))  # trailing stop
        self.mode             = self.GetParameter("mode", "both")  # "cont", "rev", or "both"

        # ── Pairs ──
        pair_list = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "NZDUSD", "USDCAD"]
        self.symbols = {}
        self.atr_indicators = {}
        self.rsi_indicators = {}
        
        for pair in pair_list:
            sym = self.AddForex(pair, Resolution.Hour, Market.Oanda).Symbol
            self.symbols[pair] = sym
            self.atr_indicators[pair] = self.ATR(sym, self.atr_period, MovingAverageType.Simple, Resolution.Hour)
            self.rsi_indicators[pair] = self.RSI(sym, self.rsi_period, MovingAverageType.Simple, Resolution.Hour)

        # ── Session tracking ──
        # London: 07:00 - 16:00 UTC
        # NY: 12:00 - 21:00 UTC (overlap 12-16)
        self.london_open_prices = {}   # pair -> price at 07:00 UTC
        self.london_close_prices = {}  # pair -> price at 16:00 UTC
        self.london_high = {}          # pair -> high during London
        self.london_low = {}           # pair -> low during London
        self.london_direction = {}     # pair -> 1 (bullish) or -1 (bearish) or 0
        self.ny_confirmed = {}         # pair -> True if NY confirmed direction
        
        # ── Position tracking ──
        self.positions = {}  # pair -> {"side", "entry", "stop", "tp", "entry_time", "trail_stop"}
        self.daily_pnl = 0
        self.last_date = None
        self.daily_trades = 0

        # Warm up
        self.SetWarmUp(self.atr_period + 5, Resolution.Hour)

    def OnData(self, data):
        if self.IsWarmingUp:
            return

        hour = self.Time.hour
        current_date = self.Time.date()
        
        # Reset daily tracking
        if self.last_date != current_date:
            self.daily_pnl = 0
            self.daily_trades = 0
            self.last_date = current_date
            # Reset session data
            self.london_open_prices.clear()
            self.london_close_prices.clear()
            self.london_high.clear()
            self.london_low.clear()
            self.london_direction.clear()
            self.ny_confirmed.clear()

        for pair, sym in self.symbols.items():
            if not data.ContainsKey(sym):
                continue
            
            price = self.Securities[sym].Price
            if price <= 0:
                continue

            atr = self.atr_indicators[pair].Current.Value
            if not self.atr_indicators[pair].IsReady or atr <= 0:
                continue

            # ── Track London Session ──
            if hour == 7:
                self.london_open_prices[pair] = price
                self.london_high[pair] = price
                self.london_low[pair] = price
            
            if 7 <= hour < 16 and pair in self.london_open_prices:
                if pair in self.london_high:
                    self.london_high[pair] = max(self.london_high[pair], price)
                    self.london_low[pair] = min(self.london_low[pair], price)

            # ── London Close — Determine Session Direction ──
            if hour == 16 and pair in self.london_open_prices and pair not in self.london_close_prices:
                self.london_close_prices[pair] = price
                london_return = price - self.london_open_prices[pair]
                london_move_atr = abs(london_return) / atr if atr > 0 else 0
                
                if london_move_atr >= self.london_min_move:
                    self.london_direction[pair] = 1 if london_return > 0 else -1
                else:
                    self.london_direction[pair] = 0  # Insufficient move
            
            # ── NY Confirmation Window (17:00 - 19:00 UTC) ──
            if 16 + self.cont_confirm_hrs >= hour > 16:
                self._check_ny_signal(pair, price, atr, hour)

            # ── Manage existing positions ──
            if pair in self.positions:
                self._manage_position(pair, price, atr)

    def _check_ny_signal(self, pair, price, atr, hour):
        """Check for continuation or reversal signal during NY session."""
        if pair not in self.london_direction or self.london_direction[pair] == 0:
            return
        if pair in self.ny_confirmed:
            return  # Already traded this session
        if pair in self.positions:
            return  # Already have a position
        if self.daily_trades >= self.max_positions:
            return  # Daily position limit
        
        # Check daily risk limit
        equity = self.Portfolio.TotalPortfolioValue
        if equity <= 0:
            return
        if abs(self.daily_pnl) / equity > self.max_daily_risk:
            return

        london_dir = self.london_direction[pair]
        london_close = self.london_close_prices.get(pair, 0)
        if london_close <= 0:
            return
        
        # NY move since London close
        ny_move = price - london_close
        ny_dir = 1 if ny_move > 0 else -1
        ny_move_atr = abs(ny_move) / atr if atr > 0 else 0
        
        sym = self.symbols[pair]
        rsi = self.rsi_indicators[pair].Current.Value
        
        signal = 0  # 0=none, 1=long, -1=short
        signal_type = ""
        
        # ── CONTINUATION: NY continues London direction ──
        if self.mode in ("both", "cont"):
            if ny_dir == london_dir and ny_move_atr >= 0.2:  # NY confirming with 0.2 ATR
                signal = london_dir
                signal_type = "CONT"
        
        # ── REVERSAL: NY reverses against London with RSI confirmation ──
        if self.mode in ("both", "rev") and signal == 0:
            if ny_dir != london_dir and ny_move_atr >= 0.3:  # NY reversing with 0.3 ATR
                # RSI confirmation for reversal
                if london_dir == 1 and rsi < (100 - self.rev_rsi_thresh):
                    # London was bullish, NY bearish, RSI confirming weakness
                    signal = -1
                    signal_type = "REV"
                elif london_dir == -1 and rsi > self.rev_rsi_thresh:
                    # London was bearish, NY bullish, RSI confirming strength
                    signal = 1
                    signal_type = "REV"

        if signal == 0:
            return

        # ── Execute Trade ──
        self.ny_confirmed[pair] = True
        self.daily_trades += 1
        
        stop_distance = atr * self.stop_atr_mult
        tp_distance = atr * self.tp_atr_mult
        risk_amount = equity * self.risk_per_trade
        quantity = int(risk_amount / stop_distance)
        if quantity < 1:
            quantity = 1
        
        if signal == 1:
            self.MarketOrder(sym, quantity)
            stop_price = price - stop_distance
            tp_price = price + tp_distance
        else:
            self.MarketOrder(sym, -quantity)
            stop_price = price + stop_distance
            tp_price = price - tp_distance
        
        self.positions[pair] = {
            "side": signal,
            "entry": price,
            "stop": stop_price,
            "tp": tp_price,
            "trail_stop": stop_price,
            "entry_time": self.Time,
            "type": signal_type,
            "atr": atr,
        }
        
        self.Log(f"{signal_type} {pair}: side={'LONG' if signal==1 else 'SHORT'}, "
                 f"entry={price:.5f}, stop={stop_price:.5f}, tp={tp_price:.5f}, "
                 f"london_dir={london_dir}, rsi={rsi:.1f}")

    def _manage_position(self, pair, price, atr):
        """Manage existing position: trailing stop, TP, time stop."""
        pos = self.positions[pair]
        sym = self.symbols[pair]
        side = pos["side"]
        
        # ── Time stop ──
        hours_held = (self.Time - pos["entry_time"]).total_seconds() / 3600
        if hours_held >= self.max_hold_hours:
            self.Liquidate(sym)
            pnl = (price - pos["entry"]) * side
            self.Log(f"TIME STOP {pair}: held {hours_held:.0f}h, pnl={pnl:.5f}")
            self.daily_pnl += pnl
            del self.positions[pair]
            return

        # ── Take profit ──
        if side == 1 and price >= pos["tp"]:
            self.Liquidate(sym)
            pnl = price - pos["entry"]
            self.Log(f"TP HIT {pair}: +{pnl:.5f}")
            self.daily_pnl += pnl
            del self.positions[pair]
            return
        elif side == -1 and price <= pos["tp"]:
            self.Liquidate(sym)
            pnl = pos["entry"] - price
            self.Log(f"TP HIT {pair}: +{pnl:.5f}")
            self.daily_pnl += pnl
            del self.positions[pair]
            return

        # ── Trailing stop update ──
        trail_dist = atr * self.trail_atr_mult
        if side == 1:
            new_trail = price - trail_dist
            if new_trail > pos["trail_stop"]:
                pos["trail_stop"] = new_trail
            # Check stop
            effective_stop = max(pos["stop"], pos["trail_stop"])
            if price <= effective_stop:
                self.Liquidate(sym)
                pnl = price - pos["entry"]
                self.Log(f"STOP {pair}: pnl={pnl:.5f}")
                self.daily_pnl += pnl
                del self.positions[pair]
                return
        else:
            new_trail = price + trail_dist
            if new_trail < pos["trail_stop"]:
                pos["trail_stop"] = new_trail
            effective_stop = min(pos["stop"], pos["trail_stop"])
            if price >= effective_stop:
                self.Liquidate(sym)
                pnl = pos["entry"] - price
                self.Log(f"STOP {pair}: pnl={pnl:.5f}")
                self.daily_pnl += pnl
                del self.positions[pair]
                return

    def OnEndOfAlgorithm(self):
        equity = self.Portfolio.TotalPortfolioValue
        ret = (equity - 10000) / 10000
        self.Log(f"=== FINAL: Equity={equity:.2f}, Return={ret:.2%} ===")
        self.Log(f"  Positions still open: {len(self.positions)}")
