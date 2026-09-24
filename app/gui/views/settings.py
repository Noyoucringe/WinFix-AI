"""Settings screen: shows current configuration (read-only, no secrets)."""

from __future__ import annotations

import platform

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from app.core.config import get_settings
from app.core.tool_registry import get_registry
from app.gui.widgets import Card, muted, section_header, title_label
from app.llm.provider import get_provider


class SettingsView(QWidget):
    back = Signal()

    def __init__(self) -> None:
        super().__init__()
        root = QVBoxLayout(self)
        root.setContentsMargins(60, 40, 60, 40)
        root.setSpacing(14)

        header = QHBoxLayout()
        header.addWidget(title_label("Settings"))
        header.addStretch(1)
        back_btn = QPushButton("Back")
        back_btn.clicked.connect(self.back.emit)
        header.addWidget(back_btn)
        root.addLayout(header)

        settings = get_settings()
        provider = get_provider()
        reg = get_registry()

        card = Card()
        card.add(section_header("Configuration"))
        card.add(muted(f"Platform: {platform.system()} {platform.release()}"))
        card.add(muted(f"LLM provider: {provider.name} "
                       f"({'available' if provider.available else 'offline'})"))
        card.add(muted(f"Model: {settings.model_name or 'default'}"))
        card.add(muted(f"Max agent steps: {settings.max_agent_steps}"))
        card.add(muted(f"Max remediation attempts: {settings.max_remediation_attempts}"))
        card.add(muted(f"Diagnostic tools: {len(reg.list_tools(read_only=True))}"))
        card.add(muted(f"Remediation tools: {len(reg.list_tools(read_only=False))}"))
        root.addWidget(card)

        note = Card()
        note.add(section_header("Configuring the AI backend"))
        note.add(muted(
            "Set LLM_PROVIDER, OPENAI_API_KEY / ANTHROPIC_API_KEY and MODEL_NAME "
            "in a .env file. API keys are never stored in this app or logged. "
            "WinFix works fully offline using local diagnostics if no AI backend "
            "is configured."
        ))
        root.addWidget(note)
        root.addStretch(1)
