"""Scrollable, color-coded log output panel."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont, QTextCharFormat
from PySide6.QtWidgets import QPlainTextEdit, QVBoxLayout, QWidget

from events import AgentEvent, EventType
from gui.bridge import EventBridge
from gui.styles import COLORS


class LogPanel(QWidget):
    """Scrollable log with content-aware coloring. Replaces the Tkinter overlay."""

    MAX_BLOCKS = 5000

    def __init__(self, bridge: EventBridge, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self._text = QPlainTextEdit()
        self._text.setReadOnly(True)
        self._text.setMaximumBlockCount(self.MAX_BLOCKS)
        self._text.setFont(QFont("Consolas", 9))
        self._text.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        layout.addWidget(self._text)

        # Pre-build text formats
        self._formats = {
            "default": self._make_fmt(COLORS["fg"]),
            "error": self._make_fmt(COLORS["error"]),
            "step": self._make_fmt(COLORS["step"]),
            "think": self._make_fmt(COLORS["think"]),
            "success": self._make_fmt(COLORS["success"]),
            "dim": self._make_fmt(COLORS["fg_dim"]),
        }

        bridge.event_received.connect(self._on_event)

    @staticmethod
    def _make_fmt(color: str) -> QTextCharFormat:
        fmt = QTextCharFormat()
        fmt.setForeground(QColor(color))
        return fmt

    def _append(self, text: str, fmt_key: str = "default"):
        cursor = self._text.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.insertText(text, self._formats[fmt_key])
        self._text.setTextCursor(cursor)
        self._text.ensureCursorVisible()

    def _append_auto(self, text: str):
        """Append with color auto-detected from content."""
        fmt = self._classify(text)
        self._append(text, fmt)

    @staticmethod
    def _classify(text: str) -> str:
        stripped = text.lstrip()
        if "ERROR" in text or "WARNING" in text:
            return "error"
        if "=====" in text or stripped.startswith("Step "):
            return "step"
        if stripped.startswith("Think:"):
            return "think"
        if "*** DONE" in text:
            return "success"
        if "--- DEBUG ---" in text or "--- END DEBUG ---" in text:
            return "dim"
        return "default"

    def _on_event(self, event: AgentEvent):
        match event.type:
            case EventType.LOG_MESSAGE:
                self._append_auto(event.message or "")
            case EventType.AGENT_STARTED:
                model = event.data.get("model", "?")
                model_id = event.data.get("model_id")
                goal = event.data.get("goal", "?")
                max_steps = event.data.get("max_steps", "?")
                self._append(f"Goal: {goal}\n", "step")
                model_str = model + (f" ({model_id})" if model_id else "")
                self._append(f"Model: {model_str}\n")
                self._append(f"Max steps: {max_steps}\n")
                self._append(f"Failsafe: move mouse to any corner to abort\n\n", "dim")
            case EventType.STEP_STARTED:
                self._append(f"\n{'='*60}\n", "step")
                self._append(f"Step {event.step}\n", "step")
                self._append(f"{'='*60}\n", "step")
            case EventType.STEP_LLM_CALL_STARTED:
                self._append(f"Calling LLM...\n", "dim")
            case EventType.STEP_LLM_CALL_FINISHED:
                think = event.data.get("think")
                if think:
                    self._append(f"Think: {think[:300]}\n", "think")
            case EventType.STEP_ACTION_EXECUTED:
                result = event.message or ""
                fmt = "error" if result.startswith("ERROR") else "default"
                self._append(f"  {result}\n", fmt)
            case EventType.AGENT_FINISHED:
                status = event.message or "unknown"
                done_reason = event.data.get("reason", "")
                if status == "done":
                    display = f"DONE: {done_reason}" if done_reason else "DONE"
                    self._append(f"\n*** {display} ***\n", "success")
                elif status == "stopped_by_user":
                    self._append(f"\n*** Stopped by user ***\n", "error")
                else:
                    self._append(f"\n*** Finished: {status} ***\n", "step")
            case EventType.AGENT_ERROR:
                self._append(f"\n[FATAL] {event.message}\n", "error")
