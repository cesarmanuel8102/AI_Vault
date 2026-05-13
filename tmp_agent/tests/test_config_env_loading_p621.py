import importlib
from pathlib import Path


def _reload_config():
    import brain_v9.config as cfg
    return importlib.reload(cfg)


def test_config_loads_dotenv_when_runtime_env_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("BRAIN_BASE_PATH", str(tmp_path))
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "OPENAI_API_KEY=env_file_openai",
                "ANTHROPIC_API_KEY=env_file_anthropic",
                "GEMINI_API_KEY=env_file_gemini",
            ]
        ),
        encoding="utf-8",
    )

    cfg = _reload_config()

    assert cfg.API_KEYS["openai"] == "env_file_openai"
    assert cfg.API_KEYS["anthropic"] == "env_file_anthropic"
    assert cfg.API_KEYS["gemini"] == "env_file_gemini"


def test_real_environment_overrides_dotenv(tmp_path, monkeypatch):
    monkeypatch.setenv("BRAIN_BASE_PATH", str(tmp_path))
    monkeypatch.setenv("OPENAI_API_KEY", "live_env_openai")
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)

    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "OPENAI_API_KEY=env_file_openai",
                "ANTHROPIC_API_KEY=env_file_anthropic",
            ]
        ),
        encoding="utf-8",
    )

    cfg = _reload_config()

    assert cfg.API_KEYS["openai"] == "live_env_openai"
    assert cfg.API_KEYS["anthropic"] == "env_file_anthropic"


def test_env_example_exists_with_placeholders():
    example = Path("C:/AI_VAULT/.env.example")
    content = example.read_text(encoding="utf-8")

    assert example.exists()
    assert "OPENAI_API_KEY=your_openai_api_key_here" in content
    assert "ANTHROPIC_API_KEY=your_anthropic_api_key_here" in content
    assert "GEMINI_API_KEY=your_gemini_api_key_here" in content
