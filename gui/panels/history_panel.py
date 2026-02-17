"""Run history browser — lists past debug sessions from the debug/ folder."""

import json
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from gui.styles import COLORS

DEBUG_ROOT = Path(__file__).resolve().parent.parent.parent / "debug"


class SessionCard(QFrame):
    """A clickable card representing one past debug session."""

    clicked = Signal(str)  # session directory path

    def __init__(self, session_dir: Path, summary: dict, parent=None):
        super().__init__(parent)
        self._path = str(session_dir)
        self.setObjectName("stepCard")
        self.setFixedHeight(60)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(2)

        # Top row: timestamp + result
        top = QHBoxLayout()
        top.setSpacing(8)

        # Parse timestamp from folder name (YYYYMMDD_HHMMSS)
        folder_name = session_dir.name
        try:
            dt = datetime.strptime(folder_name, "%Y%m%d_%H%M%S")
            time_str = dt.strftime("%Y-%m-%d  %H:%M:%S")
        except ValueError:
            time_str = folder_name

        time_label = QLabel(time_str)
        time_label.setFont(QFont("Consolas", 9, QFont.Weight.Bold))
        top.addWidget(time_label)

        top.addStretch()

        # End reason badge
        reason = summary.get("end_reason", "?")
        steps = summary.get("total_steps", "?")
        badge = QLabel(f"{reason}  ({steps} steps)")
        badge.setFont(QFont("Consolas", 8))
        if reason == "done":
            badge.setStyleSheet(f"color: {COLORS['success']};")
        elif reason == "max_steps":
            badge.setStyleSheet(f"color: {COLORS['warning']};")
        else:
            badge.setStyleSheet(f"color: {COLORS['error']};")
        top.addWidget(badge)

        layout.addLayout(top)

        # Bottom row: goal (from session.log first line after header)
        goal_text = self._read_goal(session_dir)
        goal_label = QLabel(goal_text)
        goal_label.setFont(QFont("Consolas", 8))
        goal_label.setStyleSheet(f"color: {COLORS['fg_dim']};")
        goal_label.setWordWrap(True)
        layout.addWidget(goal_label)

    @staticmethod
    def _read_goal(session_dir: Path) -> str:
        """Try to extract the goal from session.log."""
        log = session_dir / "session.log"
        if log.exists():
            try:
                text = log.read_text(encoding="utf-8", errors="ignore")
                for line in text.splitlines():
                    if line.startswith("Goal:"):
                        return line[5:].strip()[:100]
            except Exception:
                pass
        return "(unknown goal)"

    def mousePressEvent(self, event):
        self.clicked.emit(self._path)
        super().mousePressEvent(event)


class HistoryPanel(QWidget):
    """Lists past debug sessions, sorted newest first."""

    session_selected = Signal(str)  # path to session directory

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        # Header with refresh button
        header = QHBoxLayout()
        title = QLabel("Run History")
        title.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        header.addWidget(title)
        header.addStretch()

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setFixedWidth(70)
        refresh_btn.clicked.connect(self.refresh)
        header.addWidget(refresh_btn)

        layout.addLayout(header)

        # Scrollable list
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._container = QWidget()
        self._container_layout = QVBoxLayout(self._container)
        self._container_layout.setContentsMargins(0, 0, 0, 0)
        self._container_layout.setSpacing(4)
        self._container_layout.addStretch()

        scroll.setWidget(self._container)
        layout.addWidget(scroll, stretch=1)

        self._empty_label = QLabel("No debug sessions found.\nRun the agent with debug mode to create sessions.")
        self._empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._empty_label.setStyleSheet(f"color: {COLORS['fg_dim']};")
        self._empty_label.setFont(QFont("Consolas", 9))

        self.refresh()

    def refresh(self):
        """Scan debug/ folder and rebuild the list."""
        # Clear existing cards
        while self._container_layout.count() > 1:  # keep the stretch
            item = self._container_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if not DEBUG_ROOT.exists():
            self._container_layout.insertWidget(0, self._empty_label)
            return

        sessions = []
        for d in DEBUG_ROOT.iterdir():
            if not d.is_dir():
                continue
            summary_path = d / "summary.json"
            if summary_path.exists():
                try:
                    summary = json.loads(summary_path.read_text(encoding="utf-8"))
                    sessions.append((d, summary))
                except (json.JSONDecodeError, OSError):
                    sessions.append((d, {}))
            else:
                # Session exists but no summary (maybe crashed mid-run)
                sessions.append((d, {"end_reason": "incomplete", "total_steps": "?"}))

        # Sort newest first
        sessions.sort(key=lambda x: x[0].name, reverse=True)

        if not sessions:
            self._container_layout.insertWidget(0, self._empty_label)
            return

        # Remove empty label if present
        if self._empty_label.parent() == self._container:
            self._container_layout.removeWidget(self._empty_label)

        for session_dir, summary in sessions:
            card = SessionCard(session_dir, summary)
            card.clicked.connect(self._on_card_clicked)
            # Insert before the stretch
            self._container_layout.insertWidget(self._container_layout.count() - 1, card)

    def _on_card_clicked(self, path: str):
        self.session_selected.emit(path)
