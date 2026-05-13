import requests

r = requests.post('http://localhost:8090/chat',
                  json={'message': 'revisa el estado general de todos los servicios', 
                        'session_id': 'test_debug_allsvc2'},
                  timeout=90)
data = r.json()
resp = data.get('response', '')
print('FULL RESPONSE:')
print(resp[:3000])
print()
print('---')
print(f'Length: {len(resp)}')
print(f'Contains servicios: {"servicios" in resp.lower()}')
print(f'Contains healthy: {"healthy" in resp.lower()}')
print(f'Contains overall_status: {"overall_status" in resp}')
print(f'Contains critical_services_down: {"critical_services_down" in resp}')
bt = '`' * 3
print(f'Contains triple backtick: {bt in resp}')
