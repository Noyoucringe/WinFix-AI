"""Application stylesheet and shared style constants."""

from __future__ import annotations

PRIMARY = "#2563eb"
PRIMARY_DARK = "#1d4ed8"
BG = "#0f172a"
SURFACE = "#1e293b"
SURFACE_2 = "#334155"
TEXT = "#e2e8f0"
MUTED = "#94a3b8"
SUCCESS = "#22c55e"
WARN = "#f59e0b"
DANGER = "#ef4444"

RISK_COLORS = {
    "none": SUCCESS,
    "low": SUCCESS,
    "medium": WARN,
    "high": DANGER,
}

STYLESHEET = f"""
QWidget {{
    background-color: {BG};
    color: {TEXT};
    font-family: 'Segoe UI', 'Inter', sans-serif;
    font-size: 14px;
}}
QLabel#Title {{
    font-size: 30px;
    font-weight: 700;
}}
QLabel#Subtitle {{
    font-size: 16px;
    color: {MUTED};
}}
QLabel#SectionHeader {{
    font-size: 18px;
    font-weight: 600;
}}
QLabel#Muted {{
    color: {MUTED};
}}
QFrame#Card {{
    background-color: {SURFACE};
    border: 1px solid {SURFACE_2};
    border-radius: 12px;
}}
QTextEdit, QLineEdit, QPlainTextEdit {{
    background-color: {SURFACE};
    border: 1px solid {SURFACE_2};
    border-radius: 8px;
    padding: 10px;
    selection-background-color: {PRIMARY};
}}
QPushButton {{
    background-color: {SURFACE_2};
    border: none;
    border-radius: 8px;
    padding: 10px 18px;
    font-weight: 600;
}}
QPushButton:hover {{ background-color: #3f4c63; }}
QPushButton#Primary {{ background-color: {PRIMARY}; color: white; }}
QPushButton#Primary:hover {{ background-color: {PRIMARY_DARK}; }}
QPushButton#Danger {{ background-color: {DANGER}; color: white; }}
QPushButton:disabled {{ background-color: #263143; color: {MUTED}; }}
QListWidget {{
    background-color: {SURFACE};
    border: 1px solid {SURFACE_2};
    border-radius: 8px;
    padding: 4px;
}}
QListWidget::item {{ padding: 10px; border-radius: 6px; }}
QListWidget::item:selected {{ background-color: {PRIMARY}; color: white; }}
QScrollBar:vertical {{ background: {BG}; width: 10px; }}
QScrollBar::handle:vertical {{ background: {SURFACE_2}; border-radius: 5px; }}
"""
