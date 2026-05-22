"""Top-level application orchestrator.

Wires together:

  - Qt event loop
  - System tray
  - Main window (manual input, history, settings)
  - Floating overlay (with multi-question paginator)
  - Global hotkeys
  - Auto-capture scheduler
  - Notifier (sound + desktop notifications)
  - Worker thread that talks to whichever LLM backend is configured
"""

from __future__ import annotations

import sys
from dataclasses import dataclass

from PySide6.QtCore import QMetaObject, QObject, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QApplication,
    QInputDialog,
    QLineEdit,
    QMessageBox,
)

from quizai import __app_name__
from quizai.backends import Backend, BackendError, create_backend
from quizai.config import Config, load_config, save_config
from quizai.history import add_entry, init_db
from quizai.hotkey_manager import HotkeyManager
from quizai.logger import get_logger, setup_logging
from quizai.main_window import MainWindow
from quizai.notifier import Notifier
from quizai.overlay import OverlayWindow
from quizai.mobile_server import MobileServer
from quizai.scheduler import AutoCaptureScheduler
from quizai.screen_capture import capture as capture_screen
from quizai.tray import TrayIcon

log = get_logger(__name__)


# =============================================================== worker jobs
@dataclass
class _ScreenJob:
    """Run vision on a screenshot, then auto-answer the first detected question."""

    png: bytes


@dataclass
class _ManualJob:
    """Answer a free-text question typed in the main window."""

    text: str


@dataclass
class _AnswerJob:
    """Answer one question from a paginator slot (used for the 2nd/3rd/...
    questions of a multi-question screenshot)."""

    index: int
    question: str


# ================================================================ ApiWorker
class ApiWorker(QObject):
    """Lives on a QThread; receives jobs and emits results back to the UI."""

    # Result signals.
    detection_started = Signal(str)  # source: "screen" | "manual"
    questions_extracted = Signal(list)  # list[str] from a screen job
    no_question_found = Signal()
    # source, question, answer, explanation, index (-1 for manual/legacy)
    answer_ready = Signal(str, str, str, str, int)
    api_error = Signal(str, int)  # message, index (-1 if not paginator)

    def __init__(self) -> None:
        super().__init__()
        self._backend: Backend | None = None

    @Slot(str, str, str)
    def set_backend(self, provider: str, api_key: str, model: str) -> None:
        """(Re)build the backend. Called via queued connection from GUI thread."""
        if not api_key:
            self._backend = None
            return
        try:
            self._backend = create_backend(provider=provider, api_key=api_key, model=model)
            log.info("Backend ready: provider=%s model=%s", provider, model)
        except BackendError as e:
            log.error("Backend init failed: %s", e)
            self._backend = None
            self.api_error.emit(str(e), -1)
        except Exception as e:
            log.exception("Unexpected error initialising backend")
            self._backend = None
            self.api_error.emit(f"Failed to initialise {provider} backend: {e}", -1)

    @Slot(object)
    def run_job(self, job: object) -> None:
        if self._backend is None:
            self.api_error.emit(
                "No API key set. Open Settings and add one — Gemini's is free.",
                -1,
            )
            return

        try:
            if isinstance(job, _ScreenJob):
                self._handle_screen(job)
            elif isinstance(job, _ManualJob):
                self._handle_manual(job)
            elif isinstance(job, _AnswerJob):
                self._handle_answer_index(job)
            else:
                self.api_error.emit(f"Unknown job type: {type(job).__name__}", -1)
        except BackendError as e:
            self.api_error.emit(str(e), _job_index(job))
        except Exception as e:
            log.exception("API job failed")
            self.api_error.emit(f"Unexpected error: {e}", _job_index(job))

    # ----------------------------------------------------------------- screen
    def _handle_screen(self, job: _ScreenJob) -> None:
        assert self._backend is not None
        self.detection_started.emit("screen")
        det = self._backend.detect_and_extract_question(job.png)
        if not det.has_question or not det.questions:
            self.no_question_found.emit()
            return
        # Tell the UI all the extracted questions so the overlay can build
        # its paginator. Then answer just the first one — subsequent ones
        # are answered lazily as the user navigates.
        self.questions_extracted.emit(list(det.questions))
        first_q = det.questions[0]
        ans = self._backend.answer_question(first_q)
        self.answer_ready.emit("screen", first_q, ans.answer, ans.explanation, 0)

    # ----------------------------------------------------------------- manual
    def _handle_manual(self, job: _ManualJob) -> None:
        assert self._backend is not None
        self.detection_started.emit("manual")
        question = (job.text or "").strip()
        if not question:
            self.api_error.emit("Empty question.", -1)
            return
        ans = self._backend.answer_question(question)
        self.answer_ready.emit("manual", question, ans.answer, ans.explanation, -1)

    # ------------------------------------------------- single-question answer
    def _handle_answer_index(self, job: _AnswerJob) -> None:
        assert self._backend is not None
        ans = self._backend.answer_question(job.question)
        self.answer_ready.emit("screen", job.question, ans.answer, ans.explanation, job.index)


def _job_index(job: object) -> int:
    if isinstance(job, _AnswerJob):
        return job.index
    return -1


# ================================================================ application
class QuizAIApp(QObject):
    """Single instance that owns the lifecycle of all windows/threads."""

    _job_requested = Signal(object)
    _backend_changed = Signal(str, str, str)

    def __init__(self, qapp: QApplication) -> None:
        super().__init__()
        self._qapp = qapp
        self._config: Config = load_config()
        # `_busy` covers the headline operation (screen capture / manual ask).
        # Lazy paginator answers run concurrently and don't lock the UI.
        self._busy: bool = False

        init_db()

        # ---- Windows.
        self._window = MainWindow(self._config)
        self._window.manual_question_submitted.connect(self._on_manual_question)
        self._window.capture_requested.connect(self._on_capture_requested)
        self._window.settings_changed.connect(self._on_settings_changed)

        self._overlay = OverlayWindow(
            opacity=self._config.overlay_opacity,
            width=self._config.overlay_width,
            max_height=self._config.overlay_max_height,
        )
        # When the user pages to an unanswered slot, the overlay asks us to
        # answer it. We dispatch a worker job.
        self._overlay.question_answer_requested.connect(self._on_paginator_answer_requested)

        # ---- Tray.
        self._tray = TrayIcon(self)
        self._tray.capture_requested.connect(self._on_capture_requested)
        self._tray.toggle_window_requested.connect(self._toggle_window)
        self._tray.history_requested.connect(self._show_window)
        self._tray.settings_requested.connect(self._window.open_settings)
        self._tray.quit_requested.connect(self.shutdown)
        self._tray.show()

        # ---- Notifier (sound + desktop notifications).
        self._notifier = Notifier(self._tray, self)
        self._notifier.set_sound_enabled(self._config.play_sound)
        self._notifier.set_notifications_enabled(self._config.show_notifications)

        # ---- API worker on its own thread.
        self._worker_thread = QThread(self)
        self._worker_thread.setObjectName("quizai-api")
        self._worker = ApiWorker()
        self._worker.moveToThread(self._worker_thread)

        self._job_requested.connect(self._worker.run_job, Qt.ConnectionType.QueuedConnection)
        self._backend_changed.connect(self._worker.set_backend, Qt.ConnectionType.QueuedConnection)
        self._worker.detection_started.connect(self._on_detection_started)
        self._worker.questions_extracted.connect(self._on_questions_extracted)
        self._worker.no_question_found.connect(self._on_no_question_found)
        self._worker.answer_ready.connect(self._on_answer_ready)
        self._worker.answer_ready.connect(self._on_answer_ready_mobile)
        self._worker.api_error.connect(self._on_api_error)

        self._worker_thread.start()

        # ---- Global hotkeys.
        self._hotkeys = HotkeyManager()
        self._apply_hotkeys()

        # ---- Auto-capture scheduler.
        self._scheduler = AutoCaptureScheduler(self._auto_capture_trigger)
        self._scheduler.set_interval(self._config.auto_capture_interval)

        # ---- Mobile companion server.
        self._mobile = MobileServer(self._config.mobile_server_port)
        if self._config.mobile_server_enabled:
            if self._mobile.start():
                self._window.set_mobile_url(self._mobile.local_url())

        # ---- API credentials.
        if not self._config.effective_api_key():
            self._prompt_for_api_key()
        self._push_backend_to_worker()

        if self._config.show_window_on_startup:
            self._show_window()

        self._notifier.notify(
            __app_name__,
            "Running in the system tray. Right-click the icon for options.",
        )

    # ------------------------------------------------------ shutdown / quit
    def shutdown(self) -> None:
        log.info("Shutting down")
        try:
            self._mobile.stop()
        except Exception:
            log.debug("Mobile server stop failed", exc_info=True)
        try:
            self._scheduler.stop()
        except Exception:
            log.debug("Scheduler stop failed", exc_info=True)
        try:
            self._hotkeys.stop()
        except Exception:
            log.debug("Hotkey stop failed", exc_info=True)

        self._worker_thread.quit()
        self._worker_thread.wait(2000)

        try:
            self._overlay.hide()
            self._window.hide()
            self._tray.hide()
        except Exception:
            pass

        self._qapp.quit()

    # ------------------------------------------------------ user-driven flows
    @Slot()
    def _on_capture_requested(self) -> None:
        if self._busy:
            log.debug("Capture request ignored — busy")
            return
        if not self._config.effective_api_key():
            self._on_api_error(
                "No API key set. Open Settings and add one — Gemini's is free.",
                -1,
            )
            return

        try:
            shot = capture_screen(self._config.capture_monitor)
        except Exception as e:
            log.exception("Screen capture failed")
            self._on_api_error(f"Screen capture failed: {e}", -1)
            return

        self._busy = True
        self._window.set_busy(True)
        self._overlay.show_thinking("Looking for a question…")
        self._job_requested.emit(_ScreenJob(png=shot.png_bytes))

    def _on_manual_question(self, text: str) -> None:
        if self._busy:
            QMessageBox.information(
                self._window,
                "Busy",
                "QuizAI is already processing a request. Please wait a moment.",
            )
            return
        if not self._config.effective_api_key():
            self._on_api_error(
                "No API key set. Open Settings and add one — Gemini's is free.",
                -1,
            )
            return

        self._busy = True
        self._window.set_busy(True)
        self._overlay.show_thinking("Thinking…")
        self._job_requested.emit(_ManualJob(text=text))

    def _on_paginator_answer_requested(self, index: int) -> None:
        """User paginated to an unanswered slot — fire a fresh job for that one.
        Does not set `_busy` since this is a secondary, on-demand operation."""
        # Pull the question text out of the overlay's state.
        total = self._overlay.total_entries()
        if index < 0 or index >= total:
            return
        # The overlay owns the QAEntry list. We access it via a small helper
        # rather than reaching into a private attr.
        entry_question = _question_at(self._overlay, index)
        if not entry_question:
            return
        self._job_requested.emit(_AnswerJob(index=index, question=entry_question))

    def _auto_capture_trigger(self) -> None:
        """Called from the scheduler's daemon thread; hops to the Qt thread."""
        QMetaObject.invokeMethod(
            self,
            "_on_capture_requested",
            Qt.ConnectionType.QueuedConnection,
        )

    # ------------------------------------------------ worker -> GUI handlers
    @Slot(str)
    def _on_detection_started(self, source: str) -> None:
        if source == "screen":
            self._overlay.show_thinking("Reading screen…")
        else:
            self._overlay.show_thinking("Thinking…")

    @Slot(list)
    def _on_questions_extracted(self, questions: list) -> None:
        """Vision found one or more questions. Populate the overlay paginator
        with placeholders; the first answer will arrive shortly via
        _on_answer_ready."""
        qs = [str(q) for q in questions if str(q).strip()]
        if not qs:
            return
        self._overlay.show_questions(qs)
        if len(qs) > 1:
            self._notifier.notify(
                __app_name__,
                f"Found {len(qs)} questions. Use ‹ › to navigate.",
            )

    @Slot()
    def _on_no_question_found(self) -> None:
        self._busy = False
        self._window.set_busy(False)
        self._overlay.show_no_question()
        self._notifier.notify(__app_name__, "No question detected on screen.")
        self._notifier.error_sound()

    @Slot(str, str, str, str, int)
    def _on_answer_ready(
        self,
        source: str,
        question: str,
        answer: str,
        explanation: str,
        index: int,
    ) -> None:
        # Persist every answered question, including paginator ones.
        try:
            add_entry(
                source=source,
                question=question,
                answer=answer,
                explanation=explanation,
                model=f"{self._config.provider}:{self._config.effective_model()}",
            )
        except Exception:
            log.exception("Failed to save history entry")

        if index >= 0:
            # Paginator answer — update the specific slot.
            self._overlay.set_answer_for(index, answer, explanation)
        else:
            # Manual or legacy single-question path.
            self._overlay.show_single_answer(question, answer, explanation)

        # Clear busy only for the headline operation. Paginator lazy-loads
        # don't toggle `_busy` (they were never set), so this is correct.
        if index in (0, -1):
            self._busy = False
            self._window.set_busy(False)

        self._window.refresh_history()
        self._notifier.chime()

    @Slot(str, str, str, str, int)
    def _on_answer_ready_mobile(
        self,
        source: str,
        question: str,
        answer: str,
        explanation: str,
        index: int,
    ) -> None:
        """Dedicated slot for mobile push — runs independently of _on_answer_ready."""
        log.info("Mobile slot fired: running=%s source=%s", self._mobile.running, source)
        if self._mobile.running:
            try:
                self._mobile.push_answer(question, answer, explanation)
            except Exception:
                log.exception("Mobile companion push failed")

    @Slot(str, int)
    def _on_api_error(self, message: str, index: int) -> None:
        if index >= 0:
            # Error specific to a paginator slot — show inline, keep overlay open.
            self._overlay.set_error_for(index, message)
        else:
            self._busy = False
            self._window.set_busy(False)
            self._overlay.show_error(message)
        log.warning("API error: %s (index=%d)", message, index)
        self._notifier.error_sound()

    # ----------------------------------------------------------- preferences
    def _on_settings_changed(self, new_cfg: Config) -> None:
        old_cfg = self._config
        self._config = new_cfg
        save_config(new_cfg)

        # Overlay appearance.
        self._overlay.set_opacity(new_cfg.overlay_opacity)
        self._overlay.set_width(new_cfg.overlay_width)
        self._overlay.set_max_height(new_cfg.overlay_max_height)

        # Notifier toggles.
        self._notifier.set_sound_enabled(new_cfg.play_sound)
        self._notifier.set_notifications_enabled(new_cfg.show_notifications)

        # Re-init backend if provider, key, or model changed.
        provider_changed = new_cfg.provider != old_cfg.provider
        key_changed = new_cfg.effective_api_key() != old_cfg.effective_api_key()
        model_changed = new_cfg.effective_model() != old_cfg.effective_model()
        if (provider_changed or key_changed or model_changed) and new_cfg.effective_api_key():
            self._push_backend_to_worker()

        self._scheduler.set_interval(new_cfg.auto_capture_interval)
        self._apply_hotkeys()

        mobile_port_changed = new_cfg.mobile_server_port != old_cfg.mobile_server_port
        mobile_enabled_changed = new_cfg.mobile_server_enabled != old_cfg.mobile_server_enabled
        if mobile_enabled_changed or mobile_port_changed:
            self._mobile.stop()
            self._mobile = MobileServer(new_cfg.mobile_server_port)
            if new_cfg.mobile_server_enabled:
                if self._mobile.start():
                    self._window.set_mobile_url(self._mobile.local_url())
                else:
                    self._window.set_mobile_url("")
            else:
                self._window.set_mobile_url("")

    def _push_backend_to_worker(self) -> None:
        key = self._config.effective_api_key()
        if not key:
            return
        self._backend_changed.emit(
            self._config.provider,
            key,
            self._config.effective_model(),
        )

    def _apply_hotkeys(self) -> None:
        if not self._hotkeys.is_available():
            log.info("Hotkeys unavailable on this system.")
            return
        bindings: dict[str, callable] = {}
        if self._config.hotkey_capture:
            bindings[self._config.hotkey_capture] = self._auto_capture_trigger
        if self._config.hotkey_toggle_window:
            bindings[self._config.hotkey_toggle_window] = self._invoke_in_qt(self._toggle_window)
        if self._config.hotkey_dismiss_overlay:
            bindings[self._config.hotkey_dismiss_overlay] = self._invoke_in_qt(
                self._overlay.dismiss
            )
        self._hotkeys.set_bindings(bindings)

    def _invoke_in_qt(self, fn) -> callable:
        """Return a callable that re-invokes `fn` on the Qt main thread."""

        def _hop() -> None:
            QTimer.singleShot(0, fn)

        return _hop

    # ----------------------------------------------------------------- misc
    def _show_window(self) -> None:
        self._window.show()
        self._window.raise_()
        self._window.activateWindow()
        self._window.refresh_history()

    def _toggle_window(self) -> None:
        if self._window.isVisible() and self._window.isActiveWindow():
            self._window.hide()
        else:
            self._show_window()

    def _prompt_for_api_key(self) -> None:
        provider = self._config.provider
        hint = (
            "Enter your Google Gemini API key (free at https://aistudio.google.com/apikey):"
            if provider == "gemini"
            else "Enter your Anthropic API key (starts with sk-ant-…):"
        )
        text, ok = QInputDialog.getText(
            None, f"{__app_name__} — API key", hint, QLineEdit.EchoMode.Password
        )
        if not ok:
            return
        text = (text or "").strip()
        if not text:
            return
        self._config.set_api_key_for_provider(provider, text)
        save_config(self._config)


# ---------------------------------------------------------------- small helper
def _question_at(overlay: OverlayWindow, index: int) -> str:
    """Tiny accessor so the orchestrator doesn't poke into overlay internals."""
    entries = getattr(overlay, "_entries", None)
    if not entries:
        return ""
    if 0 <= index < len(entries):
        return entries[index].question
    return ""


# =========================================================== entry point
def run() -> int:
    setup_logging()
    log.info("Starting %s", __app_name__)

    QApplication.setQuitOnLastWindowClosed(False)
    QGuiApplication.setApplicationName(__app_name__)
    QGuiApplication.setOrganizationName("QuizAI")

    qapp = QApplication(sys.argv)
    qapp.setQuitOnLastWindowClosed(False)

    app = QuizAIApp(qapp)
    qapp._quizai = app  # type: ignore[attr-defined]

    return qapp.exec()
