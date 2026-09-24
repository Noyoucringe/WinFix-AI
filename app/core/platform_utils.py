"""Platform helpers and the single audited path for running system commands.

* Windows-only tools degrade gracefully on other hosts instead of crashing.
* Every command runs with a fixed argument vector (never ``shell=True``), a
  timeout, and — on Windows — ``CREATE_NO_WINDOW`` so a packaged GUI build
  never flashes console windows.
* PowerShell scripts are composed only by the application. No value that came
  from the user or an LLM is ever interpolated into a script.
"""

from __future__ import annotations

import json
import platform
import subprocess
from typing import Any, Sequence

from app.core.logging_setup import get_logger

logger = get_logger(__name__)

IS_WINDOWS = platform.system() == "Windows"

# Hide the console window for child processes of a windowed (GUI) build.
_CREATION_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0) if IS_WINDOWS else 0

# Make PowerShell emit UTF-8 so non-English Windows installs decode correctly.
_PS_PRELUDE = (
    "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8;"
    "$ProgressPreference='SilentlyContinue';"
)


class CommandError(Exception):
    """Raised when a read-only system command fails."""


def require_windows(tool: str) -> None:
    if not IS_WINDOWS:
        raise CommandError(
            f"{tool} requires Windows; current platform is {platform.system()}"
        )


def run_command(
    args: Sequence[str],
    *,
    timeout: float = 15.0,
    check: bool = True,
) -> str:
    """Run a command with a fixed argv and return its stdout."""
    if not args:
        raise CommandError("No command given")
    logger.debug("run command", extra={"component": "platform", "event": "run",
                                       "tool": args[0]})
    try:
        completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
            list(args),
            capture_output=True,
            timeout=timeout,
            shell=False,
            creationflags=_CREATION_FLAGS,
        )
    except FileNotFoundError as exc:
        raise CommandError(f"Executable not found: {args[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise CommandError(f"{args[0]} timed out after {timeout:g}s") from exc

    stdout = _decode(completed.stdout)
    if check and completed.returncode != 0:
        detail = _decode(completed.stderr).strip() or stdout.strip()
        raise CommandError(
            f"{args[0]} failed (exit {completed.returncode}): {detail[:500]}"
        )
    return stdout


def _decode(raw: bytes | None) -> str:
    if not raw:
        return ""
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        # Legacy console tools (ipconfig, netsh) write in the OEM code page.
        return raw.decode("oem" if IS_WINDOWS else "latin-1", errors="replace")


def run_powershell(script: str, *, timeout: float = 20.0) -> str:
    """Run an application-authored, read-only PowerShell script (Windows)."""
    require_windows("PowerShell")
    return run_command(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
         _PS_PRELUDE + script],
        timeout=timeout,
    )


def run_powershell_json(script: str, *, timeout: float = 20.0) -> list[dict[str, Any]]:
    """Run a script ending in ``ConvertTo-Json`` and return a list of objects.

    PowerShell emits nothing for an empty pipeline and a bare object (not an
    array) for a single result; both are normalised to a list here.
    """
    out = run_powershell(script, timeout=timeout).strip()
    if not out:
        return []
    try:
        parsed = json.loads(out)
    except json.JSONDecodeError as exc:
        raise CommandError(f"Unexpected PowerShell output: {out[:200]}") from exc
    if parsed is None:
        return []
    if isinstance(parsed, dict):
        return [parsed]
    if isinstance(parsed, list):
        return [p for p in parsed if isinstance(p, dict)]
    raise CommandError("Unexpected PowerShell JSON shape")


def is_admin() -> bool:
    """Whether the current process is elevated (Windows) / root (POSIX)."""
    if IS_WINDOWS:
        from app.core import winapi

        return winapi.is_user_admin()
    import os

    return hasattr(os, "geteuid") and os.geteuid() == 0
