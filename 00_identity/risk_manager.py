"""
AI_VAULT Risk Manager v1.0
Sistema de gestión de riesgos para Fase 6.1
Implementa VaR, CVaR, stop-loss dinámico y gestión de posiciones
"""

import numpy as np
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

@dataclass
class RiskMetrics:
    """Métricas de riesgo calculadas"""
    var_95: float  # Value at Risk 95%
    var_99: float  # Value at Risk 99%
    cvar_95: float  # Conditional VaR 95%
    cvar_99: float  # Conditional VaR 99%
    volatility: float  # Volatilidad anualizada
    sharpe_ratio: float
    max_drawdown: float
    beta: float
    timestamp: datetime
    
    def to_dict(self) -> Dict:
        return {
            "var_95": self.var_95,
            "var_99": self.var_99,
            "cvar_95": self.cvar_95,
            "cvar_99": self.cvar_99,
            "volatility": self.volatility,
            "sharpe_ratio": self.sharpe_ratio,
            "max_drawdown": self.max_drawdown,
            "beta": self.beta,
            "timestamp": self.timestamp.isoformat()
        }

@dataclass
class PositionRisk:
    """Riesgo de una posición individual"""
    symbol: str
    position_size: float
    position_value: float
    portfolio_weight: float
    unrealized_pnl: float
    risk_level: RiskLevel
    stop_loss: Optional[float]
    take_profit: Optional[float]
    recommended_action: str

class RiskManager:
    """
    Gestor de riesgos para AI_VAULT
    Implementa límites de riesgo según las premisas canónicas
    """
    
    def __init__(self):
        # Límites de riesgo (de las premisas canónicas)
        self.max_drawdown_limit = 0.10  # 10%
        self.var_daily_limit = 0.02  # 2%
        self.position_size_max = 0.05  # 5% del portafolio
        self.max_correlation = 0.80  # Correlación máxima entre posiciones
        
        # Tracking
        self.risk_history: List[RiskMetrics] = []
        self.breaches: List[Dict] = []
        
        logger.info("RiskManager initialized")
        logger.info(f"Max Drawdown Limit: {self.max_drawdown_limit*100}%")
        logger.info(f"VaR Daily Limit: {self.var_daily_limit*100}%")
        logger.info(f"Max Position Size: {self.position_size_max*100}%")
    
    def calculate_var(self, returns: List[float], confidence: float = 0.95) -> float:
        """
        Calcular Value at Risk usando método histórico
        
        Args:
            returns: Lista de retornos históricos
            confidence: Nivel de confianza (0.95 o 0.99)
        
        Returns:
            VaR como valor negativo (pérdida)
        """
        if not returns:
            return 0.0
        
        return np.percentile(returns, (1 - confidence) * 100)
    
    def calculate_cvar(self, returns: List[float], confidence: float = 0.95) -> float:
        """
        Calcular Conditional Value at Risk (Expected Shortfall)
        
        Args:
            returns: Lista de retornos históricos
            confidence: Nivel de confianza
        
        Returns:
            CVaR como valor negativo
        """
        if not returns:
            return 0.0
        
        var = self.calculate_var(returns, confidence)
        cvar = np.mean([r for r in returns if r <= var])
        return cvar
    
    def calculate_volatility(self, returns: List[float], annualize: bool = True) -> float:
        """Calcular volatilidad"""
        if len(returns) < 2:
            return 0.0
        
        vol = np.std(returns, ddof=1)
        
        if annualize:
            # Asumiendo retornos diarios, anualizar con 252 días
            vol = vol * np.sqrt(252)
        
        return vol
    
    def calculate_sharpe_ratio(self, returns: List[float], risk_free_rate: float = 0.02) -> float:
        """Calcular Sharpe Ratio"""
        if not returns or len(returns) < 2:
            return 0.0
        
        avg_return = np.mean(returns)
        volatility = self.calculate_volatility(returns, annualize=False)
        
        if volatility == 0:
            return 0.0
        
        # Anualizar
        excess_return = avg_return * 252 - risk_free_rate
        annual_vol = volatility * np.sqrt(252)
        
        return excess_return / annual_vol
    
    def calculate_max_drawdown(self, equity_curve: List[float]) -> float:
        """Calcular Maximum Drawdown"""
        if not equity_curve or len(equity_curve) < 2:
            return 0.0
        
        peak = equity_curve[0]
        max_dd = 0.0
        
        for value in equity_curve:
            if value > peak:
                peak = value
            drawdown = (peak - value) / peak
            max_dd = max(max_dd, drawdown)
        
        return max_dd
    
    def calculate_portfolio_risk(
        self,
        positions: Dict[str, Dict],
        returns_data: Dict[str, List[float]],
        total_value: float
    ) -> RiskMetrics:
        """
        Calcular métricas de riesgo del portafolio completo
        
        Args:
            positions: Dict {symbol: {quantity, avg_price, current_price}}
            returns_data: Dict {symbol: [historical_returns]}
            total_value: Valor total del portafolio
        
        Returns:
            RiskMetrics con todas las métricas calculadas
        """
        # Calcular retornos del portafolio
        portfolio_returns = []
        
        if returns_data:
            # Calcular retornos ponderados
            weights = {}
            total_position_value = 0.0
            
            for symbol, pos in positions.items():
                position_value = pos.get('quantity', 0) * pos.get('current_price', 0)
                weights[symbol] = position_value
                total_position_value += position_value
            
            if total_position_value > 0:
                for symbol in weights:
                    weights[symbol] /= total_position_value
                
                # Calcular retornos ponderados del portafolio
                min_len = min(len(returns_data.get(s, [])) for s in returns_data)
                for i in range(min_len):
                    daily_return = sum(
                        weights.get(symbol, 0) * returns_data[symbol][i]
                        for symbol in returns_data
                    )
                    portfolio_returns.append(daily_return)
        
        # Calcular métricas
        var_95 = self.calculate_var(portfolio_returns, 0.95) if portfolio_returns else 0.0
        var_99 = self.calculate_var(portfolio_returns, 0.99) if portfolio_returns else 0.0
        cvar_95 = self.calculate_cvar(portfolio_returns, 0.95) if portfolio_returns else 0.0
        cvar_99 = self.calculate_cvar(portfolio_returns, 0.99) if portfolio_returns else 0.0
        volatility = self.calculate_volatility(portfolio_returns) if portfolio_returns else 0.0
        sharpe = self.calculate_sharpe_ratio(portfolio_returns) if portfolio_returns else 0.0
        
        # Calcular equity curve para max drawdown
        equity_curve = [total_value]
        if portfolio_returns:
            current_value = total_value
            for ret in portfolio_returns:
                current_value *= (1 + ret)
                equity_curve.append(current_value)
        
        max_dd = self.calculate_max_drawdown(equity_curve)
        
        metrics = RiskMetrics(
            var_95=var_95,
            var_99=var_99,
            cvar_95=cvar_95,
            cvar_99=cvar_99,
            volatility=volatility,
            sharpe_ratio=sharpe,
            max_drawdown=max_dd,
            beta=1.0,  # Simplificado
            timestamp=datetime.now(timezone.utc)
        )
        
        self.risk_history.append(metrics)
        
        # Verificar límites
        self._check_risk_limits(metrics)
        
        return metrics
    
    def _check_risk_limits(self, metrics: RiskMetrics):
        """Verificar si se violan los límites de riesgo"""
        
        # Check VaR
        if abs(metrics.var_95) > self.var_daily_limit:
            breach = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "type": "VaR_LIMIT",
                "value": metrics.var_95,
                "limit": self.var_daily_limit,
                "severity": "HIGH"
            }
            self.breaches.append(breach)
            logger.warning(f"VaR limit breached: {metrics.var_95:.2%} > {self.var_daily_limit:.2%}")
        
        # Check Max Drawdown
        if metrics.max_drawdown > self.max_drawdown_limit:
            breach = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "type": "DRAWDOWN_LIMIT",
                "value": metrics.max_drawdown,
                "limit": self.max_drawdown_limit,
                "severity": "CRITICAL"
            }
            self.breaches.append(breach)
            logger.error(f"Max Drawdown limit breached: {metrics.max_drawdown:.2%} > {self.max_drawdown_limit:.2%}")
    
    def calculate_position_risk(
        self,
        symbol: str,
        position: Dict,
        total_portfolio_value: float,
        volatility: float = 0.20
    ) -> PositionRisk:
        """Calcular riesgo de una posición individual"""
        
        quantity = position.get('quantity', 0)
        avg_price = position.get('avg_price', 0)
        current_price = position.get('current_price', avg_price)
        
        position_value = quantity * current_price
        position_size = position_value
        portfolio_weight = position_value / total_portfolio_value if total_portfolio_value > 0 else 0
        unrealized_pnl = (current_price - avg_price) * quantity
        
        # Determinar nivel de riesgo
        if portfolio_weight > self.position_size_max:
            risk_level = RiskLevel.HIGH
        elif portfolio_weight > self.position_size_max * 0.7:
            risk_level = RiskLevel.MEDIUM
        else:
            risk_level = RiskLevel.LOW
        
        # Calcular stop-loss dinámico (2 ATR simplificado)
        atr = current_price * volatility * 0.02  # Simplificación
        stop_loss = current_price - (2 * atr) if quantity > 0 else current_price + (2 * atr)
        
        # Calcular take-profit (3:1 reward/risk)
        risk = abs(current_price - stop_loss)
        take_profit = current_price + (3 * risk) if quantity > 0 else current_price - (3 * risk)
        
        # Recomendación
        if risk_level == RiskLevel.HIGH:
            recommended_action = "REDUCE_POSITION"
        elif unrealized_pnl < -0.05 * position_value:  # Pérdida > 5%
            recommended_action = "REVIEW_STOP_LOSS"
        elif unrealized_pnl > 0.10 * position_value:  # Ganancia > 10%
            recommended_action = "CONSIDER_TAKING_PROFITS"
        else:
            recommended_action = "HOLD"
        
        return PositionRisk(
            symbol=symbol,
            position_size=position_size,
            position_value=position_value,
            portfolio_weight=portfolio_weight,
            unrealized_pnl=unrealized_pnl,
            risk_level=risk_level,
            stop_loss=stop_loss,
            take_profit=take_profit,
            recommended_action=recommended_action
        )
    
    def get_risk_report(self) -> Dict:
        """Generar reporte completo de riesgo"""
        
        if not self.risk_history:
            return {
                "status": "NO_DATA",
                "message": "No risk metrics calculated yet"
            }
        
        latest = self.risk_history[-1]
        
        return {
            "status": "OK" if not self.breaches else "LIMIT_BREACH",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "current_metrics": latest.to_dict(),
            "limits": {
                "max_drawdown": self.max_drawdown_limit,
                "var_daily": self.var_daily_limit,
                "position_size_max": self.position_size_max
            },
            "breaches": self.breaches[-10:],  # Últimas 10 violaciones
            "breach_count": len(self.breaches),
            "recommendations": self._generate_recommendations(latest)
        }
    
    def _generate_recommendations(self, metrics: RiskMetrics) -> List[str]:
        """Generar recomendaciones basadas en métricas"""
        recommendations = []
        
        if metrics.sharpe_ratio < 1.0:
            recommendations.append("Consider reducing high-volatility positions")
        
        if metrics.max_drawdown > self.max_drawdown_limit * 0.8:
            recommendations.append("Approaching max drawdown limit - review risk exposure")
        
        if abs(metrics.var_95) > self.var_daily_limit * 0.9:
            recommendations.append("VaR approaching limit - consider hedging")
        
        if not recommendations:
            recommendations.append("Risk metrics within acceptable limits")
        
        return recommendations
    
    def reset_breaches(self):
        """Resetear registro de violaciones"""
        self.breaches = []
        logger.info("Risk breaches log reset")

# Instancia global
risk_manager = RiskManager()

def test_risk_manager():
    """Probar el gestor de riesgos"""
    print("=" * 60)
    print("AI_VAULT Risk Manager - Test")
    print("=" * 60)
    
    rm = RiskManager()
    
    # Simular datos de retornos
    np.random.seed(42)
    returns = np.random.normal(0.001, 0.02, 252)  # 1 año de retornos diarios
    
    # Test 1: Calcular VaR
    print("\n[1/4] Testing VaR calculation...")
    var_95 = rm.calculate_var(returns.tolist(), 0.95)
    var_99 = rm.calculate_var(returns.tolist(), 0.99)
    print(f"   VaR 95%: {var_95:.2%}")
    print(f"   VaR 99%: {var_99:.2%}")
    
    # Test 2: Calcular CVaR
    print("\n[2/4] Testing CVaR calculation...")
    cvar_95 = rm.calculate_cvar(returns.tolist(), 0.95)
    print(f"   CVaR 95%: {cvar_95:.2%}")
    
    # Test 3: Calcular métricas de portafolio
    print("\n[3/4] Testing portfolio risk calculation...")
    positions = {
        "AAPL": {"quantity": 10, "avg_price": 150.0, "current_price": 155.0},
        "MSFT": {"quantity": 5, "avg_price": 300.0, "current_price": 310.0}
    }
    
    returns_data = {
        "AAPL": returns.tolist(),
        "MSFT": (returns + np.random.normal(0, 0.005, 252)).tolist()
    }
    
    total_value = sum(p["quantity"] * p["current_price"] for p in positions.values())
    
    metrics = rm.calculate_portfolio_risk(positions, returns_data, total_value)
    print(f"   Volatility: {metrics.volatility:.2%}")
    print(f"   Sharpe Ratio: {metrics.sharpe_ratio:.2f}")
    print(f"   Max Drawdown: {metrics.max_drawdown:.2%}")
    
    # Test 4: Reporte de riesgo
    print("\n[4/4] Testing risk report...")
    report = rm.get_risk_report()
    print(f"   Status: {report['status']}")
    print(f"   Breach Count: {report['breach_count']}")
    print(f"   Recommendations: {len(report['recommendations'])}")
    for rec in report['recommendations']:
        print(f"     - {rec}")
    
    print("\n" + "=" * 60)
    print("Test Complete - Risk Manager Operational")
    print("=" * 60)

if __name__ == "__main__":
    test_risk_manager()
