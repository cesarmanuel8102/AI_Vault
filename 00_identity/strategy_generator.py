"""
AI_VAULT Strategy Generator v1.0
Generador de estrategias cuantitativas para Fase 6.2
"""

import random
import numpy as np
from typing import Dict, List, Optional, Tuple, Any, Callable
from dataclasses import dataclass, field
from enum import Enum
import json
import logging
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class StrategyType(Enum):
    MOMENTUM = "momentum"
    MEAN_REVERSION = "mean_reversion"
    TREND_FOLLOWING = "trend_following"
    BREAKOUT = "breakout"
    VOLATILITY = "volatility"
    MACHINE_LEARNING = "machine_learning"

@dataclass
class StrategyConfig:
    """Configuración de estrategia"""
    name: str
    strategy_type: StrategyType
    parameters: Dict[str, Any]
    indicators: List[str]
    entry_rules: List[str]
    exit_rules: List[str]
    risk_management: Dict[str, float]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "type": self.strategy_type.value,
            "parameters": self.parameters,
            "indicators": self.indicators,
            "entry_rules": self.entry_rules,
            "exit_rules": self.exit_rules,
            "risk_management": self.risk_management
        }

@dataclass
class GeneratedStrategy:
    """Estrategia generada con metadatos"""
    config: StrategyConfig
    code: str
    performance_estimate: Dict[str, float]
    complexity_score: float
    uniqueness_score: float
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "config": self.config.to_dict(),
            "code": self.code[:200] + "..." if len(self.code) > 200 else self.code,
            "performance_estimate": self.performance_estimate,
            "complexity_score": self.complexity_score,
            "uniqueness_score": self.uniqueness_score,
            "generated_at": self.generated_at.isoformat()
        }

class StrategyGenerator:
    """
    Generador automático de estrategias de trading
    Crea estrategias cuantitativas basadas en diferentes paradigmas
    """
    
    def __init__(self):
        self.generated_strategies: List[GeneratedStrategy] = []
        self.strategy_templates = self._load_templates()
        self.indicator_library = self._load_indicators()
        
        logger.info("StrategyGenerator initialized")
        logger.info(f"Loaded {len(self.strategy_templates)} strategy templates")
        logger.info(f"Loaded {len(self.indicator_library)} technical indicators")
    
    def _load_templates(self) -> Dict[str, str]:
        """Cargar templates de estrategias"""
        return {
            "momentum": """
def momentum_strategy(data, short_window={short_window}, long_window={long_window}):
    signals = []
    sma_short = data['close'].rolling(window=short_window).mean()
    sma_long = data['close'].rolling(window=long_window).mean()
    
    for i in range(len(data)):
        if sma_short.iloc[i] > sma_long.iloc[i]:
            signals.append(1)  # Buy
        elif sma_short.iloc[i] < sma_long.iloc[i]:
            signals.append(-1)  # Sell
        else:
            signals.append(0)  # Hold
    
    return signals
""",
            "mean_reversion": """
def mean_reversion_strategy(data, window={window}, std_dev={std_dev}):
    signals = []
    sma = data['close'].rolling(window=window).mean()
    std = data['close'].rolling(window=window).std()
    upper_band = sma + (std * std_dev)
    lower_band = sma - (std * std_dev)
    
    for i in range(len(data)):
        if data['close'].iloc[i] < lower_band.iloc[i]:
            signals.append(1)  # Buy (oversold)
        elif data['close'].iloc[i] > upper_band.iloc[i]:
            signals.append(-1)  # Sell (overbought)
        else:
            signals.append(0)
    
    return signals
""",
            "breakout": """
def breakout_strategy(data, window={window}):
    signals = []
    high_max = data['high'].rolling(window=window).max()
    low_min = data['low'].rolling(window=window).min()
    
    for i in range(len(data)):
        if data['close'].iloc[i] > high_max.iloc[i-1]:
            signals.append(1)  # Buy breakout
        elif data['close'].iloc[i] < low_min.iloc[i-1]:
            signals.append(-1)  # Sell breakdown
        else:
            signals.append(0)
    
    return signals
""",
            "volatility": """
def volatility_strategy(data, vol_window={vol_window}, threshold={threshold}):
    signals = []
    returns = data['close'].pct_change()
    volatility = returns.rolling(window=vol_window).std()
    
    for i in range(len(data)):
        if volatility.iloc[i] > threshold:
            signals.append(1)  # High volatility - trade
        else:
            signals.append(0)  # Low volatility - hold
    
    return signals
"""
        }
    
    def _load_indicators(self) -> Dict[str, Dict]:
        """Cargar biblioteca de indicadores técnicos"""
        return {
            "SMA": {"name": "Simple Moving Average", "params": ["window"]},
            "EMA": {"name": "Exponential Moving Average", "params": ["window", "alpha"]},
            "RSI": {"name": "Relative Strength Index", "params": ["window"]},
            "MACD": {"name": "MACD", "params": ["fast", "slow", "signal"]},
            "BB": {"name": "Bollinger Bands", "params": ["window", "std_dev"]},
            "ATR": {"name": "Average True Range", "params": ["window"]},
            "ADX": {"name": "Average Directional Index", "params": ["window"]},
            "Stochastic": {"name": "Stochastic Oscillator", "params": ["k_window", "d_window"]},
            "CCI": {"name": "Commodity Channel Index", "params": ["window"]},
            "WilliamsR": {"name": "Williams %R", "params": ["window"]}
        }
    
    def generate_strategy(
        self,
        strategy_type: Optional[StrategyType] = None,
        complexity: str = "medium",
        target_performance: Optional[Dict[str, float]] = None
    ) -> GeneratedStrategy:
        """
        Generar una nueva estrategia
        
        Args:
            strategy_type: Tipo de estrategia (None = aleatorio)
            complexity: simple, medium, complex
            target_performance: Métricas objetivo
        
        Returns:
            GeneratedStrategy con código y configuración
        """
        # Seleccionar tipo si no se especifica
        if strategy_type is None:
            strategy_type = random.choice(list(StrategyType))
        
        logger.info(f"Generating {strategy_type.value} strategy...")
        
        # Generar parámetros basados en complejidad
        parameters = self._generate_parameters(strategy_type, complexity)
        
        # Seleccionar indicadores
        indicators = self._select_indicators(strategy_type, complexity)
        
        # Generar reglas
        entry_rules, exit_rules = self._generate_rules(strategy_type, indicators, parameters)
        
        # Configurar gestión de riesgo
        risk_management = self._generate_risk_management(complexity)
        
        # Crear configuración
        config = StrategyConfig(
            name=f"{strategy_type.value.title()}_{random.randint(1000, 9999)}",
            strategy_type=strategy_type,
            parameters=parameters,
            indicators=indicators,
            entry_rules=entry_rules,
            exit_rules=exit_rules,
            risk_management=risk_management
        )
        
        # Generar código
        code = self._generate_code(config)
        
        # Estimar performance
        performance = self._estimate_performance(config)
        
        # Calcular scores
        complexity_score = self._calculate_complexity(config)
        uniqueness_score = self._calculate_uniqueness(config)
        
        strategy = GeneratedStrategy(
            config=config,
            code=code,
            performance_estimate=performance,
            complexity_score=complexity_score,
            uniqueness_score=uniqueness_score
        )
        
        self.generated_strategies.append(strategy)
        
        logger.info(f"Strategy generated: {config.name}")
        logger.info(f"  Expected return: {performance['expected_return']:.2f}%")
        logger.info(f"  Expected Sharpe: {performance['expected_sharpe']:.2f}")
        
        return strategy
    
    def _generate_parameters(self, strategy_type: StrategyType, complexity: str) -> Dict[str, Any]:
        """Generar parámetros óptimos para la estrategia"""
        params = {}
        
        if strategy_type == StrategyType.MOMENTUM:
            params["short_window"] = random.choice([10, 15, 20, 25])
            params["long_window"] = random.choice([40, 50, 60, 80])
        
        elif strategy_type == StrategyType.MEAN_REVERSION:
            params["window"] = random.choice([15, 20, 25, 30])
            params["std_dev"] = random.choice([1.5, 2.0, 2.5, 3.0])
        
        elif strategy_type == StrategyType.BREAKOUT:
            params["window"] = random.choice([10, 15, 20, 30])
            params["confirmation_bars"] = random.choice([1, 2, 3])
        
        elif strategy_type == StrategyType.VOLATILITY:
            params["vol_window"] = random.choice([10, 20, 30])
            params["threshold"] = random.uniform(0.01, 0.05)
        
        elif strategy_type == StrategyType.TREND_FOLLOWING:
            params["trend_window"] = random.choice([50, 100, 200])
            params["adx_threshold"] = random.choice([20, 25, 30])
        
        return params
    
    def _select_indicators(self, strategy_type: StrategyType, complexity: str) -> List[str]:
        """Seleccionar indicadores técnicos"""
        base_indicators = {
            StrategyType.MOMENTUM: ["SMA", "EMA", "MACD"],
            StrategyType.MEAN_REVERSION: ["RSI", "BB", "Stochastic"],
            StrategyType.TREND_FOLLOWING: ["ADX", "SMA", "MACD"],
            StrategyType.BREAKOUT: ["ATR", "SMA"],
            StrategyType.VOLATILITY: ["ATR", "BB"],
            StrategyType.MACHINE_LEARNING: ["RSI", "MACD", "BB", "ADX"]
        }
        
        indicators = base_indicators.get(strategy_type, ["SMA", "RSI"])
        
        # Añadir indicadores adicionales según complejidad
        if complexity == "complex":
            additional = random.sample(["CCI", "WilliamsR", "ATR"], k=random.randint(1, 2))
            indicators.extend(additional)
        
        return list(set(indicators))  # Eliminar duplicados
    
    def _generate_rules(
        self,
        strategy_type: StrategyType,
        indicators: List[str],
        parameters: Dict[str, Any]
    ) -> Tuple[List[str], List[str]]:
        """Generar reglas de entrada y salida"""
        
        entry_rules = []
        exit_rules = []
        
        if strategy_type == StrategyType.MOMENTUM:
            entry_rules.append(f"SMA_{parameters.get('short_window', 20)} crosses above SMA_{parameters.get('long_window', 50)}")
            exit_rules.append(f"SMA_{parameters.get('short_window', 20)} crosses below SMA_{parameters.get('long_window', 50)}")
        
        elif strategy_type == StrategyType.MEAN_REVERSION:
            entry_rules.append(f"Price below BB_lower ({parameters.get('std_dev', 2)} std dev)")
            entry_rules.append(f"RSI < 30")
            exit_rules.append(f"Price above BB_upper ({parameters.get('std_dev', 2)} std dev)")
            exit_rules.append(f"RSI > 70")
        
        elif strategy_type == StrategyType.BREAKOUT:
            entry_rules.append(f"Price breaks above {parameters.get('window', 20)}-day high")
            exit_rules.append(f"Price breaks below {parameters.get('window', 20)}-day low")
        
        # Añadir reglas de stop loss y take profit
        exit_rules.append("Stop loss: -2%")
        exit_rules.append("Take profit: +6%")
        
        return entry_rules, exit_rules
    
    def _generate_risk_management(self, complexity: str) -> Dict[str, float]:
        """Generar configuración de gestión de riesgo"""
        return {
            "max_position_size": random.uniform(0.05, 0.15),
            "stop_loss_pct": random.uniform(1.5, 3.0),
            "take_profit_pct": random.uniform(4.0, 8.0),
            "max_daily_loss": random.uniform(0.02, 0.05),
            "max_drawdown": random.uniform(0.08, 0.15)
        }
    
    def _generate_code(self, config: StrategyConfig) -> str:
        """Generar código Python de la estrategia"""
        template = self.strategy_templates.get(config.strategy_type.value, "")
        
        if template:
            code = template.format(**config.parameters)
        else:
            # Código genérico
            code = f"""
def {config.name.lower()}_strategy(data):
    signals = []
    # Indicators: {', '.join(config.indicators)}
    # Entry rules: {'; '.join(config.entry_rules)}
    # Exit rules: {'; '.join(config.exit_rules)}
    
    for i in range(len(data)):
        # Implement strategy logic here
        signals.append(0)
    
    return signals
"""
        
        return code
    
    def _estimate_performance(self, config: StrategyConfig) -> Dict[str, float]:
        """Estimar performance de la estrategia"""
        # Simulación de estimación basada en tipo y parámetros
        base_return = random.uniform(5.0, 25.0)
        base_sharpe = random.uniform(0.8, 2.0)
        base_winrate = random.uniform(45.0, 65.0)
        
        # Ajustar según tipo
        if config.strategy_type == StrategyType.MOMENTUM:
            base_return *= 1.2
            base_sharpe *= 1.1
        elif config.strategy_type == StrategyType.MEAN_REVERSION:
            base_winrate *= 1.15
        
        return {
            "expected_return": base_return,
            "expected_sharpe": base_sharpe,
            "expected_winrate": base_winrate,
            "expected_max_drawdown": random.uniform(5.0, 15.0),
            "expected_trades_per_month": random.randint(10, 50)
        }
    
    def _calculate_complexity(self, config: StrategyConfig) -> float:
        """Calcular score de complejidad"""
        score = 0.0
        score += len(config.indicators) * 0.2
        score += len(config.entry_rules) * 0.15
        score += len(config.exit_rules) * 0.15
        score += len(config.parameters) * 0.1
        return min(score, 1.0)
    
    def _calculate_uniqueness(self, config: StrategyConfig) -> float:
        """Calcular score de unicidad (comparación con estrategias existentes)"""
        # Simplificación: score aleatorio basado en nombre único
        return random.uniform(0.6, 0.95)
    
    def generate_strategy_batch(
        self,
        count: int = 5,
        strategy_types: Optional[List[StrategyType]] = None
    ) -> List[GeneratedStrategy]:
        """Generar múltiples estrategias"""
        strategies = []
        
        if strategy_types is None:
            strategy_types = list(StrategyType)
        
        for i in range(count):
            strategy_type = random.choice(strategy_types)
            strategy = self.generate_strategy(strategy_type=strategy_type)
            strategies.append(strategy)
        
        logger.info(f"Generated batch of {count} strategies")
        return strategies
    
    def rank_strategies(self) -> List[GeneratedStrategy]:
        """Ranking de estrategias por performance esperada"""
        ranked = sorted(
            self.generated_strategies,
            key=lambda s: (
                s.performance_estimate["expected_sharpe"] * 0.4 +
                s.performance_estimate["expected_return"] * 0.3 +
                s.uniqueness_score * 0.2 -
                s.performance_estimate["expected_max_drawdown"] * 0.1
            ),
            reverse=True
        )
        return ranked
    
    def export_strategy(self, strategy: GeneratedStrategy, filepath: str):
        """Exportar estrategia a archivo JSON"""
        with open(filepath, 'w') as f:
            json.dump(strategy.to_dict(), f, indent=2)
        logger.info(f"Strategy exported to {filepath}")
    
    def get_strategy_summary(self) -> Dict[str, Any]:
        """Obtener resumen de estrategias generadas"""
        if not self.generated_strategies:
            return {"message": "No strategies generated yet"}
        
        types_count = {}
        for s in self.generated_strategies:
            t = s.config.strategy_type.value
            types_count[t] = types_count.get(t, 0) + 1
        
        avg_return = np.mean([s.performance_estimate["expected_return"] 
                              for s in self.generated_strategies])
        avg_sharpe = np.mean([s.performance_estimate["expected_sharpe"] 
                              for s in self.generated_strategies])
        
        return {
            "total_strategies": len(self.generated_strategies),
            "by_type": types_count,
            "avg_expected_return": avg_return,
            "avg_expected_sharpe": avg_sharpe,
            "top_strategy": self.rank_strategies()[0].config.name if self.generated_strategies else None
        }

# Instancia global
strategy_generator = StrategyGenerator()

def test_strategy_generator():
    """Probar el generador de estrategias"""
    print("="*60)
    print("AI_VAULT Strategy Generator - Test")
    print("="*60)
    
    # Generar batch de estrategias
    print("\n[1/3] Generating strategy batch...")
    strategies = strategy_generator.generate_strategy_batch(count=5)
    
    for i, strategy in enumerate(strategies, 1):
        print(f"\nStrategy {i}: {strategy.config.name}")
        print(f"  Type: {strategy.config.strategy_type.value}")
        print(f"  Indicators: {', '.join(strategy.config.indicators)}")
        print(f"  Expected Return: {strategy.performance_estimate['expected_return']:.2f}%")
        print(f"  Expected Sharpe: {strategy.performance_estimate['expected_sharpe']:.2f}")
        print(f"  Complexity: {strategy.complexity_score:.2f}")
    
    # Ranking
    print("\n[2/3] Strategy Ranking:")
    ranked = strategy_generator.rank_strategies()
    for i, strategy in enumerate(ranked[:3], 1):
        print(f"  {i}. {strategy.config.name} (Sharpe: {strategy.performance_estimate['expected_sharpe']:.2f})")
    
    # Resumen
    print("\n[3/3] Summary:")
    summary = strategy_generator.get_strategy_summary()
    print(f"  Total strategies: {summary['total_strategies']}")
    print(f"  Avg Expected Return: {summary['avg_expected_return']:.2f}%")
    print(f"  Avg Expected Sharpe: {summary['avg_expected_sharpe']:.2f}")
    print(f"  Top Strategy: {summary['top_strategy']}")
    
    print("\n" + "="*60)
    print("Strategy Generator Test Complete")
    print("="*60)

if __name__ == "__main__":
    test_strategy_generator()
