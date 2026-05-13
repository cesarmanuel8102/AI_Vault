import json
import urllib.request

url = "http://127.0.0.1:11434/v1/chat/completions"
payload = {
    "model": "qwen2.5:14b",
    "messages": [
        {"role": "system", "content": "Responde breve y en español."},
        {"role": "user", "content": "Di hola y confirma que el endpoint v1 funciona."}
    ],
    "temperature": 0.2
}

req = urllib.request.Request(
    url,
    data=json.dumps(payload).encode("utf-8"),
    headers={
        "Content-Type": "application/json",
        "Authorization": "Bearer ollama"
    },
    method="POST"
)

with urllib.request.urlopen(req, timeout=60) as resp:
    data = json.loads(resp.read().decode("utf-8"))
    print(json.dumps(data, indent=2, ensure_ascii=False))
