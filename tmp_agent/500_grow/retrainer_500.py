# retrainer_500.py
from quantconnect import ApiClient
import time

class Retrainer:
    def __init__(self, token):
        self.api = ApiClient(token)
    
    def reoptimize_params(self, deployment_id, performance):
        """
        Ajusta los parámetros críticos según el desempeño en tiempo real
        """
        changes = {}
        
        # Ajuste de stop-loss basado en volatilidad
        if performance['daily_volatility'] > 0.02:
            new_sl = 0.08  # Aumentar stop-loss en mercados volátiles
        else:
            new_sl = 0.05
        changes['STOP_LOSS'] = new_sl
        
        # Ajuste de tamaño de posición
        if performance['winrate'] > 0.6:
            changes['POSITION_SIZE_ADJ'] = 0.2  # +20% size tras éxito
        elif performance['drawdown'] > 0.1:
            changes['POSITION_SIZE_ADJ'] = 0.05  # Reducir tamaño
        
        # Optimización agresiva si el crecimiento es lento
        if performance['equity_growth'] < 0.05:
            changes['PROFIT_TARGET'] = 0.2  # Aumentar target a 20%
        
        if changes:
            self.api.update_parameters(deployment_id, changes)
            return f"Reoptimización aplicada: {changes}"
        return "Sin cambios: parámetros óptimos"

    def analyze_trades(self, deployment_id):
        metrics = self.api.get_trade_stats(deployment_id)
        
        # Calcular métricas clave
        daily_pnl = self._calculate_daily_pnl(metrics)
        winrate = self._calculate_winrate(metrics)
        volatility = self._calculate_volatility(metrics)
        
        return {
            'daily_pnl': daily_pnl,
            'winrate': winrate,
            'daily_volatility': volatility,
            'equity_growth': metrics['equity'] / 500 - 1
        }
    
    def _calculate_daily_pnl(self, metrics):
        return sum(t['pnl'] for t in metrics['trades']) / len(metrics['trades'])
    
    def _calculate_winrate(self, metrics):
        wins = [t for t in metrics['trades'] if t['pnl'] > 0]
        return len(wins) / len(metrics['trades'])

    def _calculate_volatility(self, metrics):
        prices = [t['price'] for t in metrics['trades']]
        return np.std(prices) / np.mean(prices)

# Integración con el sistema
if __name__ == '__main__':
    token = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
    retrainer = Retrainer(token)
    
    # Ejemplo de reoptimización
    stats = retrainer.analyze_trades(deployment_id="live_1234")
    print(retrainer.reoptimize_params(deployment_id="live_1234", performance=stats))