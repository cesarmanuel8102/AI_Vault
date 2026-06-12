from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CompactText:
    original_chars: int
    compact_chars: int
    text: str


def compact_text(text: str, limit: int = 600) -> CompactText:
    value = str(text or "")
    if len(value) <= limit:
        return CompactText(len(value), len(value), value)
    head = value[: max(0, limit - 80)].rstrip()
    compacted = f"{head}\n[compact_truncated original_chars={len(value)}]"
    return CompactText(len(value), len(compacted), compacted)


def compact_cycle_summary(domain: str, decision: str, reason: str, limit: int = 240) -> str:
    return compact_text(f"domain={domain}; decision={decision}; reason={reason}", limit=limit).text
