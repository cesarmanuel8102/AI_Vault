"""
AI_VAULT Backtest Engine v1.0
Motor de simulación y backtesting para Fase 6.1
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from enum import Enum
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class StrategyType(Enum):
    MOMENTUM = "momentum"
    MEAN_REVERSION = "mean_reversion"
    BREAKOUT = "breakout"
    TREND_FOLLOWING = "trend_following"

@dataclass
class Trade:
    """Trade simulado"""
    entry_date: datetime
    exit_date: Optional[datetime]
    symbol: str
    side: str  # 'long' o 'short'
    entry_price: float
    exit_price: Optional[float]
    quantity: int
    pnl: float = 0.0
    return_pct: float = 0.0
    
    def calculate_pnl(self):
        """Calcular P&L del trade"""
        if self.exit_price:
            if self.side == 'long':
                self.pnl = (self.exit_price - self.entry_price) * self.quantity
                self.return_pct = (self.exit_price / self.entry_price - 1) * 100
            else:  # short
                self.pnl = (self.entry_price - self.exit_price) * self.quantity
                self.return_pct = (self.entry_price / self.exit_price - 1) * 100

@dataclass
class BacktestResult:
    """Resultados del backtest"""
    strategy_name: str
    start_date: datetime
    end_date: datetime
    initial_capital: float
    final_capital: float
    total_return: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float
    avg_return: float
    max_drawdown: float
    sharpe_ratio: float
    trades: List[Trade] = field(default_factory=list)
    equity_curve: List[Tuple[datetime, float]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategy_name": self.strategy_name,
            "start_date": self.start_date.isoformat(),
            "end_date": self.end_date.isoformat(),
            "initial_capital": self.initial_capital,
            "final_capital": self.final_capital,
            "total_return": self.total_return,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": self.win_rate,
            "avg_return": self.avg_return,
            "max_drawdown": self.max_drawdown,
            "sharpe_ratio": self.sharpe_ratio
        }

class BacktestEngine:
    """
    Motor de backtesting para estrategias de trading
    """
    
    def __init__(self, initial_capital: float = 100000.0):
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.trades: List[Trade] = []
        self.equity_curve: List[Tuple[datetime, float]] = []
        self.positions: Dict[str, Dict] = {}  # symbol -> {quantity, entry_price, side}
        
        logger.info(f"BacktestEngine initialized with ${initial_capital:,.2f}")
    
    def reset(self):
        """Resetear el motor para nuevo backtest"""
        self.current_capital = self.initial_capital
        self.trades = []
        self.equity_curve = []
        self.positions = {}
        logger.info("BacktestEngine reset")
    
    def run_backtest(
        self,
        strategy_name: str,
        data: pd.DataFrame,
        strategy_func,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> BacktestResult:
        """
        Ejecutar backtest de una estrategia
        
        Args:
            strategy_name: Nombre de la estrategia
            data: DataFrame con datos de precios (debe tener 'open', 'high', 'low', 'close', 'volume')
            strategy_func: Función que genera señales de trading
            start_date: Fecha inicio (opcional)
            end_date: Fecha fin (opcional)
        
        Returns:
            BacktestResult con métricas de rendimiento
        """
        self.reset()
        
        # Filtrar por fechas si se especifican
        if start_date:
            data = data[data.index >= start_date]
        if end_date:
            data = data[data.index <= end_date]
        
        if len(data) == 0:
            logger.error("No data available for backtest")
            return None
        
        logger.info(f"Running backtest: {strategy_name}")
        logger.info(f"Data range: {data.index[0]} to {data.index[-1]}")
        logger.info(f"Initial capital: ${self.initial_capital:,.2f}")
        
        # Generar señales
        signals = strategy_func(data)
        
        # Simular trading
        for i, (date, row) in enumerate(data.iterrows()):
            # Actualizar equity curve
            self.equity_curve.append((date, self.current_capital))
            
            # Procesar señal
            if i < len(signals):
                signal = signals.iloc[i]
                self._process_signal(date, row, signal)
            
            # Cerrar posiciones al final
            if i == len(data) - 1:
                self._close_all_positions(date, row)
        
        # Calcular métricas
        result = self._calculate_metrics(strategy_name, data)
        
        logger.info(f"Backtest complete: {result.total_trades} trades")
        logger.info(f"Total return: {result.total_return:.2f}%")
        logger.info(f"Sharpe ratio: {result.sharpe_ratio:.2f}")
        
        return result
    
    def _process_signal(self, date: datetime, row: pd.Series, signal: int):
        """Procesar señal de trading"""
        symbol = row.get('symbol', 'UNKNOWN')
        price = row['close']
        
        # Señal 1 = Comprar, -1 = Vender, 0 = Mantener
        if signal == 1 and symbol not in self.positions:
            # Abrir posición long
            quantity = int(self.current_capital * 0.1 / price)  # 10% del capital
            if quantity > 0:
                self.positions[symbol] = {
                    'quantity': quantity,
                    'entry_price': price,
                    'side': 'long',
                    'entry_date': date
                }
                logger.debug(f"LONG {quantity} {symbol} @ ${price:.2f}")
        
        elif signal == -1 and symbol in self.positions:
            # Cerrar posición
            position = self.positions[symbol]
            trade = Trade(
                entry_date=position['entry_date'],
                exit_date=date,
                symbol=symbol,
                side=position['side'],
                entry_price=position['entry_price'],
                exit_price=price,
                quantity=position['quantity']
            )
            trade.calculate_pnl()
            self.trades.append(trade)
            self.current_capital += trade.pnl
            del self.positions[symbol]
            logger.debug(f"CLOSE {symbol} @ ${price:.2f}, P&L: ${trade.pnl:.2f}")
    
    def _close_all_positions(self, date: datetime, row: pd.Series):
        """Cerrar todas las posiciones abiertas"""
        price = row['close']
        for symbol, position in list(self.positions.items()):
            trade = Trade(
                entry_date=position['entry_date'],
                exit_date=date,
                symbol=symbol,
                side=position['side'],
                entry_price=position['entry_price'],
                exit_price=price,
                quantity=position['quantity']
            )
            trade.calculate_pnl()
            self.trades.append(trade)
            self.current_capital += trade.pnl
            logger.debug(f"CLOSE (end) {symbol} @ ${price:.2f}, P&L: ${trade.pnl:.2f}")
        self.positions.clear()
    
    def _calculate_metrics(self, strategy_name: str, data: pd.DataFrame) -> BacktestResult:
        """Calcular métricas de rendimiento"""
        
        # Métricas básicas
        total_trades = len(self.trades)
        winning_trades = len([t for t in self.trades if t.pnl > 0])
        losing_trades = len([t for t in self.trades if t.pnl <= 0])
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        
        # Retornos
        total_return = ((self.current_capital - self.initial_capital) / self.initial_capital) * 100
        avg_return = np.mean([t.return_pct for t in self.trades]) if self.trades else 0
        
        # Max drawdown
        max_drawdown = self._calculate_max_drawdown()
        
        # Sharpe ratio (simplificado)
        returns = [t.return_pct for t in self.trades]
        sharpe_ratio = self._calculate_sharpe(returns)
        
        return BacktestResult(
            strategy_name=strategy_name,
            start_date=data.index[0],
            end_date=data.index[-1],
            initial_capital=self.initial_capital,
            final_capital=self.current_capital,
            total_return=total_return,
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            avg_return=avg_return,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe_ratio,
            trades=self.trades,
            equity_curve=self.equity_curve
        )
    
    def _calculate_max_drawdown(self) -> float:
        """Calcular maximum drawdown"""
        if not self.equity_curve:
            return 0.0
        
        peak = self.equity_curve[0][1]
        max_dd = 0.0
        
        for date, value in self.equity_curve:
            if value > peak:
                peak = value
            drawdown = (peak - value) / peak
            max_dd = max(max_dd, drawdown)
        
        return max_dd * 100
    
    def _calculate_sharpe(self, returns: List[float], risk_free_rate: float = 0.02) -> float:
        """Calcular Sharpe ratio"""
        if len(returns) < 2:
            return 0.0
        
        returns_array = np.array(returns)
        excess_returns = returns_array - risk_free_rate
        
        if np.std(returns_array) == 0:
            return 0.0
        
        sharpe = np.mean(excess_returns) / np.std(returns_array)
        return sharpe * np.sqrt(252)  # Anualizado
    
    def generate_report(self, result: BacktestResult) -> str:
        """Generar reporte de backtest"""
        report = f"""
{'='*60}
BACKTEST REPORT: {result.strategy_name}
{'='*60}
Period: {result.start_date.strftime('%Y-%m-%d')} to {result.end_date.strftime('%Y-%m-%d')}
Initial Capital: ${result.initial_capital:,.2f}
Final Capital: ${result.final_capital:,.2f}
Total Return: {result.total_return:.2f}%

TRADE STATISTICS
{'='*60}
Total Trades: {result.total_trades}
Winning Trades: {result.winning_trades} ({result.win_rate:.1f}%)
Losing Trades: {result.losing_trades}
Average Return: {result.avg_return:.2f}%

RISK METRICS
{'='*60}
Max Drawdown: {result.max_drawdown:.2f}%
Sharpe Ratio: {result.sharpe_ratio:.2f}

{'='*60}
"""
        return report

# Estrategias de ejemplo
def momentum_strategy(data: pd.DataFrame, short_window: int = 20, long_window: int = 50) -> pd.Series:
    """
    Estrategia de momentum simple
    Compra cuando SMA corta > SMA larga
    """
    signals = pd.Series(index=data.index, data=0)
    
    # Calcular medias móviles
    data['SMA_short'] = data['close'].rolling(window=short_window).mean()
    data['SMA_long'] = data['close'].rolling(window=long_window).mean()
    
    # Generar señales
    for i in range(long_window, len(data)):
        if data['SMA_short'].iloc[i] > data['SMA_long'].iloc[i]:
            signals.iloc[i] = 1  # Comprar
        elif data['SMA_short'].iloc[i] < data['SMA_long'].iloc[i]:
            signals.iloc[i] = -1  # Vender
    
    return signals

def mean_reversion_strategy(data: pd.DataFrame, window: int = 20, std_dev: int = 2) -> pd.Series:
    """
    Estrategia de mean reversion (Bollinger Bands)
    """
    signals = pd.Series(index=data.index, data=0)
    
    # Calcular bandas de Bollinger
    data['SMA'] = data['close'].rolling(window=window).mean()
    data['STD'] = data['close'].rolling(window=window).std()
    data['Upper'] = data['SMA'] + (data['STD'] * std_dev)
    data['Lower'] = data['SMA'] - (data['STD'] * std_dev)
    
    # Generar señales
    for i in range(window, len(data)):
        if data['close'].iloc[i] < data['Lower'].iloc[i]:
            signals.iloc[i] = 1  # Comprar (precio bajo)
        elif data['close'].iloc[i] > data['Upper'].iloc[i]:
            signals.iloc[i] = -1  # Vender (precio alto)
    
    return signals

# Instancia global
backtest_engine = BacktestEngine()

def test_backtest():
    """Probar el motor de backtesting"""
    print("="*60)
    print("AI_VAULT Backtest Engine - Test")
    print("="*60)
    
    # Crear datos de prueba
    dates = pd.date_range(start='2024-01-01', end='2024-03-01', freq='D')
    np.random.seed(42)
    
    # Simular precios
    prices = 100 + np.cumsum(np.random.randn(len(dates)) * 2)
    
    data = pd.DataFrame({
        'open': prices + np.random.randn(len(dates)),
        'high': prices + abs(np.random.randn(len(dates))) * 2,
        'low': prices - abs(np.random.randn(len(dates))) * 2,
        'close': prices,
        'volume': np.random.randint(1000000, 5000000, len(dates)),
        'symbol': 'TEST'
    }, index=dates)
    
    # Ejecutar backtest con estrategia de momentum
    print("\n[1/2] Testing Momentum Strategy...")
    result1 = backtest_engine.run_backtest(
        strategy_name="Momentum_SMA",
        data=data,
        strategy_func=momentum_strategy
    )
    
    if result1:
        print(backtest_engine.generate_report(result1))
    
    # Ejecutar backtest con estrategia de mean reversion
    print("\n[2/2] Testing Mean Reversion Strategy...")
    result2 = backtest_engine.run_backtest(
        strategy_name="Mean_Reversion_BB",
        data=data,
        strategy_func=mean_reversion_strategy
    )
    
    if result2:
        print(backtest_engine.generate_report(result2))
    
    print("\n" + "="*60)
    print("Backtest Engine Test Complete")
    print("="*60)

if __name__ == "__main__":
    test_backtest()
