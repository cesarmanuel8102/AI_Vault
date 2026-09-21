from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Literal, Mapping

from pydantic import BaseModel


class Settings(BaseModel, frozen=True):
    paper_only: Literal[True] = True
    broker_write_authorized: Literal[False] = False
    experiment_allocation: Decimal = Decimal("500.00")
    options_permission_level: Literal[4] = 4
    autonomous_research_enabled: Literal[True] = True
    research_round_budget: int = 8
    state_dir: Path = Path("state/ibkr_paper_30d")
    logs_dir: Path = Path("logs/ibkr_paper_30d")

    @classmethod
    def load(cls, env: Mapping[str, str]) -> "Settings":
        if env.get("PAPER_ONLY", "true").lower() != "true":
            raise ValueError("paper-only mode cannot be disabled")
        if env.get("BROKER_WRITE_AUTHORIZED", "false").lower() != "false":
            raise ValueError("broker writes are outside current authority")
        return cls()
