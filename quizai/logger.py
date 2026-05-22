"""Centralized logging.

Logs go to both the console and a rotating file at ~/.quizai/quizai.log.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
from pathlib import Path

_LOG_DIR = Path.home() / ".quizai"
_LOG_FILE = _LOG_DIR / "quizai.log"

_configured = False


def setup_logging(level: int = logging.INFO) -> None:
    """Configure the root logger. Idempotent."""
    global _configured
    if _configured:
        return
    _configured = True

    _LOG_DIR.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(level)

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler.
    stream = logging.StreamHandler(sys.stderr)
    stream.setFormatter(fmt)
    root.addHandler(stream)

    # Rotating file handler — 1 MB x 3 backups.
    try:
        file_h = logging.handlers.RotatingFileHandler(
            _LOG_FILE, maxBytes=1_000_000, backupCount=3, encoding="utf-8"
        )
        file_h.setFormatter(fmt)
        root.addHandler(file_h)
    except OSError:
        # If we can't write the log file, keep going with console only.
        root.warning("Could not open log file at %s", _LOG_FILE)

    # Silence noisy third-party libs.
    logging.getLogger("PIL").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("anthropic").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Convenience wrapper around logging.getLogger."""
    return logging.getLogger(name)
