"""Reusable widgets and factory helpers for the design system."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from app.gui.theme import RISK_COLORS, RISK_SOFT, SURFACE, TEXT_MUTED


# --- text helpers ---------------------------------------------------------
def _label(text: str, object_name: str, *, wrap: bool = True) -> QLabel:
    label = QLabel(text)
    label.setObjectName(object_name)
    label.setWordWrap(wrap)
    return label


def display(text: str) -> QLabel:
    return _label(text, "Display", wrap=False)


def title_label(text: str) -> QLabel:
    return _label(text, "Title", wrap=True)


def heading(text: str) -> QLabel:
    return _label(text, "Heading", wrap=False)


def body(text: str) -> QLabel:
    return _label(text, "Body")


def muted(text: str) -> QLabel:
    return _label(text, "Muted")


def faint(text: str) -> QLabel:
    return _label(text, "Faint")


def eyebrow(text: str) -> QLabel:
    return _label(text, "Eyebrow", wrap=False)


# --- containers -----------------------------------------------------------
class Card(QFrame):
    """A rounded surface panel with a vertical layout."""

    def __init__(self, parent: QWidget | None = None, *, spacing: int = 10) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(22, 20, 22, 20)
        self._layout.setSpacing(spacing)

    def layout(self) -> QVBoxLayout:  # type: ignore[override]
        return self._layout

    def add(self, widget: QWidget) -> None:
        self._layout.addWidget(widget)

    def add_layout(self, layout) -> None:
        self._layout.addLayout(layout)


def divider() -> QFrame:
    line = QFrame()
    line.setObjectName("Divider")
    line.setFixedHeight(1)
    return line


def container(layout=None) -> QWidget:
    """A transparent wrapper widget.

    Plain QWidgets inherit the app background, which shows as a dark band when
    they sit inside a lighter card. Everything used purely to host a layout
    must go through here.
    """
    widget = QWidget()
    widget.setObjectName("Transparent")
    if layout is not None:
        widget.setLayout(layout)
    return widget


def row(*widgets: QWidget, spacing: int = 10, stretch_at: int | None = None) -> QWidget:
    """Lay widgets out horizontally inside a transparent wrapper."""
    wrapper = container()
    layout = QHBoxLayout(wrapper)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(spacing)
    for i, w in enumerate(widgets):
        layout.addWidget(w)
        if stretch_at is not None and i == stretch_at:
            layout.addStretch(1)
    return wrapper


# --- badges / indicators --------------------------------------------------
class Pill(QLabel):
    """A small rounded status badge."""

    def __init__(self, text: str, color: str, background: str) -> None:
        super().__init__(text)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.setStyleSheet(
            f"background-color:{background}; color:{color};"
            f"border:1px solid {color}; border-radius:10px;"
            "padding:3px 12px; font-size:11px; font-weight:700;"
        )


def risk_pill(risk: str) -> Pill:
    color = RISK_COLORS.get(risk, TEXT_MUTED)
    background = RISK_SOFT.get(risk, SURFACE)
    return Pill(f"{risk.upper()} RISK", color, background)


class ConfidenceBar(QWidget):
    """A labelled confidence meter for a diagnosis cause."""

    def __init__(self, confidence: float, word: str) -> None:
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 2, 0, 2)
        layout.setSpacing(12)

        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(int(round(confidence * 100)))
        bar.setTextVisible(False)
        bar.setFixedHeight(7)
        bar.setFixedWidth(160)
        layout.addWidget(bar)

        label = _label(f"{word} · {confidence:.0%} confidence", "Faint", wrap=False)
        layout.addWidget(label)
        layout.addStretch(1)


def status_dot(ok: bool | None) -> QLabel:
    """A small circular status indicator for a diagnostic step."""
    if ok is None:
        char, color = "◌", TEXT_MUTED
    elif ok:
        char, color = "●", RISK_COLORS["low"]
    else:
        char, color = "○", TEXT_MUTED
    label = QLabel(char)
    label.setStyleSheet(f"color:{color}; font-size:15px; background:transparent;")
    label.setFixedWidth(18)
    return label


# Backwards-compatible alias used by older call sites.
def section_header(text: str) -> QLabel:
    return heading(text)


def hline() -> QFrame:
    return divider()
