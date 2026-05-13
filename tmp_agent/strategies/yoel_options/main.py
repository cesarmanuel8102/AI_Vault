"""
Yoel Options V2.1 — ANTI-DEGRADATION + $10K PERSONAL ACCOUNT
=============================================================

Based on V2.0b (CHAMPION: +175.68%, CAGR 66.4%, Sharpe 1.337, DD 44%).
Focus: $10K personal account (no prop firm rules). Kill gates: CAGR>12%, Sharpe>1.0.

V2.0b Root Causes of Degradation:
  1. Cooldown trap: 93 blocks, 48-79 day gaps with ZERO trades
  2. hl=0.50 recovery trap: half-sized wins take months to recover
  3. PM_BOUNCE signals vanish in pullbacks (Oct 2023: 0 scans)
  4. SL intraday kills: 51% → SL, 80-100% SL rate in degradation
  5. MSFT is net loser: -$2,154 on 23 trades

V2.1 Anti-Degradation Changes (vs V2.0b):
  - DROP MSFT: net loser removed → 3 tickers (AAPL, NVDA, QQQ)
  - Cooldown: 2 losses/10d → 1 loss/5d, block 5d (shorter gaps)
  - Health (hl): LINEAR scale 1.0 at 0% DD → 0.5 at 25% DD (no step jumps)
  - SL: -20% → -15% (cut losses faster, reduce SL dollar damage)
  - Weekly limit: 3 → 4 (more trades available)
  - Confidence cap: 3.0x → 2.5x (slightly less max exposure)
  - Monthly circuit breaker: halt if monthly return < -8%
  - Base risk: 5% (unchanged — needed for $10K account)
  - Profit target: 35% (unchanged)

Linear hl formula: mult_health = max(0.5, 1.0 - dd/0.25)
  At DD 0%:  hl = 1.00
  At DD 5%:  hl = 0.80
  At DD 10%: hl = 0.60
  At DD 15%: hl = 0.40 → clamped to 0.50
  At DD 25%: hl = 0.00 → clamped to 0.50
  SPY below SMA20: hl = min(hl, 0.75)

Parameters (5 max per contract §13):
  1. profit_target_pct  = 0.35
  2. risk_per_trade     = 0.05  (5% base risk, scaled by confidence)
  3. max_positions      = 1
  4. dte_min            = 14
  5. dte_max            = 30
"""

from AlgorithmImports import *
import numpy as np
from datetime import timedelta


class YoelOptionsV21(QCAlgorithm):

    # SPY is added for data/filter but NOT traded
    # V2.1: MSFT dropped (net loser -$2,154 on 23 trades in V2.0b)
    TRADE_TICKERS = ["AAPL", "NVDA", "QQQ"]
    FILTER_TICKER = "SPY"

    def Initialize(self):
        start_year = int(self.GetParameter("start_year") or 2023)
        end_year = int(self.GetParameter("end_year") or 2024)
        end_month = int(self.GetParameter("end_month") or 12)

        self.SetStartDate(start_year, 1, 1)
        self.SetEndDate(end_year, end_month, 28)
        self.SetCash(10000)
        self.SetBrokerageModel(BrokerageName.InteractiveBrokersBrokerage, AccountType.Margin)

        # ── 5 Tunable Parameters ──
        self.profit_target_pct = float(self.GetParameter("profit_target_pct") or 0.35)
        self.risk_per_trade = float(self.GetParameter("risk_per_trade") or 0.05)
        self.max_positions = int(self.GetParameter("max_positions") or 1)
        self.dte_min = int(self.GetParameter("dte_min") or 14)
        self.dte_max = int(self.GetParameter("dte_max") or 30)

        # ── Fixed constants ──
        self.stop_loss_pct = -0.15
        self.max_hold_days = 5
        self.min_bb_bandwidth = 0.02
        self.pm_touch_tolerance = 0.03
        self.max_trades_per_week = 4

        # ── Soft DD thresholds (now inside confidence calc) ──
        self._peak_equity = 10000.0

        # ── Add SPY for filter (equity only, no options) ──
        self.equity_symbols = {}
        spy_eq = self.AddEquity(self.FILTER_TICKER, Resolution.Minute)
        spy_eq.SetDataNormalizationMode(DataNormalizationMode.Raw)
        self.equity_symbols[self.FILTER_TICKER] = spy_eq.Symbol

        # ── Add tradeable equities + options ──
        self.option_symbols = {}
        for ticker in self.TRADE_TICKERS:
            eq = self.AddEquity(ticker, Resolution.Minute)
            eq.SetDataNormalizationMode(DataNormalizationMode.Raw)
            self.equity_symbols[ticker] = eq.Symbol

            opt = self.AddOption(ticker, Resolution.Minute)
            opt.SetFilter(lambda u: u.Strikes(-5, 5).Expiration(self.dte_min, self.dte_max + 5))
            self.option_symbols[ticker] = opt.Symbol

        # ── State ──
        self.setups = []
        self._scanned_today = None
        self._executed_today = None
        self.positions = {}
        self.closed_trades = []
        self._entry_seq = 0
        self._companies_in_positions = set()
        self.cached_chains = {}

        # ── Weekly trade counter ──
        self._week_trade_count = 0
        self._current_week = None

        # ── Global market filter cache ──
        self._spy_direction = None

        # ── Tracking state ──
        self._total_scan_signals = 0
        self._chain_received_ever = {t: False for t in self.TRADE_TICKERS}
        self._strategy_signal_counts = {}

        # ── V2.1: Ticker Cooldown (1 loss in 5 days → block 5 days) — shorter gaps ──
        self._ticker_loss_dates = {t: [] for t in self.TRADE_TICKERS}
        self.ticker_cooldown_days = 5
        self.ticker_cooldown_threshold = 1

        # ── V1.9: Daily Circuit Breaker (1 loss today → no new entries) ──
        self._last_loss_date = None

        # ── V1.9: SPY Short-Term Filter (SPY < SMA20 daily → caution) ──
        self._spy_below_sma20 = False

        # ── V1.9 Tracking counters ──
        self._cooldown_blocks = 0
        self._circuit_breaker_blocks = 0

        # ── V2.0b: Confidence tracking ──
        self._confidence_dist = {}  # {mult_rounded: count}
        self._confidence_total = 0.0
        self._confidence_trades = 0
        self._risk_skip_count = 0

        # ── V2.0c: Monthly Circuit Breaker ──
        self._monthly_pnl = 0.0
        self._current_month = None
        self._monthly_circuit_breaker_pct = -0.08  # halt if monthly PnL < -8% of start-of-month equity
        self._month_start_equity = 10000.0
        self._monthly_halted = False
        self._monthly_halt_count = 0

        # ── Pending limit orders ──
        self._limit_order_tag = {}

        # ── Schedule ──
        self.Schedule.On(self.DateRules.EveryDay("SPY"),
                         self.TimeRules.AfterMarketOpen("SPY", 1),
                         self.MorningScan)

        self.Schedule.On(self.DateRules.EveryDay("SPY"),
                         self.TimeRules.AfterMarketOpen("SPY", 5),
                         self.ExecuteTrades)

        self.Schedule.On(self.DateRules.EveryDay("SPY"),
                         self.TimeRules.Every(timedelta(minutes=5)),
                         self.ManagePositions)

        self.Schedule.On(self.DateRules.EveryDay("SPY"),
                         self.TimeRules.BeforeMarketClose("SPY", 5),
                         self.EODCleanup)

        self.Log("V2.1 INIT: Anti-Degradation, base 5%, LINEAR hl, clamp [0.5x-2.5x], SL -15%, cooldown 1/5d, monthly breaker -8%")

    # ═══════════════════════════════════════════════════════════
    # DD State + Confidence (V2.0b)
    # ═══════════════════════════════════════════════════════════

    def _update_dd_state(self):
        """Update peak equity and return current DD fraction."""
        equity = self.Portfolio.TotalPortfolioValue
        if equity > self._peak_equity:
            self._peak_equity = equity

        dd = (self._peak_equity - equity) / self._peak_equity if self._peak_equity > 0 else 0
        return dd

    def _calc_confidence(self, setup_score, dd):
        """V2.1: Multiplicative confidence = score × regime × health.
        Returns clamped multiplier [0.5, 2.5] applied to risk_per_trade.
        LINEAR health: hl = max(0.5, 1.0 - dd/0.25). SPY<SMA20 caps hl at 0.75.
        """
        # Factor 1: Score quality
        if setup_score >= 6.5:
            mult_score = 1.25
        elif setup_score >= 5.0:
            mult_score = 1.0
        else:
            mult_score = 0.6

        # Factor 2: Market regime (SPY direction)
        if self._spy_direction == "BULL":
            mult_regime = 1.0
        elif self._spy_direction == "FLAT":
            mult_regime = 0.75
        else:  # BEAR
            mult_regime = 0.5

        # Factor 3: System health — V2.1 LINEAR scale
        # hl = max(0.5, 1.0 - dd/0.25)
        # At DD 0%: 1.0, DD 5%: 0.80, DD 10%: 0.60, DD 12.5%+: 0.50 (clamped)
        mult_health = max(0.5, 1.0 - dd / 0.25)

        # SPY below SMA20 caution: cap hl at 0.75
        if self._spy_below_sma20:
            mult_health = min(mult_health, 0.75)

        raw = mult_score * mult_regime * mult_health
        clamped = max(0.5, min(raw, 2.5))
        return clamped, mult_score, mult_regime, mult_health

    # ═══════════════════════════════════════════════════════════
    # OnData — Cache option chains ONLY
    # ═══════════════════════════════════════════════════════════

    def OnData(self, data):
        for kvp in data.OptionChains:
            for ticker, opt_sym in self.option_symbols.items():
                if kvp.Key == opt_sym:
                    chain = kvp.Value
                    self.cached_chains[ticker] = chain
                    if not self._chain_received_ever[ticker]:
                        self._chain_received_ever[ticker] = True

    # ═══════════════════════════════════════════════════════════
    # OnOrderEvent — Fill detection
    # ═══════════════════════════════════════════════════════════

    def OnOrderEvent(self, orderEvent):
        if orderEvent.Status != OrderStatus.Filled:
            return

        sym = orderEvent.Symbol
        if sym.SecurityType != SecurityType.Option:
            return

        if orderEvent.FillQuantity < 0:
            tag_to_close = None
            for tag, pos in self.positions.items():
                if pos["contract"] == sym:
                    tag_to_close = tag
                    break

            if tag_to_close is not None:
                fill_price = float(orderEvent.FillPrice)
                pos = self.positions[tag_to_close]
                entry_price = pos["entry_price"]
                pnl_pct = (fill_price / entry_price - 1) if entry_price > 0 else 0

                reason = "LIMIT_FILL_35%"
                if pnl_pct < -0.08:
                    reason = f"SL_FILL={pnl_pct:+.0%}"
                elif abs(fill_price - pos.get("limit_price", 0)) < 0.05:
                    reason = "LIMIT_FILL_35%"

                self._record_closed_trade(tag_to_close, reason, fill_price)

    # ═══════════════════════════════════════════════════════════
    # MORNING SCAN — CALL + PUT with SPY filter
    # ═══════════════════════════════════════════════════════════

    def MorningScan(self):
        today_key = self.Time.date()
        if self._scanned_today == today_key:
            return
        self._scanned_today = today_key
        self.setups = []

        # ── V2.0c: Monthly Circuit Breaker — reset on new month ──
        current_month = (self.Time.year, self.Time.month)
        if self._current_month != current_month:
            self._current_month = current_month
            self._monthly_pnl = 0.0
            self._month_start_equity = self.Portfolio.TotalPortfolioValue
            self._monthly_halted = False

        if self._monthly_halted:
            return

        # Check if monthly PnL has breached threshold
        current_equity = self.Portfolio.TotalPortfolioValue
        monthly_return = (current_equity - self._month_start_equity) / self._month_start_equity if self._month_start_equity > 0 else 0
        if monthly_return < self._monthly_circuit_breaker_pct:
            self._monthly_halted = True
            self._monthly_halt_count += 1
            self.Log(f"MONTHLY_HALT: {self.Time.strftime('%Y-%m')} return={monthly_return:+.1%} < {self._monthly_circuit_breaker_pct:.0%} — halting month")
            return

        # ── Update weekly trade counter ──
        week_num = self.Time.isocalendar()[1]
        week_year = self.Time.isocalendar()[0]
        week_key = f"{week_year}-W{week_num}"
        if self._current_week != week_key:
            self._current_week = week_key
            self._week_trade_count = 0

        if self._week_trade_count >= self.max_trades_per_week:
            return

        # ── DD check before scanning ──
        dd = self._update_dd_state()

        # All symbols including SPY for history (needed for filter)
        symbols = list(self.equity_symbols.values())

        try:
            daily_hist = self.History(symbols, 252, Resolution.Daily)
        except Exception as e:
            self.Log(f"SCAN_ERR: {str(e)[:100]}")
            return
        if daily_hist.empty:
            return

        # ── GLOBAL MARKET FILTER: SPY daily trend ──
        self._spy_direction = self._get_spy_direction(daily_hist)

        # ── V1.9: SPY Short-Term Filter: price < SMA20 → caution ──
        self._spy_below_sma20 = self._check_spy_below_sma20(daily_hist)

        # Only scan TRADE_TICKERS (not SPY)
        for ticker in self.TRADE_TICKERS:
            sym = self.equity_symbols.get(ticker)
            if sym is None:
                continue
            try:
                self._analyze_symbol(ticker, sym, daily_hist)
            except Exception:
                pass

        self.setups.sort(key=lambda x: x["score"], reverse=True)
        self.setups = self.setups[:5]
        self._total_scan_signals += len(self.setups)

        if self.setups:
            summary = ", ".join([f"{s['ticker']}({s['strategy']},sc={s['score']:.1f})" for s in self.setups[:3]])
            self.Log(f"SCAN: {len(self.setups)} SPY={self._spy_direction} DD={dd:.0%}: {summary}")

    def _get_spy_direction(self, daily_hist):
        spy_sym = self.equity_symbols.get("SPY")
        if spy_sym is None or spy_sym not in daily_hist.index.get_level_values(0):
            return "FLAT"

        df = daily_hist.loc[spy_sym]
        if len(df) < 50:
            return "FLAT"

        close = df["close"].values
        sma20 = float(np.mean(close[-20:]))
        sma40 = float(np.mean(close[-40:]))

        sma20_5ago = float(np.mean(close[-25:-5])) if len(close) >= 25 else sma20

        if sma20 > sma40 and sma20 > sma20_5ago:
            return "BULL"
        elif sma40 > sma20 and sma20 < sma20_5ago:
            return "BEAR"
        else:
            return "FLAT"

    def _check_spy_below_sma20(self, daily_hist):
        """V1.9: Return True if SPY price is below its daily SMA20."""
        spy_sym = self.equity_symbols.get("SPY")
        if spy_sym is None or spy_sym not in daily_hist.index.get_level_values(0):
            return False
        df = daily_hist.loc[spy_sym]
        if len(df) < 20:
            return False
        close = df["close"].values
        sma20 = float(np.mean(close[-20:]))
        current_price = float(close[-1])
        return current_price < sma20

    def _analyze_symbol(self, ticker, sym, daily_hist):
        """Analyze one symbol for PM_BOUNCE CALL only."""
        # V1.9: Ticker cooldown — skip if 2+ losses in last 10 days
        today = self.Time.date()
        recent_losses = [d for d in self._ticker_loss_dates.get(ticker, [])
                         if (today - d).days <= self.ticker_cooldown_days]
        if len(recent_losses) >= self.ticker_cooldown_threshold:
            self._cooldown_blocks += 1
            return

        if sym not in daily_hist.index.get_level_values(0):
            return
        df_d = daily_hist.loc[sym]
        if len(df_d) < 200:
            return

        close_d = df_d["close"].values
        price = close_d[-1]
        if price <= 0:
            return

        # ── Daily BB(20,2) ──
        sma20_d = float(np.mean(close_d[-20:]))
        std20_d = float(np.std(close_d[-20:]))
        bb_upper_d = sma20_d + 2.0 * std20_d
        bb_lower_d = sma20_d - 2.0 * std20_d
        bb_bandwidth_d = (bb_upper_d - bb_lower_d) / sma20_d if sma20_d > 0 else 0

        # ── Daily SMAs ──
        sma20 = sma20_d
        sma40 = float(np.mean(close_d[-40:])) if len(close_d) >= 40 else sma20

        sma20_prev = float(np.mean(close_d[-25:-5])) if len(close_d) >= 25 else sma20
        sma40_5ago = float(np.mean(close_d[-45:-5])) if len(close_d) >= 45 else sma40

        daily_bullish = (sma20 > sma40 and sma20 > sma20_prev and sma40 > sma40_5ago)
        daily_bearish = (sma40 > sma20 and sma20 < sma20_prev and sma40 < sma40_5ago)

        # BB volatility gate
        if bb_bandwidth_d <= self.min_bb_bandwidth:
            return

        pm_dist = abs(price - sma20) / sma20 if sma20 > 0 else 999
        if pm_dist >= self.pm_touch_tolerance:
            return

        # V1.6 bug fix #4: exclude today's bar
        touch_count = self._count_pm_touches(close_d[:-1], sma20)
        if touch_count > 2:
            return

        score = (1.0 / max(touch_count, 1)) * bb_bandwidth_d * 100

        # ════════ PM Bounce CALL (Bullish Daily) ════════
        pm_direction = "UP" if sma20 > sma20_prev else "DOWN"

        if (daily_bullish and pm_direction == "UP"
                and price >= sma20 * (1 - self.pm_touch_tolerance)
                and self._spy_direction in ("BULL", "FLAT")):
            self.setups.append({
                "ticker": ticker, "sym": sym, "strategy": "PM_BOUNCE_CALL",
                "direction": "CALL", "price": price, "pm_level": sma20,
                "touch_count": touch_count, "bb_bandwidth": bb_bandwidth_d, "score": score,
            })
            self._count_signal("PM_BOUNCE_CALL")
            return

    # ═══════════════════════════════════════════════════════════
    # EXECUTE TRADES — 5 min after open
    # ═══════════════════════════════════════════════════════════

    def ExecuteTrades(self):
        today_key = self.Time.date()
        if self._executed_today == today_key:
            return
        self._executed_today = today_key

        if not self.setups:
            return

        if self._week_trade_count >= self.max_trades_per_week:
            return

        # ── V2.0c: Monthly Circuit Breaker check ──
        if self._monthly_halted:
            return

        # ── V2.0b: DD state for confidence calc ──
        dd = self._update_dd_state()

        # ── V1.9: Daily Circuit Breaker — 1 loss today → no new entries ──
        if self._last_loss_date == today_key:
            self._circuit_breaker_blocks += 1
            return

        current_positions = len(self.positions)
        entered = 0

        for setup in self.setups:
            if current_positions + entered >= self.max_positions:
                break
            if self._week_trade_count + entered >= self.max_trades_per_week:
                break

            ticker = setup["ticker"]
            if len(self._companies_in_positions) >= 3:
                if ticker not in self._companies_in_positions:
                    continue

            direction = setup["direction"]
            underlying_price = self.Securities[setup["sym"]].Price
            if underlying_price <= 0:
                continue

            chain = self.cached_chains.get(ticker)
            if chain is None:
                self.Log(f"NO_CHAIN: {ticker}")
                continue

            contract = self._select_contract(chain, underlying_price, direction)
            if contract is None:
                self.Log(f"NO_CONTRACT: {ticker} {direction}")
                continue

            ask = contract.AskPrice
            if ask <= 0:
                ask = (contract.BidPrice + contract.AskPrice) / 2
            if ask <= 0:
                ask = contract.LastPrice
            if ask <= 0:
                continue

            # ── V2.0b: Confidence-based sizing ──
            confidence, m_sc, m_rg, m_hl = self._calc_confidence(setup["score"], dd)
            adjusted_risk = self.risk_per_trade * confidence

            equity = self.Portfolio.TotalPortfolioValue
            target_risk = equity * adjusted_risk
            risk_per_contract = ask * abs(self.stop_loss_pct) * 100
            n_contracts = int(target_risk / risk_per_contract)

            # Track confidence distribution
            conf_key = round(confidence, 2)
            self._confidence_dist[conf_key] = self._confidence_dist.get(conf_key, 0) + 1
            self._confidence_total += confidence
            self._confidence_trades += 1

            if n_contracts < 1:
                self._risk_skip_count += 1
                self.Log(f"RISK_SKIP: {ticker} conf={confidence:.2f} ask=${ask:.2f} rpc=${risk_per_contract:.0f} > target=${target_risk:.0f}")
                continue

            total_cost = n_contracts * ask * 100
            if total_cost > self.Portfolio.MarginRemaining * 0.80:
                n_contracts = int(self.Portfolio.MarginRemaining * 0.80 / (ask * 100))
                if n_contracts < 1:
                    self.Log(f"MARGIN_SKIP: {ticker} cost=${total_cost:.0f} margin=${self.Portfolio.MarginRemaining:.0f}")
                    continue

            # Execute BUY
            self.MarketOrder(contract.Symbol, n_contracts)

            # Limit sell at profit target
            limit_price = round(ask * (1 + self.profit_target_pct), 2)
            self.LimitOrder(contract.Symbol, -n_contracts, limit_price)

            # Track
            self._entry_seq += 1
            tag = f"YOEL_{direction}_{ticker}_{self.Time.strftime('%y%m%d')}_{self._entry_seq}"
            dte = (contract.Expiry - self.Time).days

            self.positions[tag] = {
                "contract": contract.Symbol,
                "underlying": setup["sym"],
                "ticker": ticker,
                "strategy": setup["strategy"],
                "direction": direction,
                "n": n_contracts,
                "entry_price": ask,
                "entry_time": self.Time,
                "underlying_price_at_entry": underlying_price,
                "pm_level": setup["pm_level"],
                "touch_count": setup["touch_count"],
                "bb_bandwidth": setup["bb_bandwidth"],
                "dte_at_entry": dte,
                "limit_price": limit_price,
                "max_value": ask,
            }

            self._limit_order_tag[contract.Symbol] = tag
            self._companies_in_positions.add(ticker)
            self._week_trade_count += 1
            entered += 1

            dd_flag = f" conf={confidence:.2f}[sc={m_sc:.2f},rg={m_rg:.2f},hl={m_hl:.2f}] risk={adjusted_risk:.1%}"
            self.Log(f"OPEN {tag}: BUY {direction} {ticker} x{n_contracts} "
                     f"ask=${ask:.2f} lim=${limit_price:.2f} DTE={dte} "
                     f"K={contract.Strike} undrl=${underlying_price:.2f} wk={self._week_trade_count}{dd_flag}")

    def _select_contract(self, chain, underlying_price, direction):
        right = OptionRight.Call if direction == "CALL" else OptionRight.Put

        candidates = []
        for c in chain:
            if c.Right != right:
                continue
            dte = (c.Expiry - self.Time).days
            if dte < self.dte_min or dte > self.dte_max:
                continue
            if c.AskPrice <= 0 and c.LastPrice <= 0:
                continue
            strike_dist = abs(float(c.Strike) - underlying_price) / underlying_price
            if strike_dist > 0.05:
                continue
            candidates.append(c)

        if not candidates:
            return None

        target_dte = (self.dte_min + self.dte_max) / 2
        best = min(candidates, key=lambda c: (
            abs(float(c.Strike) - underlying_price) / underlying_price * 10
            + abs((c.Expiry - self.Time).days - target_dte) / 100
        ))
        return best

    # ═══════════════════════════════════════════════════════════
    # POSITION MANAGEMENT (every 5 min) — SL + TIME + DTE
    # ═══════════════════════════════════════════════════════════

    def ManagePositions(self):
        if not self.positions:
            return

        to_close = []
        for tag, pos in self.positions.items():
            contract = pos["contract"]
            entry_price = pos["entry_price"]

            if not self.Portfolio[contract].Invested:
                if tag in self.positions:
                    to_close.append((tag, "CLOSED_EXTERNAL"))
                continue

            mid = self._get_mid(contract)
            if mid is None or mid <= 0:
                continue

            if mid > pos["max_value"]:
                pos["max_value"] = mid

            pnl_pct = (mid - entry_price) / entry_price if entry_price > 0 else 0

            # Hard stop loss
            if pnl_pct <= self.stop_loss_pct:
                to_close.append((tag, f"SL={pnl_pct:+.0%}"))
                continue

            # Time stop
            held_days = (self.Time - pos["entry_time"]).days
            if held_days >= self.max_hold_days:
                to_close.append((tag, f"TIME={held_days}d"))
                continue

            # DTE guard
            dte_remaining = (contract.ID.Date - self.Time).days
            if dte_remaining <= 3:
                to_close.append((tag, f"DTE={dte_remaining}"))
                continue

        for tag, reason in to_close:
            self._close_position(tag, reason)

    def _close_position(self, tag, reason):
        pos = self.positions.get(tag)
        if pos is None:
            return

        contract = pos["contract"]
        n = pos["n"]

        open_orders = self.Transactions.GetOpenOrders(contract)
        for order in open_orders:
            self.Transactions.CancelOrder(order.Id)

        mid = self._get_mid(contract)
        exit_price = mid if mid and mid > 0 else 0

        if self.Portfolio[contract].Invested:
            self.MarketOrder(contract, -n)

        self._record_closed_trade(tag, reason, exit_price)

    def _record_closed_trade(self, tag, reason, exit_price):
        pos = self.positions.get(tag)
        if pos is None:
            return

        n = pos["n"]
        pnl_dollar = (exit_price - pos["entry_price"]) * n * 100
        pnl_pct = (exit_price / pos["entry_price"] - 1) if pos["entry_price"] > 0 else 0

        self.closed_trades.append({
            "tag": tag, "strategy": pos["strategy"], "direction": pos["direction"],
            "ticker": pos["ticker"], "n": n, "entry_price": pos["entry_price"],
            "exit_price": exit_price, "pnl_dollar": pnl_dollar, "pnl_pct": pnl_pct,
            "held_days": (self.Time - pos["entry_time"]).days, "reason": reason,
            "entry_date": pos["entry_time"].strftime("%Y-%m-%d"),
            "exit_date": self.Time.strftime("%Y-%m-%d"),
            "underlying_at_entry": pos["underlying_price_at_entry"],
            "pm_level": pos["pm_level"], "touch_count": pos["touch_count"],
            "bb_bandwidth": pos["bb_bandwidth"], "dte_at_entry": pos["dte_at_entry"],
            "max_value": pos["max_value"],
        })

        self.Log(f"CLOSE {tag}: {reason} PnL=${pnl_dollar:+,.0f}({pnl_pct:+.0%}) held={(self.Time - pos['entry_time']).days}d")

        # V1.9: On loss, record for ticker cooldown + circuit breaker
        if pnl_dollar < 0:
            ticker = pos["ticker"]
            loss_date = self.Time.date()
            if ticker in self._ticker_loss_dates:
                self._ticker_loss_dates[ticker].append(loss_date)
            self._last_loss_date = loss_date

        self._companies_in_positions.discard(pos["ticker"])
        self._limit_order_tag.pop(pos["contract"], None)
        del self.positions[tag]

    # ═══════════════════════════════════════════════════════════
    # EOD CLEANUP
    # ═══════════════════════════════════════════════════════════

    def EODCleanup(self):
        for holding in self.Portfolio.Values:
            if not holding.Invested:
                continue
            sym = holding.Symbol
            if sym.SecurityType != SecurityType.Option:
                continue
            tracked = any(pos["contract"] == sym for pos in self.positions.values())
            if not tracked:
                self.MarketOrder(sym, -int(holding.Quantity))
                self.Log(f"EOD_ORPHAN: Closed {sym}")

    # ═══════════════════════════════════════════════════════════
    # END OF ALGORITHM
    # ═══════════════════════════════════════════════════════════

    def OnEndOfAlgorithm(self):
        for tag in list(self.positions.keys()):
            self._close_position(tag, "EOA")
        self.Liquidate()

        self.Log("=" * 60)
        self.Log("YOEL OPTIONS V2.1 — ANTI-DEGRADATION + $10K PERSONAL — FINAL REPORT")
        self.Log("=" * 60)

        eq = self.Portfolio.TotalPortfolioValue
        trades = self.closed_trades
        n_trades = len(trades)

        self.Log(f"  chains={dict(self._chain_received_ever)}")
        self.Log(f"  signals={self._total_scan_signals} counts={self._strategy_signal_counts}")
        self.Log(f"  V1.9: cooldown_blocks={self._cooldown_blocks} circuit_breaker_blocks={self._circuit_breaker_blocks}")
        self.Log(f"  V2.1: risk_skips={self._risk_skip_count} peak_eq=${self._peak_equity:,.0f} monthly_halts={self._monthly_halt_count}")

        # V2.1: Confidence distribution
        if self._confidence_trades > 0:
            avg_conf = self._confidence_total / self._confidence_trades
            self.Log(f"  V2.1 CONFIDENCE: avg={avg_conf:.2f} trades={self._confidence_trades}")
            for ck in sorted(self._confidence_dist.keys()):
                self.Log(f"    conf={ck:.2f}: {self._confidence_dist[ck]} trades")

        if n_trades == 0:
            self.Log("NO TRADES EXECUTED")
            self.Log("=" * 60)
            return

        wins = sum(1 for t in trades if t["pnl_dollar"] > 0)
        total_pnl = sum(t["pnl_dollar"] for t in trades)
        wr = wins / n_trades * 100
        gross_win = sum(t["pnl_dollar"] for t in trades if t["pnl_dollar"] > 0)
        gross_loss = abs(sum(t["pnl_dollar"] for t in trades if t["pnl_dollar"] < 0))
        pf = gross_win / gross_loss if gross_loss > 0 else 999

        avg_win = gross_win / max(wins, 1)
        avg_loss = gross_loss / max(n_trades - wins, 1)

        self.Log(f"  Equity: ${eq:,.0f} | Return: {eq/10000 - 1:+.2%}")
        self.Log(f"  Trades: {n_trades} | Wins: {wins} | WR: {wr:.1f}%")
        self.Log(f"  PnL: ${total_pnl:+,.0f} | PF: {pf:.2f}")
        self.Log(f"  AvgWin: ${avg_win:,.0f} AvgLoss: ${avg_loss:,.0f} R:R={avg_win/max(avg_loss,1):.2f}")

        # By strategy
        self.Log("--- BY STRATEGY ---")
        for strat in ["PM_BOUNCE_CALL"]:
            st = [t for t in trades if t["strategy"] == strat]
            if not st:
                continue
            sw = sum(1 for t in st if t["pnl_dollar"] > 0)
            sp = sum(t["pnl_dollar"] for t in st)
            self.Log(f"  {strat}: {len(st)}t WR={sw/len(st)*100:.0f}% PnL=${sp:+,.0f}")

        # By exit reason
        self.Log("--- BY EXIT ---")
        reasons = set(t["reason"].split("=")[0] for t in trades)
        for rp in sorted(reasons):
            rt = [t for t in trades if t["reason"].startswith(rp)]
            rw = sum(1 for t in rt if t["pnl_dollar"] > 0)
            rpnl = sum(t["pnl_dollar"] for t in rt)
            self.Log(f"  {rp}: {len(rt)} WR={rw/len(rt)*100:.0f}% PnL=${rpnl:+,.0f}")

        # Monthly (compact)
        self.Log("--- MONTHLY ---")
        by_month = {}
        for t in trades:
            mk = t["entry_date"][:7]
            if mk not in by_month:
                by_month[mk] = {"n": 0, "pnl": 0, "w": 0}
            by_month[mk]["n"] += 1
            by_month[mk]["pnl"] += t["pnl_dollar"]
            if t["pnl_dollar"] > 0:
                by_month[mk]["w"] += 1
        for m in sorted(by_month.keys()):
            d = by_month[m]
            self.Log(f"  {m}: {d['n']}t WR={d['w']/d['n']*100:.0f}% ${d['pnl']:+,.0f}")

        # Per-ticker breakdown
        self.Log("--- BY TICKER ---")
        tickers_used = set(t["ticker"] for t in trades)
        for tk in sorted(tickers_used):
            tt = [t for t in trades if t["ticker"] == tk]
            tw = sum(1 for t in tt if t["pnl_dollar"] > 0)
            tp = sum(t["pnl_dollar"] for t in tt)
            self.Log(f"  {tk}: {len(tt)}t WR={tw/len(tt)*100:.0f}% PnL=${tp:+,.0f}")

        self.Log("=" * 60)

    # ═══════════════════════════════════════════════════════════
    # HELPERS
    # ═══════════════════════════════════════════════════════════

    def _get_mid(self, sym):
        if sym is None:
            return None
        try:
            sec = self.Securities[sym]
            if sec.BidPrice > 0 and sec.AskPrice > 0:
                return (sec.BidPrice + sec.AskPrice) * 0.5
            if sec.Price > 0:
                return sec.Price
        except Exception:
            pass
        return None

    def _count_pm_touches(self, closes, pm_level):
        """Count touches of SMA20 in the last 20 bars.
        Caller passes closes[:-1] to exclude today's bar.
        """
        if len(closes) < 20 or pm_level <= 0:
            return 0
        recent = closes[-20:]
        touches = 0
        was_near = False
        for p in recent:
            near = abs(p - pm_level) / pm_level < self.pm_touch_tolerance
            if near and not was_near:
                touches += 1
            was_near = near
        return touches

    def _count_signal(self, strategy_name):
        if strategy_name not in self._strategy_signal_counts:
            self._strategy_signal_counts[strategy_name] = 0
        self._strategy_signal_counts[strategy_name] += 1
