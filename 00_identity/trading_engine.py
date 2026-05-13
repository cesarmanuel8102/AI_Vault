"""
AI_VAULT Trading Engine v1.0
Motor de trading para Fase 6.1 - MOTOR_FINANCIERO
"""

import asyncio
import json
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class OrderType(Enum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"

class OrderSide(Enum):
    BUY = "buy"
    SELL = "sell"

class OrderStatus(Enum):
    PENDING = "pending"
    OPEN = "open"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"

@dataclass
class Order:
    id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    price: Optional[float] = None
    stop_price: Optional[float] = None
    status: OrderStatus = OrderStatus.PENDING
    created_at: datetime = None
    filled_at: Optional[datetime] = None
    filled_price: Optional[float] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now(timezone.utc)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "symbol": self.symbol,
            "side": self.side.value,
            "order_type": self.order_type.value,
            "quantity": self.quantity,
            "price": self.price,
            "stop_price": self.stop_price,
            "status": self.status.value,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "filled_at": self.filled_at.isoformat() if self.filled_at else None,
            "filled_price": self.filled_price
        }

@dataclass
class Position:
    symbol: str
    quantity: float
    avg_entry_price: float
    current_price: float
    unrealized_pnl: float
    realized_pnl: float
    opened_at: datetime
    
    @property
    def market_value(self) -> float:
        return self.quantity * self.current_price
    
    @property
    def cost_basis(self) -> float:
        return self.quantity * self.avg_entry_price
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "symbol": self.symbol,
            "quantity": self.quantity,
            "avg_entry_price": self.avg_entry_price,
            "current_price": self.current_price,
            "unrealized_pnl": self.unrealized_pnl,
            "realized_pnl": self.realized_pnl,
            "market_value": self.market_value,
            "cost_basis": self.cost_basis,
            "opened_at": self.opened_at.isoformat()
        }

class TradingEngine:
    """
    Motor de trading principal para AI_VAULT
    Soporta paper trading y gestión de órdenes
    """
    
    def __init__(self, mode: str = "paper"):
        self.mode = mode  # "paper" o "live"
        self.orders: Dict[str, Order] = {}
        self.positions: Dict[str, Position] = {}
        self.order_history: List[Order] = []
        self.trade_history: List[Dict] = []
        self.cash = 100000.0  # Capital inicial para paper trading
        self.initial_capital = 100000.0
        
        logger.info(f"TradingEngine initialized in {mode} mode")
        logger.info(f"Initial capital: ${self.cash:,.2f}")
    
    async def submit_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        order_type: OrderType = OrderType.MARKET,
        price: Optional[float] = None,
        stop_price: Optional[float] = None
    ) -> Order:
        """Enviar una orden al mercado"""
        
        order_id = f"order_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{len(self.orders)}"
        
        order = Order(
            id=order_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            stop_price=stop_price
        )
        
        # Validar orden
        if not self._validate_order(order):
            order.status = OrderStatus.REJECTED
            logger.warning(f"Order {order_id} rejected: validation failed")
            return order
        
        self.orders[order_id] = order
        
        # Simular ejecución para paper trading
        if self.mode == "paper":
            await self._simulate_execution(order)
        
        logger.info(f"Order submitted: {order_id} - {side.value} {quantity} {symbol}")
        return order
    
    def _validate_order(self, order: Order) -> bool:
        """Validar una orden antes de enviarla"""
        
        # Validar cantidad
        if order.quantity <= 0:
            logger.error("Invalid quantity: must be > 0")
            return False
        
        # Validar capital disponible para compras
        if order.side == OrderSide.BUY:
            estimated_cost = order.quantity * (order.price or 100)  # Precio estimado
            if estimated_cost > self.cash:
                logger.error(f"Insufficient funds: need ${estimated_cost:,.2f}, have ${self.cash:,.2f}")
                return False
        
        # Validar posición existente para ventas
        if order.side == OrderSide.SELL:
            position = self.positions.get(order.symbol)
            if not position or position.quantity < order.quantity:
                logger.error(f"Insufficient position: cannot sell {order.quantity} {order.symbol}")
                return False
        
        return True
    
    async def _simulate_execution(self, order: Order):
        """Simular la ejecución de una orden (paper trading)"""
        
        # Simular delay de ejecución
        await asyncio.sleep(0.5)
        
        # Simular precio de ejecución
        import random
        base_price = 100.0  # Precio base simulado
        execution_price = base_price * (1 + random.uniform(-0.001, 0.001))
        
        order.status = OrderStatus.FILLED
        order.filled_at = datetime.now(timezone.utc)
        order.filled_price = execution_price
        
        # Actualizar posición
        self._update_position(order)
        
        # Registrar trade
        self._record_trade(order)
        
        logger.info(f"Order filled: {order.id} at ${execution_price:.2f}")
    
    def _update_position(self, order: Order):
        """Actualizar posición después de una ejecución"""
        
        symbol = order.symbol
        
        if symbol not in self.positions:
            # Nueva posición
            self.positions[symbol] = Position(
                symbol=symbol,
                quantity=order.quantity if order.side == OrderSide.BUY else -order.quantity,
                avg_entry_price=order.filled_price,
                current_price=order.filled_price,
                unrealized_pnl=0.0,
                realized_pnl=0.0,
                opened_at=datetime.now(timezone.utc)
            )
        else:
            # Actualizar posición existente
            position = self.positions[symbol]
            
            if order.side == OrderSide.BUY:
                # Aumentar posición
                total_cost = (position.quantity * position.avg_entry_price) + (order.quantity * order.filled_price)
                total_quantity = position.quantity + order.quantity
                position.avg_entry_price = total_cost / total_quantity
                position.quantity = total_quantity
            else:
                # Reducir posición
                position.realized_pnl += (order.filled_price - position.avg_entry_price) * order.quantity
                position.quantity -= order.quantity
                
                if position.quantity == 0:
                    del self.positions[symbol]
        
        # Actualizar cash
        if order.side == OrderSide.BUY:
            self.cash -= order.quantity * order.filled_price
        else:
            self.cash += order.quantity * order.filled_price
    
    def _record_trade(self, order: Order):
        """Registrar un trade en el historial"""
        
        trade = {
            "order_id": order.id,
            "symbol": order.symbol,
            "side": order.side.value,
            "quantity": order.quantity,
            "price": order.filled_price,
            "timestamp": order.filled_at.isoformat(),
            "value": order.quantity * order.filled_price
        }
        
        self.trade_history.append(trade)
    
    def get_portfolio_summary(self) -> Dict[str, Any]:
        """Obtener resumen del portafolio"""
        
        total_value = self.cash
        total_unrealized_pnl = 0.0
        total_realized_pnl = 0.0
        
        for position in self.positions.values():
            total_value += position.market_value
            total_unrealized_pnl += position.unrealized_pnl
            total_realized_pnl += position.realized_pnl
        
        return {
            "cash": self.cash,
            "positions_value": total_value - self.cash,
            "total_value": total_value,
            "unrealized_pnl": total_unrealized_pnl,
            "realized_pnl": total_realized_pnl,
            "total_pnl": total_unrealized_pnl + total_realized_pnl,
            "return_pct": ((total_value - self.initial_capital) / self.initial_capital) * 100,
            "open_positions": len(self.positions),
            "total_trades": len(self.trade_history)
        }
    
    def get_position(self, symbol: str) -> Optional[Position]:
        """Obtener posición para un símbolo"""
        return self.positions.get(symbol)
    
    def get_all_positions(self) -> List[Position]:
        """Obtener todas las posiciones"""
        return list(self.positions.values())
    
    def get_order(self, order_id: str) -> Optional[Order]:
        """Obtener una orden por ID"""
        return self.orders.get(order_id)
    
    def get_open_orders(self) -> List[Order]:
        """Obtener órdenes abiertas"""
        return [o for o in self.orders.values() if o.status == OrderStatus.OPEN]
    
    async def cancel_order(self, order_id: str) -> bool:
        """Cancelar una orden"""
        order = self.orders.get(order_id)
        if order and order.status == OrderStatus.OPEN:
            order.status = OrderStatus.CANCELLED
            logger.info(f"Order cancelled: {order_id}")
            return True
        return False
    
    def update_prices(self, prices: Dict[str, float]):
        """Actualizar precios de mercado"""
        for symbol, price in prices.items():
            if symbol in self.positions:
                position = self.positions[symbol]
                position.current_price = price
                position.unrealized_pnl = (price - position.avg_entry_price) * position.quantity

# Instancia global
trading_engine = TradingEngine(mode="paper")

async def test_trading_engine():
    """Probar el motor de trading"""
    print("=" * 60)
    print("AI_VAULT Trading Engine - Test")
    print("=" * 60)
    
    engine = TradingEngine(mode="paper")
    
    # Test 1: Comprar acciones
    print("\n[1/4] Testing BUY order...")
    order1 = await engine.submit_order(
        symbol="AAPL",
        side=OrderSide.BUY,
        quantity=10,
        order_type=OrderType.MARKET
    )
    print(f"   Order: {order1.id}")
    print(f"   Status: {order1.status.value}")
    print(f"   Filled at: ${order1.filled_price:.2f}")
    
    # Test 2: Comprar más
    print("\n[2/4] Testing second BUY order...")
    order2 = await engine.submit_order(
        symbol="AAPL",
        side=OrderSide.BUY,
        quantity=5,
        order_type=OrderType.MARKET
    )
    print(f"   Order: {order2.id}")
    print(f"   Status: {order2.status.value}")
    
    # Test 3: Vender parcialmente
    print("\n[3/4] Testing SELL order...")
    order3 = await engine.submit_order(
        symbol="AAPL",
        side=OrderSide.SELL,
        quantity=5,
        order_type=OrderType.MARKET
    )
    print(f"   Order: {order3.id}")
    print(f"   Status: {order3.status.value}")
    print(f"   Filled at: ${order3.filled_price:.2f}")
    
    # Test 4: Portfolio summary
    print("\n[4/4] Portfolio Summary...")
    summary = engine.get_portfolio_summary()
    print(f"   Cash: ${summary['cash']:,.2f}")
    print(f"   Positions Value: ${summary['positions_value']:,.2f}")
    print(f"   Total Value: ${summary['total_value']:,.2f}")
    print(f"   Return: {summary['return_pct']:.2f}%")
    print(f"   Open Positions: {summary['open_positions']}")
    print(f"   Total Trades: {summary['total_trades']}")
    
    # Mostrar posición
    position = engine.get_position("AAPL")
    if position:
        print(f"\n   AAPL Position:")
        print(f"     Quantity: {position.quantity}")
        print(f"     Avg Entry: ${position.avg_entry_price:.2f}")
        print(f"     Market Value: ${position.market_value:,.2f}")
        print(f"     Unrealized PnL: ${position.unrealized_pnl:,.2f}")
    
    print("\n" + "=" * 60)
    print("Test Complete - Trading Engine Operational")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(test_trading_engine())
