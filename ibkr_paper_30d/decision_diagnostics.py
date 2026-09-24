from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any

from .canonical import canonical_bytes, sha256_json
from .types import new_uuid7


REGRET_SCHEMA = "CODEX_REGRET_OBSERVATION_V1"
NO_CANDIDATE_SCHEMA = "CODEX_NO_IDENTIFIABLE_REJECTED_CANDIDATE_V1"
RISK_DIAGNOSTICS_SCHEMA = "CODEX_RISK_DIAGNOSTICS_V1"

IDENTIFIABLE_CANDIDATE_FIELDS = ("symbol",)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _require_identifiable_candidate(candidate: dict[str, Any]) -> None:
    if not isinstance(candidate, dict) or not any(
        str(candidate.get(field) or "").strip()
        for field in IDENTIFIABLE_CANDIDATE_FIELDS
    ):
        raise ValueError(
            "a regret record requires an identifiable candidate with at "
            "least a symbol; never fabricate a candidate from a NO_TRADE"
        )


def build_regret_record(
    *,
    decision_cycle_id: str,
    candidate: dict[str, Any],
    ex_ante_evidence: dict[str, Any],
    rejection_reason_codes: tuple[str, ...] | list[str],
    rejection_mechanism: str = "",
    sample_size: int = 1,
    repeated_mechanism: bool = False,
    uncertainty: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build an observational regret/counterfactual record.

    Rulings encoded here (user corrections 2026-09-23):
    - U2: sample_size and repeated_mechanism are descriptive fields only.
      No numeric threshold may ever transition policy_status; records are
      born OBSERVATION and only an explicit human/owner review can mark a
      hypothesis as under investigation.
    - U4: an identifiable candidate and real ex-ante evidence are required.
      NO_TRADE cycles without a concrete candidate must never produce a
      fabricated regret record.
    """

    _require_identifiable_candidate(candidate)
    if not ex_ante_evidence:
        raise ValueError(
            "a regret record requires real ex-ante evidence; an empty "
            "evidence snapshot cannot support a counterfactual"
        )
    reasons = [str(code) for code in rejection_reason_codes]
    if not reasons:
        raise ValueError("a regret record requires a real rejection reason")
    return {
        "schema": REGRET_SCHEMA,
        "record_id": f"regret-{new_uuid7()}",
        "decision_cycle_id": str(decision_cycle_id),
        "timestamp_utc": _utc_now(),
        "candidate": dict(candidate),
        "ex_ante_evidence": dict(ex_ante_evidence),
        "ex_ante_evidence_sha256": sha256_json(ex_ante_evidence),
        "rejection_reason_codes": reasons,
        "rejection_mechanism": str(
            rejection_mechanism or "MODEL_DECISION_OR_VALIDATION"
        ),
        "ex_post_outcome": None,
        "ex_post_observed_at_utc": None,
        "sample_size": int(sample_size),
        "repeated_mechanism": bool(repeated_mechanism),
        "uncertainty": dict(
            uncertainty
            or {
                "sample_size_note": (
                    "sample_size and repeated_mechanism are descriptive "
                    "observations; no automatic policy conclusion may be "
                    "drawn from any count"
                ),
                "ex_post_outcome_may_be_unobservable": True,
            }
        ),
        "policy_status": "OBSERVATION",
    }


def observation_without_identifiable_candidate(
    *,
    decision_cycle_id: str,
    reason_codes: tuple[str, ...] | list[str],
) -> dict[str, Any]:
    """Observational note for a NO_TRADE with no concrete rejected candidate.

    This is deliberately NOT a regret record: no candidate is fabricated.
    """

    return {
        "schema": NO_CANDIDATE_SCHEMA,
        "observation_type": "NO_IDENTIFIABLE_REJECTED_CANDIDATE",
        "decision_cycle_id": str(decision_cycle_id),
        "timestamp_utc": _utc_now(),
        "reason_codes": [str(code) for code in reason_codes],
    }


def persist_regret_record(db: Any, record: dict[str, Any]) -> str:
    if record.get("schema") not in {REGRET_SCHEMA, NO_CANDIDATE_SCHEMA}:
        raise ValueError("unknown observation schema for persistence")
    event_id = str(new_uuid7())
    payload = {
        "decision_cycle_id": record.get("decision_cycle_id", ""),
        "invocation_id": "observation-only",
        "observation": record,
    }
    encoded = canonical_bytes(payload).decode("utf-8")
    db.execute(
        "INSERT INTO autonomous_research_events("
        "event_id,decision_cycle_id,invocation_id,round_index,event_type,"
        "payload_json,payload_sha256,created_at_utc) VALUES(?,?,?,?,?,?,?,?)",
        (
            event_id,
            str(record.get("decision_cycle_id", "")),
            "observation-only",
            0,
            "regret_observation"
            if record["schema"] == REGRET_SCHEMA
            else "no_identifiable_rejected_candidate",
            encoded,
            sha256_json(payload),
            _utc_now(),
        ),
    )
    return event_id


def load_regret_records(db_path: Any) -> list[dict[str, Any]]:
    from pathlib import Path

    path = Path(db_path)
    if not path.exists():
        return []
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        rows = connection.execute(
            "SELECT payload_json FROM autonomous_research_events "
            "WHERE event_type='regret_observation' ORDER BY created_at_utc, rowid"
        ).fetchall()
    finally:
        connection.close()

    records: list[dict[str, Any]] = []
    for (raw_payload,) in rows:
        try:
            payload = json.loads(str(raw_payload))
        except json.JSONDecodeError:
            continue
        observation = (
            payload.get("observation") if isinstance(payload, dict) else None
        )
        if isinstance(observation, dict):
            records.append(observation)
    return records
def _money_str(value: Any) -> str:
    from decimal import Decimal, InvalidOperation

    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return "unavailable"
    if not parsed.is_finite():
        return "unavailable"
    return str(parsed.quantize(Decimal("0.01")))


def _ratio(numerator: Any, denominator: Any) -> str:
    from decimal import Decimal, InvalidOperation

    try:
        num = Decimal(str(numerator))
        den = Decimal(str(denominator))
    except (InvalidOperation, TypeError, ValueError):
        return "unavailable"
    if den == 0 or not num.is_finite() or not den.is_finite():
        return "unavailable"
    return str((num / den).quantize(Decimal("0.01")))



def _closed_trade_pnls(fills: list[dict[str, Any]] | None) -> list[Any]:
    """Per-closed-trade P&L from the ledger's own validated fill events.

    Ruling U3: no new accounting engine. This is simple aggregation over
    the same append-only BROKER_FILL events the AutonomousExperimentLedger
    already accepts; a contract contributes a closed-trade P&L only when
    its signed quantity returns to exactly zero (full round trip), using
    weighted average open cost. Partial closes are NOT split into multiple
    realized trades — that would require lot accounting the ledger does
    not provide.
    """

    from decimal import Decimal

    if not fills:
        return []
    by_contract: dict[int, list[dict[str, Any]]] = {}
    for fill in fills:
        contract = fill.get("contract") or {}
        contract_id = int(contract.get("conId") or fill.get("contract_id") or 0)
        by_contract.setdefault(contract_id, []).append(fill)

    closed: list[Decimal] = []
    for contract_id in sorted(by_contract):
        open_qty = Decimal("0")
        open_cost = Decimal("0")
        realized = Decimal("0")
        commissions = Decimal("0")
        touched = False
        for fill in by_contract[contract_id]:
            side = str(fill.get("side") or fill.get("action") or "").upper()
            quantity = abs(Decimal(str(fill.get("quantity") or fill.get("shares") or "0")))
            price = Decimal(str(fill.get("price") or "0"))
            multiplier = Decimal(str((fill.get("contract") or {}).get("multiplier") or fill.get("multiplier") or "1"))
            commission = Decimal(str(fill.get("commission") or "0"))
            commissions += commission
            touched = True
            signed = quantity if side == "BUY" else -quantity
            if open_qty == 0 or (open_qty > 0) == (signed > 0):
                open_qty += signed
                open_cost += quantity * price * multiplier
            else:
                closing = min(quantity, abs(open_qty))
                avg_cost = open_cost / abs(open_qty) if open_qty != 0 else Decimal("0")
                direction = Decimal("1") if open_qty > 0 else Decimal("-1")
                proceeds = closing * price * multiplier
                basis = closing * avg_cost
                realized += (proceeds - basis) * direction
                open_qty += direction * closing * Decimal("-1")
                open_cost -= closing * avg_cost
                if open_cost < 0:
                    open_cost = Decimal("0")
                leftover = quantity - closing
                if leftover > 0:
                    open_qty = leftover if signed > 0 else -leftover
                    open_cost = leftover * price * multiplier
        if touched and open_qty == 0:
            closed.append(realized - commissions)
    return closed


def build_risk_diagnostics(state: Any, *, fills: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Observational risk diagnostics from an existing ledger projection.

    Ruling U3 (user correction 2026-09-23): continuous metrics only — no
    invented threshold flags, no labels from magic percentages. Metrics the
    current ledger state cannot support honestly are reported as
    "unavailable" instead of being estimated. These numbers exist to
    interpret terminal results; they are diagnostics only and are never
    consumed by validation, sizing or authorization paths.
    """

    from decimal import Decimal

    allocation = getattr(state, "allocation", None)
    equity = getattr(state, "equity", None)
    positions = tuple(getattr(state, "positions", ()) or ())
    fees = getattr(state, "fees", None)
    drawdown = getattr(state, "drawdown", None)

    closed_pnls = _closed_trade_pnls(fills)

    traded_notional = Decimal("0")
    if fills is not None:
        for fill in fills:
            quantity = abs(
                Decimal(str(fill.get("quantity") or fill.get("shares") or "0"))
            )
            price = Decimal(str(fill.get("price") or "0"))
            multiplier = Decimal(
                str(
                    (fill.get("contract") or {}).get("multiplier")
                    or fill.get("multiplier")
                    or "1"
                )
            )
            traded_notional += quantity * price * multiplier

    wins = [pnl for pnl in closed_pnls if pnl > 0]
    losses = [pnl for pnl in closed_pnls if pnl < 0]
    win_total = sum(wins, Decimal("0"))
    loss_total = sum((abs(p) for p in losses), Decimal("0"))
    largest_win = max(wins, default=Decimal("0"))
    largest_loss = max((abs(p) for p in losses), default=Decimal("0"))
    realized = sum(closed_pnls, Decimal("0"))

    unrealized = (
        Decimal(str(equity or "0"))
        - Decimal(str(allocation or "0"))
        - realized
    )

    gross = sum(
        (abs(Decimal(str(getattr(p, "market_value", "0")))) for p in positions),
        Decimal("0"),
    )
    net = sum(
        (Decimal(str(getattr(p, "market_value", "0"))) for p in positions),
        Decimal("0"),
    )
    largest_position_value = max(
        (abs(Decimal(str(getattr(p, "market_value", "0")))) for p in positions),
        default=Decimal("0"),
    )

    if wins and losses:
        payoff_asymmetry = _ratio(win_total / len(wins), loss_total / len(losses))
    else:
        payoff_asymmetry = "unavailable"
    profit_concentration = (
        _ratio(largest_win, win_total) if win_total > 0 else "unavailable"
    )

    if fills is None:
        # Without the ledger's fill events, per-trade realized P&L cannot be
        # computed honestly. Report unavailable rather than relabeling
        # equity drift as unrealized P&L or fabricating trade counts.
        realized_str = "unavailable"
        unrealized_str = "unavailable"
        win_count: object = "unavailable"
        loss_count: object = "unavailable"
        largest_winner_str = "unavailable"
        largest_loser_str = "unavailable"
        payoff_asymmetry = "unavailable"
        profit_concentration = "unavailable"
        turnover = "unavailable"
    else:
        realized_str = _money_str(realized)
        unrealized_str = _money_str(unrealized)
        win_count = len(wins)
        loss_count = len(losses)
        largest_winner_str = _money_str(largest_win)
        largest_loser_str = _money_str(largest_loss)
        turnover = (
            _ratio(traded_notional, allocation)
            if traded_notional > 0
            else "0.00"
        )

    return {
        "schema": RISK_DIAGNOSTICS_SCHEMA,
        "diagnostic_status": "OBSERVATION_ONLY",
        "current_equity": _money_str(equity),
        "realized_pnl": realized_str,
        "unrealized_pnl": unrealized_str,
        "max_drawdown": _money_str(drawdown),
        "equity_variability": "unavailable",
        "gross_exposure": _money_str(gross),
        "net_exposure": _money_str(net),
        "turnover": turnover,
        "win_count": win_count,
        "loss_count": loss_count,
        "payoff_asymmetry": payoff_asymmetry,
        "largest_winner_contribution": largest_winner_str,
        "largest_loser_contribution": largest_loser_str,
        "profit_concentration": profit_concentration,
        "time_under_water": "unavailable",
        "largest_position_fraction": _ratio(largest_position_value, gross),
        "peak_gross_exposure_ratio": _ratio(gross, allocation),
        "capital_utilization": _ratio(gross, allocation),
    }


REGRET_OUTCOME_SCHEMA = "CODEX_REGRET_OUTCOME_V1"
ANALYTICAL_FAILURE_SCHEMA = "CODEX_ANALYTICAL_OBSERVER_FAILURE_V1"
RISK_DIAGNOSTICS_EVENT = "risk_diagnostics"


def extract_regret_observations(
    outcome: Any, *, rejection_mechanism: str, decision_cycle_id: str = ""
) -> list[dict[str, Any]]:
    """Extract regret observations from a REAL cycle transcript.

    Only identifiable candidates that were actually proposed and then
    rejected by observable validation evidence produce records. Nothing is
    fabricated: no proposal, no rejection evidence, no record. This
    function is pure analysis over the in-memory transcript and never
    touches the broker, risk, sizing or authorization.
    """

    records: list[dict[str, Any]] = []
    transcripts = list(getattr(outcome, "transcript", ()) or ())
    validations: dict[int, dict[str, Any]] = {}
    for event in transcripts:
        if event.get("type") != "proposal_validation":
            continue
        payload = dict(event.get("payload") or {})
        if payload.get("passed") is False:
            validations[int(event.get("round") or 0)] = payload

    for event in transcripts:
        if event.get("type") != "model_turn":
            continue
        payload = dict(event.get("payload") or {})
        if str(payload.get("decision") or "") != "PROPOSE_TRADE":
            continue
        proposal = payload.get("proposal")
        if not isinstance(proposal, dict):
            continue
        symbol = str(proposal.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        round_index = int(event.get("round") or 0)
        validation = validations.get(round_index)
        if validation is None:
            continue
        reasons = tuple(str(code) for code in (validation.get("reason_codes") or ()))
        if not reasons:
            continue
        ex_ante_evidence = {
            "proposal": {
                key: str(value)
                for key, value in proposal.items()
                if key
                in (
                    "symbol",
                    "sec_type",
                    "direction",
                    "action",
                    "quantity",
                    "order_type",
                    "limit_price",
                    "expiry",
                    "strike",
                    "right",
                    "maximum_loss",
                    "loss_is_bounded",
                    "entry_condition",
                    "thesis",
                    "catalyst",
                )
            },
            "broker_evidence": {
                key: value
                for key, value in dict(validation.get("broker_evidence") or {}).items()
                if isinstance(value, (str, int, float, bool))
            },
        }
        if not ex_ante_evidence["broker_evidence"]:
            ex_ante_evidence["broker_evidence"] = {
                "validation_passed": False
            }
        records.append(
            build_regret_record(
                decision_cycle_id=str(decision_cycle_id),
                candidate={
                    "symbol": symbol,
                    "sec_type": str(proposal.get("sec_type") or ""),
                },
                ex_ante_evidence=ex_ante_evidence,
                rejection_reason_codes=reasons,
                rejection_mechanism=rejection_mechanism,
            )
        )
    return records


def _cycle_id_from_transcript(transcripts: list[dict[str, Any]]) -> str:
    for event in transcripts:
        cycle = event.get("decision_cycle_id")
        if cycle:
            return str(cycle)
    return ""


def _observation_from_row(raw_payload: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(str(raw_payload))
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    observation = payload.get("observation")
    return observation if isinstance(observation, dict) else None


def load_pending_regret_records(db: Any) -> list[dict[str, Any]]:
    """Regret records with no ex-post outcome yet (read-only structural read)."""

    rows = db.execute(
        "SELECT payload_json FROM autonomous_research_events "
        "WHERE event_type='regret_observation' ORDER BY created_at_utc, rowid"
    ).fetchall()
    resolved = load_regret_outcome_source_keys(db)
    pending: list[dict[str, Any]] = []
    for (raw_payload,) in rows:
        observation = _observation_from_row(raw_payload)
        if observation is None:
            continue
        record_id = str(observation.get("record_id") or "")
        if not record_id or record_id in resolved:
            continue
        pending.append(observation)
    return pending


def load_regret_outcome_source_keys(db: Any) -> set[str]:
    """Already-persisted (regret_record_id, source_event_sha256) keys."""

    rows = db.execute(
        "SELECT payload_json FROM autonomous_research_events "
        "WHERE event_type='regret_outcome'"
    ).fetchall()
    keys: set[str] = set()
    for (raw_payload,) in rows:
        observation = _observation_from_row(raw_payload)
        if observation is None:
            continue
        keys.add(_outcome_source_key(observation))
    return keys


def _outcome_source_key(observation: dict[str, Any]) -> str:
    return "{record}:{source}".format(
        record=str(observation.get("regret_record_id") or ""),
        source=str(observation.get("source_event_sha256") or ""),
    )


def match_post_outcome_observations(
    pending: list[dict[str, Any]],
    transcript: list[dict[str, Any]],
    *,
    current_cycle_id: str,
) -> list[dict[str, Any]]:
    """Match pending regrets against ALREADY-OBSERVED tool results.

    Strictly observational: this never requests market data, never calls
    the broker and never executes research. It only consumes results that
    the runtime legitimately observed in the current cycle's transcript.
    A cycle can never resolve its own rejection (same-cycle filter).
    """

    matches: list[dict[str, Any]] = []
    for event in transcript:
        if event.get("type") != "research_result":
            continue
        payload = dict(event.get("payload") or {})
        if str(payload.get("tool") or "") != "QUOTE":
            continue
        if payload.get("success") is not True:
            continue
        data = dict(payload.get("data") or {})
        contract = dict(data.get("contract") or {})
        observed_symbol = str(contract.get("symbol") or "").strip().upper()
        if not observed_symbol:
            continue
        price, price_source = _observable_quote_price(data)
        if price is None:
            continue
        source_event = {
            "type": "research_result",
            "round": event.get("round"),
            "tool": "QUOTE",
            "symbol": observed_symbol,
            "price": price,
            "price_source": price_source,
            "request_id": str(payload.get("request_id") or ""),
        }
        for record in pending:
            candidate = dict(record.get("candidate") or {})
            record_symbol = str(candidate.get("symbol") or "").strip().upper()
            if record_symbol != observed_symbol:
                continue
            if str(record.get("decision_cycle_id") or "") == str(current_cycle_id):
                continue
            matches.append(
                {
                    "schema": REGRET_OUTCOME_SCHEMA,
                    "regret_record_id": str(record.get("record_id") or ""),
                    "decision_cycle_id": str(record.get("decision_cycle_id") or ""),
                    "observed_at_utc": _utc_now(),
                    "observed_symbol": observed_symbol,
                    "observed_value": price,
                    "price_source": price_source,
                    "source_event_sha256": sha256_json(source_event),
                    "sample_size": int(record.get("sample_size") or 1) + 1,
                    "repeated_mechanism": bool(record.get("repeated_mechanism")),
                    "policy_status": "OBSERVATION",
                }
            )
    return matches


def _observable_quote_price(data: dict[str, Any]) -> tuple[str | None, str]:
    from decimal import Decimal, InvalidOperation

    def _finite(value: Any) -> Decimal | None:
        try:
            parsed = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return None
        return parsed if parsed.is_finite() and parsed > 0 else None

    last = _finite(data.get("last"))
    if last is not None:
        return str(last), "last"
    bid = _finite(data.get("bid"))
    ask = _finite(data.get("ask"))
    if bid is not None and ask is not None and bid <= ask:
        return str((bid + ask) / 2), "mid"
    return None, ""


def persist_regret_outcome(db: Any, observation: dict[str, Any]) -> str:
    if observation.get("schema") != REGRET_OUTCOME_SCHEMA:
        raise ValueError("unknown regret outcome schema for persistence")
    event_id = str(new_uuid7())
    payload = {
        "decision_cycle_id": str(observation.get("decision_cycle_id") or ""),
        "invocation_id": "observation-only",
        "observation": observation,
    }
    db.execute(
        "INSERT INTO autonomous_research_events("
        "event_id,decision_cycle_id,invocation_id,round_index,event_type,"
        "payload_json,payload_sha256,created_at_utc) VALUES(?,?,?,?,?,?,?,?)",
        (
            event_id,
            str(observation.get("decision_cycle_id") or ""),
            "observation-only",
            0,
            "regret_outcome",
            canonical_bytes(payload).decode("utf-8"),
            sha256_json(payload),
            _utc_now(),
        ),
    )
    return event_id


def persist_analytical_failure(
    db: Any, *, stage: str, error_class: str, decision_cycle_id: str
) -> str:
    """Sanitized note when the analytical observer itself fails.

    Only the observer's own analysis failures land here — never structural
    SQLite/ledger/identity/authorization errors, which keep propagating.
    The note carries stage + error class only; no raw messages or
    tracebacks are persisted.
    """

    event_id = str(new_uuid7())
    note = {
        "schema": ANALYTICAL_FAILURE_SCHEMA,
        "stage": str(stage),
        "error_class": str(error_class),
        "decision_cycle_id": str(decision_cycle_id),
        "timestamp_utc": _utc_now(),
        "authoritative": False,
    }
    payload = {
        "decision_cycle_id": str(decision_cycle_id),
        "invocation_id": "observation-only",
        "observation": note,
    }
    db.execute(
        "INSERT INTO autonomous_research_events("
        "event_id,decision_cycle_id,invocation_id,round_index,event_type,"
        "payload_json,payload_sha256,created_at_utc) VALUES(?,?,?,?,?,?,?,?)",
        (
            event_id,
            str(decision_cycle_id),
            "observation-only",
            0,
            "analytical_observer_failure",
            canonical_bytes(payload).decode("utf-8"),
            sha256_json(payload),
            _utc_now(),
        ),
    )
    return event_id


def persist_risk_diagnostics(
    db: Any,
    *,
    decision_cycle_id: str,
    invocation_id: str,
    rounds: int,
    diagnostics: dict[str, Any],
) -> str:
    event_id = str(new_uuid7())
    payload = {
        "decision_cycle_id": str(decision_cycle_id),
        "invocation_id": str(invocation_id),
        "rounds": int(rounds),
        "observation": diagnostics,
    }
    db.execute(
        "INSERT INTO autonomous_research_events("
        "event_id,decision_cycle_id,invocation_id,round_index,event_type,"
        "payload_json,payload_sha256,created_at_utc) VALUES(?,?,?,?,?,?,?,?)",
        (
            event_id,
            str(decision_cycle_id),
            str(invocation_id),
            int(rounds),
            RISK_DIAGNOSTICS_EVENT,
            canonical_bytes(payload).decode("utf-8"),
            sha256_json(payload),
            _utc_now(),
        ),
    )
    return event_id
