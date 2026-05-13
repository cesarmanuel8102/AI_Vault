import json
from pathlib import Path
from unittest.mock import patch


def test_build_security_posture_summarizes_env_and_reports(isolated_base_path, monkeypatch):
    import brain_v9.brain.security_posture as sp

    base = isolated_base_path
    (base / ".env").write_text("OPENAI_API_KEY=test\n", encoding="utf-8")
    (base / ".env.example").write_text("OPENAI_API_KEY=your_openai_api_key_here\n", encoding="utf-8")
    (base / ".gitignore").write_text(".env\n.secrets/\n", encoding="utf-8")
    (base / "audit_reports").mkdir(parents=True, exist_ok=True)
    (base / "audit_reports" / "secrets_report.json").write_text(
        json.dumps(
            {
                "findings": [
                    {"classification": "real_secret"},
                    {"classification": "false_positive"},
                    {"classification": None},
                    {"file": "MIGRACION.md", "abs_path": str(base / "MIGRACION.md"), "line_text": "set OPENAI_API_KEY=sk-..."},
                    {"file": ".env", "abs_path": str(base / ".env"), "line_text": "OPENAI_API_KEY=sk-real-value"},
                    {"file": "config.py", "abs_path": str(base / "config.py"), "line_text": 'os.getenv("OPENAI_API_KEY")', "match": "OPENAI_API_KEY"},
                    {"file": "report.csv", "abs_path": str(base / "report.csv"), "line_text": "API_KEY"},
                ]
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(sp, "DOTENV_PATH", base / ".env")
    monkeypatch.setattr(sp, "DOTENV_EXAMPLE_PATH", base / ".env.example")
    monkeypatch.setattr(sp, "GITIGNORE_PATH", base / ".gitignore")
    monkeypatch.setattr(sp, "SECRETS_REPORT_PATH", base / "audit_reports" / "secrets_report.json")
    monkeypatch.setattr(sp, "SECURITY_POSTURE_ARTIFACT", base / "tmp_agent" / "state" / "security" / "security_posture_latest.json")
    monkeypatch.setattr(
        sp,
        "SECRET_SOURCE_MAP",
        {
            "openai": ("OPENAI_API_KEY", base / "tmp_agent" / "Secrets" / "openai_access.json"),
            "anthropic": ("ANTHROPIC_API_KEY", base / "tmp_agent" / "Secrets" / "anthropic_access.json"),
        },
    )
    monkeypatch.setattr(
        sp,
        "LEGACY_LOOSE_SECRET_FILES",
        [
            base / ".secrets" / "openai_api_key.txt",
            base / "tmp_agent" / "Secrets" / "OPENI_ACCESS.json",
        ],
    )
    legacy1 = base / "tmp_agent" / "brain_v9" / "agent" / "tools.py"
    legacy2 = base / "tmp_agent" / "brain_v9" / "brain" / "self_improvement.py"
    (base / "tmp_agent" / "Secrets").mkdir(parents=True, exist_ok=True)
    (base / ".secrets").mkdir(parents=True, exist_ok=True)
    legacy1.parent.mkdir(parents=True, exist_ok=True)
    legacy2.parent.mkdir(parents=True, exist_ok=True)
    legacy1.write_text("# clean\n", encoding="utf-8")
    legacy2.write_text("call brain_v9\\.env.bat\n", encoding="utf-8")
    (base / "tmp_agent" / "Secrets" / "openai_access.json").write_text(json.dumps({"token": "openai_dup"}), encoding="utf-8")
    (base / "tmp_agent" / "Secrets" / "anthropic_access.json").write_text(json.dumps({"token": "anthropic_json_only"}), encoding="utf-8")
    (base / "tmp_agent" / "Secrets" / "OPENI_ACCESS.json").write_text(json.dumps({"token": "legacy_dup"}), encoding="utf-8")
    (base / ".secrets" / "openai_api_key.txt").write_text("sk-legacy", encoding="utf-8")
    (base / ".env").write_text("OPENAI_API_KEY=openai_env\n", encoding="utf-8")
    monkeypatch.setattr(sp, "LEGACY_SECURITY_FILES", [legacy1, legacy2])
    monkeypatch.setattr(
        sp,
        "_refresh_dependency_audit",
        lambda: {
            "available": True,
            "vulnerability_count": 2,
            "affected_package_count": 1,
            "patchable_vulnerability_count": 1,
            "upstream_blocked_vulnerability_count": 1,
        },
    )

    payload = sp.build_security_posture(refresh_dependency_audit=True)

    assert payload["env_runtime"]["dotenv_exists"] is True
    assert payload["env_runtime"]["dotenv_example_exists"] is True
    assert payload["env_runtime"]["gitignore_protects_dotenv"] is True
    assert payload["secrets_audit"]["raw_finding_count"] == 7
    assert payload["secrets_audit"]["classified_real_secret"] == 1
    assert payload["legacy_runtime_refs"]["env_bat_reference_count"] == 1
    assert payload["secrets_triage"]["actionable_candidate_count"] >= 1
    assert payload["secrets_triage"]["likely_false_positive_count"] >= 1
    assert payload["secrets_triage"]["stale_actionable_candidate_count"] >= 0
    assert payload["secrets_triage"]["current_actionable_candidate_count"] >= 1
    assert payload["secret_source_audit"]["duplicate_source_count"] == 1
    assert payload["secret_source_audit"]["mismatch_count"] == 1
    assert payload["secret_source_audit"]["json_only_count"] == 1
    assert payload["legacy_secret_files"]["loose_secret_file_count"] == 2
    assert payload["legacy_secret_files"]["mapped_json_fallback_count"] == 2
    assert payload["legacy_secret_files"]["runtime_json_fallback_active"] is False
    assert payload["dependency_audit"]["vulnerability_count"] == 2
    assert payload["dependency_audit"]["patchable_vulnerability_count"] == 1
    assert payload["dependency_audit"]["upstream_blocked_vulnerability_count"] == 1


def test_build_security_posture_marks_missing_actionables_as_stale(isolated_base_path, monkeypatch):
    import brain_v9.brain.security_posture as sp

    base = isolated_base_path
    (base / ".env").write_text("OPENAI_API_KEY=test\n", encoding="utf-8")
    (base / ".env.example").write_text("OPENAI_API_KEY=your_openai_api_key_here\n", encoding="utf-8")
    (base / ".gitignore").write_text(".env\n.secrets/\n", encoding="utf-8")
    (base / "audit_reports").mkdir(parents=True, exist_ok=True)
    stale_file = base / ".secrets" / "openai_api_key.txt"
    (base / "audit_reports" / "secrets_report.json").write_text(
        json.dumps(
            {
                "findings": [
                    {
                        "file": ".secrets\\openai_api_key.txt",
                        "abs_path": str(stale_file),
                        "line": 1,
                        "line_text": "OPENAI_API_KEY=sk-real-value",
                        "match": "sk-real-value",
                        "pattern": "openai_key",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(sp, "DOTENV_PATH", base / ".env")
    monkeypatch.setattr(sp, "DOTENV_EXAMPLE_PATH", base / ".env.example")
    monkeypatch.setattr(sp, "GITIGNORE_PATH", base / ".gitignore")
    monkeypatch.setattr(sp, "SECRETS_REPORT_PATH", base / "audit_reports" / "secrets_report.json")
    monkeypatch.setattr(sp, "SECURITY_POSTURE_ARTIFACT", base / "tmp_agent" / "state" / "security" / "security_posture_latest.json")
    monkeypatch.setattr(sp, "SECRET_SOURCE_MAP", {})
    monkeypatch.setattr(sp, "LEGACY_LOOSE_SECRET_FILES", [])
    monkeypatch.setattr(sp, "LEGACY_SECURITY_FILES", [])
    monkeypatch.setattr(
        sp,
        "_refresh_dependency_audit",
        lambda: {"available": True, "vulnerability_count": 0, "affected_package_count": 0},
    )

    payload = sp.build_security_posture(refresh_dependency_audit=True)

    assert payload["secrets_triage"]["actionable_candidate_count"] == 1
    assert payload["secrets_triage"]["stale_actionable_candidate_count"] == 1
    assert payload["secrets_triage"]["current_actionable_candidate_count"] == 0
    assert payload["secrets_triage"]["current_actionable_candidates"] == []


def test_triage_treats_env_var_references_in_python_as_config_references(isolated_base_path, monkeypatch):
    import brain_v9.brain.security_posture as sp

    base = isolated_base_path
    (base / ".env").write_text("OPENAI_API_KEY=test\n", encoding="utf-8")
    (base / ".env.example").write_text("OPENAI_API_KEY=your_openai_api_key_here\n", encoding="utf-8")
    (base / ".gitignore").write_text(".env\n.secrets/\n", encoding="utf-8")
    (base / "audit_reports").mkdir(parents=True, exist_ok=True)
    py_file = base / "brain_chat_ui_server.py"
    py_file.write_text("client = OpenAI(api_key=OPENAI_API_KEY)\n", encoding="utf-8")
    (base / "audit_reports" / "secrets_report.json").write_text(
        json.dumps(
            {
                "findings": [
                    {
                        "file": "brain_chat_ui_server.py",
                        "abs_path": str(py_file),
                        "line": 1,
                        "line_text": "client = OpenAI(api_key=OPENAI_API_KEY)",
                        "match": "OPENAI_API_KEY",
                        "pattern": "env_var_style",
                    },
                    {
                        "file": "brain_chat_ui_server.py",
                        "abs_path": str(py_file),
                        "line": 1,
                        "line_text": "client = OpenAI(api_key=OPENAI_API_KEY)",
                        "match": "api_key=OPENAI_API_KEY",
                        "pattern": "generic_token_field",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(sp, "DOTENV_PATH", base / ".env")
    monkeypatch.setattr(sp, "DOTENV_EXAMPLE_PATH", base / ".env.example")
    monkeypatch.setattr(sp, "GITIGNORE_PATH", base / ".gitignore")
    monkeypatch.setattr(sp, "SECRETS_REPORT_PATH", base / "audit_reports" / "secrets_report.json")
    monkeypatch.setattr(sp, "SECURITY_POSTURE_ARTIFACT", base / "tmp_agent" / "state" / "security" / "security_posture_latest.json")
    monkeypatch.setattr(sp, "SECRET_SOURCE_MAP", {})
    monkeypatch.setattr(sp, "LEGACY_LOOSE_SECRET_FILES", [])
    monkeypatch.setattr(sp, "LEGACY_SECURITY_FILES", [])
    monkeypatch.setattr(
        sp,
        "_refresh_dependency_audit",
        lambda: {"available": True, "vulnerability_count": 0, "affected_package_count": 0},
    )

    payload = sp.build_security_posture(refresh_dependency_audit=True)

    assert payload["secrets_triage"]["categories"]["config_reference"] == 2
    assert payload["secrets_triage"]["actionable_candidate_count"] == 0
    assert payload["secrets_triage"]["current_actionable_candidate_count"] == 0


def test_triage_treats_backup_code_refs_as_non_actionable(isolated_base_path, monkeypatch):
    import brain_v9.brain.security_posture as sp

    base = isolated_base_path
    (base / ".env").write_text("OPENAI_API_KEY=test\n", encoding="utf-8")
    (base / ".env.example").write_text("OPENAI_API_KEY=your_openai_api_key_here\n", encoding="utf-8")
    (base / ".gitignore").write_text(".env\n.secrets/\n", encoding="utf-8")
    (base / "audit_reports").mkdir(parents=True, exist_ok=True)
    backup_file = base / "brain_server.py.pre_restore_20260311_111517"
    backup_file.write_text("token = getattr(obj, 'token', None)\n", encoding="utf-8")
    (base / "audit_reports" / "secrets_report.json").write_text(
        json.dumps(
            {
                "findings": [
                    {
                        "file": "brain_server.py.pre_restore_20260311_111517",
                        "abs_path": str(backup_file),
                        "line": 1,
                        "line_text": "token = getattr(obj, 'token', None)",
                        "match": "token = getattr",
                        "pattern": "generic_token_field",
                    },
                    {
                        "file": "brain_server.py.pre_restore_20260311_111517",
                        "abs_path": str(backup_file),
                        "line": 2,
                        "line_text": "_INTERNAL_KEY = os.getenv('_INTERNAL_KEY')",
                        "match": "_INTERNAL_KEY",
                        "pattern": "env_var_style",
                    },
                ]
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(sp, "DOTENV_PATH", base / ".env")
    monkeypatch.setattr(sp, "DOTENV_EXAMPLE_PATH", base / ".env.example")
    monkeypatch.setattr(sp, "GITIGNORE_PATH", base / ".gitignore")
    monkeypatch.setattr(sp, "SECRETS_REPORT_PATH", base / "audit_reports" / "secrets_report.json")
    monkeypatch.setattr(sp, "SECURITY_POSTURE_ARTIFACT", base / "tmp_agent" / "state" / "security" / "security_posture_latest.json")
    monkeypatch.setattr(sp, "SECRET_SOURCE_MAP", {})
    monkeypatch.setattr(sp, "LEGACY_LOOSE_SECRET_FILES", [])
    monkeypatch.setattr(sp, "LEGACY_SECURITY_FILES", [])
    monkeypatch.setattr(
        sp,
        "_refresh_dependency_audit",
        lambda: {"available": True, "vulnerability_count": 0, "affected_package_count": 0},
    )

    payload = sp.build_security_posture(refresh_dependency_audit=True)

    assert payload["secrets_triage"]["categories"]["generated_or_cache"] == 2
    assert payload["secrets_triage"]["actionable_candidate_count"] == 0
    assert payload["secrets_triage"]["current_actionable_candidate_count"] == 0


def test_dependency_audit_timeout_is_safe():
    import brain_v9.brain.security_posture as sp

    with patch("brain_v9.brain.security_posture.subprocess.run", side_effect=sp.subprocess.TimeoutExpired(cmd="pip_audit", timeout=120)):
        payload = sp._refresh_dependency_audit()

    assert payload["available"] is False
    assert payload["error"] == "timeout"


def test_triage_filters_logs_audit_report_and_security_signatures(isolated_base_path, monkeypatch):
    import brain_v9.brain.security_posture as sp

    base = isolated_base_path
    (base / ".env").write_text("OPENAI_API_KEY=test\n", encoding="utf-8")
    (base / ".env.example").write_text("OPENAI_API_KEY=your_openai_api_key_here\n", encoding="utf-8")
    (base / ".gitignore").write_text(".env\n.secrets/\n", encoding="utf-8")
    (base / "audit_reports").mkdir(parents=True, exist_ok=True)
    (base / "00_identity" / "logs").mkdir(parents=True, exist_ok=True)
    (base / "20_INFRASTRUCTURE" / "security").mkdir(parents=True, exist_ok=True)

    report_path = base / "audit_reports" / "secrets_report.json"
    findings = {
        "findings": [
            {
                "file": "00_identity\\logs\\brain_audit_report.txt",
                "abs_path": str(base / "00_identity" / "logs" / "brain_audit_report.txt"),
                "line_text": "BRAIN_API_KEY",
                "match": "BRAIN_API_KEY",
                "pattern": "env_var_style",
            },
            {
                "file": "audit_reports\\secrets_report.json",
                "abs_path": str(report_path),
                "line_text": "OPENAI_API_KEY",
                "match": "OPENAI_API_KEY",
                "pattern": "env_var_style",
            },
            {
                "file": "20_INFRASTRUCTURE\\security\\validation.py",
                "abs_path": str(base / "20_INFRASTRUCTURE" / "security" / "validation.py"),
                "line_text": "password: str = Field(..., min_length=12, max_length=128)",
                "match": "password: str = Field(..., min_length=12, max_length=128)",
                "pattern": "password_assignment",
            },
        ]
    }
    report_path.write_text(json.dumps(findings), encoding="utf-8")

    monkeypatch.setattr(sp, "DOTENV_PATH", base / ".env")
    monkeypatch.setattr(sp, "DOTENV_EXAMPLE_PATH", base / ".env.example")
    monkeypatch.setattr(sp, "GITIGNORE_PATH", base / ".gitignore")
    monkeypatch.setattr(sp, "SECRETS_REPORT_PATH", report_path)
    monkeypatch.setattr(sp, "SECURITY_POSTURE_ARTIFACT", base / "tmp_agent" / "state" / "security" / "security_posture_latest.json")
    monkeypatch.setattr(sp, "SECRET_SOURCE_MAP", {})
    monkeypatch.setattr(sp, "LEGACY_LOOSE_SECRET_FILES", [])
    monkeypatch.setattr(sp, "LEGACY_SECURITY_FILES", [])
    monkeypatch.setattr(
        sp,
        "_refresh_dependency_audit",
        lambda: {"available": True, "vulnerability_count": 0, "affected_package_count": 0},
    )

    payload = sp.build_security_posture(refresh_dependency_audit=True)

    assert payload["secrets_triage"]["categories"]["generated_or_cache"] == 2
    assert payload["secrets_triage"]["categories"]["config_reference"] == 1
    assert payload["secrets_triage"]["actionable_candidate_count"] == 0
    assert payload["secrets_triage"]["current_actionable_candidate_count"] == 0


def test_triage_filters_autogen_and_runtime_report_noise(isolated_base_path, monkeypatch):
    import brain_v9.brain.security_posture as sp

    base = isolated_base_path
    (base / ".env").write_text("OPENAI_API_KEY=test\n", encoding="utf-8")
    (base / ".env.example").write_text("OPENAI_API_KEY=your_openai_api_key_here\n", encoding="utf-8")
    (base / ".gitignore").write_text(".env\n.secrets/\n", encoding="utf-8")
    (base / "audit_reports").mkdir(parents=True, exist_ok=True)
    (base / "autogen_test").mkdir(parents=True, exist_ok=True)
    (base / "tmp_agent" / "state" / "reports").mkdir(parents=True, exist_ok=True)
    (base / "tmp_agent" / "brain_v9" / "trading").mkdir(parents=True, exist_ok=True)

    report_path = base / "audit_reports" / "secrets_report.json"
    report_path.write_text(json.dumps({
        "findings": [
            {
                "file": "autogen_test\\test_autogen_ollama.py",
                "abs_path": str(base / "autogen_test" / "test_autogen_ollama.py"),
                "line_text": 'client = OpenAI(api_key="ollama")',
                "match": 'api_key="ollama"',
                "pattern": "generic_token_field",
            },
            {
                "file": "tmp_agent\\state\\reports\\extract_dashboard.txt",
                "abs_path": str(base / "tmp_agent" / "state" / "reports" / "extract_dashboard.txt"),
                "line_text": "token = None",
                "match": "token = None",
                "pattern": "generic_token_field",
            },
            {
                "file": "tmp_agent\\brain_v9\\trading\\connectors.py",
                "abs_path": str(base / "tmp_agent" / "brain_v9" / "trading" / "connectors.py"),
                "line_text": "token   = token",
                "match": "token = token",
                "pattern": "generic_token_field",
            },
        ]
    }), encoding="utf-8")

    monkeypatch.setattr(sp, "DOTENV_PATH", base / ".env")
    monkeypatch.setattr(sp, "DOTENV_EXAMPLE_PATH", base / ".env.example")
    monkeypatch.setattr(sp, "GITIGNORE_PATH", base / ".gitignore")
    monkeypatch.setattr(sp, "SECRETS_REPORT_PATH", report_path)
    monkeypatch.setattr(sp, "SECURITY_POSTURE_ARTIFACT", base / "tmp_agent" / "state" / "security" / "security_posture_latest.json")
    monkeypatch.setattr(sp, "SECRET_SOURCE_MAP", {})
    monkeypatch.setattr(sp, "LEGACY_LOOSE_SECRET_FILES", [])
    monkeypatch.setattr(sp, "LEGACY_SECURITY_FILES", [])
    monkeypatch.setattr(
        sp,
        "_refresh_dependency_audit",
        lambda: {"available": True, "vulnerability_count": 0, "affected_package_count": 0},
    )

    payload = sp.build_security_posture(refresh_dependency_audit=True)

    assert payload["secrets_triage"]["categories"]["documentation_example"] == 1
    assert payload["secrets_triage"]["categories"]["generated_or_cache"] == 1
    assert payload["secrets_triage"]["categories"]["config_reference"] == 1
    assert payload["secrets_triage"]["current_actionable_candidate_count"] == 0
