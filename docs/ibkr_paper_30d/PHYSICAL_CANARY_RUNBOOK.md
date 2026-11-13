# Dual-sleeve physical PAPER canary

This runbook validates the normal autonomous writer path. It never authorizes
LIVE port 4001, a second writer, a prescribed symbol, or a fabricated economic
signal.

## Invariants

- IB Gateway must be PAPER-only on `127.0.0.1:4002`.
- The deployed Git HEAD must equal `--approved-head` exactly.
- Existing execution lock, watchdog, kill switch, reconciliation, market data,
  quote, what-if, ownership, risk, operator-control, and final writer authority
  gates remain binding.
- Codex chooses the smallest practical liquid contract and quantity. `NO_TRADE`
  is terminal when Codex identifies an exact safety or feasibility blocker.
- Technical-canary fees and P&L are attributed separately from strategy P&L.
- Run `REGULAR_SLEEVE` first. Request `CONTINUOUS_SLEEVE` only after the regular
  projection is `FLAT_RECONCILED`.

## Request

```powershell
python -m ibkr_paper_30d.cli request-physical-canary `
  --database <canonical-database> `
  --sleeve REGULAR_SLEEVE `
  --canary-id regular-e2e-<timestamp> `
  --approved-head <40-character-head> `
  --owner-authorization-sha256 <64-character-authorization-hash>
```

The command appends one durable directive and makes zero broker calls.

## Inspect

```powershell
python -m ibkr_paper_30d.cli inspect-physical-canary `
  --database <canonical-database> `
  --canary-id <canary-id>
```

The inspection command is database-only. It reports projection, broker identity,
registry events, fills, and evidence without connecting to IBKR.

## Terminal handling

- `FLAT_RECONCILED`: broker order absent, position zero, and balanced fill
  history; the next sleeve may be requested.
- `TERMINAL_NO_FILL`: no exposure was created; stop and report.
- `MODEL_DECLINED` or `BLOCKED`: stop and report exact reason codes.
- `UNCERTAIN`: stop immediately. Do not retry, replace, cancel, or submit the
  other sleeve until reconciliation resolves the identity and exposure.
- `BROKER_BOUND` or `ACTIVE_MANAGEMENT`: allow ordinary autonomous cycles to
  manage the order/position; do not impose a time exit.

Never infer flatness merely because an order or position is missing from one
snapshot. Flatness requires reconciled order, position, and execution evidence.
