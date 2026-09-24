# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for WinFix AI.

Builds a single-file, windowed Windows executable:

    python scripts/build.py            (recommended: checks, notices, zip, hashes)
    pyinstaller WinFixAI.spec --noconfirm --clean

Output: dist/WinFixAI.exe

Nothing secret is bundled: only the ``app`` package and its assets. .env files,
settings, databases, logs, tests and reports are never collected.
"""

import sys
from pathlib import Path

ROOT = Path(SPECPATH)
ASSETS = ROOT / "app" / "gui" / "assets"
ICON = ASSETS / "winfix.ico"
VERSION_FILE = ROOT / "scripts" / "file_version_info.txt"
NOTICES = ROOT / "build" / "THIRD-PARTY-NOTICES.txt"

datas = [(str(ASSETS), "app/gui/assets")]
if NOTICES.exists():
    datas.append((str(NOTICES), "."))

a = Analysis(
    [str(ROOT / "app" / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "PySide6.QtSvg",
        # keyring picks its backend at runtime; make sure the Windows one ships.
        "keyring.backends.Windows",
        "keyring.backends.fail",
        "win32ctypes.core",
        "win32ctypes.pywin32.win32cred",
    ],
    hookspath=[],
    runtime_hooks=[],
    # The desktop app never uses the HTTP API server, test tools or heavy Qt modules.
    excludes=[
        "fastapi", "uvicorn", "starlette", "app.api",
        "pytest", "_pytest", "tests",
        "tkinter", "matplotlib", "numpy", "PIL", "setuptools", "pkg_resources",
        "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuick3D", "PySide6.QtQuickWidgets",
        "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore",
        "PySide6.QtMultimedia", "PySide6.QtCharts", "PySide6.QtPdf", "PySide6.QtNetwork",
        "PySide6.QtOpenGL", "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtDBus",
        "PySide6.QtConcurrent", "PySide6.QtXml", "PySide6.QtDesigner", "PySide6.QtHelp",
        "PySide6.QtUiTools",
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
    name="WinFixAI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,          # GUI app: no console window
    disable_windowed_traceback=False,
    icon=str(ICON),
    version=str(VERSION_FILE),
)
