# region imports
from AlgorithmImports import *
from collections import deque
from datetime import timedelta
import math
# endregion


class FusionV1(QCAlgorithm):
    """
    Fusion of Yoel V2.0b (CALL swing on AAPL/QQQ) and Brain V10.13b
    (NVDA equity + SPY PCS + Bear Puts).
    """

    # ── Lifecycle ──────────────────────────────────────────────────────

    def Initialize(self):
        # ── Parameters ────────────────────────────────────────────────
        start_year  = int(self.GetParameter("start_year")  or 2023)
        end_year    = int(self.GetParameter("end_year")    or 2024)
        end_month   = int(self.GetParameter("end_month")   or 12)

        self.SetStartDate(start_year, 1, 1)
        self.SetEndDate(end_year, end_month, 28)
        self.SetCash(10_000)
        self.SetBrokerageModel(BrokerageName.InteractiveBrokersBrokerage,
                               AccountType.Margin)

        # ── Capital splits ────────────────────────────────────────────
        self.TOTAL_CAPITAL     = 10_000
        self.YOEL_ALLOC_PCT    = 0.40   # $4,000
        self.BRAIN_ALLOC_PCT   = 0.60   # $6,000

        # ── Equities ─────────────────────────────────────────────────
        self.spy   = self.AddEquity("SPY",  Resolution.Minute).Symbol
        self.aapl  = self.AddEquity("AAPL", Resolution.Minute).Symbol
        self.qqq   = self.AddEquity("QQQ",  Resolution.Minute).Symbol
        self.nvda  = self.AddEquity("NVDA", Resolution.Minute).Symbol

        for sym in [self.spy, self.aapl, self.qqq, self.nvda]:
            self.Securities[sym].SetDataNormalizationMode(
                DataNormalizationMode.Raw)

        # ── Options ──────────────────────────────────────────────────
        # Yoel needs options on AAPL, QQQ
        for eq_sym in [self.aapl, self.qqq]:
            opt = self.AddOption(eq_sym.Value, Resolution.Minute)
            opt.SetFilter(lambda u: u.Strikes(-5, 5)
                                     .Expiration(3, 45))

        # Brain needs options on SPY (for PCS and bear puts)
        spy_opt = self.AddOption("SPY", Resolution.Minute)
        spy_opt.SetFilter(lambda u: u.Strikes(-15, 15)
                                     .Expiration(7, 50))

        # ── VIX (estimated from SPY 20d realized vol) ──────────────
        self.vix_symbol = None  # No CBOE module; use _get_vix() estimation

        # ── Indicators ───────────────────────────────────────────────
        # SPY indicators (shared)
        self.spy_sma20  = self.SMA(self.spy, 20, Resolution.Daily)
        self.spy_sma40  = self.SMA(self.spy, 40, Resolution.Daily)
        self.spy_sma50  = self.SMA(self.spy, 50, Resolution.Daily)
        self.spy_sma200 = self.SMA(self.spy, 200, Resolution.Daily)

        # NVDA EMA20
        self.nvda_ema20 = self.EMA(self.nvda, 20, Resolution.Daily)

        # Yoel: per-ticker indicators
        self.yoel_sma20 = {}
        self.yoel_bb    = {}
        for sym in [self.aapl, self.qqq]:
            self.yoel_sma20[sym] = self.SMA(sym, 20, Resolution.Daily)
            self.yoel_bb[sym]    = self.BB(sym, 20, 2.0, MovingAverageType.Simple, Resolution.Daily)

        # ── Warm-up ──────────────────────────────────────────────────
        self.SetWarmUp(210, Resolution.Daily)

        # ── Option chain caches ──────────────────────────────────────
        self._chain_cache = {}   # canonical → OptionChain

        # ════════════════════════════════════════════════════════════
        # YOEL STATE
        # ════════════════════════════════════════════════════════════
        self._yoel_positions     = {}        # sym → contract Symbol
        self._yoel_entry_time    = {}        # sym → datetime
        self._yoel_entry_price   = {}        # sym → float
        self._yoel_trades_week   = deque()   # timestamps
        self._yoel_loss_log      = deque()   # (date, ticker)
        self._yoel_cooldown      = {}        # ticker → unblock date
        self._yoel_daily_loss    = False
        self._yoel_peak_equity   = self.TOTAL_CAPITAL * self.YOEL_ALLOC_PCT
        self._yoel_touch_count   = {}        # sym → int (touches of SMA20)

        # ════════════════════════════════════════════════════════════
        # BRAIN STATE
        # ════════════════════════════════════════════════════════════
        self._brain_regime          = "SIDEWAYS"
        self._brain_regime_pending  = None
        self._brain_regime_counter  = 0

        # NVDA equity
        self._nvda_target_shares    = 0
        self._nvda_below_ema_days   = 0
        self._nvda_is_out           = False

        # PCS tracking
        self._pcs_spreads      = {}   # id → dict
        self._pcs_id_counter   = 0
        self._pcs_cooldown_end = self.StartDate

        # Bear puts
        self._bear_puts        = {}   # id → dict
        self._bear_put_id      = 0

        self._brain_peak_equity = self.TOTAL_CAPITAL * self.BRAIN_ALLOC_PCT

        # ── Schedules ────────────────────────────────────────────────
        self.Schedule.On(self.DateRules.EveryDay(self.spy),
                         self.TimeRules.AfterMarketOpen(self.spy, 1),
                         self._morning_scan)

        self.Schedule.On(self.DateRules.EveryDay(self.spy),
                         self.TimeRules.AfterMarketOpen(self.spy, 5),
                         self._execute_trades)

        # Manage every 5 min from open+10 to close-10
        for offset in range(10, 385, 5):
            self.Schedule.On(self.DateRules.EveryDay(self.spy),
                             self.TimeRules.AfterMarketOpen(self.spy, offset),
                             self._manage_positions)

        self.Schedule.On(self.DateRules.EveryDay(self.spy),
                         self.TimeRules.BeforeMarketClose(self.spy, 5),
                         self._eod_cleanup)

        # PCS entry: Mon-Wed at 11 AM ET
        self.Schedule.On(self.DateRules.Every(DayOfWeek.Monday,
                                              DayOfWeek.Tuesday,
                                              DayOfWeek.Wednesday),
                         self.TimeRules.At(11, 0),
                         self._brain_pcs_entry_check)

        # Daily reset
        self.Schedule.On(self.DateRules.EveryDay(self.spy),
                         self.TimeRules.AfterMarketOpen(self.spy, 0),
                         self._daily_reset)

    # ── OnData ────────────────────────────────────────────────────────

    def OnData(self, data: Slice):
        if self.IsWarmingUp:
            return

        # Cache option chains for later use
        for kvp in data.OptionChains:
            canonical = kvp.Key
            self._chain_cache[canonical] = kvp.Value

    # ── OnEndOfAlgorithm ──────────────────────────────────────────────

    def OnEndOfAlgorithm(self):
        self.Liquidate()
        self.Log("[FUSION] OnEndOfAlgorithm — all positions liquidated.")

    # ══════════════════════════════════════════════════════════════════
    #  SHARED HELPERS
    # ══════════════════════════════════════════════════════════════════

    def _daily_reset(self):
        """Reset per-day flags at market open."""
        self._yoel_daily_loss = False

    def _get_vix(self):
        """Estimate VIX from SPY 20-day realized volatility, annualized.
        Approximation: realized_vol * sqrt(252) * 100 ≈ VIX.
        Falls back to 20.0 if not enough data."""
        try:
            hist = self.History(self.spy, 21, Resolution.Daily)
            if hist is not None and not hist.empty:
                closes = hist["close"].values
                if len(closes) >= 2:
                    import numpy as np
                    returns = np.diff(np.log(closes))
                    rv = float(np.std(returns) * math.sqrt(252) * 100)
                    if rv > 0:
                        return rv
        except Exception:
            pass
        return 20.0

    def _get_spy_direction_yoel(self):
        """Yoel's SPY filter: BULL / FLAT / BEAR via SMA20/SMA40."""
        if not (self.spy_sma20.IsReady and self.spy_sma40.IsReady):
            return "FLAT"
        price = self.Securities[self.spy].Price
        s20 = self.spy_sma20.Current.Value
        s40 = self.spy_sma40.Current.Value
        if price > s20 and s20 > s40:
            return "BULL"
        elif price < s20 and s20 < s40:
            return "BEAR"
        return "FLAT"

    def _get_brain_regime(self):
        """Brain regime with 5-day confirmation."""
        if not (self.spy_sma50.IsReady and self.spy_sma200.IsReady):
            return self._brain_regime
        price = self.Securities[self.spy].Price
        s50   = self.spy_sma50.Current.Value
        s200  = self.spy_sma200.Current.Value

        if s50 > s200 and price > s50:
            raw = "BULL"
        elif s50 < s200 and price < s50:
            raw = "BEAR"
        else:
            raw = "SIDEWAYS"

        if raw != self._brain_regime:
            if raw == self._brain_regime_pending:
                self._brain_regime_counter += 1
            else:
                self._brain_regime_pending = raw
                self._brain_regime_counter = 1

            if self._brain_regime_counter >= 5:
                old = self._brain_regime
                self._brain_regime = raw
                self._brain_regime_pending = None
                self._brain_regime_counter = 0
                self.Log(f"[BRAIN] Regime change: {old} → {raw}")
        else:
            self._brain_regime_pending = None
            self._brain_regime_counter = 0

        return self._brain_regime

    def _current_dd_pct(self, peak, alloc_pct):
        """Drawdown from peak for a given allocation slice."""
        current_equity = self.Portfolio.TotalPortfolioValue * alloc_pct
        if peak <= 0:
            return 0.0
        dd = (peak - current_equity) / peak
        return max(dd, 0.0)

    def _get_option_chain(self, underlying_symbol):
        """Retrieve cached option chain for an underlying."""
        for canonical, chain in self._chain_cache.items():
            if canonical.Underlying == underlying_symbol:
                return chain
        return None

    def _yoel_equity(self):
        return self.Portfolio.TotalPortfolioValue * self.YOEL_ALLOC_PCT

    def _brain_equity(self):
        return self.Portfolio.TotalPortfolioValue * self.BRAIN_ALLOC_PCT

    # ══════════════════════════════════════════════════════════════════
    #  MORNING SCAN — runs at open +1 min
    # ══════════════════════════════════════════════════════════════════

    def _morning_scan(self):
        if self.IsWarmingUp:
            return

        # Update peaks
        ye = self._yoel_equity()
        if ye > self._yoel_peak_equity:
            self._yoel_peak_equity = ye

        be = self._brain_equity()
        if be > self._brain_peak_equity:
            self._brain_peak_equity = be

        # Update Brain regime
        self._get_brain_regime()

        # NVDA EMA20 daily check
        self._brain_nvda_ema_check()

    # ══════════════════════════════════════════════════════════════════
    #  EXECUTE TRADES — runs at open +5 min
    # ══════════════════════════════════════════════════════════════════

    def _execute_trades(self):
        if self.IsWarmingUp:
            return

        self._yoel_scan_entries()
        self._brain_nvda_rebalance()
        self._brain_bear_put_entry()

    # ══════════════════════════════════════════════════════════════════
    #  MANAGE POSITIONS — runs every 5 min
    # ══════════════════════════════════════════════════════════════════

    def _manage_positions(self):
        if self.IsWarmingUp:
            return
        self._yoel_manage()
        self._brain_pcs_manage()
        self._brain_bear_put_manage()

    # ══════════════════════════════════════════════════════════════════
    #  EOD CLEANUP — runs at close -5 min
    # ══════════════════════════════════════════════════════════════════

    def _eod_cleanup(self):
        if self.IsWarmingUp:
            return
        # Prune old trade-week entries
        cutoff = self.Time - timedelta(days=7)
        while self._yoel_trades_week and self._yoel_trades_week[0] < cutoff:
            self._yoel_trades_week.popleft()

    # ══════════════════════════════════════════════════════════════════
    #  YOEL V2.0b — CALL Options Swing Trading
    # ══════════════════════════════════════════════════════════════════

    def _yoel_scan_entries(self):
        spy_dir = self._get_spy_direction_yoel()

        for sym in [self.aapl, self.qqq]:
            ticker = sym.Value

            # ── Guards ────────────────────────────────────────────────
            # Already holding a position on this ticker
            if sym in self._yoel_positions:
                continue

            # Max 1 total position across tickers
            if len(self._yoel_positions) >= 1:
                continue

            # Max 3 trades this week
            if len(self._yoel_trades_week) >= 3:
                continue

            # Daily circuit breaker
            if self._yoel_daily_loss:
                continue

            # Cooldown
            if ticker in self._yoel_cooldown:
                if self.Time.date() < self._yoel_cooldown[ticker]:
                    continue
                else:
                    del self._yoel_cooldown[ticker]

            # Indicators ready?
            if not (self.yoel_sma20[sym].IsReady and
                    self.yoel_bb[sym].IsReady):
                continue

            price = self.Securities[sym].Price
            if price <= 0:
                continue

            sma20 = self.yoel_sma20[sym].Current.Value
            bb    = self.yoel_bb[sym]
            upper = bb.UpperBand.Current.Value
            lower = bb.LowerBand.Current.Value

            # BB bandwidth gate: require non-zero bandwidth
            bandwidth = (upper - lower) / sma20 if sma20 > 0 else 0
            if bandwidth < 0.01:
                continue

            # PM_BOUNCE_CALL: price near SMA20 during bullish daily trend
            # "touches SMA20" = within 0.5% of SMA20
            touch_dist = abs(price - sma20) / sma20
            if touch_dist > 0.005:
                # Reset touch count if price moved away
                self._yoel_touch_count[sym] = 0
                continue

            # Increment touch count
            self._yoel_touch_count[sym] = self._yoel_touch_count.get(sym, 0) + 1

            # Need at least 1 touch (current one counts)
            if self._yoel_touch_count.get(sym, 0) < 1:
                continue

            # Price must be above SMA20 for bullish context
            if price < sma20:
                continue

            # ── Scoring ───────────────────────────────────────────────
            score = self._yoel_compute_score(sym, price, sma20, bb,
                                              spy_dir, bandwidth)

            if score < 4.0:
                continue

            # ── Confidence & Sizing ──────────────────────────────────
            dd = self._current_dd_pct(self._yoel_peak_equity,
                                       self.YOEL_ALLOC_PCT)
            confidence = self._yoel_confidence(score, spy_dir, dd)

            risk_pct   = 0.05 * confidence  # 5% base × confidence
            alloc      = self._yoel_equity()
            risk_amt   = alloc * risk_pct

            # ── Find ATM Call ────────────────────────────────────────
            chain = self._get_option_chain(sym)
            if chain is None:
                continue

            calls = [c for c in chain
                     if c.Right == OptionRight.Call
                     and 5 <= (c.Expiry - self.Time).days <= 30
                     and c.BidPrice > 0 and c.AskPrice > 0]
            if not calls:
                continue

            # ATM: closest strike to current price
            atm = min(calls, key=lambda c: abs(c.Strike - price))

            # DTE guard: need at least 3 days
            dte = (atm.Expiry - self.Time).days
            if dte < 3:
                continue

            mid_price = (atm.BidPrice + atm.AskPrice) / 2.0
            if mid_price <= 0:
                continue

            qty = max(1, int(risk_amt / (mid_price * 100)))

            # ── Execute ──────────────────────────────────────────────
            ticket = self.MarketOrder(atm.Symbol, qty)
            if ticket and ticket.Status != OrderStatus.Invalid:
                self._yoel_positions[sym]   = atm.Symbol
                self._yoel_entry_time[sym]  = self.Time
                self._yoel_entry_price[sym] = mid_price
                self._yoel_trades_week.append(self.Time)
                self._yoel_touch_count[sym] = 0

                # Place TP limit order at +35%
                tp_price = round(mid_price * 1.35, 2)
                self.LimitOrder(atm.Symbol, -qty, tp_price)

                self.Log(f"[YOEL] OPEN CALL {ticker} strike={atm.Strike} "
                         f"exp={atm.Expiry.date()} qty={qty} "
                         f"mid={mid_price:.2f} score={score:.1f} "
                         f"conf={confidence:.2f} spy={spy_dir}")

    def _yoel_compute_score(self, sym, price, sma20, bb, spy_dir, bandwidth):
        """Score 0-10 for PM_BOUNCE_CALL setup quality."""
        score = 0.0

        # Price > SMA20 = bullish
        if price > sma20:
            score += 2.0

        # SPY direction bonus
        if spy_dir == "BULL":
            score += 2.5
        elif spy_dir == "FLAT":
            score += 1.0

        # BB bandwidth: moderate is best (0.02-0.06)
        if 0.02 <= bandwidth <= 0.06:
            score += 2.0
        elif bandwidth < 0.02:
            score += 0.5

        # Touch count: first touch is strongest
        touches = self._yoel_touch_count.get(sym, 0)
        if touches == 1:
            score += 2.0
        elif touches == 2:
            score += 1.0
        else:
            score += 0.5

        # Price near lower BB = oversold bounce potential
        lower = bb.LowerBand.Current.Value
        upper = bb.UpperBand.Current.Value
        bb_range = upper - lower if upper > lower else 1
        bb_pos = (price - lower) / bb_range
        if bb_pos < 0.4:
            score += 1.5
        elif bb_pos < 0.6:
            score += 1.0

        return min(score, 10.0)

    def _yoel_confidence(self, score, spy_dir, dd):
        mult_score  = 1.25 if score >= 6.5 else (1.0 if score >= 5.0 else 0.6)
        mult_regime = 1.0 if spy_dir == "BULL" else (
                      0.75 if spy_dir == "FLAT" else 0.5)
        mult_health = 1.0 if dd < 0.15 else (0.75 if dd < 0.30 else 0.5)
        return max(0.5, min(mult_score * mult_regime * mult_health, 3.0))

    def _yoel_manage(self):
        """SL / time-stop management for Yoel positions."""
        closed = []
        for sym, contract in list(self._yoel_positions.items()):
            # Check if we still hold
            if not self.Portfolio[contract].Invested:
                # TP limit filled or assignment — record and clean up
                closed.append(sym)
                continue

            entry_price = self._yoel_entry_price.get(sym, 0)
            if entry_price <= 0:
                closed.append(sym)
                continue

            current_price = self.Securities[contract].Price
            if current_price <= 0:
                continue

            pnl_pct = (current_price - entry_price) / entry_price
            days_held = (self.Time - self._yoel_entry_time[sym]).days
            dte = (self.Securities[contract].Expiry - self.Time).days \
                  if hasattr(self.Securities[contract], 'Expiry') else 999

            # Try to get DTE from symbol ID
            try:
                dte = (contract.ID.Date - self.Time).days
            except Exception:
                pass

            should_close = False
            reason = ""

            # SL: -20%
            if pnl_pct <= -0.20:
                should_close = True
                reason = "SL -20%"

            # Time stop: 5 days
            elif days_held >= 5:
                should_close = True
                reason = f"TIME {days_held}d"

            # DTE guard: 3 days
            elif dte <= 3:
                should_close = True
                reason = f"DTE {dte}"

            if should_close:
                qty = self.Portfolio[contract].Quantity
                self.MarketOrder(contract, -qty)
                # Cancel any open TP limit
                for order in self.Transactions.GetOpenOrders(contract):
                    self.Transactions.CancelOrder(order.Id)

                is_loss = pnl_pct < 0
                self.Log(f"[YOEL] CLOSE {sym.Value} reason={reason} "
                         f"pnl={pnl_pct*100:.1f}%")

                if is_loss:
                    self._yoel_daily_loss = True
                    self._yoel_loss_log.append(
                        (self.Time.date(), sym.Value))
                    self._yoel_check_cooldown(sym.Value)

                closed.append(sym)

        for sym in closed:
            self._yoel_positions.pop(sym, None)
            self._yoel_entry_time.pop(sym, None)
            self._yoel_entry_price.pop(sym, None)

    def _yoel_check_cooldown(self, ticker):
        """2 losses in 10 days → block 10 days for that ticker."""
        cutoff = self.Time.date() - timedelta(days=10)
        recent = [d for d, t in self._yoel_loss_log
                  if t == ticker and d >= cutoff]
        if len(recent) >= 2:
            block_until = self.Time.date() + timedelta(days=10)
            self._yoel_cooldown[ticker] = block_until
            self.Log(f"[YOEL] Cooldown {ticker} until {block_until}")

        # Prune old entries
        while (self._yoel_loss_log and
               self._yoel_loss_log[0][0] < cutoff):
            self._yoel_loss_log.popleft()

    # ══════════════════════════════════════════════════════════════════
    #  BRAIN V10.13b — NVDA Equity
    # ══════════════════════════════════════════════════════════════════

    def _brain_nvda_ema_check(self):
        """Daily check: NVDA vs EMA20 sell/re-entry gate."""
        if not self.nvda_ema20.IsReady:
            return

        price = self.Securities[self.nvda].Price
        if price <= 0:
            return

        ema = self.nvda_ema20.Current.Value

        if price < ema:
            self._nvda_below_ema_days += 1
        else:
            self._nvda_below_ema_days = 0

        # 2 consecutive days below EMA20 → sell all
        if self._nvda_below_ema_days >= 2 and not self._nvda_is_out:
            if self.Portfolio[self.nvda].Invested:
                self.Liquidate(self.nvda)
                self.Log("[BRAIN] NVDA sold — 2 days below EMA20")
            self._nvda_is_out = True
            self._nvda_target_shares = 0

        # First close above EMA20 → re-entry signal
        if self._nvda_below_ema_days == 0 and self._nvda_is_out:
            self._nvda_is_out = False
            self.Log("[BRAIN] NVDA re-entry — back above EMA20")

    def _brain_nvda_rebalance(self):
        """Rebalance NVDA equity position. 65% of brain alloc in BULL."""
        regime = self._get_brain_regime()

        if regime != "BULL" or self._nvda_is_out:
            # Liquidate NVDA if not BULL or EMA gate triggered
            if self.Portfolio[self.nvda].Invested:
                self.Liquidate(self.nvda)
                self.Log(f"[BRAIN] NVDA liquidated — regime={regime} "
                         f"ema_out={self._nvda_is_out}")
            self._nvda_target_shares = 0
            return

        price = self.Securities[self.nvda].Price
        if price <= 0:
            return

        brain_alloc = self._brain_equity()
        nvda_target_value = brain_alloc * 0.65
        target_shares = int(nvda_target_value / price)

        current_shares = self.Portfolio[self.nvda].Quantity

        # 10% rebalance threshold
        if target_shares > 0:
            diff_pct = abs(current_shares - target_shares) / target_shares
            if diff_pct > 0.10 or (current_shares == 0 and target_shares > 0):
                self.MarketOrder(self.nvda, target_shares - current_shares)
                self._nvda_target_shares = target_shares
                self.Log(f"[BRAIN] NVDA rebalance {current_shares} → "
                         f"{target_shares} shares @ {price:.2f}")

    # ══════════════════════════════════════════════════════════════════
    #  BRAIN V10.13b — SPY Put Credit Spreads
    # ══════════════════════════════════════════════════════════════════

    def _brain_pcs_entry_check(self):
        """PCS entry: Mon-Wed at 11 AM, BULL or SIDEWAYS regime."""
        if self.IsWarmingUp:
            return

        regime = self._get_brain_regime()
        if regime not in ("BULL", "SIDEWAYS"):
            return

        # Max 3 concurrent
        if len(self._pcs_spreads) >= 3:
            return

        # Cooldown check
        if self.Time.date() < self._pcs_cooldown_end.date():
            return

        # DD gate: block if DD > 12%
        dd = self._current_dd_pct(self._brain_peak_equity,
                                   self.BRAIN_ALLOC_PCT)
        if dd > 0.12:
            self.Log(f"[BRAIN] PCS blocked — DD {dd*100:.1f}% > 12%")
            return

        # VIX gates
        vix = self._get_vix()
        if vix > 35:
            self.Log(f"[BRAIN] PCS blocked — VIX {vix:.1f} > 35")
            return
        if vix < 14:
            self.Log(f"[BRAIN] PCS blocked — VIX {vix:.1f} < 14 (floor)")
            return

        half_size = vix > 25

        # Total PCS risk check: max 12% of brain equity
        brain_alloc  = self._brain_equity()
        total_risk   = sum(s["max_loss"] for s in self._pcs_spreads.values())
        max_total    = brain_alloc * 0.12
        if total_risk >= max_total:
            return

        # Get SPY option chain
        chain = self._get_option_chain(self.spy)
        if chain is None:
            return

        spy_price = self.Securities[self.spy].Price
        if spy_price <= 0:
            return

        # Filter puts 30-45 DTE
        puts = [c for c in chain
                if c.Right == OptionRight.Put
                and 30 <= (c.Expiry - self.Time).days <= 45
                and c.BidPrice > 0]
        if not puts:
            return

        # Group by expiry, pick the one closest to 37 DTE
        expiries = set(c.Expiry for c in puts)
        target_dte = 37
        best_expiry = min(expiries,
                          key=lambda e: abs((e - self.Time).days - target_dte))

        exp_puts = sorted([c for c in puts if c.Expiry == best_expiry],
                          key=lambda c: c.Strike)

        # Find short put: delta ~ -0.10 (closest to 0.10 in magnitude)
        # Use greeks if available, else approximate by OTM distance
        short_put = None
        for c in exp_puts:
            try:
                if c.Greeks and c.Greeks.Delta:
                    delta = abs(c.Greeks.Delta)
                    if 0.05 <= delta <= 0.20:
                        if short_put is None:
                            short_put = c
                        elif abs(delta - 0.10) < abs(
                                abs(short_put.Greeks.Delta) - 0.10):
                            short_put = c
            except Exception:
                pass

        # Fallback: pick strike ~5-7% below current price
        if short_put is None:
            target_strike = spy_price * 0.93
            candidates = [c for c in exp_puts if c.Strike <= target_strike]
            if not candidates:
                return
            short_put = max(candidates, key=lambda c: c.Strike)

        # Long put: $5 below short
        long_strike = short_put.Strike - 5
        long_put = None
        for c in exp_puts:
            if abs(c.Strike - long_strike) < 0.50:
                long_put = c
                break

        if long_put is None:
            return

        # Calculate credit and risk
        credit = short_put.BidPrice - long_put.AskPrice
        if credit <= 0:
            return

        width    = short_put.Strike - long_put.Strike
        max_loss = (width - credit) * 100  # per contract

        # Position sizing: max 4% risk per trade
        per_trade_limit = brain_alloc * 0.04
        if half_size:
            per_trade_limit *= 0.5

        contracts = max(1, int(per_trade_limit / max_loss))

        # Check total risk
        new_total_risk = total_risk + (max_loss * contracts)
        if new_total_risk > max_total:
            contracts = max(1, int((max_total - total_risk) / max_loss))
            if contracts < 1:
                return

        # Execute: sell short put, buy long put
        t1 = self.MarketOrder(short_put.Symbol, -contracts)
        t2 = self.MarketOrder(long_put.Symbol, contracts)

        self._pcs_id_counter += 1
        sid = self._pcs_id_counter
        self._pcs_spreads[sid] = {
            "short_symbol": short_put.Symbol,
            "long_symbol":  long_put.Symbol,
            "short_strike": short_put.Strike,
            "long_strike":  long_put.Strike,
            "expiry":       best_expiry,
            "credit":       credit,
            "max_loss":     max_loss * contracts,
            "contracts":    contracts,
            "entry_time":   self.Time,
        }

        self.Log(f"[BRAIN] PCS OPEN id={sid} "
                 f"short={short_put.Strike} long={long_put.Strike} "
                 f"exp={best_expiry.date()} credit={credit:.2f} "
                 f"qty={contracts} vix={vix:.1f} "
                 f"{'HALF' if half_size else 'FULL'}")

    def _brain_pcs_manage(self):
        """Manage open PCS: TP 50% credit, SL 2x credit, DTE <= 21 close."""
        closed_ids = []
        for sid, spread in list(self._pcs_spreads.items()):
            short_sym = spread["short_symbol"]
            long_sym  = spread["long_symbol"]
            credit    = spread["credit"]
            contracts = spread["contracts"]

            # Check if positions still exist
            short_held = self.Portfolio[short_sym].Quantity
            long_held  = self.Portfolio[long_sym].Quantity

            if short_held == 0 and long_held == 0:
                closed_ids.append(sid)
                continue

            # Current spread value (cost to close)
            short_price = self.Securities[short_sym].Price
            long_price  = self.Securities[long_sym].Price

            if short_price <= 0 and long_price <= 0:
                continue

            current_debit = short_price - long_price  # cost to close
            profit_per_contract = credit - current_debit

            dte = (spread["expiry"] - self.Time).days

            should_close = False
            reason = ""
            is_loss = False

            # TP: captured 50% of credit
            if profit_per_contract >= credit * 0.50:
                should_close = True
                reason = "TP 50%"

            # SL: loss exceeds 2x credit
            elif profit_per_contract <= -credit * 2.0:
                should_close = True
                reason = "SL 2x"
                is_loss = True

            # DTE close
            elif dte <= 21:
                should_close = True
                reason = f"DTE {dte}"
                is_loss = profit_per_contract < 0

            if should_close:
                # Close: buy back short, sell long
                if short_held != 0:
                    self.MarketOrder(short_sym, -short_held)
                if long_held != 0:
                    self.MarketOrder(long_sym, -long_held)

                self.Log(f"[BRAIN] PCS CLOSE id={sid} reason={reason} "
                         f"pnl/c={profit_per_contract:.2f}")

                if is_loss:
                    self._pcs_cooldown_end = self.Time + timedelta(days=3)
                    self.Log(f"[BRAIN] PCS cooldown until "
                             f"{self._pcs_cooldown_end.date()}")

                closed_ids.append(sid)

        for sid in closed_ids:
            self._pcs_spreads.pop(sid, None)

    # ══════════════════════════════════════════════════════════════════
    #  BRAIN V10.13b — Bear Puts
    # ══════════════════════════════════════════════════════════════════

    def _brain_bear_put_entry(self):
        """Bear puts: BEAR regime only, SPY puts delta 0.30."""
        regime = self._get_brain_regime()
        if regime != "BEAR":
            return

        # Max 2 positions
        if len(self._bear_puts) >= 2:
            return

        brain_alloc = self._brain_equity()
        per_trade = brain_alloc * 0.05  # 5% capital per trade

        chain = self._get_option_chain(self.spy)
        if chain is None:
            return

        spy_price = self.Securities[self.spy].Price
        if spy_price <= 0:
            return

        # Filter puts 14-30 DTE
        puts = [c for c in chain
                if c.Right == OptionRight.Put
                and 14 <= (c.Expiry - self.Time).days <= 30
                and c.AskPrice > 0]
        if not puts:
            return

        # Find delta ~0.30
        best = None
        for c in puts:
            try:
                if c.Greeks and c.Greeks.Delta:
                    delta = abs(c.Greeks.Delta)
                    if 0.15 <= delta <= 0.45:
                        if best is None:
                            best = c
                        elif abs(delta - 0.30) < abs(
                                abs(best.Greeks.Delta) - 0.30):
                            best = c
            except Exception:
                pass

        # Fallback: strike ~3% below current
        if best is None:
            target_strike = spy_price * 0.97
            expiries = set(c.Expiry for c in puts)
            best_exp = min(expiries,
                           key=lambda e: abs((e - self.Time).days - 21))
            candidates = [c for c in puts
                          if c.Expiry == best_exp
                          and abs(c.Strike - target_strike) < 5]
            if not candidates:
                return
            best = min(candidates,
                       key=lambda c: abs(c.Strike - target_strike))

        mid_price = (best.BidPrice + best.AskPrice) / 2.0
        if mid_price <= 0:
            return

        qty = max(1, int(per_trade / (mid_price * 100)))

        ticket = self.MarketOrder(best.Symbol, qty)
        if ticket and ticket.Status != OrderStatus.Invalid:
            self._bear_put_id += 1
            bid = self._bear_put_id
            self._bear_puts[bid] = {
                "symbol":      best.Symbol,
                "entry_price": mid_price,
                "qty":         qty,
                "entry_time":  self.Time,
                "trailing":    False,
                "trail_high":  mid_price,
            }
            self.Log(f"[BRAIN] BEAR PUT OPEN id={bid} "
                     f"strike={best.Strike} exp={best.Expiry.date()} "
                     f"qty={qty} mid={mid_price:.2f}")

    def _brain_bear_put_manage(self):
        """Manage bear puts: TP 2x, SL 0.5x, trailing after 80%."""
        closed_ids = []
        for bid, pos in list(self._bear_puts.items()):
            sym = pos["symbol"]
            if not self.Portfolio[sym].Invested:
                closed_ids.append(bid)
                continue

            entry = pos["entry_price"]
            if entry <= 0:
                closed_ids.append(bid)
                continue

            current = self.Securities[sym].Price
            if current <= 0:
                continue

            pnl_pct = (current - entry) / entry

            # Update trail high
            if current > pos["trail_high"]:
                pos["trail_high"] = current

            should_close = False
            reason = ""

            # TP: 2x (100% gain)
            if pnl_pct >= 1.0:
                should_close = True
                reason = "TP 2x"

            # SL: 0.5x (50% loss)
            elif pnl_pct <= -0.50:
                should_close = True
                reason = "SL 0.5x"

            # Trailing stop after 80% gain
            elif pnl_pct >= 0.80:
                pos["trailing"] = True

            if pos["trailing"]:
                trail_drop = (pos["trail_high"] - current) / pos["trail_high"]
                if trail_drop >= 0.20:  # 20% pullback from high
                    should_close = True
                    reason = "TRAIL STOP"

            # DTE guard
            try:
                dte = (sym.ID.Date - self.Time).days
                if dte <= 2:
                    should_close = True
                    reason = f"DTE {dte}"
            except Exception:
                pass

            if should_close:
                qty = pos["qty"]
                self.MarketOrder(sym, -qty)
                self.Log(f"[BRAIN] BEAR PUT CLOSE id={bid} "
                         f"reason={reason} pnl={pnl_pct*100:.1f}%")
                closed_ids.append(bid)

        for bid in closed_ids:
            self._bear_puts.pop(bid, None)
