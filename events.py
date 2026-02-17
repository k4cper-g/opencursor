"""Structured event system for agent-to-consumer communication."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable


class EventType(Enum):
    # Lifecycle
    AGENT_STARTED = auto()
    AGENT_FINISHED = auto()
    AGENT_ERROR = auto()

    # Step lifecycle
    STEP_STARTED = auto()
    STEP_SCREENSHOT_TAKEN = auto()
    STEP_LLM_CALL_STARTED = auto()
    STEP_LLM_REASONING_DELTA = auto()
    STEP_LLM_CALL_FINISHED = auto()
    STEP_ACTION_EXECUTED = auto()
    STEP_COMPLETED = auto()

    # Data
    LOG_MESSAGE = auto()
    STATUS_CHANGE = auto()


@dataclass
class AgentEvent:
    type: EventType
    data: dict = field(default_factory=dict)
    step: int | None = None
    message: str | None = None


class AgentEventBus:
    """Thread-safe pub/sub event bus with pause/resume/stop controls.

    The agent thread publishes events; consumer threads subscribe.
    Pause uses threading.Event for zero-CPU blocking.
    """

    def __init__(self):
        self._subscribers: dict[EventType | None, list[Callable]] = {}
        self._lock = threading.Lock()

        # Pause/resume: set = running, clear = paused
        self._pause_event = threading.Event()
        self._pause_event.set()

        self._stop_requested = threading.Event()

        # Live-adjustable settings
        self._live_settings: dict[str, Any] = {}
        self._settings_lock = threading.Lock()

    def subscribe(self, event_type: EventType | None, callback: Callable[[AgentEvent], None]):
        """Subscribe to a specific event type, or None for all events."""
        with self._lock:
            self._subscribers.setdefault(event_type, []).append(callback)

    def emit(self, event: AgentEvent):
        """Publish an event to all matching subscribers. Thread-safe."""
        with self._lock:
            callbacks = list(self._subscribers.get(event.type, []))
            callbacks += list(self._subscribers.get(None, []))
        for cb in callbacks:
            cb(event)

    # --- Pause / Resume / Stop ---

    def request_pause(self):
        self._pause_event.clear()

    def request_resume(self):
        self._pause_event.set()

    def request_stop(self):
        self._stop_requested.set()
        self._pause_event.set()  # unblock if paused

    def check_pause(self):
        """Called by agent loop between steps. Blocks if paused."""
        self._pause_event.wait()

    @property
    def stop_requested(self) -> bool:
        return self._stop_requested.is_set()

    # --- Live settings ---

    def set_live_setting(self, key: str, value: Any):
        with self._settings_lock:
            self._live_settings[key] = value

    def get_live_setting(self, key: str, default: Any = None) -> Any:
        with self._settings_lock:
            return self._live_settings.get(key, default)
