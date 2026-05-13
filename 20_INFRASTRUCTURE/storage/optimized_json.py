"""
AI_VAULT Optimized JSON Storage
Fase 7: Performance Optimization - JSON Storage Optimization
"""

import json
import gzip
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from datetime import datetime
from dataclasses import dataclass, asdict
import threading
import logging

logger = logging.getLogger(__name__)


@dataclass
class StorageConfig:
    """Configuracion de almacenamiento"""
    compress: bool = True
    indent: Optional[int] = None
    encoding: str = "utf-8"
    backup_count: int = 3
    max_file_size_mb: int = 100


class OptimizedJSONStorage:
    """
    Almacenamiento JSON optimizado con compresion y backup
    """
    
    def __init__(self, base_path: str = None, config: StorageConfig = None):
        self.base_path = Path(base_path) if base_path else Path("C:/AI_VAULT/data")
        self.base_path.mkdir(parents=True, exist_ok=True)
        self.config = config or StorageConfig()
        self._lock = threading.RLock()
        
        # Cache de metadatos de archivos
        self._file_meta: Dict[str, Dict] = {}
    
    def _get_file_path(self, key: str, compressed: bool = None) -> Path:
        """Genera ruta de archivo desde clave"""
        compressed = compressed if compressed is not None else self.config.compress
        ext = ".json.gz" if compressed else ".json"
        
        # Sanitizar nombre de archivo
        safe_key = "".join(c for c in key if c.isalnum() or c in "_-.")
        return self.base_path / f"{safe_key}{ext}"
    
    def save(self, key: str, data: Any, compress: bool = None) -> bool:
        """
        Guarda datos en archivo JSON
        
        Args:
            key: Identificador de los datos
            data: Datos a guardar (deben ser serializables)
            compress: Forzar compresion (None = usar config)
            
        Returns:
            True si se guardo exitosamente
        """
        compress = compress if compress is not None else self.config.compress
        
        with self._lock:
            try:
                file_path = self._get_file_path(key, compress)
                
                # Crear backup si existe
                if file_path.exists():
                    self._create_backup(file_path)
                
                # Serializar datos
                json_str = json.dumps(
                    data, 
                    indent=self.config.indent,
                    default=self._json_serializer,
                    ensure_ascii=False
                )
                
                if compress:
                    # Guardar comprimido
                    with gzip.open(file_path, "wt", encoding=self.config.encoding) as f:
                        f.write(json_str)
                else:
                    # Guardar sin comprimir
                    with open(file_path, "w", encoding=self.config.encoding) as f:
                        f.write(json_str)
                
                # Actualizar metadatos
                self._file_meta[key] = {
                    "path": str(file_path),
                    "size": file_path.stat().st_size,
                    "modified": datetime.now().isoformat(),
                    "compressed": compress
                }
                
                logger.debug(f"Datos guardados: {key} ({self._file_meta[key]['size']} bytes)")
                return True
                
            except Exception as e:
                logger.error(f"Error guardando {key}: {e}")
                return False
    
    def load(self, key: str, default: Any = None) -> Any:
        """
        Carga datos desde archivo JSON
        
        Args:
            key: Identificador de los datos
            default: Valor por defecto si no existe
            
        Returns:
            Datos cargados o default
        """
        with self._lock:
            # Intentar archivo comprimido primero
            for compress in [True, False]:
                file_path = self._get_file_path(key, compress)
                
                if not file_path.exists():
                    continue
                
                try:
                    if compress:
                        with gzip.open(file_path, "rt", encoding=self.config.encoding) as f:
                            json_str = f.read()
                    else:
                        with open(file_path, "r", encoding=self.config.encoding) as f:
                            json_str = f.read()
                    
                    data = json.loads(json_str)
                    logger.debug(f"Datos cargados: {key}")
                    return data
                    
                except Exception as e:
                    logger.error(f"Error cargando {key}: {e}")
                    continue
            
            return default
    
    def delete(self, key: str) -> bool:
        """Elimina archivo de datos"""
        with self._lock:
            for compress in [True, False]:
                file_path = self._get_file_path(key, compress)
                if file_path.exists():
                    try:
                        file_path.unlink()
                        self._file_meta.pop(key, None)
                        logger.debug(f"Datos eliminados: {key}")
                        return True
                    except Exception as e:
                        logger.error(f"Error eliminando {key}: {e}")
            return False
    
    def exists(self, key: str) -> bool:
        """Verifica si existen datos para una clave"""
        return any(
            self._get_file_path(key, compress).exists() 
            for compress in [True, False]
        )
    
    def _create_backup(self, file_path: Path):
        """Crea backup de archivo existente"""
        backup_dir = file_path.parent / ".backups"
        backup_dir.mkdir(exist_ok=True)
        
        # Rotar backups
        for i in range(self.config.backup_count - 1, 0, -1):
            old_backup = backup_dir / f"{file_path.stem}.bak{i}"
            new_backup = backup_dir / f"{file_path.stem}.bak{i+1}"
            if old_backup.exists():
                old_backup.rename(new_backup)
        
        # Crear backup actual
        backup_path = backup_dir / f"{file_path.stem}.bak1"
        if file_path.exists():
            import shutil
            shutil.copy2(file_path, backup_path)
    
    def _json_serializer(self, obj) -> Any:
        """Serializador JSON personalizado"""
        if isinstance(obj, datetime):
            return obj.isoformat()
        elif hasattr(obj, "__dataclass_fields__"):
            return asdict(obj)
        elif hasattr(obj, "to_dict"):
            return obj.to_dict()
        elif hasattr(obj, "__dict__"):
            return obj.__dict__
        raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
    
    def get_stats(self) -> Dict:
        """Retorna estadisticas de almacenamiento"""
        with self._lock:
            total_size = 0
            file_count = 0
            
            for ext in ["*.json", "*.json.gz"]:
                for file_path in self.base_path.glob(ext):
                    total_size += file_path.stat().st_size
                    file_count += 1
            
            return {
                "base_path": str(self.base_path),
                "file_count": file_count,
                "total_size_bytes": total_size,
                "total_size_mb": round(total_size / (1024 * 1024), 2),
                "compression_enabled": self.config.compress
            }
    
    def list_keys(self) -> List[str]:
        """Lista todas las claves almacenadas"""
        keys = set()
        for ext in ["*.json", "*.json.gz"]:
            for file_path in self.base_path.glob(ext):
                key = file_path.stem
                if file_path.suffix == ".gz":
                    key = file_path.stem  # Remover .json
                keys.add(key)
        return sorted(list(keys))
    
    def batch_save(self, items: Dict[str, Any]) -> Dict[str, bool]:
        """
        Guarda multiples items eficientemente
        
        Args:
            items: Diccionario de clave -> datos
            
        Returns:
            Diccionario de clave -> exito
        """
        results = {}
        for key, data in items.items():
            results[key] = self.save(key, data)
        return results
    
    def batch_load(self, keys: List[str]) -> Dict[str, Any]:
        """
        Carga multiples items eficientemente
        
        Args:
            keys: Lista de claves a cargar
            
        Returns:
            Diccionario de clave -> datos
        """
        results = {}
        for key in keys:
            data = self.load(key)
            if data is not None:
                results[key] = data
        return results


class JSONLinesStorage:
    """
    Almacenamiento en formato JSON Lines (ndjson)
    Optimizado para logs y datos append-only
    """
    
    def __init__(self, file_path: str, max_file_size_mb: int = 100):
        self.file_path = Path(file_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self.max_size = max_file_size_mb * 1024 * 1024
        self._lock = threading.RLock()
    
    def append(self, record: Dict) -> bool:
        """Agrega un registro al archivo"""
        with self._lock:
            try:
                # Verificar rotacion
                if self.file_path.exists() and self.file_path.stat().st_size > self.max_size:
                    self._rotate()
                
                # Agregar registro
                with open(self.file_path, "a", encoding="utf-8") as f:
                    json_line = json.dumps(record, default=str, ensure_ascii=False)
                    f.write(json_line + "\n")
                
                return True
            except Exception as e:
                logger.error(f"Error escribiendo registro: {e}")
                return False
    
    def read_all(self) -> List[Dict]:
        """Lee todos los registros"""
        records = []
        if not self.file_path.exists():
            return records
        
        with self._lock:
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            try:
                                records.append(json.loads(line))
                            except json.JSONDecodeError:
                                continue
            except Exception as e:
                logger.error(f"Error leyendo registros: {e}")
        
        return records
    
    def _rotate(self):
        """Rota archivo cuando excede tamaño maximo"""
        if self.file_path.exists():
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            rotated = self.file_path.parent / f"{self.file_path.stem}_{timestamp}{self.file_path.suffix}"
            self.file_path.rename(rotated)
            logger.info(f"Archivo rotado: {rotated}")


# Instancia global
_storage = None

def get_storage() -> OptimizedJSONStorage:
    """Retorna instancia global de almacenamiento"""
    global _storage
    if _storage is None:
        _storage = OptimizedJSONStorage()
    return _storage


def save_json(key: str, data: Any, compress: bool = True) -> bool:
    """Guarda datos JSON usando almacenamiento global"""
    return get_storage().save(key, data, compress=compress)

def load_json(key: str, default: Any = None) -> Any:
    """Carga datos JSON usando almacenamiento global"""
    return get_storage().load(key, default=default)


if __name__ == "__main__":
    # Demo de almacenamiento
    print("AI_VAULT Optimized JSON Storage Demo")
    print("=" * 50)
    
    storage = OptimizedJSONStorage("C:/AI_VAULT/test_data")
    
    # Guardar datos
    test_data = {
        "users": [
            {"id": 1, "name": "Alice", "created": datetime.now()},
            {"id": 2, "name": "Bob", "created": datetime.now()}
        ],
        "count": 2
    }
    
    storage.save("users", test_data, compress=True)
    print(f"Datos guardados")
    
    # Cargar datos
    loaded = storage.load("users")
    print(f"Datos cargados: {loaded}")
    
    # Estadisticas
    print(f"\nStats: {storage.get_stats()}")
    
    # JSON Lines demo
    print("\nJSON Lines Demo:")
    lines_storage = JSONLinesStorage("C:/AI_VAULT/test_data/events.ndjson")
    
    for i in range(5):
        lines_storage.append({
            "event": "test",
            "index": i,
            "timestamp": datetime.now().isoformat()
        })
    
    records = lines_storage.read_all()
    print(f"Registros leidos: {len(records)}")
