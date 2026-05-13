# realistic_spy_trader.py
# Estrategia realista para QuantConnect con $500
# Activo: SPY | Temporalidad: 1 minuto | Estilo: Scalping conservador

from AlgorithmImports import *

class RealisticSPYTrader(QCAlgorithm):

    # ── CAPITAL Y RIESGO ──────────────────────────────────────────────
    INITIAL_CAPITAL   = 500
    MAX_DAILY_TRADES  = 6          # Menos trades = menos comisiones
    RISK_PER_TRADE    = 0.01       # Arriesga solo 1% del portafolio por trade ($5)
    PROFIT_TARGET     = 0.004      # 0.4% take profit (realista para SPY intradía)
    STOP_LOSS         = 0.002      # 0.2% stop loss (ratio 2:1)
    MAX_DAILY_LOSS    = 0.03       # Detiene operaciones si pierde 3% en el día

    # ── FILTROS DE CALIDAD ────────────────────────────────────────────
    MIN_ATR_RATIO     = 0.3        # Solo opera si hay volatilidad suficiente
    TRADE_START_MIN   = 30         # Espera 30 min tras apertura (evita ruido)
    TRADE_END_MIN     = 30         # Cierra todo 55 min antes del cierre

    def Initialize(self):
        if not self.LiveMode:
            self.SetStartDate(2023, 1, 1)
            self.SetEndDate(2024, 6, 1)
            self.SetCash(self.INITIAL_CAPITAL)
        self.SetBrokerageModel(BrokerageName.InteractiveBrokersBrokerage, AccountType.Margin)

        # Activo principal
        self.spy = self.AddEquity("SPY", Resolution.Minute).Symbol

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

        # VWAP manual (suma de precio*volumen / volumen acumulado)
        self.vwap_sum        = 0.0
        self.vwap_vol        = 0.0
        self.vwap_value      = 0.0

        # ── SCHEDULES ─────────────────────────────────────────────────
        self.Schedule.On(
            self.DateRules.EveryDay("SPY"),
            self.TimeRules.AfterMarketOpen("SPY", 1),
            self._reset_daily
        )
        self.Schedule.On(
            self.DateRules.EveryDay("SPY"),
            self.TimeRules.BeforeMarketClose("SPY", self.TRADE_END_MIN),
            self._force_close
        )
        self.Schedule.On(
            self.DateRules.EveryDay("SPY"),
            self.TimeRules.BeforeMarketClose("SPY", 2),
            self._daily_report
        )
        self.Debug("INIT OK: RealisticSPYTrader activo")

    # ── LOOP PRINCIPAL ────────────────────────────────────────────────
    def OnData(self, data):
        if not (self.spy in data and data[self.spy] is not None):
            return

        bar = data[self.spy]

        # Actualizar VWAP manualmente
        self._update_vwap(bar)

        # Gestionar posición abierta primero
        if self.in_trade:
            self._manage_position(bar.close)
            return

        # Filtros de sesión
        minutes_open = (self.Time - self.Time.replace(
            hour=9, minute=30, second=0)).total_seconds() / 60
        if minutes_open < self.TRADE_START_MIN:
            return

        # Filtro de pérdida diaria máxima
        if self.daily_pnl <= -self.MAX_DAILY_LOSS * self.INITIAL_CAPITAL:
            return

        # Límite de trades diarios
        if self.daily_trades >= self.MAX_DAILY_TRADES:
            return

        # Indicadores listos
        if not (self.ema_fast.is_ready and self.ema_slow.is_ready and
                self.rsi.is_ready and self.atr.is_ready):
            return

        price    = bar.close
        ema_f    = self.ema_fast.current.value
        ema_s    = self.ema_slow.current.value
        rsi_val  = self.rsi.current.value
        atr_val  = self.atr.current.value

        # Filtro de volatilidad mínima
        if atr_val < price * self.MIN_ATR_RATIO / 100:
            return

        # ── SEÑAL DE ENTRADA LONG ─────────────────────────────────────
        # Condiciones:
        # 1. EMA rápida > EMA lenta (tendencia alcista)
        # 2. Precio > VWAP (momentum positivo)
        # 3. RSI entre 50-65 (momentum sin sobrecompra)
        if (ema_f > ema_s and
            price > self.vwap_value and
            50 < rsi_val < 65):
            self._enter_long(price)

    def _enter_long(self, price):
        capital    = float(self.Portfolio.TotalPortfolioValue)
        risk_amt   = capital * self.RISK_PER_TRADE          # $5 en riesgo
        shares_risk = int(risk_amt / (price * self.STOP_LOSS))
        cash_available = float(self.Portfolio.CashBook["USD"].Amount) if "USD" in self.Portfolio.CashBook else float(self.Portfolio.Cash)
        shares_cash = int((cash_available * 0.98) / price)
        shares = min(shares_risk, shares_cash)

        if shares < 1:
            self.Debug(f"SKIP ENTRY: shares<1 risk={shares_risk} cash={shares_cash} price={price:.2f}")
            return

        self.MarketOrder(self.spy, shares)
        self.in_trade    = True
        self.entry_price = price
        self.stop_price  = price * (1 - self.STOP_LOSS)
        self.target_price= price * (1 + self.PROFIT_TARGET)
        self.daily_trades += 1

        self.Log(f"ENTRADA | Precio: ${price:.2f} | "
                 f"Shares: {shares} | Stop: ${self.stop_price:.2f} | "
                 f"Target: ${self.target_price:.2f}")

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
        self.daily_trades = 0
        self.daily_pnl    = 0.0
        self.vwap_sum     = 0.0
        self.vwap_vol     = 0.0
        self.vwap_value   = 0.0

    def _force_close(self):
        if self.in_trade:
            self.Liquidate(self.spy)
            self.in_trade = False
            self.Log("CIERRE FORZADO por fin de sesión")

    def _daily_report(self):
        equity   = self.Portfolio.TotalPortfolioValue
        total_t  = self.wins + self.losses
        winrate  = self.wins / total_t if total_t > 0 else 0
        self.Log(
            f"REPORTE | Equity: ${equity:.2f} | "
            f"PnL hoy: ${self.daily_pnl:.2f} | "
            f"Trades hoy: {self.daily_trades} | "
            f"Winrate total: {winrate:.1%} | "
            f"W:{self.wins} L:{self.losses}"
        )

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
