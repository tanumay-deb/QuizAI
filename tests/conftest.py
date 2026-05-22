"""Shared pytest fixtures.

Sets QT_QPA_PLATFORM=offscreen so Qt tests run without a display, and points
HOME at a per-test temp dir so config/db/log files don't pollute the user's
real home directory.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Configure Qt before any Qt module is imported.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest


@pytest.fixture(autouse=True)
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect HOME and clear API-key env vars so each test starts clean."""
    monkeypatch.setenv("HOME", str(tmp_path))
    # On Windows, Path.home() consults USERPROFILE first; set both.
    monkeypatch.setenv("USERPROFILE", str(tmp_path))

    for key in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        monkeypatch.delenv(key, raising=False)

    # Several modules cache Path.home() at import time via module-level
    # constants. Reload them so they pick up the new HOME.
    for mod_name in (
        "quizai.config",
        "quizai.history",
        "quizai.logger",
        "quizai.notifier",
    ):
        if mod_name in sys.modules:
            import importlib

            importlib.reload(sys.modules[mod_name])
    return tmp_path


@pytest.fixture(scope="session")
def qapp():
    """A single QApplication for all Qt tests in the session."""
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app
