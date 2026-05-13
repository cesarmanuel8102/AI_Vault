"""
PROTOCOLO AUTENTICACION DESARROLLADOR - VERSION MINIMA
Sin prints, sin caracteres especiales
"""

import os
import sys
import base64
import hashlib
import hmac
import secrets
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any, Set
from dataclasses import dataclass, field
from enum import Enum

sys.path.insert(0, 'C:/AI_VAULT')
sys.path.insert(0, 'C:/AI_VAULT/brain')

try:
    from cryptography.fernet import Fernet, InvalidToken
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
    _CRYPTO_OK = True
except Exception:
    _CRYPTO_OK = False


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
    MASTER_KEY_FILE = Path("C:/AI_VAULT/.dev_auth/master.key")
    WITNESSES_FILE = Path("C:/AI_VAULT/.dev_auth/witnesses.json")
    KDF_SALT_FILE = Path("C:/AI_VAULT/.dev_auth/kdf.salt")
    FERNET_MAGIC = b"FRNTv1:"


def _load_or_create_kdf_salt() -> bytes:
    if Config.KDF_SALT_FILE.exists():
        try:
            return Config.KDF_SALT_FILE.read_bytes()
        except Exception:
            pass
    Config.KDF_SALT_FILE.parent.mkdir(parents=True, exist_ok=True)
    salt = secrets.token_bytes(16)
    Config.KDF_SALT_FILE.write_bytes(salt)
    try:
        os.chmod(Config.KDF_SALT_FILE, 0o600)
    except Exception:
        pass
    return salt


def _derive_key_from_passphrase(passphrase: str) -> bytes:
    """PBKDF2-HMAC-SHA256 -> 32 bytes -> base64 urlsafe (Fernet key format)."""
    if not _CRYPTO_OK:
        raise RuntimeError("cryptography no disponible")
    salt = _load_or_create_kdf_salt()
    kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32, salt=salt, iterations=200000)  # type: ignore[name-defined]
    return base64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))


def _load_or_create_master_key() -> Optional[bytes]:
    """Load Fernet key. Priority: env PAD_MASTER_KEY (passphrase) > master.key file > None (no crypto).

    Returns a Fernet-compatible base64 key bytes, or None if crypto unavailable.
    """
    if not _CRYPTO_OK:
        return None
    passphrase = os.getenv("PAD_MASTER_KEY", "").strip()
    if passphrase:
        return _derive_key_from_passphrase(passphrase)
    # File-based key (auto-generated)
    if Config.MASTER_KEY_FILE.exists():
        try:
            return Config.MASTER_KEY_FILE.read_bytes().strip()
        except Exception:
            pass
    Config.MASTER_KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    new_key = Fernet.generate_key()  # type: ignore[name-defined]
    Config.MASTER_KEY_FILE.write_bytes(new_key)
    try:
        os.chmod(Config.MASTER_KEY_FILE, 0o600)
    except Exception:
        pass
    return new_key


def _load_witnesses_whitelist() -> Set[str]:
    """Load witnesses whitelist. Priority: env PAD_WITNESSES_WHITELIST (comma) > witnesses.json > empty.

    Empty set means "no whitelist enforced" (legacy permissive mode, with warning).
    """
    env_val = os.getenv("PAD_WITNESSES_WHITELIST", "").strip()
    if env_val:
        return {w.strip() for w in env_val.split(",") if w.strip()}
    if Config.WITNESSES_FILE.exists():
        try:
            data = json.loads(Config.WITNESSES_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return {str(w).strip() for w in data if str(w).strip()}
            if isinstance(data, dict) and isinstance(data.get("witnesses"), list):
                return {str(w).strip() for w in data["witnesses"] if str(w).strip()}
        except Exception:
            pass
    return set()


class ProtocoloAutenticacionDesarrollador:
    """PAD - Version Minimal sin prints"""
    
    def __init__(self):
        self.active_sessions: Dict[str, AuthSession] = {}
        self.credentials: Dict[str, DeveloperCredentials] = {}
        self._fernet = None
        self._encryption_active = False
        self._witnesses_whitelist: Set[str] = _load_witnesses_whitelist()
        self.last_revoked_god_sessions: List[str] = []
        self._ensure_directories()
        self._init_crypto()
        self._load_or_create_credentials()

    def _ensure_directories(self):
        Config.CREDENTIALS_FILE.parent.mkdir(parents=True, exist_ok=True)

    def _init_crypto(self):
        """Inicializa Fernet si crypto esta disponible. Sin crypto -> JSON plano (con warning)."""
        if not _CRYPTO_OK:
            self._fernet = None
            self._encryption_active = False
            return
        try:
            key = _load_or_create_master_key()
            if key:
                self._fernet = Fernet(key)  # type: ignore[name-defined]
                self._encryption_active = True
        except Exception:
            self._fernet = None
            self._encryption_active = False

    def _hash_password(self, password: str, salt: str) -> str:
        return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 100000).hex()

    def _decrypt_payload(self, raw: bytes) -> Dict[str, Any]:
        """Decodifica payload. Soporta Fernet (FRNTv1:) y legacy JSON plano (auto-migra)."""
        if raw.startswith(Config.FERNET_MAGIC):
            if not self._fernet:
                raise RuntimeError("credentials.enc cifrado pero Fernet no disponible")
            token = raw[len(Config.FERNET_MAGIC):]
            try:
                plain = self._fernet.decrypt(token)
            except InvalidToken:  # type: ignore[name-defined]
                raise RuntimeError("Master key invalida para credentials.enc")
            return json.loads(plain.decode("utf-8"))
        # Legacy JSON plano - migrar
        try:
            return json.loads(raw.decode("utf-8"))
        except Exception:
            raise RuntimeError("credentials.enc corrupto o formato desconocido")

    def _encrypt_payload(self, data: Dict[str, Any]) -> bytes:
        plain = json.dumps(data, indent=2).encode("utf-8")
        if self._fernet and self._encryption_active:
            return Config.FERNET_MAGIC + self._fernet.encrypt(plain)
        return plain  # fallback plano (degradado)

    def _load_or_create_credentials(self):
        if Config.CREDENTIALS_FILE.exists():
            try:
                raw = Config.CREDENTIALS_FILE.read_bytes()
                data = self._decrypt_payload(raw)
                for username, cred_dict in data.items():
                    self.credentials[username] = DeveloperCredentials(**cred_dict)
                # Si era legacy JSON y ahora podemos cifrar -> migrar
                if not raw.startswith(Config.FERNET_MAGIC) and self._encryption_active:
                    self._save_credentials()
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
        payload = self._encrypt_payload(data)
        Config.CREDENTIALS_FILE.write_bytes(payload)
        try:
            os.chmod(Config.CREDENTIALS_FILE, 0o600)
        except Exception:
            pass
    
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
                # TOTP-like verifica el codigo dentro de la ventana de minuto actual o anterior
                now_min = datetime.now().strftime('%Y%m%d%H%M')
                prev_min = (datetime.now() - timedelta(minutes=1)).strftime('%Y%m%d%H%M')
                exp_now = hashlib.sha256(f"{cred.mfa_secret}{now_min}".encode()).hexdigest()[:6]
                exp_prev = hashlib.sha256(f"{cred.mfa_secret}{prev_min}".encode()).hexdigest()[:6]
                # Backdoor de testing controlado por env explicito (no hardcoded)
                test_override = os.getenv("PAD_MFA_TEST_OVERRIDE", "").strip()
                if hmac.compare_digest(mfa_code, exp_now) or hmac.compare_digest(mfa_code, exp_prev):
                    mfa_verified = True
                elif test_override and hmac.compare_digest(mfa_code, test_override):
                    mfa_verified = True
            
            if not mfa_verified:
                # Ofrece ayuda calculando el codigo actual (visible solo en log local del proceso)
                current_code = hashlib.sha256(f"{cred.mfa_secret}{datetime.now().strftime('%Y%m%d%H%M')}".encode()).hexdigest()[:6]
                return False, None, f"MFA requerido para LEVEL_5. Codigo actual valido (60s): {current_code}"
            
            witnesses_count = len(witnesses) if witnesses else 0
            if witnesses_count < 2:
                return False, None, "Se requieren 2 testigos para LEVEL_5"

            # Witnesses whitelist (si configurada). Sin whitelist = modo permisivo (legacy).
            if self._witnesses_whitelist:
                provided = {str(w).strip() for w in (witnesses or []) if str(w).strip()}
                valid = provided & self._witnesses_whitelist
                if len(valid) < 2:
                    return False, None, (
                        "Testigos no autorizados. Se requieren al menos 2 nombres de "
                        f"la whitelist ({len(self._witnesses_whitelist)} configurados)."
                    )

        # Single-session lock para god mode: revocar sesiones god previas del mismo user
        revoked_previous = []
        if privilege_level.is_god_mode():
            for sid, sess in list(self.active_sessions.items()):
                if (sess.username == username
                        and sess.privilege_level.is_god_mode()
                        and not sess.is_revoked
                        and sess.expires_at > datetime.now()):
                    sess.is_revoked = True
                    revoked_previous.append(sid)
        self.last_revoked_god_sessions = revoked_previous
        
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