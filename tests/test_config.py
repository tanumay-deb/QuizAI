"""Tests for quizai.config."""

from __future__ import annotations


def test_defaults():
    from quizai.config import load_config

    c = load_config()
    assert c.provider == "gemini"
    assert c.effective_model() == "gemini-2.5-flash"
    assert c.models["anthropic"] == "claude-sonnet-4-6"
    assert c.play_sound is True
    assert c.show_notifications is True
    assert c.auto_capture_interval == 0


def test_round_trip():
    from quizai.config import load_config, save_config

    c = load_config()
    c.gemini_api_key = "AIza-test"
    c.anthropic_api_key = "sk-ant-test"
    c.auto_capture_interval = 60
    c.play_sound = False
    save_config(c)

    c2 = load_config()
    assert c2.gemini_api_key == "AIza-test"
    assert c2.anthropic_api_key == "sk-ant-test"
    assert c2.auto_capture_interval == 60
    assert c2.play_sound is False


def test_env_var_fallback(monkeypatch):
    from quizai.config import Config

    # A key set in config/UI takes precedence over the environment.
    c = Config(gemini_api_key="from-config", provider="gemini")
    monkeypatch.setenv("GEMINI_API_KEY", "from-env")
    assert c.effective_api_key() == "from-config"

    # Env var is used as a fallback when no config/UI key is set.
    c2 = Config(gemini_api_key="", provider="gemini")
    assert c2.effective_api_key() == "from-env"

    # GOOGLE_API_KEY is accepted as a Gemini fallback too.
    monkeypatch.delenv("GEMINI_API_KEY")
    monkeypatch.setenv("GOOGLE_API_KEY", "google-fallback")
    assert c2.effective_api_key() == "google-fallback"


def test_per_provider_key_storage():
    from quizai.config import Config

    c = Config()
    c.set_api_key_for_provider("gemini", "AIza-g")
    c.set_api_key_for_provider("anthropic", "sk-ant-a")
    assert c.api_key_for_provider("gemini") == "AIza-g"
    assert c.api_key_for_provider("anthropic") == "sk-ant-a"

    c.provider = "gemini"
    assert c.effective_api_key() == "AIza-g"
    c.provider = "anthropic"
    assert c.effective_api_key() == "sk-ant-a"


def test_v1_migration_anthropic_only():
    from quizai.config import Config

    v1 = {
        "api_key": "sk-ant-old",
        "model": "claude-3-haiku",
        "auto_capture_interval": 30,
    }
    mig = Config.from_dict(v1)
    assert mig.anthropic_api_key == "sk-ant-old"
    assert mig.models["anthropic"] == "claude-3-haiku"
    # Gemini default still populated
    assert mig.models["gemini"] == "gemini-2.5-flash"
    assert mig.auto_capture_interval == 30


def test_v1_migration_non_claude_model_falls_back():
    """v1 configs with a non-Claude model string should not pollute the
    anthropic slot with garbage."""
    from quizai.config import Config

    v1 = {"api_key": "key", "model": "gpt-4-vision"}
    mig = Config.from_dict(v1)
    assert mig.models["anthropic"] == "claude-sonnet-4-6"


def test_from_dict_tolerates_empty():
    from quizai.config import Config

    c = Config.from_dict({})
    assert c.provider == "gemini"
    assert c.models["gemini"]
    assert c.models["anthropic"]


def test_from_dict_drops_unknown_keys():
    from quizai.config import Config

    c = Config.from_dict({"provider": "gemini", "bogus_field": "ignored"})
    assert c.provider == "gemini"


def test_corrupted_config_file_falls_back(tmp_path, monkeypatch):
    """A junk JSON file shouldn't crash the app."""
    monkeypatch.setenv("HOME", str(tmp_path))
    cfg_dir = tmp_path / ".quizai"
    cfg_dir.mkdir()
    (cfg_dir / "config.json").write_text("{not valid json")

    import importlib

    import quizai.config as config_mod

    importlib.reload(config_mod)

    c = config_mod.load_config()
    assert c.provider == "gemini"  # fell back to defaults
