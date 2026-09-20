from __future__ import annotations

import re


_ACCOUNT = re.compile(r"\b(?:DU|U)\d{5,}\b", re.IGNORECASE)
_ASSIGNMENT = re.compile(
    r"(?i)\b(EMAIL_PASS|PASSWORD|PASS|TOKEN|AUTH_TOKEN|API_KEY|SECRET)\s*=\s*([^\s,;]+)"
)


def redact_text(text: str) -> str:
    redacted = _ACCOUNT.sub("[REDACTED_ACCOUNT]", text)
    return _ASSIGNMENT.sub(lambda match: f"{match.group(1)}=[REDACTED]", redacted)

