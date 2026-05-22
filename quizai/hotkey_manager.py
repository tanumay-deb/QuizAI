"""Cross-platform global hotkey support via pynput.

pynput's GlobalHotKeys runs its own listener thread. We wrap it so the rest
of the app can swap hotkey bindings at runtime when the user edits settings.

Callbacks are invoked on pynput's listener thread; consumers must marshal back
to the GUI thread themselves (we use Qt signals for that).
"""

from __future__ import annotations

import threading
from collections.abc import Callable

try:
    from pynput import keyboard  # type: ignore
except Exception as e:  # pragma: no cover
    keyboard = None  # type: ignore
    _import_err: Exception | None = e
else:
    _import_err = None

from quizai.logger import get_logger

log = get_logger(__name__)


class HotkeyManager:
    """Manage a small set of named global hotkeys."""

    def __init__(self) -> None:
        self._listener: keyboard.GlobalHotKeys | None = None  # type: ignore[name-defined]
        self._lock = threading.Lock()
        self._bindings: dict[str, Callable[[], None]] = {}

    def is_available(self) -> bool:
        return keyboard is not None

    def set_bindings(self, bindings: dict[str, Callable[[], None]]) -> None:
        """Replace all bindings atomically.

        `bindings` maps hotkey strings (pynput format like "<ctrl>+<shift>+q")
        to zero-arg callables.
        """
        if keyboard is None:
            log.warning(
                "Global hotkeys unavailable: pynput failed to load (%s)",
                _import_err,
            )
            return

        with self._lock:
            self._stop_locked()
            self._bindings = dict(bindings)
            cleaned: dict[str, Callable[[], None]] = {}
            for combo, cb in self._bindings.items():
                combo = (combo or "").strip()
                if not combo:
                    continue
                cleaned[combo] = _wrap_callback(combo, cb)

            if not cleaned:
                return

            try:
                self._listener = keyboard.GlobalHotKeys(cleaned)
                self._listener.daemon = True
                self._listener.start()
                log.info("Hotkeys active: %s", ", ".join(cleaned))
            except Exception as e:
                log.error("Failed to start hotkey listener: %s", e)
                self._listener = None

    def stop(self) -> None:
        with self._lock:
            self._stop_locked()

    def _stop_locked(self) -> None:
        if self._listener is not None:
            try:
                self._listener.stop()
            except Exception as e:
                log.debug("Hotkey listener stop raised: %s", e)
            self._listener = None


def _wrap_callback(combo: str, cb: Callable[[], None]) -> Callable[[], None]:
    """Wrap a user callback to log and swallow exceptions — pynput will
    silently kill the listener thread if a callback raises."""

    def _safe() -> None:
        try:
            cb()
        except Exception:
            log.exception("Hotkey '%s' callback raised", combo)

    return _safe
