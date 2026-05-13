# verify_fix.py - Verificar que la corrección funcionó
import ast
import sys

def verify_syntax(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Verificar sintaxis
        ast.parse(content)
        print(f"✅ {file_path} - Sintaxis válida")
        return True
    except SyntaxError as e:
        print(f"❌ {file_path} - Error de sintaxis: {e}")
        return False
    except Exception as e:
        print(f"⚠️ {file_path} - Error: {e}")
        return False

# Verificar archivos clave
files_to_check = [
    r"C:\AI_VAULT\00_identity\brain_server.py",
    r"C:\AI_VAULT\brain_server_emergency.py",
    r"C:\AI_VAULT\financial_autonomy\api\financial_endpoints.py"
]

all_valid = True
for file_path in files_to_check:
    if verify_syntax(file_path):
        # Verificar que no tenga el import problemático
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
            if "30_financial_autonomy" in content:
                print(f"❌ {file_path} - Todavía contiene '30_financial_autonomy'")
                all_valid = False
            else:
                print(f"✅ {file_path} - Libre de imports problemáticos")
    else:
        all_valid = False

if all_valid:
    print("🎯 ¡Todas las correcciones aplicadas correctamente!")
else:
    print("⚠️ Algunos archivos todavía necesitan corrección")

sys.exit(0 if all_valid else 1)
