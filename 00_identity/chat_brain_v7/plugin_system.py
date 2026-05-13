#!/usr/bin/env python3
"""
Sistema de Plugins - Extensibilidad del Agente
Permite agregar herramientas y capacidades dinámicamente
"""

import json
import importlib
import inspect
from pathlib import Path
from typing import Dict, List, Callable, Any
from dataclasses import dataclass


@dataclass
class PluginInfo:
    """Información de un plugin"""
    name: str
    version: str
    description: str
    author: str
    entry_point: str
    hooks: List[str]
    enabled: bool = True


class PluginManager:
    """Gestor de plugins del sistema"""
    
    def __init__(self, plugins_dir: str = None):
        if plugins_dir is None:
            plugins_dir = "C:/AI_VAULT/00_identity/chat_brain_v7/plugins"
        self.plugins_dir = Path(plugins_dir)
        self.plugins_dir.mkdir(parents=True, exist_ok=True)
        
        self.loaded_plugins: Dict[str, Any] = {}
        self.plugin_info: Dict[str, PluginInfo] = {}
        self.hooks: Dict[str, List[Callable]] = {}
        
        self._create_default_plugins()
    
    def _create_default_plugins(self):
        """Crea plugins por defecto"""
        # Plugin de ejemplo
        example_plugin = self.plugins_dir / "example_plugin.py"
        if not example_plugin.exists():
            example_plugin.write_text('''
def initialize():
    """Inicializa el plugin"""
    return {"status": "loaded"}

def execute(data: dict) -> dict:
    """Ejecuta el plugin"""
    return {"processed": True, "data": data}
''')
    
    def load_plugin(self, plugin_name: str) -> bool:
        """Carga un plugin"""
        try:
            plugin_file = self.plugins_dir / f"{plugin_name}.py"
            if not plugin_file.exists():
                return False
            
            # Cargar módulo dinámicamente
            spec = importlib.util.spec_from_file_location(
                plugin_name, plugin_file
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            self.loaded_plugins[plugin_name] = module
            
            # Registrar hooks
            if hasattr(module, 'register_hooks'):
                hooks = module.register_hooks()
                for hook_name, callback in hooks.items():
                    self.register_hook(hook_name, callback)
            
            return True
        except Exception as e:
            print(f"[ERROR] No se pudo cargar plugin {plugin_name}: {e}")
            return False
    
    def register_hook(self, hook_name: str, callback: Callable):
        """Registra un hook"""
        if hook_name not in self.hooks:
            self.hooks[hook_name] = []
        self.hooks[hook_name].append(callback)
    
    def execute_hook(self, hook_name: str, *args, **kwargs) -> List[Any]:
        """Ejecuta todos los callbacks de un hook"""
        results = []
        if hook_name in self.hooks:
            for callback in self.hooks[hook_name]:
                try:
                    result = callback(*args, **kwargs)
                    results.append(result)
                except Exception as e:
                    print(f"[ERROR] Hook {hook_name} falló: {e}")
        return results
    
    def list_plugins(self) -> List[str]:
        """Lista plugins disponibles"""
        return [f.stem for f in self.plugins_dir.glob("*.py")]
    
    def unload_plugin(self, plugin_name: str) -> bool:
        """Descarga un plugin"""
        if plugin_name in self.loaded_plugins:
            del self.loaded_plugins[plugin_name]
            return True
        return False


class ToolPlugin:
    """Plugin base para herramientas"""
    
    def __init__(self, name: str, description: str):
        self.name = name
        self.description = description
        self.enabled = True
    
    def execute(self, **kwargs) -> Dict:
        """Método a sobrescribir"""
        raise NotImplementedError
    
    def get_info(self) -> Dict:
        """Retorna información del plugin"""
        return {
            "name": self.name,
            "description": self.description,
            "enabled": self.enabled
        }


if __name__ == "__main__":
    # Test
    print("Sistema de Plugins - Brain Agent V8")
    
    manager = PluginManager()
    plugins = manager.list_plugins()
    print(f"Plugins disponibles: {plugins}")
    
    if plugins:
        loaded = manager.load_plugin(plugins[0])
        print(f"Cargado: {loaded}")
