"""Pause/Resume/Stop controls and token usage tracking."""

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from events import AgentEventBus
from gui.bridge import EventBridge
from gui.styles import COLORS


class ControlsPanel(QWidget):
    """Top bar with pause/resume, stop, status, and token counter."""

    def __init__(self, bus: AgentEventBus, bridge: EventBridge, parent=None):
        super().__init__(parent)
        self._bus = bus
        self._paused = False
        self.setFixedHeight(44)

        # Token accumulators
        self._total_prompt = 0
        self._total_completion = 0
        self._total_tokens = 0
        self._step_count = 0

        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 4, 8, 4)

        # Pause/Resume
        self._pause_btn = QPushButton("Pause")
        self._pause_btn.setFixedWidth(80)
        self._pause_btn.clicked.connect(self._toggle_pause)
        layout.addWidget(self._pause_btn)

        # Stop
        self._stop_btn = QPushButton("Stop")
        self._stop_btn.setObjectName("stopButton")
        self._stop_btn.setFixedWidth(80)
        self._stop_btn.clicked.connect(self._on_stop)
        layout.addWidget(self._stop_btn)

        layout.addSpacing(16)

        # Status
        self._status = QLabel("Idle")
        self._status.setFont(QFont("Consolas", 10))
        self._status.setStyleSheet(f"color: {COLORS['accent']};")
        layout.addWidget(self._status)

        layout.addStretch()

        # Token counter
        self._token_label = QLabel("Tokens: 0")
        self._token_label.setFont(QFont("Consolas", 9))
        self._token_label.setStyleSheet(f"color: {COLORS['fg_dim']};")
        layout.addWidget(self._token_label)

        # Connect signals
        bridge.agent_started.connect(self._on_agent_started)
        bridge.step_started.connect(self._on_step_started)
        bridge.llm_finished.connect(self._on_llm_finished)
        bridge.agent_finished.connect(self._on_agent_finished)
        bridge.agent_error.connect(self._on_agent_error)

    def _toggle_pause(self):
        if self._paused:
            self._bus.request_resume()
            self._pause_btn.setText("Pause")
            self._status.setText("Running")
            self._status.setStyleSheet(f"color: {COLORS['accent']};")
        else:
            self._bus.request_pause()
            self._pause_btn.setText("Resume")
            self._status.setText("Paused")
            self._status.setStyleSheet(f"color: {COLORS['warning']};")
        self._paused = not self._paused

    def _on_stop(self):
        self._bus.request_stop()
        self._stop_btn.setEnabled(False)
        self._pause_btn.setEnabled(False)
        self._status.setText("Stopping...")
        self._status.setStyleSheet(f"color: {COLORS['error']};")

    def _on_agent_started(self, data: dict):
        self._status.setText("Running")
        self._status.setStyleSheet(f"color: {COLORS['accent']};")
        self._pause_btn.setEnabled(True)
        self._stop_btn.setEnabled(True)

    def _on_step_started(self, step: int):
        self._step_count = step
        if not self._paused:
            self._status.setText(f"Step {step}")
            self._status.setStyleSheet(f"color: {COLORS['accent']};")

    def _on_llm_finished(self, step: int, data: dict):
        usage = data.get("usage")
        if not usage:
            return
        prompt = usage.get("prompt_tokens", usage.get("input_tokens", usage.get("prompt", 0)))
        completion = usage.get("completion_tokens", usage.get("output_tokens", usage.get("completion", 0)))
        total = usage.get("total_tokens", usage.get("total", prompt + completion))
        self._total_prompt += prompt
        self._total_completion += completion
        self._total_tokens += total
        self._token_label.setText(
            f"Step: {prompt}+{completion} | Total: {self._total_tokens:,}"
        )

    def _on_agent_finished(self, status: str, reason: str):
        display = reason if reason else status
        self._status.setText(f"Finished: {display}")
        if status == "done":
            self._status.setStyleSheet(f"color: {COLORS['success']};")
        else:
            self._status.setStyleSheet(f"color: {COLORS['step']};")
        self._pause_btn.setEnabled(False)
        self._stop_btn.setEnabled(False)

    def _on_agent_error(self, message: str):
        self._status.setText(f"Error: {message[:60]}")
        self._status.setStyleSheet(f"color: {COLORS['error']};")
        self._pause_btn.setEnabled(False)
        self._stop_btn.setEnabled(False)
