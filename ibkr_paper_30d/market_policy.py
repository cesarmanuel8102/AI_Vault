from __future__ import annotations

import hashlib
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field

from .canonical import canonical_bytes
from .market_data import MarketDataPolicy
from .market_observation_ledger import MarketObservationLedger
from .market_observation_collector import MARKET_OBSERVATION_COLLECTOR_VERSION


class DistributionStatistics(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    count: int = Field(ge=0)
    minimum_ms: int | None
    median_ms: int | None
    p95_ms: int | None
    p99_ms: int | None
    maximum_ms: int | None
    iqr_ms: int | None
    missing_rate: float = Field(ge=0, le=1)
    rejection_rate: float = Field(ge=0, le=1)


class PolicyStatistics(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    accepted_count: int = Field(ge=0)
    rejected_count: int = Field(ge=0)
    per_symbol_accepted_count: dict[str, int]
    quote_age: DistributionStatistics
    receipt_latency: DistributionStatistics
    absolute_clock_skew: DistributionStatistics
    by_symbol: dict[str, dict[str, DistributionStatistics]]

    @property
    def p99_quote_age_ms(self) -> int:
        return int(self.quote_age.p99_ms or 0)

    @property
    def quote_age_iqr_ms(self) -> int:
        return int(self.quote_age.iqr_ms or 0)

    @property
    def p99_absolute_clock_skew_ms(self) -> int:
        return int(self.absolute_clock_skew.p99_ms or 0)

    @property
    def clock_skew_iqr_ms(self) -> int:
        return int(self.absolute_clock_skew.iqr_ms or 0)


class MarketPolicyArtifact(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    schema_id: str = Field(alias="schema")
    policy_version: str
    predecessor_sha256: str | None
    created_at_utc: datetime
    evidence: dict[str, Any]
    statistics: PolicyStatistics
    controls: MarketDataPolicy
    rationale: dict[str, int]
    policy_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class PolicyFreezeResult(BaseModel, frozen=True):
    model_config = ConfigDict(extra="forbid")

    status: str
    reason_codes: tuple[str, ...] = ()
    policy: MarketDataPolicy | None = None
    statistics: PolicyStatistics | None = None
    artifact_sha256: str | None = None


class MarketPolicyFreezer:
    REQUIRED_SYMBOLS = frozenset({"SPY", "QQQ", "IEF"})

    def __init__(self, *, now_utc: Callable[[], datetime] | None = None) -> None:
        self.now_utc = now_utc or (lambda: datetime.now(timezone.utc))

    def freeze(
        self,
        ledger: MarketObservationLedger,
        destination: str | Path,
        version: str = "MARKET_DATA_POLICY_V1",
        *,
        predecessor_sha256: str | None = None,
        predecessor_path: str | Path | None = None,
    ) -> PolicyFreezeResult:
        verification = ledger.verify()
        if not verification.valid or verification.status != "VALID":
            return PolicyFreezeResult(
                status="BLOCK", reason_codes=("LEDGER_INTEGRITY_FAILURE",)
            )
        if not self._valid_predecessor(version, predecessor_sha256, predecessor_path):
            return PolicyFreezeResult(
                status="PREDECESSOR_MISMATCH",
                reason_codes=("PREDECESSOR_MISMATCH",),
            )

        records = self._read_records(ledger.path)
        reasons = self._protocol_reasons(records)
        if reasons:
            return PolicyFreezeResult(status="BLOCK", reason_codes=tuple(reasons))

        statistics = self._statistics(records)
        quote_p99 = statistics.p99_quote_age_ms
        quote_iqr = statistics.quote_age_iqr_ms
        skew_p99 = statistics.p99_absolute_clock_skew_ms
        skew_iqr = statistics.clock_skew_iqr_ms
        age_margin = max(250, 2 * quote_iqr)
        max_new = _ceil_to(quote_p99 + age_margin, 100)
        max_management = _ceil_to(max(2 * max_new, quote_p99 + 1_000), 100)
        skew_margin = max(100, 2 * skew_iqr)
        max_skew = _ceil_to(skew_p99 + skew_margin, 50)
        thresholds = (max_new, max_management, max_skew)
        if any(not math.isfinite(value) or value < 0 for value in thresholds):
            return PolicyFreezeResult(
                status="BLOCK", reason_codes=("INVALID_COMPUTED_THRESHOLD",)
            )

        policy = MarketDataPolicy(
            version=version,
            max_new_trade_age_ms=max_new,
            max_position_management_age_ms=max_management,
            max_clock_skew_ms=max_skew,
            require_realtime_for_new_trade=True,
            require_bid_ask_for_spread=True,
        )
        ledger_bytes = ledger.path.read_bytes()
        accepted = [record for record in records if record.get("accepted") is True]
        window_manifests = []
        seen_windows: set[str] = set()
        for record in accepted:
            manifest = record["window"]
            if manifest["window_id"] not in seen_windows:
                window_manifests.append(manifest)
                seen_windows.add(manifest["window_id"])
        evidence = {
            "ledger_sha256": hashlib.sha256(ledger_bytes).hexdigest(),
            "ledger_record_count": len(records),
            "ledger_last_record_sha256": verification.last_record_sha256,
            "evidence_start_utc": min(
                record["broker_quote_timestamp"] for record in accepted
            ),
            "evidence_end_utc": max(
                record["broker_quote_timestamp"] for record in accepted
            ),
            "accepted_windows": window_manifests,
            "symbols": sorted({record["symbol"] for record in accepted}),
            "source": "IBKR",
            "collector_version": MARKET_OBSERVATION_COLLECTOR_VERSION,
            "session_classes": sorted({record["market_session"] for record in records}),
            "entitlement_states": sorted(
                {record["entitlement_state"] for record in records}
            ),
        }
        rationale = {
            "p99_quote_age_ms": quote_p99,
            "quote_age_iqr_ms": quote_iqr,
            "age_margin_ms": age_margin,
            "p99_absolute_clock_skew_ms": skew_p99,
            "clock_skew_iqr_ms": skew_iqr,
            "skew_margin_ms": skew_margin,
        }
        unsigned = {
            "schema": "MARKET_DATA_POLICY_V1",
            "policy_version": version,
            "predecessor_sha256": predecessor_sha256,
            "created_at_utc": self.now_utc(),
            "evidence": evidence,
            "statistics": statistics.model_dump(mode="json"),
            "controls": policy.model_dump(mode="json"),
            "rationale": rationale,
        }

        target = Path(destination).absolute()
        if target.exists():
            return self._existing_result(
                target,
                version=version,
                predecessor_sha256=predecessor_sha256,
                evidence=evidence,
                statistics=statistics,
                policy=policy,
                rationale=rationale,
            )
        digest = hashlib.sha256(canonical_bytes(unsigned)).hexdigest()
        artifact = {**unsigned, "policy_sha256": digest}
        target.parent.mkdir(parents=True, exist_ok=True)
        try:
            with target.open("xb") as handle:
                handle.write(canonical_bytes(artifact))
                handle.flush()
                os.fsync(handle.fileno())
        except FileExistsError:
            return PolicyFreezeResult(
                status="VERSION_CONFLICT", reason_codes=("VERSION_CONFLICT",)
            )
        loaded = load_verified_policy(target)
        if loaded != policy:
            raise RuntimeError("POLICY_DURABLE_READBACK_FAILED")
        return PolicyFreezeResult(
            status="PASS",
            policy=policy,
            statistics=statistics,
            artifact_sha256=digest,
        )

    def _existing_result(
        self,
        target: Path,
        *,
        version: str,
        predecessor_sha256: str | None,
        evidence: dict[str, Any],
        statistics: PolicyStatistics,
        policy: MarketDataPolicy,
        rationale: dict[str, int],
    ) -> PolicyFreezeResult:
        try:
            payload = _load_artifact_payload(target)
        except ValueError:
            return PolicyFreezeResult(
                status="VERSION_CONFLICT", reason_codes=("VERSION_CONFLICT",)
            )
        same = (
            payload.get("policy_version") == version
            and payload.get("predecessor_sha256") == predecessor_sha256
            and payload.get("evidence") == evidence
            and payload.get("statistics") == statistics.model_dump(mode="json")
            and payload.get("controls") == policy.model_dump(mode="json")
            and payload.get("rationale") == rationale
        )
        if not same:
            return PolicyFreezeResult(
                status="VERSION_CONFLICT", reason_codes=("VERSION_CONFLICT",)
            )
        return PolicyFreezeResult(
            status="ALREADY_FROZEN",
            policy=policy,
            statistics=statistics,
            artifact_sha256=str(payload["policy_sha256"]),
        )

    @staticmethod
    def _valid_predecessor(
        version: str,
        predecessor_sha256: str | None,
        predecessor_path: str | Path | None,
    ) -> bool:
        if version == "MARKET_DATA_POLICY_V1":
            return predecessor_sha256 is None and predecessor_path is None
        if predecessor_sha256 is None or predecessor_path is None:
            return False
        try:
            payload = _load_artifact_payload(Path(predecessor_path))
        except (ValueError, OSError):
            return False
        return payload.get("policy_sha256") == predecessor_sha256

    @staticmethod
    def _read_records(path: Path) -> list[dict[str, Any]]:
        return [
            json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
        ]

    def _protocol_reasons(self, records: list[dict[str, Any]]) -> list[str]:
        reasons: list[str] = []
        accepted = [record for record in records if record.get("accepted") is True]
        regular = [
            record for record in accepted if record.get("market_session") == "REGULAR"
        ]
        if not regular or len(regular) != len(accepted):
            reasons.append("REGULAR_SESSION_EVIDENCE_REQUIRED")
        windows: dict[str, dict[str, Any]] = {}
        for record in regular:
            manifest = record.get("window", {})
            window_id = str(manifest.get("window_id", ""))
            windows.setdefault(window_id, manifest)
        ordered_windows = sorted(
            windows.values(), key=lambda item: str(item.get("started_at_utc", ""))
        )
        if len(ordered_windows) < 3:
            reasons.append("WINDOW_COUNT_INSUFFICIENT")
        if any(
            _parse_time(item["ended_at_utc"]) - _parse_time(item["started_at_utc"])
            < _minutes(5)
            for item in ordered_windows
        ):
            reasons.append("WINDOW_DURATION_INSUFFICIENT")
        starts = [_parse_time(item["started_at_utc"]) for item in ordered_windows]
        if any(
            later - earlier < _minutes(30) for earlier, later in zip(starts, starts[1:])
        ):
            reasons.append("WINDOW_SEPARATION_INSUFFICIENT")
        if len(accepted) < 540:
            reasons.append("OBSERVATION_COUNT_INSUFFICIENT")
        symbols = {str(record.get("symbol")) for record in accepted}
        counts = {
            symbol: sum(record.get("symbol") == symbol for record in accepted)
            for symbol in symbols
        }
        if not self.REQUIRED_SYMBOLS <= symbols or any(
            counts.get(symbol, 0) < 180 for symbol in self.REQUIRED_SYMBOLS
        ):
            reasons.append("SYMBOL_SET_INSUFFICIENT")
        if accepted:
            broker_times = [
                _parse_time(str(record["broker_quote_timestamp"]))
                for record in accepted
                if record.get("broker_quote_timestamp")
            ]
            if len(broker_times) != len(accepted):
                reasons.append("BROKER_TIMESTAMP_EVIDENCE_INCOMPLETE")
            else:
                broker_times.sort()
                if broker_times[-1] - broker_times[0] < _minutes(65):
                    reasons.append("EVIDENCE_SPAN_INSUFFICIENT")
        entitlement_by_symbol: dict[str, set[str]] = {}
        for record in records:
            entitlement_by_symbol.setdefault(str(record.get("symbol")), set()).add(
                str(record.get("entitlement_state"))
            )
        if any(
            len(states) != 1 or states != {"AVAILABLE"}
            for states in entitlement_by_symbol.values()
        ):
            reasons.append("ENTITLEMENT_CONFLICT")
        required_fields = (
            "corrected_quote_age_ms",
            "raw_quote_age_ms",
            "clock_skew_ms",
            "broker_quote_timestamp",
            "local_receipt_timestamp",
        )
        if any(
            record.get("realtime_or_delayed") != "REALTIME"
            or record.get("source_health") != "HEALTHY"
            or record.get("bid") is None
            or record.get("ask") is None
            or any(record.get(field) is None for field in required_fields)
            for record in accepted
        ):
            reasons.append("OBSERVATION_PROVENANCE_INVALID")
        return list(dict.fromkeys(reasons))

    def _statistics(self, records: list[dict[str, Any]]) -> PolicyStatistics:
        accepted = [record for record in records if record.get("accepted") is True]
        rejected_count = len(records) - len(accepted)
        rejection_rate = rejected_count / len(records) if records else 1.0

        def distributions(
            subset: list[dict[str, Any]],
        ) -> dict[str, DistributionStatistics]:
            return {
                "quote_age": _distribution(
                    [item.get("corrected_quote_age_ms") for item in subset],
                    len(subset),
                    rejection_rate,
                ),
                "receipt_latency": _distribution(
                    [item.get("raw_quote_age_ms") for item in subset],
                    len(subset),
                    rejection_rate,
                ),
                "absolute_clock_skew": _distribution(
                    [
                        (
                            abs(int(item["clock_skew_ms"]))
                            if item.get("clock_skew_ms") is not None
                            else None
                        )
                        for item in subset
                    ],
                    len(subset),
                    rejection_rate,
                ),
            }

        aggregate = distributions(accepted)
        symbols = sorted({str(item["symbol"]) for item in accepted})
        by_symbol = {
            symbol: distributions(
                [item for item in accepted if item["symbol"] == symbol]
            )
            for symbol in symbols
        }
        return PolicyStatistics(
            accepted_count=len(accepted),
            rejected_count=rejected_count,
            per_symbol_accepted_count={
                symbol: sum(item["symbol"] == symbol for item in accepted)
                for symbol in symbols
            },
            quote_age=aggregate["quote_age"],
            receipt_latency=aggregate["receipt_latency"],
            absolute_clock_skew=aggregate["absolute_clock_skew"],
            by_symbol=by_symbol,
        )


def load_verified_policy(path: str | Path) -> MarketDataPolicy:
    payload = _load_artifact_payload(Path(path))
    try:
        return MarketDataPolicy.model_validate(payload["controls"])
    except (KeyError, ValueError) as exc:
        raise ValueError("POLICY_INVALID") from exc


def _load_artifact_payload(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError
        claimed = payload["policy_sha256"]
        unsigned = dict(payload)
        unsigned.pop("policy_sha256")
        actual = hashlib.sha256(canonical_bytes(unsigned)).hexdigest()
        if payload.get("schema") != "MARKET_DATA_POLICY_V1" or claimed != actual:
            raise ValueError
        artifact = MarketPolicyArtifact.model_validate(payload)
        evidence = payload.get("evidence") or {}
        if evidence.get("collector_version") != MARKET_OBSERVATION_COLLECTOR_VERSION:
            raise ValueError("MARKET_POLICY_COLLECTOR_VERSION_STALE")
        return payload
    except (OSError, json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise ValueError("POLICY_INVALID") from exc


def _distribution(
    values: list[object], total: int, rejection_rate: float
) -> DistributionStatistics:
    finite = sorted(
        int(value)
        for value in values
        if value is not None and math.isfinite(float(value))
    )
    missing_rate = (total - len(finite)) / total if total else 1.0
    if not finite:
        return DistributionStatistics(
            count=0,
            minimum_ms=None,
            median_ms=None,
            p95_ms=None,
            p99_ms=None,
            maximum_ms=None,
            iqr_ms=None,
            missing_rate=missing_rate,
            rejection_rate=rejection_rate,
        )
    q25 = _nearest_rank(finite, 25)
    q75 = _nearest_rank(finite, 75)
    return DistributionStatistics(
        count=len(finite),
        minimum_ms=finite[0],
        median_ms=_nearest_rank(finite, 50),
        p95_ms=_nearest_rank(finite, 95),
        p99_ms=_nearest_rank(finite, 99),
        maximum_ms=finite[-1],
        iqr_ms=q75 - q25,
        missing_rate=missing_rate,
        rejection_rate=rejection_rate,
    )


def _nearest_rank(values: list[int], percentile: int) -> int:
    index = max(0, math.ceil(percentile * len(values) / 100) - 1)
    return values[index]


def _ceil_to(value: int, increment: int) -> int:
    return math.ceil(value / increment) * increment


def _parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _minutes(value: int):
    from datetime import timedelta

    return timedelta(minutes=value)
