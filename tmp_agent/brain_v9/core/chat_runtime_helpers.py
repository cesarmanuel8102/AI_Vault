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
