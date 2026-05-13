import requests
access_token = read_file('tmp_agent/Secrets/quantconnect_access.json')['token']
api_url = 'https://api.quantconnect.com/v3'
response = requests.get(api_url, headers={'Authorization': f'Bearer {access_token}'}))