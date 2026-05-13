"""
CORE/SETTINGS.PY - Configuracion centralizada y externalizada.
Lee de env vars + archivo opcional, valida tipos, expone via singleton.
Reemplaza rutas hardcodeadas y constantes dispersas.
"""
import json
import os
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, Optional


def _env(key: str, default: Any = None, cast: Any = str) -> Any:
    val = os.getenv(key)
    if val is None:
        return default
    try:
        if cast is bool:
            return val.lower() in ("1", "true", "yes", "on")
        return cast(val)
    except Exception:
        return default


@dataclass
class Settings:
    # Rutas (con defaults pero overridables)
    vault_root: str = field(default_factory=lambda: _env("AI_VAULT_ROOT", "C:/AI_VAULT"))
    state_dir: str = field(default_factory=lambda: _env("AI_VAULT_STATE", "C:/AI_VAULT/tmp_agent/state"))
    logs_dir: str = field(default_factory=lambda: _env("AI_VAULT_LOGS", "C:/AI_VAULT/50_LOGS"))
    backups_dir: str = field(default_factory=lambda: _env("AI_VAULT_BACKUPS", "C:/AI_VAULT/backups"))

    # Servidor
    server_host: str = field(default_factory=lambda: _env("BRAIN_HOST", "127.0.0.1"))
    server_port: int = field(default_factory=lambda: _env("BRAIN_PORT", 8090, int))

    # LLM
    llm_provider: str = field(default_factory=lambda: _env("LLM_PROVIDER", "ollama"))
    ollama_model: str = field(default_factory=lambda: _env("OLLAMA_MODEL", "llama3.2"))
    ollama_url: str = field(default_factory=lambda: _env("OLLAMA_URL", "http://localhost:11434"))
    openai_api_key: Optional[str] = field(default_factory=lambda: _env("OPENAI_API_KEY", None))

    # Autonomia
    aos_enabled: bool = field(default_factory=lambda: _env("AOS_ENABLED", True, bool))
    aos_interval: int = field(default_factory=lambda: _env("AOS_INTERVAL", 120, int))
    auto_debugging: bool = field(default_factory=lambda: _env("AUTO_DEBUGGING", True, bool))
    proactive_monitoring: bool = field(default_factory=lambda: _env("PROACTIVE_MONITOR", True, bool))
    debugger_interval: int = field(default_factory=lambda: _env("DEBUGGER_INTERVAL", 300, int))
    monitor_interval: int = field(default_factory=lambda: _env("MONITOR_INTERVAL", 60, int))

    # Auto-desarrollo
    self_dev_enabled: bool = field(default_factory=lambda: _env("SELF_DEV_ENABLED", False, bool))
    self_dev_max_risk: float = field(default_factory=lambda: _env("SELF_DEV_MAX_RISK", 0.4, float))
    self_dev_require_approval: bool = field(default_factory=lambda: _env("SELF_DEV_REQUIRE_APPROVAL", _env("SELF_DEV_APPROVAL", True, bool), bool))

    # Metacognicion
    metacog_l2_enabled: bool = field(default_factory=lambda: _env("METACOG_L2", True, bool))
    metacog_save_interval: int = field(default_factory=lambda: _env("METACOG_SAVE_INTERVAL", 300, int))

    # Eventos
    event_bus_persist: bool = field(default_factory=lambda: _env("EVENT_BUS_PERSIST", True, bool))

    # Seguridad
    pad_enabled: bool = field(default_factory=lambda: _env("PAD_ENABLED", True, bool))
    rate_limit_chat: int = field(default_factory=lambda: _env("RATE_LIMIT_CHAT", 30, int))

    @property
    def state_path(self) -> Path:
        p = Path(self.state_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def logs_path(self) -> Path:
        p = Path(self.logs_dir)
        p.mkdir(parents=True, exist_ok=True)
        return p

    def as_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        # Ocultar secretos
        if d.get("openai_api_key"):
            d["openai_api_key"] = "***"
        return d

    @classmethod
    def from_file(cls, path: str = "C:/AI_VAULT/settings.json") -> "Settings":
        s = cls()
        f = Path(path)
        if f.exists():
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                for k, v in data.items():
                    if hasattr(s, k):
                        setattr(s, k, v)
            except Exception:
                pass
        return s


_SETTINGS: Optional[Settings] = None

def get_settings() -> Settings:
    global _SETTINGS
    if _SETTINGS is None:
        _SETTINGS = Settings.from_file()
    return _SETTINGS

def reload_settings():
    global _SETTINGS
    _SETTINGS = None
    return get_settings()
