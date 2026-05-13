import os
import re

origin = 'C:/AI_VAULT/00_identity/brain_server_limpio.py'
target = 'C:/AI_VAULT/00_identity/brain_server.py'

if os.path.exists(origin):
    with open(origin, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Asegurar CORS (para que la consola 8040 pueda hablar con el 8010)
    if 'CORSMiddleware' not in content:
        content = "from fastapi.middleware.cors import CORSMiddleware\n" + content
        cors_code = "\napp.add_middleware(CORSMiddleware, allow_origins=['*'], allow_credentials=True, allow_methods=['*'], allow_headers=['*'])\n"
        content = re.sub(r'(app = FastAPI\(.*?\))', r'\1' + cors_code, content)

    # Asegurar endpoint de salud (para que el boton se ponga verde)
    if 'def healthz' not in content:
        content += "\n@app.get('/healthz')\ndef healthz(): return {'ok': True, 'status': 'healthy'}\n"

    # Asegurar motor de arranque
    if '__main__' not in content:
        content += "\nif __name__ == '__main__':\n    import uvicorn\n    uvicorn.run(app, host='127.0.0.1', port=8010)\n"

    with open(target, 'w', encoding='utf-8') as f:
        f.write(content)
    print("--- [SUCCESS] Brain Server preparado con toda la logica limpia ---")
else:
    print("--- [ERROR] No se encontro brain_server_limpio.py ---")
