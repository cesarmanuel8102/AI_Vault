"""Test B3: _dashboard_status_fastpath no debe inventar estado runtime sin verificación real.
- No debe afirmar runtime=activo sin prueba.
- Si HTTP health responde OK → runtime_status=verified.
- Si HTTP health falla → runtime_status=unknown.
- Schema backward compat preserved (ui_url, dashboard_url, host, puerto).
"""
import json, os, sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "tmp_agent"))
from brain_v9.core.session import BrainSession


def _get_text(result):
    return result.get("content") or result.get("text") or result.get("response", "")


def test_dashboard_fastpath_no_fake_active_without_verification():
    result = BrainSession("b3")._dashboard_status_fastpath()
    txt = _get_text(result)
    assert "runtime: activo" not in txt.lower(), "B3: no puede afirmar runtime activo sin verificación"


def test_dashboard_fastpath_runtime_status_field_present():
    result = BrainSession("b3")._dashboard_status_fastpath()
    txt = _get_text(result)
    assert "runtime_status:" in txt, "B3: debe incluir runtime_status"


def test_dashboard_fastpath_verified_by_field_present():
    result = BrainSession("b3")._dashboard_status_fastpath()
    txt = _get_text(result)
    assert "verified_by:" in txt, "B3: debe incluir verified_by"


def test_dashboard_fastpath_schema_backward_compat():
    result = BrainSession("b3")._dashboard_status_fastpath()
    txt = _get_text(result)
    assert "ui_url" in txt, "B3: ui_url missing"
    assert "dashboard_url" in txt, "B3: dashboard_url missing"
    assert "host" in txt, "B3: host missing"
    assert "puerto" in txt, "B3: puerto missing"


if __name__ == "__main__":
    test_dashboard_fastpath_no_fake_active_without_verification()
    test_dashboard_fastpath_runtime_status_field_present()
    test_dashboard_fastpath_verified_by_field_present()
    test_dashboard_fastpath_schema_backward_compat()
    print("All B3 tests passed.")
