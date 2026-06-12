from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any


@dataclass(frozen=True)
class TokenBudgetPolicy:
    max_prompt_chars: int = 1200
    max_response_chars: int = 1200
    compact_mode: bool = True
    raw_log_dump_default: bool = False
    error_tail_chars: int = 2400
    evidence_files_required: bool = True

    def clamp_prompt(self, prompt: str) -> str:
        text = str(prompt or "")
        if len(text) <= self.max_prompt_chars:
            return text
        return text[: self.max_prompt_chars - 32].rstrip() + "\n[truncated_by_token_policy]"

    def clamp_response(self, response: str) -> str:
        text = str(response or "")
        if len(text) <= self.max_response_chars:
            return text
        return text[: self.max_response_chars - 35].rstrip() + "\n[response_truncated_by_policy]"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


DEFAULT_TOKEN_BUDGET = TokenBudgetPolicy()
