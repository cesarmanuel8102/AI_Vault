import sys
try:
    import fastapi
    import uvicorn
    from fastapi import FastAPI
    app = FastAPI()
    print('Librerias OK')
except Exception as e:
    with open('C:/AI_VAULT/ERROR_FORENSE.txt', 'w') as f: f.write(f'ERROR DE LIBRERIA: {str(e)}')
    sys.exit(1)
