"""
AI_VAULT Test Configuration
Configuracion centralizada para pytest
"""

import pytest
import sys
import os
from pathlib import Path
from unittest.mock import MagicMock, Mock
from datetime import datetime

# Agregar AI_VAULT al path
AI_VAULT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(AI_VAULT_ROOT))


@pytest.fixture(scope="session")
def vault_root():
    """Retorna la ruta raiz de AI_VAULT"""
    return AI_VAULT_ROOT


@pytest.fixture(scope="session")
def test_data_dir(tmp_path_factory):
    """Directorio temporal para datos de prueba"""
    return tmp_path_factory.mktemp("test_data")


@pytest.fixture
def mock_openai_response():
    """Mock de respuesta de OpenAI API"""
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": int(datetime.now().timestamp()),
        "model": "gpt-4",
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": "Respuesta de prueba del asistente"
            },
            "finish_reason": "stop"
        }],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30
        }
    }


@pytest.fixture
def mock_episode_data():
    """Datos de episodio de prueba"""
    return {
        "episode_id": "EP_TEST_001",
        "timestamp": datetime.now().isoformat(),
        "agent": "test_agent",
        "mission": "test_mission",
        "status": "completed",
        "data": {"key": "value"}
    }


@pytest.fixture
def mock_financial_data():
    """Datos financieros de prueba"""
    return {
        "symbol": "BTC-USD",
        "price": 65000.00,
        "volume": 1500000000,
        "timestamp": datetime.now().isoformat(),
        "change_24h": 2.5,
        "high_24h": 67000.00,
        "low_24h": 63000.00
    }


@pytest.fixture
def mock_db_connection():
    """Mock de conexion a base de datos"""
    conn = MagicMock()
    conn.execute = Mock(return_value=None)
    conn.fetchone = Mock(return_value={"id": 1, "name": "test"})
    conn.fetchall = Mock(return_value=[{"id": 1, "name": "test1"}, {"id": 2, "name": "test2"}])
    conn.commit = Mock(return_value=None)
    conn.close = Mock(return_value=None)
    return conn


@pytest.fixture(autouse=True)
def clean_environment():
    """Limpia variables de entorno antes de cada test"""
    original_env = dict(os.environ)
    yield
    os.environ.clear()
    os.environ.update(original_env)


@pytest.fixture
def api_client():
    """Cliente HTTP de prueba para FastAPI"""
    from fastapi.testclient import TestClient
    # Importar app principal. `main.py` es la entrada viva; `brain_server` queda
    # como compatibilidad por si reaparece en ramas viejas.
    try:
        from main import app
        return TestClient(app)
    except ImportError:
        try:
            from brain_server import app
            return TestClient(app)
        except ImportError:
            pytest.skip("No hay app FastAPI importable (main/brain_server)")


# Configuracion de pytest
def pytest_configure(config):
    """Configuracion adicional de pytest"""
    config.addinivalue_line(
        "markers", "slow: marca tests que tardan mas de 1 segundo"
    )
    config.addinivalue_line(
        "markers", "integration: marca tests de integracion"
    )
    config.addinivalue_line(
        "markers", "unit: marca tests unitarios"
    )


def pytest_collection_modifyitems(config, items):
    """Modifica items de test antes de ejecucion"""
    # Agregar marker 'unit' a tests que no tengan marker
    for item in items:
        if not any(marker.name in ['unit', 'integration', 'slow'] for marker in item.own_markers):
            item.add_marker(pytest.mark.unit)


# Hooks para reportes
def pytest_terminal_summary(terminalreporter, exitstatus, config):
    """Resumen personalizado de tests"""
    passed = len(terminalreporter.stats.get('passed', []))
    failed = len(terminalreporter.stats.get('failed', []))
    skipped = len(terminalreporter.stats.get('skipped', []))
    
    terminalreporter.write_sep("=", "AI_VAULT Test Summary")
    terminalreporter.write_line(f"Tests passed: {passed}")
    terminalreporter.write_line(f"Tests failed: {failed}")
    terminalreporter.write_line(f"Tests skipped: {skipped}")
    terminalreporter.write_line(f"Exit status: {exitstatus}")
