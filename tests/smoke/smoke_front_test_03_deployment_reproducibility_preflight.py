"""
FRONT-TEST-03: Deployment reproducibility preflight smoke test.

Este test verifica la reproducibilidad del deployment al medir los
gaps del sistema sin arrancar produccion. Es de caracterizacion:
acepta la realidad actual y documenta gaps.

No toca produccion, memoria, FAISS, trading, B8, main, session, red, Docker.
"""
from __future__ import annotations

import ast
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

MODULE_PATH = Path(__file__).resolve()
REPO_ROOT = MODULE_PATH.parents[2]

INVENTORY_PATH = REPO_ROOT / "tmp_agent" / "front_test_03" / "deployment_inventory.json"


@pytest.fixture(scope="module")
def inventory():
    assert INVENTORY_PATH.exists(), f"inventory no encontrado en {INVENTORY_PATH}"
    return json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def brain_config():
    return REPO_ROOT / "tmp_agent" / "brain_v9" / "config.py"


@pytest.fixture(scope="module")
def api_security():
    return REPO_ROOT / "tmp_agent" / "brain_v9" / "api_security.py"


# 1
class TestRepositoryHasPythonEntrypointsOrScripts:
    def test_startup_scripts_exist(self, inventory):
        assert inventory["startup_scripts_found"], "no startup scripts found"

    def test_main_py_exists(self):
        assert (REPO_ROOT / "tmp_agent" / "brain_v9" / "main.py").exists()

# 2
class TestDependencyManifestPresenceOrGapReported:
    def test_dependency_manifest_status_reported(self, inventory):
        assert "dependency_files_found" in inventory
        assert "dependency_files_missing" in inventory

    def test_dependency_gap_documented(self, inventory):
        missing = inventory.get("dependency_files_missing", [])
        assert missing, "dependency gap not documented"

    def test_gap_not_hidden(self, inventory):
        assert isinstance(inventory["dependency_files_found"], list)
        assert isinstance(inventory["dependency_files_missing"], list)

# 3
class TestSmokeTestsDiscoverable:
    def test_smoke_dir_exists(self):
        smoke_dir = REPO_ROOT / "tests" / "smoke"
        assert smoke_dir.exists() and smoke_dir.is_dir()

    def test_some_smoke_tests_present(self):
        smoke_files = list((REPO_ROOT / "tests" / "smoke").glob("smoke_*.py"))
        assert len(smoke_files) >= 10, f"expected >=10 smoke tests, found {len(smoke_files)}"

    def test_custom_smoke_tests_present(self):
        f2 = REPO_ROOT / "tests" / "smoke" / "smoke_front_test_02_self_improvement_minimum_coverage.py"
        assert f2.exists()

# 4
class TestNoRequiredSecretForImportLevelChecks:
    def test_no_secret_required_to_parse_ast(self, api_security):
        tree = ast.parse(api_security.read_text(encoding="utf-8"))
        assert isinstance(tree, ast.Module)

    def test_no_secret_required_to_parse_config(self, brain_config):
        tree = ast.parse(brain_config.read_text(encoding="utf-8"))
        assert isinstance(tree, ast.Module)

# 5
class TestNoDefaultDevModeTrueRegression:
    def test_config_default_dev_mode_false(self, brain_config):
        src = brain_config.read_text(encoding="utf-8")
        for line in src.splitlines():
            if "BRAIN_CHAT_DEV_MODE" in line and "os.getenv" in line:
                # Extract the default argument of os.getenv using a safe check
                # The line BRAIN_CHAT_DEV_MODE = os.getenv("...", "false")
                import re
                match = re.search(r'os\.getenv\("BRAIN_CHAT_DEV_MODE"\s*,\s*"([^"]*)"\s*\)', line)
                if match:
                    assert match.group(1) == "false", f"default is not false: {match.group(1)}"
                else:
                    # Fallback: if regex fails, ensure line doesn't have default true literal
                    assert '"true"' not in line or '"false"' in line, f"possible default true: {line}"

# 6
class TestNoRealWriteFlagsEnabledByDefault:
    def test_no_literal_true_for_real_write_in_api_security(self, api_security):
        src = api_security.read_text(encoding="utf-8")
        for line in src.splitlines():
            if "real_write" in line.lower() and "= True" in line:
                pytest.fail(f"real_write=True found: {line}")

# 7
class TestNoMemorySemanticWriteDuringPreflight:
    def test_no_add_memory_call(self, api_security):
        tree = ast.parse(api_security.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    assert node.func.attr != "add_memory"

    def test_no_semantic_memory_import(self, api_security):
        src = api_security.read_text(encoding="utf-8")
        assert "semantic_memory" not in src

# 8
class TestNoFaissWriteDuringPreflight:
    def test_no_faiss_import(self, api_security):
        tree = ast.parse(api_security.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                assert "faiss" not in (node.module or "").lower()

# 9
class TestNoTradingOrB8Touch:
    def test_no_trading_keywords(self, api_security):
        src = api_security.read_text(encoding="utf-8")
        for kw in ["execute_trade", "place_order", "run_strategy", "backtest"]:
            assert kw not in src

    def test_no_b8_reference(self, api_security):
        src = api_security.read_text(encoding="utf-8")
        assert "B8" not in src

# 10
class TestStartupPreflightReportSchema:
    def test_inventory_has_all_required_fields(self, inventory):
        required = [
            "dependency_files_found",
            "dependency_files_missing",
            "startup_scripts_found",
            "smoke_tests_found",
            "docker_files_found",
            "env_files_required",
            "ports_required",
            "runtime_services_required",
            "python_version_detected",
            "reproducibility_risks",
            "recommended_minimal_fix",
        ]
        for field in required:
            assert field in inventory, f"missing field: {field}"

# 11
class TestRuntimePortsDocumentedOrReported:
    def test_ports_detected(self, inventory):
        ports = inventory.get("ports_required", [])
        assert ports, "no ports detected in inventory"

    def test_port_8090_or_8080_detected(self, inventory):
        ports = [str(p) for p in inventory.get("ports_required", [])]
        assert any("8090" in p or "8080" in p for p in ports), "no port 8090/8080 detected"

# 12
class TestDeploymentGapReportContainsRequiredFields:
    def test_reproducibility_risks_not_empty(self, inventory):
        risks = inventory.get("reproducibility_risks", [])
        assert risks, "reproducibility risks empty"
        assert "No dependency manifest" in str(risks), "no dependency manifest risk reported"

    def test_recommended_minimal_fix_not_empty(self, inventory):
        fixes = inventory.get("recommended_minimal_fix", [])
        assert fixes, "recommended fixes empty"
        assert any("requirements" in f.lower() or "pyproject" in f.lower() for f in fixes), "no dep fix recommendation"
