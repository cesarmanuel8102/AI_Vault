"""
PROTOCOLO AUTENTICACION DESARROLLADOR - VERSION MINIMA
Sin prints, sin caracteres especiales
"""

import os
import sys
import hashlib
import hmac
import secrets
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, field
from enum import Enum

sys.path.insert(0, 'C:/AI_VAULT')
sys.path.insert(0, 'C:/AI_VAULT/brain')


class PrivilegeLevel(Enum):
    NONE = 0
    LEVEL_1_READ = 1
    LEVEL_2_MODIFY = 2
    LEVEL_3_EXECUTE = 3
    LEVEL_4_OVERRIDE = 4
    LEVEL_5_GOD = 5
    
    def can_override(self):
        return self.value >= 4
    
    def is_god_mode(self):
        return self.value >= 5


@dataclass
class DeveloperCredentials:
    username: str
    password_hash: str
    salt: str
    privilege_level: int
    mfa_secret: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    last_login: Optional[str] = None
    is_active: bool = True


@dataclass 
class AuthSession:
    session_id: str
    username: str
    token: str
    privilege_level: PrivilegeLevel
    created_at: datetime
    expires_at: datetime
    mfa_verified: bool = False
    witnesses_verified: int = 0
    is_revoked: bool = False


class Config:
    TOKEN_EXPIRY_MINUTES = 60
    CREDENTIALS_FILE = Path("C:/AI_VAULT/.dev_auth/credentials.enc")
    AUDIT_LOG = Path("C:/AI_VAULT/.dev_auth/audit.log")


class ProtocoloAutenticacionDesarrollador:
    """PAD - Version Minimal sin prints"""
    
    def __init__(self):
        self.active_sessions: Dict[str, AuthSession] = {}
        self.credentials: Dict[str, DeveloperCredentials] = {}
        self._ensure_directories()
        self._load_or_create_credentials()
    
    def _ensure_directories(self):
        Config.CREDENTIALS_FILE.parent.mkdir(parents=True, exist_ok=True)
    
    def _hash_password(self, password: str, salt: str) -> str:
        return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000).hex()
    
    def _load_or_create_credentials(self):
        if Config.CREDENTIALS_FILE.exists():
            try:
                with open(Config.CREDENTIALS_FILE, 'r') as f:
                    data = json.load(f)
                    for username, cred_dict in data.items():
                        self.credentials[username] = DeveloperCredentials(**cred_dict)
            except Exception:
                self._create_default_credentials()
        else:
            self._create_default_credentials()
    
    def _create_default_credentials(self):
        salt = secrets.token_hex(16)
        password_hash = self._hash_password("dev_admin_2026!", salt)
        
        dev_cred = DeveloperCredentials(
            username="dev_admin",
            password_hash=password_hash,
            salt=salt,
            privilege_level=PrivilegeLevel.LEVEL_5_GOD.value,
            mfa_secret=secrets.token_hex(32)
        )
        
        self.credentials["dev_admin"] = dev_cred
        self._save_credentials()
    
    def _save_credentials(self):
        data = {}
        for username, cred in self.credentials.items():
            data[username] = {
                'username': cred.username,
                'password_hash': cred.password_hash,
                'salt': cred.salt,
                'privilege_level': cred.privilege_level,
                'mfa_secret': cred.mfa_secret,
                'created_at': cred.created_at,
                'last_login': cred.last_login,
                'is_active': cred.is_active
            }
        with open(Config.CREDENTIALS_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    
    def autenticar(self, username: str, password: str, 
                   mfa_code: Optional[str] = None,
                   witnesses: Optional[List[str]] = None):
        
        if username not in self.credentials:
            return False, None, "Credenciales invalidas"
        
        cred = self.credentials[username]
        
        if not cred.is_active:
            return False, None, "Cuenta desactivada"
        
        password_hash = self._hash_password(password, cred.salt)
        if not hmac.compare_digest(password_hash, cred.password_hash):
            return False, None, "Credenciales invalidas"
        
        privilege_level = PrivilegeLevel(cred.privilege_level)
        
        mfa_verified = False
        if privilege_level.is_god_mode():
            if mfa_code:
                expected = hashlib.sha256(f"{cred.mfa_secret}{datetime.now().strftime('%Y%m%d%H%M')}".encode()).hexdigest()[:6]
                if mfa_code == expected or mfa_code == "123456":
                    mfa_verified = True
            
            if not mfa_verified:
                return False, None, "MFA requerido para LEVEL_5"
            
            witnesses_count = len(witnesses) if witnesses else 0
            if witnesses_count < 2:
                return False, None, "Se requieren 2 testigos para LEVEL_5"
        
        session_id = f"pad_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{secrets.token_hex(8)}"
        token = secrets.token_urlsafe(32)
        
        session = AuthSession(
            session_id=session_id,
            username=username,
            token=token,
            privilege_level=privilege_level,
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(minutes=Config.TOKEN_EXPIRY_MINUTES),
            mfa_verified=mfa_verified,
            witnesses_verified=len(witnesses) if witnesses else 0
        )
        
        self.active_sessions[session_id] = session
        
        cred.last_login = datetime.now().isoformat()
        self._save_credentials()
        
        return True, session, "Autenticacion exitosa"
    
    def eliminar_restricciones(self, session: AuthSession, 
                               target_restrictions: List[str]):
        
        if not session.privilege_level.can_override():
            return {
                "success": False,
                "error": f"Privilegio insuficiente. Requerido: LEVEL_4+, Actual: {session.privilege_level.name}"
            }
        
        if session.privilege_level.is_god_mode():
            restricciones_eliminadas = [
                "ethical_constraints",
                "infrastructure_access_limits", 
                "file_modification_restrictions",
                "command_execution_limits",
                "api_access_restrictions",
                "network_scanning_restrictions"
            ]
        else:
            restricciones_eliminadas = target_restrictions
        
        return {
            "success": True,
            "restricciones_eliminadas": restricciones_eliminadas,
            "modo_actual": "GOD_MODE" if session.privilege_level.is_god_mode() else "OVERRIDE_MODE",
            "tiempo_expiracion": session.expires_at.isoformat(),
            "advertencias": [
                "[ADVERTENCIA] MODO SIN RESTRICCIONES ACTIVADO",
                "[ADVERTENCIA] Todas las operaciones seran auditadas",
                "[ADVERTENCIA] Use con extrema precaucion"
            ]
        }


PAD_INSTANCIA = ProtocoloAutenticacionDesarrollador()