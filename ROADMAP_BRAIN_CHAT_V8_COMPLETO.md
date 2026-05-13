# ROADMAP BRAIN CHAT V8.0 - Agente Autónomo 100%
## De Chatbot con Herramientas → Agente de Software Engineering

**Fecha Inicio:** 2026-03-20  
**Estado Actual:** 25% (Infraestructura completa, núcleo ausente)  
**Objetivo:** 100% equivalencia funcional con OpenCode  
**Tiempo Estimado:** 8-12 semanas (desarrollo intensivo)

---

## FASE 0: PREPARACIÓN CRÍTICA (Semana 0)
**Objetivo:** Establecer base sólida antes de construir el agente

### Tarea 0.1: Corregir Configuración LLM
**Descripción:** Cambiar modelo Ollama de "llama2" (inexistente) a modelo funcional
**Archivo:** `C:\AI_VAULT\00_identity\chat_brain_v7\brain_chat_v8.py:828`
**Cambio:** `"model": "llama2"` → `"model": "qwen2.5:14b"`
**Verificación:** 
```bash
curl http://127.0.0.1:11434/api/tags | grep qwen2.5
# Debe mostrar: qwen2.5:14b disponible
```
**Estado:** ✅ COMPLETADO (detectado, listo para implementar)

### Tarea 0.2: Priorizar Ollama sobre APIs externas
**Descripción:** Cambiar orden de modelos para evitar timeouts
**Archivo:** `brain_chat_v8.py:107`
**Cambio:** `MODEL_PRIORITY = ["gpt4", "claude", "ollama"]` → `["ollama", "gpt4", "claude"]`
**Verificación:** 
```bash
# En logs: Debe intentar Ollama primero, no GPT4
```
**Estado:** ✅ COMPLETADO (detectado, listo para implementar)

### Tarea 0.3: Sistema de Test Automatizado
**Descripción:** Crear suite de tests que verifique funcionalidad del agente
**Archivo Nuevo:** `tests/test_agent_capabilities.py`
**Tests requeridos:**
- Test de conexión LLM
- Test de ejecución de herramientas
- Test de memoria persistente
- Test de planificación
- Test de verificación de cambios
**Verificación:** `python -m pytest tests/test_agent_capabilities.py -v`
**Estado:** ⏳ PENDIENTE

**Métricas de Éxito Fase 0:**
- [ ] Ollama responde en < 5 segundos
- [ ] No hay timeouts con GPT4/Claude
- [ ] Suite de tests ejecuta sin errores
- [ ] 100% tests pasan

---

## FASE 1: NÚCLEO DEL AGENTE - Loop Básico (Semanas 1-2)
**Objetivo:** Implementar ciclo fundamental: Observe → Reason → Act → Verify

### Tarea 1.1: Implementar AgentLoop Core
**Descripción:** Crear clase AgentLoop con ciclo básico de agente
**Archivo Nuevo:** `00_identity/agent_core.py`
**Responsabilidades:**
```python
class AgentLoop:
    def observe(self, context: Dict) -> Observations
    def reason(self, observations: Observations) -> Plan  
    def act(self, plan: Plan) -> Actions
    def verify(self, actions: Actions) -> Results
    def run_cycle(self, task: str) -> ExecutionResult
```
**Lineas estimadas:** 400-600
**Dependencias:** Ninguna (usa ToolRegistry existente)
**Verificación:**
```python
# Test: agente ejecuta tarea simple de 3 pasos
result = agent.run_cycle("Crea un archivo test.txt con 'hola'")
assert result.steps == 3
assert result.success == True
assert Path("test.txt").exists()
```
**Estado:** ⏳ PENDIENTE

### Tarea 1.2: Sistema de Planificación Simple
**Descripción:** Descomponer tareas en pasos ejecutables
**Archivo:** `agent_core.py:Planner`
**Capacidades:**
- Recibir objetivo de alto nivel: "Refactoriza brain_server.py para usar async"
- Generar plan de 3-7 pasos concretos
- Cada paso debe ser atómico y verificable
- Manejar dependencias entre pasos
**Ejemplo entrada:** "Agrega logging a brain_chat_v8.py"
**Ejemplo salida:**
```json
{
  "steps": [
    {"id": 1, "action": "read_file", "params": {"path": "brain_chat_v8.py"}, "verify": "file_read"},
    {"id": 2, "action": "find_imports", "params": {"pattern": "logging"}, "verify": "imports_found"},
    {"id": 3, "action": "edit_file", "params": {"add_import": "import logging"}, "verify": "import_added"},
    {"id": 4, "action": "add_logging_calls", "params": {"functions": ["process_message"]}, "verify": "logging_present"}
  ]
}
```
**Verificación:** Plan debe descomponer 10 tareas de ejemplo correctamente
**Estado:** ⏳ PENDIENTE

### Tarea 1.3: Integración con LLM para Razonamiento
**Descripción:** Usar Ollama (qwen2.5:14b) para razonamiento de planificación
**Archivo:** `agent_core.py:LLMReasoner`
**Prompt template:**
```
Eres un agente de software engineering. Tu tarea es descomponer objetivos en pasos ejecutables.

CONTEXTO DEL SISTEMA:
- Trabajas en C:\AI_VAULT\00_identity\chat_brain_v7
- Herramientas disponibles: read_file, write_file, edit_file, search_files, execute_command, analyze_code
- Eres Brain Chat V8.0, parte del sistema AI_VAULT

OBJETIVO DEL USUARIO: {user_goal}

ESTADO ACTUAL: {system_state}

Genera un plan JSON con pasos específicos. Cada paso debe:
1. Ser atómico (una sola acción)
2. Ser verificable (cómo sé que se completó)
3. Tener manejo de errores

Responde SOLO con el JSON del plan.
```
**Verificación:** 
- Latencia < 10 segundos por query
- Planes válidos en 80% de casos
- Manejo correcto de errores
**Estado:** ⏳ PENDIENTE

### Tarea 1.4: Memoria de Ejecución
**Descripción:** Sistema de memoria para mantener contexto entre pasos
**Archivo:** `agent_core.py:ExecutionMemory`
**Capacidades:**
- Guardar resultados de cada paso
- Acceder a resultados anteriores
- Manejar variables entre pasos
- Recuperación ante fallos
**Verificación:**
```python
memory.set("step_1_result", file_content)
memory.get("step_1_result")  # Retorna contenido
memory.save_to_disk()  # Persistente
```
**Estado:** ⏳ PENDIENTE

**Métricas de Éxito Fase 1:**
- [ ] AgentLoop ejecuta ciclo completo sin errores
- [ ] Planifica correctamente 10 tareas de ejemplo
- [ ] Latencia LLM < 10s promedio
- [ ] Memoria persistente entre ciclos
- [ ] 100% tareas simples (1-3 pasos) completadas exitosamente

---

## FASE 2: HERRAMIENTAS AVANZADAS (Semanas 3-4)
**Objetivo:** Expandir ToolRegistry con herramientas de nivel OpenCode

### Tarea 2.1: Análisis AST Profundo
**Descripción:** Herramientas para entender código Python semánticamente
**Archivo:** `00_identity/tools_ast.py`
**Herramientas:**
- `parse_ast(file_path)` → Árbol sintáctico completo
- `find_functions(file_path)` → Con docstrings, parámetros, líneas
- `find_classes(file_path)` → Con métodos, herencia, atributos
- `find_imports(file_path)` → Con origen y usos
- `calculate_complexity(file_path)` → Complejidad ciclomática
- `find_dependencies(file_path)` → Grafo de dependencias
**Verificación:**
```python
result = tools.parse_ast("brain_chat_v8.py")
assert len(result.functions) > 50
assert "process_message" in [f.name for f in result.functions]
assert result.imports[0].module == "os"
```
**Estado:** ⏳ PENDIENTE

### Tarea 2.2: Suite de Búsqueda
**Descripción:** Herramientas de búsqueda tipo grep/glob
**Archivo:** `00_identity/tools_search.py`
**Herramientas:**
- `grep(pattern, path, recursive=True)` → Buscar contenido en archivos
- `glob_files(pattern, path)` → Encontrar archivos por patrón
- `find_symbol(symbol_name, path)` → Buscar definición de símbolo
- `find_references(symbol_name, path)` → Buscar usos de símbolo
**Verificación:**
```python
results = tools.grep("def process_message", "C:\AI_VAULT")
assert len(results) > 0
assert all("process_message" in r.content for r in results)
```
**Estado:** ⏳ PENDIENTE

### Tarea 2.3: Edición Avanzada
**Descripción:** Herramientas para modificar código de forma inteligente
**Archivo:** `00_identity/tools_edit.py`
**Herramientas:**
- `edit_by_ast(file_path, target, replacement)` → Editar usando AST
- `insert_function(file_path, function_code, position)` → Insertar función
- `add_import(file_path, import_statement)` → Agregar import ordenado
- `refactor_rename(file_path, old_name, new_name)` → Renombrar símbolo
**Verificación:**
```python
tools.add_import("brain_chat_v8.py", "import asyncio")
# Verificar que el import está presente y ordenado
```
**Estado:** ⏳ PENDIENTE

### Tarea 2.4: Integración con Git
**Descripción:** Herramientas para control de versiones
**Archivo:** `00_identity/tools_git.py`
**Herramientas:**
- `git_status(path)` → Estado del repositorio
- `git_diff(path)` → Diferencias actuales
- `git_commit(message, path)` → Crear commit
- `git_log(path, n=10)` → Historial de commits
**Verificación:**
```python
status = tools.git_status("C:\AI_VAULT")
assert "brain_chat_v8.py" in status.modified
```
**Estado:** ⏳ PENDIENTE

**Métricas de Éxito Fase 2:**
- [ ] Análisis AST funciona en 100% archivos Python
- [ ] Búsqueda grep/glob equivalente a herramientas Unix
- [ ] Edición preserva sintaxis válida
- [ ] Git integration sin errores
- [ ] Suite de tests cubre 90% de herramientas

---

## FASE 3: RAZONAMIENTO COMPLEJO (Semanas 5-6)
**Objetivo:** Capacidad de razonamiento multi-paso con LLM

### Tarea 3.1: Chain-of-Thought para Debugging
**Descripción:** Sistema de razonamiento paso a paso para debugging
**Archivo:** `00_identity/reasoning.py:DebugReasoner`
**Proceso:**
1. Recibir error y stack trace
2. Analizar código relevante con AST
3. Identificar posibles causas (ranking)
4. Proponer hipótesis de solución
5. Verificar hipótesis
6. Implementar fix
7. Verificar fix
**Ejemplo:**
```
Error: "NameError: name 'tool_registry' is not defined"
Reasoning:
1. Analizar archivo donde ocurre el error
2. Buscar definiciones de 'tool_registry'
3. Identificar que se usa 'self.tool_registry' vs 'tool_registry'
4. Hipótesis: Falta 'self.' o variable no inicializada
5. Verificar inicialización en __init__
6. Aplicar fix: cambiar a 'self.tool_registry'
7. Test: ejecutar código → OK
```
**Verificación:** Resolver 5 bugs de ejemplo automáticamente
**Estado:** ⏳ PENDIENTE

### Tarea 3.2: Refactorización Inteligente
**Descripción:** Capacidad de refactorizar código manteniendo comportamiento
**Archivo:** `00_identity/reasoning.py:RefactoringPlanner`
**Capacidades:**
- Extraer función (extract method)
- Renombrar símbolos (rename symbol)
- Mover código entre archivos
- Eliminar código muerto
- Optimizar imports
**Verificación:**
```python
# Antes: Código duplicado en 3 lugares
# Después: Función extraída, 3 llamadas, tests pasan
```
**Estado:** ⏳ PENDIENTE

### Tarea 3.3: Generación de Código
**Descripción:** Crear nuevo código a partir de especificaciones
**Archivo:** `00_identity/reasoning.py:CodeGenerator`
**Capacidades:**
- Generar funciones con docstrings
- Crear clases con métodos base
- Implementar interfaces
- Generar tests unitarios
**Ejemplo:**
```
Input: "Crea una clase FileManager con métodos read, write, delete"
Output: Código Python completo con type hints, docstrings, manejo de errores
```
**Verificación:** Código generado pasa tests de sintaxis y funcionalidad
**Estado:** ⏳ PENDIENTE

**Métricas de Éxito Fase 3:**
- [ ] DebugReasoner resuelve 80% de bugs comunes
- [ ] Refactorización preserva comportamiento (tests pasan)
- [ ] Código generado es funcional y sigue PEP8
- [ ] Tiempo de razonamiento < 30s por decisión compleja

---

## FASE 4: VERIFICACIÓN Y VALIDACIÓN (Semana 7)
**Objetivo:** Sistema robusto de verificación de cambios

### Tarea 4.1: Verificación Sintáctica
**Descripción:** Verificar que código modificado es sintácticamente válido
**Archivo:** `00_identity/verification.py:SyntaxVerifier`
**Métodos:**
- Análisis AST antes y después
- Detección de syntax errors
- Verificación de imports válidos
**Verificación:**
```python
# Después de cualquier edit
assert verifier.check_syntax(file_path) == True
```
**Estado:** ⏳ PENDIENTE

### Tarea 4.2: Verificación Semántica
**Descripción:** Verificar que comportamiento se preserva
**Archivo:** `00_identity/verification.py:SemanticVerifier`
**Métodos:**
- Comparación de AST estructural
- Detección de cambios en firmas de funciones
- Verificación de llamadas a funciones modificadas
**Verificación:** Tests existentes deben pasar
**Estado:** ⏳ PENDIENTE

### Tarea 4.3: Tests Automatizados
**Descripción:** Ejecutar tests para validar cambios
**Archivo:** `00_identity/verification.py:TestRunner`
**Integración:** pytest, unittest
**Verificación:**
```python
result = test_runner.run_tests("tests/")
assert result.passed == result.total
```
**Estado:** ⏳ PENDIENTE

**Métricas de Éxito Fase 4:**
- [ ] 100% cambios verificados sintácticamente
- [ ] 90% cambios pasan tests existentes
- [ ] Sistema puede auto-revertir cambios fallidos
- [ ] Tiempo de verificación < 10s

---

## FASE 5: INTEGRACIÓN BRAIN LAB (Semana 8)
**Objetivo:** Conectar con ecosistema Brain existente

### Tarea 5.1: Integración con Brain Router
**Descripción:** El agente debe usar brain_router.py para comunicación
**Archivo:** Modificar `agent_core.py`
**Integración:**
- Usar brain_router para requests HTTP
- Integrar con endpoints existentes (/brain/health, /brain/metrics)
- Respetar autenticación de sistema
**Verificación:**
```python
health = agent.query_brain("/health")
assert health["status"] == "healthy"
```
**Estado:** ⏳ PENDIENTE

### Tarea 5.2: Integración con RSI Manager
**Descripción:** Consultar y actuar sobre análisis RSI
**Archivo:** `00_identity/rsi_integration.py`
**Capacidades:**
- Obtener brechas estratégicas
- Priorizar tareas según RSI
- Reportar progreso al sistema RSI
**Verificación:** Actualizar estado de tareas en RSI automáticamente
**Estado:** ⏳ PENDIENTE

### Tarea 5.3: Integración con Dashboard 8070
**Descripción:** Mostrar actividad del agente en dashboard
**Archivo:** `00_identity/dashboard_integration.py`
**Capacidades:**
- Enviar métricas de ejecución
- Mostrar tareas en progreso
- Reportar errores y alertas
**Verificación:** Dashboard muestra actividad del agente en tiempo real
**Estado:** ⏳ PENDIENTE

**Métricas de Éxito Fase 5:**
- [ ] Agente usa infraestructura Brain existente
- [ ] RSI refleja trabajo del agente
- [ ] Dashboard muestra métricas del agente
- [ ] Integración sin duplicar funcionalidad

---

## FASE 6: OPTIMIZACIÓN Y PRODUCCIÓN (Semanas 9-10)
**Objetivo:** Sistema robusto, rápido y confiable

### Tarea 6.1: Caché de LLM
**Descripción:** Cachear respuestas de LLM para consultas similares
**Archivo:** `00_identity/cache.py`
**Estrategia:** embeddings + similitud coseno
**Verificación:** Reducir latencia en 50% para queries repetidas
**Estado:** ⏳ PENDIENTE

### Tarea 6.2: Manejo de Errores Robusto
**Descripción:** Sistema de recuperación ante fallos
**Archivo:** `00_identity/error_recovery.py`
**Capacidades:**
- Retry con backoff exponencial
- Fallback entre modelos (Ollama → Claude → GPT-4)
- Checkpoint de ejecución
- Recuperación de estado
**Verificación:** Agente recupera 90% de fallos automáticamente
**Estado:** ⏳ PENDIENTE

### Tarea 6.3: Optimización de Performance
**Descripción:** Reducir latencia y uso de recursos
**Tareas:**
- Profiling de código lento
- Optimización de queries AST
- Batch processing de archivos
- Lazy loading de herramientas
**Verificación:** 
- Tiempo de respuesta < 2s para tareas simples
- Uso de memoria < 500MB
- Capacidad de procesar archivos de 10k+ líneas
**Estado:** ⏳ PENDIENTE

**Métricas de Éxito Fase 6:**
- [ ] Latencia promedio < 2s
- [ ] Uso de memoria < 500MB
- [ ] 90% recuperación automática de errores
- [ ] Soporta archivos grandes (>10k líneas)

---

## FASE 7: VALIDACIÓN FINAL (Semanas 11-12)
**Objetivo:** Verificar equivalencia 100% con OpenCode

### Tarea 7.1: Suite de Benchmarks
**Descripción:** Tests comparativos contra OpenCode
**Archivo:** `tests/benchmark_opencode.py`
**Tests:**
- Analizar archivo de 1000 líneas
- Refactorizar función compleja
- Buscar patrón en codebase completo
- Generar código nuevo
- Debuggear error real
**Verificación:** V8 debe completar todas las tareas que OpenCode completa
**Estado:** ⏳ PENDIENTE

### Tarea 7.2: Prueba de Autonomía Extendida
**Descripción:** Dejar agente trabajando 4 horas sin supervisión
**Objetivo:** Completar backlog de tareas automáticamente
**Métricas:**
- Tareas completadas: > 20
- Tasa de éxito: > 80%
- Errores críticos: 0
- Intervención humana: < 5 veces
**Estado:** ⏳ PENDIENTE

### Tarea 7.3: Documentación y Handover
**Descripción:** Documentar sistema completo
**Archivos:**
- `docs/ARCHITECTURE.md` - Arquitectura del agente
- `docs/API.md` - API del agente
- `docs/USAGE.md` - Guía de uso
- `docs/DEVELOPMENT.md` - Guía de desarrollo
**Verificación:** Nuevo desarrollador puede entender y extender el sistema en 1 día
**Estado:** ⏳ PENDIENTE

**Métricas de Éxito Fase 7:**
- [ ] Pasa 100% de benchmarks de OpenCode
- [ ] Trabaja 4h autónomamente con >80% éxito
- [ ] Documentación completa y clara
- [ ] Sistema listo para producción

---

## SISTEMA DE VERIFICACIÓN CONTINUA

### Métricas Clave por Fase
```python
METRICS = {
    "Fase 0": {
        "ollama_response_time": "< 5s",
        "test_suite_pass_rate": "100%",
        "no_timeout_errors": True
    },
    "Fase 1": {
        "agent_loop_success_rate": "100%",
        "planning_accuracy": "> 80%",
        "llm_latency_avg": "< 10s",
        "memory_persistence": "100%"
    },
    "Fase 2": {
        "ast_coverage": "100%",
        "search_equivalence": "grep/glob",
        "edit_syntax_valid": "100%",
        "tool_test_coverage": "> 90%"
    },
    "Fase 3": {
        "debug_success_rate": "> 80%",
        "refactor_preservation": "100%",
        "code_generation_valid": "> 90%",
        "reasoning_time": "< 30s"
    },
    "Fase 4": {
        "syntax_verification": "100%",
        "test_pass_rate": "> 90%",
        "auto_revert_rate": "< 10%",
        "verification_time": "< 10s"
    },
    "Fase 5": {
        "brain_integration": "100%",
        "rsi_sync": "real-time",
        "dashboard_metrics": "active",
        "no_duplication": True
    },
    "Fase 6": {
        "latency_p95": "< 2s",
        "memory_usage": "< 500MB",
        "recovery_rate": "> 90%",
        "large_file_support": "> 10k lines"
    },
    "Fase 7": {
        "opencode_equivalence": "100%",
        "autonomy_4h_success": "> 80%",
        "documentation_complete": True,
        "production_ready": True
    }
}
```

### Tests de Verificación Automatizados
Cada fase incluye tests automatizados en `tests/test_fase_{N}.py`

**Comando de verificación:**
```bash
# Verificar fase específica
python -m pytest tests/test_fase_1.py -v

# Verificar todas las fases completadas
python -m pytest tests/ -v --tb=short

# Reporte de cobertura
python -m pytest tests/ --cov=00_identity --cov-report=html
```

### Checkpoints de Decisión

**Checkpoint 0 → 1:**
- [ ] Ollama funcional con qwen2.5:14b
- [ ] Test suite ejecuta sin errores
- [ ] Sistema base estable

**Checkpoint 1 → 2:**
- [ ] AgentLoop ejecuta ciclo completo
- [ ] Planificación funciona en 80% de casos
- [ ] Memoria persistente operativa

**Checkpoint 2 → 3:**
- [ ] Suite de herramientas completa
- [ ] Equivalencia grep/glob
- [ ] Edición AST funcional

**Checkpoint 3 → 4:**
- [ ] Razonamiento multi-paso funciona
- [ ] Debug automático resuelve 80% de bugs
- [ ] Generación de código operativa

**Checkpoint 4 → 5:**
- [ ] Verificación automática robusta
- [ ] Tests pasan en 90% de cambios
- [ ] Auto-revert funciona

**Checkpoint 5 → 6:**
- [ ] Integración Brain Lab completa
- [ ] RSI actualizado automáticamente
- [ ] Dashboard muestra actividad

**Checkpoint 6 → 7:**
- [ ] Performance objetivo alcanzada
- [ ] Recuperación automática de errores
- [ ] Sistema estable bajo carga

**Checkpoint 7 → PRODUCCIÓN:**
- [ ] 100% equivalencia con OpenCode
- [ ] 4h autonomía demostrada
- [ ] Documentación completa

---

## RESUMEN EJECUTIVO

**ESTADO ACTUAL:**
- ✅ Infraestructura: 100% (servidor, UI, endpoints)
- ✅ ToolRegistry: 100% (24 herramientas registradas)
- ✅ Sistema de trading: 100% (integrado)
- ⚠️ LLM: 50% (configurado pero no funcional)
- ❌ Núcleo de agente: 0% (no existe)
- ❌ Razonamiento: 0% (no existe)
- ❌ Verificación: 0% (no existe)

**COMPARACIÓN:**
| Capacidad | V8 Actual | OpenCode | Objetivo |
|-----------|-----------|----------|----------|
| Chat simple | ✅ | ✅ | ✅ |
| Ejecutar comandos | ✅ | ✅ | ✅ |
| Análisis de código | ⚠️ superficial | ✅ profundo | ✅ profundo |
| Búsqueda codebase | ⚠️ básica | ✅ avanzada | ✅ avanzada |
| Editar archivos | ⚠️ simple | ✅ inteligente | ✅ inteligente |
| Planificar tareas | ❌ | ✅ | ✅ |
| Razonamiento multi-paso | ❌ | ✅ | ✅ |
| Debug automático | ❌ | ✅ | ✅ |
| Generar código | ❌ | ✅ | ✅ |
| Verificación automática | ❌ | ✅ | ✅ |
| Autonomía extendida | ❌ | ✅ | ✅ |

**RUTA CRÍTICA:**
Fase 0 → Fase 1 → Fase 2 → Fase 3 → Fase 4 → Fase 7

**Sin estas fases, el sistema NO será un agente autónomo.**

**TIEMPO ESTIMADO TOTAL:** 8-12 semanas  
**RECURSOS NECESARIOS:** 
- 1 GPU para Ollama (qwen2.5:14b requiere ~10GB VRAM)
- Desarrollador Python senior (o equivalente en esfuerzo)
- Tests automatizados en cada fase

**PRÓXIMO PASO INMEDIATO:**
Implementar Fase 0 (Preparación) y Fase 1 (Núcleo del Agente).
Sin estas, ninguna otra fase tiene sentido.

---

**Documento generado:** 2026-03-20  
**Versión:** 1.0  
**Autor:** OpenCode (Auditoría AI_VAULT)  
**Estado:** Listo para ejecución
