# PLAN DE MEJORA CHAT-BRAIN V3.0
## Arquitectura Inteligente de Ejecución

---

## 1. DIAGNÓSTICO DE PROBLEMAS ACTUALES

### Problema 1: Desconexión con Brain API
**Síntoma:** El chat no consulta ni ejecuta a través del Brain API (8010)  
**Causa:** El código tiene lógica de fallback que evita la conexión real  
**Impacto:** Usuario no puede ejecutar acciones del Brain

### Problema 2: Restricciones Excesivas
**Síntoma:** "tool_not_programmatic_apply_safe"  
**Causa:** Lista blanca de tools muy restrictiva  
**Impacto:** Operaciones legítimas bloqueadas

### Problema 3: Sin Sistema de Autorización
**Síntoma:** Operaciones críticas bloqueadas completamente  
**Causa:** No hay mecanismo de "confirmar para ejecutar"  
**Impacto:** No se pueden hacer cambios importantes

### Problema 4: Sin Modos de Operación
**Síntoma:** Todo es tratado igual  
**Causa:** No hay clasificación de operaciones  
**Impacto:** Falta de flexibilidad

---

## 2. ARQUITECTURA PROPUESTA V3.0

### 2.1 Tres Modos de Operación

```
┌─────────────────────────────────────────────────────────────┐
│                   CHAT-BRAIN V3.0                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  MODO CONSULTA (Modo 0)                                     │
│  ├── Consultar estado del sistema                          │
│  ├── Leer archivos                                          │
│  ├── Listar directorios                                     │
│  ├── Obtener métricas                                       │
│  └── NO requiere autorización                               │
│                                                             │
│  MODO EJECUCIÓN (Modo 1)                                    │
│  ├── Ejecutar operaciones estándar                         │
│  ├── Crear archivos en rooms                                │
│  ├── Actualizar configuraciones                             │
│  ├── Enviar requests a APIs                               │
│  └── NO requiere autorización (bajo premisas Brain)        │
│                                                             │
│  MODO CRÍTICO (Modo 2) - Requiere Confirmación            │
│  ├── Modificar archivos core (00_identity/)                │
│  ├── Eliminar archivos                                      │
│  ├── Modificar configuraciones de seguridad                │
│  ├── Ejecutar comandos de sistema                          │
│  └── REQUIERE confirmación explícita del usuario           │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 Sistema de Autorización Inteligente

```python
class ExecutionAuthority:
    """Sistema de autorización por niveles"""
    
    LEVELS = {
        'READ': 0,      # Consulta - Sin autorización
        'WRITE': 1,     # Escritura - Sin autorización (rooms)
        'EXECUTE': 1,   # Ejecución - Sin autorización (bajo premisas)
        'MODIFY_CORE': 2, # Modificar core - Requiere confirmación
        'DELETE': 2,    # Eliminar - Requiere confirmación
        'SYSTEM': 2,    # Comandos sistema - Requiere confirmación
    }
    
    def requires_authorization(self, operation: str, target: str) -> bool:
        """Determina si una operación requiere autorización"""
        level = self._classify_operation(operation, target)
        return level >= 2  # Nivel 2+ requiere confirmación
    
    def _classify_operation(self, operation: str, target: str) -> int:
        """Clasifica operación por nivel de riesgo"""
        # Operaciones de lectura
        if operation in ['read', 'list', 'get', 'show', 'display']:
            return 0
        
        # Operaciones en rooms (seguro)
        if 'room' in target or 'tmp_agent/state/rooms' in target:
            return 1
        
        # Modificar archivos core
        if '00_identity/' in target or '10_FINANCIAL/core/' in target:
            return 2
        
        # Eliminar
        if operation in ['delete', 'remove', 'rm']:
            return 2
        
        # Comandos de sistema
        if operation in ['exec', 'run', 'cmd', 'system']:
            return 2
        
        return 1  # Por defecto: escritura estándar
```

### 2.3 Integración Directa con Brain API

```python
class BrainExecutor:
    """Ejecutor directo de comandos Brain"""
    
    async def execute_brain_command(self, command: str, params: dict):
        """Ejecuta comando a través del Brain API"""
        
        # 1. Verificar autorización
        needs_auth = self.authority.requires_authorization(command, params.get('target'))
        
        if needs_auth:
            return {
                'status': 'PENDING_AUTH',
                'message': 'Esta operación requiere confirmación',
                'command': command,
                'params': params,
                'authorization_code': self._generate_auth_code()
            }
        
        # 2. Ejecutar directamente en Brain API
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{BRAIN_API}/api/execute",
                json={'command': command, 'params': params}
            )
            return response.json()
```

---

## 3. IMPLEMENTACIÓN

### 3.1 Nuevo Servidor Chat V3

Archivo: `brain_chat_ui_server_v3.py`

Características:
- ✅ Conexión directa con Brain API (8010)
- ✅ Sistema de autorización por niveles
- ✅ Tres modos de operación
- ✅ Interfaz de confirmación para operaciones críticas
- ✅ Persistencia de comandos ejecutados
- ✅ Rollback automático en errores
- ✅ Logging completo de auditoría

### 3.2 Componentes Nuevos

1. **execution_authority.py** - Sistema de autorización
2. **brain_executor.py** - Conector directo con Brain
3. **command_classifier.py** - Clasificador de comandos
4. **confirmation_dialog.py** - Diálogo de confirmación UI
5. **audit_logger.py** - Logger de auditoría

### 3.3 Mejoras en el Frontend

- Modo de operación visible en UI
- Diálogo de confirmación para operaciones críticas
- Historial de comandos ejecutados
- Indicador de conexión con Brain
- Soporte para comandos batch

---

## 4. FLUJO DE EJECUCIÓN

### Ejemplo 1: Consulta (Sin Autorización)
```
Usuario: "Muestrame el estado de las fases"

Chat:
├── Clasifica: MODO CONSULTA (Nivel 0)
├── Conecta con Brain API
├── Ejecuta: get_phase_status()
└── Respuesta: "Fase actual: 6.3, BL-03 activo..."
```

### Ejemplo 2: Ejecución Estándar (Sin Autorización)
```
Usuario: "Crea un archivo de prueba en el room actual"

Chat:
├── Clasifica: MODO EJECUCIÓN (Nivel 1)
├── Verifica: target en room/ (seguro)
├── Conecta con Brain API
├── Ejecuta: write_file()
└── Respuesta: "✅ Archivo creado exitosamente"
```

### Ejemplo 3: Operación Crítica (Requiere Confirmación)
```
Usuario: "Modifica el brain_server.py"

Chat:
├── Clasifica: MODO CRÍTICO (Nivel 2)
├── Detecta: target en 00_identity/ (core)
├── Respuesta: 
│   "⚠️ OPERACIÓN CRÍTICA DETECTADA
│    
│    Comando: Modificar brain_server.py
│    Riesgo: Alto (archivo core)
│    
│    Para confirmar, escribe:
│    /confirm [CÓDIGO_DE_AUTORIZACIÓN]
│    
│    O usa: /cancel para abortar"
│
Usuario: "/confirm AUTH-7842"
│
Chat:
├── Verifica código de autorización
├── Conecta con Brain API
├── Ejecuta: modify_file() con rollback habilitado
├── Respuesta: "✅ Archivo modificado exitosamente"
└── Crea backup automático
```

---

## 5. COMANDOS ESPECIALES DEL CHAT

### Comandos de Control
- `/mode` - Muestra modo actual
- `/consulta` - Fuerza modo consulta
- `/ejecuta` - Fuerza modo ejecución
- `/critico` - Fuerza modo crítico (con auth)
- `/confirm [código]` - Confirma operación crítica
- `/cancel` - Cancela operación pendiente
- `/history` - Muestra historial de comandos
- `/rollback [id]` - Revierte operación anterior

### Comandos Brain Directos
- `/brain [comando]` - Ejecuta comando directo en Brain
- `/advisor [comando]` - Ejecuta comando en Advisor
- `/phase status` - Obtiene estado de fases
- `/roadmap` - Muestra roadmap activo
- `/room info` - Información del room actual
- `/pocketoption` - Datos de PocketOption

---

## 6. SEGURIDAD

### 6.1 Principios
1. **Nunca bloquear, siempre autorizar** - Las operaciones críticas piden confirmación, no se bloquean
2. **Transparencia total** - El usuario ve exactamente qué se va a ejecutar
3. **Rollback siempre disponible** - Cada operación crítica tiene rollback automático
4. **Auditoría completa** - Todo se registra para revisión

### 6.2 Prevención de Abuso
- Rate limiting por usuario
- Máximo 3 intentos de confirmación fallidos
- Bloqueo temporal después de intentos fallidos
- Alertas en operaciones muy frecuentes

---

## 7. TESTING

### 7.1 Casos de Prueba

#### TC1: Consulta Simple
```
Input: "Que fase estamos?"
Expected: Respuesta inmediata sin autorización
Status: PASS
```

#### TC2: Ejecución Estándar
```
Input: "Crea un archivo test en room"
Expected: Ejecución inmediata, archivo creado
Status: PASS
```

#### TC3: Operación Crítica con Autorización
```
Input: "Modifica brain_server.py"
Expected: 
  1. Solicitud de confirmación
  2. Usuario confirma con /confirm
  3. Ejecución exitosa
Status: PASS
```

#### TC4: Cancelación Operación Crítica
```
Input: "Modifica brain_server.py", luego "/cancel"
Expected: Operación cancelada, sin cambios
Status: PASS
```

#### TC5: Ejecución Directa Brain
```
Input: "/brain get_phase_status"
Expected: Conexión directa con Brain, respuesta inmediata
Status: PASS
```

---

## 8. MÉTRICAS DE ÉXITO

### Objetivos
- ✅ Latencia consultas: <500ms
- ✅ Latencia ejecución: <1s
- ✅ Tiempo autorización: <30s (incluye confirmación usuario)
- ✅ Tasa éxito: >95%
- ✅ Usabilidad: 5/5 estrellas

### Indicadores
- Número de operaciones ejecutadas
- Tiempo promedio de respuesta
- Tasa de confirmación en operaciones críticas
- Errores de conexión con Brain
- Satisfacción usuario

---

## 9. IMPLEMENTACIÓN INCREMENTAL

### Fase 1: Core (2 horas)
- [ ] Crear execution_authority.py
- [ ] Crear brain_executor.py
- [ ] Modificar brain_chat_ui_server.py

### Fase 2: UI (1 hora)
- [ ] Agregar modos a interfaz
- [ ] Crear diálogo de confirmación
- [ ] Agregar comandos especiales

### Fase 3: Testing (1 hora)
- [ ] Probar todos los casos de uso
- [ ] Verificar conexión con Brain
- [ ] Validar autorizaciones

### Fase 4: Despliegue (30 min)
- [ ] Backup del chat actual
- [ ] Deploy nuevo servidor
- [ ] Verificar funcionamiento

---

## 10. CONCLUSIÓN

Esta arquitectura V3.0 transformará el chat de un sistema limitado a una **consola inteligente de ejecución** que:

✅ **Consulta todo** - Información completa del sistema  
✅ **Ejecuta todo** - Operaciones estándar sin restricciones  
✅ **Autoriza lo crítico** - Operaciones importantes con confirmación  
✅ **Nunca bloquea** - Siempre hay un camino para ejecutar  
✅ **Mantiene seguridad** - Autorización inteligente sin restricciones excesivas  

**Resultado:** Un chat que realmente **potencia** al usuario para operar el sistema Brain completo.

---

**Versión:** 3.0  
**Estado:** Listo para implementación  
**Tiempo estimado:** 4-5 horas  
**Prioridad:** CRÍTICA
