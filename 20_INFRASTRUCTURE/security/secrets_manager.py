"""
AI_VAULT Secrets Manager
Fase 6: Security Enhancements - Centralized Encrypted Secrets
"""

import os
import json
import base64
import hashlib
from pathlib import Path
from typing import Dict, Optional, Any
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


class SecretsManager:
    """
    Gestor centralizado de secretos con encriptacion
    Almacena y recupera secretos de forma segura
    """
    
    def __init__(self, vault_path: str = None, master_key: str = None):
        self.vault_path = Path(vault_path) if vault_path else Path("C:/AI_VAULT/20_INFRASTRUCTURE/security/.secrets")
        self.vault_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Inicializar o cargar clave maestra
        self._init_encryption(master_key)
        
        # Cache de secretos desencriptados
        self._cache: Dict[str, Any] = {}
        self._cache_ttl: Dict[str, datetime] = {}
        self._cache_duration = timedelta(minutes=5)
        
        # Cargar vault existente
        self._secrets = self._load_vault()
    
    def _init_encryption(self, master_key: Optional[str] = None):
        """Inicializa el sistema de encriptacion"""
        key_file = self.vault_path.parent / ".master_key"
        
        if master_key:
            # Usar clave proporcionada
            self._derive_key(master_key)
        elif key_file.exists():
            # Cargar clave existente
            with open(key_file, "rb") as f:
                self._fernet = Fernet(f.read())
        else:
            # Generar nueva clave
            key = Fernet.generate_key()
            with open(key_file, "wb") as f:
                f.write(key)
            os.chmod(key_file, 0o600)  # Solo lectura para owner
            self._fernet = Fernet(key)
    
    def _derive_key(self, password: str):
        """Deriva clave de encriptacion desde password"""
        salt = os.urandom(16)
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=480000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        self._fernet = Fernet(key)
    
    def _load_vault(self) -> Dict[str, str]:
        """Carga el vault de secretos"""
        if not self.vault_path.exists():
            return {}
        
        try:
            with open(self.vault_path, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error cargando vault: {e}")
            return {}
    
    def _save_vault(self):
        """Guarda el vault de secretos"""
        try:
            with open(self.vault_path, "w") as f:
                json.dump(self._secrets, f, indent=2)
            os.chmod(self.vault_path, 0o600)
        except Exception as e:
            logger.error(f"Error guardando vault: {e}")
            raise
    
    def set_secret(self, key: str, value: Any, encrypt: bool = True):
        """
        Almacena un secreto
        
        Args:
            key: Identificador del secreto
            value: Valor a almacenar
            encrypt: Si True, encripta el valor
        """
        if encrypt:
            # Encriptar valor
            if isinstance(value, dict):
                value_str = json.dumps(value)
            else:
                value_str = str(value)
            
            encrypted = self._fernet.encrypt(value_str.encode())
            self._secrets[key] = base64.urlsafe_b64encode(encrypted).decode()
        else:
            self._secrets[key] = value
        
        # Actualizar cache
        self._cache[key] = value
        self._cache_ttl[key] = datetime.now() + self._cache_duration
        
        self._save_vault()
        logger.info(f"Secreto '{key}' almacenado")
    
    def get_secret(self, key: str, default: Any = None) -> Any:
        """
        Recupera un secreto
        
        Args:
            key: Identificador del secreto
            default: Valor por defecto si no existe
            
        Returns:
            Valor desencriptado del secreto
        """
        # Verificar cache
        if key in self._cache:
            if datetime.now() < self._cache_ttl.get(key, datetime.min):
                return self._cache[key]
            else:
                del self._cache[key]
                del self._cache_ttl[key]
        
        if key not in self._secrets:
            return default
        
        try:
            encrypted = base64.urlsafe_b64decode(self._secrets[key].encode())
            decrypted = self._fernet.decrypt(encrypted).decode()
            
            # Intentar parsear como JSON
            try:
                value = json.loads(decrypted)
            except json.JSONDecodeError:
                value = decrypted
            
            # Actualizar cache
            self._cache[key] = value
            self._cache_ttl[key] = datetime.now() + self._cache_duration
            
            return value
        except Exception as e:
            logger.error(f"Error desencriptando secreto '{key}': {e}")
            return default
    
    def delete_secret(self, key: str):
        """Elimina un secreto"""
        if key in self._secrets:
            del self._secrets[key]
            self._cache.pop(key, None)
            self._cache_ttl.pop(key, None)
            self._save_vault()
            logger.info(f"Secreto '{key}' eliminado")
    
    def rotate_key(self, new_master_key: str):
        """Rota la clave maestra y re-encripta todos los secretos"""
        # Guardar secretos actuales
        current_secrets = {
            key: self.get_secret(key) 
            for key in self._secrets.keys()
        }
        
        # Inicializar nueva encriptacion
        self._derive_key(new_master_key)
        
        # Re-encriptar todos los secretos
        self._secrets = {}
        for key, value in current_secrets.items():
            self.set_secret(key, value)
        
        logger.info("Clave maestra rotada exitosamente")
    
    def list_secrets(self) -> list:
        """Lista todos los identificadores de secretos"""
        return list(self._secrets.keys())
    
    def clear_cache(self):
        """Limpia el cache de secretos en memoria"""
        self._cache.clear()
        self._cache_ttl.clear()
        logger.info("Cache de secretos limpiado")
    
    def get_audit_log(self) -> list:
        """Retorna log de auditoria de accesos"""
        log_file = self.vault_path.parent / ".secrets_audit.log"
        if log_file.exists():
            with open(log_file, "r") as f:
                return [line.strip() for line in f.readlines()]
        return []


class EnvironmentSecrets:
    """
    Wrapper para secretos desde variables de entorno
    con fallback al SecretsManager
    """
    
    def __init__(self, manager: SecretsManager = None):
        self.manager = manager or SecretsManager()
    
    def get(self, key: str, default: Any = None, env_prefix: str = "AI_VAULT_") -> Any:
        """
        Obtiene secreto desde variable de entorno o vault
        
        Priority:
        1. Variable de entorno
        2. SecretsManager
        3. Default
        """
        env_key = f"{env_prefix}{key.upper()}"
        
        # Intentar variable de entorno
        env_value = os.getenv(env_key)
        if env_value:
            return env_value
        
        # Fallback a SecretsManager
        return self.manager.get_secret(key, default)
    
    def require(self, key: str, env_prefix: str = "AI_VAULT_") -> Any:
        """
        Obtiene secreto requerido, lanza error si no existe
        """
        value = self.get(key, env_prefix=env_prefix)
        if value is None:
            raise ValueError(f"Secreto requerido '{key}' no encontrado")
        return value


# Instancia global
_secrets_manager = None

def get_secrets_manager() -> SecretsManager:
    """Retorna instancia singleton del SecretsManager"""
    global _secrets_manager
    if _secrets_manager is None:
        _secrets_manager = SecretsManager()
    return _secrets_manager


# Funciones de conveniencia
def set_secret(key: str, value: Any, encrypt: bool = True):
    """Almacena un secreto en el vault global"""
    return get_secrets_manager().set_secret(key, value, encrypt)

def get_secret(key: str, default: Any = None) -> Any:
    """Recupera un secreto del vault global"""
    return get_secrets_manager().get_secret(key, default)

def delete_secret(key: str):
    """Elimina un secreto del vault global"""
    return get_secrets_manager().delete_secret(key)


if __name__ == "__main__":
    # Demo de uso
    print("AI_VAULT Secrets Manager Demo")
    print("=" * 50)
    
    sm = SecretsManager()
    
    # Demo de uso removido para evitar hardcoded secrets en el repo.
    # Para pruebas, usar variables de entorno o un vault temporal fuera del repositorio.
    # Ejemplo de uso seguro (no almacenar valores reales en el código):
    # sm.set_secret("openai_api_key", os.getenv("AI_VAULT_OPENAI_API_KEY"))
    # db_creds = {
    #     "host": os.getenv("AI_VAULT_DB_HOST", "localhost"),
    #     "port": int(os.getenv("AI_VAULT_DB_PORT", "5432")),
    #     "user": os.getenv("AI_VAULT_DB_USER", "ai_vault"),
    # }
    # sm.set_secret("db_credentials", db_creds)
    print("Demo de SecretsManager deshabilitada para seguridad.")
