import os
ruta = 'C:/AI_VAULT/00_identity/brain_server.py'
with open(ruta, 'r', encoding='utf-8') as f: content = f.read()
# Inyectamos el endpoint /healthz en la raiz si no existe
health_code = '\n@app.get("/healthz")\ndef health_root(): return {"ok": True, "status": "healthy"}\n'
if 'def health_root():' not in content:
    # Insertar antes del bloque __main__
    new_content = content.replace('if __name__ == "__main__":', health_code + '\nif __name__ == "__main__":')
    with open(ruta, 'w', encoding='utf-8') as f: f.write(new_content)
print('Endpoint /healthz inyectado.')