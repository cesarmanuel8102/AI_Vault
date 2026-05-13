# Tutorial Brain Agent V8
## Guía Paso a Paso

### 1. Iniciar el Agente

```python
from brain_agent_v8_final import BrainAgentV8Final

agent = BrainAgentV8Final("mi_sesion")
result = await agent.process_message("Hola")
print(result['message'])
```

### 2. Analizar Código

```python
# Analizar archivo Python
result = await agent.process_message("analiza agent_core.py")

# Buscar patrones
result = await agent.process_message("busca class Agent")
```

### 3. Usar el Sistema de Plugins

```python
from plugin_system import PluginManager

manager = PluginManager()
plugins = manager.list_plugins()
manager.load_plugin("mi_plugin")
```

### 4. Exportar Métricas

```python
from metrics_exporter import MetricsExporter

exporter = MetricsExporter()
exporter.export_conversations(conversations)
```

### 5. WebSocket Realtime

```javascript
const ws = new WebSocket('ws://localhost:8091');
ws.send(JSON.stringify({type: 'chat', message: 'Hola'}));
```

### Comandos Disponibles

- `analiza archivo.py` - Análisis AST
- `busca patron` - Búsqueda
- `debug error` - Debugging
- `genera funcion` - Generación
- `rsi` - Estado sistema
- `ejecuta comando` - Shell

### Tips

- Usar mensajes claros y específicos
- El agente mantiene contexto entre mensajes
- Reporta errores para mejorar
