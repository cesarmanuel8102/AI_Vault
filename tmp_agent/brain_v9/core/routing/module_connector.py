"""Module Connector for Orphan Modules

FASE 4: Minimal reconnection of InformationCurator, LearningValidator, PhaseEvaluator.
NO complex orchestration - just simple wiring and accessibility.

NOTE: This module exists as INFRASTRUCTURE for future module integration.
The target modules (InformationCurator, LearningValidator, PhaseEvaluator)
exist in brain.* namespace but are NOT yet wired into the main system.

This connector provides the capability to access these modules once they
are properly integrated, but currently serves as infrastructure rather than
operational capability.
"""

from typing import Any, Dict, Optional, Type
from pathlib import Path
import sys
import logging

log = logging.getLogger("module_connector")

# Module registry
_modules: Dict[str, Any] = {}
_module_status: Dict[str, Dict[str, Any]] = {}

# Orphan module paths
ORPHAN_MODULES = {
    "InformationCurator": "brain.information_curator",
    "LearningValidator": "brain.learning_validator", 
    "PhaseEvaluator": "brain.phase_evaluator",
}


def _try_import(module_path: str) -> Optional[Type]:
    """Try to import a module, return None if not found."""
    try:
        parts = module_path.split(".")
        module_name = ".".join(parts[:-1]) if len(parts) > 1 else module_path
        class_name = parts[-1] if len(parts) > 1 else None
        
        __import__(module_path)
        module = sys.modules[module_path]
        
        if class_name:
            return getattr(module, class_name, None)
        return module
    except ImportError as e:
        log.debug(f"Failed to import {module_path}: {e}")
        return None
    except Exception as e:
        log.warning(f"Unexpected error importing {module_path}: {e}")
        return None


def discover_modules() -> Dict[str, Dict[str, Any]]:
    """Discover orphan modules and their status.
    
    Returns dict with module availability status.
    """
    status = {}
    
    for name, path in ORPHAN_MODULES.items():
        module_class = _try_import(path)
        
        if module_class:
            status[name] = {
                "available": True,
                "path": path,
                "type": "class" if isinstance(module_class, type) else "module",
                "can_instantiate": isinstance(module_class, type),
            }
        else:
            status[name] = {
                "available": False,
                "path": path,
                "error": "Import failed",
            }
    
    _module_status.update(status)
    return status


def get_module(name: str) -> Optional[Any]:
    """Get a module instance (cached).
    
    Args:
        name: Module name (e.g., "InformationCurator")
        
    Returns:
        Module instance or None if not available
    """
    if name in _modules:
        return _modules[name]
    
    # Discover if not done
    if not _module_status:
        discover_modules()
    
    if name not in _module_status or not _module_status[name]["available"]:
        return None
    
    # Try to instantiate if it's a class
    path = ORPHAN_MODULES[name]
    module_class = _try_import(path)
    
    if module_class and isinstance(module_class, type):
        try:
            instance = module_class()
            _modules[name] = instance
            return instance
        except Exception as e:
            log.warning(f"Failed to instantiate {name}: {e}")
            return module_class  # Return class if instantiation fails
    
    return module_class


def get_module_info() -> Dict[str, Any]:
    """Get information about all orphan modules.
    
    Returns:
        Dict with module info and connection status
    """
    if not _module_status:
        discover_modules()
    
    return {
        "modules": dict(_module_status),
        "connected_count": sum(1 for s in _module_status.values() if s.get("available", False)),
        "total_count": len(ORPHAN_MODULES),
        "registry_size": len(_modules),
    }


class ModuleConnector:
    """Minimal connector for orphan modules.
    
    Usage:
        connector = ModuleConnector()
        curator = connector.get("InformationCurator")
        if curator:
            # Use curator
            pass
    """
    
    def __init__(self):
        self._local_cache: Dict[str, Any] = {}
    
    def get(self, name: str) -> Optional[Any]:
        """Get module by name."""
        if name in self._local_cache:
            return self._local_cache[name]
        
        module = get_module(name)
        if module:
            self._local_cache[name] = module
        return module
    
    def status(self) -> Dict[str, Any]:
        """Get connection status."""
        return get_module_info()
    
    def is_available(self, name: str) -> bool:
        """Check if module is available."""
        if not _module_status:
            discover_modules()
        return _module_status.get(name, {}).get("available", False)


# Simple function exports for direct use
def get_information_curator() -> Optional[Any]:
    """Get InformationCurator instance."""
    return get_module("InformationCurator")


def get_learning_validator() -> Optional[Any]:
    """Get LearningValidator instance."""
    return get_module("LearningValidator")


def get_phase_evaluator() -> Optional[Any]:
    """Get PhaseEvaluator instance."""
    return get_module("PhaseEvaluator")
