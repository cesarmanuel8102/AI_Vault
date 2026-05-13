"""
AI_VAULT Capital Manager v1.0
Sistema de gestión de capital Core/Satélite/Explorador
Fase 6.1 - MOTOR_FINANCIERO
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CapitalLayer(Enum):
    """Capas de capital según estrategia"""
    CORE = "core"           # 60% - Estrategias probadas, bajo riesgo
    SATELLITE = "satellite" # 30% - Estrategias en validación
    EXPLORER = "explorer"   # 10% - Nuevas estrategias experimentales

@dataclass
class CapitalAllocation:
    """Asignación de capital a una capa"""
    layer: CapitalLayer
    allocated: float
    used: float = 0.0
    available: float = 0.0
    target_pct: float = 0.0
    
    def __post_init__(self):
        self.available = self.allocated - self.used
    
    @property
    def utilization_pct(self) -> float:
        return (self.used / self.allocated * 100) if self.allocated > 0 else 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "layer": self.layer.value,
            "allocated": self.allocated,
            "used": self.used,
            "available": self.available,
            "target_pct": self.target_pct,
            "utilization_pct": self.utilization_pct
        }

@dataclass
class StrategyAllocation:
    """Asignación de capital a una estrategia específica"""
    strategy_id: str
    name: str
    layer: CapitalLayer
    allocated: float
    used: float = 0.0
    pnl: float = 0.0
    sharpe_ratio: float = 0.0
    max_drawdown: float = 0.0
    status: str = "active"  # active, paused, liquidating
    
    @property
    def available(self) -> float:
        return self.allocated - self.used
    
    @property
    def return_pct(self) -> float:
        return (self.pnl / self.allocated * 100) if self.allocated > 0 else 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "strategy_id": self.strategy_id,
            "name": self.name,
            "layer": self.layer.value,
            "allocated": self.allocated,
            "used": self.used,
            "available": self.available,
            "pnl": self.pnl,
            "return_pct": self.return_pct,
            "sharpe_ratio": self.sharpe_ratio,
            "max_drawdown": self.max_drawdown,
            "status": self.status
        }

class CapitalManager:
    """
    Gestor de capital con arquitectura Core/Satélite/Explorador
    Implementa reglas de asignación y rebalancing
    """
    
    def __init__(self, total_capital: float = 100000.0):
        self.total_capital = total_capital
        self.initial_capital = total_capital
        
        # Asignaciones por capa (porcentajes objetivo)
        self.layer_targets = {
            CapitalLayer.CORE: 0.60,      # 60%
            CapitalLayer.SATELLITE: 0.30,  # 30%
            CapitalLayer.EXPLORER: 0.10   # 10%
        }
        
        # Inicializar capas
        self.layers: Dict[CapitalLayer, CapitalAllocation] = {}
        self._initialize_layers()
        
        # Estrategias
        self.strategies: Dict[str, StrategyAllocation] = {}
        
        # Historial
        self.allocation_history: List[Dict] = []
        self.rebalance_history: List[Dict] = []
        
        logger.info(f"CapitalManager initialized")
        logger.info(f"Total Capital: ${total_capital:,.2f}")
        for layer, alloc in self.layers.items():
            logger.info(f"  {layer.value}: ${alloc.allocated:,.2f} ({alloc.target_pct}%)")
    
    def _initialize_layers(self):
        """Inicializar las tres capas de capital"""
        for layer, target_pct in self.layer_targets.items():
            allocated = self.total_capital * target_pct
            self.layers[layer] = CapitalAllocation(
                layer=layer,
                allocated=allocated,
                target_pct=target_pct * 100
            )
    
    def register_strategy(
        self,
        strategy_id: str,
        name: str,
        layer: CapitalLayer,
        allocation: float
    ) -> bool:
        """
        Registrar una nueva estrategia
        
        Args:
            strategy_id: ID único de la estrategia
            name: Nombre descriptivo
            layer: Capa de capital (core/satellite/explorer)
            allocation: Capital asignado
        
        Returns:
            True si se registró exitosamente
        """
        # Verificar que hay capital disponible en la capa
        layer_cap = self.layers[layer]
        if allocation > layer_cap.available:
            logger.error(f"Insufficient capital in {layer.value} layer")
            logger.error(f"  Requested: ${allocation:,.2f}")
            logger.error(f"  Available: ${layer_cap.available:,.2f}")
            return False
        
        # Crear estrategia
        strategy = StrategyAllocation(
            strategy_id=strategy_id,
            name=name,
            layer=layer,
            allocated=allocation
        )
        
        self.strategies[strategy_id] = strategy
        layer_cap.used += allocation
        layer_cap.available = layer_cap.allocated - layer_cap.used
        
        logger.info(f"Strategy registered: {name}")
        logger.info(f"  Layer: {layer.value}")
        logger.info(f"  Allocation: ${allocation:,.2f}")
        
        return True
    
    def allocate_to_strategy(self, strategy_id: str, amount: float) -> bool:
        """Asignar capital adicional a una estrategia"""
        if strategy_id not in self.strategies:
            logger.error(f"Strategy not found: {strategy_id}")
            return False
        
        strategy = self.strategies[strategy_id]
        layer = self.layers[strategy.layer]
        
        if amount > layer.available:
            logger.error(f"Insufficient capital in {strategy.layer.value} layer")
            return False
        
        strategy.allocated += amount
        layer.used += amount
        layer.available = layer.allocated - layer.used
        
        logger.info(f"Additional ${amount:,.2f} allocated to {strategy.name}")
        return True
    
    def release_from_strategy(self, strategy_id: str, amount: float) -> bool:
        """Liberar capital de una estrategia"""
        if strategy_id not in self.strategies:
            logger.error(f"Strategy not found: {strategy_id}")
            return False
        
        strategy = self.strategies[strategy_id]
        
        if amount > strategy.available:
            logger.error(f"Cannot release more than available")
            return False
        
        strategy.allocated -= amount
        layer = self.layers[strategy.layer]
        layer.used -= amount
        layer.available = layer.allocated - layer.used
        
        logger.info(f"Released ${amount:,.2f} from {strategy.name}")
        return True
    
    def update_strategy_performance(
        self,
        strategy_id: str,
        pnl: float,
        sharpe: float = None,
        max_dd: float = None
    ):
        """Actualizar métricas de performance de una estrategia"""
        if strategy_id not in self.strategies:
            return
        
        strategy = self.strategies[strategy_id]
        strategy.pnl = pnl
        if sharpe is not None:
            strategy.sharpe_ratio = sharpe
        if max_dd is not None:
            strategy.max_drawdown = max_dd
        
        # Verificar si necesita ser promovida o degradada
        self._evaluate_strategy_promotion(strategy)
    
    def _evaluate_strategy_promotion(self, strategy: StrategyAllocation):
        """Evaluar si una estrategia debe cambiar de capa"""
        
        # Reglas de promoción
        if strategy.layer == CapitalLayer.EXPLORER:
            # Promover a SATELLITE si:
            # - Sharpe > 1.0
            # - Max Drawdown < 10%
            # - Return > 5%
            if (strategy.sharpe_ratio > 1.0 and 
                strategy.max_drawdown < 0.10 and 
                strategy.return_pct > 5.0):
                logger.info(f"Strategy {strategy.name} ready for promotion to SATELLITE")
        
        elif strategy.layer == CapitalLayer.SATELLITE:
            # Promover a CORE si:
            # - Sharpe > 1.5
            # - Max Drawdown < 7%
            # - Return > 10%
            if (strategy.sharpe_ratio > 1.5 and 
                strategy.max_drawdown < 0.07 and 
                strategy.return_pct > 10.0):
                logger.info(f"Strategy {strategy.name} ready for promotion to CORE")
        
        # Reglas de degradación
        if strategy.layer == CapitalLayer.CORE:
            # Degradar si:
            # - Max Drawdown > 15%
            # - Sharpe < 0.5 por 3 meses
            if strategy.max_drawdown > 0.15:
                logger.warning(f"Strategy {strategy.name} should be demoted from CORE")
    
    def rebalance(self) -> Dict[str, Any]:
        """
        Rebalancear el portafolio según objetivos
        
        Returns:
            Dict con resultado del rebalancing
        """
        logger.info("Starting portfolio rebalance...")
        
        # Calcular valores actuales
        total_value = self.total_capital
        for strategy in self.strategies.values():
            total_value += strategy.pnl
        
        # Calcular desviaciones
        deviations = {}
        for layer, alloc in self.layers.items():
            current_pct = alloc.allocated / total_value if total_value > 0 else 0
            target_pct = self.layer_targets[layer]
            deviation = current_pct - target_pct
            deviations[layer] = {
                "current_pct": current_pct * 100,
                "target_pct": target_pct * 100,
                "deviation_pct": deviation * 100
            }
        
        # Generar órdenes de rebalanceo
        rebalance_orders = []
        for layer, dev in deviations.items():
            if abs(dev["deviation_pct"]) > 5:  # Umbral de 5%
                action = "INCREASE" if dev["deviation_pct"] < 0 else "DECREASE"
                rebalance_orders.append({
                    "layer": layer.value,
                    "action": action,
                    "deviation": dev["deviation_pct"]
                })
        
        rebalance_result = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_value": total_value,
            "deviations": {l.value: d for l, d in deviations.items()},
            "orders": rebalance_orders,
            "rebalance_needed": len(rebalance_orders) > 0
        }
        
        self.rebalance_history.append(rebalance_result)
        
        if rebalance_orders:
            logger.info(f"Rebalance needed: {len(rebalance_orders)} adjustments")
        else:
            logger.info("No rebalance needed - allocations within tolerance")
        
        return rebalance_result
    
    def get_portfolio_summary(self) -> Dict[str, Any]:
        """Obtener resumen completo del portafolio"""
        
        total_pnl = sum(s.pnl for s in self.strategies.values())
        current_value = self.total_capital + total_pnl
        
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "initial_capital": self.initial_capital,
            "current_value": current_value,
            "total_pnl": total_pnl,
            "return_pct": ((current_value - self.initial_capital) / self.initial_capital * 100),
            "layers": {l.value: a.to_dict() for l, a in self.layers.items()},
            "strategies": {sid: s.to_dict() for sid, s in self.strategies.items()},
            "strategy_count": len(self.strategies)
        }
    
    def get_layer_summary(self, layer: CapitalLayer) -> Dict[str, Any]:
        """Obtener resumen de una capa específica"""
        
        layer_strategies = [s for s in self.strategies.values() if s.layer == layer]
        total_pnl = sum(s.pnl for s in layer_strategies)
        
        return {
            "layer": layer.value,
            "allocation": self.layers[layer].to_dict(),
            "strategies": [s.to_dict() for s in layer_strategies],
            "total_pnl": total_pnl,
            "avg_sharpe": sum(s.sharpe_ratio for s in layer_strategies) / len(layer_strategies) if layer_strategies else 0
        }
    
    def get_available_capital(self, layer: CapitalLayer = None) -> float:
        """Obtener capital disponible"""
        if layer:
            return self.layers[layer].available
        return sum(l.available for l in self.layers.values())
    
    def emergency_liquidation(self, strategy_id: str) -> bool:
        """Liquidación de emergencia de una estrategia"""
        if strategy_id not in self.strategies:
            return False
        
        strategy = self.strategies[strategy_id]
        strategy.status = "liquidating"
        
        logger.critical(f"EMERGENCY LIQUIDATION: {strategy.name}")
        logger.critical(f"  Releasing ${strategy.allocated:,.2f}")
        
        # Liberar todo el capital
        self.release_from_strategy(strategy_id, strategy.allocated)
        strategy.status = "liquidated"
        
        return True

def test_capital_manager():
    """Probar el gestor de capital"""
    print("=" * 60)
    print("AI_VAULT Capital Manager - Test")
    print("=" * 60)
    
    # Inicializar
    cm = CapitalManager(total_capital=100000.0)
    
    # Test 1: Registrar estrategias en diferentes capas
    print("\n[1/4] Registering strategies...")
    
    # Core strategy
    cm.register_strategy(
        strategy_id="core_001",
        name="Conservative Value",
        layer=CapitalLayer.CORE,
        allocation=30000.0
    )
    
    # Satellite strategy
    cm.register_strategy(
        strategy_id="sat_001",
        name="Momentum Trading",
        layer=CapitalLayer.SATELLITE,
        allocation=15000.0
    )
    
    # Explorer strategy
    cm.register_strategy(
        strategy_id="exp_001",
        name="AI Pattern Recognition",
        layer=CapitalLayer.EXPLORER,
        allocation=5000.0
    )
    
    print(f"   Registered {len(cm.strategies)} strategies")
    
    # Test 2: Actualizar performance
    print("\n[2/4] Updating strategy performance...")
    cm.update_strategy_performance("core_001", pnl=1500.0, sharpe=1.2, max_dd=0.05)
    cm.update_strategy_performance("sat_001", pnl=800.0, sharpe=1.1, max_dd=0.08)
    cm.update_strategy_performance("exp_001", pnl=-200.0, sharpe=0.3, max_dd=0.15)
    
    print("   Performance updated")
    
    # Test 3: Portfolio summary
    print("\n[3/4] Portfolio Summary...")
    summary = cm.get_portfolio_summary()
    print(f"   Initial Capital: ${summary['initial_capital']:,.2f}")
    print(f"   Current Value: ${summary['current_value']:,.2f}")
    print(f"   Total PnL: ${summary['total_pnl']:,.2f}")
    print(f"   Return: {summary['return_pct']:.2f}%")
    print(f"   Strategies: {summary['strategy_count']}")
    
    # Test 4: Rebalance
    print("\n[4/4] Rebalance check...")
    rebalance = cm.rebalance()
    print(f"   Rebalance needed: {rebalance['rebalance_needed']}")
    if rebalance['orders']:
        for order in rebalance['orders']:
            print(f"   - {order['layer']}: {order['action']} ({order['deviation']:.2f}%)")
    
    # Mostrar capas
    print("\n   Layer Status:")
    for layer in CapitalLayer:
        layer_sum = cm.get_layer_summary(layer)
        print(f"     {layer.value.upper()}: ${layer_sum['allocation']['allocated']:,.2f} "
              f"({layer_sum['allocation']['utilization_pct']:.1f}% used)")
    
    print("\n" + "=" * 60)
    print("Test Complete - Capital Manager Operational")
    print("=" * 60)

if __name__ == "__main__":
    test_capital_manager()
