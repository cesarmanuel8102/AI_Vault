"""Generate curl command and also try with httpx."""
import json
import hashlib
import time
from base64 import b64encode

USER_ID = "384945"
API_TOKEN = "4104f8d1f1560106f534113a77dee303f39e42851443b4d3467424d305aeefa3"
PROJECT_ID = 29490680
COMPILE_ID = "91e9aa704f8c13a10e39acd5d5f62604-e27715652009231a5f8a4635045934c0"

timestamp = str(int(time.time()))
time_stamped_token = f"{API_TOKEN}:{timestamp}".encode("utf-8")
hashed_token = hashlib.sha256(time_stamped_token).hexdigest()
authentication = f"{USER_ID}:{hashed_token}"
auth_b64 = b64encode(authentication.encode("utf-8")).decode("ascii")

payload = {
    "versionId": "-1",
    "projectId": PROJECT_ID,
    "compileId": COMPILE_ID,
    "nodeId": "LN-64d4787830461ee45574254f643f69b3",
    "brokerage": {
        "id": "InteractiveBrokersBrokerage",
        "ib-user-name": "cesarmanuel81",
        "ib-account": "DUM891854",
        "ib-password": "Casiopea8102*",
        "ib-weekly-restart-utc-time": "22:00:00"
    },
    "dataProviders": {
        "InteractiveBrokersBrokerage": {
            "id": "InteractiveBrokersBrokerage"
        }
    }
}

body_json = json.dumps(payload)

# Write curl command to a .ps1 file
curl_cmd = f'''$body = @'
{body_json}
'@

$headers = @{{
    "Authorization" = "Basic {auth_b64}"
    "Timestamp" = "{timestamp}"
    "Content-Type" = "application/json"
}}

$response = Invoke-WebRequest -Uri "https://www.quantconnect.com/api/v2/live/create" -Method Post -Body $body -Headers $headers -ContentType "application/json"
Write-Host $response.Content
'''

with open("C:/AI_VAULT/tmp_agent/deploy_curl.ps1", "w") as f:
    f.write(curl_cmd)

print("PowerShell script written to deploy_curl.ps1")
print(f"Timestamp: {timestamp}")
print(f"Auth: Basic {auth_b64[:20]}...")
print(f"Body length: {len(body_json)}")
print(f"Body preview: {body_json[:200]}")
