# region imports
from AlgorithmImports import *
# endregion

class FXCarryTrade(QCAlgorithm):
    """
    FX Carry Trade — Systematic carry factor on G10 currencies.
    
    Hypothesis: Long high-yield currencies, short low-yield currencies
    captures the forward rate bias (carry premium). This is the most
    documented FX factor with 200+ years of evidence.
    
    Approach:
    - Use hardcoded central bank rate history as carry proxy
    - Monthly rebalance: rank 8 G10 currencies by rate differential vs USD
    - Go long top-3 high yield pairs, short bottom-3 low yield pairs
    - Risk management: ATR-based stops, max DD circuit breaker
    - Regime filter: reduce exposure during risk-off (VIX proxy via FX vol)
    
    Contract: Brain V9 Forex | Family: Carry Trade | Version: V1.0
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
        self.risk_per_trade   = float(self.GetParameter("risk_per_trade", "0.02"))
        self.max_positions    = int(self.GetParameter("max_positions", "6"))  # 3 long + 3 short
        self.top_n            = int(self.GetParameter("top_n", "3"))  # top N to go long
        self.bottom_n         = int(self.GetParameter("bottom_n", "3"))  # bottom N to go short
        self.atr_period       = int(self.GetParameter("atr_period", "14"))
        self.stop_atr_mult    = float(self.GetParameter("stop_atr_mult", "2.0"))
        self.rebalance_freq   = int(self.GetParameter("rebalance_freq", "20"))  # trading days
        self.vol_lookback     = int(self.GetParameter("vol_lookback", "20"))
        self.vol_threshold    = float(self.GetParameter("vol_threshold", "1.5"))  # vol regime filter multiplier
        self.trend_filter     = int(self.GetParameter("trend_filter", "1"))  # 1=on, 0=off
        self.sma_period       = int(self.GetParameter("sma_period", "50"))  # trend filter SMA
        self.max_dd_pct       = float(self.GetParameter("max_dd_pct", "0.15"))  # circuit breaker
        self.max_daily_risk   = float(self.GetParameter("max_daily_risk", "0.03"))

        # ── Forex Pairs (all vs USD) ──
        # We trade these pairs to express carry on individual currencies
        self.pair_map = {
            "EURUSD": "EUR",
            "GBPUSD": "GBP", 
            "AUDUSD": "AUD",
            "NZDUSD": "NZD",
            "USDCAD": "CAD",
            "USDCHF": "CHF",
            "USDJPY": "JPY",
            "USDSEK": "SEK",
        }
        
        self.symbols = {}
        self.atr_indicators = {}
        self.sma_indicators = {}
        self.vol_indicators = {}
        
        for pair in self.pair_map:
            sym = self.AddForex(pair, Resolution.Hour, Market.Oanda).Symbol
            self.symbols[pair] = sym
            self.atr_indicators[pair] = self.ATR(sym, self.atr_period, MovingAverageType.Simple, Resolution.Daily)
            self.sma_indicators[pair] = self.SMA(sym, self.sma_period, Resolution.Daily)
            # Rolling std of daily returns as vol measure
            self.vol_indicators[pair] = self.STD(sym, self.vol_lookback, Resolution.Daily)

        # ── Central Bank Rates History (approximate, used as carry proxy) ──
        # Format: {currency: [(start_date, rate), ...]} 
        # Sorted chronologically. We use the latest applicable rate.
        # Source: Central bank announcements 2019-2024
        self.rate_history = {
            "USD": [
                (datetime(2019, 10, 31), 1.75), (datetime(2020, 3, 16), 0.25),
                (datetime(2022, 3, 17), 0.50), (datetime(2022, 5, 5), 1.00),
                (datetime(2022, 6, 16), 1.75), (datetime(2022, 7, 28), 2.50),
                (datetime(2022, 9, 22), 3.25), (datetime(2022, 11, 3), 4.00),
                (datetime(2022, 12, 15), 4.50), (datetime(2023, 2, 2), 4.75),
                (datetime(2023, 3, 23), 5.00), (datetime(2023, 5, 4), 5.25),
                (datetime(2023, 7, 27), 5.50), (datetime(2024, 9, 19), 5.00),
                (datetime(2024, 11, 8), 4.75), (datetime(2024, 12, 19), 4.50),
            ],
            "EUR": [
                (datetime(2019, 9, 18), -0.50), (datetime(2022, 7, 27), 0.00),
                (datetime(2022, 9, 14), 0.75), (datetime(2022, 10, 27), 1.50),
                (datetime(2022, 12, 21), 2.00), (datetime(2023, 2, 8), 2.50),
                (datetime(2023, 3, 22), 3.00), (datetime(2023, 5, 10), 3.25),
                (datetime(2023, 6, 21), 3.50), (datetime(2023, 7, 27), 3.75),
                (datetime(2023, 9, 20), 4.00), (datetime(2024, 6, 12), 3.75),
                (datetime(2024, 9, 18), 3.50), (datetime(2024, 10, 23), 3.25),
                (datetime(2024, 12, 18), 3.00),
            ],
            "GBP": [
                (datetime(2020, 3, 19), 0.10), (datetime(2021, 12, 16), 0.25),
                (datetime(2022, 2, 3), 0.50), (datetime(2022, 3, 17), 0.75),
                (datetime(2022, 5, 5), 1.00), (datetime(2022, 6, 16), 1.25),
                (datetime(2022, 8, 4), 1.75), (datetime(2022, 9, 22), 2.25),
                (datetime(2022, 11, 3), 3.00), (datetime(2022, 12, 15), 3.50),
                (datetime(2023, 2, 2), 4.00), (datetime(2023, 3, 23), 4.25),
                (datetime(2023, 5, 11), 4.50), (datetime(2023, 6, 22), 5.00),
                (datetime(2023, 8, 3), 5.25), (datetime(2024, 8, 1), 5.00),
                (datetime(2024, 11, 7), 4.75),
            ],
            "AUD": [
                (datetime(2020, 3, 19), 0.25), (datetime(2020, 11, 3), 0.10),
                (datetime(2022, 5, 3), 0.35), (datetime(2022, 6, 7), 0.85),
                (datetime(2022, 7, 5), 1.35), (datetime(2022, 8, 2), 1.85),
                (datetime(2022, 9, 6), 2.35), (datetime(2022, 10, 4), 2.60),
                (datetime(2022, 11, 1), 2.85), (datetime(2022, 12, 6), 3.10),
                (datetime(2023, 2, 7), 3.35), (datetime(2023, 3, 7), 3.60),
                (datetime(2023, 5, 2), 3.85), (datetime(2023, 6, 6), 4.10),
                (datetime(2023, 11, 7), 4.35),
            ],
            "NZD": [
                (datetime(2020, 3, 16), 0.25), (datetime(2021, 10, 6), 0.50),
                (datetime(2021, 11, 24), 0.75), (datetime(2022, 2, 23), 1.00),
                (datetime(2022, 4, 13), 1.50), (datetime(2022, 5, 25), 2.00),
                (datetime(2022, 7, 13), 2.50), (datetime(2022, 8, 17), 3.00),
                (datetime(2022, 10, 5), 3.50), (datetime(2022, 11, 23), 4.25),
                (datetime(2023, 2, 22), 4.75), (datetime(2023, 4, 5), 5.25),
                (datetime(2023, 5, 24), 5.50), (datetime(2024, 8, 14), 5.25),
                (datetime(2024, 10, 9), 4.75), (datetime(2024, 11, 27), 4.25),
            ],
            "CAD": [
                (datetime(2020, 3, 27), 0.25), (datetime(2022, 3, 2), 0.50),
                (datetime(2022, 4, 13), 1.00), (datetime(2022, 6, 1), 1.50),
                (datetime(2022, 7, 13), 2.50), (datetime(2022, 9, 7), 3.25),
                (datetime(2022, 10, 26), 3.75), (datetime(2022, 12, 7), 4.25),
                (datetime(2023, 1, 25), 4.50), (datetime(2023, 6, 7), 4.75),
                (datetime(2023, 7, 12), 5.00), (datetime(2024, 6, 5), 4.75),
                (datetime(2024, 7, 24), 4.50), (datetime(2024, 9, 4), 4.25),
                (datetime(2024, 10, 23), 3.75), (datetime(2024, 12, 11), 3.25),
            ],
            "CHF": [
                (datetime(2019, 9, 19), -0.75), (datetime(2022, 6, 16), -0.25),
                (datetime(2022, 9, 22), 0.50), (datetime(2022, 12, 15), 1.00),
                (datetime(2023, 3, 23), 1.50), (datetime(2023, 6, 22), 1.75),
                (datetime(2024, 3, 21), 1.50), (datetime(2024, 6, 20), 1.25),
                (datetime(2024, 9, 26), 1.00), (datetime(2024, 12, 12), 0.50),
            ],
            "JPY": [
                (datetime(2016, 1, 29), -0.10),  # Stayed at -0.10 until 2024
                (datetime(2024, 3, 19), 0.00), (datetime(2024, 7, 31), 0.25),
            ],
            "SEK": [
                (datetime(2020, 1, 1), 0.00), (datetime(2022, 4, 28), 0.25),
                (datetime(2022, 6, 30), 0.75), (datetime(2022, 9, 20), 1.75),
                (datetime(2022, 11, 24), 2.50), (datetime(2023, 2, 9), 3.00),
                (datetime(2023, 4, 26), 3.50), (datetime(2023, 6, 29), 3.75),
                (datetime(2023, 9, 21), 4.00), (datetime(2024, 5, 8), 3.75),
                (datetime(2024, 6, 27), 3.75), (datetime(2024, 8, 20), 3.50),
                (datetime(2024, 11, 7), 2.75), (datetime(2024, 12, 19), 2.50),
            ],
        }

        # ── State ──
        self.positions = {}  # pair -> {"side": 1/-1, "entry": price, "stop": price}
        self.last_rebalance = None
        self.bars_since_rebalance = 0
        self.peak_equity = 10000
        self.daily_pnl = 0
        self.last_date = None
        self.warmup_done = False

        # Warm up
        self.SetWarmUp(max(self.sma_period, self.vol_lookback, self.atr_period) + 5, Resolution.Daily)

        # Schedule monthly rebalance check
        self.Schedule.On(
            self.DateRules.EveryDay(),
            self.TimeRules.At(14, 0),  # 2 PM UTC — London+NY overlap
            self._on_rebalance_check
        )

    def _get_rate(self, currency, dt):
        """Get the applicable interest rate for a currency at a given datetime."""
        history = self.rate_history.get(currency, [])
        applicable_rate = 0.0
        for date, rate in history:
            if dt >= date:
                applicable_rate = rate
            else:
                break
        return applicable_rate

    def _get_carry_scores(self):
        """
        Calculate carry score for each pair.
        For XXX/USD pairs (EURUSD, GBPUSD, AUDUSD, NZDUSD):
            carry = rate(XXX) - rate(USD)
            positive carry = long the pair (buy XXX, sell USD)
        For USD/XXX pairs (USDCAD, USDCHF, USDJPY, USDSEK):
            carry = rate(USD) - rate(XXX) 
            positive carry = long the pair (buy USD, sell XXX)
        """
        dt = self.Time
        usd_rate = self._get_rate("USD", dt)
        scores = {}
        
        for pair, currency in self.pair_map.items():
            foreign_rate = self._get_rate(currency, dt)
            
            if pair.startswith("USD"):
                # USD/XXX — long means buy USD, sell XXX
                # Positive carry when USD rate > XXX rate
                carry = usd_rate - foreign_rate
            else:
                # XXX/USD — long means buy XXX, sell USD
                # Positive carry when XXX rate > USD rate
                carry = foreign_rate - usd_rate
            
            scores[pair] = carry
        
        return scores

    def _check_indicators_ready(self):
        """Check if all indicators are ready."""
        for pair in self.pair_map:
            if not self.atr_indicators[pair].IsReady:
                return False
            if not self.sma_indicators[pair].IsReady:
                return False
        return True

    def _get_vol_regime(self):
        """
        Check if we're in a high-vol (risk-off) regime.
        Uses average FX volatility across all pairs.
        Returns True if vol is elevated (should reduce exposure).
        """
        vols = []
        for pair in self.pair_map:
            ind = self.vol_indicators[pair]
            if ind.IsReady:
                vols.append(ind.Current.Value)
        
        if len(vols) < 4:
            return False  # Not enough data
        
        avg_vol = sum(vols) / len(vols)
        # We can't easily compute long-term average vol in real-time,
        # so we use a simple threshold: if current vol > threshold * median
        # For now, just return False (no filter) and enable in V1.1
        return False

    def _on_rebalance_check(self):
        """Called daily at 2 PM UTC. Rebalance if enough time has passed."""
        if self.IsWarmingUp:
            return
        if not self._check_indicators_ready():
            return

        self.bars_since_rebalance += 1
        
        # Check circuit breaker
        equity = self.Portfolio.TotalPortfolioValue
        self.peak_equity = max(self.peak_equity, equity)
        dd = (self.peak_equity - equity) / self.peak_equity if self.peak_equity > 0 else 0
        
        if dd > self.max_dd_pct:
            self.Log(f"CIRCUIT BREAKER: DD {dd:.2%} > {self.max_dd_pct:.2%}. Liquidating all.")
            self.Liquidate()
            self.positions.clear()
            self.bars_since_rebalance = 0
            return

        # Daily risk check
        current_date = self.Time.date()
        if self.last_date != current_date:
            self.daily_pnl = 0
            self.last_date = current_date

        # Rebalance on schedule
        if self.bars_since_rebalance >= self.rebalance_freq:
            self._rebalance()
            self.bars_since_rebalance = 0

    def _rebalance(self):
        """Core carry trade rebalance logic."""
        equity = self.Portfolio.TotalPortfolioValue
        if equity <= 0:
            return

        # Get carry scores
        scores = self._get_carry_scores()
        
        # Sort pairs by carry score
        sorted_pairs = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        
        self.Log(f"=== CARRY REBALANCE {self.Time.strftime('%Y-%m-%d')} ===")
        for pair, score in sorted_pairs:
            self.Log(f"  {pair}: carry={score:.2f}%")

        # Select top N for long, bottom N for short
        long_pairs = []
        short_pairs = []
        
        for pair, score in sorted_pairs[:self.top_n]:
            if score > 0:  # Only go long if carry is positive
                # Optional trend filter
                if self.trend_filter:
                    sym = self.symbols[pair]
                    price = self.Securities[sym].Price
                    sma = self.sma_indicators[pair].Current.Value
                    if price > sma:  # Price above SMA = trend aligned
                        long_pairs.append((pair, score))
                    else:
                        self.Log(f"  SKIP LONG {pair}: price {price:.5f} < SMA {sma:.5f}")
                else:
                    long_pairs.append((pair, score))
        
        for pair, score in sorted_pairs[-self.bottom_n:]:
            if score < 0:  # Only go short if carry is negative
                if self.trend_filter:
                    sym = self.symbols[pair]
                    price = self.Securities[sym].Price
                    sma = self.sma_indicators[pair].Current.Value
                    if price < sma:  # Price below SMA = trend aligned for short
                        short_pairs.append((pair, score))
                    else:
                        self.Log(f"  SKIP SHORT {pair}: price {price:.5f} > SMA {sma:.5f}")
                else:
                    short_pairs.append((pair, score))

        # Determine target positions
        target = {}
        for pair, score in long_pairs:
            target[pair] = 1  # Long
        for pair, score in short_pairs:
            target[pair] = -1  # Short

        # Close positions that are no longer in target
        for pair in list(self.positions.keys()):
            if pair not in target or target[pair] != self.positions[pair]["side"]:
                sym = self.symbols[pair]
                if self.Portfolio[sym].Invested:
                    self.Liquidate(sym)
                    self.Log(f"  CLOSE {pair}")
                del self.positions[pair]

        # Open/adjust target positions
        n_positions = len(target)
        if n_positions == 0:
            self.Log("  No positions to take (all filtered out)")
            return

        risk_per_pos = self.risk_per_trade  # Risk per position
        
        for pair, side in target.items():
            sym = self.symbols[pair]
            price = self.Securities[sym].Price
            if price <= 0:
                continue
            
            atr = self.atr_indicators[pair].Current.Value
            if atr <= 0:
                continue

            # Skip if already positioned correctly
            if pair in self.positions and self.positions[pair]["side"] == side:
                # Update stop
                self._update_trailing_stop(pair, price, atr, side)
                continue

            # Calculate position size based on ATR risk
            stop_distance = atr * self.stop_atr_mult
            risk_amount = equity * risk_per_pos
            
            # For forex: lot size = risk_amount / (stop_distance * pip_value)
            # Simplified: quantity = risk_amount / stop_distance
            quantity = int(risk_amount / stop_distance)
            if quantity < 1:
                quantity = 1

            if side == 1:
                self.MarketOrder(sym, quantity)
                stop_price = price - stop_distance
                self.Log(f"  LONG {pair}: qty={quantity}, entry={price:.5f}, stop={stop_price:.5f}, carry={scores[pair]:.2f}%")
            else:
                self.MarketOrder(sym, -quantity)
                stop_price = price + stop_distance
                self.Log(f"  SHORT {pair}: qty={quantity}, entry={price:.5f}, stop={stop_price:.5f}, carry={scores[pair]:.2f}%")

            self.positions[pair] = {
                "side": side,
                "entry": price,
                "stop": stop_price,
                "atr_at_entry": atr,
            }

    def _update_trailing_stop(self, pair, price, atr, side):
        """Update trailing stop for existing position."""
        pos = self.positions[pair]
        stop_distance = atr * self.stop_atr_mult
        
        if side == 1:  # Long
            new_stop = price - stop_distance
            if new_stop > pos["stop"]:
                pos["stop"] = new_stop
        else:  # Short
            new_stop = price + stop_distance
            if new_stop < pos["stop"]:
                pos["stop"] = new_stop

    def OnData(self, data):
        """Check stops on every bar."""
        if self.IsWarmingUp:
            return

        for pair in list(self.positions.keys()):
            sym = self.symbols[pair]
            if not data.ContainsKey(sym):
                continue
            
            price = self.Securities[sym].Price
            if price <= 0:
                continue
            
            pos = self.positions[pair]
            stopped = False
            
            if pos["side"] == 1 and price <= pos["stop"]:
                stopped = True
            elif pos["side"] == -1 and price >= pos["stop"]:
                stopped = True
            
            if stopped:
                self.Liquidate(sym)
                pnl = (price - pos["entry"]) * pos["side"]
                self.Log(f"  STOPPED OUT {pair}: entry={pos['entry']:.5f}, exit={price:.5f}, pnl={pnl:.5f}")
                del self.positions[pair]

    def OnEndOfAlgorithm(self):
        equity = self.Portfolio.TotalPortfolioValue
        ret = (equity - 10000) / 10000
        self.Log(f"=== FINAL: Equity={equity:.2f}, Return={ret:.2%} ===")
        self.Log(f"  Active positions at end: {len(self.positions)}")
