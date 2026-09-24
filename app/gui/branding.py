"""Application branding assets.

Resolves the app icon both when running from source and when running from a
PyInstaller one-file bundle (where data files are extracted to ``sys._MEIPASS``).
Falls back to a drawn icon if the asset is missing, so the GUI never fails to
start over branding.
"""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QIcon, QLinearGradient, QPainter, QPixmap

_ASSET_RELATIVE = Path("app") / "gui" / "assets"


def asset_dir() -> Path:
    """Directory holding bundled assets, in source and frozen builds alike."""
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        return Path(bundle) / _ASSET_RELATIVE
    return Path(__file__).resolve().parent / "assets"


def _drawn_icon() -> QIcon:
    """Fallback icon rendered at runtime."""
    size = 256
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)

    gradient = QLinearGradient(0, 0, 0, size)
    gradient.setColorAt(0.0, QColor("#3B82F6"))
    gradient.setColorAt(1.0, QColor("#2563EB"))
    painter.setBrush(QBrush(gradient))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(QRectF(0, 0, size, size), size * 0.22, size * 0.22)

    font = painter.font()
    font.setPointSizeF(size * 0.52)
    font.setBold(True)
    painter.setFont(font)
    painter.setPen(QColor("white"))
    painter.drawText(QRectF(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, "W")
    painter.end()

    return QIcon(pixmap)


@lru_cache(maxsize=1)
def app_icon() -> QIcon:
    """The WinFix application icon."""
    for name in ("winfix.ico", "winfix.png"):
        candidate = asset_dir() / name
        if candidate.exists():
            icon = QIcon(str(candidate))
            if not icon.isNull():
                return icon
    return _drawn_icon()
