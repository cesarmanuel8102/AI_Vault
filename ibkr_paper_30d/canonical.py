from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import UUID


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (Enum, Path, UUID)):
        return str(value.value if isinstance(value, Enum) else value)
    if is_dataclass(value):
        return asdict(value)
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    raise TypeError(f"unsupported canonical JSON type: {type(value).__name__}")


def canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
        default=_json_default,
    ).encode("utf-8")


def sha256_json(value: object) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()

