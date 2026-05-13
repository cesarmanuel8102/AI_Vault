# region imports
from AlgorithmImports import *
from datetime import datetime, timedelta
import math
# endregion


class StatArbPairsV10(QCAlgorithm):
    """
    Brain V9 -- Stat-Arb Pairs V1.0

    MODE A -- High-Velocity Edge Discovery
    Family: Statistical Arbitrage on cointegrated pairs
    Target: CAGR >= 20%, Sharpe >= 1.2
    Kill gates: CAGR < 12% or Sharpe < 1.0 = DEAD

    HYPOTHESIS: Certain CFD pairs (indices, commodities, bonds) exhibit
    mean-reverting spread behavior. Trading the z-score of the ratio/spread
    when it diverges beyond thresholds captures reversion alpha that is
    uncorrelated with directional trend strategies.

    PAIRS:
      1. SPX500USD / NAS100USD  (US index pair, high correlation ~0.95)
      2. WTICOUSD / BCOUSD      (crude oil pair, ~0.98 correlation)
      3. XAUUSD / XAGUSD        (gold/silver ratio, classic mean-revert)
      4. USB10YUSD / USB30YUSD  (yield curve pair)

    METHOD:
      - Calculate log ratio of pair prices
      - Z-score using rolling 60-day mean and std dev
      - Enter LONG spread when z < -entry_z (ratio is cheap)
      - Enter SHORT spread when z > +entry_z (ratio is rich)
      - Exit at z = 0 (mean) or at stop_z (blowout)
      - Time stop: max_hold_days

    RISK:
      - 1.0% per pair trade
      - Max 3 pair positions simultaneously
      - DD throttle at 5%
      - Daily loss limit 2%

    FREE PARAMETERS (5):
      P1: entry_z       (z-score entry threshold)
      P2: exit_z        (z-score exit threshold)
      P3: stop_z        (z-score stop loss)
      P4: lookback      (rolling window for mean/std)
      P5: risk_pct      (risk per trade)
    """

    VERSION = "SA-V1.0"

    def Initialize(self):
        start_year = int(self.GetParameter("start_year", 2010))
        end_year = int(self.GetParameter("end_year", 2020))
        end_month = int(self.GetParameter("end_month", 12))
        self.SetStartDate(start_year, 1, 1)
        self.SetEndDate(end_year, end_month, 28)
        self.SetCash(10000)
        self.SetBrokerageModel(BrokerageName.OandaBrokerage, AccountType.Margin)

        # -- Free parameters (5) --
        self.entry_z = float(self.GetParameter("entry_z", 2.0))          # P1
        self.exit_z = float(self.GetParameter("exit_z", 0.5))            # P2
        self.stop_z = float(self.GetParameter("stop_z", 3.5))            # P3
        self.lookback = int(self.GetParameter("lookback", 60))           # P4
        self.risk_per_trade = float(self.GetParameter("risk_pct", 0.01)) # P5

        # -- Fixed parameters --
        self.max_positions = 3
        self.max_hold_days = 15
        self.dd_threshold = 0.05
        self.risk_reduced = 0.005
        self.max_daily_loss = 0.02
        self.reentry_cooldown_hours = 24

        # -- Pair definitions --
        # Each pair: (leg_a, leg_b, name)
        # LONG spread = long A, short B
        # SHORT spread = short A, long B
        self.pair_defs = [
            ("SPX500USD", "NAS100USD", "SPX_NAS"),
            ("WTICOUSD", "BCOUSD", "WTI_BCO"),
            ("XAUUSD", "XAGUSD", "XAU_XAG"),
            ("USB10YUSD", "USB30YUSD", "US10_US30"),
        ]

        self.symbols = {}
        for ticker in set(t for pd in self.pair_defs for t in [pd[0], pd[1]]):
            cfd = self.AddCfd(ticker, Resolution.Hour, Market.Oanda)
            cfd.SetLeverage(20)
            self.symbols[ticker] = cfd.Symbol

        # -- Per-pair state --
        self.pairs = {}
        for leg_a, leg_b, name in self.pair_defs:
            self.pairs[name] = {
                "leg_a": leg_a,
                "leg_b": leg_b,
                "sym_a": self.symbols[leg_a],
                "sym_b": self.symbols[leg_b],
                "ratio_history": [],       # rolling log-ratio values
                "position": 0,             # +1 long spread, -1 short spread, 0 flat
                "entry_time": None,
                "entry_z": 0.0,
                "entry_prices": (0, 0),
                "last_exit_time": None,
            }

        # -- Portfolio tracking --
        self.peak_equity = self.Portfolio.TotalPortfolioValue
        self.daily_start_equity = self.Portfolio.TotalPortfolioValue
        self.last_date = None
        self.is_throttled = False

        # Schedule daily checks
        self.Schedule.On(
            self.DateRules.EveryDay(),
            self.TimeRules.At(0, 5),
            self.DailyReset
        )

        # Schedule Friday liquidation for weekend risk
        self.Schedule.On(
            self.DateRules.Every(DayOfWeek.Friday),
            self.TimeRules.At(16, 50),
            self.FridayLiquidate
        )

        self.SetWarmUp(timedelta(days=self.lookback + 30))

    def DailyReset(self):
        self.daily_start_equity = self.Portfolio.TotalPortfolioValue
        equity = self.Portfolio.TotalPortfolioValue
        if equity > self.peak_equity:
            self.peak_equity = equity
        dd = (self.peak_equity - equity) / self.peak_equity if self.peak_equity > 0 else 0
        self.is_throttled = dd > self.dd_threshold

    def FridayLiquidate(self):
        """Close all positions before weekend."""
        for name, pair in self.pairs.items():
            if pair["position"] != 0:
                self.ClosePair(name, "weekend_close")

    def OnData(self, data):
        if self.IsWarmingUp:
            return

        # Daily loss check
        current_equity = self.Portfolio.TotalPortfolioValue
        if self.daily_start_equity > 0:
            daily_loss = (self.daily_start_equity - current_equity) / self.daily_start_equity
            if daily_loss > self.max_daily_loss:
                for name, pair in self.pairs.items():
                    if pair["position"] != 0:
                        self.ClosePair(name, "daily_loss_limit")
                return

        # Update ratios and check signals for each pair
        for name, pair in self.pairs.items():
            sym_a = pair["sym_a"]
            sym_b = pair["sym_b"]

            # Get current prices
            if not (data.ContainsKey(sym_a) and data.ContainsKey(sym_b)):
                continue

            bar_a = data[sym_a]
            bar_b = data[sym_b]
            if bar_a is None or bar_b is None:
                continue

            # For CFDs, use Close from QuoteBar
            price_a = self.GetClosePrice(bar_a)
            price_b = self.GetClosePrice(bar_b)

            if price_a is None or price_b is None or price_a <= 0 or price_b <= 0:
                continue

            # Calculate log ratio
            log_ratio = math.log(price_a / price_b)
            pair["ratio_history"].append(log_ratio)

            # Keep only lookback + buffer
            max_len = self.lookback + 10
            if len(pair["ratio_history"]) > max_len:
                pair["ratio_history"] = pair["ratio_history"][-max_len:]

            # Need enough history
            if len(pair["ratio_history"]) < self.lookback:
                continue

            # Calculate z-score
            window = pair["ratio_history"][-self.lookback:]
            mean_r = sum(window) / len(window)
            variance = sum((x - mean_r) ** 2 for x in window) / len(window)
            std_r = math.sqrt(variance) if variance > 0 else 0

            if std_r < 1e-10:
                continue

            z = (log_ratio - mean_r) / std_r

            # -- Manage existing position --
            if pair["position"] != 0:
                self.ManagePosition(name, pair, z, price_a, price_b)

            # -- Check for new entry --
            elif pair["position"] == 0:
                self.CheckEntry(name, pair, z, price_a, price_b)

    def GetClosePrice(self, bar):
        """Extract close price from TradeBar or QuoteBar."""
        if hasattr(bar, "Close") and bar.Close > 0:
            return float(bar.Close)
        if hasattr(bar, "Bid") and bar.Bid is not None and hasattr(bar.Bid, "Close"):
            bid = float(bar.Bid.Close) if bar.Bid.Close > 0 else 0
            ask = float(bar.Ask.Close) if bar.Ask is not None and bar.Ask.Close > 0 else 0
            if bid > 0 and ask > 0:
                return (bid + ask) / 2.0
            return bid if bid > 0 else ask
        return None

    def CheckEntry(self, name, pair, z, price_a, price_b):
        """Check if we should enter a new pair trade."""
        # Cooldown check
        if pair["last_exit_time"] is not None:
            hours_since = (self.Time - pair["last_exit_time"]).total_seconds() / 3600
            if hours_since < self.reentry_cooldown_hours:
                return

        # Count active positions
        active = sum(1 for p in self.pairs.values() if p["position"] != 0)
        if active >= self.max_positions:
            return

        # Throttle check
        risk = self.risk_reduced if self.is_throttled else self.risk_per_trade

        direction = 0
        if z < -self.entry_z:
            direction = 1   # Long spread: ratio is cheap, buy A sell B
        elif z > self.entry_z:
            direction = -1  # Short spread: ratio is rich, sell A buy B

        if direction == 0:
            return

        # Size the trade based on risk
        equity = self.Portfolio.TotalPortfolioValue
        risk_amount = equity * risk

        # Use the z-score distance to stop as risk measure
        z_risk = abs(self.stop_z - abs(z))
        if z_risk <= 0:
            return

        # Approximate dollar risk: we need to estimate how much the spread moves per z
        # Use std of ratio * prices as proxy
        window = pair["ratio_history"][-self.lookback:]
        mean_r = sum(window) / len(window)
        variance = sum((x - mean_r) ** 2 for x in window) / len(window)
        std_r = math.sqrt(variance) if variance > 0 else 0.01

        # Dollar value per z-unit approximately = std_r * notional
        # We want: qty * std_r * z_risk * price ~= risk_amount
        # For simplicity, size each leg as fraction of equity
        notional_per_leg = risk_amount / (z_risk * std_r) if (z_risk * std_r) > 0 else 0

        # Cap notional at 25% of equity per leg
        max_notional = equity * 0.25
        notional_per_leg = min(notional_per_leg, max_notional)

        if notional_per_leg < 100:
            return

        qty_a = notional_per_leg / price_a
        qty_b = notional_per_leg / price_b

        # Minimum quantity check
        if qty_a < 0.01 or qty_b < 0.01:
            return

        # Round quantities
        qty_a = round(qty_a, 2)
        qty_b = round(qty_b, 2)

        # Execute pair trade
        if direction == 1:  # Long spread: buy A, sell B
            self.MarketOrder(pair["sym_a"], qty_a)
            self.MarketOrder(pair["sym_b"], -qty_b)
        else:  # Short spread: sell A, buy B
            self.MarketOrder(pair["sym_a"], -qty_a)
            self.MarketOrder(pair["sym_b"], qty_b)

        pair["position"] = direction
        pair["entry_time"] = self.Time
        pair["entry_z"] = z
        pair["entry_prices"] = (price_a, price_b)

        if self.is_throttled:
            self.Debug(f"[{self.VERSION}] {name} THROTTLED entry dir={direction} z={z:.2f}")

    def ManagePosition(self, name, pair, z, price_a, price_b):
        """Manage an existing pair position."""
        direction = pair["position"]
        should_close = False
        reason = ""

        # 1. Mean reversion exit: z crosses exit threshold toward zero
        if direction == 1 and z >= -self.exit_z:
            should_close = True
            reason = f"mean_revert z={z:.2f}"
        elif direction == -1 and z <= self.exit_z:
            should_close = True
            reason = f"mean_revert z={z:.2f}"

        # 2. Stop loss: z blows out further
        if direction == 1 and z < -self.stop_z:
            should_close = True
            reason = f"stop_loss z={z:.2f}"
        elif direction == -1 and z > self.stop_z:
            should_close = True
            reason = f"stop_loss z={z:.2f}"

        # 3. Time stop
        if pair["entry_time"] is not None:
            days_held = (self.Time - pair["entry_time"]).total_seconds() / 86400
            if days_held > self.max_hold_days:
                should_close = True
                reason = f"time_stop days={days_held:.1f}"

        if should_close:
            self.ClosePair(name, reason)

    def ClosePair(self, name, reason):
        """Close both legs of a pair trade."""
        pair = self.pairs[name]
        sym_a = pair["sym_a"]
        sym_b = pair["sym_b"]

        # Liquidate both legs
        if self.Portfolio[sym_a].Quantity != 0:
            self.Liquidate(sym_a)
        if self.Portfolio[sym_b].Quantity != 0:
            self.Liquidate(sym_b)

        pair["position"] = 0
        pair["entry_time"] = None
        pair["last_exit_time"] = self.Time

    def OnEndOfAlgorithm(self):
        equity = self.Portfolio.TotalPortfolioValue
        self.Debug(f"[{self.VERSION}] Final equity: ${equity:.2f}")
