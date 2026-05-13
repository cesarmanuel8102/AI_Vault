import os
import glob

def check_file(path):
    if os.path.exists(path):
        size = os.path.getsize(path)
        print(f'--- [OK] Detectado: {path} ({size} bytes) ---')
        try:
            with open(path, "r", encoding="utf-8") as f:
                lines = f.readlines()
                print(f'Ultimas 10 lineas de {path}:')
                for l in lines[-10:]:
                    print(l.strip())
        except Exception as e:
            print(f'[ERROR] No se pudo leer {path}: {e}')
    else:
        print(f'--- [MISSING] No se encuentra: {path} ---')

print('Iniciando Diagnostico de Emergencia...')
check_file('C:/AI_VAULT/00_identity/brain_server.py')
check_file('C:/AI_VAULT/00_identity/brain_chat_ui_server.py')
