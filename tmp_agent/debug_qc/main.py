# realistic_spy_trader.py
# Estrategia realista para QuantConnect con $500
# Activo: SPY | Temporalidad: 1 minuto | Estilo: Scalping conservador

from AlgorithmImports import *

class RealisticSPYTrader(QCAlgorithm):

    # ── CAPITAL Y RIESGO ──────────────────────────────────────────────
    INITIAL_CAPITAL   = 500
    MAX_DAILY_TRADES  = 2          # Reducir frecuencia para no quemar en comisiones
    RISK_PER_TRADE    = 0.01       # Arriesga solo 1% del portafolio por trade ($5)
    PROFIT_TARGET     = 0.012      # 1.2% TP base: buscar superar round-trip fee
    STOP_LOSS         = 0.004      # 0.4% SL base
    MAX_DAILY_LOSS    = 0.03       # Detiene operaciones si pierde 3% en el día

    # ── FILTROS DE CALIDAD ────────────────────────────────────────────
    MIN_ATR_RATIO     = 0.2        # Filtro menos estricto para permitir mas entradas
    TRADE_START_MIN   = 5          # Inicia pronto para no perder la primera hora
    TRADE_END_MIN     = 30         # Cierra todo 55 min antes del cierre
    DIAG_EVERY_MIN    = 15         # Ritmo de logs de diagnostico de no-entrada
    TARGET_MULTIPLIER = 2.0        # Objetivo del ciclo: duplicar capital
    TARGET_CYCLE_DAYS = 63         # ~trimestre de mercado
    MAX_RISK_PER_TRADE = 0.04      # Techo de riesgo por trade en modo catch-up
    CATCHUP_RISK_MULT = 3.0        # Intensidad de aceleracion cuando va atrasado
    MIN_GROSS_EDGE_USD = 3.0       # Ganancia bruta minima esperada para justificar comisiones

    def Initialize(self):
        # Parametros de backtest (GetParameter solo afecta BT; live usa defaults)
        bt_start_year = self._p_int("start_year", 2024)
        bt_start_month = self._p_int("start_month", 1)
        bt_start_day = self._p_int("start_day", 1)
        bt_end_year = self._p_int("end_year", 2026)
        bt_end_month = self._p_int("end_month", 4)
        bt_end_day = self._p_int("end_day", 10)

        if not self.LiveMode:
            self.SetStartDate(bt_start_year, bt_start_month, bt_start_day)
            self.SetEndDate(bt_end_year, bt_end_month, bt_end_day)
            self.SetCash(self.INITIAL_CAPITAL)

        # Parametros de estrategia para barridos/matriz
        self.min_atr_ratio = self._p_float("min_atr_ratio", self.MIN_ATR_RATIO)
        self.trade_start_min = self._p_int("trade_start_min", self.TRADE_START_MIN)
        self.trade_end_min = self._p_int("trade_end_min", self.TRADE_END_MIN)
        self.diag_every_min = self._p_int("diag_every_min", self.DIAG_EVERY_MIN)
        self.rsi_low = self._p_float("rsi_low", 40.0)
        self.rsi_high = self._p_float("rsi_high", 55.0)
        self.stop_loss = self._p_float("stop_loss", self.STOP_LOSS)
        self.profit_target = self._p_float("profit_target", self.PROFIT_TARGET)
        self.risk_per_trade = self._p_float("risk_per_trade", self.RISK_PER_TRADE)
        self.max_daily_trades = self._p_int("max_daily_trades", self.MAX_DAILY_TRADES)
        self.min_gross_edge_usd = self._p_float("min_gross_edge_usd", self.MIN_GROSS_EDGE_USD)
        self.entry_mode = (self.GetParameter("entry_mode") or "pullback").lower()
        self.vwap_pullback_buffer = self._p_float("vwap_pullback_buffer", 0.0015)
        self.min_trend_strength = self._p_float("min_trend_strength", 0.0008)
        self.target_multiplier = self._p_float("target_multiplier", self.TARGET_MULTIPLIER)
        self.target_cycle_days = self._p_int("target_cycle_days", self.TARGET_CYCLE_DAYS)
        self.max_risk_per_trade = self._p_float("max_risk_per_trade", self.MAX_RISK_PER_TRADE)
        self.catchup_risk_mult = self._p_float("catchup_risk_mult", self.CATCHUP_RISK_MULT)
        raw_symbol = self.GetParameter("trade_symbol") or self.GetParameter("ticker") or "SPY"
        self.trade_symbol = str(raw_symbol).upper()

        self.SetBrokerageModel(BrokerageName.InteractiveBrokersBrokerage, AccountType.Margin)

        # Activo principal (por defecto SPY; usar trade_symbol=TQQQ si quieres modo mas agresivo)
        self.spy = self.AddEquity(self.trade_symbol, Resolution.Minute).Symbol

        # ── INDICADORES ───────────────────────────────────────────────
        self.ema_fast  = self.EMA(self.spy, 9,  Resolution.Minute)
        self.ema_slow  = self.EMA(self.spy, 21, Resolution.Minute)
        self.rsi       = self.RSI(self.spy, 14, MovingAverageType.Wilders, Resolution.Minute)
        self.atr       = self.ATR(self.spy, 14, MovingAverageType.Simple,  Resolution.Minute)

        # ── ESTADO ────────────────────────────────────────────────────
        self.in_trade       = False
        self.entry_price    = 0.0
        self.stop_price     = 0.0
        self.target_price   = 0.0
        self.daily_trades   = 0
        self.daily_pnl      = 0.0
        self.wins           = 0
        self.losses         = 0
        self.last_diag_bucket = -1
        self.daily_loss_limit = self.MAX_DAILY_LOSS * self.INITIAL_CAPITAL

        # Estado de ciclos de crecimiento (objetivo: duplicar periodicamente)
        self.cycle_index = 1
        self.cycle_start_date = None
        self.cycle_start_equity = float(self.INITIAL_CAPITAL)
        self.cycle_target_equity = self.cycle_start_equity * self.target_multiplier

        # VWAP manual (suma de precio*volumen / volumen acumulado)
        self.vwap_sum        = 0.0
        self.vwap_vol        = 0.0
        self.vwap_value      = 0.0

        # ── SCHEDULES ─────────────────────────────────────────────────
        self.Schedule.On(
            self.DateRules.EveryDay(self.trade_symbol),
            self.TimeRules.AfterMarketOpen(self.trade_symbol, 1),
            self._reset_daily
        )
        self.Schedule.On(
            self.DateRules.EveryDay(self.trade_symbol),
            self.TimeRules.BeforeMarketClose(self.trade_symbol, self.trade_end_min),
            self._force_close
        )
        self.Schedule.On(
            self.DateRules.EveryDay(self.trade_symbol),
            self.TimeRules.BeforeMarketClose(self.trade_symbol, 2),
            self._daily_report
        )
        self.Debug("INIT OK: RealisticSPYTrader activo")
        self.Debug(
            f"PARAMS | symbol={self.trade_symbol} | atr>={self.min_atr_ratio:.3f}% | start={self.trade_start_min}m | "
            f"end={self.trade_end_min}m | rsi=({self.rsi_low:.1f},{self.rsi_high:.1f}) | "
            f"sl={self.stop_loss:.4f} | tp={self.profit_target:.4f} | edge>={self.min_gross_edge_usd:.2f}$ | "
            f"trend>={self.min_trend_strength:.4%} | "
            f"entry={self.entry_mode} | target=x{self.target_multiplier:.2f}/{self.target_cycle_days}d"
        )

    # ── LOOP PRINCIPAL ────────────────────────────────────────────────
    def OnData(self, data):
        if not (self.spy in data and data[self.spy] is not None):
            return

        bar = data[self.spy]
        price = bar.close

        # Actualizar VWAP manualmente
        self._update_vwap(bar)

        # Gestionar posición abierta primero
        if self.in_trade:
            self._manage_position(bar.close)
            return

        # Filtros de sesión
        minutes_open = (self.Time - self.Time.replace(
            hour=9, minute=30, second=0)).total_seconds() / 60
        max_session_minutes = 390 - self.trade_end_min
        if minutes_open < self.trade_start_min:
            self._maybe_diag("pre_open_window", price=price)
            return
        if minutes_open > max_session_minutes:
            self._maybe_diag("post_cutoff_window", price=price)
            return

        # Filtro de pérdida diaria máxima
        if self.daily_pnl <= -self.daily_loss_limit:
            self._maybe_diag("max_daily_loss", price=price)
            return

        # Límite de trades diarios
        if self.daily_trades >= self.max_daily_trades:
            self._maybe_diag("max_daily_trades", price=price)
            return

        # Indicadores listos
        if not (self.ema_fast.is_ready and self.ema_slow.is_ready and
                self.rsi.is_ready and self.atr.is_ready):
            self._maybe_diag("indicators_not_ready", price=price)
            return

        ema_f    = self.ema_fast.current.value
        ema_s    = self.ema_slow.current.value
        rsi_val  = self.rsi.current.value
        atr_val  = self.atr.current.value
        cycle = self._cycle_stats()
        trend_strength = (ema_f - ema_s) / ema_s if ema_s else 0.0

        # Acelera al ir atrasado del objetivo de duplicacion
        catchup = cycle["catchup_factor"]
        eff_min_atr = max(0.05, self.min_atr_ratio * (1.0 - 0.45 * catchup))
        eff_rsi_low = max(35.0, self.rsi_low - 8.0 * catchup)
        eff_rsi_high = min(80.0, self.rsi_high + 8.0 * catchup)

        # Filtro de volatilidad mínima
        if atr_val < price * eff_min_atr / 100:
            self._maybe_diag("atr_filter", price, ema_f, ema_s, rsi_val, atr_val)
            return

        if trend_strength < self.min_trend_strength:
            self._maybe_diag("weak_trend", price, ema_f, ema_s, rsi_val, atr_val)
            return

        # ── SEÑAL DE ENTRADA LONG ─────────────────────────────────────
        # Modo pullback (default): en tendencia alcista, compra retroceso cerca/debajo de VWAP.
        long_signal = False
        if self.entry_mode == "pullback":
            near_vwap = price <= self.vwap_value * (1.0 + self.vwap_pullback_buffer)
            bullish_reclaim_bar = bar.close > bar.open
            long_signal = (ema_f > ema_s and near_vwap and bullish_reclaim_bar and eff_rsi_low < rsi_val < eff_rsi_high)
        else:
            # Modo momentum legacy para pruebas comparativas
            long_signal = (ema_f > ema_s and price > self.vwap_value and eff_rsi_low < rsi_val < eff_rsi_high)

        if long_signal:
            self._enter_long(price)
        else:
            self._maybe_diag("signal_filter", price, ema_f, ema_s, rsi_val, atr_val)

    def _enter_long(self, price):
        capital    = float(self.Portfolio.TotalPortfolioValue)
        risk_pct = self._effective_risk_per_trade()
        risk_amt   = capital * risk_pct          # riesgo dinamico por parametro/ciclo
        shares_risk = int(risk_amt / (price * self.stop_loss))
        cash_available = float(self.Portfolio.CashBook["USD"].Amount) if "USD" in self.Portfolio.CashBook else float(self.Portfolio.Cash)
        shares_cash = int((cash_available * 0.98) / price)
        shares = min(shares_risk, shares_cash)

        if shares < 1:
            self.Debug(f"SKIP ENTRY: shares<1 risk={shares_risk} cash={shares_cash} price={price:.2f}")
            return

        expected_gross_target = shares * price * self.profit_target
        if expected_gross_target < self.min_gross_edge_usd:
            self.Debug(
                f"SKIP ENTRY: edge low grossTP=${expected_gross_target:.2f} "
                f"< min=${self.min_gross_edge_usd:.2f} shares={shares} price={price:.2f}"
            )
            return

        self.MarketOrder(self.spy, shares)
        self.in_trade    = True
        self.entry_price = price
        self.stop_price  = price * (1 - self.stop_loss)
        self.target_price= price * (1 + self.profit_target)
        self.daily_trades += 1

        self.Log(f"ENTRADA | Precio: ${price:.2f} | "
                 f"Shares: {shares} | Stop: ${self.stop_price:.2f} | "
                 f"Target: ${self.target_price:.2f} | Risk%: {risk_pct:.3%}")

    def _manage_position(self, price):
        # Stop loss
        if price <= self.stop_price:
            pnl = (price - self.entry_price) * self.Portfolio[self.spy].Quantity
            self.Liquidate(self.spy)
            self.in_trade = False
            self.daily_pnl += pnl
            self.losses += 1
            self.Log(f"STOP LOSS | Precio: ${price:.2f} | PnL: ${pnl:.2f}")

        # Take profit
        elif price >= self.target_price:
            pnl = (price - self.entry_price) * self.Portfolio[self.spy].Quantity
            self.Liquidate(self.spy)
            self.in_trade = False
            self.daily_pnl += pnl
            self.wins += 1
            self.Log(f"TAKE PROFIT | Precio: ${price:.2f} | PnL: ${pnl:.2f}")

    def _update_vwap(self, bar):
        typical = (bar.high + bar.low + bar.close) / 3
        self.vwap_sum += typical * bar.volume
        self.vwap_vol += bar.volume
        if self.vwap_vol > 0:
            self.vwap_value = self.vwap_sum / self.vwap_vol

    def _reset_daily(self):
        self._roll_cycle_if_needed()
        self.daily_trades = 0
        self.daily_pnl    = 0.0
        self.vwap_sum     = 0.0
        self.vwap_vol     = 0.0
        self.vwap_value   = 0.0
        ref_equity = max(float(self.Portfolio.TotalPortfolioValue), self.cycle_start_equity, float(self.INITIAL_CAPITAL))
        self.daily_loss_limit = self.MAX_DAILY_LOSS * ref_equity

    def _force_close(self):
        if self.in_trade:
            self.Liquidate(self.spy)
            self.in_trade = False
            self.Log("CIERRE FORZADO por fin de sesión")

    def _daily_report(self):
        equity   = self.Portfolio.TotalPortfolioValue
        total_t  = self.wins + self.losses
        winrate  = self.wins / total_t if total_t > 0 else 0
        cycle = self._cycle_stats()
        self.Log(
            f"REPORTE | Equity: ${equity:.2f} | "
            f"PnL hoy: ${self.daily_pnl:.2f} | "
            f"Trades hoy: {self.daily_trades} | "
            f"Winrate total: {winrate:.1%} | "
            f"W:{self.wins} L:{self.losses} | "
            f"Ciclo {self.cycle_index}: ${cycle['equity']:.2f}/${cycle['target']:.2f} ({cycle['progress_to_target']:.1%}) d={cycle['days_elapsed']}"
        )

    def _maybe_diag(self, reason, price=None, ema_f=None, ema_s=None, rsi_val=None, atr_val=None):
        bucket = int((self.Time.hour * 60 + self.Time.minute) / max(1, self.diag_every_min))
        if bucket == self.last_diag_bucket:
            return
        self.last_diag_bucket = bucket

        parts = [f"reason={reason}", f"time={self.Time:%Y-%m-%d %H:%M}", f"trades={self.daily_trades}"]
        if price is not None:
            parts.append(f"px={price:.2f}")
        if ema_f is not None and ema_s is not None:
            parts.append(f"ema9={ema_f:.2f}")
            parts.append(f"ema21={ema_s:.2f}")
        if rsi_val is not None:
            parts.append(f"rsi={rsi_val:.2f}")
        if atr_val is not None and price is not None:
            atr_pct = (atr_val / price) * 100 if price else 0.0
            parts.append(f"atr%={atr_pct:.3f}")
        if self.vwap_value:
            parts.append(f"vwap={self.vwap_value:.2f}")
        self.Debug("DIAG | " + " | ".join(parts))

    def _p_int(self, name, default):
        raw = self.GetParameter(name)
        if raw is None or raw == "":
            return default
        try:
            return int(float(raw))
        except Exception:
            self.Debug(f"PARAM_WARN int {name}={raw}, using {default}")
            return default

    def _p_float(self, name, default):
        raw = self.GetParameter(name)
        if raw is None or raw == "":
            return default
        try:
            return float(raw)
        except Exception:
            self.Debug(f"PARAM_WARN float {name}={raw}, using {default}")
            return default

    def _cycle_stats(self):
        equity = float(self.Portfolio.TotalPortfolioValue)
        target = max(1.0, float(self.cycle_target_equity))
        if self.cycle_start_date is None:
            days_elapsed = 0
        else:
            days_elapsed = max(0, (self.Time.date() - self.cycle_start_date).days)

        time_progress = min(1.0, days_elapsed / max(1, self.target_cycle_days))
        target_progress = equity / target
        catchup_factor = max(0.0, time_progress - target_progress)
        return {
            "equity": equity,
            "target": target,
            "days_elapsed": days_elapsed,
            "time_progress": time_progress,
            "progress_to_target": target_progress,
            "catchup_factor": catchup_factor,
        }

    def _effective_risk_per_trade(self):
        cycle = self._cycle_stats()
        mult = 1.0 + cycle["catchup_factor"] * self.catchup_risk_mult
        return min(self.max_risk_per_trade, self.risk_per_trade * mult)

    def _roll_cycle_if_needed(self):
        equity = float(self.Portfolio.TotalPortfolioValue)
        if self.cycle_start_date is None:
            self.cycle_start_date = self.Time.date()
            self.cycle_start_equity = equity
            self.cycle_target_equity = self.cycle_start_equity * self.target_multiplier
            self.Log(
                f"CYCLE START #{self.cycle_index} | start=${self.cycle_start_equity:.2f} "
                f"| target=${self.cycle_target_equity:.2f} | days={self.target_cycle_days}"
            )
            return

        days_elapsed = max(0, (self.Time.date() - self.cycle_start_date).days)
        hit_target = equity >= self.cycle_target_equity
        expired = days_elapsed >= self.target_cycle_days
        if not (hit_target or expired):
            return

        status = "HIT" if hit_target else "MISS"
        progress = equity / max(1.0, self.cycle_target_equity)
        self.Log(
            f"CYCLE {status} #{self.cycle_index} | equity=${equity:.2f} | "
            f"target=${self.cycle_target_equity:.2f} | progress={progress:.1%} | days={days_elapsed}"
        )

        self.cycle_index += 1
        self.cycle_start_date = self.Time.date()
        self.cycle_start_equity = equity
        self.cycle_target_equity = self.cycle_start_equity * self.target_multiplier

    def OnEndOfAlgorithm(self):
        equity  = self.Portfolio.TotalPortfolioValue
        ret_pct = (equity - self.INITIAL_CAPITAL) / self.INITIAL_CAPITAL * 100
        self.Log(
            f"\n{'='*50}\n"
            f"RESULTADO FINAL\n"
            f"Capital inicial: ${self.INITIAL_CAPITAL}\n"
            f"Capital final:   ${equity:.2f}\n"
            f"Retorno total:   {ret_pct:.1f}%\n"
            f"Wins: {self.wins} | Losses: {self.losses}\n"
            f"{'='*50}"
        )
