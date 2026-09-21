from __future__ import annotations

from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, ConfigDict, Field


class ExperimentClock(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    start_at_utc: datetime
    end_at_utc: datetime
    observed_at_utc: datetime
    duration_days: int = Field(gt=0)
    day_index: int = Field(ge=0)
    elapsed_seconds: float = Field(ge=0)
    remaining_seconds: float = Field(ge=0)
    days_remaining: float = Field(ge=0)
    status: str
    expired: bool


def _aware_utc(value: str | datetime) -> datetime:
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    else:
        parsed = value
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError("experiment timestamps must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def build_experiment_clock(
    start_at_utc: str | datetime,
    *,
    observed_at_utc: str | datetime | None = None,
    duration_days: int = 30,
) -> ExperimentClock:
    if duration_days <= 0:
        raise ValueError("duration_days must be positive")
    start = _aware_utc(start_at_utc)
    observed = (
        datetime.now(timezone.utc)
        if observed_at_utc is None
        else _aware_utc(observed_at_utc)
    )
    end = start + timedelta(days=duration_days)

    if observed < start:
        return ExperimentClock(
            start_at_utc=start,
            end_at_utc=end,
            observed_at_utc=observed,
            duration_days=duration_days,
            day_index=0,
            elapsed_seconds=0.0,
            remaining_seconds=(end - start).total_seconds(),
            days_remaining=float(duration_days),
            status="NOT_STARTED",
            expired=False,
        )

    elapsed = max(0.0, (observed - start).total_seconds())
    remaining = max(0.0, (end - observed).total_seconds())
    expired = observed >= end
    day_index = min(duration_days, int(elapsed // 86400) + 1)
    return ExperimentClock(
        start_at_utc=start,
        end_at_utc=end,
        observed_at_utc=observed,
        duration_days=duration_days,
        day_index=day_index,
        elapsed_seconds=elapsed,
        remaining_seconds=remaining,
        days_remaining=remaining / 86400.0,
        status="EXPIRED" if expired else "ACTIVE",
        expired=expired,
    )
