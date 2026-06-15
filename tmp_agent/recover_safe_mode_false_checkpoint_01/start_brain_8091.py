import subprocess, os, time, urllib.request, json, socket

env = os.environ.copy()
env['BRAIN_SAFE_MODE'] = 'false'
env['BRAIN_PORT'] = '8091'
env['BRAIN_START_AUTONOMY'] = 'false'
env['BRAIN_START_PROACTIVE'] = 'false'
env['BRAIN_START_SELF_DIAGNOSTIC'] = 'false'
env['BRAIN_START_QC_LIVE_MONITOR'] = 'false'
env['BRAIN_ENABLE_UNSAFE_DEV_ENDPOINTS'] = 'false'

# Start server in background
p = subprocess.Popen(
    ['python', '-u', 'tmp_agent/brain_v9/start_safe_server.py'],
    env=env, cwd='C:\\AI_VAULT_CANONICAL',
    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
)
print(f'Started Brain PID {p.pid} on port 8091')
time.sleep(6)

# Wait for port to be listening
for i in range(10):
    s = socket.socket()
    try:
        s.connect(('127.0.0.1', 8091))
        s.close()
        print('Port 8091 is UP')
        break
    except:
        s.close()
        time.sleep(1)
else:
    print('Port 8091 did not come up')

# Verify health
try:
    resp = urllib.request.urlopen('http://127.0.0.1:8091/health', timeout=5)
    data = json.loads(resp.read().decode())
    print(f'Health: safe_mode={data.get("safe_mode")} status={data.get("status")}')
except Exception as e:
    print(f'Health check failed: {e}')
