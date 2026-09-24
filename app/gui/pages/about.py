"""About WinFix AI: version, what it can do, safety model, notices."""

from __future__ import annotations

import platform

import PySide6
from PySide6.QtCore import QSize, Qt, qVersion
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QLabel

from app import ENGINE_VERSION, PUBLISHER, __version__
from app.core.config import user_data_dir
from app.core.tool_registry import get_registry
from app.gui.branding import app_icon
from app.gui.icons import IconLabel
from app.gui.pages.base import AppContext, Page
from app.gui.pages.settings import open_folder
from app.gui.widgets.composite import Footnote, KeyValueTable
from app.gui.widgets.core import Button, Card, Text, hbox, vbox

NOTICES = [
    ("Qt for Python (PySide6)", "LGPL-3.0", "The Qt Company"),
    ("Fluent UI System Icons", "MIT", "Microsoft Corporation"),
    ("psutil", "BSD-3-Clause", "Giampaolo Rodola"),
    ("pydantic", "MIT", "Pydantic Services Inc."),
    ("keyring", "MIT", "Jason R. Coombs"),
    ("httpx", "BSD-3-Clause", "Encode OSS Ltd."),
]

SAFETY = [
    "Checks are read-only. WinFix looks before it changes anything.",
    "Only predefined, reviewed fixes can change your PC. There is no way to run "
    "arbitrary commands, scripts or registry edits.",
    "Every change needs your approval, shows its risk first, and is verified afterwards.",
    "AI can suggest extra read-only checks, never commands.",
]


class AboutPage(Page):
    key = nav_key = "about"

    def __init__(self, ctx: AppContext) -> None:
        super().__init__(ctx)
        logo = QLabel()
        logo.setPixmap(app_icon().pixmap(QSize(64, 64)))
        logo.setFixedSize(64, 64)
        logo.setAccessibleName("WinFix AI logo")
        self.add(hbox(logo, vbox(Text("WinFix AI", "title"),
                                 Text(f"Version {__version__} · Diagnostics engine "
                                      f"{ENGINE_VERSION}", "body", "secondary"),
                                 spacing=2), spacing=20, stretch_at=-1))
        self.add(12)
        self.add(Text("Troubleshoot Windows problems with evidence, not guesswork.",
                      "body", wrap=True))
        self.add(24)

        registry = get_registry()
        self.add(Text("Details", "body_strong"))
        self.add(8)
        details = Card(padding=(16, 6, 16, 6), spacing=0)
        table = KeyValueTable(label_width=200)
        table.add("Version", __version__)
        table.add("Publisher", PUBLISHER)
        table.add("Diagnostics engine", ENGINE_VERSION)
        table.add("Read-only checks", str(len(registry.diagnostic_names())))
        table.add("Approved fixes", str(len(registry.remediation_names())))
        table.add("Data folder", str(user_data_dir()))
        self.system_info = (f"WinFix AI {__version__} (engine {ENGINE_VERSION}); "
                            f"{platform.system()} {platform.release()} "
                            f"({platform.version()}); Python {platform.python_version()}; "
                            f"Qt {qVersion()}; PySide6 {PySide6.__version__}")
        table.add("Runtime", f"Python {platform.python_version()} · Qt {qVersion()}")
        details.add(table)
        self.add(details)
        self.add(8)
        copy = Button("Copy version info", "Standard", "copy")
        copy.clicked.connect(self._copy)
        folder = Button("Open data folder", "Standard", "folder")
        folder.clicked.connect(lambda: open_folder(user_data_dir()))
        self.add(hbox(copy, folder, spacing=8, stretch_at=-1))

        self.add(24)
        self.add(Text("How WinFix keeps your PC safe", "body_strong"))
        self.add(8)
        safety = Card(padding=(16, 14, 16, 14), spacing=10)
        for line in SAFETY:
            row = hbox(spacing=12)
            row.addWidget(IconLabel("shield_check", "accent_text", 16), 0,
                          Qt.AlignmentFlag.AlignTop)
            row.addWidget(Text(line, "body", wrap=True), 1)
            safety.add(row)
        self.add(safety)

        self.add(24)
        self.add(Text("Third-party software", "body_strong"))
        self.add(8)
        notices = Card(padding=(16, 6, 16, 6), spacing=0)
        table = KeyValueTable(label_width=240)
        for name, license_, holder in NOTICES:
            table.add(name, f"{license_} · {holder}")
        notices.add(table)
        self.add(notices)
        self.add(8)
        self.add(Footnote("Full license texts are included in THIRD-PARTY-NOTICES.txt next "
                          "to the app and in the source repository."))

    def _copy(self) -> None:
        QGuiApplication.clipboard().setText(self.system_info)
        self.ctx.notify("Copied", "Version information was copied to the clipboard.")
