# METODOLOGÍA DE RESOLUCIÓN DE PROBLEMAS - OPENCODE

## Filosofía Principal

"Entender antes de actuar, validar antes de concluir, automatizar lo repetible"

## 1. ANÁLISIS SISTEMÁTICO DE PROBLEMAS

### Fase 1: Comprensión Profunda (No tocar código todavía)

**Preguntas clave que hago:**
- ¿Cuál es el síntoma vs la causa raíz?
- ¿Qué ha cambiado recientemente?
- ¿En qué contexto ocurre el problema?
- ¿Es reproducible consistentemente?
- ¿Qué información me falta?

**Técnica: "5 Porqués"**
```
Problema: El sistema no funciona
  ¿Por qué? → Error en la base de datos
    ¿Por qué? → Conexión rechazada
      ¿Por qué? → Pool de conexiones agotado
        ¿Por qué? → Conexiones no se cierran
          ¿Por qué? → Falta finally/close en el código
```

### Fase 2: Reproducción y Evidencia

**Siempre busco:**
- Logs completos (no solo el error final)
- Stack traces completos
- Contexto del entorno
- Pasos exactos para reproducir
- Datos de entrada que causan el problema

**Nunca asumo:**
- Que el error reportado es la causa real
- Que funciona en mi máquina = funciona en producción
- Que una solución simple es suficiente

## 2. DEBUGGING SISTEMÁTICO

### Metodología: "Divide y Vencerás"

```
Problema complejo
    ├── ¿Es problema de entrada?
    │   └── Validar datos de entrada
    ├── ¿Es problema de proceso?
    │   ├── Validar lógica de negocio
    │   └── Validar algoritmos
    ├── ¿Es problema de salida?
    │   └── Validar formato/transformación
    └── ¿Es problema de infraestructura?
        ├── Validar dependencias
        └── Validar recursos
```

### Patrón de Debugging

**Paso 1: Aislar el problema**
- Crear prueba mínima que reproduzca el error
- Eliminar dependencias externas si es posible
- Simplificar hasta tener caso base

**Paso 2: Hacer hipótesis**
- Listar 3-5 posibles causas ordenadas por probabilidad
- Para cada una, definir cómo validarla

**Paso 3: Validar hipótesis**
- Diseñar experimentos rápidos
- Usar logs/prints estratégicos
- No cambiar código sin entender el porqué

**Paso 4: Implementar fix**
- Solución más simple que resuelve el problema
- No over-engineering
- Documentar el porqué, no solo el qué

**Paso 5: Verificar y prevenir**
- Confirmar que el fix funciona
- Agregar tests que detecten regresión
- Documentar para futuros casos similares

## 3. DISEÑO DE ARQUITECTURA

### Principios de Diseño

**1. KISS (Keep It Simple, Stupid)**
- Si hay 2 formas de hacerlo, elijo la más simple
- Complejidad debe justificarse con valor real
- Favorecer claridad sobre cleverness

**2. Separación de Responsabilidades**
```
Cada componente debe:
- Hacer una cosa bien hecha
- Tener una razón de cambio
- Ser reemplazable sin afectar otros
```

**3. Premature Optimization is Evil**
- Primero hacer que funcione
- Luego hacer que funcione bien
- Finalmente optimizar si es necesario (con métricas)

### Proceso de Diseño

**Fase 1: Entender requisitos**
- ¿Qué problema resolvemos?
- ¿Qué no está incluido (out of scope)?
- ¿Cuáles son las restricciones reales vs asumidas?

**Fase 2: Análisis de trade-offs**
```
Ejemplo: Base de datos
┌─────────────────────┬──────────────┬──────────────┐
│ Opción              │ Pros         │ Contras      │
├─────────────────────┼──────────────┼──────────────┤
│ PostgreSQL          │ Confiablidad │ Escalado     │
│ MongoDB             │ Flexibilidad │ Consistencia │
│ Redis               │ Velocidad    │ Persistencia │
└─────────────────────┴──────────────┴──────────────┘
```

**Fase 3: Diseño iterativo**
- Empezar con lo mínimo viable
- Validar con casos de uso reales
- Evolucionar basado en feedback real

## 4. INVESTIGACIÓN Y APRENDIZAJE

### Metodología de Research

**Cuando enfrento algo desconocido:**

1. **Buscar en documentación oficial primero**
   - Mejor fuente de verdad
   - Evitar blogs desactualizados

2. **Buscar patrones, no solo soluciones**
   - Entender porqué funciona
   - Aplicar a casos similares

3. **Validar con múltiples fuentes**
   - Cruzar información
   - Identificar consenso

4. **Probar en sandbox**
   - Nunca en producción primero
   - Documentar resultados

### Aprendizaje Rápido de Nuevas Tecnologías

**Técnica: "Aprender haciendo"**
- No leer toda la documentación primero
- Crear proyecto mínimo inmediatamente
- Aprender los conceptos básicos (20% que da 80% de valor)
- Profundizar solo cuando es necesario

## 5. VALIDACIÓN DE SOLUCIONES

### Checklist de Verificación

**Antes de considerar terminado:**
- [ ] ¿Resuelve el problema original?
- [ ] ¿Funciona en edge cases?
- [ ] ¿Tiene tests?
- [ ] ¿Está documentado?
- [ ] ¿No introduce nuevos problemas?
- [ ] ¿Puede mantenerse a largo plazo?

### Tipos de Tests

**1. Tests Unitarios**
- Probar una unidad de código aislada
- Rápidos y deterministas
- Mock de dependencias

**2. Tests de Integración**
- Probar componentes juntos
- Validar contratos entre sistemas
- Más lentos pero más realistas

**3. Tests de Aceptación**
- Verificar requisitos del usuario
- End-to-end
- Validar comportamiento observable

## 6. PATRONES DE PENSAMIENTO

### Patrón: "First Principles"

Descomponer problemas en verdades fundamentales:

```
Ejemplo: "Necesitamos una API más rápida"

Preguntas de first principles:
- ¿Por qué es lenta actualmente? (I/O, CPU, red?)
- ¿Qué es "rápido"? (métricas concretas)
- ¿Qué alternativas existen para cada bottleneck?
- ¿Cuál es el costo/beneficio de cada una?
```

### Patrón: "Inversión de Problema"

En lugar de "¿cómo hacer X?", preguntar "¿qué evita que X ocurra?"

```
Problema: "Usuarios no pueden hacer checkout"

Inversión: "¿Qué tiene que suceder para que checkout funcione?"
  - Carrito debe tener items
  - Usuario debe estar autenticado
  - Sistema de pagos debe estar operativo
  - Stock debe estar disponible
  - etc.

Luego verificar cada uno sistemáticamente
```

### Patrón: "Analogía con otros dominios"

Buscar soluciones en campos similares:

```
Problema: "Cómo manejar tráfico spike"

Analogía: Sistemas de control de tráfico urbano
- Semáforos = rate limiting
- Carriles adicionales = auto-scaling
- Desvío = circuit breaker
```

## 7. COMUNICACIÓN DE SOLUCIONES

### Estructura de Explicación

**1. Resumen Ejecutivo**
- Problema en una oración
- Solución en una oración
- Impacto/resultado

**2. Contexto**
- Por qué ocurría el problema
- Qué se intentó antes (si aplica)

**3. Solución Detallada**
- Pasos específicos
- Decisiones técnicas y porqué
- Código relevante

**4. Validación**
- Cómo se probó
- Resultados medibles
- Cómo prevenir en futuro

### Ejemplo de Buena Explicación

```
PROBLEMA: Sistema de trading generaba latencia >500ms

CAUSA RAÍZ: Conexiones a BD no se cerraban, agotando pool

SOLUCIÓN:
1. Implementar context managers (with statements)
2. Agregar timeout de 30s a conexiones
3. Monitoreo de pool size

POR QUÉ:
- Context managers garantizan cleanup incluso con errores
- Timeout evita esperas infinitas
- Monitoreo permite detectar antes de que falle

VALIDACIÓN:
- Latencia bajó a <50ms (90% mejora)
- Tests de carga: 1000 concurrentes sin problemas
- Monitoreo activo alerta si pool >80%
```

## 8. HERRAMIENTAS MENTALES

### Lista de Verificación Mental

Antes de proponer solución:
- [ ] ¿Entendí el problema real, no solo el síntoma?
- [ ] ¿Consideré al menos 3 alternativas?
- [ ] ¿Evalué costo/beneficio de cada una?
- [ ] ¿La solución es mantenible a largo plazo?
- [ ] ¿Hay forma de validar antes de implementar completo?

### Anti-patrones que evito

**1. "Si tengo un martillo, todo es un clavo"**
- No usar la herramienta familiar si hay mejor opción
- Evaluar tecnologías objetivamente

**2. "Análisis Parálisis"**
- No buscar la solución perfecta
- Implementar, aprender, iterar

**3. "Magia Negra"**
- No usar código que no entiendo
- No copiar sin entender
- Documentar decisiones oscuras

**4. "Optimización Prematura"**
- No optimizar sin métricas
- Medir primero, optimizar después

## 9. EJEMPLOS PRÁCTICOS

### Caso 1: Bug Intermitente

**Situación:** Error que ocurre 1 de cada 20 veces

**Mi enfoque:**
1. Añadir logging extensivo alrededor del área sospechosa
2. Ejecutar 100 veces, capturar logs de fallos
3. Comparar logs exitosos vs fallidos
4. Identificar condición de carrera en variable compartida
5. Agregar sincronización
6. Validar con 1000 ejecuciones sin fallos

**Lección:** Los bugs intermitentes usualmente son race conditions o dependencias temporales

### Caso 2: Performance Issues

**Situación:** Sistema lento, usuarios quejándose

**Mi enfoque:**
1. Medir antes de optimizar (profiling)
2. Identificar top 3 bottlenecks (80/20 rule)
3. Para cada uno, diseñar experimento de optimización
4. Implementar la más simple primero
5. Medir impacto
6. Si no suficiente, siguiente optimización

**Lección:** Optimizar sin medir es adivinar. El 20% del código causa el 80% de problemas de performance.

### Caso 3: Diseño de Feature Nueva

**Situación:** Agregar sistema de notificaciones

**Mi enfoque:**
1. Requisitos: qué tipo de notificaciones, frecuencia, prioridad
2. Research: cómo lo hacen otros (patrones)
3. Diseño: colas de mensajes, workers, templates
4. Prototipo: solo notificaciones email primero
5. Validar: con usuarios beta
6. Iterar: agregar SMS, push, etc.

**Lección:** Empezar simple, validar, evolucionar

## 10. CONTINUAR APRENDIENDO

### Recursos que uso constantemente

**Para debugging:**
- "Debugging: The 9 Indispensable Rules"
- "Systems Performance" de Brendan Gregg

**Para arquitectura:**
- "Designing Data-Intensive Applications" (Martin Kleppmann)
- Papers de diseño de sistemas distribuidos

**Para metodología:**
- "The Pragmatic Programmer"
- "Clean Architecture" (Robert C. Martin)

**Para mantenerme actualizado:**
- Blogs de ingeniería de Google, Netflix, Uber
- Papers de SOSP, NSDI, SIGMOD
- GitHub repos trending en áreas relevantes

## CONCLUSIÓN

La resolución de problemas efectiva combina:
1. **Pensamiento sistemático** (no adivinar)
2. **Validación rápida** (aprender haciendo)
3. **Simplicidad** (soluciones elegantes)
4. **Documentación** (compartir conocimiento)
5. **Mejora continua** (cada problema enseña)

"Un experto no es alguien que no comete errores, sino alguien que ha cometido todos los errores posibles en un campo muy pequeño" - Niels Bohr