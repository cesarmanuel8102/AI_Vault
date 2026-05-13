# live_500_manager.py
import time
from qc_api_tools import QCAPIWrapper
import os

# Configuración crítica para $500
TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
PROJECT_ID = 29490680
STRATEGY_NAME = "aggressive_500_grow"
CAPITAL = 500


def live_cycle():
    api = QCAPIWrapper(TOKEN)
    
    # 1. Despliegue inicial en Paper Live
    deploy = api.deploy_live(
        project_id=PROJECT_ID,
        strategy_name=STRATEGY_NAME,
        capital=CAPITAL
    )
    print(f"[DEPLOY] {STRATEGY_NAME} deployed as deployment {deploy.get('id')}")
    
    # 2. Loop continuo de monitoreo (5 minutos)
    while True:
        try:
            stats = api.get_live_metrics(deploy_id=deploy.get('id'))
            equity = stats.get('equity', 0)
            winrate = stats.get('winrate', 1.0)
                    
            # 3. Ajuste automático si se cumplen condiciones
            if equity < CAPITAL * 0.95:  # -5% en capital
                print("[OPTIMIZE] Activating reoptimization")
                api.reoptimize_parameters(
                    deployment_id=deploy.get('id'),
                    new_params={
                        "MAX_DAILY_TRADES": 12,
                        "MAX_ENTRY_PCT": 0.035
                    }
                )
            
            # 4. Detección de duplicación de capital
            if equity >= CAPITAL * 2:
                print(f"[GROWTH] Capital DOUBLED: ${equity:.2f}")
                api.trigger_alert(f"Doubled capital to ${equity:.2f} in {stats.get('days_active')} days")
                
            # 5. Reporte diario en consola
            print(f"[METRICS] Equity: ${equity:.2f} | Winrate: {winrate:.1%} | Trades: {stats.get('trades')}")
        except Exception as e:
            print(f"[ERROR] Live cycle error: {str(e)}")
            
        # Poll cada 5 minutos
        time.sleep(300)

def main():
    print("=== AGGRESSIVE_500 GROWTH SYSTEM ===")
    live_cycle()
    
if __name__ == "__main__":
    main()
