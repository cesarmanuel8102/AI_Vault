import os

ruta = 'C:/AI_VAULT/00_identity/brain_server.py'
if os.path.exists(ruta):
    with open(ruta, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    
    # 1. Identificar la linea de future y las demas
    future_line = "from __future__ import annotations\n"
    # Quitamos cualquier version de esa linea que ya este en el archivo
    clean_lines = [l for l in lines if "from __future__" not in l]
    
    # 2. Re-ensamblar: Future primero, luego el resto
    new_content = future_line + "".join(clean_lines)
    
    with open(ruta, 'w', encoding='utf-8') as f:
        f.write(new_content)
    print("--- [FIXED] Orden de cabeceras corregido. ---")
