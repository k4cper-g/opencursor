"""Compact run overlay — positioned top-right, capture-hidden, minimal UI."""

import time

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from events import AgentEventBus
from gui.bridge import EventBridge
from gui.capture_hide import hide_from_capture
from gui.styles import COLORS, DARK_STYLESHEET


class OverlayWindow(QWidget):
    """Compact overlay shown during agent execution.

    Displays current step, reasoning, last action, token count,
    and pause/stop controls. Capture-hidden and always-on-top.
    """

    closed = Signal()  # emitted when user closes the overlay

    OVERLAY_WIDTH = 400
    OVERLAY_HEIGHT = 260

    def __init__(self, bus: AgentEventBus, bridge: EventBridge, parent=None):
        super().__init__(parent, Qt.WindowType.Window)
        self._bus = bus
        self._bridge = bridge
        self._paused = False
        self._capture_hide_pending = True

        # Token accumulators
        self._total_prompt = 0
        self._total_completion = 0
        self._total_tokens = 0

        # Streaming throttle
        self._last_reasoning_update = 0.0

        # Window flags: frameless, always-on-top, tool window (no taskbar)
        self.setWindowFlags(
            Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_NativeWindow)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self.setFixedSize(self.OVERLAY_WIDTH, self.OVERLAY_HEIGHT)
        self.setStyleSheet(DARK_STYLESHEET)

        self._build_ui()
        self._connect_signals()
        self._position_top_right()

    def showEvent(self, event):
        super().showEvent(event)
        if self._capture_hide_pending:
            hide_from_capture(int(self.winId()))
            self._capture_hide_pending = False

    def _position_top_right(self):
        """Place the overlay at the top-right of the primary screen."""
        from PySide6.QtWidgets import QApplication
        screen = QApplication.primaryScreen()
        if screen:
            geom = screen.availableGeometry()
            x = geom.right() - self.OVERLAY_WIDTH - 12
            y = geom.top() + 12
            self.move(x, y)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(6)

        # --- Row 1: Step + controls ---
        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        self._step_label = QLabel("Starting...")
        self._step_label.setFont(QFont("Consolas", 11, QFont.Weight.Bold))
        self._step_label.setStyleSheet(f"color: {COLORS['accent']};")
        top_row.addWidget(self._step_label)

        top_row.addStretch()

        self._pause_btn = QPushButton("Pause")
        self._pause_btn.setFixedSize(60, 26)
        self._pause_btn.setFont(QFont("Segoe UI", 8))
        self._pause_btn.clicked.connect(self._toggle_pause)
        top_row.addWidget(self._pause_btn)

        self._stop_btn = QPushButton("Stop")
        self._stop_btn.setObjectName("stopButton")
        self._stop_btn.setFixedSize(50, 26)
        self._stop_btn.setFont(QFont("Segoe UI", 8))
        self._stop_btn.clicked.connect(self._on_stop)
        top_row.addWidget(self._stop_btn)

        layout.addLayout(top_row)

        # --- Row 2: Reasoning (multi-line, truncated) ---
        self._reasoning_label = QLabel("Waiting for model response...")
        self._reasoning_label.setFont(QFont("Consolas", 9))
        self._reasoning_label.setStyleSheet(f"color: {COLORS['think']};")
        self._reasoning_label.setWordWrap(True)
        self._reasoning_label.setMinimumHeight(80)
        self._reasoning_label.setMaximumHeight(120)
        self._reasoning_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self._reasoning_label, stretch=1)

        # --- Row 3: Last action ---
        self._action_label = QLabel("")
        self._action_label.setFont(QFont("Consolas", 8))
        self._action_label.setStyleSheet(f"color: {COLORS['fg_dim']};")
        self._action_label.setWordWrap(True)
        layout.addWidget(self._action_label)

        # --- Row 4: Token counter ---
        self._token_label = QLabel("Tokens: 0")
        self._token_label.setFont(QFont("Consolas", 8))
        self._token_label.setStyleSheet(f"color: {COLORS['fg_dim']};")
        layout.addWidget(self._token_label)

    def _connect_signals(self):
        self._bridge.step_started.connect(self._on_step_started)
        self._bridge.llm_call_started.connect(self._on_llm_call_started)
        self._bridge.llm_reasoning_delta.connect(self._on_reasoning_delta)
        self._bridge.llm_finished.connect(self._on_llm_finished)
        self._bridge.action_executed.connect(self._on_action_executed)
        self._bridge.agent_finished.connect(self._on_agent_finished)
        self._bridge.agent_error.connect(self._on_agent_error)

    # --- Event handlers ---

    def _on_step_started(self, step: int):
        self._step_label.setText(f"Step {step}")
        self._step_label.setStyleSheet(f"color: {COLORS['accent']};")

    def _on_llm_call_started(self, step: int):
        self._reasoning_label.setText("Thinking...")
        self._reasoning_label.setStyleSheet(f"color: {COLORS['fg_dim']};")
        self._last_reasoning_update = 0.0

    def _on_reasoning_delta(self, step: int, delta: str, accumulated: str):
        if not accumulated:
            # Reset signal (retry)
            self._reasoning_label.setText("Thinking...")
            self._reasoning_label.setStyleSheet(f"color: {COLORS['fg_dim']};")
            self._last_reasoning_update = 0.0
            return

        now = time.monotonic()
        if now - self._last_reasoning_update < 0.05:
            return  # throttle: next update will catch up via accumulated
        self._last_reasoning_update = now

        display = accumulated[:250] + "..." if len(accumulated) > 250 else accumulated
        self._reasoning_label.setText(display)
        self._reasoning_label.setStyleSheet(f"color: {COLORS['think']};")

    def _on_llm_finished(self, step: int, data: dict):
        think = data.get("think")
        if think:
            # Truncate to ~250 chars for the compact view
            display = think[:250] + "..." if len(think) > 250 else think
            self._reasoning_label.setText(display)
            self._reasoning_label.setStyleSheet(f"color: {COLORS['think']};")
        else:
            self._reasoning_label.setText("(no reasoning)")
            self._reasoning_label.setStyleSheet(f"color: {COLORS['fg_dim']};")

        # Token tracking
        usage = data.get("usage")
        if usage:
            prompt = usage.get("prompt_tokens", usage.get("input_tokens", usage.get("prompt", 0)))
            completion = usage.get("completion_tokens", usage.get("output_tokens", usage.get("completion", 0)))
            total = usage.get("total_tokens", usage.get("total", prompt + completion))
            self._total_prompt += prompt
            self._total_completion += completion
            self._total_tokens += total
            self._token_label.setText(
                f"Step: {prompt}+{completion} | Total: {self._total_tokens:,}"
            )

    def _on_action_executed(self, step: int, result: str, action: dict):
        display = result[:80] + "..." if len(result) > 80 else result
        if result.startswith("ERROR"):
            self._action_label.setStyleSheet(f"color: {COLORS['error']};")
        else:
            self._action_label.setStyleSheet(f"color: {COLORS['fg']};")
        self._action_label.setText(f"Last: {display}")

    def _on_agent_finished(self, status: str, reason: str):
        if status == "done":
            self._step_label.setText("Done")
            self._step_label.setStyleSheet(f"color: {COLORS['success']};")
            if reason:
                self._reasoning_label.setText(reason)
                self._reasoning_label.setStyleSheet(f"color: {COLORS['success']};")
        elif status == "stopped_by_user":
            self._step_label.setText("Stopped")
            self._step_label.setStyleSheet(f"color: {COLORS['error']};")
        else:
            self._step_label.setText(f"Finished: {status}")
            self._step_label.setStyleSheet(f"color: {COLORS['step']};")
        self._pause_btn.setEnabled(False)
        self._stop_btn.setEnabled(False)

    def _on_agent_error(self, message: str):
        self._step_label.setText("Error")
        self._step_label.setStyleSheet(f"color: {COLORS['error']};")
        self._reasoning_label.setText(message[:250])
        self._reasoning_label.setStyleSheet(f"color: {COLORS['error']};")
        self._pause_btn.setEnabled(False)
        self._stop_btn.setEnabled(False)

    # --- Controls ---

    def _toggle_pause(self):
        if self._paused:
            self._bus.request_resume()
            self._pause_btn.setText("Pause")
            self._step_label.setStyleSheet(f"color: {COLORS['accent']};")
        else:
            self._bus.request_pause()
            self._pause_btn.setText("Resume")
            self._step_label.setStyleSheet(f"color: {COLORS['warning']};")
        self._paused = not self._paused

    def _on_stop(self):
        self._bus.request_stop()
        self._stop_btn.setEnabled(False)
        self._pause_btn.setEnabled(False)
        self.closed.emit()

    def closeEvent(self, event):
        self._bus.request_stop()
        self.closed.emit()
        super().closeEvent(event)

    # --- Allow dragging the frameless window ---

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if hasattr(self, '_drag_pos') and event.buttons() & Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self._drag_pos)
            event.accept()
