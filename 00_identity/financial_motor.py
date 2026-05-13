"""
AI_VAULT Financial Motor Integration
Integración de componentes del Motor Financiero (Fase 6.1)
Conecta trading_engine, risk_manager y capital_manager
"""

import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
import logging

# Importar componentes
from trading_engine import TradingEngine, OrderSide, OrderType
from risk_manager import RiskManager
from capital_manager import CapitalManager, CapitalLayer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FinancialMotor:
    """
    Motor Financiero Integrado de AI_VAULT
    Coordina trading, riesgo y gestión de capital
    """
    
    def __init__(self, initial_capital: float = 100000.0, mode: str = "paper"):
        self.initial_capital = initial_capital
        self.mode = mode
        
        # Inicializar componentes
        self.trading_engine = TradingEngine(mode=mode)
        self.risk_manager = RiskManager()
        self.capital_manager = CapitalManager(total_capital=initial_capital)
        
        # Estado
        self.is_running = False
        self.last_update = datetime.now(timezone.utc)
        
        logger.info("=" * 60)
        logger.info("AI_VAULT Financial Motor Initialized")
        logger.info("=" * 60)
        logger.info(f"Mode: {mode.upper()}")
        logger.info(f"Initial Capital: ${initial_capital:,.2f}")
        logger.info("Components:")
        logger.info("  - Trading Engine: OK")
        logger.info("  - Risk Manager: OK")
        logger.info("  - Capital Manager: OK")
        logger.info("=" * 60)
    
    async def execute_trade(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        strategy_id: str,
        order_type: OrderType = OrderType.MARKET,
        price: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Ejecutar un trade con validación de riesgo y capital
        
        Args:
            symbol: Símbolo del activo
            side: BUY o SELL
            quantity: Cantidad
            strategy_id: ID de la estrategia
            order_type: Tipo de orden
            price: Precio (para órdenes limit)
        
        Returns:
            Dict con resultado de la operación
        """
        
        # 1. Verificar que la estrategia existe
        if strategy_id not in self.capital_manager.strategies:
            return {
                "success": False,
                "error": f"Strategy {strategy_id} not found",
                "timestamp": datetime.now(timezone.utc).isoformat()
            }
        
        strategy = self.capital_manager.strategies[strategy_id]
        
        # 2. Verificar capital disponible
        if side == OrderSide.BUY:
            estimated_cost = quantity * (price or 100)
            if estimated_cost > strategy.available:
                return {
                    "success": False,
                    "error": f"Insufficient capital in strategy {strategy_id}",
                    "required": estimated_cost,
                    "available": strategy.available,
                    "timestamp": datetime.now(timezone.utc).isoformat()
                }
        
        # 3. Verificar límites de riesgo
        portfolio_summary = self.trading_engine.get_portfolio_summary()
        position = self.trading_engine.get_position(symbol)
        
        if position:
            # Calcular riesgo de la posición
            position_data = {
                "quantity": position.quantity,
                "avg_price": position.avg_entry_price,
                "current_price": position.current_price
            }
            
            position_risk = self.risk_manager.calculate_position_risk(
                symbol=symbol,
                position=position_data,
                total_portfolio_value=portfolio_summary["total_value"],
                volatility=0.20
            )
            
            # Verificar si excede límites
            if position_risk.risk_level.value == "high":
                logger.warning(f"High risk detected for {symbol}")
                logger.warning(f"  Recommended action: {position_risk.recommended_action}")
        
        # 4. Ejecutar orden
        order = await self.trading_engine.submit_order(
            symbol=symbol,
            side=side,
            quantity=quantity,
            order_type=order_type,
            price=price
        )
        
        # 5. Actualizar capital de la estrategia
        if order.status.value == "filled":
            trade_value = order.quantity * order.filled_price
            if side == OrderSide.BUY:
                strategy.used += trade_value
            else:
                strategy.used -= trade_value
        
        # 6. Registrar resultado
        result = {
            "success": order.status.value == "filled",
            "order_id": order.id,
            "symbol": symbol,
            "side": side.value,
            "quantity": quantity,
            "filled_price": order.filled_price,
            "status": order.status.value,
            "strategy_id": strategy_id,
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
        
        if order.status.value == "filled":
            logger.info(f"Trade executed: {side.value} {quantity} {symbol} @ ${order.filled_price:.2f}")
        else:
            logger.error(f"Trade failed: {order.id} - {order.status.value}")
        
        return result
    
    def get_portfolio_status(self) -> Dict[str, Any]:
        """Obtener estado completo del portafolio"""
        
        trading_summary = self.trading_engine.get_portfolio_summary()
        capital_summary = self.capital_manager.get_portfolio_summary()
        risk_report = self.risk_manager.get_risk_report()
        
        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "mode": self.mode,
            "trading": trading_summary,
            "capital": capital_summary,
            "risk": risk_report,
            "positions": [p.to_dict() for p in self.trading_engine.get_all_positions()],
            "strategies": len(self.capital_manager.strategies)
        }
    
    def register_strategy(
        self,
        strategy_id: str,
        name: str,
        layer: CapitalLayer,
        allocation: float
    ) -> bool:
        """Registrar una estrategia en el motor financiero"""
        return self.capital_manager.register_strategy(strategy_id, name, layer, allocation)
    
    async def run_monitoring_cycle(self):
        """Ciclo de monitoreo continuo"""
        while self.is_running:
            try:
                # Actualizar precios (simulado)
                # En producción, esto vendría de data_integrator
                
                # Calcular métricas de riesgo
                # self.risk_manager.calculate_portfolio_risk(...)
                
                # Verificar rebalanceo
                rebalance = self.capital_manager.rebalance()
                
                if rebalance["rebalance_needed"]:
                    logger.info("Rebalance needed - check recommendations")
                
                self.last_update = datetime.now(timezone.utc)
                
                # Esperar 60 segundos
                await asyncio.sleep(60)
                
            except Exception as e:
                logger.error(f"Error in monitoring cycle: {e}")
                await asyncio.sleep(60)
    
    def start(self):
        """Iniciar el motor financiero"""
        self.is_running = True
        logger.info("Financial Motor started")
        
        # Iniciar monitoreo en background
        asyncio.create_task(self.run_monitoring_cycle())
    
    def stop(self):
        """Detener el motor financiero"""
        self.is_running = False
        logger.info("Financial Motor stopped")

# Instancia global
financial_motor = FinancialMotor()

async def test_financial_motor():
    """Probar el motor financiero integrado"""
    print("=" * 70)
    print("AI_VAULT Financial Motor - Integration Test")
    print("=" * 70)
    
    motor = FinancialMotor(initial_capital=100000.0, mode="paper")
    
    # Registrar estrategias
    print("\n[1/5] Registering strategies...")
    motor.register_strategy(
        strategy_id="core_value",
        name="Core Value Strategy",
        layer=CapitalLayer.CORE,
        allocation=30000.0
    )
    
    motor.register_strategy(
        strategy_id="sat_momentum",
        name="Satellite Momentum",
        layer=CapitalLayer.SATELLITE,
        allocation=15000.0
    )
    
    print(f"   Registered {len(motor.capital_manager.strategies)} strategies")
    
    # Ejecutar trades
    print("\n[2/5] Executing trades...")
    
    trade1 = await motor.execute_trade(
        symbol="AAPL",
        side=OrderSide.BUY,
        quantity=10,
        strategy_id="core_value"
    )
    print(f"   Trade 1: {trade1['side']} {trade1['quantity']} {trade1['symbol']} - {trade1['status']}")
    
    trade2 = await motor.execute_trade(
        symbol="MSFT",
        side=OrderSide.BUY,
        quantity=5,
        strategy_id="sat_momentum"
    )
    print(f"   Trade 2: {trade2['side']} {trade2['quantity']} {trade2['symbol']} - {trade2['status']}")
    
    # Portfolio status
    print("\n[3/5] Portfolio Status...")
    status = motor.get_portfolio_status()
    print(f"   Total Value: ${status['trading']['total_value']:,.2f}")
    print(f"   Cash: ${status['trading']['cash']:,.2f}")
    print(f"   Open Positions: {status['trading']['open_positions']}")
    print(f"   Total Trades: {status['trading']['total_trades']}")
    
    # Capital layers
    print("\n[4/5] Capital Allocation...")
    for layer in CapitalLayer:
        layer_data = motor.capital_manager.get_layer_summary(layer)
        print(f"   {layer.value.upper()}: ${layer_data['allocation']['allocated']:,.2f} "
              f"({len(layer_data['strategies'])} strategies)")
    
    # Risk metrics
    print("\n[5/5] Risk Status...")
    print(f"   Risk Status: {status['risk']['status']}")
    if status['risk']['recommendations']:
        print(f"   Recommendations:")
        for rec in status['risk']['recommendations'][:2]:
            print(f"     - {rec}")
    
    print("\n" + "=" * 70)
    print("Integration Test Complete - Financial Motor Operational")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(test_financial_motor())
