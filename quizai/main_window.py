"""Main application window and settings dialog.

Window: manual question input + searchable history browser.
Settings: provider/key/model + hotkeys + overlay appearance + capture +
notifications.

Closing the window hides it; the app stays alive in the system tray.
"""

from __future__ import annotations

import csv
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QCloseEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QFrame,
    QSpinBox,
    QSplitter,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from quizai import __app_name__, __version__
from quizai.backends import PROVIDER_INFO
from quizai.config import Config
from quizai.history import HistoryEntry, clear_all, delete_entry, list_entries
from quizai.logger import get_logger
from quizai.screen_capture import list_monitors

log = get_logger(__name__)


MAIN_QSS = """
QWidget {
    background-color: #181a20;
    color: #e8eaf0;
    font-family: -apple-system, "Segoe UI", "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
}
QPlainTextEdit, QLineEdit, QTextBrowser, QListWidget, QSpinBox, QDoubleSpinBox, QComboBox {
    background-color: #22252e;
    color: #f0f2f8;
    border: 1px solid #2f333d;
    border-radius: 6px;
    padding: 6px 8px;
    selection-background-color: #3d6cc4;
}
QPlainTextEdit:focus, QLineEdit:focus, QTextBrowser:focus, QListWidget:focus,
QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
    border: 1px solid #4c84e0;
}
/* The padding above squeezes the up-button out of its hit area (up stops
   working while down still does) unless we anchor the buttons to the border
   box and give them an explicit width. */
QSpinBox::up-button, QDoubleSpinBox::up-button {
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 18px;
    border-left: 1px solid #2f333d;
    border-top-right-radius: 6px;
}
QSpinBox::down-button, QDoubleSpinBox::down-button {
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 18px;
    border-left: 1px solid #2f333d;
    border-bottom-right-radius: 6px;
}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {
    background-color: #2c3140;
}
QPushButton {
    background-color: #2c3140;
    color: #f0f2f8;
    border: 1px solid #353a47;
    border-radius: 6px;
    padding: 6px 14px;
}
QPushButton:hover { background-color: #353a47; }
QPushButton:pressed { background-color: #262a36; }
QPushButton:disabled { color: #777a86; background-color: #20232c; }
QPushButton#primary {
    background-color: #3d6cc4;
    border: 1px solid #4c84e0;
}
QPushButton#primary:hover { background-color: #4c84e0; }
QPushButton#primary:disabled { background-color: #2a3a5a; color: #99a1b3; }
QLabel#sectionHeader {
    color: #ffffff;
    font-size: 13px;
    font-weight: 600;
    letter-spacing: 0.5px;
}
QLabel#hint {
    color: #8b909e;
    font-size: 11px;
}
QListWidget::item { padding: 8px 6px; border-bottom: 1px solid #2a2d36; }
QListWidget::item:selected { background-color: #324569; }
QSplitter::handle { background: #2a2d36; }
QSplitter::handle:horizontal { width: 4px; }
QScrollBar:vertical {
    background: #181a20; width: 10px; margin: 0;
}
QScrollBar::handle:vertical {
    background: #353a47; border-radius: 5px; min-height: 24px;
}
QScrollBar::handle:vertical:hover { background: #4a5060; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
"""


# ===================================================================== window
class MainWindow(QWidget):
    manual_question_submitted = Signal(str)
    followup_submitted = Signal(str, str)  # follow-up text, prior context
    capture_requested = Signal()
    settings_changed = Signal(Config)

    def __init__(self, config: Config) -> None:
        super().__init__()
        self._config = config
        self.setWindowTitle(__app_name__)
        self.resize(960, 600)
        self.setStyleSheet(MAIN_QSS)
        self._build_ui()
        self.refresh_history()

        esc = QShortcut(QKeySequence("Esc"), self)
        esc.activated.connect(self.hide)

    # --------------------------------------------------------------- UI build
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        # Top toolbar.
        toolbar = QHBoxLayout()
        title = QLabel(__app_name__)
        title.setObjectName("sectionHeader")
        f = title.font()
        f.setPointSize(15)
        title.setFont(f)
        toolbar.addWidget(title)
        toolbar.addStretch(1)

        self._capture_btn = QPushButton("Capture screen now")
        self._capture_btn.clicked.connect(self.capture_requested.emit)
        toolbar.addWidget(self._capture_btn)

        self._settings_btn = QPushButton("Settings…")
        self._settings_btn.clicked.connect(self.open_settings)
        toolbar.addWidget(self._settings_btn)
        root.addLayout(toolbar)

        self._mobile_bar = QLabel("")
        self._mobile_bar.setObjectName("hint")
        self._mobile_bar.setTextFormat(Qt.TextFormat.RichText)
        self._mobile_bar.setOpenExternalLinks(True)
        self._mobile_bar.hide()
        root.addWidget(self._mobile_bar)

        splitter = QSplitter(Qt.Orientation.Horizontal, self)

        # ---- Left pane.
        left = QWidget(splitter)
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        ask_header = QLabel("Ask a question")
        ask_header.setObjectName("sectionHeader")
        left_layout.addWidget(ask_header)

        self._input = QPlainTextEdit()
        self._input.setPlaceholderText(
            "Type or paste a question, then press Ctrl+Enter or click Ask."
        )
        self._input.setFixedHeight(120)
        left_layout.addWidget(self._input)

        ask_row = QHBoxLayout()
        ask_row.addStretch(1)
        self._ask_btn = QPushButton("Ask AI")
        self._ask_btn.setObjectName("primary")
        self._ask_btn.clicked.connect(self._on_ask_clicked)
        ask_row.addWidget(self._ask_btn)
        left_layout.addLayout(ask_row)

        QShortcut(QKeySequence("Ctrl+Return"), self._input).activated.connect(self._on_ask_clicked)
        QShortcut(QKeySequence("Ctrl+Enter"), self._input).activated.connect(self._on_ask_clicked)

        detail_header = QLabel("Selected entry")
        detail_header.setObjectName("sectionHeader")
        left_layout.addWidget(detail_header)

        self._detail = QTextBrowser()
        self._detail.setOpenExternalLinks(True)
        left_layout.addWidget(self._detail, 1)

        # Follow-up input — visible whenever an entry is selected.
        followup_row = QHBoxLayout()
        self._followup_input = QLineEdit()
        self._followup_input.setPlaceholderText(
            "Ask a follow-up about this entry (e.g. \"explain step 3 more\")…"
        )
        self._followup_input.returnPressed.connect(self._on_followup_clicked)
        followup_row.addWidget(self._followup_input, 1)
        self._followup_btn = QPushButton("Ask follow-up")
        self._followup_btn.clicked.connect(self._on_followup_clicked)
        followup_row.addWidget(self._followup_btn)
        left_layout.addLayout(followup_row)

        splitter.addWidget(left)

        # ---- Right pane (history).
        right = QWidget(splitter)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        hist_row = QHBoxLayout()
        hist_header = QLabel("History")
        hist_header.setObjectName("sectionHeader")
        hist_row.addWidget(hist_header)
        hist_row.addStretch(1)
        right_layout.addLayout(hist_row)

        filter_row = QHBoxLayout()
        self._search = QLineEdit()
        self._search.setPlaceholderText("Search question, answer, explanation…")
        self._search.textChanged.connect(lambda _t: self.refresh_history())
        filter_row.addWidget(self._search, 1)

        self._source_filter = QComboBox()
        # itemData = source string, "" means all.
        self._source_filter.addItem("All sources", "")
        self._source_filter.addItem("Screen", "screen")
        self._source_filter.addItem("Manual", "manual")
        self._source_filter.addItem("Telegram", "telegram")
        self._source_filter.currentIndexChanged.connect(lambda _i: self.refresh_history())
        filter_row.addWidget(self._source_filter)
        right_layout.addLayout(filter_row)

        self._history_list = QListWidget()
        self._history_list.currentItemChanged.connect(self._on_history_selected)
        right_layout.addWidget(self._history_list, 1)

        hist_buttons = QHBoxLayout()
        self._delete_btn = QPushButton("Delete")
        self._delete_btn.clicked.connect(self._on_delete_clicked)
        hist_buttons.addWidget(self._delete_btn)
        self._clear_btn = QPushButton("Clear all")
        self._clear_btn.clicked.connect(self._on_clear_clicked)
        hist_buttons.addWidget(self._clear_btn)
        self._export_btn = QPushButton("Export…")
        self._export_btn.clicked.connect(self._on_export_clicked)
        hist_buttons.addWidget(self._export_btn)
        hist_buttons.addStretch(1)
        right_layout.addLayout(hist_buttons)

        splitter.addWidget(right)
        splitter.setSizes([560, 380])
        root.addWidget(splitter, 1)

        hint = QLabel(
            "Tip: closing this window keeps QuizAI running in the system tray. "
            "Reopen it from the tray icon."
        )
        hint.setObjectName("hint")
        hint.setWordWrap(True)
        root.addWidget(hint)

    # ---------------------------------------------------------------- events
    def closeEvent(self, event: QCloseEvent) -> None:
        event.ignore()
        self.hide()

    def _on_ask_clicked(self) -> None:
        text = self._input.toPlainText().strip()
        if not text:
            return
        self._input.clear()
        self.manual_question_submitted.emit(text)

    def _on_followup_clicked(self) -> None:
        text = self._followup_input.text().strip()
        if not text:
            return
        item = self._history_list.currentItem()
        entry: HistoryEntry | None = (
            item.data(Qt.ItemDataRole.UserRole + 1) if item else None
        )
        if entry is None:
            QMessageBox.information(
                self,
                "No entry selected",
                "Select an entry on the right first — its question and answer "
                "will be sent as context for the follow-up.",
            )
            return
        context = (
            f"Q: {entry.question}\n"
            f"A: {entry.answer}\n"
            f"Explanation: {entry.explanation}"
        )
        self._followup_input.clear()
        self.followup_submitted.emit(text, context)

    def _on_delete_clicked(self) -> None:
        item = self._history_list.currentItem()
        if item is None:
            return
        entry_id = item.data(Qt.ItemDataRole.UserRole)
        if not entry_id:
            return
        delete_entry(int(entry_id))
        self.refresh_history()
        self._detail.clear()

    def _on_clear_clicked(self) -> None:
        confirm = QMessageBox.question(
            self,
            "Clear all history?",
            "This will permanently delete every saved Q&A entry. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if confirm == QMessageBox.StandardButton.Yes:
            clear_all()
            self.refresh_history()
            self._detail.clear()

    def _on_history_selected(
        self, current: QListWidgetItem | None, _previous: QListWidgetItem | None
    ) -> None:
        if current is None:
            self._detail.clear()
            return
        entry: HistoryEntry | None = current.data(Qt.ItemDataRole.UserRole + 1)
        if entry is None:
            return
        self._detail.setHtml(_render_entry_html(entry))

    # -------------------------------------------------------- public actions
    def set_busy(self, busy: bool) -> None:
        self._ask_btn.setEnabled(not busy)
        self._capture_btn.setEnabled(not busy)
        self._followup_btn.setEnabled(not busy)
        self._ask_btn.setText("Asking…" if busy else "Ask AI")
        self._followup_btn.setText("Asking…" if busy else "Ask follow-up")

    def refresh_history(self) -> None:
        search = self._search.text().strip() or None
        source = (self._source_filter.currentData() or "") if hasattr(self, "_source_filter") else ""
        entries = list_entries(limit=500, search=search, source=source or None)
        self._history_list.clear()
        for e in entries:
            item = QListWidgetItem(_short_label(e))
            item.setData(Qt.ItemDataRole.UserRole, e.id)
            item.setData(Qt.ItemDataRole.UserRole + 1, e)
            self._history_list.addItem(item)
        if self._history_list.count() > 0:
            self._history_list.setCurrentRow(0)
        else:
            self._detail.setHtml(
                "<p style='color:#8b909e'>No history yet. Ask a question or "
                "trigger a screen capture to get started.</p>"
            )

    def _on_export_clicked(self) -> None:
        """Export the currently-visible history rows to Markdown or CSV."""
        rows: list[HistoryEntry] = []
        for i in range(self._history_list.count()):
            item = self._history_list.item(i)
            entry = item.data(Qt.ItemDataRole.UserRole + 1) if item else None
            if isinstance(entry, HistoryEntry):
                rows.append(entry)
        if not rows:
            QMessageBox.information(self, "Nothing to export", "There are no entries to export.")
            return
        path_str, selected_filter = QFileDialog.getSaveFileName(
            self,
            "Export history",
            "quizai-history.md",
            "Markdown (*.md);;CSV (*.csv)",
        )
        if not path_str:
            return
        path = Path(path_str)
        try:
            if path.suffix.lower() == ".csv" or "CSV" in selected_filter:
                _write_history_csv(path, rows)
            else:
                _write_history_markdown(path, rows)
        except OSError as exc:
            QMessageBox.warning(self, "Export failed", f"Could not write {path}: {exc}")
            return
        QMessageBox.information(self, "Export complete", f"Exported {len(rows)} entries to:\n{path}")

    def open_settings(self) -> None:
        dlg = SettingsDialog(self._config, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            new_cfg = dlg.result_config()
            self._config = new_cfg
            self.settings_changed.emit(new_cfg)

    def set_mobile_url(self, url: str) -> None:
        if url:
            self._mobile_bar.setText(
                f"Mobile companion active — open on your phone: "
                f"<a href='{url}' style='color:#8ab4f8;'>{url}</a>"
            )
            self._mobile_bar.show()
        else:
            self._mobile_bar.hide()

    def apply_config(self, cfg: Config) -> None:
        self._config = cfg


# --------------------------------------------------------------------- helpers
def _short_label(e: HistoryEntry) -> str:
    q = e.question.replace("\n", " ").strip()
    if len(q) > 80:
        q = q[:79] + "…"
    ts = e.timestamp.replace("T", " ").split("+")[0]
    return f"{ts}  •  {q}"


def _write_history_csv(path: Path, rows: list[HistoryEntry]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["timestamp", "source", "model", "question", "answer", "explanation"])
        for e in rows:
            w.writerow([e.timestamp, e.source, e.model, e.question, e.answer, e.explanation])


def _write_history_markdown(path: Path, rows: list[HistoryEntry]) -> None:
    lines: list[str] = ["# QuizAI history", ""]
    for e in rows:
        lines.append(f"## {e.timestamp} — {e.source}")
        lines.append("")
        lines.append(f"**Q.** {e.question}")
        lines.append("")
        lines.append(f"**A.** {e.answer}")
        if e.explanation:
            lines.append("")
            lines.append(e.explanation)
        lines.append("")
        lines.append(f"<sub>model: {e.model}</sub>")
        lines.append("")
        lines.append("---")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _render_entry_html(e: HistoryEntry) -> str:
    def esc(s: str) -> str:
        return (
            s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
        )

    return f"""
    <div style="color:#8b909e; font-size:11px; margin-bottom:6px;">
      {esc(e.timestamp)} &nbsp;•&nbsp; source: {esc(e.source)} &nbsp;•&nbsp; model: {esc(e.model)}
    </div>
    <div style="color:#b5b9c4; font-size:12px; margin-bottom:8px;">
      <b style="color:#dde0e8;">Question</b><br>{esc(e.question)}
    </div>
    <div style="color:#ffffff; font-size:14px; font-weight:600; margin-bottom:8px;">
      <span style="color:#8be3a4;">Answer:</span> {esc(e.answer)}
    </div>
    <div style="color:#d3d6de; font-size:13px;">
      <b style="color:#dde0e8;">Explanation</b><br>{esc(e.explanation) or '<i style="color:#8b909e;">(none)</i>'}
    </div>
    """


# ===================================================================== Settings
class SettingsDialog(QDialog):
    """Edit config: provider, API key, model, intervals, hotkeys, overlay,
    notifications."""

    def __init__(self, config: Config, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("QuizAI Settings")
        self.setMinimumWidth(540)
        self.setStyleSheet(MAIN_QSS)
        self._original = config
        self._draft = Config.from_dict(config.to_dict())
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("QScrollArea { background: transparent; }")
        
        scroll_widget = QWidget()
        scroll_widget.setStyleSheet("QWidget { background: transparent; }")
        
        form = QFormLayout(scroll_widget)
        form.setSpacing(8)

        # ---- Provider.
        self._provider = QComboBox()
        for pid, info in PROVIDER_INFO.items():
            self._provider.addItem(info["label"], pid)
        self._select_provider_in_combo(self._draft.provider)
        self._provider.currentIndexChanged.connect(self._on_provider_changed)
        form.addRow("Provider:", self._provider)

        self._api_key_label = QLabel("API key:")
        self._api_key = QLineEdit()
        self._api_key.setEchoMode(QLineEdit.EchoMode.Password)
        self._api_key.editingFinished.connect(self._on_key_edited)
        form.addRow(self._api_key_label, self._api_key)

        self._show_key = QCheckBox("Show key")
        self._show_key.toggled.connect(
            lambda on: self._api_key.setEchoMode(
                QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password
            )
        )
        form.addRow("", self._show_key)

        self._key_help = QLabel("")
        self._key_help.setObjectName("hint")
        self._key_help.setWordWrap(True)
        self._key_help.setOpenExternalLinks(True)
        form.addRow("", self._key_help)

        # Base URL — only shown for the OpenAI-compatible provider.
        self._base_url_label = QLabel("Base URL:")
        self._base_url = QLineEdit()
        self._base_url.setPlaceholderText("https://api.openai.com/v1")
        self._base_url.editingFinished.connect(self._on_base_url_edited)
        form.addRow(self._base_url_label, self._base_url)

        self._model = QComboBox()
        self._model.setEditable(True)
        self._model.currentTextChanged.connect(self._on_model_changed)
        form.addRow("Model:", self._model)

        # ---- Capture & scheduling.
        self._interval = QSpinBox()
        self._interval.setRange(0, 3600)
        self._interval.setSuffix(" s")
        self._interval.setValue(self._draft.auto_capture_interval)
        self._interval.setToolTip("0 disables automatic background captures.")
        form.addRow("Auto-capture interval:", self._interval)

        self._capture_monitor = QComboBox()
        monitors = list_monitors()
        if not monitors:
            # Fallback when mss couldn't enumerate (headless / permission denied).
            monitors_labels = [(0, "All monitors")]
            for i in range(1, 9):
                monitors_labels.append((i, f"Monitor {i}"))
            for idx, label in monitors_labels:
                self._capture_monitor.addItem(label, idx)
        else:
            for m in monitors:
                self._capture_monitor.addItem(m.label, m.index)
        self._select_monitor_in_combo(self._draft.capture_monitor)
        self._capture_monitor.setToolTip(
            "Choose which monitor to capture. \"All monitors\" stitches them together."
        )
        form.addRow("Capture monitor:", self._capture_monitor)

        # ---- Notifications.
        self._play_sound = QCheckBox("Play a sound when an answer arrives")
        self._play_sound.setChecked(self._draft.play_sound)
        form.addRow("Sound:", self._play_sound)

        self._show_notifications = QCheckBox("Show desktop notifications")
        self._show_notifications.setChecked(self._draft.show_notifications)
        form.addRow("Notifications:", self._show_notifications)

        # ---- Hotkeys.
        self._hk_capture = QLineEdit(self._draft.hotkey_capture)
        self._hk_capture.setPlaceholderText("<ctrl>+<shift>+q")
        form.addRow("Hotkey — capture:", self._hk_capture)

        self._hk_toggle = QLineEdit(self._draft.hotkey_toggle_window)
        self._hk_toggle.setPlaceholderText("<ctrl>+<shift>+h")
        form.addRow("Hotkey — show/hide window:", self._hk_toggle)

        self._hk_dismiss = QLineEdit(self._draft.hotkey_dismiss_overlay)
        self._hk_dismiss.setPlaceholderText("<ctrl>+<shift>+x")
        form.addRow("Hotkey — dismiss overlay:", self._hk_dismiss)

        self._hk_quit = QLineEdit(getattr(self._draft, "hotkey_quit", ""))
        self._hk_quit.setPlaceholderText("e.g. <ctrl>+<shift>+k")
        form.addRow("Hotkey — stop the bot:", self._hk_quit)

        self._hk_quit_alt = QLineEdit(getattr(self._draft, "hotkey_quit_alt", ""))
        self._hk_quit_alt.setPlaceholderText("e.g. <alt>+q")
        form.addRow("Hotkey — stop the bot (alt):", self._hk_quit_alt)

        # ---- Overlay.
        self._opacity = QDoubleSpinBox()
        self._opacity.setRange(0.4, 1.0)
        self._opacity.setSingleStep(0.05)
        self._opacity.setDecimals(2)
        self._opacity.setValue(self._draft.overlay_opacity)
        form.addRow("Overlay opacity:", self._opacity)

        self._width = QSpinBox()
        self._width.setRange(320, 1200)
        self._width.setSuffix(" px")
        self._width.setValue(self._draft.overlay_width)
        form.addRow("Overlay width:", self._width)

        self._max_height = QSpinBox()
        self._max_height.setRange(220, 1600)
        self._max_height.setSuffix(" px")
        self._max_height.setValue(self._draft.overlay_max_height)
        form.addRow("Overlay max height:", self._max_height)

        # ---- Mobile companion.
        self._mobile_enabled = QCheckBox("Enable mobile companion (local Wi-Fi)")
        self._mobile_enabled.setChecked(self._draft.mobile_server_enabled)
        form.addRow("Mobile companion:", self._mobile_enabled)

        self._mobile_port = QSpinBox()
        self._mobile_port.setRange(1024, 65535)
        self._mobile_port.setValue(self._draft.mobile_server_port)
        self._mobile_port.setToolTip(
            "Port the mobile web page is served on. Change if 7432 is already in use."
        )
        form.addRow("Mobile port:", self._mobile_port)

        # ---- Telegram companion.
        self._telegram_enabled = QCheckBox("Enable two-way Telegram companion")
        self._telegram_enabled.setChecked(self._draft.telegram_enabled)
        form.addRow("Telegram bot:", self._telegram_enabled)

        self._telegram_token = QLineEdit()
        self._telegram_token.setEchoMode(QLineEdit.EchoMode.Password)
        self._telegram_token.setText(self._draft.telegram_token)
        form.addRow("Telegram bot token:", self._telegram_token)

        self._telegram_chat_id = QLineEdit()
        self._telegram_chat_id.setText(self._draft.telegram_chat_id)
        self._telegram_chat_id.setPlaceholderText("123456 (or comma-separated: 123, 456)")
        form.addRow("Telegram chat ID(s):", self._telegram_chat_id)

        self._telegram_help = QLabel(
            "1. Talk to <a href='https://t.me/BotFather' style='color:#8ab4f8;'>@BotFather</a> to create a bot & get a token.<br>"
            "2. Send any message to your new bot.<br>"
            "3. Talk to <a href='https://t.me/userinfobot' style='color:#8ab4f8;'>@userinfobot</a> to get your chat ID.<br>"
            "Multiple IDs: separate with commas to allow several people (group access)."
        )
        self._telegram_help.setObjectName("hint")
        self._telegram_help.setWordWrap(True)
        self._telegram_help.setOpenExternalLinks(True)
        form.addRow("", self._telegram_help)

        # ---- Caching.
        self._cache_enabled = QCheckBox("Reuse previous answers for identical questions")
        self._cache_enabled.setChecked(self._draft.question_cache_enabled)
        form.addRow("Question cache:", self._cache_enabled)

        self._cache_days = QSpinBox()
        self._cache_days.setRange(1, 365)
        self._cache_days.setSuffix(" days")
        self._cache_days.setValue(self._draft.question_cache_days)
        self._cache_days.setToolTip(
            "How far back to look when matching a new question against past answers."
        )
        form.addRow("Cache age limit:", self._cache_days)

        # ---- Misc.
        self._startup = QCheckBox("Show main window on startup")
        self._startup.setChecked(self._draft.show_window_on_startup)
        form.addRow("", self._startup)

        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)

        footer = QLabel(
            "Hotkey format: <code>&lt;ctrl&gt;+&lt;shift&gt;+q</code>. "
            "Leave a hotkey blank to disable it.<br>"
            f"QuizAI Assistant v{__version__}"
        )
        footer.setObjectName("hint")
        footer.setWordWrap(True)
        footer.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(footer)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

        self._refresh_for_provider()

    # ---------------------------------------------------- provider switching
    def _current_provider(self) -> str:
        return self._provider.currentData() or self._draft.provider

    def _select_provider_in_combo(self, provider: str) -> None:
        for i in range(self._provider.count()):
            if self._provider.itemData(i) == provider:
                self._provider.setCurrentIndex(i)
                return
        self._provider.setCurrentIndex(0)

    def _select_monitor_in_combo(self, monitor: int) -> None:
        for i in range(self._capture_monitor.count()):
            if self._capture_monitor.itemData(i) == monitor:
                self._capture_monitor.setCurrentIndex(i)
                return
        self._capture_monitor.setCurrentIndex(0)

    def _on_provider_changed(self, _idx: int) -> None:
        self._draft.provider = self._current_provider()
        self._refresh_for_provider()

    def _refresh_for_provider(self) -> None:
        provider = self._current_provider()
        info = PROVIDER_INFO.get(provider, {})

        # Field label + echo mode depend on provider (Ollama uses a plaintext host URL).
        self._api_key_label.setText(info.get("key_label", "API key:"))
        is_secret = bool(info.get("key_is_secret", True))
        if is_secret:
            self._api_key.setEchoMode(
                QLineEdit.EchoMode.Normal
                if self._show_key.isChecked()
                else QLineEdit.EchoMode.Password
            )
            self._show_key.show()
        else:
            self._api_key.setEchoMode(QLineEdit.EchoMode.Normal)
            self._show_key.hide()

        self._api_key.blockSignals(True)
        current = self._draft.api_key_for_provider(provider)
        # Show a sensible default for Ollama if nothing's saved yet.
        if provider == "ollama" and not current.strip():
            from quizai.config import DEFAULT_OLLAMA_HOST
            current = DEFAULT_OLLAMA_HOST
        self._api_key.setText(current)
        self._api_key.blockSignals(False)

        help_text = info.get("key_help", "")
        for url in (
            "https://aistudio.google.com/apikey",
            "https://console.anthropic.com/",
            "https://ollama.com/download",
        ):
            help_text = help_text.replace(
                url,
                f"<a href='{url}' style='color:#8ab4f8;'>{url}</a>",
            )
        self._key_help.setText(help_text)

        # Base URL field is only relevant for the OpenAI-compatible provider.
        needs_base_url = bool(info.get("needs_base_url", False))
        self._base_url_label.setVisible(needs_base_url)
        self._base_url.setVisible(needs_base_url)
        if needs_base_url:
            from quizai.config import DEFAULT_OPENAI_BASE_URL
            self._base_url.blockSignals(True)
            self._base_url.setText(self._draft.openai_base_url or DEFAULT_OPENAI_BASE_URL)
            self._base_url.blockSignals(False)

        self._model.blockSignals(True)
        self._model.clear()
        models = list(info.get("models", []))
        current_model = self._draft.models.get(provider, "") or (models[0] if models else "")
        for m in models:
            self._model.addItem(m)
        if current_model and current_model not in models:
            self._model.addItem(current_model)
        self._model.setCurrentText(current_model)
        self._model.blockSignals(False)

    def _on_key_edited(self) -> None:
        provider = self._current_provider()
        self._draft.set_api_key_for_provider(provider, self._api_key.text())

    def _on_model_changed(self, text: str) -> None:
        provider = self._current_provider()
        self._draft.set_model_for_provider(provider, text)

    def _on_base_url_edited(self) -> None:
        self._draft.openai_base_url = self._base_url.text().strip()

    # --------------------------------------------------------------- accept
    def result_config(self) -> Config:
        self._on_key_edited()
        self._on_model_changed(self._model.currentText())

        c = self._draft
        # Persist Base URL only for the OpenAI-compatible provider (the field is
        # hidden otherwise and would clobber the saved value with a blank).
        if self._current_provider() == "openai":
            from quizai.config import DEFAULT_OPENAI_BASE_URL
            c.openai_base_url = self._base_url.text().strip() or DEFAULT_OPENAI_BASE_URL

        c.auto_capture_interval = int(self._interval.value())
        mon_data = self._capture_monitor.currentData()
        c.capture_monitor = int(mon_data) if mon_data is not None else 0

        c.play_sound = self._play_sound.isChecked()
        c.show_notifications = self._show_notifications.isChecked()

        c.hotkey_capture = self._hk_capture.text().strip()
        c.hotkey_toggle_window = self._hk_toggle.text().strip()
        c.hotkey_dismiss_overlay = self._hk_dismiss.text().strip()
        c.hotkey_quit = self._hk_quit.text().strip()
        c.hotkey_quit_alt = self._hk_quit_alt.text().strip()

        c.overlay_opacity = float(self._opacity.value())
        c.overlay_width = int(self._width.value())
        c.overlay_max_height = int(self._max_height.value())

        c.mobile_server_enabled = self._mobile_enabled.isChecked()
        c.mobile_server_port = int(self._mobile_port.value())

        c.telegram_enabled = self._telegram_enabled.isChecked()
        c.telegram_token = self._telegram_token.text().strip()
        c.telegram_chat_id = self._telegram_chat_id.text().strip()

        c.question_cache_enabled = self._cache_enabled.isChecked()
        c.question_cache_days = int(self._cache_days.value())

        c.show_window_on_startup = self._startup.isChecked()
        return c
