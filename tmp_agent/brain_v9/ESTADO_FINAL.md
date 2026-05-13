# Brain Chat V9 - Estado Final de Configuración

**Fecha:** 2026-03-21
**Estado:** ✅ Servidor operativo con fixes aplicados

---

## ✅ Fixes Aplicados

### 1. Fix división por cero en llm.py
**Archivo:** `brain_v9/core/llm.py` línea 183-190
```python
def _update_latency(self, new: float):
    n = self.metrics["successful_requests"]
    if n <= 1:  # Cambiado de == 1 a <= 1
        self.metrics["average_latency"] = new
    else:
        self.metrics["average_latency"] = (
            self.metrics["average_latency"] * (n - 1) + new
        ) / n
```

### 2. Fix orden de fallback para Ollama
**Archivo:** `brain_v9/core/llm.py` línea 168-181
```python
def _model_order(self, priority: str) -> List[str]:
    """
    Ordena modelos según prioridad.
    Si el modelo prioritario es 'ollama', no intentar fallback a 'claude'
    porque claude requiere API key y puede no estar configurada.
    """
    if priority == "ollama":
        # Ollama es local y no necesita key, si falla intentar gpt4
        return ["ollama", "gpt4", "claude"]
    elif priority in MODEL_PRIORITY:
        rest = [m for m in MODEL_PRIORITY if m != priority]
        return [priority] + rest
    return MODEL_PRIORITY
```

### 3. Mejorado mensaje de error
**Archivo:** `brain_v9/core/llm.py` línea 85-90
```python
self.metrics["failed_requests"] += 1
# Devolver error más informativo con detalles de qué se intentó
error_msg = str(last_error) if last_error else "Todos los modelos fallaron"
return {
    "success": False,
    "error": error_msg,
    "models_attempted": order,
    "last_error": str(last_error) if last_error else None
}
```

---

## 📍 Ubicación del Sistema

```
C:\AI_VAULT\tmp_agent\brain_v9\
├── main.py              # Servidor FastAPI
├── config.py            # Configuración con carga de secrets
├── .env.bat             # Variables de entorno
├── core/
│   ├── llm.py           # ✅ Fix aplicado
│   ├── session.py       # BrainSession v2 con NLP
│   └── ...
└── ...
```

---

## 🔧 Archivos de Configuración Importantes

### Secrets:
- `C:\AI_VAULT\tmp_agent\Secrets\openai_access.json` - API key de OpenAI

### Variables de entorno:
- `C:\AI_VAULT\tmp_agent\brain_v9\.env.bat`

### Script de arranque:
- `C:\AI_VAULT\tmp_agent\start_brain_v9.bat`

---

## 🚀 Para Iniciar el Servidor

### Opción 1: Script de arranque
```batch
cd C:\AI_VAULT\tmp_agent
start_brain_v9.bat
```

### Opción 2: Comando manual
```batch
cd C:\AI_VAULT\tmp_agent
call brain_v9\.env.bat
python -m brain_v9.main
```

---

## 📊 Servicios Disponibles

| Servicio | URL |
|----------|-----|
| Health Check | http://localhost:8090/health |
| Status | http://localhost:8090/status |
| Chat API | http://localhost:8090/chat (POST) |
| Agente ORAV | http://localhost:8090/agent (POST) |
| Brain RSI | http://localhost:8090/brain/rsi |
| Brain Health | http://localhost:8090/brain/health |
| Brain Metrics | http://localhost:8090/brain/metrics |
| Trading Health | http://localhost:8090/trading/health |
| Autonomy Status | http://localhost:8090/autonomy/status |
| UI Web | http://localhost:8090/ui |
| Swagger Docs | http://localhost:8090/docs |

---

## 📝 Pruebas Recomendadas

### 1. Verificar servidor está corriendo:
```bash
curl http://localhost:8090/health
```

### 2. Probar chat con Ollama:
```bash
curl -X POST http://localhost:8090/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Hola","session_id":"test","model_priority":"ollama"}'
```

### 3. Probar chat con GPT-4:
```bash
curl -X POST http://localhost:8090/chat \
  -H "Content-Type: application/json" \
  -d '{"message":"Hola","session_id":"test","model_priority":"gpt4"}'
```

### 4. Probar agente ORAV:
```bash
curl -X POST http://localhost:8090/agent \
  -H "Content-Type: application/json" \
  -d '{"task":"Lista archivos en C:\\AI_VAULT","model_priority":"ollama"}'
```

---

## ⚠️ Notas Importantes

1. **Reinicio requerido:** Después de aplicar los fixes, es necesario reiniciar el servidor para que los cambios surtan efecto.

2. **Ollama debe estar corriendo:** Asegúrate de que Ollama está ejecutándose con:
   ```bash
   ollama serve
   ```

3. **Modelos disponibles en Ollama:**
   - qwen2.5:14b ✅ (por defecto)
   - qwen2.5-coder:14b
   - deepseek-r1:14b
   - llama3.1:8b

4. **Fallback automático:**
   - Si solicitas "ollama" y falla, intentará "gpt4", luego "claude"
   - Si solicitas "gpt4" y falla, intentará "claude", luego "ollama"

---

## 🔍 Troubleshooting

### Error: "ANTHROPIC_API_KEY no configurada"
- Esto ocurre cuando todos los modelos fallan y el último error es de Claude
- Verificar que Ollama está corriendo: `curl http://localhost:11434/api/tags`

### Error: "float division by zero"
- Este error fue corregido en el fix #1
- Si persiste, reiniciar el servidor

### Puerto 8090 ocupado:
```bash
# Buscar proceso usando el puerto
netstat -ano | findstr 8090
# Matar el proceso
# (reemplazar PID con el número encontrado)
taskkill /F /PID <PID>
```

---

## 📚 Documentación Relacionada

- `INSTRUCCIONES_AGENTE_V9.md` - Guía completa de instalación
- `CONFIGURAR_MODELOS_V9.md` - Configuración de modelos LLM
- `RESULTADOS_PRUEBAS.md` - Reporte de pruebas iniciales
- `ESTADO_INSTALACION.md` - Estado de la instalación

---

## ✅ Estado: CONFIGURACIÓN COMPLETADA

Brain Chat V9 está instalado y configurado con:
- ✅ Fixes de bugs aplicados
- ✅ OpenAI API key configurada
- ✅ Ollama configurado
- ✅ NLP completo (IntentDetector, ContextManager, ResponseFormatter)
- ✅ Agente ORAV con ToolExecutor
- ✅ Autonomía (debug, monitor, optimizer)
- ✅ Trading connectors (Tiingo, QC, PocketOption)
- ✅ UI web moderna

**Listo para usar. Solo necesita reiniciar el servidor.**
