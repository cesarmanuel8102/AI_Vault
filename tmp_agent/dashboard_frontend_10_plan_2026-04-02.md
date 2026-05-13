# Plan Maestro: Dashboard 8090 hacia 10/10

**Fecha:** 2026-04-02  
**Ámbito:** `tmp_agent/brain_v9/ui/dashboard.html` + contrato visible del runtime `8090`

## Punto de partida honesto

Estado actual estimado: **6.8/10**

Fortalezas:
- La capa de datos visible ya es bastante más canónica.
- El dashboard sirve para operar y detectar contradicciones reales.
- La jerarquía principal ya existe: `Overview`, `Platforms`, `Strategy Engine`, `System`.

Debilidades:
- `dashboard.html` sigue siendo un archivo monolítico con mezcla de estilos, fetch, estado, render y semántica.
- Hay demasiada construcción imperativa por `innerHTML`.
- Los estados vacíos, errores y loading no siguen un contrato único.
- Parte de la semántica operativa todavía exige reconstrucción mental.
- La accesibilidad y la mantenibilidad siguen por debajo de nivel senior.

## Definición de 10/10 para este dashboard

Se considerará **10/10 operativo** cuando cumpla simultáneamente:

1. **Verdad**
- Ningún bloque importante inventa liderazgo, score o estado.
- Cada KPI crítico deja claro su base semántica.
- `runtime live truth`, `resolved sample truth` y `global effective truth` no se mezclan.

2. **Lectura**
- Un operador técnico entiende en menos de `10s`:
  - modo actual
  - bloqueo principal
  - siguiente acción
  - foco operativo
  - salud de infraestructura
  - diferencia entre actividad live y performance resuelta

3. **Consistencia**
- Todos los estados `loading / empty / pending / error / unavailable / inactive` usan una misma semántica y presentación.
- Los paneles usan helpers de presentación reutilizables.

4. **Mantenibilidad**
- El HTML principal queda dividido en helpers y bloques claramente separables.
- Las mejoras futuras se pueden hacer sin volver a mezclar conceptos.

5. **Accesibilidad**
- Los mensajes dinámicos importantes usan `aria-live`.
- Los estados de error y vacío tienen roles semánticos.
- Las acciones críticas son distinguibles sin depender solo del color.

6. **Validación**
- Toda mejora de semántica o jerarquía queda probada y documentada en el repo.

## Fases para llegar a 10

### Fase 1. Contrato de presentación y estados UI

**Objetivo**
- Quitar fragilidad básica del frontend sin mover lógica del Brain.

**Trabajo**
- Introducir helpers reutilizables para:
  - `kpiCard`
  - estados `loading / empty / error / info`
  - notas semánticas
  - render seguro a targets
- Aplicar ese contrato al menos en:
  - `Overview`
  - `Platforms`
  - `Strategy Engine`
  - errores globales de refresh
- Añadir `aria-live` y roles básicos donde sí cambia decisión operativa.

**Validación**
- Tests HTML verifican presencia del sistema de estados y de helpers nuevos.
- Las vistas sin datos dejan de usar cadenas sueltas repetidas.

**Impacto esperado**
- +0.6 a +0.8 puntos

### Fase 2. Jerarquía operativa y lectura en 10 segundos

**Objetivo**
- Hacer que `Overview` sea una vista ejecutiva real y no una agregación de KPIs.

**Trabajo**
- Consolidar la franja ejecutiva superior:
  - modo
  - blocker
  - next action
  - lane
  - fair test progress
  - maintenance risk
- Reducir ruido visual en bloques secundarios.
- Ordenar las cards por decisión, no por subsistema técnico.

**Validación**
- Checklist manual con captura:
  - un operador puede responder 6 preguntas críticas en menos de 10 segundos.

**Impacto esperado**
- +0.5 a +0.7 puntos

### Fase 3. Strategy Engine: semántica operativa vs ranking técnico

**Objetivo**
- Separar definitivamente:
  - selección canónica
  - ranking técnico
  - lane operativa
  - estado de ejecución

**Trabajo**
- Rehacer el encabezado de `Strategy Engine`.
- Agrupar estrategias en:
  - `lane focus`
  - `ranked global`
  - `blocked / diagnostic`
- Mostrar explícitamente por qué algo rankea alto pero no gobierna.

**Validación**
- Tests HTML y revisión manual con ejemplos `top_strategy = null` y con `ranked leader` distinto.

**Impacto esperado**
- +0.4 a +0.6 puntos

### Fase 4. Accesibilidad y estados de interacción

**Objetivo**
- Subir el estándar profesional sin cambiar estética base.

**Trabajo**
- `aria-live`, `role=status`, `role=alert`
- mejor foco visible en acciones
- textos auxiliares coherentes
- estados de mantenimiento y feedback más claros

**Validación**
- Checklist de accesibilidad básica en DOM
- revisión manual de navegación y feedback

**Impacto esperado**
- +0.3 a +0.5 puntos

### Fase 5. Modularización interna sin romper el despliegue actual

**Objetivo**
- Reducir el riesgo estructural del archivo monolítico.

**Trabajo**
- extraer helpers de render y view-models a módulos JS locales servidos por `8090`, o al menos a secciones claramente encapsuladas dentro del HTML actual
- centralizar transformaciones de datos de UI
- reducir duplicación de markup repetido

**Validación**
- menor duplicación visible
- tests actualizados
- dashboard funcional idéntico para el operador

**Impacto esperado**
- +0.5 a +0.8 puntos

### Fase 6. Responsive y pulido visual senior

**Objetivo**
- Llevar la experiencia al nivel de un dashboard sólido también fuera de escritorio ancho.

**Trabajo**
- puntos de quiebre reales
- tablas con degradación controlada
- grids más robustos
- menor densidad cognitiva en pantallas medianas

**Validación**
- revisión manual desktop + ancho reducido

**Impacto esperado**
- +0.3 a +0.5 puntos

## Limitaciones reales que no puedo superar solo desde el frontend

### 1. El dashboard no puede ser más verdadero que sus fuentes canónicas

Si un endpoint mezcla conceptos o no expone un campo, la UI solo puede:
- explicitar el límite
- degradar bien
- evitar fingir exactitud

Pero no puede inventar una métrica correcta.

### 2. Parte de la nota depende del backend semántico

Ejemplos:
- qué significa exactamente `effective_u_score`
- cuándo una estrategia es `execution_ready`
- qué cuenta como `trade`, `position`, `activity`, `resolved sample`

Eso depende del contrato del runtime, no solo del render.

### 3. El despliegue actual embebido en un HTML único tiene techo arquitectónico

Puedo dejarlo mucho más limpio y menos frágil, pero no llega a excelencia estructural total sin:
- extraer módulos
- introducir build mínimo
- separar claramente data layer y presentation layer

Mientras sigamos en un solo archivo gigante, hay un límite de mantenibilidad.

### 4. No puedo validar UX con usuarios reales dentro de esta sesión

Puedo aplicar criterio senior, consistencia y pruebas técnicas, pero no sustituye:
- observación de uso real
- feedback de operador
- iteración con métricas de interacción

## Orden de ejecución acordado para esta sesión

1. Fase 1 completa
2. Validación + documentación
3. Revisión visible en `8090`
4. Si queda tiempo en esta sesión: entrar a Fase 2 en `Overview`

## Criterio de no-regresión

Ningún cambio de frontend debe:
- alterar lógica operativa del Brain
- introducir datos inventados
- ocultar incertidumbre real
- chocar con el trabajo paralelo sobre PO/IBKR
