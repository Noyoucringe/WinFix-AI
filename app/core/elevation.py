"""Run one approved, admin-only fix through a UAC prompt.

WinFix runs unelevated. When the user approves a fix that needs administrator
rights, WinFix relaunches *itself* with the ``runas`` verb in a narrow helper
mode (``--run-remediation``). That helper:

* accepts only a registered remediation name plus JSON arguments,
* re-validates them through the safety layer,
* writes the structured result to a file inside WinFix's own data folder,
* and exits — it never shows UI and never runs anything else.

If the user declines the UAC prompt, nothing changes and the fix is reported
as not applied.
"""

from __future__ import annotations

import ctypes
import json
import subprocess
import sys
import uuid
from ctypes import wintypes
from pathlib import Path
from typing import Any

from app.core.config import IS_FROZEN, PROJECT_ROOT, user_data_dir
from app.core.logging_setup import get_logger
from app.core.result import ToolResult, error_result

logger = get_logger(__name__)

HELPER_FLAG = "--run-remediation"
ERROR_CANCELLED = 1223
_TIMEOUT_MS = 180_000


def request_dir() -> Path:
    path = user_data_dir() / "elevation"
    path.mkdir(parents=True, exist_ok=True)
    return path


def helper_command(tool: str, arguments: dict[str, Any], result_path: Path) -> tuple[str, list[str]]:
    """(executable, argv) that relaunches WinFix in helper mode."""
    flags = [HELPER_FLAG, tool, "--arguments", json.dumps(arguments),
             "--result", str(result_path)]
    if IS_FROZEN:
        return sys.executable, flags
    return sys.executable, ["-m", "app.main", *flags]


class _ShellExecuteInfo(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD), ("fMask", ctypes.c_ulong), ("hwnd", wintypes.HWND),
        ("lpVerb", wintypes.LPCWSTR), ("lpFile", wintypes.LPCWSTR),
        ("lpParameters", wintypes.LPCWSTR), ("lpDirectory", wintypes.LPCWSTR),
        ("nShow", ctypes.c_int), ("hInstApp", wintypes.HINSTANCE),
        ("lpIDList", ctypes.c_void_p), ("lpClass", wintypes.LPCWSTR),
        ("hkeyClass", wintypes.HKEY), ("dwHotKey", wintypes.DWORD),
        ("hIconOrMonitor", wintypes.HANDLE), ("hProcess", wintypes.HANDLE),
    ]


def run_elevated(tool: str, arguments: dict[str, Any]) -> ToolResult:
    """Run a remediation in an elevated helper process. Windows only."""
    if sys.platform != "win32":
        return error_result(tool, "UnsupportedPlatform", "Elevation requires Windows")

    result_path = request_dir() / f"{uuid.uuid4().hex}.json"
    exe, argv = helper_command(tool, arguments, result_path)

    see_mask_nocloseprocess, sw_hide = 0x00000040, 0
    info = _ShellExecuteInfo()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = see_mask_nocloseprocess
    info.lpVerb = "runas"
    info.lpFile = exe
    info.lpParameters = subprocess.list2cmdline(argv)
    info.lpDirectory = str(PROJECT_ROOT) if not IS_FROZEN else None
    info.nShow = sw_hide

    logger.info("requesting elevation", extra={"component": "elevation",
                                               "event": "request", "tool": tool})
    if not ctypes.windll.shell32.ShellExecuteExW(ctypes.byref(info)):
        code = ctypes.GetLastError()
        if code == ERROR_CANCELLED:
            logger.info("elevation declined", extra={"component": "elevation",
                                                     "event": "declined", "tool": tool})
            return error_result(tool, "ElevationDeclined",
                                "Administrator permission was not granted.")
        return error_result(tool, "ElevationFailed", f"Couldn't start the helper (error {code}).")

    kernel32 = ctypes.windll.kernel32
    try:
        if kernel32.WaitForSingleObject(info.hProcess, _TIMEOUT_MS) != 0:
            return error_result(tool, "TimeoutError", "The fix took too long to finish.")
    finally:
        kernel32.CloseHandle(info.hProcess)
    return read_result(tool, result_path)


def read_result(tool: str, result_path: Path) -> ToolResult:
    try:
        payload = json.loads(result_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return error_result(tool, "ElevationFailed", "The helper didn't report a result.")
    finally:
        result_path.unlink(missing_ok=True)
    if not isinstance(payload, dict) or payload.get("tool") != tool or "success" not in payload:
        return error_result(tool, "ElevationFailed", "The helper returned an invalid result.")
    return payload


def helper_main(tool: str, arguments_json: str, result_file: str) -> int:
    """Entry point of the elevated helper process. Runs exactly one fix."""
    from app.core.safety import SafetyValidator
    from app.core.tool_registry import get_registry

    result_path = Path(result_file).resolve()
    if result_path.parent != request_dir().resolve() or result_path.suffix != ".json":
        return 2  # refuse to write anywhere but WinFix's own request folder
    try:
        arguments = json.loads(arguments_json)
        if not isinstance(arguments, dict):
            raise ValueError("arguments must be an object")
        SafetyValidator().validate_remediation(tool, approved=True, arguments=arguments)
        result = get_registry().execute_tool(tool, arguments)
    except Exception as exc:  # noqa: BLE001 - report, don't crash silently
        result = error_result(tool, type(exc).__name__, str(exc))
    tmp = result_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(result, default=str), encoding="utf-8")
    tmp.replace(result_path)
    return 0 if result.get("success") else 1
