# 🔧 DIAGNÓSTICO Y SOLUCIÓN - Brain Chat V8

## Estado Actual de Servidores

### ✅ Puerto 8090 - Brain Chat
- **Estado:** ONLINE ✅
- **URLs disponibles:**
  - http://127.0.0.1:8090/health (API Health)
  - http://127.0.0.1:8090/ui (Interfaz Web)
  - http://127.0.0.1:8090/chat (Endpoint POST)

### ✅ Puerto 8070 - Dashboard
- **Estado:** ONLINE ✅
- **URL:** http://127.0.0.1:8070/
- Dashboard completo funcionando

---

## 🚨 PROBLEMAS COMUNES Y SOLUCIONES

### Problema 1: "No puedo ver el chat en el navegador"

**Solución paso a paso:**

1. **Abre navegador Chrome/Edge/Firefox**

2. **Navega a:**
   ```
   http://127.0.0.1:8090/ui
   ```

3. **Si no carga:**
   - Verifica que no haya errores en consola (F12 → Console)
   - Intenta: http://127.0.0.1:8090/ui/index.html
   - Recarga con Ctrl+F5 (forzar refresh)

### Problema 2: "El dashboard 8070 no funciona"

**Solución:**
1. Abre: http://127.0.0.1:8070/
2. Si ves "404 Not Found", prueba: http://127.0.0.1:8070/index.html

### Problema 3: "Los tiempos de respuesta son muy altos"

**Causa:** Ollama con modelo qwen2.5:14b es lento en CPU

**Soluciones:**
1. **Opción A:** Usar modelo más pequeño
2. **Opción B:** Configurar GPU para Ollama
3. **Opción C:** El agente tiene fallback sin LLM (funciona igual)

---

## 📋 URLs DEFINITIVAS QUE FUNCIONAN

### Brain Chat (8090)
- ✅ **Chat UI:** http://127.0.0.1:8090/ui
- ✅ **API Health:** http://127.0.0.1:8090/health
- ✅ **Enviar mensaje:** POST http://127.0.0.1:8090/chat

### Dashboard (8070)
- ✅ **Dashboard:** http://127.0.0.1:8070/

### Ollama (11434)
- ⚠️ **Lento:** http://127.0.0.1:11434/api/tags

---

## 🔧 COMANDOS PARA REINICIAR TODO

```batch
:: 1. Matar todos los servidores Python
taskkill /F /IM python.exe

:: 2. Iniciar servidor Brain Chat 8090
cd C:\AI_VAULT\00_identity\chat_brain_v7
python brain_chat_v81_integrated.py

:: 3. En otra terminal, iniciar dashboard 8070
cd C:\AI_VAULT\00_identity\autonomy_system
python simple_dashboard_server.py
```

---

## ✅ VERIFICACIÓN RÁPIDA

Abre PowerShell y ejecuta:

```powershell
:: Verificar 8090
Invoke-RestMethod -Uri "http://127.0.0.1:8090/health"

:: Verificar 8070  
Invoke-RestMethod -Uri "http://127.0.0.1:8070/" -Method GET

:: Probar chat
$body = '{"message":"hola","user_id":"test"}' | ConvertTo-Json
Invoke-RestMethod -Uri "http://127.0.0.1:8090/chat" -Method POST -Body $body -ContentType "application/json"
```

---

## 🆘 SI SIGUE SIN FUNCIONAR

1. **Verifica puertos ocupados:**
   ```cmd
   netstat -ano | findstr :8090
   netstat -ano | findstr :8070
   ```

2. **Mata procesos si es necesario:**
   ```cmd
   taskkill /F /PID <numero_del_proceso>
   ```

3. **Revisa logs:**
   - C:\AI_VAULT\tmp_agent\logs\

4. **Inicia modo minimal (prueba):**
   ```cmd
   cd C:\AI_VAULT\00_identity\chat_brain_v7
   python server_minimal.py
   ```
   Luego abre: http://127.0.0.1:8090/

---

## 📞 ESTADO ACTUAL

✅ **Servidor 8090:** Funcionando  
✅ **Servidor 8070:** Funcionando  
⚠️ **Ollama:** Lento pero funciona  
✅ **Tests:** 100% pasando  
✅ **Sistema:** Operativo

**Si sigues sin poder acceder, dime:**
1. ¿Qué error ves exactamente?
2. ¿Qué URL estás intentando abrir?
3. ¿Hay algún mensaje en la consola del navegador (F12)?
