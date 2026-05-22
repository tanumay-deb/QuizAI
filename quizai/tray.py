"""System tray icon and menu.

Uses Qt's QSystemTrayIcon. We generate a simple programmatic icon so the
package doesn't need any image assets.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from quizai.logger import get_logger

log = get_logger(__name__)


class TrayIcon(QObject):
    """Wrapper around QSystemTrayIcon exposing user-friendly signals."""

    capture_requested = Signal()
    toggle_window_requested = Signal()
    settings_requested = Signal()
    history_requested = Signal()
    quit_requested = Signal()

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        if not QSystemTrayIcon.isSystemTrayAvailable():
            log.warning("System tray not available on this platform; tray icon disabled.")
        self._tray = QSystemTrayIcon(self._make_icon(), parent)
        self._tray.setToolTip("QuizAI Assistant")

        self._menu = QMenu()

        act_capture = QAction("Capture now", self._menu)
        act_capture.triggered.connect(self.capture_requested.emit)
        self._menu.addAction(act_capture)

        act_window = QAction("Show / hide window", self._menu)
        act_window.triggered.connect(self.toggle_window_requested.emit)
        self._menu.addAction(act_window)

        act_history = QAction("Open history", self._menu)
        act_history.triggered.connect(self.history_requested.emit)
        self._menu.addAction(act_history)

        self._menu.addSeparator()

        act_settings = QAction("Settings…", self._menu)
        act_settings.triggered.connect(self.settings_requested.emit)
        self._menu.addAction(act_settings)

        self._menu.addSeparator()

        act_quit = QAction("Quit", self._menu)
        act_quit.triggered.connect(self.quit_requested.emit)
        self._menu.addAction(act_quit)

        self._tray.setContextMenu(self._menu)
        self._tray.activated.connect(self._on_activated)

    def show(self) -> None:
        if QSystemTrayIcon.isSystemTrayAvailable():
            self._tray.show()

    def hide(self) -> None:
        self._tray.hide()

    def notify(self, title: str, message: str, duration_ms: int = 4000) -> None:
        if not self._tray.isVisible():
            return
        try:
            self._tray.showMessage(
                title, message, QSystemTrayIcon.MessageIcon.Information, duration_ms
            )
        except Exception:
            log.debug("Tray notification failed silently")

    # ---------------------------------------------------------------- events
    def _on_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        # Left-click on Windows/Linux toggles the window. macOS only fires
        # Context on menu open, so a single click does nothing — that's fine.
        if reason == QSystemTrayIcon.ActivationReason.Trigger:
            self.toggle_window_requested.emit()
        elif reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self.capture_requested.emit()

    # ----------------------------------------------------------------- icon
    @staticmethod
    def _make_icon() -> QIcon:
        """Draw a simple Q glyph onto a square pixmap."""
        size = 64
        pix = QPixmap(size, size)
        pix.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pix)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            # Rounded square background.
            painter.setBrush(QColor(40, 110, 230))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(2, 2, size - 4, size - 4, 14, 14)

            # White "Q".
            font = painter.font()
            font.setBold(True)
            font.setPointSize(34)
            painter.setFont(font)
            painter.setPen(QPen(QColor("white")))
            painter.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, "Q")
        finally:
            painter.end()

        # Ensure HiDPI looks crisp.
        app = QApplication.instance()
        if app is not None:
            ratio = app.devicePixelRatio() if hasattr(app, "devicePixelRatio") else 1.0
            pix.setDevicePixelRatio(ratio)
        return QIcon(pix)
