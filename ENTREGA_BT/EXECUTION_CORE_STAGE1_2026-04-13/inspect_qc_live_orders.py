import argparse
import json
from collections import Counter
from pathlib import Path

from build_phase0_signals_from_qc import (
    extract_symbol,
    fetch_live_orders,
    is_filled,
    load_bridge_config,
    load_qc_credentials,
    parse_timestamp_et,
)


def main() -> None:
    p = argparse.ArgumentParser(description="Inspect QuantConnect live orders for bridge debugging")
    p.add_argument("--config", default="config/qc_signal_bridge.sample.json")
    p.add_argument("--qc-secrets", default=None)
    args = p.parse_args()

    base = Path(__file__).resolve().parent
    cfg = load_bridge_config((base / args.config).resolve())
    creds = load_qc_credentials(args.qc_secrets)

    orders = fetch_live_orders(
        creds=creds,
        project_id=int(cfg["project_id"]),
        deploy_id=str(cfg.get("deploy_id", "") or ""),
        start=int(cfg.get("start", 0)),
        end=int(cfg.get("end", 500)),
    )

    by_symbol = Counter()
    by_date = Counter()
    by_status = Counter()
    filled = 0

    for o in orders:
        sym = extract_symbol(o)
        ts = parse_timestamp_et(o) or ""
        status = str(o.get("status") or o.get("Status") or "?")

        by_symbol[sym] += 1
        if ts:
            by_date[ts[:10]] += 1
        by_status[status] += 1
        if is_filled(o):
            filled += 1

    payload = {
        "orders_total": len(orders),
        "orders_filled_detected": filled,
        "by_symbol": dict(by_symbol.most_common(20)),
        "by_date": dict(by_date.most_common(20)),
        "by_status": dict(by_status.most_common(20)),
    }
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    main()
