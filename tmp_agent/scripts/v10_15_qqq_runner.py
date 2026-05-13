"""
Runner for v10.15 QQQ – launches IS, OOS and Full backtests via QuantConnect API.

Requisitos:
- Parámetros start_year y end_year explícitos (no usar BT_START/BT_END internos).
- Autenticación SHA‑256 (TOKEN:timestamp) y timeout=30 s con reintento.
- Formato de progreso como porcentaje (f'{progress:.0%}').
- Guardar resultados completos (27 métricas) en JSON.
"""

import hashlib
import json
import os
import time
from datetime import datetime
from quantconnect.api import ApiClient, ApiException

# ------------------------------------------------------------
# Configuración del proyecto (identificadores del usuario)
# ------------------------------------------------------------
USER_ID = "384945"
TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
ORG_ID = "6d487993ca17881264c2ac55e41ae539"
PROJECT_ID = "29490680"

# ------------------------------------------------------------
# Helper para autenticación SHA‑256 con timestamp
# ------------------------------------------------------------
def get_auth_header():
    timestamp = int(time.time())
    token_hash = hashlib.sha256(f"{TOKEN}:{timestamp}".encode()).hexdigest()
    return {"Authorization": f"Bearer {token_hash}", "Timestamp": str(timestamp)}

# ------------------------------------------------------------
# Función genérica que llama a la API de QC con reintentos
# ------------------------------------------------------------
def call_qc_api(endpoint, method="GET", data=None, max_retries=3, timeout=30):
    url = f"https://www.quantconnect.com/api/v2/{endpoint}"
    headers = get_auth_header()
    for attempt in range(1, max_retries + 1):
        try:
            client = ApiClient()
            if method == "GET":
                response = client.call_api(url, "GET", headers=headers, timeout=timeout)
            elif method == "POST":
                response = client.call_api(url, "POST", headers=headers, body=data, timeout=timeout)
            else:
                raise ValueError("Unsupported HTTP method")
            return json.loads(response.data)
        except (ApiException, Exception) as e:
            if attempt == max_retries:
                raise
            time.sleep(2 ** attempt)  # back‑off exponencial

# ------------------------------------------------------------
# Build backtest payload – recibe start_year y end_year
# ------------------------------------------------------------
def build_backtest_payload(start_year, end_year, name_suffix):
    # La estrategia está en el archivo v10_15_qqq.py del proyecto
    payload = {
        "projectId": PROJECT_ID,
        "name": f"v10_15_qqq_{name_suffix}",
        "parameters": {
            "start_year": start_year,
            "end_year": end_year,
        },
        "description": f"v10.15 QQQ backtest {name_suffix}",
        "backtest": True,
    }
    return payload

# ------------------------------------------------------------
# Ejecuta un backtest y devuelve el ID
# ------------------------------------------------------------
def launch_backtest(start_year, end_year, suffix):
    payload = build_backtest_payload(start_year, end_year, suffix)
    resp = call_qc_api("backtests/create", method="POST", data=json.dumps(payload))
    return resp["backtestId"]

# ------------------------------------------------------------
# Espera a que el backtest termine, muestra progreso y extrae métricas
# ------------------------------------------------------------
def wait_backtest(bt_id):
    while True:
        bt = call_qc_api(f"backtests/{bt_id}")
        status = bt.get("status")
        progress = bt.get("progress", 0)
        print(f"Backtest {bt_id}: {status} – progress {progress:.0%}")
        if status in ("Completed", "Failed"):
            return bt
        time.sleep(10)

# ------------------------------------------------------------
# Main – lanza IS, OOS y Full y guarda resultados
# ------------------------------------------------------------
def main():
    # IS: 2023‑01‑01 a 2024‑12‑31
    is_id = launch_backtest(2023, 2024, "IS")
    is_res = wait_backtest(is_id)
    # OOS: 2025‑01‑01 a 2026‑12‑31
    oos_id = launch_backtest(2025, 2026, "OOS")
    oos_res = wait_backtest(oos_id)
    # Full: 2023‑01‑01 a 2026‑12‑31
    full_id = launch_backtest(2023, 2026, "FULL")
    full_res = wait_backtest(full_id)

    results = {
        "IS": is_res,
        "OOS": oos_res,
        "FULL": full_res,
    }
    out_path = os.path.join(os.getcwd(), "v10_15_qqq_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"Resultados guardados en {out_path}")

if __name__ == "__main__":
    main()
