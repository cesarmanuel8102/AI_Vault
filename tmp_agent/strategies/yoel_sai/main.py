from AlgorithmImports import *
from datetime import timedelta, datetime


class YoelSAI_GapBollinger(QCAlgorithm):
    """
    Yoel SAI V2.1 - Data-Driven Fixes on V2.0 Architecture

    V2.0 RESULTS: CAGR -18.4%, Sharpe -1.69, DD 57%, WR 41%, 475 trades
    
    V2.0 FORENSIC FINDINGS applied:
    1. SL 30% → 15% : MAE data shows >15% = 10-0% WR (confirmed V1.x AND V2.0)
    2. TP 30% → 20% : 68% of losers were profitable first, avg MFE +9.4%
    3. TIME STOP 120→60 min : 2-4 hr bucket had 269 trades at 33% WR = -$46K
    4. TRAILING STOP restored: +12% activation, +5% floor (from V1.5)
    5. TICKERS reduced: SPY (WR 51%, +$2.7K), TSLA (49%, -$1.3K), AMZN (47%, -$2K)
       Removed: NVDA (32% WR, -$20K), META (36%, -$9K), QQQ (35%, -$5K)
    6. Keep: hourly BB(40,2.5) + 15-min BB(20,2) + SMAs + 10-21 day options
    7. Keep: Both PUTs and CALLs (SPY PUT WR 59%, TSLA CALL WR 55%)

    KEY V1.x FINDINGS REAPPLIED:
    - V1.1b: 0-30 min trades had 96-100% WR (direction is correct early)
    - V1.5: PUTs-only PF 0.92, closest to breakeven
    - MAE cliff at 15% confirmed across ALL versions (V1.x and V2.0)
    """

    def Initialize(self):
        start_year = int(self.GetParameter("start_year") or 2021)
        end_year = int(self.GetParameter("end_year") or 2024)
        end_month = int(self.GetParameter("end_month") or 12)

        self.SetStartDate(start_year, 1, 1)
        self.SetEndDate(end_year, end_month, 28)
        self.SetCash(100000)
        self.SetBrokerageModel(BrokerageName.InteractiveBrokersBrokerage, AccountType.Margin)

        # ============================================================
        # MULTI-TICKER UNIVERSE — V2.1: Only top 3 tickers from V2.0 forensics
        # SPY (WR 51%, +$2.7K), TSLA (49%, -$1.3K), AMZN (47%, -$2K)
        # ============================================================
        self.tickers = ["SPY", "TSLA", "AMZN"]

        self.equity_symbols = {}
        self.option_symbols = {}
        self.indicators = {}

        for ticker in self.tickers:
            equity = self.AddEquity(ticker, Resolution.Minute)
            equity.SetDataNormalizationMode(DataNormalizationMode.Raw)
            self.equity_symbols[ticker] = equity.Symbol

            option = self.AddOption(ticker, Resolution.Minute)
            option.SetFilter(lambda u: u.Strikes(-10, 10).Expiration(10, 21))
            self.option_symbols[ticker] = option.Symbol

            bb_hourly = BollingerBands(40, 2.5, MovingAverageType.Simple)
            sma20h = SimpleMovingAverage(20)
            sma40h = SimpleMovingAverage(40)
            bb_15m = BollingerBands(20, 2, MovingAverageType.Simple)
            sma20_15m = SimpleMovingAverage(20)
            sma50_15m = SimpleMovingAverage(50)

            cons_1h = TradeBarConsolidator(timedelta(hours=1))
            cons_1h.DataConsolidated += lambda s, b, t=ticker: self.OnHourly(s, b, t)
            self.SubscriptionManager.AddConsolidator(equity.Symbol, cons_1h)

            cons_15m = TradeBarConsolidator(timedelta(minutes=15))
            cons_15m.DataConsolidated += lambda s, b, t=ticker: self.On15Min(s, b, t)
            self.SubscriptionManager.AddConsolidator(equity.Symbol, cons_15m)

            self.indicators[ticker] = {
                "bb_hourly": bb_hourly,
                "sma20h": sma20h,
                "sma40h": sma40h,
                "bb_15m": bb_15m,
                "sma20_15m": sma20_15m,
                "sma50_15m": sma50_15m,
            }

        self.ref_symbol = self.equity_symbols["SPY"]

        # ============================================================
        # STATE
        # ============================================================
        self.today_traded = False
        self.trades_this_week = 0
        self.current_week = -1
        # option_symbol -> {"entry", "qty", "entry_time", "ticker", "max_price"}
        self.active_positions = {}

        # ============================================================
        # PARAMETERS — V2.1 (data-driven from V2.0 + V1.x forensics)
        # ============================================================
        self.BB_PROXIMITY = 0.002       # ~0.2% — "near or beyond" hourly BB
        self.TP_PCT = 0.20              # V2.1: 30%→20% (68% losers were profitable first)
        self.SL_PCT = 0.15              # V2.1: 30%→15% (MAE >15% = dead, confirmed 2x)
        self.TIME_STOP_MINUTES = 60     # V2.1: 120→60 min (2-4hr bucket destroys)
        self.TRAIL_ACTIVATION = 0.12    # V2.1: restored from V1.5 (protect early gains)
        self.TRAIL_FLOOR = 0.05         # V2.1: lock 5% profit once +12% hit
        self.POS_SIZE = 0.05
        self.MAX_TRADES_WEEK = 3

        # ============================================================
        # SCHEDULING
        # ============================================================
        self.Schedule.On(
            self.DateRules.EveryDay(self.ref_symbol),
            self.TimeRules.AfterMarketOpen(self.ref_symbol, 0),
            self.NewDay)

        self.Schedule.On(
            self.DateRules.EveryDay(self.ref_symbol),
            self.TimeRules.At(15, 0),
            self.CloseDayTrades)

        self.SetWarmUp(timedelta(days=90))

        # ============================================================
        # TRACKING
        # ============================================================
        self.total_entries = 0
        self.put_entries = 0
        self.call_entries = 0
        self.sl_exits = 0
        self.tp_exits = 0
        self.eod_exits = 0
        self.time_stop_exits = 0
        self.trail_exits = 0
        self.entries_by_ticker = {}

    # ================================================================
    #  CONSOLIDATOR HANDLERS
    # ================================================================
    def On15Min(self, sender, bar, ticker):
        ind = self.indicators[ticker]
        ind["bb_15m"].Update(bar.EndTime, bar.Close)
        ind["sma20_15m"].Update(bar.EndTime, bar.Close)
        ind["sma50_15m"].Update(bar.EndTime, bar.Close)

    def OnHourly(self, sender, bar, ticker):
        ind = self.indicators[ticker]
        ind["bb_hourly"].Update(bar.EndTime, bar.Close)
        ind["sma20h"].Update(bar.EndTime, bar.Close)
        ind["sma40h"].Update(bar.EndTime, bar.Close)

    # ================================================================
    #  SCHEDULED EVENTS
    # ================================================================
    def NewDay(self):
        self.today_traded = False
        w = self.Time.isocalendar()[1]
        if w != self.current_week:
            self.trades_this_week = 0
            self.current_week = w

    def CloseDayTrades(self):
        for sym in list(self.active_positions.keys()):
            if self.Portfolio[sym].Invested:
                self.Liquidate(sym, tag="EOD-3PM")
                self.eod_exits += 1
            self.active_positions.pop(sym, None)

    # ================================================================
    #  MAIN LOGIC
    # ================================================================
    def OnData(self, slice):
        if self.IsWarmingUp:
            return

        self.ManagePositions()

        if self.today_traded or self.trades_this_week >= self.MAX_TRADES_WEEK:
            return
        if self.Portfolio.Invested:
            return

        market_open = self.Time.replace(hour=9, minute=30, second=0)
        mins_since_open = (self.Time - market_open).total_seconds() / 60.0
        if mins_since_open < 1 or mins_since_open > 15:
            return

        candidates = []

        for ticker in self.tickers:
            sym = self.equity_symbols[ticker]
            ind = self.indicators[ticker]

            if not (ind["bb_hourly"].IsReady and ind["bb_15m"].IsReady
                    and ind["sma20_15m"].IsReady and ind["sma50_15m"].IsReady):
                continue

            if not slice.Bars.ContainsKey(sym):
                continue

            price = self.Securities[sym].Price
            if price == 0:
                continue

            bb_h_upper = ind["bb_hourly"].UpperBand.Current.Value
            bb_h_lower = ind["bb_hourly"].LowerBand.Current.Value
            bb_15_upper = ind["bb_15m"].UpperBand.Current.Value
            bb_15_lower = ind["bb_15m"].LowerBand.Current.Value
            sma20 = ind["sma20_15m"].Current.Value
            sma50 = ind["sma50_15m"].Current.Value

            proximity = bb_h_upper * self.BB_PROXIMITY

            # PUT: price above upper hourly BB
            if price >= (bb_h_upper - proximity):
                if price > bb_15_upper:
                    if price > sma20 and price > sma50:
                        overext = (price - bb_h_upper) / bb_h_upper
                        candidates.append((ticker, OptionRight.Put, overext))

            # CALL: price below lower hourly BB
            if price <= (bb_h_lower + proximity):
                if price < bb_15_lower:
                    if price < sma20 and price < sma50:
                        overext = (bb_h_lower - price) / bb_h_lower
                        candidates.append((ticker, OptionRight.Call, overext))

        if not candidates:
            return

        candidates.sort(key=lambda x: x[2], reverse=True)
        best_ticker, best_right, best_overext = candidates[0]

        direction = "PUT" if best_right == OptionRight.Put else "CALL"
        tag = f"V21-{best_ticker}-{direction}"

        self.TryBuy(slice, best_ticker, best_right, tag)

    # ================================================================
    #  POSITION MANAGEMENT — V2.1 (SL 15% + Trail + Time 60min)
    # ================================================================
    def ManagePositions(self):
        for sym in list(self.active_positions.keys()):
            if not self.Portfolio[sym].Invested:
                self.active_positions.pop(sym, None)
                continue

            info = self.active_positions.get(sym)
            if info is None:
                continue

            entry = info["entry"]
            current = self.Securities[sym].Price
            if current <= 0 or entry <= 0:
                continue

            pnl_pct = (current - entry) / entry

            # Update max price for trailing stop
            if current > info.get("max_price", entry):
                info["max_price"] = current
            max_price = info.get("max_price", entry)

            # --- 1. HARD STOP LOSS at 15% ---
            if pnl_pct <= -self.SL_PCT:
                self.Liquidate(sym, tag=f"SL15@{current:.2f}")
                self.sl_exits += 1
                self.active_positions.pop(sym, None)
                continue

            # --- 2. TIME STOP at 60 minutes ---
            entry_time = info.get("entry_time")
            if entry_time is not None:
                hold_mins = (self.Time - entry_time).total_seconds() / 60.0
                if hold_mins >= self.TIME_STOP_MINUTES:
                    self.Liquidate(sym, tag=f"TIME60@{current:.2f}")
                    self.time_stop_exits += 1
                    self.active_positions.pop(sym, None)
                    continue

            # --- 3. TRAILING STOP: once +12%, floor at +5% ---
            max_pnl = (max_price - entry) / entry
            if max_pnl >= self.TRAIL_ACTIVATION:
                floor_price = entry * (1.0 + self.TRAIL_FLOOR)
                if current <= floor_price:
                    self.Liquidate(sym, tag=f"TRAIL@{current:.2f}")
                    self.trail_exits += 1
                    self.active_positions.pop(sym, None)
                    continue

    # ================================================================
    #  ORDER EXECUTION
    # ================================================================
    def TryBuy(self, slice, ticker, right, tag):
        opt_sym = self.option_symbols[ticker]
        chain = slice.OptionChains.get(opt_sym)
        if chain is None:
            return

        px = self.Securities[self.equity_symbols[ticker]].Price

        contracts = [c for c in chain
                     if c.Right == right
                     and c.Expiry > self.Time + timedelta(days=9)
                     and c.Expiry <= self.Time + timedelta(days=22)
                     and c.AskPrice > 0.10
                     and c.AskPrice < 20.0]

        if not contracts:
            return

        if right == OptionRight.Call:
            otm = [c for c in contracts if c.Strike > px]
            if not otm:
                return
            otm.sort(key=lambda c: c.Strike)
            contract = otm[0]
        else:
            otm = [c for c in contracts if c.Strike < px]
            if not otm:
                return
            otm.sort(key=lambda c: c.Strike, reverse=True)
            contract = otm[0]

        ask = contract.AskPrice
        if ask <= 0:
            return

        max_invest = self.Portfolio.TotalPortfolioValue * self.POS_SIZE
        qty = max(1, int(max_invest / (ask * 100)))
        qty = min(qty, 30)

        self.MarketOrder(contract.Symbol, qty, tag=tag)
        self.active_positions[contract.Symbol] = {
            "entry": ask,
            "qty": qty,
            "entry_time": self.Time,
            "ticker": ticker,
            "max_price": ask,
        }
        self.today_traded = True
        self.trades_this_week += 1
        self.total_entries += 1

        self.entries_by_ticker[ticker] = self.entries_by_ticker.get(ticker, 0) + 1

        if right == OptionRight.Put:
            self.put_entries += 1
        else:
            self.call_entries += 1

    def OnOrderEvent(self, orderEvent):
        if orderEvent.Status != OrderStatus.Filled:
            return
        sym = orderEvent.Symbol
        if sym.SecurityType != SecurityType.Option:
            return

        if orderEvent.FillQuantity > 0:
            fill_px = orderEvent.FillPrice
            tp = round(fill_px * (1.0 + self.TP_PCT), 2)
            qty = orderEvent.FillQuantity
            self.LimitOrder(sym, -qty, tp, tag=f"TP20@{tp:.2f}")
            self.Plot("Trades", "Entry", fill_px)

            if sym in self.active_positions:
                self.active_positions[sym]["entry"] = fill_px
                self.active_positions[sym]["max_price"] = fill_px

        elif orderEvent.FillQuantity < 0:
            info = self.active_positions.get(sym)
            if info is not None:
                entry = info["entry"]
                pnl_pct = (orderEvent.FillPrice - entry) / entry * 100 if entry > 0 else 0
                self.Plot("Trades", "Exit P&L %", pnl_pct)
                if orderEvent.FillPrice >= entry * (1.0 + self.TP_PCT * 0.9):
                    self.tp_exits += 1
                self.active_positions.pop(sym, None)

    def OnEndOfAlgorithm(self):
        self.Log(f"=== SUMMARY V2.1 ===")
        self.Log(f"Total entries: {self.total_entries}")
        self.Log(f"PUT entries: {self.put_entries}")
        self.Log(f"CALL entries: {self.call_entries}")
        self.Log(f"--- Entries by ticker ---")
        for t, count in sorted(self.entries_by_ticker.items(), key=lambda x: -x[1]):
            self.Log(f"  {t}: {count}")
        self.Log(f"--- Exit breakdown ---")
        self.Log(f"TP exits: {self.tp_exits}")
        self.Log(f"SL exits: {self.sl_exits}")
        self.Log(f"TIME STOP exits: {self.time_stop_exits}")
        self.Log(f"TRAIL exits: {self.trail_exits}")
        self.Log(f"EOD exits: {self.eod_exits}")
