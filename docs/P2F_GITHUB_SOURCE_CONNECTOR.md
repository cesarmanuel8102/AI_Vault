# P2-F GitHub Source Connector

## Objetivo

Implementar un conector read-only/dry-run para fuentes GitHub que permita inspeccionar repositorios sin escribir a SemanticMemory y sin usar APIs de escritura de GitHub.

## Modo de Operación

**SIEMPRE DRY-RUN**: El conector nunca escribe datos. Solo inspecciona y produce evidence bundles.

### Constantes de Seguridad (Hardcoded)

```python
GITHUB_WRITE_ALLOWED = False        # SIEMPRE False
SEMANTIC_WRITE_ALLOWED = False      # SIEMPRE False
PROMOTION_ALLOWED = False           # SIEMPRE False
DRY_RUN_ONLY = True                 # SIEMPRE True
```

## Arquitectura

### Componentes

1. **`brain/github_source_connector.py`** - Core del conector
2. **`tests/unit/test_github_source_connector.py`** - Tests unitarios
3. **`tests/smoke/smoke_github_source_connector_dry_run.py`** - Validación dry-run

### Flujo de Datos

```
GitHub API (tree endpoint)
    ↓
GitHubSourceConnector
    ↓
GitHubEvidenceBundle
    ↓
(NO SemanticMemory)
```

## API GitHub Utilizada

- **Endpoint**: `GET /repos/{owner}/{repo}/git/trees/{branch}?recursive=1`
- **Método**: Solo lectura (tree recursivo)
- **Autenticación**: Opcional, via `GITHUB_TOKEN` env var
- **Rate Limit**: 60 req/hr (público) / 5000 req/hr (autenticado)

## Evidence Bundle

El bundle contiene:

```python
{
    "source_type": "github",
    "repo": "owner/repo",
    "branch": "branch-name",
    "commit": "abc123...",
    "fetched_at_utc": "2026-05-24T17:00:00Z",
    "files_seen": 150,
    "files_selected": ["brain/main.py", "docs/guide.md"],
    "selected_file_git_shas": {
        "brain/main.py": "abc123...",  # Git blob SHA desde GitHub API
        "docs/guide.md": "def456..."
    },
    "selected_file_content_sha256": {
        "brain/main.py": "sha256:..."  # SHA-256 calculado localmente (solo si se recibió contenido real)
    },
    "promotion_allowed": False,          # SIEMPRE False
    "semantic_write_allowed": False,     # SIEMPRE False
    "dry_run": True,                     # SIEMPRE True
    "token_mode": "none" | "env",
    "errors": [],
}
```

**Nota sobre Hashes:**

- **`selected_file_git_shas`**: Git blob SHA proporcionado por GitHub API tree. Identifica el blob en el repositorio Git.
- **`selected_file_content_sha256`**: SHA-256 calculado localmente del contenido del archivo. **Solo existe si se recibió contenido real** (vía `file_payloads`). Si el archivo excede `max_bytes_per_file`, no se calcula content_sha256 para evitar hashes de contenido truncado.

Estos son conceptos diferentes:
- Git SHA identifica el blob en el repo de Git
- Content SHA-256 es el hash criptográfico del contenido real del archivo

## Seguridad de Token

- Token leído únicamente de variable de entorno `GITHUB_TOKEN`
- Token nunca logueado (se enmascara: `ghp_***cdef`)
- Token nunca incluido en evidence bundle
- Modo público funciona sin token (rate limit más bajo)

## Filtros de Archivos

### Inclusión (include_globs)
- `*.py` - Archivos Python
- `*.md` - Documentación Markdown
- `*.json` - Configuraciones JSON
- `*.yaml`, `*.yml` - Configuraciones YAML

### Exclusión (exclude_globs)
- `node_modules/*` - Dependencias Node
- `.git/*` - Metadata Git
- `__pycache__/*` - Cache Python
- `*.pyc` - Bytecode Python

## Tests

### Unit Tests

```bash
cd /c/AI_VAULT
python -m pytest tests/unit/test_github_source_connector.py -v
```

Tests incluidos:
- Constantes de seguridad son correctas
- Masking de token no expone secretos
- Selección de archivos por glob patterns
- Construcción de URLs de API
- Manejo de errores HTTP
- Construcción de evidence bundles

### Smoke Test

```bash
cd /c/AI_VAULT
python tests/smoke/smoke_github_source_connector_dry_run.py
```

Valida:
- Ejecución dry-run completa
- Security flags son correctos
- NO escritura a SemanticMemory
- Evidence bundle es válido
- Filtros de inclusión/exclusión funcionan

## Uso

### Ejemplo Básico

```python
from brain.github_source_connector import (
    GitHubSourceRequest,
    GitHubSourceConnector,
)

# Crear request
request = GitHubSourceRequest(
    owner="cesarmanuel8102",
    repo="AI_Vault",
    branch="codex/own-capital-sustainable-return",
    include_globs=("*.py", "*.md"),
    exclude_globs=("node_modules/*", "__pycache__/*"),
    max_files=50,
)

# Ejecutar dry-run
connector = GitHubSourceConnector()
bundle = connector.inspect(request)

# Verificar bundle
assert bundle.promotion_allowed is False
assert bundle.semantic_write_allowed is False
print(f"Files selected: {len(bundle.files_selected)}")
```

### Ejemplo con Fake Opener (Testing)

```python
from brain.github_source_connector import (
    GitHubSourceRequest,
    run_github_source_dry_run,
)

request = GitHubSourceRequest(
    owner="testowner",
    repo="testrepo",
    branch="main",
)

# Usar fake opener para testing
fake_opener = FakeOpener({"sha": "abc123", "tree": []})
bundle = run_github_source_dry_run(request, opener=fake_opener)
```

## Limitaciones

- Solo lectura de tree (no descarga contenido de archivos por defecto)
- Rate limit de GitHub API
- No soporta autenticación via archivo de config (solo env var)
- No cache de respuestas (cada llamada es fresh)

## Próximos Pasos

1. **Live API Testing**: Validar contra API real de GitHub
2. **Content Download**: Opción para descargar contenido de archivos
3. **Caching**: Implementar cache de responses
4. **Pagination**: Manejar trees grandes (>100k archivos)
5. **Integration**: Conectar con P2-E evidence system para decisión de promoción

## Estado

**Implementado**: Core del conector, tests unitarios, smoke test
**Pendiente**: Validación contra API real, integración con evidence system

---

*P2-F GitHubSourceConnector - Read-only/Dry-run Mode*
