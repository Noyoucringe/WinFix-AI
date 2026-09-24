"""Design system: color tokens, spacing, and the application stylesheet."""

from __future__ import annotations

# --- Color tokens ---------------------------------------------------------
BG = "#0B1020"          # app background
SIDEBAR = "#0E1526"     # navigation rail
SURFACE = "#151D33"     # cards
SURFACE_HOVER = "#1C2740"
BORDER = "#25314F"
BORDER_SOFT = "#1B2540"

TEXT = "#EAF0FF"
TEXT_MUTED = "#8FA0C4"
TEXT_FAINT = "#64769B"

PRIMARY = "#3B82F6"
PRIMARY_HOVER = "#2F6FE0"
PRIMARY_SOFT = "#16264A"

SUCCESS = "#34D399"
SUCCESS_SOFT = "#0E2E26"
WARN = "#FBBF24"
WARN_SOFT = "#332612"
DANGER = "#F87171"
DANGER_SOFT = "#3A1A1C"

RISK_COLORS = {
    "none": SUCCESS,
    "low": SUCCESS,
    "medium": WARN,
    "high": DANGER,
}
RISK_SOFT = {
    "none": SUCCESS_SOFT,
    "low": SUCCESS_SOFT,
    "medium": WARN_SOFT,
    "high": DANGER_SOFT,
}

STYLESHEET = f"""
/* ---- base ---- */
QWidget {{
    background-color: {BG};
    color: {TEXT};
    font-family: 'Segoe UI Variable', 'Segoe UI', 'Inter', sans-serif;
    font-size: 14px;
}}

/* Labels and layout containers must never paint their own panel background,
   otherwise they show as dark rectangles when placed inside a lighter card. */
QLabel {{
    background: transparent;
}}
QWidget#Transparent {{
    background: transparent;
}}

/* ---- typography ---- */
QLabel#Display  {{ font-size: 32px; font-weight: 700; letter-spacing: -0.5px; }}
QLabel#Title    {{ font-size: 24px; font-weight: 700; letter-spacing: -0.3px; }}
QLabel#Heading  {{ font-size: 16px; font-weight: 600; }}
QLabel#Body     {{ font-size: 14px; color: {TEXT}; }}
QLabel#Muted    {{ font-size: 13px; color: {TEXT_MUTED}; }}
QLabel#Faint    {{ font-size: 12px; color: {TEXT_FAINT}; }}
QLabel#Metric   {{ font-size: 13px; color: {TEXT_MUTED}; }}
QLabel#Eyebrow  {{
    font-size: 11px; font-weight: 700; color: {TEXT_FAINT};
    letter-spacing: 1.2px;
}}

/* ---- sidebar ---- */
QFrame#Sidebar {{
    background-color: {SIDEBAR};
    border-right: 1px solid {BORDER_SOFT};
}}
QLabel#Brand     {{ font-size: 18px; font-weight: 700; }}
QLabel#BrandMark {{
    font-size: 17px; font-weight: 800; color: white;
    background-color: {PRIMARY}; border-radius: 9px;
}}
QPushButton#NavItem {{
    background: transparent;
    color: {TEXT_MUTED};
    text-align: left;
    padding: 11px 14px;
    border-radius: 9px;
    font-weight: 600;
}}
QPushButton#NavItem:hover {{ background-color: {SURFACE_HOVER}; color: {TEXT}; }}
QPushButton#NavItem:checked {{ background-color: {PRIMARY_SOFT}; color: {TEXT}; }}

/* ---- cards ---- */
QFrame#Card {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 14px;
}}
QFrame#Banner {{ border-radius: 14px; border: 1px solid {BORDER}; }}
QFrame#Divider {{ background-color: {BORDER}; max-height: 1px; border: none; }}

/* ---- inputs ---- */
QPlainTextEdit, QTextEdit, QLineEdit {{
    background-color: {BG};
    border: 1px solid {BORDER};
    border-radius: 12px;
    padding: 14px;
    font-size: 15px;
    selection-background-color: {PRIMARY};
}}
QPlainTextEdit:focus, QTextEdit:focus, QLineEdit:focus {{ border: 1px solid {PRIMARY}; }}

/* ---- buttons ---- */
QPushButton {{
    background-color: {SURFACE_HOVER};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 11px 20px;
    font-weight: 600;
}}
QPushButton:hover  {{ background-color: {BORDER}; }}
QPushButton:disabled {{ background-color: {SURFACE}; color: {TEXT_FAINT}; border-color: {BORDER_SOFT}; }}

QPushButton#Primary {{ background-color: {PRIMARY}; border: none; color: white; padding: 12px 24px; }}
QPushButton#Primary:hover {{ background-color: {PRIMARY_HOVER}; }}
QPushButton#Danger  {{ background-color: {DANGER}; border: none; color: #2A0B0C; padding: 12px 24px; }}
QPushButton#Ghost   {{ background: transparent; border: 1px solid {BORDER}; color: {TEXT_MUTED}; }}
QPushButton#Ghost:hover {{ color: {TEXT}; background-color: {SURFACE_HOVER}; }}

/* Example-problem chips on the home screen */
QPushButton#Chip {{
    background-color: {SURFACE};
    border: 1px solid {BORDER};
    color: {TEXT_MUTED};
    text-align: left;
    padding: 12px 14px;
    font-weight: 500;
    border-radius: 10px;
}}
QPushButton#Chip:hover {{ border-color: {PRIMARY}; color: {TEXT}; background-color: {SURFACE_HOVER}; }}

/* ---- lists ---- */
QListWidget {{
    background-color: transparent;
    border: none;
    outline: none;
}}
QListWidget::item {{
    padding: 11px 12px;
    border-radius: 9px;
    color: {TEXT_MUTED};
    margin-bottom: 3px;
}}
QListWidget::item:selected {{ background-color: {PRIMARY_SOFT}; color: {TEXT}; }}
QListWidget#Steps::item {{ color: {TEXT}; }}

/* ---- progress bar (confidence) ---- */
QProgressBar {{
    background-color: {BG};
    border: none;
    border-radius: 4px;
    height: 7px;
    text-align: center;
}}
QProgressBar::chunk {{ background-color: {PRIMARY}; border-radius: 4px; }}

/* ---- scrollbars ---- */
QScrollArea {{ border: none; background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 4px; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 5px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {TEXT_FAINT}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
"""
