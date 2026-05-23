"""
Tests for CuratedMemoryPromotion — brain/curated_memory_promotion.py

Valida promoción gobernada de conocimiento curado a memoria semántica.
Todos los tests usan modo dry-run (nunca escriben memoria real).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from brain.curated_memory_promotion import (
    CuratedMemoryPromotionService,
    CuratedMemoryPromotionPlan,
    PromotionStatus,
    create_curated_memory_promotion_service,
)
from brain.information_curator import InformationCurator, ContentTopic
from brain.curation_validation_adapter import (
    CurationValidationResult,
    CurationValidationStatus,
)


class TestCuratedMemoryPromotion:
    """Tests para CuratedMemoryPromotionService."""
    
    @staticmethod
    def _create_validated_record():
        """Helper: Crear record validado usando InformationCurator."""
        curator = InformationCurator()
        return curator.ingest_text(
            "Python es un lenguaje de programación de alto nivel.",
            source="test_docs",
            topic=ContentTopic.TECHNOLOGY,
        )
    
    @staticmethod
    def _create_validation_result(record, status=CurationValidationStatus.VALIDATED, score=0.85):
        """Helper: Crear CurationValidationResult."""
        return CurationValidationResult(
            record_id=record.record_id,
            content_hash=record.content_hash,
            source=record.source,
            topic=str(record.topic) if hasattr(record, 'topic') else "general",
            status=status,
            validator_status=status.value,
            passed=(status == CurationValidationStatus.VALIDATED),
            score=score,
            reason="Validation passed" if status == CurationValidationStatus.VALIDATED else "Low quality",
            validation_id=f"test_validation_{status.value}",
        )
    
    def test_validated_record_produces_dry_run_plan(self):
        """Un record validado produce plan de promoción dry-run."""
        service = create_curated_memory_promotion_service()
        record = self._create_validated_record()
        validation_result = self._create_validation_result(record)
        
        plan = service.promote_dry_run(record, validation_result)
        
        assert plan.record_id == record.record_id
        assert plan.dry_run is True
        assert plan.validation_score == 0.85
        assert plan.status in [PromotionStatus.ELIGIBLE, PromotionStatus.REQUIRES_APPROVAL]
        assert plan.memory_payload is not None
    
    def test_rejected_record_cannot_promote(self):
        """Un record rechazado no puede ser promovido."""
        service = create_curated_memory_promotion_service()
        record = self._create_validated_record()
        validation_result = self._create_validation_result(
            record, 
            status=CurationValidationStatus.REJECTED, 
            score=0.3
        )
        
        plan = service.promote_dry_run(record, validation_result)
        
        assert plan.status == PromotionStatus.REJECTED_NOT_VALIDATED
        assert plan.memory_payload is None
        assert plan.rejection_reason is not None
    
    def test_unvalidated_record_cannot_promote(self):
        """Un record sin validar no puede ser promovido."""
        service = create_curated_memory_promotion_service()
        record = self._create_validated_record()
        validation_result = self._create_validation_result(
            record,
            status=CurationValidationStatus.UNVALIDATED,
            score=0.0
        )
        
        plan = service.promote_dry_run(record, validation_result)
        
        assert plan.status == PromotionStatus.REJECTED_NOT_VALIDATED
        assert plan.memory_payload is None
    
    def test_low_score_record_is_rejected(self):
        """Un record con score bajo es rechazado."""
        service = create_curated_memory_promotion_service(min_validation_score=0.7)
        record = self._create_validated_record()
        validation_result = self._create_validation_result(
            record,
            status=CurationValidationStatus.VALIDATED,
            score=0.5  # Por debajo de 0.7
        )
        
        plan = service.promote_dry_run(record, validation_result)
        
        assert plan.status == PromotionStatus.REJECTED_LOW_SCORE
        assert plan.memory_payload is None
        assert "score" in plan.rejection_reason.lower()
    
    def test_missing_traceability_is_rejected(self):
        """Falta de trazabilidad causa rechazo."""
        service = create_curated_memory_promotion_service()
        
        # Crear record normal y luego modificar para simular falta de trazabilidad
        record = self._create_validated_record()
        record.source = ""  # Eliminar source para simular falta de trazabilidad
        
        validation_result = self._create_validation_result(record)
        
        plan = service.promote_dry_run(record, validation_result)
        
        assert plan.status == PromotionStatus.REJECTED_MISSING_TRACEABILITY
        assert "source" in plan.rejection_reason.lower() or "traceability" in plan.rejection_reason.lower()
    
    def test_dry_run_never_writes(self):
        """promote_dry_run nunca escribe archivos ni modifica estado externo."""
        service = create_curated_memory_promotion_service()
        record = self._create_validated_record()
        validation_result = self._create_validation_result(record)
        
        # Ejecutar múltiples veces - no debe haber efectos secundarios
        plan1 = service.promote_dry_run(record, validation_result)
        plan2 = service.promote_dry_run(record, validation_result)
        
        assert plan1.dry_run is True
        assert plan2.dry_run is True
        assert plan1.memory_payload == plan2.memory_payload  # Idempotente
    
    def test_promotion_payload_contains_provenance(self):
        """El payload incluye provenance completo."""
        service = create_curated_memory_promotion_service()
        record = self._create_validated_record()
        validation_result = self._create_validation_result(record)
        
        plan = service.promote_dry_run(record, validation_result)
        
        assert plan.memory_payload is not None
        metadata = plan.memory_payload.get("metadata", {})
        assert "provenance" in metadata
        provenance = metadata["provenance"]
        assert provenance.get("ingested_by") == "InformationCurator"
        assert provenance.get("validated_by") == "CurationValidationAdapter"
        assert "tags" in metadata
        assert "curated" in metadata["tags"]
        assert "validated" in metadata["tags"]
    
    def test_promotion_requires_explicit_approval(self):
        """La promoción requiere aprobación explícita cuando require_approval=True."""
        service = create_curated_memory_promotion_service(require_approval=True)
        record = self._create_validated_record()
        validation_result = self._create_validation_result(record)
        
        plan = service.promote_dry_run(record, validation_result)
        
        assert plan.status == PromotionStatus.REQUIRES_APPROVAL
        assert plan.governance_required is True
        assert plan.dry_run is True  # No ejecutado aún
    
    def test_module_does_not_import_faiss_or_semantic_memory(self):
        """El módulo no importa FAISS ni SemanticMemory."""
        import ast
        
        provider_path = Path(__file__).parent.parent.parent / "brain" / "curated_memory_promotion.py"
        source = provider_path.read_text()
        tree = ast.parse(source)
        
        forbidden_imports = [
            "faiss",
            "semantic_memory",
            "semantic_memory_faiss",
            "SemanticMemoryBridge",
            "_do_ingest",
        ]
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    for forbidden in forbidden_imports:
                        assert forbidden not in alias.name.lower(), \
                            f"Import prohibido detectado: {alias.name}"
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    for forbidden in forbidden_imports:
                        assert forbidden not in node.module.lower(), \
                            f"Import prohibido detectado: {node.module}"
    
    def test_module_does_not_use_direct_file_or_http_writes(self):
        """El módulo no usa escritura directa a archivos ni HTTP."""
        import ast
        
        provider_path = Path(__file__).parent.parent.parent / "brain" / "curated_memory_promotion.py"
        source = provider_path.read_text()
        tree = ast.parse(source)
        
        forbidden_calls = [
            "open(",
            "write_text",
            "append",
            "requests.post",
            "httpx.post",
            "urllib.request",
        ]
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                # Verificar llamadas a funciones
                if isinstance(node.func, ast.Name):
                    func_name = node.func.id
                    for forbidden in forbidden_calls:
                        if forbidden in func_name.lower():
                            # Permitir 'open' solo si es para leer (no 'w' mode)
                            if func_name == "open":
                                # Chequear si hay modo escritura
                                if len(node.args) > 1:
                                    first_arg = node.args[1]
                                    if isinstance(first_arg, ast.Constant) and isinstance(first_arg.value, str):
                                        if 'w' in first_arg.value or 'a' in first_arg.value:
                                            assert False, f"open() con modo escritura detectado"
                            else:
                                assert False, f"Llamada prohibida detectada: {func_name}"


class TestCuratedMemoryPromotionPayload:
    """Tests específicos del payload de memoria."""
    
    @staticmethod
    def _create_test_record():
        """Helper: Crear record de prueba."""
        curator = InformationCurator()
        return curator.ingest_text(
            "Test content for payload structure validation.",
            source="test_payload",
            topic=ContentTopic.GENERAL,
        )
    
    @staticmethod
    def _create_validation_result(record):
        """Helper: Crear validation result válido."""
        return CurationValidationResult(
            record_id=record.record_id,
            content_hash=record.content_hash,
            source=record.source,
            topic=str(record.topic) if hasattr(record, 'topic') else "general",
            status=CurationValidationStatus.VALIDATED,
            validator_status="VALIDATED",
            passed=True,
            score=0.85,
            reason="Test validation",
            validation_id="test_payload_validation",
        )
    
    def test_payload_structure(self):
        """El payload tiene estructura correcta."""
        service = create_curated_memory_promotion_service()
        record = self._create_test_record()
        validation_result = self._create_validation_result(record)
        
        payload = service.build_memory_payload(record, validation_result)
        
        assert "text" in payload
        assert "source" in payload
        assert "session_id" in payload
        assert "kind" in payload
        assert "metadata" in payload
        
        metadata = payload["metadata"]
        assert "record_id" in metadata
        assert "content_hash" in metadata
        assert "topic" in metadata
        assert "validation_status" in metadata
        assert "validation_score" in metadata
        assert "promotion_policy" in metadata
        assert "provenance" in metadata
    
    def test_source_prefixing(self):
        """El source tiene prefijo 'curated:'."""
        service = create_curated_memory_promotion_service()
        curator = InformationCurator()
        record = curator.ingest_text(
            "Test for source prefixing",
            source="github:microsoft/autogen",
            topic=ContentTopic.AI_ML,
        )
        validation_result = self._create_validation_result(record)
        
        payload = service.build_memory_payload(record, validation_result)
        
        assert payload["source"].startswith("curated:")
        assert record.source in payload["source"]
    
    def test_promotion_policy_tag(self):
        """El payload incluye tag de política P2-E."""
        service = create_curated_memory_promotion_service()
        record = self._create_test_record()
        validation_result = self._create_validation_result(record)
        
        payload = service.build_memory_payload(record, validation_result)
        
        assert payload["metadata"]["promotion_policy"] == "P2-E"
        assert "p2e_dry_run" in payload["metadata"]["tags"]
