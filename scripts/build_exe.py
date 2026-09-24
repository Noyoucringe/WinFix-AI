"""Build a standalone Windows executable (WinFix.exe) with PyInstaller.

Run on Windows:

    python -m pip install -r requirements.txt pyinstaller
    python scripts/build_exe.py

The result is ``dist/WinFix.exe``. API keys are never bundled: configuration is
read from a ``.env`` next to the executable at runtime.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENTRY = ROOT / "app" / "main.py"


def main() -> int:
    args = [
        sys.executable, "-m", "PyInstaller",
        "--name", "WinFix",
        "--onefile",
        "--windowed",
        "--noconfirm",
        "--clean",
        # Ensure lazily-imported modules are collected.
        "--collect-submodules", "app",
        "--hidden-import", "PySide6.QtWidgets",
        str(ENTRY),
    ]
    print("Running:", " ".join(args))
    return subprocess.call(args, cwd=str(ROOT))


if __name__ == "__main__":
    raise SystemExit(main())
