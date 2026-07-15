"""Pure helpers for the legacy ``POST /chat`` runtime path.

These helpers intentionally avoid importing Brain runtime, session, indexed
memory, external HTTP clients, or process execution modules. 15C keeps the route
in ``main.py`` and only extracts deterministic predicates/parsing.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Optional


HARMFUL_INTRUSION_MARKERS = (
    "hackea",
    "hackear",
    "rompe la clave",
    "crackea",
    "crackear",
    "entrar al wifi",
    "entrar en el wifi",
    "entrar a un wifi",
    "robar wifi",
    "bypass",
    "saltate",
    "sáltate",
    "credenciales ajenas",
    "wifi vecino",
)

LOCAL_NETWORK_MARKERS = (
    "red local",
    "network",
    "ip local",
    "gateway",
    "scan",
    "escan",
    "cidr",
    "subred",
    "subnet",
    "interfaces",
    "interfaz",
    "host vivo",
    "ping sweep",
    "red wifi",
    "wifi",
    "nmap",
    "puerto abierto",
    "dispositivos conectados",
    "dispositivos observables",
    "hosts activos",
    "bloqueado",
)

LOCAL_NETWORK_EXECUTION_MARKERS = (
    "escan",
    "scan",
    "detecta",
    "ejecut",
    "muestra",
    "lista",
    "enumera",
    "dime",
    "que hosts",
    "cuales hosts",
    "barre",
    "conectados",
)

CODE_INSPECTION_MARKERS = (
    ".py",
    ".json",
    ".md",
    ".ps1",
    "tmp_agent\\",
    "tmp_agent/",
    "brain_v9\\",
    "brain_v9/",
    "core\\",
    "core/",
    "tests\\",
    "tests/",
    "agent\\",
    "agent/",
)

PENDING_ID_PATTERN = re.compile(r"(confirm_\d{8}_\d{6}_\w+)")
PAD_USERNAME_PATTERN = re.compile(r"usuario[=:]\s*(\S+)", re.IGNORECASE)
PAD_PASSWORD_PATTERN = re.compile(r"password[=:]\s*(\S+)", re.IGNORECASE)
PAD_MFA_PATTERN = re.compile(r"mfa[=:]\s*(\S+)", re.IGNORECASE)
PAD_WITNESSES_PATTERN = re.compile(r"testigos\[=\s*([^\]]+)", re.IGNORECASE)

GOD_PRIVILEGE_TERMS = (
    "modo god",
    "modo desarrollador",
    "developer mode",
    "god mode",
)

GOD_EXISTENCE_TERMS = (
    "tienes",
    "existe",
    "hay",
    "implementado",
    "disponible",
    "solo responde si existe",
)

GOD_ACTIVATION_TERMS = (
    "autenticar:",
    "activar",
    "habilitar",
    "entrar",
    "iniciar",
    "bypass",
    "sin restricciones",
    "quita restricciones",
    "elimina restricciones",
)


def _lower_message(message: str) -> str:
    return (message or "").lower()


def looks_like_harmful_intrusion_request(message: str) -> bool:
    """Return true for explicit offensive network/access prompts."""
    msg_low = _lower_message(message)
    return any(marker in msg_low for marker in HARMFUL_INTRUSION_MARKERS)


def is_code_inspection_request(message: str) -> bool:
    """Avoid treating code/file inspection text as a live network scan request."""
    msg_low = _lower_message(message)
    return any(marker in msg_low for marker in CODE_INSPECTION_MARKERS)


def should_scan_local_network(message: str) -> bool:
    """Return true when the message is about local-network visibility."""
    msg_low = _lower_message(message)
    return any(marker in msg_low for marker in LOCAL_NETWORK_MARKERS)


def should_attempt_local_network_tool(message: str) -> bool:
    """Return true only for explicit local-network execution prompts."""
    msg_low = _lower_message(message)
    wants_execution = any(marker in msg_low for marker in LOCAL_NETWORK_EXECUTION_MARKERS)
    return wants_execution and should_scan_local_network(message) and not is_code_inspection_request(message)


def is_safe_god_existence_question(message: str) -> bool:
    """Detect safe questions about whether PAD/GOD exists without activating it."""
    msg_low = _lower_message(message)
    return (
        any(term in msg_low for term in GOD_PRIVILEGE_TERMS)
        and any(term in msg_low for term in GOD_EXISTENCE_TERMS)
        and not any(term in msg_low for term in GOD_ACTIVATION_TERMS)
    )


def is_explicit_god_task(message: str) -> bool:
    """Detect an explicit already-authenticated GOD task command."""
    msg_low = _lower_message(message)
    return (
        msg_low.startswith(("god:", "dev:", "ejecuta:", "comando:", "shell:"))
        or "ejecuta " in msg_low[:20]
    )


def extract_god_task_text(message: str) -> str:
    """Preserve the legacy GOD task-text extraction behavior."""
    message_text = message or ""
    msg_low = message_text.lower()
    if msg_low.startswith(("god:", "dev:")) and ":" in message_text:
        return message_text.split(":", 1)[1].strip()
    return message_text


def parse_pad_credentials(message: str) -> Optional[Dict[str, Any]]:
    """Parse PAD credentials from the legacy chat command format."""
    message_text = message or ""
    if "autenticar:" not in message_text.lower():
        return None

    username = PAD_USERNAME_PATTERN.search(message_text)
    password = PAD_PASSWORD_PATTERN.search(message_text)
    mfa = PAD_MFA_PATTERN.search(message_text)
    witnesses_match = PAD_WITNESSES_PATTERN.search(message_text)
    if not (username and password and mfa):
        return None

    witnesses = witnesses_match.group(1).split(",") if witnesses_match else ["w1", "w2"]
    return {
        "username": username.group(1),
        "password": password.group(1),
        "mfa_code": mfa.group(1),
        "witnesses": witnesses,
    }


def has_pending_action_signal(result: Any, content: str) -> bool:
    """Detect response text/result markers that may carry a pending action id."""
    content_str = content or ""
    return (
        "pending_id" in str(result)
        or "Accion P2" in content_str
        or "requiere confirmacion" in content_str.lower()
    )


def extract_pending_action_from_text(text: str) -> Optional[Dict[str, str]]:
    """Extract the legacy pending_action payload from a response string."""
    content_str = text or ""
    match = PENDING_ID_PATTERN.search(content_str)
    if not match:
        return None

    pending_id = match.group(1)
    tool_parts = pending_id.split("_", 3)
    tool_name = tool_parts[3] if len(tool_parts) > 3 else pending_id
    description = content_str.split("\n")[0] if "\n" in content_str else content_str[:200]
    return {
        "pending_id": pending_id,
        "tool": tool_name,
        "risk": "P2",
        "description": description,
    }
