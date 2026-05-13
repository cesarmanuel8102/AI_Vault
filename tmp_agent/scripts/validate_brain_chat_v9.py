import requests
url = 'http://127.0.0.1:8090/health'
response = requests.get(url)
if response.status_code == 200:
    print('Conectado a Brain Chat V9')
else:
    print('No conectado a Brain Chat V9')