#!/usr/bin/env python3
"""
QuantConnect Backtests Fetcher
Obtiene los últimos backtests usando la API de QuantConnect
"""

import json
import requests
import os
from datetime import datetime
from pathlib import Path

def load_qc_credentials():
    """Carga las credenciales de QuantConnect"""
    secrets_path = Path("C:/AI_VAULT/tmp_agent/Secrets/quantconnect_access.json")
    
    # Permitir override con variable de entorno
    env_path = os.getenv('QC_SECRETS')
    if env_path:
        secrets_path = Path(env_path)
    
    if not secrets_path.exists():
        raise FileNotFoundError(f"Archivo de credenciales no encontrado: {secrets_path}")
    
    with open(secrets_path, 'r') as f:
        return json.load(f)

def get_latest_backtests(credentials, limit=10):
    """Obtiene los últimos backtests de QuantConnect"""
    base_url = "https://www.quantconnect.com/api/v2"
    
    # Headers de autenticación
    headers = {
        'Authorization': f'Basic {credentials.get("token", "")}',
        'Content-Type': 'application/json'
    }
    
    # Endpoint para obtener backtests
    url = f"{base_url}/backtests/read"
    
    params = {
        'limit': limit
    }
    
    try:
        print(f"Llamando a QuantConnect API: {url}")
        response = requests.get(url, headers=headers, params=params, timeout=30)
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            return data
        else:
            print(f"Error en la respuesta: {response.text}")
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"Error en la petición: {e}")
        return None

def format_backtest_info(backtests_data):
    """Formatea la información de backtests para mostrar"""
    if not backtests_data or 'backtests' not in backtests_data:
        return "No se encontraron backtests"
    
    backtests = backtests_data['backtests']
    
    print(f"\n=== ÚLTIMOS {len(backtests)} BACKTESTS ===")
    
    for i, bt in enumerate(backtests, 1):
        print(f"\n{i}. Backtest ID: {bt.get('backtestId', 'N/A')}")
        print(f"   Nombre: {bt.get('name', 'Sin nombre')}")
        print(f"   Proyecto: {bt.get('projectId', 'N/A')}")
        print(f"   Estado: {bt.get('status', 'N/A')}")
        print(f"   Creado: {bt.get('created', 'N/A')}")
        
        # Estadísticas si están disponibles
        if 'statistics' in bt:
            stats = bt['statistics']
            print(f"   Return: {stats.get('TotalPerformance', {}).get('PortfolioStatistics', {}).get('TotalReturn', 'N/A')}")
            print(f"   Sharpe: {stats.get('TotalPerformance', {}).get('PortfolioStatistics', {}).get('SharpeRatio', 'N/A')}")
        
        print(f"   ---")

def main():
    """Función principal"""
    try:
        print("Cargando credenciales de QuantConnect...")
        credentials = load_qc_credentials()
        
        print("Obteniendo últimos backtests...")
        backtests_data = get_latest_backtests(credentials)
        
        if backtests_data:
            format_backtest_info(backtests_data)
            
            # Guardar resultado en archivo
            output_path = Path("C:/AI_VAULT/tmp_agent/outputs/qc_backtests_latest.json")
            output_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_path, 'w') as f:
                json.dump(backtests_data, f, indent=2)
            
            print(f"\nResultados guardados en: {output_path}")
        else:
            print("No se pudieron obtener los backtests")
            
    except Exception as e:
        print(f"Error: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
