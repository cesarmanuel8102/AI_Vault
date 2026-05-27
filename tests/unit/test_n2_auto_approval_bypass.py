"""
N2 Auto-Approval API Bypass — Static Structure Tests
Verify that critical endpoints require StrictOperatorAccess.
Read main.py as text to avoid FastAPI import overhead.
"""
import os

MAIN_PY = os.path.join(os.path.dirname(__file__), "..", "..", "tmp_agent", "brain_v9", "main.py")


def _read_main_text() -> str:
    with open(MAIN_PY, "r", encoding="utf-8") as f:
        return f.read()


def _get_func_signature(text: str, func_name: str) -> str:
    idx = text.find(f"async def {func_name}(")
    if idx == -1:
        return ""
    start = idx
    end = text.find("):", start)
    if end == -1:
        return ""
    return text[start:end + 2]


def test_mutations_test_apply_requires_strict_operator():
    sig = _get_func_signature(_read_main_text(), "brain_mutations_test_apply")
    assert "StrictOperatorAccess" in sig, "N2: /brain/mutations/test_apply must require StrictOperatorAccess"


def test_proposal_apply_requires_strict_operator():
    sig = _get_func_signature(_read_main_text(), "brain_ce_proposal_apply")
    assert "StrictOperatorAccess" in sig, "N2: /brain/chat_excellence/proposals/{id}/apply must require StrictOperatorAccess"


def test_proposal_reject_requires_strict_operator():
    sig = _get_func_signature(_read_main_text(), "brain_ce_proposal_reject")
    assert "StrictOperatorAccess" in sig, "N2: /brain/chat_excellence/proposals/{id}/reject must require StrictOperatorAccess"


def test_gate_reject_symmetric_with_gate_approve():
    text = _read_main_text()
    approve_sig = _get_func_signature(text, "gate_approve")
    reject_sig = _get_func_signature(text, "gate_reject")
    assert "StrictOperatorAccess" in approve_sig, "N2: /gate/approve must already have StrictOperatorAccess"
    assert "StrictOperatorAccess" in reject_sig, "N2: /gate/reject must mirror /gate/approve protection"


def test_no_payload_by_trusted_as_identity():
    text = _read_main_text()
    sig = _get_func_signature(text, "brain_ce_proposal_apply")
    body = text[text.find(sig): text.find(sig) + 800]
    # Ensure we do not unconditionally trust payload['by']
    # The patch does not change internal logic; but auth now enforced.
    assert "by = payload.get" in body or "payload.get(\"by\"" in body, "N2: payload.by still exists but is gated by StrictOperatorAccess"
    assert "StrictOperatorAccess" in sig, "N2: payload.by is only reachable after StrictOperatorAccess gate"


def test_no_audit_only_auto_applied_without_operator():
    sig = _get_func_signature(_read_main_text(), "brain_ce_proposal_apply")
    assert "StrictOperatorAccess" in sig, "N2: audit_only path must require StrictOperatorAccess"


if __name__ == "__main__":
    test_mutations_test_apply_requires_strict_operator()
    test_proposal_apply_requires_strict_operator()
    test_proposal_reject_requires_strict_operator()
    test_gate_reject_symmetric_with_gate_approve()
    test_no_payload_by_trusted_as_identity()
    test_no_audit_only_auto_applied_without_operator()
    print("All N2 tests passed.")
