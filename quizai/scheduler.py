"""Background timer that periodically triggers a capture.

We use a plain threading.Event for sleep so the loop can be stopped or
re-tuned promptly when the user changes the interval.
"""

from __future__ import annotations

import threading
from collections.abc import Callable

from quizai.logger import get_logger

log = get_logger(__name__)


class AutoCaptureScheduler:
    def __init__(self, trigger: Callable[[], None]) -> None:
        self._trigger = trigger
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._interval = 0
        self._lock = threading.Lock()

    def set_interval(self, seconds: int) -> None:
        """Set the polling interval in seconds. 0 disables auto-capture."""
        with self._lock:
            self._interval = max(0, int(seconds))
            # Wake the loop so it picks up the new interval (or exits).
            self._stop_event.set()
            self._stop_event = threading.Event()
            self._start_if_needed_locked()

    def start(self) -> None:
        with self._lock:
            self._start_if_needed_locked()

    def stop(self) -> None:
        with self._lock:
            self._interval = 0
            self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _start_if_needed_locked(self) -> None:
        if self._interval <= 0:
            return
        if self._thread is not None and self._thread.is_alive():
            return
        self._thread = threading.Thread(target=self._run, name="quizai-auto-capture", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        log.info("Auto-capture scheduler started")
        while True:
            with self._lock:
                interval = self._interval
                stop_event = self._stop_event
            if interval <= 0:
                log.info("Auto-capture scheduler stopping (interval 0)")
                return
            # Wait the full interval before the first run too, so we don't
            # fire immediately on every reconfigure.
            if stop_event.wait(timeout=interval):
                # Either stopping or reconfiguring; loop back to re-check.
                continue
            try:
                self._trigger()
            except Exception:
                log.exception("Auto-capture trigger raised")
