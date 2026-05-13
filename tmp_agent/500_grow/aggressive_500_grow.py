# aggressive_500_grow.py
from AlgorithmImports import *
import numpy as np

class Aggressive500Grow(QCAlgorithm):
    
    # CRITICAL SETTINGS FOR $500
    INITIAL_CAPITAL = 500
    MAX_DAILY_TRADES = 10
    MAX_ENTRY_PCT = 0.04  # $20 por operación (4% de $500)
    PROFIT_TARGET = 0.15   # 15% de ganancia por trade
    STOP_LOSS = 0.07      # 7% stop-loss
    
    # AUTONOMOUS LOOP PARAMETERS
    REOPTIMIZE_THRESHOLD = -0.05  # Reajustar si rentabilidad diaria < -5%
    POSITION_SIZE_ADJ = 0.1       # Ajustar tamaño 10% tras 3 trades exitosos

    def Initialize(self):
        self.SetStartDate(2026, 1, 1)
        self.SetEndDate(2026, 12, 4)
        self.SetCash(self.INITIAL_CAPITAL)
        self.SetBrokerageModel(InteractiveBrokersBrokerageModel(AccountType.Margin))
        self.SetMarginCallModel(MarginCallModel.CashFirst)
        
        # SPY options para operaciones intradía (costo bajo)
        self.symbol = self.AddOption("SPY", Resolution.Minute)
        self.symbol.SetFilter(lambda u: u.Strikes(-1, 1).Expiration(0, 2))

        # Indicadores de alta frecuencia
        self.ema5 = self.EMA("SPY", 5, Resolution.Minute, Field.Close)
        self.atr = self.ATR("SPY", 10, Resolution.Minute)

        # Variables de control
        self.open_position = False
        self.last_trade_profit = 0.0
        self.daily_trades = 0
        self.position_size = 1  # 1 contrato por defecto
        
        # Schedules
        self.Schedule.On(self.DateRules.EveryDay("SPY"),
                         self.TimeRules.AfterMarketOpen("SPY", 5),
                         self._reoptimize)
        self.Schedule.On(self.DateRules.EveryDay("SPY"),
                         self.TimeRules.BeforeMarketClose("SPY", 5),
                         self._daily_report)

    def OnData(self, data):
        if self.daily_trades >= self.MAX_DAILY_TRADES or self.open_position:
            return
            
        if self.ema5.IsReady and data.ContainsKey(self.symbol):
            # Detectar tendencia intradía
            price = data[self.symbol].Close
            ema = self.ema5.Current.Value
            atr = self.atr.Current.Value

            # Entrada agresiva si price > EMA5 + 0.5*ATR (momentum alcista)
            if price > ema + 0.5*atr and self.Portfolio.Cash > price * self.position_size * 100:
                self.OpenLongPosition()
                
    def OpenLongPosition(self):
        price = self.Securities[self.symbol].Price
        size = int(self.Portfolio.Cash * self.MAX_ENTRY_PCT / (price * 100))
        
        # Ajustar tamaño por estrategia autónoma
        if self.last_trade_profit > 0:
            self.position_size = min(self.position_size * (1 + self.POSITION_SIZE_ADJ), 5)
            
        self.MarketOrder(self.symbol, size)
        self.open_position = True
        self.stop_loss = price * (1 - self.STOP_LOSS)
        self.profit_target = price * (1 + self.PROFIT_TARGET)
        self.daily_trades += 1

    def ManagePosition(self):
        if not self.open_position:
            return
        current = self.Securities[self.symbol].Price
        
        # Salida por stop-loss
        if current <= self.stop_loss:
            self.Liquidate(self.symbol)
            self.open_position = False
            
        # Salida por profit target
        elif current >= self.profit_target:
            self.Liquidate(self.symbol)
            self.open_position = False
            self.last_trade_profit = (current - self.stop_loss) / self.stop_loss
            
        # Salida por cierre del mercado (máximo 10 minutos)
        elif self.Time.minute >= 10:
            self.Liquidate(self.symbol)
            self.open_position = False

    def _reoptimize(self):
        # Auto-sistema: reajustar parámetros tras bajo desempeño diario
        if self.Portfolio.TotalProfit < self.REOPTIMIZE_THRESHOLD * self.INITIAL_CAPITAL:
            self.MAX_DAILY_TRADES = max(10, self.MAX_DAILY_TRADES - 1)
            self.MAX_ENTRY_PCT *= 0.95

    def _daily_report(self):
        self.Log(f"DAILY REPORT | Equity: ${self.Portfolio.TotalPortfolioValue:.2f} | "
                f"Trades: {self.daily_trades} | Winrate: {self.CalculateWinRate():.1%}")

    def CalculateWinRate(self):
        trades = self.TradeBuilder.GetTrades()
        wins = [t for t in trades if t.ClosedProfit > 0]
        return len(wins) / len(trades) if len(trades) > 0 else 1.0

    def OnEndOfAlgorithm(self):
        self.Log("AGGRESSIVE_500: Final Equity = " + str(self.Portfolio.TotalPortfolioValue))