"""
AI_VAULT PocketOption Integrator
Integra datos de PocketOption al sistema principal
"""

import json
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Any
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class PocketOptionIntegrator:
    """
    Integrador de PocketOption para el dashboard y estadísticas
    """
    
    def __init__(self):
        self.bridge_path = Path(r"C:\AI_VAULT\tmp_agent\state\rooms\brain_binary_paper_pb04_demo_execution\browser_bridge_normalized_feed.json")
        self.latest_path = Path(r"C:\AI_VAULT\tmp_agent\state\rooms\brain_binary_paper_pb04_demo_execution\browser_bridge_latest.json")
        self.data: Dict[str, Any] = {}
        self.symbols = ["EURUSD_otc", "AUDUSD_otc", "AUDNZD_otc", "AUDCAD_otc", "USDJPY_otc"]
        
        logger.info("PocketOptionIntegrator initialized")
    
    def read_bridge_data(self) -> Optional[Dict]:
        """Leer datos del bridge de PocketOption"""
        try:
            if self.bridge_path.exists():
                with open(self.bridge_path, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Error reading bridge data: {e}")
        return None
    
    def get_latest_prices(self) -> Dict[str, float]:
        """Obtener últimos precios de los símbolos"""
        data = self.read_bridge_data()
        prices = {}
        
        if data and 'rows' in data:
            rows = data['rows']
            for symbol in self.symbols:
                # Buscar última fila para este símbolo
                for row in reversed(rows):
                    if row.get('symbol') == symbol and row.get('price'):
                        prices[symbol] = float(row['price'])
                        break
        
        return prices
    
    def get_balance(self) -> Optional[float]:
        """Obtener balance demo"""
        data = self.read_bridge_data()
        if data and 'rows' in data and len(data['rows']) > 0:
            last_row = data['rows'][-1]
            balance = last_row.get('balance_demo')
            if balance:
                return float(balance)
        return None
    
    def get_statistics(self) -> Dict[str, Any]:
        """Obtener estadísticas de trading"""
        data = self.read_bridge_data()
        
        if not data or 'rows' not in data:
            return {
                "status": "no_data",
                "message": "No PocketOption data available"
            }
        
        rows = data['rows']
        
        # Calcular estadísticas
        total_updates = len(rows)
        unique_symbols = set(row.get('symbol') for row in rows if row.get('symbol'))
        
        # Última actualización
        last_update = rows[-1].get('captured_utc') if rows else None
        
        # Precios actuales
        current_prices = self.get_latest_prices()
        
        # Balance
        balance = self.get_balance()
        
        return {
            "status": "active",
            "total_updates": total_updates,
            "active_symbols": len(unique_symbols),
            "symbols": list(unique_symbols),
            "last_update": last_update,
            "current_prices": current_prices,
            "balance_demo": balance,
            "bridge_port": 8765,
            "extension_status": "connected" if current_prices else "waiting_data"
        }
    
    def get_price_history(self, symbol: str, limit: int = 100) -> List[Dict]:
        """Obtener historial de precios para un símbolo"""
        data = self.read_bridge_data()
        history = []
        
        if data and 'rows' in data:
            for row in data['rows']:
                if row.get('symbol') == symbol:
                    history.append({
                        "timestamp": row.get('captured_utc'),
                        "price": row.get('price'),
                        "pair": row.get('pair')
                    })
        
        return history[-limit:]
    
    async def monitor_loop(self):
        """Loop de monitoreo continuo"""
        while True:
            stats = self.get_statistics()
            if stats['status'] == 'active':
                logger.info(f"PocketOption: {stats['active_symbols']} symbols, Balance: ${stats.get('balance_demo', 0)}")
            await asyncio.sleep(30)

# Instancia global
pocketoption_integrator = PocketOptionIntegrator()

if __name__ == "__main__":
    # Test
    stats = pocketoption_integrator.get_statistics()
    print(json.dumps(stats, indent=2))
