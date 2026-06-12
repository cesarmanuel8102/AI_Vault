import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _git(args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def test_01_import_main_testclient_does_not_dirty_github_knowledge():
    before = _git(["diff", "--name-only", "--", "tmp_agent/knowledge/external/github"])
    assert before == ""
    from fastapi.testclient import TestClient
    from tmp_agent.brain_v9.main import app
    client = TestClient(app)
    client.get("/health")
    after = _git(["diff", "--name-only", "--", "tmp_agent/knowledge/external/github"])
    assert after == ""


def test_02_no_protected_paths_staged():
    staged = _git(["diff", "--cached", "--name-only"]).replace("\\", "/")
    assert "memory/semantic" not in staged
    assert "trading/" not in staged
    assert "B8/" not in staged
    assert "tmp_agent/strategies" not in staged
