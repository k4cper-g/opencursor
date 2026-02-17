"""Application orchestrator — manages ConfigWindow ↔ OverlayWindow transitions."""

from __future__ import annotations

import threading
from typing import Callable

from PySide6.QtCore import QObject

from events import AgentEvent, AgentEventBus, EventType
from gui.bridge import EventBridge
from gui.config_window import ConfigWindow
from gui.overlay_window import OverlayWindow


class Application(QObject):
    """Manages the two-mode UI lifecycle:

    1. Config window shown → user clicks Run
    2. Config window hides → overlay appears → agent runs
    3. Agent finishes → overlay hides → config window reappears with debug data
    """

    def __init__(self, run_fn: Callable, config: dict, goal_hint: str | None = None):
        super().__init__()
        self._run_fn = run_fn
        self._config = config

        # Initial bus/bridge for the config window (used for reviewing past runs)
        self._bus = AgentEventBus()
        self._bridge = EventBridge(self._bus, parent=self)

        # Config window
        self._config_window = ConfigWindow(
            self._bus, self._bridge, config, goal_hint=goal_hint,
        )
        self._config_window.run_requested.connect(self._on_run_requested)

        self._overlay: OverlayWindow | None = None
        self._agent_thread: threading.Thread | None = None

    def show(self):
        """Show the config window to start."""
        self._config_window.show()

    def _on_run_requested(self, goal: str, config_overrides: dict):
        """User clicked Run in the config window."""
        # Merge config overrides
        run_config = {**self._config, **config_overrides}

        # Fresh bus and bridge for this run
        self._bus = AgentEventBus()
        self._bridge = EventBridge(self._bus, parent=self)

        # Connect finish/error signals to transition back
        self._bridge.agent_finished.connect(self._on_agent_done)
        self._bridge.agent_error.connect(self._on_agent_error)

        # Prepare config window for the new run (re-wires debug panel + settings bus)
        self._config_window.prepare_for_new_run(self._bus, self._bridge)

        # Hide config, show overlay
        self._config_window.hide()

        self._overlay = OverlayWindow(self._bus, self._bridge)
        self._overlay.closed.connect(self._on_overlay_closed)
        self._overlay.show()

        # Start agent thread
        self._start_agent(goal, run_config)

    def _start_agent(self, goal: str, config: dict):
        """Launch the agent in a background thread."""
        def wrapper():
            try:
                self._run_fn(goal, config, event_bus=self._bus)
            except SystemExit as e:
                self._bus.emit(AgentEvent(
                    type=EventType.AGENT_ERROR,
                    message=str(e),
                ))
            except Exception as e:
                self._bus.emit(AgentEvent(
                    type=EventType.AGENT_ERROR,
                    message=f"{type(e).__name__}: {e}",
                ))

        self._agent_thread = threading.Thread(target=wrapper, daemon=True)
        self._agent_thread.start()

    def _on_agent_done(self, status: str, reason: str):
        """Agent finished — transition overlay → config window."""
        # Small delay so user can see the "Done" status in overlay
        from PySide6.QtCore import QTimer
        QTimer.singleShot(1500, self._transition_to_config)

    def _on_agent_error(self, message: str):
        """Agent errored — transition back after brief display."""
        from PySide6.QtCore import QTimer
        QTimer.singleShot(2000, self._transition_to_config)

    def _on_overlay_closed(self):
        """User manually closed the overlay."""
        self._bus.request_stop()
        self._transition_to_config()

    def _transition_to_config(self):
        """Hide overlay, show config window with debug data."""
        if self._overlay is None:
            return  # already transitioned

        self._overlay.hide()
        self._overlay.deleteLater()
        self._overlay = None

        self._config_window.load_current_run_debug()
        self._config_window.show()
        self._config_window.activateWindow()
