"""Debug viewer: side-by-side screenshot + reasoning + action details."""

from __future__ import annotations

import json
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from gui.styles import COLORS
from gui.utils import pil_to_qpixmap

# Import is optional — bridge may be None when viewing past sessions
try:
    from gui.bridge import EventBridge
except ImportError:
    EventBridge = None


class DebugPanel(QWidget):
    """Per-step debug viewer with screenshot, reasoning, and action details."""

    def __init__(self, bridge: EventBridge | None = None, parent=None):
        super().__init__(parent)
        self._steps_data: dict[int, dict] = {}
        self._current_step: int | None = None
        self._sorted_steps: list[int] = []
        self._current_pil_image: Image.Image | None = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        # Navigation bar
        nav = QHBoxLayout()
        nav.setSpacing(8)

        self._prev_btn = QPushButton("<")
        self._prev_btn.setFixedWidth(32)
        self._prev_btn.clicked.connect(self._go_prev)
        nav.addWidget(self._prev_btn)

        self._step_label = QLabel("No steps yet")
        self._step_label.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
        self._step_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        nav.addWidget(self._step_label, stretch=1)

        self._next_btn = QPushButton(">")
        self._next_btn.setFixedWidth(32)
        self._next_btn.clicked.connect(self._go_next)
        nav.addWidget(self._next_btn)

        layout.addLayout(nav)

        # Main content: horizontal splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: screenshot
        screenshot_container = QWidget()
        screenshot_layout = QVBoxLayout(screenshot_container)
        screenshot_layout.setContentsMargins(0, 0, 0, 0)

        screenshot_header = QLabel("Screenshot")
        screenshot_header.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        screenshot_header.setStyleSheet(f"color: {COLORS['fg_dim']};")
        screenshot_layout.addWidget(screenshot_header)

        self._screenshot_label = QLabel("No screenshot")
        self._screenshot_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._screenshot_label.setMinimumSize(200, 150)
        self._screenshot_label.setCursor(Qt.CursorShape.PointingHandCursor)
        self._screenshot_label.setStyleSheet(
            f"background-color: {COLORS['bg_tertiary']}; border-radius: 4px;"
        )
        self._screenshot_label.mousePressEvent = self._on_screenshot_clicked
        screenshot_layout.addWidget(self._screenshot_label, stretch=1)
        splitter.addWidget(screenshot_container)

        # Right: vertical split of reasoning + action
        right_splitter = QSplitter(Qt.Orientation.Vertical)

        # Reasoning
        reasoning_container = QWidget()
        reasoning_layout = QVBoxLayout(reasoning_container)
        reasoning_layout.setContentsMargins(0, 0, 0, 0)

        reasoning_header = QLabel("Reasoning")
        reasoning_header.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        reasoning_header.setStyleSheet(f"color: {COLORS['think']};")
        reasoning_layout.addWidget(reasoning_header)

        self._reasoning_text = QPlainTextEdit()
        self._reasoning_text.setReadOnly(True)
        self._reasoning_text.setPlaceholderText("Model reasoning will appear here")
        reasoning_layout.addWidget(self._reasoning_text)
        right_splitter.addWidget(reasoning_container)

        # Action details
        action_container = QWidget()
        action_layout = QVBoxLayout(action_container)
        action_layout.setContentsMargins(0, 0, 0, 0)

        action_header = QLabel("Parsed Action")
        action_header.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        action_header.setStyleSheet(f"color: {COLORS['step']};")
        action_layout.addWidget(action_header)

        self._action_text = QPlainTextEdit()
        self._action_text.setReadOnly(True)
        self._action_text.setPlaceholderText("Parsed action details")
        action_layout.addWidget(self._action_text)
        right_splitter.addWidget(action_container)

        right_splitter.setSizes([200, 200])
        splitter.addWidget(right_splitter)
        splitter.setSizes([400, 350])

        layout.addWidget(splitter, stretch=1)

        # Streaming throttle
        self._last_reasoning_update = 0.0

        # Connect signals (bridge may be None for offline viewing)
        if bridge is not None:
            bridge.screenshot_taken.connect(self._on_screenshot)
            bridge.llm_call_started.connect(self._on_llm_call_started)
            bridge.llm_reasoning_delta.connect(self._on_reasoning_delta)
            bridge.llm_finished.connect(self._on_llm_finished)
            bridge.action_executed.connect(self._on_action_executed)

    def navigate_to_step(self, step: int):
        """Public: navigate to a specific step (used by timeline click)."""
        if step in self._steps_data:
            self._show_step(step)

    def _on_screenshot(self, step: int, pil_image):
        self._ensure_step(step)
        self._steps_data[step]["screenshot"] = pil_image
        if self._current_step == step:
            self._display_screenshot(pil_image)
        # Auto-navigate to latest step
        self._show_step(step)

    def _on_llm_call_started(self, step: int):
        self._ensure_step(step)
        self._last_reasoning_update = 0.0
        if self._current_step == step:
            self._reasoning_text.setPlainText("Thinking...")

    def _on_reasoning_delta(self, step: int, delta: str, accumulated: str):
        if self._current_step != step:
            return
        if not accumulated:
            self._reasoning_text.setPlainText("Thinking...")
            self._last_reasoning_update = 0.0
            return

        import time
        now = time.monotonic()
        if now - self._last_reasoning_update < 0.05:
            return
        self._last_reasoning_update = now

        self._reasoning_text.setPlainText(accumulated)
        scrollbar = self._reasoning_text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def _on_llm_finished(self, step: int, data: dict):
        self._ensure_step(step)
        self._steps_data[step]["think"] = data.get("think")
        self._steps_data[step]["parsed"] = data.get("parsed")
        self._steps_data[step]["raw"] = data.get("raw")
        self._steps_data[step]["usage"] = data.get("usage")
        # Auto-navigate to latest step
        self._show_step(step)

    def _on_action_executed(self, step: int, result: str, action: dict):
        self._ensure_step(step)
        self._steps_data[step].setdefault("actions", []).append({
            "action": action,
            "result": result,
        })
        if self._current_step == step:
            self._display_actions(step)

    def _ensure_step(self, step: int):
        if step not in self._steps_data:
            self._steps_data[step] = {}
            self._sorted_steps = sorted(self._steps_data.keys())

    def _show_step(self, step: int):
        self._current_step = step
        data = self._steps_data.get(step, {})

        self._step_label.setText(f"Step {step}")

        # Reasoning
        think = data.get("think")
        self._reasoning_text.setPlainText(think or "(no reasoning)")

        # Actions
        self._display_actions(step)

        # Screenshot
        screenshot = data.get("screenshot")
        if screenshot:
            self._display_screenshot(screenshot)
        else:
            self._screenshot_label.setText("No screenshot")
            self._screenshot_label.setPixmap(QPixmap())

        # Update nav button state
        self._update_nav_buttons()

    def _display_actions(self, step: int):
        data = self._steps_data.get(step, {})
        parts = []

        # Parsed response from LLM
        parsed = data.get("parsed")
        if parsed:
            parts.append("=== Parsed Response ===")
            parts.append(json.dumps(parsed, indent=2))

        # Execution results
        actions = data.get("actions", [])
        if actions:
            parts.append("\n=== Execution Results ===")
            for i, entry in enumerate(actions, 1):
                parts.append(f"[{i}] {entry['result']}")

        # Usage
        usage = data.get("usage")
        if usage:
            parts.append(f"\n=== Token Usage ===")
            parts.append(json.dumps(usage, indent=2))

        self._action_text.setPlainText("\n".join(parts) if parts else "(no data)")

    def _display_screenshot(self, pil_image):
        self._current_pil_image = pil_image
        available = self._screenshot_label.size()
        pixmap = pil_to_qpixmap(pil_image, max_size=QSize(available.width() - 8, available.height() - 8))
        self._screenshot_label.setPixmap(pixmap)

    def _on_screenshot_clicked(self, event):
        if self._current_pil_image is None:
            return

        screen = self.screen().availableSize()
        max_w = int(screen.width() * 0.8)
        max_h = int(screen.height() * 0.8)
        pixmap = pil_to_qpixmap(self._current_pil_image, max_size=QSize(max_w, max_h))

        dialog = QDialog(self)
        dialog.setWindowTitle(f"Screenshot — Step {self._current_step}")
        dialog.resize(pixmap.width() + 20, pixmap.height() + 20)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        label = QLabel()
        label.setPixmap(pixmap)
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        scroll.setWidget(label)
        layout.addWidget(scroll)

        dialog.exec()

    def _update_nav_buttons(self):
        if not self._sorted_steps or self._current_step is None:
            self._prev_btn.setEnabled(False)
            self._next_btn.setEnabled(False)
            return
        idx = self._sorted_steps.index(self._current_step) if self._current_step in self._sorted_steps else 0
        self._prev_btn.setEnabled(idx > 0)
        self._next_btn.setEnabled(idx < len(self._sorted_steps) - 1)

    def _go_prev(self):
        if self._current_step is None or self._current_step not in self._sorted_steps:
            return
        idx = self._sorted_steps.index(self._current_step)
        if idx > 0:
            self._show_step(self._sorted_steps[idx - 1])

    def _go_next(self):
        if self._current_step is None or self._current_step not in self._sorted_steps:
            return
        idx = self._sorted_steps.index(self._current_step)
        if idx < len(self._sorted_steps) - 1:
            self._show_step(self._sorted_steps[idx + 1])

    # --- Session loading (for past runs and post-run review) ---

    def clear(self):
        """Reset all step data for a fresh run."""
        self._steps_data.clear()
        self._sorted_steps.clear()
        self._current_step = None
        self._step_label.setText("No steps yet")
        self._reasoning_text.clear()
        self._action_text.clear()
        self._screenshot_label.setText("No screenshot")
        self._screenshot_label.setPixmap(QPixmap())
        self._current_pil_image = None
        self._update_nav_buttons()

    def load_session(self, session_dir: str | Path):
        """Load a past debug session from disk into the viewer."""
        self.clear()
        session_path = Path(session_dir)
        summary_path = session_path / "summary.json"

        if not summary_path.exists():
            self._step_label.setText("No summary.json found")
            return

        try:
            summary = json.loads(summary_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            self._step_label.setText(f"Error: {e}")
            return

        for entry in summary.get("steps", []):
            step = entry.get("step", 0)
            self._ensure_step(step)
            self._steps_data[step]["think"] = entry.get("think")
            self._steps_data[step]["parsed"] = entry.get("parsed")
            self._steps_data[step]["usage"] = entry.get("usage")

            # Load execution results
            results = entry.get("results", [])
            parsed = entry.get("parsed", {})
            if parsed.get("type") == "sequence":
                for i, (act, res) in enumerate(zip(parsed.get("steps", []), results)):
                    self._steps_data[step].setdefault("actions", []).append({
                        "action": act, "result": res,
                    })
            elif results:
                action = parsed.get("action", {})
                for res in results:
                    self._steps_data[step].setdefault("actions", []).append({
                        "action": action, "result": res,
                    })

            # Load screenshot if it exists
            screenshot_path = session_path / f"step_{step:03d}.png"
            if screenshot_path.exists():
                try:
                    self._steps_data[step]["screenshot"] = Image.open(str(screenshot_path))
                except Exception:
                    pass

        self._sorted_steps = sorted(self._steps_data.keys())
        if self._sorted_steps:
            self._show_step(self._sorted_steps[0])
