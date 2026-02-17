"""Config window — main menu for setup, run history, and debug review."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from events import AgentEventBus
from gui.bridge import EventBridge
from gui.panels.debug_panel import DebugPanel
from gui.panels.history_panel import HistoryPanel
from gui.panels.settings_panel import SettingsPanel
from gui.styles import COLORS, DARK_STYLESHEET


class ConfigWindow(QMainWindow):
    """Main config/review window. Shown before and after agent runs."""

    run_requested = Signal(str, dict)  # goal, config overrides

    def __init__(self, bus: AgentEventBus, bridge: EventBridge, config: dict,
                 goal_hint: str | None = None, parent=None):
        super().__init__(parent)
        self._bus = bus
        self._bridge = bridge
        self._config = config

        self.setWindowTitle("OpenCursor")
        self.setMinimumSize(750, 500)
        self.resize(850, 600)
        self.setStyleSheet(DARK_STYLESHEET)

        self._build_ui(config, goal_hint)

    def _build_ui(self, config: dict, goal_hint: str | None):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        # --- Title ---
        title = QLabel("OpenCursor")
        title.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        title.setStyleSheet(f"color: {COLORS['accent']};")
        layout.addWidget(title)

        # --- Goal + Run row ---
        goal_row = QHBoxLayout()
        goal_row.setSpacing(8)

        goal_label = QLabel("Goal:")
        goal_label.setFont(QFont("Segoe UI", 10))
        goal_row.addWidget(goal_label)

        self._goal_input = QLineEdit()
        self._goal_input.setPlaceholderText('e.g. "open notepad and type hello world"')
        self._goal_input.setFont(QFont("Consolas", 10))
        self._goal_input.setMinimumHeight(32)
        if goal_hint:
            self._goal_input.setText(goal_hint)
        # Enter key triggers run
        self._goal_input.returnPressed.connect(self._on_run_clicked)
        goal_row.addWidget(self._goal_input, stretch=1)

        self._run_btn = QPushButton("Run")
        self._run_btn.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        self._run_btn.setFixedSize(80, 32)
        self._run_btn.setStyleSheet(
            f"background-color: {COLORS['accent']}; color: #1e1e1e; "
            f"border: none; border-radius: 4px; font-weight: bold;"
        )
        self._run_btn.clicked.connect(self._on_run_clicked)
        goal_row.addWidget(self._run_btn)

        layout.addLayout(goal_row)

        # --- Tabs ---
        self._tabs = QTabWidget()

        # Settings tab
        self._settings = SettingsPanel(self._bus, self._bridge, config)
        self._tabs.addTab(self._settings, "Settings")

        # Run History tab
        self._history = HistoryPanel()
        self._history.session_selected.connect(self._on_session_selected)
        self._tabs.addTab(self._history, "Run History")

        # Debug Viewer tab
        self._debug = DebugPanel(bridge=self._bridge)
        self._tabs.addTab(self._debug, "Debug Viewer")

        layout.addWidget(self._tabs, stretch=1)

    def _on_run_clicked(self):
        goal = self._goal_input.text().strip()
        if not goal:
            self._goal_input.setFocus()
            self._goal_input.setStyleSheet(
                f"border: 1px solid {COLORS['error']}; "
                f"background-color: {COLORS['bg_secondary']}; "
                f"color: {COLORS['fg']};"
            )
            return

        # Reset goal input styling
        self._goal_input.setStyleSheet("")

        config_overrides = self._settings.get_config_overrides()
        self.run_requested.emit(goal, config_overrides)

    def _on_session_selected(self, path: str):
        """Load a past session into the debug viewer and switch to that tab."""
        self._debug.load_session(path)
        self._tabs.setCurrentWidget(self._debug)

    def load_current_run_debug(self):
        """Switch to debug viewer tab to show the just-completed run."""
        self._tabs.setCurrentWidget(self._debug)

    def prepare_for_new_run(self, bus: AgentEventBus, bridge: EventBridge):
        """Re-wire panels to a fresh bus/bridge for a new run."""
        self._bus = bus
        self._bridge = bridge

        # Point settings panel at the new bus for live settings
        self._settings.set_bus(bus)

        # Recreate debug panel with new bridge so it picks up live events
        old_debug = self._debug
        self._debug = DebugPanel(bridge=bridge)
        idx = self._tabs.indexOf(old_debug)
        self._tabs.removeTab(idx)
        self._tabs.insertTab(idx, self._debug, "Debug Viewer")
        old_debug.deleteLater()

        # Refresh history (previous run may have written debug data)
        self._history.refresh()
