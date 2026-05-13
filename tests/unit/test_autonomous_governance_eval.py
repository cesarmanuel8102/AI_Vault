from brain_v9.brain.autonomous_governance_eval import (
    build_autonomous_governance_eval,
    ensure_autonomous_governance_artifacts,
    run_chat_net_truth_probe,
    run_chat_review_truth_probe,
)


def test_autonomous_governance_artifacts_exist():
    registry = ensure_autonomous_governance_artifacts()
    assert registry["rooms"]
    assert "brain_eval_ages01_contract" in registry["rooms"]
    assert "autonomous_governance_eval_contract.json" in registry["rooms"]["brain_eval_ages01_contract"]


def test_autonomous_governance_eval_builds_status():
    status = build_autonomous_governance_eval(refresh=False, run_self_test=False)
    assert status["schema_version"] == "autonomous_governance_eval_status_v1"
    assert "scores" in status
    assert "promotion_gate" in status
    assert "global_score" in status["scores"]
    assert "allow_promote" in status["promotion_gate"]


def test_chat_corpus_includes_network_truth_case():
    registry = ensure_autonomous_governance_artifacts()
    assert "network_scan_truth_cases.json" in registry["rooms"]["brain_eval_ages02_chat_corpus"]

    status = build_autonomous_governance_eval(refresh=False, run_self_test=False)
    tool_exec = status["scores"]["components"]["tool_execution"]
    assert "chat_truth_regression_score" in tool_exec
    assert "chat_truth_regression_checks" in tool_exec


def test_chat_net_probe_scores_pass_when_response_closes_subgoals(monkeypatch):
    class _Resp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return (
                b'{"response":"Hosts observables: 192.168.1.10, 192.168.1.20. '
                b'No puedo afirmar que haya dispositivos bloqueados sin evidencia del router/AP/DHCP/ACL/logs."}'
            )

    monkeypatch.setattr(
        "brain_v9.brain.autonomous_governance_eval.urlrequest.urlopen",
        lambda req, timeout=90: _Resp(),
    )

    result = run_chat_net_truth_probe("http://127.0.0.1:8090")
    assert result["verdict"] == "pass"
    assert result["score"] == 1.0


def test_chat_review_probe_scores_pass_when_response_names_root_cause(monkeypatch):
    class _Resp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return (
                b'{"response":"Revision de interacciones chat-brain recientes. '
                b'Hubo ghost_completion y respuestas extractivas por fallos de sintesis. '
                b'Siguiente accion correcta: endurecer la ruta de cierre."}'
            )

    monkeypatch.setattr(
        "brain_v9.brain.autonomous_governance_eval.urlrequest.urlopen",
        lambda req, timeout=90: _Resp(),
    )

    result = run_chat_review_truth_probe("http://127.0.0.1:8090")
    assert result["verdict"] == "pass"
    assert result["score"] == 1.0
