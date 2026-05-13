# fix_brain_imports.py - Corregir imports con nombres inválidos
import re

def fix_brain_server_imports():
    # Leer brain_server.py
    with open(r"C:\AI_VAULT\00_identity\brain_server.py", "r", encoding="utf-8") as f:
        content = f.read()
    
    # Reemplazar el import problemático
    old_import = "from 30_financial_autonomy.api.financial_endpoints import router as financial_autonomy_router"
    new_import = "from financial_autonomy.api.financial_endpoints import router as financial_autonomy_router"
    
    if old_import in content:
        content = content.replace(old_import, new_import)
        print("✅ Import corregido en brain_server.py")
    else:
        print("⚠️ Import problemático no encontrado (puede que ya esté corregido)")
    
    # También corregir la línea del router
    content = re.sub(
        r'30_financial_autonomy', 
        'financial_autonomy', 
        content
    )
    
    # Escribir archivo corregido
    with open(r"C:\AI_VAULT\00_identity\brain_server.py", "w", encoding="utf-8") as f:
        f.write(content)
    
    print("✅ brain_server.py corregido")

def fix_emergency_server():
    # También corregir el servidor de emergencia
    with open(r"C:\AI_VAULT\brain_server_emergency.py", "r", encoding="utf-8") as f:
        content = f.read()
    
    content = content.replace(
        "from 30_financial_autonomy.api.financial_endpoints import router as financial_autonomy_router",
        "from financial_autonomy.api.financial_endpoints import router as financial_autonomy_router"
    )
    
    with open(r"C:\AI_VAULT\brain_server_emergency.py", "w", encoding="utf-8") as f:
        f.write(content)
    
    print("✅ brain_server_emergency.py corregido")

if __name__ == "__main__":
    fix_brain_server_imports()
    fix_emergency_server()
    print("🎯 Todos los imports corregidos")
