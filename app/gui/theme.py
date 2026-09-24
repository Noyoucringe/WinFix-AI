"""Design tokens and the application stylesheet (Windows 11 Fluent-inspired).

Colors are the values from the WinFix AI design specification. Light and dark
are separate palettes (dark mode is designed, not inverted). Widgets read
colors through the current :class:`Palette`, and the global stylesheet is
regenerated when the theme changes.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QColor, QGuiApplication


@dataclass(frozen=True)
class Palette:
    name: str
    # surfaces
    mica_start: str
    mica_end: str
    layer: str
    layer_border: str
    card: str
    card_border: str
    card_hover: str
    card_pressed: str
    divider: str
    shadow: tuple[int, int, int, int]
    smoke: str
    dialog: str
    dialog_footer: str
    # text
    text: str
    text_secondary: str
    text_disabled: str
    # accent + states
    accent: str
    accent_hover: str
    accent_pressed: str
    accent_disabled: str
    on_accent: str
    accent_text: str
    success: str
    caution: str
    critical: str
    on_status: str
    success_bg: str
    caution_bg: str
    critical_bg: str
    info_bg: str
    # controls
    control: str
    control_hover: str
    control_pressed: str
    control_border: str
    control_border_bottom: str
    subtle_hover: str
    subtle_pressed: str
    input: str
    input_focus: str
    input_border_bottom: str
    strong_stroke: str
    nav_hover: str
    nav_selected: str
    focus: str
    close_hover: str = "#C42B1C"

    def qcolor(self, token: str) -> QColor:
        return QColor(getattr(self, token))


LIGHT = Palette(
    name="light",
    mica_start="#E9EEF5", mica_end="#F3F3F3",
    layer="#F9F9F9", layer_border="#E5E5E5",
    card="#FFFFFF", card_border="#E5E5E5", card_hover="#F6F6F6", card_pressed="#F2F2F2",
    divider="rgba(0,0,0,0.08)", shadow=(0, 0, 0, 22),
    smoke="rgba(0,0,0,0.30)", dialog="#F9F9F9", dialog_footer="#F3F3F3",
    text="#1A1A1A", text_secondary="#5C5C5C", text_disabled="#A0A0A0",
    accent="#0067C0", accent_hover="#1975C5", accent_pressed="#3183CA",
    accent_disabled="#BFBFBF", on_accent="#FFFFFF", accent_text="#005FB8",
    success="#0F7B0F", caution="#9D5D00", critical="#C42B1C", on_status="#FFFFFF",
    success_bg="#DFF6DD", caution_bg="#FFF4CE", critical_bg="#FDE7E9", info_bg="#F6F6F6",
    control="#FDFDFD", control_hover="#F6F6F6", control_pressed="#F2F2F2",
    control_border="#E5E5E5", control_border_bottom="#CCCCCC",
    subtle_hover="rgba(0,0,0,0.04)", subtle_pressed="rgba(0,0,0,0.025)",
    input="#FFFFFF", input_focus="#FFFFFF", input_border_bottom="#8A8A8A",
    strong_stroke="#8A8A8A",
    nav_hover="rgba(0,0,0,0.04)", nav_selected="rgba(0,0,0,0.06)",
    focus="#000000",
)

DARK = Palette(
    name="dark",
    mica_start="#1D2027", mica_end="#202020",
    layer="#272727", layer_border="#1C1C1C",
    card="#2D2D2D", card_border="#353535", card_hover="#323232", card_pressed="#2A2A2A",
    divider="rgba(255,255,255,0.08)", shadow=(0, 0, 0, 70),
    smoke="rgba(0,0,0,0.40)", dialog="#2B2B2B", dialog_footer="#202020",
    text="#FFFFFF", text_secondary="#CFCFCF", text_disabled="#787878",
    accent="#4CC2FF", accent_hover="#47B1E8", accent_pressed="#42A1D2",
    accent_disabled="#434343", on_accent="#000000", accent_text="#99EBFF",
    success="#6CCB5F", caution="#FCE100", critical="#FF99A4", on_status="#000000",
    success_bg="#393D1B", caution_bg="#433519", critical_bg="#442726", info_bg="#2B2B2B",
    control="#2D2D2D", control_hover="#323232", control_pressed="#272727",
    control_border="#3A3A3A", control_border_bottom="#3A3A3A",
    subtle_hover="rgba(255,255,255,0.06)", subtle_pressed="rgba(255,255,255,0.04)",
    input="#2D2D2D", input_focus="#1F1F1F", input_border_bottom="#9A9A9A",
    strong_stroke="#9A9A9A",
    nav_hover="rgba(255,255,255,0.05)", nav_selected="rgba(255,255,255,0.07)",
    focus="#FFFFFF",
)

LEVEL_TOKEN = {"ok": "success", "success": "success", "info": "accent",
               "caution": "caution", "critical": "critical"}


# --- typography ----------------------------------------------------------------
@dataclass(frozen=True)
class TypeStyle:
    size: int
    line: int
    weight: int  # 400 regular, 600 semibold
    display: bool = False


TYPE = {
    "title_large": TypeStyle(40, 52, 600, True),
    "title": TypeStyle(28, 36, 600, True),
    "subtitle": TypeStyle(20, 28, 600, True),
    "body_strong": TypeStyle(14, 20, 600),
    "body": TypeStyle(14, 20, 400),
    "caption": TypeStyle(12, 16, 400),
    "value": TypeStyle(28, 36, 600, True),
}

TEXT_FAMILIES = ["Segoe UI Variable Text", "Segoe UI", "Open Sans", "Noto Sans",
                 "DejaVu Sans"]
DISPLAY_FAMILIES = ["Segoe UI Variable Display", "Segoe UI", "Open Sans", "Noto Sans",
                    "DejaVu Sans"]


def _stylesheet(p: Palette) -> str:
    return f"""
* {{ outline: none; }}
QWidget {{ color: {p.text}; background: transparent; }}
QWidget#Layer {{ background: {p.layer}; border-top: 1px solid {p.layer_border};
    border-left: 1px solid {p.layer_border}; border-top-left-radius: 8px; }}
QToolTip {{ background: {p.card}; color: {p.text}; border: 1px solid {p.card_border};
    padding: 6px 8px; border-radius: 4px; }}

QLabel[role="secondary"] {{ color: {p.text_secondary}; }}
QLabel[role="disabled"] {{ color: {p.text_disabled}; }}
QLabel[role="accent"] {{ color: {p.accent_text}; }}
QLabel[role="success"] {{ color: {p.success}; }}
QLabel[role="caution"] {{ color: {p.caution}; }}
QLabel[role="critical"] {{ color: {p.critical}; }}

QFrame#Card {{ background: {p.card}; border: 1px solid {p.card_border}; border-radius: 8px; }}
QFrame#CardRow {{ background: {p.card}; border: 1px solid {p.card_border}; border-radius: 4px; }}
QFrame#ListCard {{ background: {p.card}; border: 1px solid {p.card_border}; border-radius: 8px; }}
QFrame#Divider {{ background: {p.divider}; border: none; }}
QPushButton#RowButton {{ background: {p.card}; border: 1px solid {p.card_border};
    border-radius: 4px; text-align: left; padding: 0; min-height: 0px; }}
QPushButton#RowButton:hover {{ background: {p.card_hover}; }}
QPushButton#RowButton:pressed {{ background: {p.card_pressed}; }}
QPushButton#RowButton:focus {{ border: 2px solid {p.focus}; }}

QPushButton {{ font-size: 14px; min-height: 30px; padding: 0 12px; border-radius: 4px; }}
QPushButton#Accent {{ background: {p.accent}; color: {p.on_accent};
    border: 1px solid {p.accent}; }}
QPushButton#Accent:hover {{ background: {p.accent_hover}; border-color: {p.accent_hover}; }}
QPushButton#Accent:pressed {{ background: {p.accent_pressed}; border-color: {p.accent_pressed}; }}
QPushButton#Accent:disabled {{ background: {p.accent_disabled}; border-color: {p.accent_disabled};
    color: {p.text_disabled if p.name == "dark" else "#FFFFFF"}; }}
QPushButton#Standard {{ background: {p.control}; color: {p.text};
    border: 1px solid {p.control_border}; border-bottom-color: {p.control_border_bottom}; }}
QPushButton#Standard:hover {{ background: {p.control_hover}; }}
QPushButton#Standard:pressed {{ background: {p.control_pressed}; color: {p.text_secondary}; }}
QPushButton#Standard:disabled {{ color: {p.text_disabled}; }}
QPushButton#Subtle {{ background: transparent; color: {p.text}; border: 1px solid transparent; }}
QPushButton#Subtle:hover {{ background: {p.subtle_hover}; }}
QPushButton#Subtle:pressed {{ background: {p.subtle_pressed}; color: {p.text_secondary}; }}
QPushButton#Subtle:disabled {{ color: {p.text_disabled}; }}
QPushButton#Hyperlink {{ background: transparent; color: {p.accent_text};
    border: 1px solid transparent; padding: 0 6px; }}
QPushButton#Hyperlink:hover {{ background: {p.subtle_hover}; }}
QPushButton#Hyperlink:pressed {{ color: {p.text_secondary}; }}
QPushButton#Chip {{ background: {p.control}; color: {p.text}; border: 1px solid {p.control_border};
    border-bottom-color: {p.control_border_bottom}; padding: 0 10px; }}
QPushButton#Chip:hover {{ background: {p.control_hover}; }}
QPushButton#Accent:focus, QPushButton#Standard:focus, QPushButton#Subtle:focus,
QPushButton#Hyperlink:focus, QPushButton#Chip:focus {{ border: 2px solid {p.focus}; }}

QPushButton#Caption {{ background: transparent; border: none; border-radius: 0;
    min-height: 32px; padding: 0; }}
QPushButton#Caption:hover {{ background: {p.subtle_hover}; }}
QPushButton#Caption:pressed {{ background: {p.subtle_pressed}; }}
QPushButton#Close {{ background: transparent; border: none; border-radius: 0;
    min-height: 32px; padding: 0; }}
QPushButton#Close:hover {{ background: {p.close_hover}; }}
QPushButton#Close:pressed {{ background: #C83C31; }}

QLineEdit, QPlainTextEdit {{ background: {p.input}; color: {p.text}; font-size: 14px;
    border: 1px solid {p.control_border}; border-bottom: 1px solid {p.input_border_bottom};
    border-radius: 4px; padding: 5px 10px; selection-background-color: {p.accent};
    selection-color: {p.on_accent}; }}
QLineEdit:hover {{ background: {p.control_hover}; }}
QLineEdit:focus {{ background: {p.input_focus}; border-bottom: 2px solid {p.accent}; }}
QLineEdit[error="true"] {{ border-bottom: 2px solid {p.critical}; }}
QLineEdit:disabled {{ color: {p.text_disabled}; }}

QComboBox {{ background: {p.control}; color: {p.text}; border: 1px solid {p.control_border};
    border-bottom-color: {p.control_border_bottom}; border-radius: 4px; padding: 4px 10px;
    min-height: 22px; font-size: 14px; }}
QComboBox:hover {{ background: {p.control_hover}; }}
QComboBox:focus {{ border: 2px solid {p.focus}; }}
QComboBox::drop-down {{ border: none; width: 28px; }}
QComboBox::down-arrow {{ image: none; }}
QComboBox QAbstractItemView {{ background: {p.dialog}; color: {p.text};
    border: 1px solid {p.card_border}; border-radius: 8px; padding: 4px; outline: none;
    selection-background-color: {p.nav_selected}; selection-color: {p.text}; }}
QComboBox QAbstractItemView::item {{ min-height: 32px; padding: 0 10px; border-radius: 4px; }}

QCheckBox {{ spacing: 8px; font-size: 14px; }}
QRadioButton {{ spacing: 8px; font-size: 14px; }}

QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 12px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {p.strong_stroke}; border-radius: 3px;
    min-height: 32px; margin: 0 3px; }}
QScrollBar::handle:vertical:hover {{ margin: 0 2px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QScrollBar:horizontal {{ height: 0; }}

QTableWidget {{ background: {p.card}; border: 1px solid {p.card_border}; border-radius: 8px;
    gridline-color: transparent; font-size: 14px; selection-background-color: {p.nav_selected};
    selection-color: {p.text}; }}
QTableWidget::item {{ padding: 0 8px; border-bottom: 1px solid {p.divider}; }}
QHeaderView::section {{ background: {p.card}; color: {p.text_secondary}; font-size: 12px;
    border: none; border-bottom: 1px solid {p.divider}; padding: 8px 8px; }}
QHeaderView::section:hover {{ color: {p.text}; }}

QMenu {{ background: {p.dialog}; color: {p.text}; border: 1px solid {p.card_border};
    border-radius: 8px; padding: 4px; }}
QMenu::item {{ padding: 6px 12px; border-radius: 4px; }}
QMenu::item:selected {{ background: {p.nav_selected}; }}
"""


class ThemeManager(QObject):
    """Holds the active palette; resolves "system" from Windows' app mode."""

    changed = Signal(object)  # Palette

    def __init__(self) -> None:
        super().__init__()
        self.mode = "system"
        self.palette = LIGHT

    @staticmethod
    def system_is_dark() -> bool:
        from app.core import winapi

        light = winapi.apps_use_light_theme()
        if light is not None:
            return not light
        app = QGuiApplication.instance()
        if app is not None:
            try:
                from PySide6.QtCore import Qt

                return app.styleHints().colorScheme() == Qt.ColorScheme.Dark
            except AttributeError:
                return False
        return False

    def apply(self, mode: str) -> Palette:
        self.mode = mode
        dark = mode == "dark" or (mode == "system" and self.system_is_dark())
        self.palette = DARK if dark else LIGHT
        app = QGuiApplication.instance()
        if app is not None:
            app.setStyleSheet(_stylesheet(self.palette))
        self.changed.emit(self.palette)
        return self.palette


_manager: ThemeManager | None = None


def manager() -> ThemeManager:
    global _manager
    if _manager is None:
        _manager = ThemeManager()
    return _manager


def palette() -> Palette:
    return manager().palette


def status_color(level: str) -> QColor:
    return palette().qcolor(LEVEL_TOKEN.get(level, "text_secondary"))
