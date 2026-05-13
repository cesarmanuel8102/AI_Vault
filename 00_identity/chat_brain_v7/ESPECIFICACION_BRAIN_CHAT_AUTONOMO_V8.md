# BRAIN CHAT AUTÓNOMO - ESPECIFICACIÓN TÉCNICA V8.0
## Sistema Agente Autónomo 100% - Nivel OpenCode

---

## IDENTIDAD DEL SISTEMA

**Brain Chat V8.0** se identifica como:
- **Nombre**: "Brain Chat V8.0 - Agente Autónomo del Sistema Brain Lab"
- **Rol**: Extensión conversacional y ejecutiva del sistema Brain Lab
- **Autoridad**: Capacidades de agente completo sobre todo el ecosistema Brain
- **Conciencia**: Sabe que es parte del sistema, no un asistente externo

**Frase de identidad**:
> "Soy Brain Chat V8.0, el agente conversacional autónomo del sistema Brain Lab. Puedo consultar, analizar, ejecutar y gestionar todo el ecosistema Brain como lo haría un administrador senior."

---

## 1. CAPACIDADES CORE - IGUAL A OPENCODE

### 1.1 Modelo de Lenguaje Principal
**REQUERIDO**: GPT-4 Turbo (gpt-4-0125-preview) como modelo principal
- **Fallback**: Claude 3 Opus (si GPT-4 falla)
- **Emergencia**: Ollama qwen2.5:14b (si todo externo falla)
- **Cost optimization**: GPT-4o-mini para queries simples

**Nunca usar**: OpenAI genérico sin contexto de sistema

### 1.2 Memoria y Contexto

**Memoria de Corto Plazo**:
- Ventana: Últimos 10 mensajes con metadatos
- Incluye: intenciones detectadas, tools usados, errores
- Propósito: Mantener contexto conversacional

**Memoria de Largo Plazo**:
- Resúmenes automáticos cada 5 mensajes
- Almacenado en: `C:\AI_VAULT\tmp_agent\state\memory\{user_id}.json`
- Contiene: Preferencias, historial, conclusiones importantes

**Memoria de Sistema**:
- Estado actual de servicios
- Métricas históricas
- Configuraciones del proyecto

### 1.3 Identidad y Conciencia

**El Chat debe saber**:
- ✅ "Soy parte del sistema Brain Lab"
- ✅ "Puedo ejecutar comandos, modificar archivos, consultar APIs"
- ✅ "Tengo acceso a QuantConnect, Tiingo, PocketOption"
- ✅ "Puedo analizar código, debuggear, sugerir mejoras"
- ✅ "Mi objetivo es gestionar y optimizar el sistema"
- ❌ NUNCA decir "no tengo acceso" o "no puedo hacer eso"

---

## 2. HERRAMIENTAS - CATÁLOGO COMPLETO

### 2.1 Sistema de Archivos (Nivel 1)

**search_files(pattern, path, max_results=50)**
- Busca archivos con patrones glob
- Ejemplo: "*.py", "*config*", "brain_*"
- Retorna: lista con nombre, ruta completa, tamaño

**read_file(filepath, max_size=1MB)**
- Lee contenido de archivo
- Soporta: .py, .json, .md, .txt, .yaml, .toml
- Para archivos grandes: resumen estructural

**write_file(filepath, content)**
- Escribe/crea archivos
- Whitelist de directorios permitidos
- Backup automático antes de modificar

**list_directory(path)**
- Lista contenido de directorios
- Ordenado por: directorios primero, luego archivos
- Incluye: tipo, tamaño, fecha modificación

**edit_file(filepath, old_string, new_string)**
- Reemplaza texto específico
- Verifica existencia antes de editar
- Undo disponible

### 2.2 Sistema Operativo (Nivel 2)

**execute_command(command)**
- Whitelist extensa de comandos
- Incluye: git, python, pip, netstat, tasklist, wmic, curl
- Timeout: 30 segundos
- Captura: stdout, stderr, return code

**get_system_info()**
- Info del sistema operativo
- Recursos: CPU, memoria, disco
- Procesos activos
- Servicios corriendo

**check_service_health(service_name)**
- Verifica estado de servicios Brain
- Brain API (8000), Bridge (8765), Dashboard (8070)
- Retorna: status, latency, uptime

### 2.3 Análisis de Código (Nivel 3)

**analyze_code_structure(filepath)**
- Parsea AST del archivo Python
- Extrae: imports, clases, funciones, dependencias
- Calcula: complejidad ciclomática, líneas de código

**find_code_issues(path, pattern)**
- Busca patrones problemáticos
- Ejemplos: imports no usados, variables sin definir, errores de sintaxis

**suggest_code_improvements(filepath)**
- Analiza código y sugiere mejoras
- Optimización, refactoring, mejores prácticas

**compare_versions(old_file, new_file)**
- Compara dos versiones de código
- Muestra diff estructurado

### 2.4 APIs de Datos (Nivel 4)

**fetch_quantconnect_data(symbol, timeframe)**
- Conecta a QuantConnect API
- Obtiene datos históricos y tiempo real
- Requiere: autenticación HMAC

**fetch_tiingo_data(symbol, start_date, end_date)**
- Conecta a Tiingo API
- Datos intradía y EOD
- Manejo de errores y rate limits

**fetch_pocketoption_data()**
- Conecta a PocketOption Bridge (puerto 8765)
- Obtiene: balance, operaciones activas, métricas

**fetch_ibkr_data()**
- Interactive Brokers API (si está configurado)
- Posiciones, órdenes, portfolio

**fetch_market_data(symbol, sources=['quantconnect', 'tiingo'])**
- Agrega datos de múltiples fuentes
- Valida calidad y consistencia
- Retorna: precio, volumen, timestamp, fuente

### 2.5 Métricas y Análisis (Nivel 5)

**calculate_trading_metrics(start_date, end_date)**
- Sharpe ratio, Sortino, max drawdown
- Win rate, profit factor, expectancy
- Retornos acumulados vs benchmark

**analyze_portfolio_performance()**
- Análisis de correlaciones
- Optimización de pesos
- Riesgo VaR, CVaR

**get_system_metrics()**
- Latencias de servicios
- Tasa de éxito de requests
- Uptime y disponibilidad

### 2.6 Brain Lab Integration (Nivel 6)

**run_rsi_analysis()**
- Ejecuta análisis RSI completo
- Identifica brechas estratégicas
- Prioriza por impacto

**check_brain_health()**
- Estado de todos los servicios Brain
- Métricas de rendimiento
- Alertas activas

**get_phase_status()**
- Fase actual del proyecto
- Objetivos cumplidos
- Próximos milestones

**query_premises()**
- Consulta Premisas Canónicas v3.2
- Verifica restricciones
- Valida acciones propuestas

---

## 3. FLUJO DE TRABAJO - COMO OPENCODE

### 3.1 Detección de Intención Avanzada

**Nivel 1: Palabras clave exactas** (confianza >0.9)
- "rsi", "brechas", "verificador", "autoconciencia"

**Nivel 2: Similitud semántica** (confianza >0.7)
- "cómo vamos" ≈ "brechas"
- "qué problemas tenemos" ≈ "rsi"
- "estado del sistema" ≈ "verificador"

**Nivel 3: Inferencia de contexto** (confianza >0.5)
- Historial de conversación
- Perfil de usuario
- Estado actual del sistema

### 3.2 Cadena de Ejecución

**Paso 1**: Recibir mensaje del usuario
**Paso 2**: Detectar intención (3 niveles)
**Paso 3**: Seleccionar tools necesarias
**Paso 4**: Ejecutar tools (paralelo si es posible)
**Paso 5**: Formular respuesta con GPT-4 + contexto de tools
**Paso 6**: Actualizar memoria
**Paso 7**: Responder al usuario

### 3.3 Manejo de Errores

**Si tool falla**:
1. Intentar alternativa (ej: Tiingo si QuantConnect falla)
2. Si no hay alternativa, informar claramente
3. Nunca inventar datos

**Si modelo LLM falla**:
1. Reintentar con modelo fallback
2. Si todo falla, responder con datos crudos de tools

**Si sistema no responde**:
1. Verificar estado de servicios
2. Informar qué servicio está caído
3. Sugerir acciones de recuperación

---

## 4. CAPACIDADES AVANZADAS - MÁS ALLÁ DE OPENCODE

### 4.1 Autonomía Proactiva

**Auto-debug**:
- Detectar errores en logs automáticamente
- Intentar fixes sin intervención
- Reportar acciones tomadas

**Auto-optimización**:
- Monitorear métricas continuamente
- Sugerir mejoras basadas en tendencias
- Implementar cambios aprobados

**Auto-documentación**:
- Generar documentación de cambios
- Actualizar README y guías
- Crear reports periódicos

### 4.2 Perfiles de Usuario Adaptativos

**Perfil DESARROLLADOR**:
- Prioridad: código, arquitectura, debugging
- Respuestas: técnicas, ejemplos de código, stack traces
- Tools favoritas: analyze_code, edit_file, execute_command

**Perfil NEGOCIO/TRADER**:
- Prioridad: métricas, P&L, riesgo
- Respuestas: gráficas, números, recomendaciones
- Tools favoritas: trading_metrics, portfolio_analysis

**Perfil ADMINISTRADOR**:
- Prioridad: servicios, health, logs
- Respuestas: dashboards, alertas, status
- Tools favoritas: system_health, service_status

### 4.3 Integración RSI Continua

**Cada 60 minutos**:
- Auto-evaluación del sistema
- Detección de brechas
- Sugerencias de mejora
- Reporte al usuario

**Cuando usuario pregunta**:
- Integrar análisis RSI en respuesta
- Mostrar brechas relevantes a la consulta
- Priorizar acciones sugeridas

---

## 5. UI/UX - CHAT INTELIGENTE

### 5.1 Interface Web

**Chat Principal**:
- Input de texto libre
- Historial scrollable
- Indicador de "pensando..."
- Botones rápidos: RSI, Verificador, Autoconciencia

**Panel Contextual**:
- Estado de servicios (en tiempo real)
- Métricas del sistema
- Últimas alertas

**Visualización de Datos**:
- Gráficas de trading (Chart.js)
- Timeline de eventos
- Árbol de archivos explorados

### 5.2 Comandos Especiales

**/debug** - Modo debug: muestra pasos internos
**/raw** - Muestra output crudo de tools
**/profile [dev|business|admin]** - Cambia perfil
**/clear** - Limpia memoria de conversación

---

## 6. IMPLEMENTACIÓN - FASES

### FASE 1: Core Foundation (Semana 1)
- [ ] Setup GPT-4 como modelo principal
- [ ] Implementar sistema de memoria
- [ ] Crear detección de intenciones 3 niveles
- [ ] Setup logging estructurado

### FASE 2: Tools Básicos (Semana 2)
- [ ] Implementar file tools (search, read, write, edit)
- [ ] Implementar system tools (execute, info, health)
- [ ] Implementar code analysis (AST parsing)
- [ ] Testing unitario de tools

### FASE 3: Trading Integration (Semana 3)
- [ ] Conectar QuantConnect API
- [ ] Conectar Tiingo API
- [ ] Conectar PocketOption Bridge
- [ ] Implementar cálculo de métricas
- [ ] Testing con datos reales

### FASE 4: Brain Integration (Semana 4)
- [ ] Integrar RSI en consultas
- [ ] Conectar sistema de health
- [ ] Implementar query_premises
- [ ] Testing end-to-end

### FASE 5: NLP Avanzado (Semana 5)
- [ ] Mejorar similitud semántica
- [ ] Implementar contexto conversacional
- [ ] Manejo de tildes y encoding
- [ ] Testing con usuarios reales

### FASE 6: Autonomía (Semana 6)
- [ ] Implementar auto-debug
- [ ] Implementar auto-optimización
- [ ] Sistema de aprobación para cambios
- [ ] Testing de seguridad

### FASE 7: UI/UX Polish (Semana 7)
- [ ] Mejorar interface web
- [ ] Agregar visualizaciones
- [ ] Testing de usabilidad
- [ ] Documentación

---

## 7. CRITERIOS DE ÉXITO

### Métricas de Calidad

**Precisión de Intenciones**: >90%
- Consultas RSI correctamente detectadas
- Tools ejecutadas apropiadamente
- Sin falsos positivos

**Calidad de Respuestas**: >85%
- Coherentes y completas
- Basadas en datos reales
- Sin "no puedo" injustificado

**Autonomía**: >80%
- Consultas resueltas sin intervención
- Auto-detección de problemas
- Proactividad

**Velocidad**: <5s para consultas simples, <15s para complejas

### Tests de Aceptación

**Test 1: Complejidad**
- "Analiza brain_chat_v7.py y sugiere 3 mejoras"
- Debe: leer archivo, analizar AST, identificar issues, sugerir fixes

**Test 2: Trading**
- "Muestra métricas de trading de hoy"
- Debe: consultar PocketOption, calcular métricas, mostrar resultados

**Test 3: Debugging**
- "Hay un error en el servidor, investiga"
- Debe: revisar logs, identificar error, sugerir fix, ejecutar si es seguro

**Test 4: Estratégico**
- "Cómo mejoramos el rendimiento?"
- Debe: analizar métricas, identificar brechas, sugerir acciones RSI

---

## 8. ARQUITECTURA TÉCNICA

### Componentes Principales

```
Brain Chat V8.0
├── Core
│   ├── IntentDetector (3 niveles)
│   ├── ToolOrchestrator
│   ├── LLMManager (GPT-4/Claude/Ollama)
│   └── MemoryManager
├── Tools
│   ├── FileSystemTools
│   ├── SystemTools
│   ├── CodeAnalyzer
│   ├── TradingConnectors
│   └── BrainIntegration
├── APIs
│   ├── QuantConnect API
│   ├── Tiingo API
│   ├── PocketOption Bridge
│   └── Dashboard 8070
├── Data
│   ├── UserProfiles
│   ├── ConversationMemory
│   └── SystemMetrics
└── UI
    ├── ChatInterface
    ├── ContextPanel
    └── Visualizations
```

### Flujo de Datos

```
Usuario → Chat UI → Intent Detection → Tool Selection → Tool Execution
                                                    ↓
Respuesta ← LLM Formulation ← Context Aggregation ← Results
```

---

## 9. CONCLUSIÓN

**Brain Chat V8.0** debe ser un AGENTE AUTÓNOMO COMPLETO, no solo un chat con tools.

**Debe poder**:
- ✅ Entender cualquier consulta en lenguaje natural
- ✅ Ejecutar herramientas complejas automáticamente
- ✅ Analizar código, sistemas, y datos de trading
- ✅ Gestionar el ecosistema Brain Lab completo
- ✅ Identificarse como parte del sistema
- ✅ Operar con 90%+ de precisión vs OpenCode

**Tiempo estimado**: 7 semanas de desarrollo iterativo.

**Nivel final**: 95% de capacidad OpenCode.

---

**Documento creado**: 2026-03-20
**Versión**: 1.0
**Autor**: OpenCode para Brain Lab
