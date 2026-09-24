"""Motion tokens from the design spec: fast, quiet, functional.

Fast 83 ms (hover/pressed), Normal 167 ms (toggles, selection pill, status
icon), Dialog 250 ms (scale 1.05 -> 1), Page 300 ms (28 px up + fade in).
When Windows animation effects are off, entrances and pops are removed;
progress indicators keep moving.
"""

from __future__ import annotations

import os

from PySide6.QtCore import (
    QAbstractAnimation,
    QEasingCurve,
    QParallelAnimationGroup,
    QPoint,
    QPointF,
    QPropertyAnimation,
)
from PySide6.QtWidgets import QGraphicsOpacityEffect, QWidget

FAST_MS = 83
NORMAL_MS = 167
DIALOG_MS = 250
PAGE_MS = 300
PROGRESS_LOOP_MS = 1800


def animations_enabled() -> bool:
    if os.environ.get("WINFIX_REDUCED_MOTION") == "1":
        return False
    from app.core import winapi

    return winapi.animations_enabled()


def decelerate() -> QEasingCurve:
    """cubic-bezier(0, 0, 0, 1)."""
    curve = QEasingCurve(QEasingCurve.Type.BezierSpline)
    curve.addCubicBezierSegment(QPointF(0, 0), QPointF(0, 1), QPointF(1, 1))
    return curve


def page_curve() -> QEasingCurve:
    """cubic-bezier(0.1, 0.9, 0.2, 1)."""
    curve = QEasingCurve(QEasingCurve.Type.BezierSpline)
    curve.addCubicBezierSegment(QPointF(0.1, 0.9), QPointF(0.2, 1), QPointF(1, 1))
    return curve


def page_entrance(widget: QWidget) -> None:
    """28 px upward slide + fade in over 300 ms (skipped with reduced motion)."""
    if not animations_enabled() or not widget.isVisible():
        return
    effect = QGraphicsOpacityEffect(widget)
    widget.setGraphicsEffect(effect)
    fade = QPropertyAnimation(effect, b"opacity", widget)
    fade.setDuration(PAGE_MS)
    fade.setStartValue(0.0)
    fade.setEndValue(1.0)
    fade.setEasingCurve(page_curve())
    end = widget.pos()
    slide = QPropertyAnimation(widget, b"pos", widget)
    slide.setDuration(PAGE_MS)
    slide.setStartValue(end + QPoint(0, 28))
    slide.setEndValue(end)
    slide.setEasingCurve(page_curve())
    group = QParallelAnimationGroup(widget)
    group.addAnimation(fade)
    group.addAnimation(slide)
    # Graphics effects slow text rendering; drop it once the entrance ends.
    group.finished.connect(lambda: widget.setGraphicsEffect(None))
    group.start(QAbstractAnimation.DeletionPolicy.DeleteWhenStopped)
