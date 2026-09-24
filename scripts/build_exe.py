"""Build the standalone Windows executable (WinFix.exe).

Must be run **on Windows** — PyInstaller cannot cross-compile, so a Windows
binary cannot be produced from Linux or macOS.

    py -m pip install -r requirements.txt pyinstaller
    py scripts/build_exe.py

Output: dist/WinFix.exe

CI builds the same artifact via .github/workflows/build-windows.yml.
"""

from __future__ import annotations

import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "winfix.spec"


def main() -> int:
    if platform.system() != "Windows":
        print(
            "Refusing to build: PyInstaller cannot cross-compile a Windows .exe\n"
            f"from {platform.system()}. Run this on Windows, or let the\n"
            "'Build Windows executable' GitHub Actions workflow build it for you.",
            file=sys.stderr,
        )
        return 1

    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller is not installed. Run: py -m pip install pyinstaller",
              file=sys.stderr)
        return 1

    args = [sys.executable, "-m", "PyInstaller", str(SPEC), "--noconfirm", "--clean"]
    print("Running:", " ".join(args))
    code = subprocess.call(args, cwd=str(ROOT))
    if code == 0:
        print(f"\nBuilt: {ROOT / 'dist' / 'WinFix.exe'}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
