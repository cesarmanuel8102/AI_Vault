#!/usr/bin/env python3
"""
Script para procesar resultados de QuantConnect y actualizar scorecards
Creado por Brain V9 - Agente Autónomo
"""

import json
import os
import sys
import requests
from datetime import datetime
from pathlib import Path

# Configuración
AI_VAULT_ROOT = Path("C:/AI_VAULT")
SECRETS_PATH = AI_VAULT_ROOT / "tmp_agent" / "Secrets" / "quantconnect_access.json"
BRAIN_API = "http://127.0.0.1:8090"

def load_qc_credentials():
    """Carga credenciales de QuantConnect"""
    try:
        if SECRETS_PATH.exists():
            with open(SECRETS_PATH, 'r') as f:
                return json.load(f)
        else:
            # Fallback a variable de entorno
            qc_secrets_env = os.getenv('QC_SECRETS')
            if qc_secrets_env:
                with open(qc_secrets_env, 'r') as f:
                    return json.load(f)
            else:
                print("❌ No se encontraron credenciales de QuantConnect")
                return None
    except Exception as e:
        print(f"❌ Error cargando credenciales: {e}")
        return None

def fetch_qc_backtests(credentials, limit=10):
    """Obtiene backtests recientes de QuantConnect"""
    try:
        headers = {
            'Authorization': f"Basic {credentials.get('api_token', '')}",
            'Content-Type': 'application/json'
        }
        
        # API endpoint para listar backtests
        url = f"https://www.quantconnect.com/api/v2/backtests/read"
        params = {
            'projectId': credentials.get('project_id', ''),
            'start': 0,
            'length': limit
        }
        
        response = requests.get(url, headers=headers, params=params, timeout=30)
        
        if response.status_code == 200:
            data = response.json()
            return data.get('backtests', [])
        else:
            print(f"❌ Error API QuantConnect: {response.status_code} - {response.text}")
            return []
            
    except Exception as e:
        print(f"❌ Error obteniendo backtests: {e}")
        return []

def process_backtest_results(backtests):
    """Procesa resultados de backtests para scorecards"""
    processed_results = []
    
    for bt in backtests:
        try:
            # Extraer métricas clave
            stats = bt.get('statistics', {})
            
            result = {
                'backtest_id': bt.get('backtestId', ''),
                'name': bt.get('name', 'Sin nombre'),
                'created': bt.get('created', ''),
                'completed': bt.get('completed', ''),
                'strategy': bt.get('name', '').split('_')[0] if '_' in bt.get('name', '') else 'unknown',
                'metrics': {
                    'total_return': stats.get('Total Performance', {}).get('value', 0),
                    'sharpe_ratio': stats.get('Sharpe Ratio', {}).get('value', 0),
                    'max_drawdown': stats.get('Drawdown', {}).get('value', 0),
                    'win_rate': stats.get('Win Rate', {}).get('value', 0),
                    'profit_loss_ratio': stats.get('Profit-Loss Ratio', {}).get('value', 0),
                    'trades_count': stats.get('Total Trades', {}).get('value', 0)
                },
                'timestamp': datetime.now().isoformat()
            }
            
            processed_results.append(result)
            print(f"✅ Procesado: {result['name']} - Return: {result['metrics']['total_return']:.2%}")
            
        except Exception as e:
            print(f"❌ Error procesando backtest {bt.get('backtestId', 'unknown')}: {e}")
            continue
    
    return processed_results

def update_scorecards_via_brain(processed_results):
    """Actualiza scorecards usando la API de Brain V9"""
    try:
        # Endpoint para ingest_qc_results
        url = f"{BRAIN_API}/api/trading/ingest_qc_results"
        
        payload = {
            'results': processed_results,
            'source': 'quantconnect',
            'timestamp': datetime.now().isoformat(),
            'processor': 'process_qc_scorecards.py'
        }
        
        response = requests.post(url, json=payload, timeout=30)
        
        if response.status_code == 200:
            result = response.json()
            print(f"✅ Scorecards actualizados: {result.get('message', 'OK')}")
            return True
        else:
            print(f"❌ Error actualizando scorecards: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error conectando con Brain API: {e}")
        return False

def main():
    """Función principal"""
    print("🚀 Iniciando procesamiento de resultados QuantConnect...")
    
    # 1. Cargar credenciales
    credentials = load_qc_credentials()
    if not credentials:
        sys.exit(1)
    
    # 2. Obtener backtests
    print("📡 Obteniendo backtests de QuantConnect...")
    backtests = fetch_qc_backtests(credentials)
    
    if not backtests:
        print("⚠️ No se encontraron backtests")
        sys.exit(1)
    
    print(f"📊 Encontrados {len(backtests)} backtests")
    
    # 3. Procesar resultados
    print("⚙️ Procesando resultados...")
    processed = process_backtest_results(backtests)
    
    if not processed:
        print("❌ No se pudieron procesar los resultados")
        sys.exit(1)
    
    # 4. Actualizar scorecards
    print("📈 Actualizando scorecards...")
    success = update_scorecards_via_brain(processed)
    
    if success:
        print(f"✅ Proceso completado: {len(processed)} resultados procesados")
        
        # Resumen
        print("\n📋 RESUMEN:")
        for result in processed:
            metrics = result['metrics']
            print(f"  • {result['name']}: Return {metrics['total_return']:.2%}, Sharpe {metrics['sharpe_ratio']:.2f}, Trades {metrics['trades_count']}")
    else:
        print("❌ Error en la actualización de scorecards")
        sys.exit(1)

if __name__ == "__main__":
    main()
