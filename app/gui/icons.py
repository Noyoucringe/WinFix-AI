"""Fluent UI System Icons (MIT), recolored per theme at render time."""

from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QWidget

from app.gui import theme
from app.gui.branding import asset_dir

# Semantic names used in the app -> Fluent icon file names.
ALIASES = {
    "back": "arrow_left", "menu": "navigation", "diagnostics": "pulse",
    "troubleshoot": "wrench", "cpu": "developer_board", "memory": "ram",
    "disk": "hard_drive", "list": "text_bullet_list_ltr", "services": "puzzle_piece",
    "event": "document_error", "document": "document_text", "refresh": "arrow_clockwise",
    "export": "arrow_export_ltr", "speed": "top_speed", "wifi": "wifi_1",
    "update": "arrow_sync", "lock": "lock_closed", "theme": "dark_theme",
    "privacy": "shield_lock", "bell": "alert", "speaker": "speaker_2",
    "app": "app_generic", "device": "phone_laptop", "restart": "arrow_counterclockwise",
    "close": "dismiss", "minimize": "subtract", "restore": "square_multiple",
    "pc": "desktop", "rocket": "rocket", "check": "checkmark", "folder": "folder_open",
    "shield_check": "shield_checkmark", "chevron": "chevron_right",
}


@lru_cache(maxsize=128)
def _svg(name: str) -> bytes:
    file = ALIASES.get(name, name)
    path = asset_dir() / "icons" / f"{file}.svg"
    if not path.exists():
        path = asset_dir() / "icons" / "info.svg"
    return path.read_bytes()


@lru_cache(maxsize=1024)
def pixmap(name: str, color: str, size: int = 16, dpr: float = 1.0) -> QPixmap:
    data = _svg(name).replace(b"<svg ", f'<svg fill="{color}" '.encode(), 1)
    renderer = QSvgRenderer(QByteArray(data))
    px = max(1, round(size * dpr))
    image = QPixmap(px, px)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    renderer.render(painter, QRectF(0, 0, px, px))
    painter.end()
    image.setDevicePixelRatio(dpr)
    return image


def icon(name: str, token: str = "text", size: int = 16) -> QIcon:
    color = getattr(theme.palette(), token, token)
    result = QIcon()
    for dpr in (1.0, 1.5, 2.0):
        result.addPixmap(pixmap(name, color, size, dpr))
    return result


class IconLabel(QWidget):
    """A themed Fluent icon that repaints when the theme changes."""

    def __init__(self, name: str, token: str = "text", size: int = 16,
                 parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._name, self._token, self._size = name, token, size
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def set_icon(self, name: str, token: str | None = None) -> None:
        self._name = name
        if token:
            self._token = token
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(self._size, self._size)

    def paintEvent(self, _event) -> None:
        color = getattr(theme.palette(), self._token, self._token)
        painter = QPainter(self)
        painter.drawPixmap(0, 0, pixmap(self._name, QColor(color).name(),
                                        self._size, self.devicePixelRatioF()))
        painter.end()
