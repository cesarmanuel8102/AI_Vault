from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .auditor_gate_v2 import (
    PaperIdentityBinding,
    load_and_evaluate_auditor_gate_v2,
)
from .market_data import (
    DecisionClass,
    MarketDataGate,
    MarketDataSnapshot,
    QuoteSnapshot,
)
from .market_observation_collector import (
    IBKRMarketDataSource,
    MarketDataSource,
    MarketObservationCollector,
    ObservationConfig,
    ObservationPrerequisites,
)
from .market_policy import MarketPolicyFreezer, load_verified_policy


DEFAULT_REPORT_ROOT = Path("state/ibkr_paper_30d/reports")
DEFAULT_MARKET_POLICY = DEFAULT_REPORT_ROOT / "market_data_policy_v1.json"
DEFAULT_READONLY_RECEIPT = DEFAULT_REPORT_ROOT / "read_only_real_paper_reconciliation.json"
DEFAULT_AUDITOR_RECEIPT = DEFAULT_REPORT_ROOT / "auditor_gate_v2_receipt.json"
DEFAULT_AUDITOR_RUNTIME = Path(r"C:\ProgramData\CodexAuditorV1\runtime")
DEFAULT_AUDITOR_PROVISIONING = Path(r"C:\ProgramData\CodexAuditorV1\provisioning")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class RuntimeMarketDataGate:
    def __init__(
        self,
        *,
        policy_path: Path = DEFAULT_MARKET_POLICY,
        expected_account_hash: str,
        source_factory: Callable[[], MarketDataSource] | None = None,
        now_utc: Callable[[], datetime] | None = None,
    ) -> None:
        self.policy_path = Path(policy_path)
        self.expected_account_hash = expected_account_hash
        self.source_factory = source_factory or (lambda: IBKRMarketDataSource())
        self.now_utc = now_utc or (lambda: datetime.now(timezone.utc))

    def evaluate(
        self,
        decision_class: DecisionClass = DecisionClass.NEW_TRADE,
    ) -> dict[str, Any]:
        try:
            policy = load_verified_policy(self.policy_path)
        except (OSError, ValueError) as exc:
            return {
                "gate_status": "BLOCK",
                "reason_codes": ["MARKET_POLICY_INVALID_OR_MISSING"],
                "error": f"{type(exc).__name__}:{exc}",
            }

        source = self.source_factory()
        now = self.now_utc()
        try:
            window = MarketObservationCollector(
                source, now_utc=self.now_utc
            ).collect_window(
                ObservationConfig(
                    symbols=tuple(sorted(MarketPolicyFreezer.REQUIRED_SYMBOLS)),
                    cadence_seconds=5,
                    window_seconds=0,
                ),
                ObservationPrerequisites(
                    identity_receipt_sha256=self.expected_account_hash,
                    reconciliation_receipt_sha256=hashlib.sha256(
                        b"runtime-market-gate"
                    ).hexdigest(),
                    paper_identity_proven=True,
                    broker_reconciliation_gate="PASS",
                ),
            )
            rejected = [
                reason
                for observation in window.observations
                if not observation.accepted
                for reason in observation.reason_codes
            ]
            quotes = [
                QuoteSnapshot(
                    symbol=item.symbol,
                    contract_id=item.contract_id,
                    source=item.source,
                    bid=item.bid,
                    ask=item.ask,
                    last=item.last,
                    bid_size=item.bid_size,
                    ask_size=item.ask_size,
                    last_size=item.last_size,
                    quote_timestamp=item.broker_quote_timestamp,
                    local_receipt_timestamp=item.local_receipt_timestamp,
                    market_session=item.market_session.value,
                    realtime_or_delayed=item.realtime_or_delayed,
                    data_entitlement_status=item.entitlement_state,
                    declared_quote_age_ms=item.corrected_quote_age_ms,
                    source_health=item.source_health,
                )
                for item in window.observations
            ]
            snapshot = MarketDataSnapshot.freeze(quotes, created_at_utc=now)
            result = MarketDataGate(policy).evaluate(
                snapshot, decision_class, now=now
            )
            reasons = list(result.reason_codes)
            reasons.extend(rejected)
            if rejected:
                status = "BLOCK"
            else:
                status = result.status
            return {
                "gate_status": status,
                "reason_codes": list(dict.fromkeys(reasons)),
                "policy_version": result.market_data_policy_version,
                "snapshot_id": result.market_data_snapshot_id,
                "snapshot_sha256": result.market_data_snapshot_sha256,
                "quote_timestamp": (
                    result.quote_timestamp.isoformat()
                    if result.quote_timestamp is not None
                    else None
                ),
                "oldest_quote_timestamp": (
                    result.oldest_quote_timestamp.isoformat()
                    if result.oldest_quote_timestamp is not None
                    else None
                ),
                "latest_quote_timestamp": (
                    result.latest_quote_timestamp.isoformat()
                    if result.latest_quote_timestamp is not None
                    else None
                ),
                "quote_age_at_decision_ms": result.quote_age_at_decision_ms,
                "decision_class": decision_class.value,
            }
        except Exception as exc:
            return {
                "gate_status": "BLOCK",
                "reason_codes": ["RUNTIME_MARKET_DATA_EVALUATION_FAILED"],
                "error": f"{type(exc).__name__}:{exc}",
            }


class RuntimeAuditorGate:
    def __init__(
        self,
        *,
        readonly_receipt_path: Path = DEFAULT_READONLY_RECEIPT,
        auditor_receipt_path: Path = DEFAULT_AUDITOR_RECEIPT,
        runtime_root: Path = DEFAULT_AUDITOR_RUNTIME,
        provisioning_root: Path = DEFAULT_AUDITOR_PROVISIONING,
        now_utc: Callable[[], datetime] | None = None,
    ) -> None:
        self.readonly_receipt_path = Path(readonly_receipt_path)
        self.auditor_receipt_path = Path(auditor_receipt_path)
        self.runtime_root = Path(runtime_root)
        self.provisioning_root = Path(provisioning_root)
        self.now_utc = now_utc or (lambda: datetime.now(timezone.utc))

    def evaluate(self) -> dict[str, Any]:
        runtime_manifest = self.runtime_root / "AUDITOR_RUNTIME_MANIFEST_V2.json"
        deployment_manifest = (
            self.provisioning_root / "AUDITOR_RUNTIME_V2_DEPLOYMENT_MANIFEST.json"
        )
        probe = self.runtime_root / "AUDITOR_GATE_V2_PROBE.ps1"
        target_manifest = (
            self.provisioning_root / "AUDITOR_PROBE_TARGET_MANIFEST_V1.json"
        )
        required = (
            self.readonly_receipt_path,
            self.auditor_receipt_path,
            runtime_manifest,
            deployment_manifest,
            probe,
            target_manifest,
        )
        if any(not path.is_file() for path in required):
            return {
                "gate_status": "BLOCK",
                "reason_codes": ["AUDITOR_RUNTIME_EVIDENCE_MISSING"],
            }
        try:
            readonly_bytes = self.readonly_receipt_path.read_bytes()
            readonly_payload = json.loads(readonly_bytes)
            binding = PaperIdentityBinding.from_readonly_receipt(
                readonly_payload, readonly_bytes
            )
            binding = replace(
                binding,
                runtime_manifest_sha256=_sha256(runtime_manifest),
                deployment_manifest_sha256=_sha256(deployment_manifest),
                probe_sha256=_sha256(probe),
                probe_manifest_sha256=_sha256(target_manifest),
            )
            evaluation = load_and_evaluate_auditor_gate_v2(
                self.auditor_receipt_path,
                binding,
                self.now_utc(),
            )
            return {
                "gate_status": evaluation.canonical_gate,
                "compatibility_gate": evaluation.compatibility_gate,
                "reason_codes": list(evaluation.reason_codes),
                "gate_version": evaluation.gate_version,
                "receipt_sha256": _sha256(self.auditor_receipt_path),
            }
        except Exception as exc:
            return {
                "gate_status": "BLOCK",
                "reason_codes": ["RUNTIME_AUDITOR_EVALUATION_FAILED"],
                "error": f"{type(exc).__name__}:{exc}",
            }
