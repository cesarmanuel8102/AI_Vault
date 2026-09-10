"""Pure simulated-paper soak and incident receipts for BRAIN-101 R15.3."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json


@dataclass(frozen=True)
class PaperSoakIncidentReceipt:
    accepted: bool
    reason: str
    incident_recovered: bool
    rollback_validated: bool
    receipt_id: str


def evaluate_paper_soak_incident(*, soak_window: str, incident_id: str, reconciliation_complete: bool, rollback_reference: str, paper_only: bool, broker_action: bool, provider_call: bool, network_call: bool, runtime_execution: bool, scheduler_activation: bool, live_trading: bool, real_money: bool) -> PaperSoakIncidentReceipt:
    """Evaluate simulated evidence only; no external action can occur here."""
    checks=((not paper_only,"paper_only_required"),(not soak_window.strip(),"soak_window_required"),(not incident_id.strip(),"incident_required"),(not reconciliation_complete,"reconciliation_required"),(not rollback_reference.strip(),"rollback_reference_required"),(broker_action,"broker_action_forbidden"),(provider_call,"provider_action_forbidden"),(network_call,"network_action_forbidden"),(runtime_execution,"runtime_execution_forbidden"),(scheduler_activation,"scheduler_activation_forbidden"),(live_trading,"live_trading_forbidden"),(real_money,"real_money_forbidden"))
    reason=next((reason for invalid,reason in checks if invalid),"")
    accepted=not reason
    identity={"soak_window":soak_window,"incident_id":incident_id,"reconciliation_complete":reconciliation_complete,"rollback_reference":rollback_reference,"accepted":accepted,"reason":reason}
    return PaperSoakIncidentReceipt(accepted,reason,accepted,accepted,sha256(json.dumps(identity,sort_keys=True,separators=(",",":")).encode()).hexdigest())
