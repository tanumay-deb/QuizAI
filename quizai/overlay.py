"""Floating semi-transparent always-on-top overlay window.

Renders the current answer + explanation in a scrollable list when several
questions were extracted from one screenshot. Drag with the mouse to
reposition; click ✕ to dismiss; click 📌 to pin (disables auto-hide).

Multi-question state is owned by the overlay so the rest of the app can
just feed it a list of (question, answer, explanation) tuples and let the
overlay handle navigation.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPoint, Qt, QTimer, Signal
from PySide6.QtGui import QGuiApplication, QMouseEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from quizai.logger import get_logger

log = get_logger(__name__)


@dataclass
class QAEntry:
    """One question slot in the overlay's list.

    `answer` / `explanation` are None until that question has been answered;
    the overlay shows a "thinking" placeholder for unanswered slots.
    """

    question: str
    answer: str | None = None
    explanation: str | None = None


OVERLAY_QSS = """
#overlayRoot {
    background-color: rgba(20, 22, 28, 235);
    border: 1px solid rgba(255, 255, 255, 40);
    border-radius: 14px;
}
#overlayTitle {
    color: #e8eaf0;
    font-size: 12px;
    font-weight: 600;
    letter-spacing: 1px;
    text-transform: uppercase;
}
#overlayQuestion {
    color: #b5b9c4;
    font-size: 12px;
    font-style: italic;
}
#overlayAnswer {
    color: #ffffff;
    font-size: 16px;
    font-weight: 600;
}
#overlayExplanation {
    color: #d3d6de;
    font-size: 13px;
}
#overlayStatus {
    color: #ffd479;
    font-size: 13px;
    font-style: italic;
}
#overlayError {
    color: #ff8a8a;
    font-size: 13px;
}
QPushButton#overlayClose, QPushButton#overlayPin {
    background: transparent;
    color: #c5c9d2;
    border: none;
    font-size: 14px;
    padding: 2px 8px;
}
QPushButton#overlayClose:hover, QPushButton#overlayPin:hover {
    color: #ffffff;
}
QScrollArea, QScrollArea > QWidget > QWidget {
    background: transparent;
    border: none;
}
QScrollBar:vertical {
    background: transparent;
    width: 6px;
    margin: 2px;
}
QScrollBar::handle:vertical {
    background: rgba(255, 255, 255, 60);
    border-radius: 3px;
    min-height: 20px;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}
"""


class OverlayWindow(QWidget):
    """Frameless, always-on-top, semi-transparent answer display."""

    dismissed = Signal()
    # Fired when the user navigates to a question that hasn't been answered (legacy paginator support, mostly unused now since we queue all at once).
    question_answer_requested = Signal(int) 

    def __init__(self, opacity: float = 0.92, width: int = 480, max_height: int = 600):
        super().__init__()
        self._drag_offset: QPoint | None = None
        self._opacity = max(0.4, min(1.0, opacity))
        self._target_width = width
        self._max_height = max_height
        self._auto_hide_timer = QTimer(self)
        self._auto_hide_timer.setSingleShot(True)
        self._auto_hide_timer.timeout.connect(self._on_auto_hide)
        self._pinned = False

        # State
        self._entries: list[QAEntry] = []

        self._build_ui()
        self._apply_window_flags()
        self.setWindowOpacity(self._opacity)

    # -------------------------------------------------------------- UI build
    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        self._root = QFrame(self)
        self._root.setObjectName("overlayRoot")
        self._root.setStyleSheet(OVERLAY_QSS)
        outer.addWidget(self._root)

        root_layout = QVBoxLayout(self._root)
        root_layout.setContentsMargins(16, 12, 16, 14)
        root_layout.setSpacing(8)

        # Header row.
        header = QHBoxLayout()
        header.setSpacing(6)
        title = QLabel("QuizAI", self._root)
        title.setObjectName("overlayTitle")
        header.addWidget(title)
        header.addStretch(1)

        self._pin_btn = QPushButton("📌", self._root)
        self._pin_btn.setObjectName("overlayPin")
        self._pin_btn.setToolTip("Pin (disables auto-hide)")
        self._pin_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pin_btn.setCheckable(True)
        self._pin_btn.toggled.connect(self._on_pin_toggled)
        header.addWidget(self._pin_btn)

        close_btn = QPushButton("✕", self._root)
        close_btn.setObjectName("overlayClose")
        close_btn.setToolTip("Dismiss")
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.clicked.connect(self.dismiss)
        header.addWidget(close_btn)
        root_layout.addLayout(header)

        # Scrollable body.
        self._scroll = QScrollArea(self._root)
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setFrameShape(QFrame.Shape.NoFrame)

        self._body = QWidget(self._scroll)
        self._body_layout = QVBoxLayout(self._body)
        self._body_layout.setContentsMargins(0, 0, 0, 0)
        self._body_layout.setSpacing(8)

        self._body_layout.addStretch(1)
        self._scroll.setWidget(self._body)
        root_layout.addWidget(self._scroll, 1)

        self.setFixedWidth(self._target_width)
        self.resize(self._target_width, 160)


    def _apply_window_flags(self) -> None:
        flags = (
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setWindowFlags(flags)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)

    def _clear_body(self):
        while self._body_layout.count() > 1: # keeping the stretch at the end
            item = self._body_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

    # ------------------------------------------------------------- public API
    def set_opacity(self, opacity: float) -> None:
        self._opacity = max(0.4, min(1.0, opacity))
        self.setWindowOpacity(self._opacity)

    def set_width(self, width: int) -> None:
        self._target_width = max(280, int(width))
        self.setFixedWidth(self._target_width)

    def set_max_height(self, h: int) -> None:
        self._max_height = max(200, int(h))
        self._fit_height()

    def show_thinking(self, message: str = "Analyzing screenshot…") -> None:
        """Initial 'looking for question' state — no entries yet."""
        self._cancel_auto_hide()
        self._entries = []
        self._clear_body()
        lbl = QLabel(message, self._body)
        lbl.setObjectName("overlayStatus")
        self._body_layout.insertWidget(0, lbl)
        self._show_positioned()

    def show_error(self, message: str) -> None:
        self._cancel_auto_hide()
        self._entries = []
        self._clear_body()
        lbl = QLabel(message, self._body)
        lbl.setObjectName("overlayError")
        lbl.setWordWrap(True)
        self._body_layout.insertWidget(0, lbl)
        self._show_positioned()
        self._schedule_auto_hide(10_000)

    def show_no_question(self) -> None:
        self.show_error("No question detected on screen.")

    def show_single_answer(self, question: str, answer: str, explanation: str) -> None:
        """Backwards-compatible single-question display."""
        self.show_questions([question])
        self.set_answer_for(0, answer, explanation)

    def show_questions(self, questions: list[str]) -> None:
        """Populate the list with one or more questions. The orchestrator should call
        set_answer_for(i, ...) as each answer arrives."""
        self._cancel_auto_hide()
        self._entries = [QAEntry(question=q) for q in questions if q.strip()]
        if not self._entries:
            self.show_no_question()
            return
        self._render_all()
        self._show_positioned()

    def set_answer_for(self, index: int, answer: str, explanation: str) -> None:
        """Update one slot with its answer. Re-renders."""
        if not (0 <= index < len(self._entries)):
            return
        self._entries[index].answer = answer
        self._entries[index].explanation = explanation
        self._render_all()
        self._schedule_auto_hide(45_000)

    def set_error_for(self, index: int, message: str) -> None:
        """Mark a specific slot as failed. Renders the message in place."""
        if not (0 <= index < len(self._entries)):
            return
        self._entries[index].answer = f"(error: {message})"
        self._entries[index].explanation = ""
        self._render_all()
        self._schedule_auto_hide(20_000)

    def current_index(self) -> int:
        return 0

    def total_entries(self) -> int:
        return len(self._entries)

    def dismiss(self) -> None:
        self._cancel_auto_hide()
        self.hide()
        self.dismissed.emit()

    def _render_all(self) -> None:
        self._clear_body()
        
        for i, entry in enumerate(self._entries):
            container = QWidget()
            layout = QVBoxLayout(container)
            layout.setContentsMargins(0, 0, 0, 12)
            layout.setSpacing(6)
            
            q_preview = _truncate(entry.question, 500)
            q_lbl = QLabel(f"Q: {q_preview}")
            q_lbl.setObjectName("overlayQuestion")
            q_lbl.setWordWrap(True)
            layout.addWidget(q_lbl)
            
            if entry.answer is None:
                # Pending
                s_lbl = QLabel("Thinking…")
                s_lbl.setObjectName("overlayStatus")
                layout.addWidget(s_lbl)
            else:
                a_lbl = QLabel(entry.answer or "(no answer)")
                a_lbl.setObjectName("overlayAnswer")
                a_lbl.setWordWrap(True)
                layout.addWidget(a_lbl)
                
                if entry.explanation:
                    e_lbl = QLabel(entry.explanation)
                    e_lbl.setObjectName("overlayExplanation")
                    e_lbl.setWordWrap(True)
                    layout.addWidget(e_lbl)
            
            # Separator if not the last item
            if i < len(self._entries) - 1:
                line = QFrame()
                line.setFrameShape(QFrame.Shape.HLine)
                line.setStyleSheet("background-color: rgba(255, 255, 255, 20); border: none; height: 1px;")
                layout.addWidget(line)
            
            self._body_layout.insertWidget(self._body_layout.count() - 1, container)
            
        self._fit_height()

    # ----------------------------------------------------------- positioning
    def _show_positioned(self) -> None:
        self._fit_height()
        if not self.isVisible():
            self._center_top_right()
        self.show()
        self.raise_()

    def _fit_height(self) -> None:
        self._scroll.widget().adjustSize()
        ideal = self._scroll.widget().sizeHint().height() + 70
        h = max(140, min(self._max_height, ideal))
        self.resize(self._target_width, h)

    def _center_top_right(self) -> None:
        screen = QGuiApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        x = geo.right() - self.width() - 24
        y = geo.top() + 60
        self.move(max(geo.left(), x), max(geo.top(), y))

    # ------------------------------------------------------------- auto-hide
    def _schedule_auto_hide(self, ms: int) -> None:
        if self._pinned:
            return
        self._auto_hide_timer.start(ms)

    def _cancel_auto_hide(self) -> None:
        self._auto_hide_timer.stop()

    def _on_auto_hide(self) -> None:
        if self._pinned:
            return
        self.hide()

    def _on_pin_toggled(self, pinned: bool) -> None:
        self._pinned = pinned
        if pinned:
            self._cancel_auto_hide()

    # ----------------------------------------------------------------- drag
    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_offset = event.globalPosition().toPoint() - self.pos()
            event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._drag_offset is not None and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_offset)
            event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        self._drag_offset = None


def _truncate(s: str, n: int) -> str:
    s = s.strip().replace("\n", " ")
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"
