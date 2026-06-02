"""B7-STRANGLER-08: Token-aware truncation / context budget helpers.

This module contains the token-aware context truncation helpers extracted
from ``brain_v9.core.session.BrainSession``:

    - :data:`MAX_MSG_CHARS`         (default per-message tail-truncation budget)
    - :func:`truncate_message`      (single-message tail-truncation)
    - :func:`truncate_to_budget`    (history pruning to fit a token budget)

It was extracted verbatim from ``brain_v9/core/session.py`` during the B7
strangler refactor to reduce the size of ``session.py`` and isolate the
context-budget logic.

Backward compatibility is preserved by ``BrainSession`` via:

    - ``BrainSession._MAX_MSG_CHARS``       (class attr re-bind to ``MAX_MSG_CHARS``)
    - ``BrainSession._truncate_message``    (``@staticmethod`` shim)
    - ``BrainSession._truncate_to_budget``  (``@classmethod`` shim)

No behavioral change vs. pre-extraction code.

Public API:
    - :data:`MAX_MSG_CHARS`
    - :func:`truncate_message`
    - :func:`truncate_to_budget`

This module deliberately has no dependency on
``brain_v9.core.session`` to avoid circular imports, and uses only the
already-existing :class:`brain_v9.core.llm.LLMManager` for token estimation.
"""

from __future__ import annotations

import logging
from typing import Dict, List

from brain_v9.core.llm import LLMManager

# Module-level logger — mirrors the diagnostic line emitted by the original
# BrainSession._truncate_to_budget classmethod.  Using a dedicated child
# logger keeps the message routable while matching the original "BrainSession"
# format string verbatim.
log = logging.getLogger("session_context_budget")

# Maximum characters per single message before tail-truncation
# (~2000 tokens at 3.0 chars/token).  Mirrors ``BrainSession._MAX_MSG_CHARS``.
MAX_MSG_CHARS: int = 6000

__all__ = [
    "MAX_MSG_CHARS",
    "truncate_message",
    "truncate_to_budget",
]


def truncate_message(msg: Dict, max_chars: int) -> Dict:
    """Tail-truncate a single message if it exceeds *max_chars*.

    Behaviour preserved verbatim from the original
    ``BrainSession._truncate_message`` staticmethod:

        - If ``len(content) <= max_chars``, returns the original ``msg``
          object unchanged (same identity, no copy).
        - Otherwise returns a NEW dict (``{**msg, "content": truncated}``)
          where ``truncated`` is the first ``max_chars`` characters followed
          by the literal marker ``"\\n... [truncado por longitud]"``.
        - Other fields (``role``, timestamps, metadata, …) are preserved.
        - The original input ``msg`` is never mutated.
    """
    content = msg.get("content", "")
    if len(content) <= max_chars:
        return msg
    truncated = content[:max_chars] + "\n... [truncado por longitud]"
    return {**msg, "content": truncated}


def truncate_to_budget(
    history: List[Dict],
    *,
    budget_tokens: int,
    max_msg_chars: int = 0,
    max_msg_chars_default: int = MAX_MSG_CHARS,
) -> List[Dict]:
    """Return the most-recent slice of *history* that fits within *budget_tokens*.

    Behaviour preserved verbatim from the original
    ``BrainSession._truncate_to_budget`` classmethod:

        1. If ``max_msg_chars <= 0``, fall back to ``max_msg_chars_default``
           (which the BrainSession shim binds to ``cls._MAX_MSG_CHARS``,
           matching the original ``cls._MAX_MSG_CHARS`` lookup).
        2. Tail-truncate every individual oversized message via
           :func:`truncate_message`.
        3. Compute per-message token cost as
           ``4 + LLMManager.estimate_tokens(content)`` (4-token overhead
           preserved from the original).
        4. Drop the oldest messages first until the running total fits in
           ``budget_tokens``.
        5. Emit the same ``log.info`` diagnostic line as the original when
           any messages were dropped.

    The system message (if any) is NOT expected here — callers should
    pass only user/assistant history, exactly as before.
    """
    if max_msg_chars <= 0:
        max_msg_chars = max_msg_chars_default

    # First pass: tail-truncate any individual oversized messages
    trimmed: List[Dict] = [
        truncate_message(m, max_msg_chars) for m in history
    ]

    # Compute tokens for each message (4 overhead + content estimate)
    costs = [
        4 + LLMManager.estimate_tokens(m.get("content", ""))
        for m in trimmed
    ]

    # Drop oldest messages until we fit in budget
    total = sum(costs)
    start = 0
    while total > budget_tokens and start < len(costs):
        total -= costs[start]
        start += 1

    result = trimmed[start:]
    if start > 0:
        log.info(
            "Context truncation: dropped %d oldest messages "
            "(budget=%d tokens, kept=%d msgs)",
            start, budget_tokens, len(result),
        )
    return result
