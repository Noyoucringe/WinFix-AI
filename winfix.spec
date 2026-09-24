# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for WinFix AI.

Builds a single-file, windowed Windows executable:

    pyinstaller winfix.spec --noconfirm --clean

Output: dist/WinFix.exe
"""

import sys
from pathlib import Path

ROOT = Path(SPECPATH)
IS_WINDOWS = sys.platform == "win32"

# The icon and version resource are Windows-only. They are skipped elsewhere so
# the spec still builds on Linux/macOS for validation purposes.
ICON = ROOT / "app" / "gui" / "assets" / "winfix.ico"
VERSION_FILE = ROOT / "scripts" / "file_version_info.txt"

a = Analysis(
    [str(ROOT / "app" / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    # Bundle the icon/branding assets; branding.py resolves them via sys._MEIPASS.
    datas=[(str(ROOT / "app" / "gui" / "assets"), "app/gui/assets")],
    hiddenimports=[
        "PySide6.QtWidgets",
        "PySide6.QtGui",
        "PySide6.QtCore",
    ],
    hookspath=[],
    runtime_hooks=[],
    # Trim heavyweight Qt modules and server-only deps the desktop app never uses.
    excludes=[
        "PySide6.QtQml",
        "PySide6.QtQuick",
        "PySide6.QtQuick3D",
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.Qt3DCore",
        "PySide6.QtMultimedia",
        "PySide6.QtCharts",
        "tkinter",
        "matplotlib",
        "numpy",
        "pytest",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="WinFix",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,          # GUI app: no console window
    disable_windowed_traceback=False,
    icon=str(ICON) if ICON.exists() else None,
    version=str(VERSION_FILE) if (IS_WINDOWS and VERSION_FILE.exists()) else None,
)
