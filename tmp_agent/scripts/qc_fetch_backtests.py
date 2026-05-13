#!/usr/bin/env python3
"""
Script para obtener últimos backtests de QuantConnect API
Brain V9 - Autonomous System Agent
"""
import json
import requests
from pathlib import Path
from datetime import datetime

# Cargar credenciales
CREDS_PATH = Path(r"C:\AI_VAULT\tmp_agent\Secrets\quantconnect_access.json")
with open(CREDS_PATH) as f:
    creds = json.load(f)

# Configuración API QC
BASE_URL = "https://www.quantconnect.com/api/v2"
HEADERS = {
    "Authorization": f"Token {creds.get('access_token')}",
    "Content-Type": "application/json"
}

def get_backtests(project_id=None, limit=10):
    """Obtiene últimos backtests de QuantConnect"""
    endpoint = f"{BASE_URL}/backtests/read"
    
    payload = {
        "limit": limit,
        "sort": "created-desc"
    }
    
    if project_id:
        payload["projectId"] = project_id
    
    try:
        response = requests.post(
            endpoint,
            headers=HEADERS,
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        data = response.json()
        
        print(f"[{datetime.now().isoformat()}] Backtests obtenidos exitosamente")
        print(f"Total recibidos: {len(data.get('backtests', []))}")
        
        # Guardar resultados
        output_path = Path(r"C:\AI_VAULT\tmp_agent\output") / f"qc_backtests_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w') as f:
            json.dump(data, f, indent=2)
        
        print(f"Resultados guardados en: {output_path}")
        return data
        
    except requests.exceptions.RequestException as e:
        print(f"Error en API call: {e}")
        if hasattr(e.response, 'text'):
            print(f"Response: {e.response.text}")
        raise

if __name__ == "__main__":
    print("="*60)
    print("QuantConnect Backtest Fetcher - Brain V9")
    print("="*60)
    
    # Obtener backtests (sin filtro de proyecto = todos)
    results = get_backtests(limit=20)
    
    # Mostrar resumen
    backtests = results.get('backtests', [])
    if backtests:
        print("\n--- Últimos Backtests ---")
        for bt in backtests[:5]:  # Mostrar top 5
            print(f"ID: {bt.get('backtestId')} | Proyecto: {bt.get('projectId')} | "
                  f"Creado: {bt.get('created', 'N/A')} | Estado: {bt.get('status', 'N/A')}")
    else:
        print("No se encontraron backtests")