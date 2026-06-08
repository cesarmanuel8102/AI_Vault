"""Smoke test for FRONT-INFRA-03 startup runbook."""

import os

RUNBOOK_PATH = 'docs/FRONT_INFRA_03_STARTUP_RUNBOOK.md'
INVENTORY_PATH = 'tmp_agent/front_infra_03/startup_inventory.json'


def test_runbook_exists():
    assert os.path.isfile(RUNBOOK_PATH), f"Runbook not found: {RUNBOOK_PATH}"


def test_runbook_declares_no_runtime_start():
    with open(RUNBOOK_PATH, 'r', encoding='utf-8') as f:
        content = f.read()
    assert "not start or stop the runtime by itself" in content.lower() or \
           "no arrancar servidor automaticamente" in content.lower(), \
           "Runbook must declare it does not start runtime autonomously"


def test_runbook_declares_no_runtime_stop():
    with open(RUNBOOK_PATH, 'r', encoding='utf-8') as f:
        content = f.read()
    assert "no parar servidor automaticamente" in content.lower() or \
           "stop the runtime" in content.lower(), \
           "Runbook must declare it does not stop runtime autonomously"


def test_runbook_documents_port_8090():
    with open(RUNBOOK_PATH, 'r', encoding='utf-8') as f:
        content = f.read()
    assert "8090" in content, "Runbook must document port 8090"


def test_runbook_documents_health_endpoint():
    with open(RUNBOOK_PATH, 'r', encoding='utf-8') as f:
        content = f.read()
    assert "127.0.0.1:8090/health" in content, "Runbook must document health endpoint"


def test_runbook_documents_env_example():
    with open(RUNBOOK_PATH, 'r', encoding='utf-8') as f:
        content = f.read()
    assert "BRAIN_PORT" in content, "Runbook must document BRAIN_PORT env var"
    assert "BRAIN_HOST" in content, "Runbook must document BRAIN_HOST env var"
    assert "BRAIN_SAFE_MODE" in content, "Runbook must document BRAIN_SAFE_MODE env var"


def test_runbook_documents_startup_command():
    with open(RUNBOOK_PATH, 'r', encoding='utf-8') as f:
        content = f.read()
    assert "uvicorn" in content, "Runbook must document uvicorn startup command"


def test_runbook_documents_shutdown_command():
    with open(RUNBOOK_PATH, 'r', encoding='utf-8') as f:
        content = f.read()
    assert "Get-NetTCPConnection" in content or "taskkill" in content, \
           "Runbook must document shutdown command"


def test_runbook_documents_staged_empty_check():
    with open(RUNBOOK_PATH, 'r', encoding='utf-8') as f:
        content = f.read()
    assert "git diff --cached --name-status" in content, \
           "Runbook must document staged empty check"


def test_runbook_documents_runtime_stopped_before_write():
    with open(RUNBOOK_PATH, 'r', encoding='utf-8') as f:
        content = f.read()
    assert "runtime detenido" in content.lower() or "runtime stopped" in content.lower(), \
           "Runbook must document runtime stopped before write"


def test_runbook_documents_safe_mode_risk():
    with open(RUNBOOK_PATH, 'r', encoding='utf-8') as f:
        content = f.read()
    assert "safe_mode" in content.lower(), "Runbook must document safe_mode risk"


def test_runbook_has_stop_conditions():
    with open(RUNBOOK_PATH, 'r', encoding='utf-8') as f:
        content = f.read()
    assert "Stop Conditions" in content, "Runbook must have Stop Conditions section"


def test_startup_inventory_exists():
    assert os.path.isfile(INVENTORY_PATH), f"Inventory not found: {INVENTORY_PATH}"


def test_requirements_exists():
    assert os.path.isfile('requirements.txt'), "requirements.txt not found"


def test_env_example_exists():
    assert os.path.isfile('.env.example'), ".env.example not found"


def test_no_memory_write_evidence():
    # This front should not create memory write evidence
    assert not os.path.isfile('tmp_agent/front_infra_03/write_operation.json'), \
           "Unexpected write_operation.json found"
