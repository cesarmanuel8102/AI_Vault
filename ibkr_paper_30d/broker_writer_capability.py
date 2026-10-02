"""Disabled-by-default harness for validating same-client PAPER write ownership."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


DESCRIPTION = {
    "schema": "BROKER_WRITER_CAPABILITY_V1",
    "default_mode": "DESCRIBE_ONLY",
    "connections_performed": 0,
    "writes_performed": 0,
    "required_checks": [
        "single authoritative execution client ID",
        "duplicate connection rejected with IBKR error 326",
        "cross-client reqAllOpenOrders visibility is not write authority",
        "same-client cancel and modify ownership",
        "exact order identity and post-write reconciliation",
    ],
}


def describe() -> dict:
    return dict(DESCRIPTION)


def _paper_probe(receipt_path: Path, runtime_state_path: Path) -> int:
    if not receipt_path.is_file():
        raise PermissionError("ONE_USE_AUTHORIZATION_RECEIPT_REQUIRED")
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PermissionError("ONE_USE_AUTHORIZATION_RECEIPT_INVALID") from exc
    if (
        receipt.get("schema") != "BROKER_WRITER_PAPER_PROBE_AUTHORIZATION_V1"
        or receipt.get("one_use") is not True
        or receipt.get("consumed") is True
    ):
        raise PermissionError("ONE_USE_AUTHORIZATION_RECEIPT_INVALID")
    if runtime_state_path.exists():
        try:
            state = json.loads(runtime_state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise PermissionError("RUNTIME_STATE_UNCERTAIN") from exc
        if state.get("runtime_active") or state.get("open_order_count", 0):
            raise PermissionError("ACTIVE_EXPERIMENT_OR_ORDER_SET")
    raise PermissionError("PAPER_PROBE_IMPLEMENTATION_PHASE_DISABLED")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--describe", action="store_true")
    modes.add_argument("--paper-probe", action="store_true")
    parser.add_argument("--authorization-receipt", type=Path)
    parser.add_argument("--runtime-state", type=Path)
    args = parser.parse_args(argv)
    if args.describe:
        print(json.dumps(describe(), sort_keys=True))
        return 0
    if args.authorization_receipt is None or args.runtime_state is None:
        parser.error("--paper-probe requires --authorization-receipt and --runtime-state")
    try:
        return _paper_probe(args.authorization_receipt, args.runtime_state)
    except PermissionError as exc:
        print(json.dumps({"status": "BLOCKED", "reason": str(exc)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
