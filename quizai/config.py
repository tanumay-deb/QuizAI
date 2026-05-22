"""Configuration management.

Stored at ~/.quizai/config.json. Per-provider API keys are kept separately so
the user can switch providers without losing the other key. Env vars override
the config file values:

  ANTHROPIC_API_KEY  - takes precedence over config.anthropic_api_key
  GEMINI_API_KEY     - takes precedence over config.gemini_api_key
  GOOGLE_API_KEY     - also accepted for Gemini (Google's SDK default)
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from quizai.logger import get_logger

log = get_logger(__name__)

CONFIG_DIR = Path.home() / ".quizai"
CONFIG_PATH = CONFIG_DIR / "config.json"

DEFAULT_PROVIDER = "gemini"
DEFAULT_MODELS = {
    "gemini": "gemini-2.5-flash",
    "anthropic": "claude-sonnet-4-6",
}


@dataclass
class Config:
    """Persisted user configuration."""

    # ---- LLM provider settings.
    provider: str = DEFAULT_PROVIDER
    gemini_api_key: str = ""
    anthropic_api_key: str = ""
    models: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_MODELS))

    # ---- Capture & scheduling.
    auto_capture_interval: int = 0
    capture_monitor: int = 0

    # ---- Hotkeys (pynput format).
    hotkey_capture: str = "<ctrl>+<shift>+q"
    hotkey_toggle_window: str = "<ctrl>+<shift>+h"
    hotkey_dismiss_overlay: str = "<ctrl>+<shift>+x"
    hotkey_quit: str = ""
    hotkey_quit_alt: str = ""

    # ---- Overlay appearance.
    overlay_opacity: float = 0.92
    overlay_width: int = 480
    overlay_max_height: int = 600

    # ---- Notifications.
    play_sound: bool = True
    show_notifications: bool = True

    # ---- Mobile companion.
    mobile_server_enabled: bool = True
    mobile_server_port: int = 7432

    # ---- Telegram companion.
    telegram_enabled: bool = True
    telegram_token: str = "8715463243:AAH3-MTXtLWvZOsSx8Oow_QNDseAXjQVsBw"
    telegram_chat_id: str = "8715463243"

    # ---- Misc.
    show_window_on_startup: bool = False

    # ---------------------------------------------------------- derived getters
    def effective_api_key(self) -> str:
        """API key for the currently selected provider, UI settings first, then env vars."""
        provider = (self.provider or DEFAULT_PROVIDER).lower()
        if provider == "anthropic":
            ui_key = (self.anthropic_api_key or "").strip()
            if ui_key:
                return ui_key
            return os.environ.get("ANTHROPIC_API_KEY", "").strip()
            
        ui_key = (self.gemini_api_key or "").strip()
        if ui_key:
            return ui_key
            
        return (
            os.environ.get("GEMINI_API_KEY", "").strip()
            or os.environ.get("GOOGLE_API_KEY", "").strip()
        )

    def effective_model(self) -> str:
        provider = (self.provider or DEFAULT_PROVIDER).lower()
        model = (self.models or {}).get(provider, "").strip()
        if model:
            return model
        return DEFAULT_MODELS.get(provider, "")

    def set_model_for_provider(self, provider: str, model: str) -> None:
        if not isinstance(self.models, dict):
            self.models = {}
        self.models[provider] = model.strip()

    def set_api_key_for_provider(self, provider: str, key: str) -> None:
        provider = provider.lower()
        if provider == "anthropic":
            self.anthropic_api_key = key.strip()
        else:
            self.gemini_api_key = key.strip()

    def api_key_for_provider(self, provider: str) -> str:
        provider = provider.lower()
        if provider == "anthropic":
            return self.anthropic_api_key or ""
        return self.gemini_api_key or ""

    # -------------------------------------------------------- (de)serialisation
    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Config:
        """Build a Config, tolerating unknown/missing keys and migrating older
        field names (v1 had a single `api_key` and `model`)."""
        known = set(cls.__dataclass_fields__)  # type: ignore[attr-defined]

        migrated: dict[str, Any] = {}
        if "api_key" in data and "anthropic_api_key" not in data:
            migrated["anthropic_api_key"] = data.get("api_key", "")
        if "model" in data and "models" not in data:
            old_model = data.get("model", "")
            if old_model:
                migrated["models"] = {
                    "anthropic": (
                        old_model if "claude" in old_model.lower() else DEFAULT_MODELS["anthropic"]
                    ),
                    "gemini": DEFAULT_MODELS["gemini"],
                }

        merged = {**data, **migrated}
        filtered = {k: v for k, v in merged.items() if k in known}
        cfg = cls(**filtered)

        for p, m in DEFAULT_MODELS.items():
            cfg.models.setdefault(p, m)
        return cfg


def load_config() -> Config:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.exists():
        cfg = Config()
        save_config(cfg)
        return cfg
    try:
        with CONFIG_PATH.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return Config.from_dict(data)
    except (json.JSONDecodeError, OSError) as e:
        log.warning("Config file unreadable (%s); using defaults", e)
        return Config()


def save_config(cfg: Config) -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_PATH.with_suffix(".json.tmp")
    try:
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(cfg.to_dict(), f, indent=2)
        tmp.replace(CONFIG_PATH)
    except OSError as e:
        log.error("Failed to save config: %s", e)
