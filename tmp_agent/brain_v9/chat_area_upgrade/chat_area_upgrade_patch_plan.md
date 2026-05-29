# CHAT-A Brain Chat V9 — Chat Area UX Upgrade Patch Plan

## Scope
Solo el área de conversación del tab Chat en Brain Chat V9. No se toca Agent Workspace, tabs, backend ni endpoints.

## Archivo
`tmp_agent/brain_v9/ui/index.html` — single file con CSS + JS embebidos.

## Estado actual (resumen)
- Render de mensajes: `renderMarkdown()` regex inline (código, bold, newlines). No hay `marked`, `DOMPurify`, `highlight.js`.
- Streaming: NO existe. Backend devuelve JSON completo. `addTyping()` solo muestra puntos mientras espera respuesta.
- Tool results: solo renderizados inline dentro del texto o dentro de approval/tool01 cards. No hay collapsible block genérico.
- CSS chat: todo embebido en `<style>`. Clases: `.msg`, `.bubble`, `.avatar`, `.meta`, `.typing`.

## Cambios SAFE_NOW (propuestos para CHAT-A patch)

### 1. Markdown mejorado (sin librería nueva)
Ampliar `renderMarkdown()` para soportar:
- Headers `#`, `##`, `###` → `<h1>`, `<h2>`, `<h3>` con estilos scoped
- Listas `- item` y `* item` → `<ul><li>`
- Tablas markdown simples → `<table>`
- Bloques de código con fondo `#0d1117`
- Inline code con fondo `#24283b`

### 2. Copy button en bloques de código
Añadir un pequeño botón absoluto dentro de cada `<pre>` (usar CSS `:hover` + JS). No depende de librería.

### 3. Estilo mensajes Brain
- Quitar burbuja para messages `agent`
- Texto fluido, fondo transparente
- Avatar `B` con color `#7c6af7`
- Alinear a la izquierda

### 4. Mensajes sistema
- Centrados horizontalmente
- Sin avatar
- Color texto `#666`
- Sin burbuja
- Fuente más pequeña, estilo informativo

### 5. Empty state
Insertar HTML estático dentro del `<div id="messages">` al cargar:
- Logo B grande
- Texto "Brain Chat V9"
- 3 botones sugeridos clickeables:
  - "¿Cuál es el estado del sistema?"
  - "Muestra los últimos resultados de investigación"
  - "Ejecuta git status"
- Ocultar empty state en el primer mensaje real

### 6. Auto-scroll + scroll-down button
- Scroll automático al enviar mensaje
- Si el usuario scrollea hacia arriba, mostrar botón "↓ Bajar"
- Al hacer clic, vuelve al final y oculta el botón

### 7. Input bar mejoras menores
- Placeholder: "Escribe a Brain..."
- Ícono de clip (visual placeholder, no función)
- Ajustar `autoResize` para expandir hasta ~5 líneas (~120px altura)

## Cambios DEFERRED (requieren backend o dependencias nuevas)

### Streaming con cursor real
Razón: Backend `/chat` y `/agent` devuelven JSON completo. No hay SSE de texto. Para streaming real, necesitaría:
- Backend endpoint que emita chunks (`/chat/stream`)
- Frontend handler de SSE o fetch con ReadableStream

### Tool collapsible blocks estructurados
Razón: Backend no devuelve tool results como objetos estructurados. Solo texto. Requiere:
- Cambio en respuesta JSON de `/agent` y `/chat` para incluir `tool_results: [{tool, output}]`
- O parsing desde texto (fragile)

### Syntax highlighting real
Razón: No hay librería cargada. Opciones:
- Cargar `highlight.js` desde CDN (increases trust boundary)
- Implementar mapeo mínimo de keywords para ~5 lenguajes
- Recomendación: DEFER hasta evaluación de seguridad de CDN

## Zonas específicas a tocar en index.html

### CSS (líneas ~78-280 aprox)
1. `.bubble` — quitar para `.msg.agent`, mantener para `.msg.user`
2. `.msg.agent` — estilo flat
3. `.msg.system` — centrado, sin avatar, gris
4. `.typing` — añadir cursor parpadeante (pseudo-elemento)
5. `.pre` — estilo código block, copiar botón
6. `@keyframes` — cursor blink

### JS (líneas ~855-910 aprox)
1. `renderMarkdown()` — ampliar regex
2. `addMsg()` — condicionar estructura HTML según rol
3. `autoResize()` — ajustar límite de altura
4. Nueva función `showScrollDownBtn()` / `hideScrollDownBtn()`
5. Nuevas funciones sugeridas para empty state

## Riesgo de romper tabs/workspace
**Bajo.** Todas las clases `.msg.*` y `#panel-chat` son scoped. Las otras tabs usan `#panel-platforms`, `#panel-status`, etc. No hay colisión.

## Rollback Plan
Si el patch introduce regresión:
1. Revertir commit CHAT-A
2. Restaurar `tmp_agent/brain_v9/ui/index.html` al estado previo (HEAD antes de CHAT-A)
3. Verificar que otras tabs siguen funcionando
4. Re-ejecutar smoke manual: enviar mensaje, verificar respuesta, tabs

## Tests manual recomendados
1. Enviar mensaje simple → ver burbuja usuario OK, respuesta agente sin burbuja
2. Enviar mensaje con markdown → verificar que se ve bold/code/listas
3. Enviar mensaje con código block → verificar Copy button y fondo #0d1117
4. Scrollear arriba → verificar botón "↓ Bajar" aparece
5. Clic en sugerencia empty state → vaciarse y enviar mensaje
6. Cambiar tab a Platforms → volver a Chat → estado intacto
7. Verificar System messages centrados/gris sin avatar

## Tests automatizables
Si se desea en CHAT-B:
- Puppeteer/Playwright: screenshot diff del tab Chat
- Test textual: verificar que `renderMarkdown('# title')` produce `<h1>title</h1>`

## Prompt para CHAT-B patch recomendado
"Aplica el CHAT-A patch plan en tmp_agent/brain_v9/ui/index.html. Solo CSS + JS embebido. No backend. Confirma visualmente mediante screenshot o smoke test que las tabs no se rompen y el chat mantiene funcionalidad.

## Archivos creados en esta fase
- `tmp_agent/brain_v9/chat_area_upgrade/chat_area_upgrade_audit.json`
- `tmp_agent/brain_v9/chat_area_upgrade/chat_area_upgrade_patch_plan.md`
