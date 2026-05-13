import json, hashlib, base64, time, requests, sys

with open('C:/AI_VAULT/tmp_agent/Secrets/quantconnect_access.json') as f:
    creds = json.load(f)

user_id = creds['user_id']
token = creds['token']
ts = str(int(time.time()))
hash_bytes = hashlib.sha256(f'{token}:{ts}'.encode('utf-8')).digest()
auth = base64.b64encode(f'{user_id}:{hash_bytes.hex()}'.encode('utf-8')).decode('utf-8')
headers = {'Authorization': f'Basic {auth}', 'Timestamp': ts}

proj_id = 29652652
bt_id = sys.argv[1] if len(sys.argv) > 1 else 'fb414b5ef7726a25bd4258bdb8645eeb'

r = requests.post('https://www.quantconnect.com/api/v2/backtests/read/log',
    headers=headers,
    json={'projectId': proj_id, 'backtestId': bt_id, 'start': 0, 'end': 500})
logs = r.json().get('logs', [])
for log in logs:
    print(log)
