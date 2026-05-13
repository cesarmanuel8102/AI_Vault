# deploy_500_grow.py
import json
import requests
import os
import time
import hashlib
import base64
from datetime import datetime

# Configuration
SECRETS_DIR = 'C:/AI_VAULT/tmp_agent/Secrets'
ALGORITHM_DIR = 'C:/AI_VAULT/tmp_agent/500_grow'
PROJECT_ID = 29490680
BASE_URL = 'https://www.quantconnect.com/api/v2'

# Load API credentials
with open(os.path.join(SECRETS_DIR, 'quantconnect_access.json'), 'r') as f:
    config = json.load(f)
TOKEN = config['token']
USER_ID = config['user_id']

# Create authentication headers
now = int(time.time())
hash_val = hashlib.sha256(f"{TOKEN}:{now}".encode()).hexdigest()
b64 = base64.b64encode(f"{USER_ID}:{hash_val}".encode()).decode()
headers = {
    'Authorization': f'Basic {b64}',
    'Timestamp': str(now),
    'Content-Type': 'application/json',
}

# Terminate existing live deployments
live_res = requests.get(f'{BASE_URL}/live/read',
    headers=headers,
    params={'projectId': PROJECT_ID}
)

if live_res.status_code == 200:
    live_data = live_res.json()
    if 'liveDeployments' in live_data and live_data['liveDeployments']:
        print(f"Terminating {len(live_data['liveDeployments'])} existing live deployments")
        for live in live_data['liveDeployments']:
            requests.delete(
                f'{BASE_URL}/live/terminate',
                headers=headers,
                json={'projectId': PROJECT_ID, 'liveDeploymentId': live['id']}
            )

# Upload strategy file
with open(os.path.join(ALGORITHM_DIR, 'aggressive_500_grow.py'), 'r') as f:
    code = f.read()

update_res = requests.post(
    f'{BASE_URL}/files/update',
    headers=headers,
    json={
        'projectId': PROJECT_ID,
        'name': 'main.py',
        'content': code
    }
)

if update_res.status_code != 200 or not update_res.json().get('success'):
    print(f"Error uploading strategy: {update_res.text}")
    exit(1)

# Compile the algorithm
compile_res = requests.post(
    f'{BASE_URL}/compile/create',
    headers=headers,
    json={'projectId': PROJECT_ID}
)

if compile_res.status_code != 200:
    print(f"Compile failed: {compile_res.text}")
    exit(1)

compile_id = compile_res.json().get('compileId')
if not compile_id:
    print('No compile ID returned from compilation')
    exit(1)

# Wait for compilation
for i in range(10):
    status_res = requests.get(
        f'{BASE_URL}/compile/read',
        headers=headers,
        params={'projectId': PROJECT_ID, 'compileId': compile_id}
    )
    if status_res.status_code == 200:
        status = status_res.json().get('state')
        if status == 'BuildSuccess':
            break
        elif status in ['Failed', 'In Error']:
            print('Compile failed')
            exit(1)
    time.sleep(5)
else:
    print('Timed out waiting for compilation')
    exit(1)

# Get cluster node
node_res = requests.get(f'{BASE_URL}/clusters', headers=headers)
node_id = 'B2-8'
if node_res.status_code == 200:
    try:
        node_id = node_res.json()['clusters'][0]['id']
    except:
        pass

# Deploy live
live_res = requests.post(
    f'{BASE_URL}/live/create',
    headers=headers,
    json={
        'projectId': PROJECT_ID,
        'compileId': compile_id,
        'name': 'AGGRESSIVE_500_DAILY',
        'nodeId': node_id,
        'parameters': {'initial_capital': 500}
    }
)

if live_res.status_code == 200 and live_res.json().get('success', False):
    live_data = live_res.json()
    live_id = live_data['liveDeployment']['id']
    print('DEPLOYED LIVE SYSTEM')
    print(f'Live ID: {live_id}')
    print(f'Project URL: https://www.quantconnect.com/project/{PROJECT_ID}/live/{live_id}')
else:
    print('Deployment failed')
    print(f'Response: {live_res.text}')
