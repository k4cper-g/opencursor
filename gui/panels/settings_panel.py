"""Settings panel — some fields locked during agent run."""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QWidget,
)
from PySide6.QtGui import QFont

from events import AgentEventBus
from gui.bridge import EventBridge
from gui.styles import COLORS


class SettingsPanel(QWidget):
    """Model and runtime settings. Some adjustable mid-run, some only at start."""

    def __init__(self, bus: AgentEventBus, bridge: EventBridge, config: dict, parent=None):
        super().__init__(parent)
        self._bus = bus
        self._config = config

        layout = QFormLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # Section header: startup settings
        startup_header = QLabel("Startup Settings")
        startup_header.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        startup_header.setStyleSheet(f"color: {COLORS['fg_dim']};")
        layout.addRow(startup_header)

        # Model selector
        self._model_combo = QComboBox()
        self._model_combo.addItems(["qwen", "gpt4o", "claude", "gemini", "generic"])
        self._model_combo.setCurrentText(config.get("model", "qwen"))
        layout.addRow("Model:", self._model_combo)

        # Model ID
        self._model_id_edit = QLineEdit(config.get("model_id") or "")
        self._model_id_edit.setPlaceholderText("e.g. gpt-4o-2024-11-20")
        layout.addRow("Model ID:", self._model_id_edit)

        # Base URL
        self._base_url_edit = QLineEdit(config.get("base_url") or "")
        self._base_url_edit.setPlaceholderText("e.g. http://localhost:11434/v1")
        layout.addRow("Base URL:", self._base_url_edit)

        # Section header: live settings
        live_header = QLabel("Live Settings (adjustable during run)")
        live_header.setFont(QFont("Segoe UI", 9, QFont.Weight.Bold))
        live_header.setStyleSheet(f"color: {COLORS['fg_dim']};")
        layout.addRow(live_header)

        # Step delay
        self._delay_spin = QDoubleSpinBox()
        self._delay_spin.setRange(0.0, 10.0)
        self._delay_spin.setSingleStep(0.1)
        self._delay_spin.setDecimals(1)
        self._delay_spin.setSuffix(" s")
        self._delay_spin.setValue(config.get("step_delay", 1.5))
        self._delay_spin.valueChanged.connect(self._on_delay_changed)
        layout.addRow("Step Delay:", self._delay_spin)

        # Max steps
        self._max_steps_spin = QSpinBox()
        self._max_steps_spin.setRange(1, 500)
        self._max_steps_spin.setValue(config.get("max_steps", 30))
        self._max_steps_spin.valueChanged.connect(self._on_max_steps_changed)
        layout.addRow("Max Steps:", self._max_steps_spin)

        # Temperature
        self._temp_spin = QDoubleSpinBox()
        self._temp_spin.setRange(0.0, 2.0)
        self._temp_spin.setSingleStep(0.1)
        self._temp_spin.setDecimals(1)
        self._temp_spin.setValue(config.get("temperature", 0))
        self._temp_spin.valueChanged.connect(self._on_temp_changed)
        layout.addRow("Temperature:", self._temp_spin)

        # Debug toggle
        self._debug_check = QCheckBox("Enable debug logging")
        self._debug_check.setChecked(config.get("debug", False))
        self._debug_check.toggled.connect(self._on_debug_toggled)
        layout.addRow(self._debug_check)

        layout.addRow(QWidget())  # spacer

        # Track startup-only widgets for locking
        self._startup_widgets = [
            self._model_combo,
            self._model_id_edit,
            self._base_url_edit,
        ]

    def set_bus(self, bus: AgentEventBus):
        """Point live settings at a new bus (called when a new run starts)."""
        self._bus = bus

    def get_config_overrides(self) -> dict:
        """Return all config values from the settings panel."""
        overrides = {}
        model = self._model_combo.currentText()
        if model:
            overrides["model"] = model
        model_id = self._model_id_edit.text().strip()
        if model_id:
            overrides["model_id"] = model_id
        base_url = self._base_url_edit.text().strip()
        if base_url:
            overrides["base_url"] = base_url
        overrides["step_delay"] = self._delay_spin.value()
        overrides["max_steps"] = self._max_steps_spin.value()
        overrides["temperature"] = self._temp_spin.value()
        overrides["debug"] = self._debug_check.isChecked()
        return overrides

    # --- Live setting forwarding (uses current bus) ---

    def _on_delay_changed(self, value):
        self._bus.set_live_setting("step_delay", value)

    def _on_max_steps_changed(self, value):
        self._bus.set_live_setting("max_steps", value)

    def _on_temp_changed(self, value):
        self._bus.set_live_setting("temperature", value)

    def _on_debug_toggled(self, checked):
        self._bus.set_live_setting("debug", checked)
