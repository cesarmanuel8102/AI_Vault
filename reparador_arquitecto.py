import os
def limpiar(ruta):
    if not os.path.exists(ruta): return
    with open(ruta, 'r', encoding='utf-8', errors='ignore') as f: lines = f.readlines()
    while lines and not lines[-1].strip(): lines.pop()
    with open(ruta, 'w', encoding='utf-8') as f: f.writelines(lines)
    print(f'Limpiado: {ruta}')

def cerrar_ui(ruta):
    with open(ruta, 'a', encoding='utf-8') as f:
        f.write('\n    return {"ok": True}\n\nif __name__ == "__main__":\n    import uvicorn\n    uvicorn.run(app, host="127.0.0.1", port=8040)\n')
    print('UI Server cerrado y configurado para puerto 8040.')

limpiar('C:/AI_VAULT/00_identity/brain_server.py')
limpiar('C:/AI_VAULT/00_identity/brain_chat_ui_server.py')
cerrar_ui('C:/AI_VAULT/00_identity/brain_chat_ui_server.py')