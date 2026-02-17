"""Step timeline with thumbnail cards."""

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QFont, QPixmap
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from gui.bridge import EventBridge
from gui.styles import COLORS
from gui.utils import pil_to_qpixmap

THUMB_SIZE = QSize(80, 50)


class StepCard(QFrame):
    """One card in the timeline representing a single agent step."""

    clicked = Signal(int)

    def __init__(self, step: int, parent=None):
        super().__init__(parent)
        self.step = step
        self.setObjectName("stepCard")
        self.setFixedHeight(66)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(8)

        # Thumbnail
        self._thumbnail = QLabel()
        self._thumbnail.setFixedSize(THUMB_SIZE)
        self._thumbnail.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._thumbnail.setStyleSheet(
            f"background-color: {COLORS['bg_tertiary']}; border-radius: 2px;"
        )
        layout.addWidget(self._thumbnail)

        # Info column
        info = QVBoxLayout()
        info.setSpacing(2)

        self._step_label = QLabel(f"Step {step}")
        self._step_label.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        self._step_label.setStyleSheet(f"color: {COLORS['step']};")
        info.addWidget(self._step_label)

        self._action_label = QLabel("waiting...")
        self._action_label.setFont(QFont("Consolas", 8))
        self._action_label.setStyleSheet(f"color: {COLORS['fg_dim']};")
        self._action_label.setWordWrap(True)
        info.addWidget(self._action_label)

        self._status_icon = QLabel()
        self._status_icon.setFont(QFont("Consolas", 8))
        info.addWidget(self._status_icon)

        info.addStretch()
        layout.addLayout(info, stretch=1)

    def set_screenshot(self, pil_image):
        """Set thumbnail from a PIL Image."""
        pixmap = pil_to_qpixmap(pil_image, max_size=THUMB_SIZE)
        self._thumbnail.setPixmap(pixmap)

    def set_result(self, result: str, is_error: bool):
        # Truncate long results
        display = result[:60] + "..." if len(result) > 60 else result
        self._action_label.setText(display)
        if is_error:
            self._action_label.setStyleSheet(f"color: {COLORS['error']};")
            self._status_icon.setText("FAIL")
            self._status_icon.setStyleSheet(f"color: {COLORS['error']};")
        else:
            self._action_label.setStyleSheet(f"color: {COLORS['fg']};")
            self._status_icon.setText("OK")
            self._status_icon.setStyleSheet(f"color: {COLORS['success']};")

    def set_selected(self, selected: bool):
        self.setObjectName("stepCardSelected" if selected else "stepCard")
        self.style().unpolish(self)
        self.style().polish(self)

    def mousePressEvent(self, event):
        self.clicked.emit(self.step)
        super().mousePressEvent(event)


class TimelinePanel(QWidget):
    """Scrollable vertical list of StepCards."""

    step_selected = Signal(int)

    def __init__(self, bridge: EventBridge, parent=None):
        super().__init__(parent)
        self._cards: dict[int, StepCard] = {}
        self._selected_step: int | None = None

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        header = QLabel("  Timeline")
        header.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        header.setFixedHeight(24)
        header.setStyleSheet(f"color: {COLORS['fg_dim']};")
        main_layout.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._container = QWidget()
        self._container_layout = QVBoxLayout(self._container)
        self._container_layout.setContentsMargins(4, 4, 4, 4)
        self._container_layout.setSpacing(4)
        self._container_layout.addStretch()

        scroll.setWidget(self._container)
        main_layout.addWidget(scroll)

        self._scroll_area = scroll

        bridge.step_started.connect(self._on_step_started)
        bridge.screenshot_taken.connect(self._on_screenshot)
        bridge.action_executed.connect(self._on_action_executed)

    def _on_step_started(self, step: int):
        card = StepCard(step)
        card.clicked.connect(self._on_card_clicked)
        self._cards[step] = card
        # Insert before the stretch
        self._container_layout.insertWidget(self._container_layout.count() - 1, card)
        # Auto-scroll to bottom
        self._scroll_area.verticalScrollBar().setValue(
            self._scroll_area.verticalScrollBar().maximum()
        )

    def _on_screenshot(self, step: int, pil_image):
        if step in self._cards and pil_image is not None:
            self._cards[step].set_screenshot(pil_image)

    def _on_action_executed(self, step: int, result: str, action: dict):
        if step in self._cards:
            self._cards[step].set_result(result, result.startswith("ERROR"))

    def _on_card_clicked(self, step: int):
        # Update selection visuals
        if self._selected_step is not None and self._selected_step in self._cards:
            self._cards[self._selected_step].set_selected(False)
        self._selected_step = step
        self._cards[step].set_selected(True)
        self.step_selected.emit(step)
