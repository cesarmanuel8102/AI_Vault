from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable


@dataclass(frozen=True)
class DialoguePromptProfile:
    profile_id: str
    description: str
    prompt: str
    expected_format: str
    max_tokens: int = 96
    temperature: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _compact_constraints() -> str:
    return (
        "Constraints: no tools, no memory writes, no FAISS writes, no trading, "
        "no secrets, no chain-of-thought. Answer only final content."
    )


PROMPT_PROFILES: tuple[DialoguePromptProfile, ...] = (
    DialoguePromptProfile(
        "exact_output",
        "Exact short answer to verify provider can return deterministic content.",
        "Return exactly: AUTONOMY_OK",
        "exact_text",
        16,
    ),
    DialoguePromptProfile(
        "bullet_only",
        "Three compact bullets for a safe autonomy improvement.",
        f"{_compact_constraints()}\nGive 3 bullets to improve Brain autonomy safely.",
        "bullets",
    ),
    DialoguePromptProfile(
        "json_only",
        "Small JSON object for machine-readable calibration.",
        f"{_compact_constraints()}\nReturn JSON only: {{\"status\":\"ok\",\"next\":\"one safe autonomy improvement\"}}",
        "json",
    ),
    DialoguePromptProfile(
        "role_compressed",
        "Compressed student role prompt.",
        f"You are Brain student. {_compact_constraints()}\nState one low-risk self-improvement.",
        "sentence",
    ),
    DialoguePromptProfile(
        "one_sentence_proposal",
        "Single sentence proposal.",
        f"{_compact_constraints()}\nOne sentence: propose one LOW-risk improvement for operator clarity.",
        "sentence",
    ),
    DialoguePromptProfile(
        "critic",
        "Critique a candidate without hidden reasoning.",
        f"{_compact_constraints()}\nCritique this proposal in 2 bullets: add autonomous scheduler now.",
        "bullets",
    ),
    DialoguePromptProfile(
        "revise",
        "Revise unsafe proposal into safe dry-run.",
        f"{_compact_constraints()}\nRevise safely: write semantic memory from every chat turn.",
        "bullets",
    ),
    DialoguePromptProfile(
        "score",
        "Compact score output.",
        f"{_compact_constraints()}\nScore Brain token efficiency from 0.0 to 1.0 and give one fix.",
        "score_line",
    ),
)


def iter_prompt_profiles() -> Iterable[DialoguePromptProfile]:
    return iter(PROMPT_PROFILES)


def stable_micro_prompt_profile_ids() -> set[str]:
    """Profiles expected to remain safe even when open dialogue is unstable."""
    return {"exact_output", "json_only", "score"}
