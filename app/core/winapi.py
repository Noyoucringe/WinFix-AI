"""Thin, read-only ctypes wrappers around Win32 APIs.

These replace shelling out for data Windows exposes directly: hung windows,
memory commit/cache counters, file descriptions, Recycle Bin size, theme and
animation preferences. Every function is safe to call on any platform and
returns ``None``/empty when the API is unavailable.
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from functools import lru_cache

_IS_WINDOWS = sys.platform == "win32"


# --- privileges -------------------------------------------------------------
def is_user_admin() -> bool:
    if not _IS_WINDOWS:
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


# --- hung (not responding) windows -----------------------------------------
def hung_window_pids() -> set[int]:
    """PIDs owning a visible top-level window that Windows marks as hung.

    This is the same signal Task Manager uses for "Not responding".
    """
    if not _IS_WINDOWS:
        return set()
    user32 = ctypes.windll.user32
    pids: set[int] = set()
    enum_proc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    user32.IsWindowVisible.argtypes = [wintypes.HWND]
    user32.IsHungAppWindow.argtypes = [wintypes.HWND]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND,
                                                ctypes.POINTER(wintypes.DWORD)]

    def _callback(hwnd, _lparam):
        if user32.IsWindowVisible(hwnd) and user32.IsHungAppWindow(hwnd):
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if pid.value:
                pids.add(int(pid.value))
        return True

    user32.EnumWindows(enum_proc(_callback), 0)
    return pids


# --- memory counters -------------------------------------------------------
class _PerformanceInformation(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("CommitTotal", ctypes.c_size_t),
        ("CommitLimit", ctypes.c_size_t),
        ("CommitPeak", ctypes.c_size_t),
        ("PhysicalTotal", ctypes.c_size_t),
        ("PhysicalAvailable", ctypes.c_size_t),
        ("SystemCache", ctypes.c_size_t),
        ("KernelTotal", ctypes.c_size_t),
        ("KernelPaged", ctypes.c_size_t),
        ("KernelNonpaged", ctypes.c_size_t),
        ("PageSize", ctypes.c_size_t),
        ("HandleCount", wintypes.DWORD),
        ("ProcessCount", wintypes.DWORD),
        ("ThreadCount", wintypes.DWORD),
    ]


def performance_info() -> dict[str, int] | None:
    """Commit charge, cache and counts from ``GetPerformanceInfo`` (bytes)."""
    if not _IS_WINDOWS:
        return None
    info = _PerformanceInformation()
    info.cb = ctypes.sizeof(info)
    if not ctypes.windll.psapi.GetPerformanceInfo(ctypes.byref(info), info.cb):
        return None
    page = info.PageSize
    return {
        "commit_total": info.CommitTotal * page,
        "commit_limit": info.CommitLimit * page,
        "system_cache": info.SystemCache * page,
        "process_count": int(info.ProcessCount),
        "thread_count": int(info.ThreadCount),
        "handle_count": int(info.HandleCount),
    }


# --- Recycle Bin -----------------------------------------------------------
class _ShQueryRbInfo(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("i64Size", ctypes.c_longlong),
        ("i64NumItems", ctypes.c_longlong),
    ]


def recycle_bin_usage() -> tuple[int, int] | None:
    """(bytes, item count) across all drives, via ``SHQueryRecycleBinW``."""
    if not _IS_WINDOWS:
        return None
    info = _ShQueryRbInfo()
    info.cbSize = ctypes.sizeof(info)
    result = ctypes.windll.shell32.SHQueryRecycleBinW(None, ctypes.byref(info))
    if result != 0:
        return None
    return int(info.i64Size), int(info.i64NumItems)


# --- file descriptions ("Google Chrome" rather than "chrome.exe") ----------
@lru_cache(maxsize=512)
def file_description(path: str) -> str | None:
    if not _IS_WINDOWS or not path:
        return None
    version = ctypes.windll.version
    size = version.GetFileVersionInfoSizeW(path, None)
    if not size:
        return None
    buffer = ctypes.create_string_buffer(size)
    if not version.GetFileVersionInfoW(path, 0, size, buffer):
        return None

    value = ctypes.c_void_p()
    length = wintypes.UINT()
    if not version.VerQueryValueW(buffer, "\\VarFileInfo\\Translation",
                                  ctypes.byref(value), ctypes.byref(length)):
        return None
    if length.value < 4:
        return None
    lang, codepage = ctypes.cast(value, ctypes.POINTER(wintypes.WORD * 2)).contents
    key = f"\\StringFileInfo\\{lang:04x}{codepage:04x}\\FileDescription"
    if not version.VerQueryValueW(buffer, key, ctypes.byref(value), ctypes.byref(length)):
        return None
    text = ctypes.wstring_at(value, max(0, length.value - 1)).strip()
    return text or None


# --- user preferences ------------------------------------------------------
def apps_use_light_theme() -> bool | None:
    """The 'Choose your app mode' setting, or None when unknown."""
    if not _IS_WINDOWS:
        return None
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize",
        ) as key:
            value, _ = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return bool(value)
    except OSError:
        return None


def animations_enabled() -> bool:
    """False when 'Animation effects' is turned off in Windows settings."""
    if not _IS_WINDOWS:
        return True
    spi_getclientareaanimation = 0x1042
    enabled = wintypes.BOOL(True)
    ok = ctypes.windll.user32.SystemParametersInfoW(
        spi_getclientareaanimation, 0, ctypes.byref(enabled), 0
    )
    return bool(enabled.value) if ok else True
