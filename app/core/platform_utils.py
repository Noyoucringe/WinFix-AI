"""Platform helpers.

Windows-specific diagnostics rely on PowerShell / CIM. This module centralizes
platform detection and safe, read-only command execution so that:

* On non-Windows hosts (e.g. CI/Linux), Windows-only tools degrade gracefully
  instead of crashing.
* All command execution goes through a single audited helper with timeouts and
  a fixed argument list (no ``shell=True``, no string interpolation of user
  input — arguments are always passed as a list).
"""

from __future__ import annotations

import platform
import subprocess
from typing import Sequence

from app.core.logging_setup import get_logger

logger = get_logger(__name__)

IS_WINDOWS = platform.system() == "Windows"


class CommandError(Exception):
    """Raised when a read-only system command fails."""


def require_windows(tool: str) -> None:
    """Raise a clear error if not on Windows. Callers convert this into an
    ``unsupported_result`` so the engine keeps collecting evidence.
    """
    if not IS_WINDOWS:
        raise CommandError(
            f"{tool} requires Windows; current platform is {platform.system()}"
        )


def run_command(
    args: Sequence[str],
    *,
    timeout: float = 15.0,
) -> str:
    """Run a read-only command and return stdout.

    Arguments are always passed as a list (never a shell string) to avoid
    command injection. This helper is only ever called with fixed argument
    vectors built by the application, never with LLM-provided strings.
    """
    logger.debug(
        "run command",
        extra={"component": "platform", "event": "run", "tool": args[0] if args else ""},
    )
    try:
        completed = subprocess.run(  # noqa: S603 - fixed argv, no shell
            list(args),
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
        )
    except FileNotFoundError as exc:
        raise CommandError(f"Executable not found: {args[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise CommandError(f"Command timed out after {timeout}s") from exc

    if completed.returncode != 0:
        raise CommandError(
            f"Command failed (exit {completed.returncode}): "
            f"{completed.stderr.strip() or completed.stdout.strip()}"
        )
    return completed.stdout


def run_powershell(script: str, *, timeout: float = 15.0) -> str:
    """Run a read-only PowerShell script on Windows.

    ``script`` is composed entirely by the application (never by the LLM or
    the user). PowerShell is invoked with a non-interactive, restricted-ish
    profile. Returns stdout.
    """
    require_windows("PowerShell")
    args = [
        "powershell",
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        script,
    ]
    return run_command(args, timeout=timeout)
