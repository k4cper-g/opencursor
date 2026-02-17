"""QSS dark theme stylesheet and color constants."""

COLORS = {
    "bg": "#1e1e1e",
    "bg_secondary": "#2d2d2d",
    "bg_tertiary": "#252526",
    "fg": "#d4d4d4",
    "fg_dim": "#808080",
    "accent": "#00ff88",
    "error": "#f44747",
    "warning": "#cca700",
    "step": "#569cd6",
    "think": "#ce9178",
    "success": "#00ff88",
    "border": "#3e3e3e",
}

DARK_STYLESHEET = f"""
QMainWindow, QWidget {{
    background-color: {COLORS['bg']};
    color: {COLORS['fg']};
    font-family: "Segoe UI", "SF Pro Text", "Helvetica Neue", sans-serif;
    font-size: 10pt;
}}

QPlainTextEdit {{
    background-color: {COLORS['bg']};
    color: {COLORS['fg']};
    border: 1px solid {COLORS['border']};
    font-family: Consolas, "SF Mono", "Courier New", monospace;
    font-size: 9pt;
    padding: 4px;
    selection-background-color: #264f78;
}}

QPushButton {{
    background-color: {COLORS['bg_secondary']};
    color: {COLORS['fg']};
    border: 1px solid {COLORS['border']};
    padding: 5px 14px;
    border-radius: 3px;
    min-width: 60px;
}}
QPushButton:hover {{
    background-color: #3e3e3e;
}}
QPushButton:pressed {{
    background-color: #4e4e4e;
}}
QPushButton:disabled {{
    color: #606060;
    background-color: #252526;
}}

QPushButton#stopButton {{
    border-color: {COLORS['error']};
}}
QPushButton#stopButton:hover {{
    background-color: #3a1d1d;
}}

QComboBox, QSpinBox, QDoubleSpinBox, QLineEdit {{
    background-color: {COLORS['bg_secondary']};
    color: {COLORS['fg']};
    border: 1px solid {COLORS['border']};
    padding: 3px 8px;
    border-radius: 2px;
    min-height: 22px;
}}
QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QLineEdit:disabled {{
    color: #606060;
    background-color: #252526;
}}
QComboBox::drop-down {{
    border: none;
    padding-right: 6px;
}}

QTabWidget::pane {{
    border: 1px solid {COLORS['border']};
    background-color: {COLORS['bg']};
}}
QTabBar::tab {{
    background-color: {COLORS['bg_secondary']};
    color: {COLORS['fg']};
    padding: 7px 18px;
    border: 1px solid {COLORS['border']};
    border-bottom: none;
    margin-right: 1px;
}}
QTabBar::tab:selected {{
    background-color: {COLORS['bg']};
    border-bottom: 2px solid {COLORS['accent']};
}}
QTabBar::tab:hover:!selected {{
    background-color: #353535;
}}

QSplitter::handle {{
    background-color: {COLORS['border']};
    width: 2px;
    height: 2px;
}}

QScrollArea {{
    border: none;
    background-color: {COLORS['bg']};
}}

QScrollBar:vertical {{
    background: {COLORS['bg']};
    width: 10px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {COLORS['border']};
    border-radius: 4px;
    min-height: 20px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background: {COLORS['bg']};
    height: 10px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: {COLORS['border']};
    border-radius: 4px;
    min-width: 20px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

QLabel {{
    color: {COLORS['fg']};
    background: transparent;
}}

QCheckBox {{
    color: {COLORS['fg']};
    spacing: 6px;
}}
QCheckBox::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {COLORS['border']};
    border-radius: 2px;
    background-color: {COLORS['bg_secondary']};
}}
QCheckBox::indicator:checked {{
    background-color: {COLORS['accent']};
    border-color: {COLORS['accent']};
}}

QFrame#stepCard {{
    background-color: {COLORS['bg_secondary']};
    border: 1px solid {COLORS['border']};
    border-radius: 4px;
    padding: 4px;
}}
QFrame#stepCard:hover {{
    border-color: {COLORS['step']};
}}
QFrame#stepCardSelected {{
    background-color: {COLORS['bg_secondary']};
    border: 1px solid {COLORS['accent']};
    border-radius: 4px;
    padding: 4px;
}}

QFormLayout {{
    margin: 8px;
}}
"""
