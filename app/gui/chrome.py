"""Native-feeling window chrome on Windows.

The app draws its own title bar (back button, icon, title, caption buttons)
like Windows Settings. To keep what users expect from a real window — Snap,
Aero shake, minimize/maximize animations, the drop shadow and Windows 11
rounded corners — the window keeps its caption and resizable-frame styles,
and the app answers two messages itself:

* ``WM_NCCALCSIZE``: the whole window is client area (no system title bar).
* ``WM_NCHITTEST``: 8 px edges resize; the empty title bar area drags.

Set ``WINFIX_NATIVE_FRAME=1`` to use the standard Windows title bar instead.
"""

from __future__ import annotations

import ctypes
import os
import sys
from ctypes import wintypes

from PySide6.QtCore import QPoint, Qt
from PySide6.QtWidgets import QPushButton, QWidget

IS_WINDOWS = sys.platform == "win32"

WM_NCCALCSIZE = 0x0083
WM_NCHITTEST = 0x0084
HTCAPTION, HTLEFT, HTRIGHT, HTTOP = 2, 10, 11, 12
HTTOPLEFT, HTTOPRIGHT, HTBOTTOM, HTBOTTOMLEFT, HTBOTTOMRIGHT = 13, 14, 15, 16, 17
GWL_STYLE = -16
WS_CAPTION, WS_THICKFRAME = 0x00C00000, 0x00040000
WS_MINIMIZEBOX, WS_MAXIMIZEBOX, WS_SYSMENU = 0x00020000, 0x00010000, 0x00080000
SWP_FLAGS = 0x0001 | 0x0002 | 0x0004 | 0x0020  # NOSIZE|NOMOVE|NOZORDER|FRAMECHANGED
DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWCP_ROUND = 2
RESIZE_BORDER = 8


def use_custom_frame() -> bool:
    return IS_WINDOWS and os.environ.get("WINFIX_NATIVE_FRAME") != "1"


class _Margins(ctypes.Structure):
    _fields_ = [("left", ctypes.c_int), ("right", ctypes.c_int),
                ("top", ctypes.c_int), ("bottom", ctypes.c_int)]


class _NCCalcSizeParams(ctypes.Structure):
    _fields_ = [("rgrc", wintypes.RECT * 3), ("lppos", ctypes.c_void_p)]


def install(window: QWidget) -> None:
    """Restore native frame behaviour on a frameless top-level window."""
    if not use_custom_frame():
        return
    hwnd = int(window.winId())
    user32 = ctypes.windll.user32
    get_style = user32.GetWindowLongPtrW
    set_style = user32.SetWindowLongPtrW
    get_style.restype = ctypes.c_ssize_t
    set_style.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
    style = get_style(wintypes.HWND(hwnd), GWL_STYLE)
    set_style(wintypes.HWND(hwnd), GWL_STYLE,
              style | WS_CAPTION | WS_THICKFRAME | WS_MINIMIZEBOX | WS_MAXIMIZEBOX | WS_SYSMENU)
    try:
        dwm = ctypes.windll.dwmapi
        # A 1 px top margin keeps DWM's shadow without a visible frame.
        dwm.DwmExtendFrameIntoClientArea(wintypes.HWND(hwnd),
                                         ctypes.byref(_Margins(0, 0, 1, 0)))
        corner = ctypes.c_int(DWMWCP_ROUND)
        dwm.DwmSetWindowAttribute(wintypes.HWND(hwnd), DWMWA_WINDOW_CORNER_PREFERENCE,
                                  ctypes.byref(corner), ctypes.sizeof(corner))
    except (AttributeError, OSError):
        pass  # older Windows: square corners, still fully functional
    user32.SetWindowPos(wintypes.HWND(hwnd), None, 0, 0, 0, 0, SWP_FLAGS)


def set_dark(window: QWidget, dark: bool) -> None:
    """Match the (hidden) native frame and border to the app theme."""
    if not IS_WINDOWS:
        return
    try:
        value = ctypes.c_int(1 if dark else 0)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(int(window.winId())), DWMWA_USE_IMMERSIVE_DARK_MODE,
            ctypes.byref(value), ctypes.sizeof(value))
    except (AttributeError, OSError):
        pass


def _frame_thickness() -> int:
    user32 = ctypes.windll.user32
    sm_cxsizeframe, sm_cxpaddedborder = 32, 92
    return user32.GetSystemMetrics(sm_cxsizeframe) + user32.GetSystemMetrics(sm_cxpaddedborder)


def handle_native_event(window: QWidget, title_bar: QWidget, message) -> tuple[bool, int]:
    """Called from ``nativeEvent``. Returns (handled, result)."""
    if not use_custom_frame():
        return False, 0
    msg = wintypes.MSG.from_address(int(message))
    if msg.message == WM_NCCALCSIZE and msg.wParam:
        if window.isMaximized():
            # A maximized window extends past the monitor by the frame
            # thickness; pull the client area back inside the work area.
            params = _NCCalcSizeParams.from_address(msg.lParam)
            inset = _frame_thickness()
            rect = params.rgrc[0]
            rect.left += inset
            rect.top += inset
            rect.right -= inset
            rect.bottom -= inset
        return True, 0

    if msg.message == WM_NCHITTEST:
        x = ctypes.c_short(msg.lParam & 0xFFFF).value
        y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
        ratio = window.devicePixelRatioF() or 1.0
        screen = window.screen().geometry() if window.screen() else None
        # lParam is in physical pixels; Qt geometry is in device-independent
        # pixels with each screen's origin kept at its native position.
        if screen is not None:
            gx = screen.x() + (x - screen.x()) / ratio
            gy = screen.y() + (y - screen.y()) / ratio
        else:
            gx, gy = x / ratio, y / ratio
        local = window.mapFromGlobal(QPoint(int(gx), int(gy)))
        w, h = window.width(), window.height()
        if not window.isMaximized():
            left, right = local.x() < RESIZE_BORDER, local.x() >= w - RESIZE_BORDER
            top, bottom = local.y() < RESIZE_BORDER, local.y() >= h - RESIZE_BORDER
            if top and left:
                return True, HTTOPLEFT
            if top and right:
                return True, HTTOPRIGHT
            if bottom and left:
                return True, HTBOTTOMLEFT
            if bottom and right:
                return True, HTBOTTOMRIGHT
            if left:
                return True, HTLEFT
            if right:
                return True, HTRIGHT
            if top:
                return True, HTTOP
            if bottom:
                return True, HTBOTTOM
        bar_pos = title_bar.mapFrom(window, local)
        if title_bar.rect().contains(bar_pos):
            child = title_bar.childAt(bar_pos)
            if not isinstance(child, QPushButton):
                return True, HTCAPTION
    return False, 0


def frameless_flags() -> Qt.WindowType:
    return Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint
