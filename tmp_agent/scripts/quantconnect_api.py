# script Python para acceder a la API de QuantConnect
import requests
# credenciales obtenidas de grep_codebase
api_key = "" 
api_secret = ""

def get_data():
    url = "https://api.quantconnect.com/v3/data"
    headers = {
        'Authorization': f'Bearer {api_key}'
    }
    response = requests.get(url, headers=headers)
    return response.json()
