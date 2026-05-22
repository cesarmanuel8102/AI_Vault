"""Test P2-A: Contrato de InformationCurator - Ingesta curada.

Este test verifica que InformationCurator cumple con el contrato P2-A:
- Todo conocimiento nuevo entra como UNVALIDATED (o sin marcar como validado)
- Preserva metadata/fuente
- Detecta duplicados
- Detecta contradicciones
- Calcula quality score
- No toca SemanticMemoryBridge
- No escribe en estado real (usa tmp_path)
"""

import sys
import inspect
import pytest
from pathlib import Path

sys.path.insert(0, r"C:\AI_VAULT\brain")

from information_curator import (
    InformationCurator,
    CuratedRecord,
    ContentTopic,
    QualityLevel,
)


class TestInformationCuratorContract:
    """Tests de contrato P2-A para InformationCurator."""

    def test_ingesta_basica_crea_record(self, tmp_path):
        """1. Ingesta básica: entrada simple → registro curado."""
        curator = InformationCurator(storage_path=str(tmp_path / "curator.json"))
        text = "Este es un texto técnico sobre Python y machine learning para testing."

        record = curator.ingest_text(text, source="test")

        assert isinstance(record, CuratedRecord)
        assert record.record_id.startswith("rec_")
        assert record.content == text
        assert record.source == "test"

    def test_fuente_metadata_preservada(self, tmp_path):
        """2. Fuente/metadata: entrada con source → metadata preservada."""
        curator = InformationCurator(storage_path=str(tmp_path / "curator.json"))
        text = "Contenido con fuente específica."
        custom_source = "source:documento_test"

        record = curator.ingest_text(text, source=custom_source)

        assert record.source == custom_source
        assert record.metadata.get("original_length") == len(text)
        assert record.content_hash is not None

    def test_ingesta_sin_validated_automatico(self, tmp_path):
        """3. No validación automática: record no debe estar validated sin LearningValidator."""
        curator = InformationCurator(storage_path=str(tmp_path / "curator.json"))
        text = "Contenido de prueba para verificar que no es auto-validado."

        record = curator.ingest_text(text, source="test")

        # P2-A: InformationCurator NO debe marcar como validado por sí solo
        # El campo validated_at debe ser None (no validado aún)
        assert record.validated_at is None
        # deprecated debe ser False inicialmente
        assert record.deprecated is False

    def test_dedupe_textos_identicos(self, tmp_path):
        """4. Dedupe: dos textos idénticos → no duplicar."""
        curator = InformationCurator(storage_path=str(tmp_path / "curator.json"))
        text = "Texto idéntico que debe ser deduplicado por hash."

        record1 = curator.ingest_text(text, source="source_a")
        record2 = curator.ingest_text(text, source="source_b")

        # El segundo debe devolver el mismo registro (no crear duplicado)
        assert record1.record_id == record2.record_id
        assert record1.content_hash == record2.content_hash

    def test_quality_score_calculado(self, tmp_path):
        """5. Quality score: entrada con contenido → quality_score existe."""
        curator = InformationCurator(storage_path=str(tmp_path / "curator.json"))
        text = "Texto con suficiente contenido y estructura. Tiene más de cien caracteres para que el quality score sea calculado correctamente."

        record = curator.ingest_text(text, source="test")

        # Debe tener quality_score calculado
        assert hasattr(record, 'quality_score')
        assert 0.0 <= record.quality_score <= 1.0
        assert record.quality is not None

    def test_deteccion_contradicciones(self, tmp_path):
        """6. Contradicción: texto A afirma X, texto B niega X → detectar."""
        curator = InformationCurator(storage_path=str(tmp_path / "curator.json"))

        text_a = "Es correcto usar machine learning para trading."
        text_b = "Es incorrecto usar machine learning para trading."

        record_a = curator.ingest_text(text_a, source="expert_a")
        record_b = curator.ingest_text(text_b, source="expert_b")

        # Verificar que se detectan contradicciones
        contradictions = curator.get_contradictions()
        assert len(contradictions) > 0

    def test_no_semantic_memory_bridge(self):
        """7. No SemanticMemoryBridge: confirmar que no se importa ni invoca."""
        # Verificar que el módulo no tiene imports de SemanticMemoryBridge ni FAISS
        import information_curator as ic_module
        import sys
        
        # Verificar que no hay SemanticMemoryBridge ni faiss en los módulos importados
        loaded_modules = [name.lower() for name in sys.modules.keys()]
        
        # Verificar que no hay imports de semantic_memory, faiss, o SemanticMemoryBridge
        for mod in loaded_modules:
            if "semantic_memory" in mod or "faiss" in mod or "semanticmemorybridge" in mod:
                pytest.fail(f"Módulo no permitido cargado: {mod}")

    def test_trazabilidad_id_hash(self, tmp_path):
        """8. Trazabilidad: verificar que id y hash son estables."""
        curator = InformationCurator(storage_path=str(tmp_path / "curator.json"))
        text = "Texto para verificar trazabilidad de id y hash."

        record = curator.ingest_text(text, source="test")

        # ID debe ser string y empezar con rec_
        assert isinstance(record.record_id, str)
        assert record.record_id.startswith("rec_")

        # Hash debe ser SHA-256 (64 caracteres hex)
        assert isinstance(record.content_hash, str)
        assert len(record.content_hash) == 64

    def test_topic_clasificacion(self, tmp_path):
        """9. Clasificación: verificar que asigna topic apropiado."""
        curator = InformationCurator(storage_path=str(tmp_path / "curator.json"))

        # Texto de trading
        trading_text = "Estrategia de trading con backtest y señales de entrada."
        record_trading = curator.ingest_text(trading_text, source="test")
        assert record_trading.topic == ContentTopic.TRADING

        # Texto de AI
        ai_text = "Modelo de machine learning con entrenamiento y embeddings."
        record_ai = curator.ingest_text(ai_text, source="test")
        assert record_ai.topic == ContentTopic.AI_ML

    def test_no_side_effects_disco(self, tmp_path):
        """10. No side effects: verificar que solo escribe en tmp_path proporcionado."""
        storage_file = tmp_path / "curator_test.json"
        curator = InformationCurator(storage_path=str(storage_file))

        text = "Texto para verificar persistencia controlada."
        curator.ingest_text(text, source="test")

        # Debe haber creado el archivo de persistencia
        assert storage_file.exists()

        # Verificar que el archivo contiene datos válidos (InformationCurator persiste directamente un dict de records)
        import json
        with open(storage_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            # InformationCurator guarda directamente el dict de records sin wrapper "records"
            # Verificamos que haya al menos un record con estructura válida
            assert len(data) > 0
            first_key = list(data.keys())[0]
            assert first_key.startswith("rec_")
            assert "content" in data[first_key]


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
