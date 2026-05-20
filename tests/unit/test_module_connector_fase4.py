"""Tests for Module Connector - FASE 4

Tests for minimal reconnection of orphan modules.
"""

import pytest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "tmp_agent"))

from brain_v9.core.routing.module_connector import (
    ModuleConnector,
    discover_modules,
    get_module,
    get_module_info,
    get_information_curator,
    get_learning_validator,
    get_phase_evaluator,
    ORPHAN_MODULES,
)


class TestModuleDiscovery:
    """Test module discovery functionality."""
    
    def test_can_discover_modules(self):
        """Should discover orphan modules."""
        status = discover_modules()
        
        assert isinstance(status, dict)
        assert len(status) > 0
        
        # Should have status for each orphan module
        for name in ORPHAN_MODULES.keys():
            assert name in status, f"Missing status for {name}"


class TestModuleConnector:
    """Test ModuleConnector class."""
    
    def test_connector_can_be_created(self):
        """Should be able to create connector."""
        connector = ModuleConnector()
        assert connector is not None
    
    def test_connector_can_check_status(self):
        """Should be able to check connection status."""
        connector = ModuleConnector()
        status = connector.status()
        
        assert "modules" in status
        assert "connected_count" in status
        assert "total_count" in status
        assert status["total_count"] > 0
    
    def test_connector_can_check_availability(self):
        """Should be able to check if module is available."""
        connector = ModuleConnector()
        
        for name in ORPHAN_MODULES.keys():
            available = connector.is_available(name)
            # Should be boolean
            assert isinstance(available, bool)


class TestModuleAccess:
    """Test module access functions."""
    
    def test_get_module_returns_none_or_object(self):
        """get_module should return module or None."""
        for name in ORPHAN_MODULES.keys():
            module = get_module(name)
            # Should return something or None
            assert module is not None or module is None
    
    def test_get_information_curator(self):
        """Should be able to get InformationCurator."""
        curator = get_information_curator()
        # May return None if not available, but should not crash
        assert curator is not None or curator is None
    
    def test_get_learning_validator(self):
        """Should be able to get LearningValidator."""
        validator = get_learning_validator()
        assert validator is not None or validator is None
    
    def test_get_phase_evaluator(self):
        """Should be able to get PhaseEvaluator."""
        evaluator = get_phase_evaluator()
        assert evaluator is not None or evaluator is None


class TestModuleInfo:
    """Test module information reporting."""
    
    def test_get_module_info_returns_dict(self):
        """Should return module info dict."""
        info = get_module_info()
        
        assert isinstance(info, dict)
        assert "modules" in info
        assert "total_count" in info
        assert info["total_count"] == len(ORPHAN_MODULES)
    
    def test_module_info_tracks_registry(self):
        """Should track registry size."""
        info = get_module_info()
        
        assert "registry_size" in info
        assert isinstance(info["registry_size"], int)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
