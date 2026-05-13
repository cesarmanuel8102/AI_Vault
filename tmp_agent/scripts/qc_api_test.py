import os
import json
import requests
from pathlib import Path

# Cargar credenciales desde la ruta configurada
creds_path = os.getenv("QC_SECRETS", r"C:\AI_VAULT\tmp_agent\Secrets\quantconnect_access.json")
print(f"Buscando credenciales en: {creds_path}")

if not Path(creds_path).exists():
    print(f"ERROR: Archivo de credenciales no encontrado: {creds_path}")
    exit(1)

with open(creds_path, 'r') as f:
    creds = json.load(f)

user_id = creds.get('user-id') or creds.get('userId') or creds.get('user_id')
token = creds.get('api-token') or creds.get('apiToken') or creds.get('token') or creds.get('accessToken')

if not user_id or not token:
    print("ERROR: Credenciales incompletas. Se requiere user-id y api-token")
    print(f"Claves encontradas: {list(creds.keys())}")
    exit(1)

print(f"Credenciales cargadas. User ID: {user_id[:4]}...")

# Llamar a la API de QuantConnect (endpoint de autenticación/proyectos)
base_url = "https://www.quantconnect.com/api/v2"
endpoint = f"{base_url}/projects/list"

headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json"
}

# QuantConnect usa autenticación básica o header específico dependiendo de la implementación
# Intentamos con el formato estándar de API
params = {
    "userId": user_id,
    "token": token
}

try:
    print(f"Llamando a: {endpoint}")
    response = requests.get(endpoint, headers=headers, params=params, timeout=30)
    print(f"Status Code: {response.status_code}")
    print(f"Response: {response.text[:500]}")
    
    if response.status_code == 200:
        data = response.json()
        print(f"Proyectos encontrados: {len(data.get('projects', []))}")
    else:
        print(f"Error en la llamada: {response.status_code}")
        
except Exception as e:
    print(f"Excepción durante la llamada: {e}")
    import traceback
    traceback.print_exc()
