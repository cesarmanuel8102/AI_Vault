"""
Curated Runtime Lookup — Read-Only.

Puro/offline: sin imports de runtime, sin escritura a semantic memory,
sin FAISS writes, sin real adapter, sin bridge.
Solo lectura de un índice separado de candidatos curated/verificados.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence
import hashlib
import json
import re


LOOKUP_VERSION = "1.0-readonly"
REAL_WRITE_ALLOWED = False
FAISS_WRITE_ALLOWED = False

ALLOWED_STATES_FOR_LOOKUP = frozenset({
    "dry_run_verified",
    "ready_for_readonly_runtime_lookup",
})

FORBIDDEN_STATES_FOR_LOOKUP = frozenset({
    "discovered",
    "extracted",
    "normalized",
    "curated_candidate",
    "validated_candidate",
    "promotion_plan_created",
    "approval_required",
    "approved_for_dry_run",
    "blocked",
    "rejected",
    "deprecated",
    "promoted_real_write",
    "active_write",
})

DEFAULT_LOOKUP_INDEX_PATH = Path("tmp_agent/state/curated_learning/readonly_lookup_index.jsonl")
DEFAULT_FRESHNESS_DAYS = 30
DEFAULT_TOP_K = 5
DEFAULT_MIN_VALIDATION_SCORE = 0.75
DEFAULT_MIN_CURATION_SCORE = 0.70


# ── Excepciones ────────────────────────────────────────────────────────────

class LookupError(Exception):
    """Base para errores de lookup."""


class LookupWriteAttemptBlocked(LookupError):
    """Se detectó un intento de escritura (fail-closed)."""


class InvalidLookupState(LookupError):
    """Estado de candidato no permitido para lookup."""


class MissingProvenance(LookupError):
    """Registro sin provenance bundle."""


class StaleLookupRecord(LookupError):
    """Registro más viejo que freshness_days."""


class EmptyLookupIndex(LookupError):
    """Índice vacío o no encontrado."""


class MissingProvenanceField(LookupError):
    """Provenance bundle incompleto."""


# ── Dataclasses ───────────────────────────────────────────────────────────

@dataclass(frozen=True)
class CuratedLookupQuery:
    text: str
    allowed_states: tuple[str, ...] = ("ready_for_readonly_runtime_lookup",)
    top_k: int = DEFAULT_TOP_K
    min_validation_score: float = DEFAULT_MIN_VALIDATION_SCORE
    min_curation_score: float = DEFAULT_MIN_CURATION_SCORE
    require_provenance: bool = True
    freshness_days: int = DEFAULT_FRESHNESS_DAYS
    include_stale: bool = False


@dataclass(frozen=True)
class CuratedLookupResult:
    candidate_id: str
    state: str
    text: str
    source_id: str
    evidence_refs: tuple[str, ...]
    provenance_bundle: Mapping[str, Any]
    validation_score: float
    curation_score: float
    trust_score: float
    freshness: str
    dry_run_id: str
    created_at: str
    label: str = "verified_curated_readonly"
    is_stale: bool = False


@dataclass(frozen=True)
class CuratedLookupRecord:
    query: CuratedLookupQuery
    results: tuple[CuratedLookupResult, ...]
    total_available: int
    filtered_out: int
    lookup_id: str = field(default_factory=lambda: _make_id("lookup"))
    timestamp_utc: str = field(default_factory=lambda: _now_utc())


@dataclass(frozen=True)
class CuratedLookupDecision:
    allow_lookup: bool
    reason_codes: tuple[str, ...] = ()
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CuratedLookupSourceRef:
    source_type: str
    path: str
    checksum: str
    created_at: str


# ── Helpers privados ────────────────────────────────────────────────────────

def _now_utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _make_id(prefix: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    return f"{prefix}_{ts}"


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _is_stale(freshness_iso: str, days: int) -> bool:
    try:
        then = datetime.fromisoformat(freshness_iso)
        now = datetime.now(timezone.utc)
        return (now - then).days > days
    except Exception:
        return True  # fail-closed: si no parsea, es stale


# ── Seguridad: assert_read_only ─────────────────────────────────────────────

def assert_lookup_is_read_only() -> None:
    """Fail-closed: verifica que no hay funciones de escritura ni imports prohibidos."""
    import sys
    mod = sys.modules[__name__]
    forbidden_names = {
        "write_index", "add_record", "delete_record", "update_record",
        "ingest_text", "add_memory", "write_text", "open_write",
    }
    for name in forbidden_names:
        if hasattr(mod, name):
            raise LookupWriteAttemptBlocked(
                f"Forbidden write function detected in curated_runtime_lookup: {name}"
            )


def verify_lookup_does_not_import_semantic_writers() -> CuratedLookupDecision:
    """Verifica que el módulo no importa semantic writers."""
    import sys
    mod = sys.modules[__name__]
    source = getattr(mod, "__file__", "")
    if not source:
        return CuratedLookupDecision(
            allow_lookup=False,
            reason_codes=("missing_source_file",),
        )
    try:
        text = Path(source).read_text(encoding="utf-8")
    except Exception as e:
        return CuratedLookupDecision(
            allow_lookup=False,
            reason_codes=("cannot_read_source",),
            details={"error": str(e)},
        )
    # Buscar import statements reales (líneas que empiezan con import/from)
    import_lines = [l.strip() for l in text.splitlines() if l.strip().startswith(("import ", "from "))]
    forbidden_patterns = [
        "semantic_memory_adapter_real",
        "semantic_memory_bridge",
        "SemanticMemoryFAISS",
        "ingest_text",
        "from brain.semantic_memory_real",
        "import semantic_memory_real",
    ]
    found = []
    for line in import_lines:
        for pattern in forbidden_patterns:
            if pattern in line:
                found.append((pattern, line))
                break
    if found:
        return CuratedLookupDecision(
            allow_lookup=False,
            reason_codes=("forbidden_import_detected",),
            details={"patterns_found": [f"{p} in: {line}" for p, line in found]},
        )
    return CuratedLookupDecision(allow_lookup=True)


# ── Carga de índice ─────────────────────────────────────────────────────────

def load_curated_lookup_index(
    index_path: Path | str | None = None,
) -> tuple[CuratedLookupResult, ...]:
    """Carga índice read-only desde JSONL."""
    path = Path(index_path) if index_path else DEFAULT_LOOKUP_INDEX_PATH
    if not path.exists():
        return ()
    results = []
    for line in path.read_text(encoding="utf-8").strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue  # skip corrupt lines
        try:
            result = _parse_index_record(record)
            results.append(result)
        except (InvalidLookupState, MissingProvenance, MissingProvenanceField):
            continue  # skip invalid records
    return tuple(results)


def _parse_index_record(record: dict[str, Any]) -> CuratedLookupResult:
    state = record.get("state", "")
    if state in FORBIDDEN_STATES_FOR_LOOKUP:
        raise InvalidLookupState(f"State {state!r} is forbidden for lookup")
    if state not in ALLOWED_STATES_FOR_LOOKUP:
        raise InvalidLookupState(f"State {state!r} is not allowed for lookup")
    provenance = record.get("provenance_bundle") or {}
    if not provenance:
        raise MissingProvenance("provenance_bundle is missing")
    required_provenance_fields = ("source_type", "source_uri", "curation_score", "validation_score")
    missing = [f for f in required_provenance_fields if f not in provenance]
    if missing:
        raise MissingProvenanceField(f"Missing provenance fields: {missing}")
    evidence_refs = record.get("evidence_refs", [])
    if isinstance(evidence_refs, str):
        evidence_refs = [evidence_refs]
    return CuratedLookupResult(
        candidate_id=record.get("candidate_id", ""),
        state=state,
        text=record.get("text", ""),
        source_id=record.get("source_id", ""),
        evidence_refs=tuple(evidence_refs),
        provenance_bundle=provenance,
        validation_score=float(record.get("validation_score", 0.0)),
        curation_score=float(record.get("curation_score", 0.0)),
        trust_score=float(record.get("trust_score", 0.0)),
        freshness=record.get("freshness", ""),
        dry_run_id=record.get("dry_run_id", ""),
        created_at=record.get("created_at", ""),
        is_stale=_is_stale(record.get("freshness", ""), DEFAULT_FRESHNESS_DAYS),
    )


# ── Búsqueda / filtrado ─────────────────────────────────────────────────────

def search_curated_candidates(
    query_text: str,
    index_path: Path | str | None = None,
    allowed_states: tuple[str, ...] | None = None,
    top_k: int = DEFAULT_TOP_K,
    min_validation_score: float = DEFAULT_MIN_VALIDATION_SCORE,
    min_curation_score: float = DEFAULT_MIN_CURATION_SCORE,
    require_provenance: bool = True,
    freshness_days: int = DEFAULT_FRESHNESS_DAYS,
    include_stale: bool = False,
) -> CuratedLookupRecord:
    """Busca candidatos curated que cumplan filtros."""
    query = CuratedLookupQuery(
        text=query_text,
        allowed_states=allowed_states or ("ready_for_readonly_runtime_lookup",),
        top_k=top_k,
        min_validation_score=min_validation_score,
        min_curation_score=min_curation_score,
        require_provenance=require_provenance,
        freshness_days=freshness_days,
        include_stale=include_stale,
    )
    all_records = load_curated_lookup_index(index_path)
    if not all_records:
        return CuratedLookupRecord(
            query=query,
            results=(),
            total_available=0,
            filtered_out=0,
        )
    filtered = filter_lookup_records(
        all_records,
        allowed_states=query.allowed_states,
        min_validation_score=query.min_validation_score,
        min_curation_score=query.min_curation_score,
        require_provenance=query.require_provenance,
        freshness_days=query.freshness_days,
        include_stale=query.include_stale,
    )
    total_available = len(all_records)
    filtered_out = total_available - len(filtered)
    # Simple ranking: validation_score desc, then curation_score desc
    ranked = sorted(
        filtered,
        key=lambda r: (r.validation_score, r.curation_score, r.trust_score),
        reverse=True,
    )
    top_results = tuple(ranked[: top_k])
    return CuratedLookupRecord(
        query=query,
        results=top_results,
        total_available=total_available,
        filtered_out=filtered_out,
    )


def filter_lookup_records(
    records: Sequence[CuratedLookupResult],
    allowed_states: tuple[str, ...] | None = None,
    min_validation_score: float = DEFAULT_MIN_VALIDATION_SCORE,
    min_curation_score: float = DEFAULT_MIN_CURATION_SCORE,
    require_provenance: bool = True,
    freshness_days: int = DEFAULT_FRESHNESS_DAYS,
    include_stale: bool = False,
) -> list[CuratedLookupResult]:
    """Filtra registros según criterios de seguridad."""
    allowed = frozenset(allowed_states or ALLOWED_STATES_FOR_LOOKUP)
    out = []
    for rec in records:
        if rec.state not in allowed:
            continue
        if rec.validation_score < min_validation_score:
            continue
        if rec.curation_score < min_curation_score:
            continue
        if require_provenance and (not rec.provenance_bundle or not rec.provenance_bundle.get("source_type")):
            continue
        if not include_stale and rec.is_stale:
            continue
        out.append(rec)
    return out


# ── Formateo para chat ──────────────────────────────────────────────────────

def format_curated_lookup_for_chat(record: CuratedLookupRecord) -> str:
    """Formatea resultados para mostrar en chat."""
    if not record.results:
        return "[verified_curated_readonly]\n\nNo se encontró conocimiento curado para esta consulta."
    lines = [
        "[verified_curated_readonly]",
        "",
        f"Resultados encontrados: {len(record.results)} (de {record.total_available} disponibles, {record.filtered_out} filtrados)",
        "",
    ]
    for i, res in enumerate(record.results, 1):
        stale_note = " [STALE]" if res.is_stale else ""
        lines.append(
            f"{i}. [Source: {res.source_id} | Validation: {res.validation_score:.2f} | Curation: {res.curation_score:.2f}]{stale_note}"
        )
        lines.append(f"   {res.text[:200]}{'...' if len(res.text) > 200 else ''}")
        lines.append(f"   Evidence: {', '.join(res.evidence_refs) or 'N/A'}")
        lines.append("")
    lines.append("---")
    lines.append(
        "Estos resultados provienen de conocimiento curado y verificado mediante dry-run. "
        "No han sido promovidos a escritura real."
    )
    return "\n".join(lines)


# ── Inicialización de seguridad ─────────────────────────────────────────────

assert_lookup_is_read_only()
