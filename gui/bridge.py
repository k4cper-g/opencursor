"""Bridge between AgentEventBus (threading) and Qt signals.

The agent thread emits events on the bus; this bridge re-emits them as
Qt signals which are automatically queued to the main thread via
AutoConnection (since emitter and receiver live on different threads).
"""

from PySide6.QtCore import QObject, Signal

from events import AgentEventBus, AgentEvent, EventType


class EventBridge(QObject):
    """Subscribes to AgentEventBus and re-emits as Qt signals."""

    # Generic signal for any event
    event_received = Signal(object)

    # Typed convenience signals
    agent_started = Signal(dict)               # config data
    agent_finished = Signal(str, str)           # status, reason
    agent_error = Signal(str)                  # error message
    step_started = Signal(int)                 # step number
    screenshot_taken = Signal(int, object)     # step, PIL.Image
    llm_call_started = Signal(int)             # step
    llm_reasoning_delta = Signal(int, str, str) # step, delta, accumulated
    llm_finished = Signal(int, dict)           # step, {raw, parsed, think, usage}
    action_executed = Signal(int, str, dict)   # step, result string, action dict
    step_completed = Signal(int)               # step
    log_message = Signal(str)                  # text
    status_changed = Signal(str)               # status text

    def __init__(self, bus: AgentEventBus, parent=None):
        super().__init__(parent)
        self._bus = bus
        bus.subscribe(None, self._on_event)

    def _on_event(self, event: AgentEvent):
        """Called from the agent thread. Qt auto-queues to main thread."""
        self.event_received.emit(event)

        match event.type:
            case EventType.AGENT_STARTED:
                self.agent_started.emit(event.data)
            case EventType.AGENT_FINISHED:
                self.agent_finished.emit(
                    event.message or "unknown",
                    event.data.get("reason", ""),
                )
            case EventType.AGENT_ERROR:
                self.agent_error.emit(event.message or "unknown error")
            case EventType.STEP_STARTED:
                self.step_started.emit(event.step or 0)
            case EventType.STEP_SCREENSHOT_TAKEN:
                self.screenshot_taken.emit(event.step or 0, event.data.get("screenshot"))
            case EventType.STEP_LLM_CALL_STARTED:
                self.llm_call_started.emit(event.step or 0)
            case EventType.STEP_LLM_REASONING_DELTA:
                self.llm_reasoning_delta.emit(
                    event.step or 0,
                    event.data.get("delta", ""),
                    event.data.get("accumulated", ""),
                )
            case EventType.STEP_LLM_CALL_FINISHED:
                self.llm_finished.emit(event.step or 0, event.data)
            case EventType.STEP_ACTION_EXECUTED:
                self.action_executed.emit(
                    event.step or 0,
                    event.message or "",
                    event.data.get("action", {}),
                )
            case EventType.STEP_COMPLETED:
                self.step_completed.emit(event.step or 0)
            case EventType.LOG_MESSAGE:
                self.log_message.emit(event.message or "")
            case EventType.STATUS_CHANGE:
                self.status_changed.emit(event.message or "")
