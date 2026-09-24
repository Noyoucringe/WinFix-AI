"""Settings screen: current configuration (read-only, never shows secrets)."""

from __future__ import annotations

import platform

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QScrollArea, QVBoxLayout, QWidget

from app.core.config import get_settings
from app.core.tool_registry import get_registry
from app.gui.widgets import (
    Card,
    Pill,
    body,
    container,
    display,
    divider,
    eyebrow,
    faint,
    heading,
    muted,
    row,
)
from app.gui.theme import SUCCESS, SUCCESS_SOFT, WARN, WARN_SOFT


class SettingsView(QWidget):
    def __init__(self) -> None:
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        host = container()
        root = QVBoxLayout(host)
        root.setContentsMargins(56, 48, 56, 40)
        root.setSpacing(16)
        scroll.setWidget(host)
        outer.addWidget(scroll)

        settings = get_settings()
        reg = get_registry()
        from app.llm.provider import get_provider

        provider = get_provider()

        root.addWidget(eyebrow("SETTINGS"))
        root.addWidget(display("Configuration"))
        root.addSpacing(6)

        # AI backend
        ai = Card(spacing=10)
        online = provider.available and provider.name != "local"
        pill = (
            Pill("CLOUD AI", SUCCESS, SUCCESS_SOFT) if online
            else Pill("OFFLINE MODE", WARN, WARN_SOFT)
        )
        ai.add(row(heading("AI backend"), pill, spacing=10, stretch_at=0))
        ai.add(body(f"Provider: {provider.name}"))
        ai.add(muted(f"Model: {settings.model_name or 'provider default'}"))
        ai.add(divider())
        ai.add(faint(
            "WinFix works fully offline using local diagnostics and deterministic "
            "analysis. Configure LLM_PROVIDER and the matching API key in a .env "
            "file next to the app to enable AI-written explanations. API keys are "
            "never bundled into the executable and never logged."
        ))
        root.addWidget(ai)

        # Safety limits
        limits = Card(spacing=8)
        limits.add(heading("Safety limits"))
        limits.add(muted(f"Maximum agent steps: {settings.max_agent_steps}"))
        limits.add(muted(
            f"Maximum remediation attempts: {settings.max_remediation_attempts}"
        ))
        limits.add(muted(f"Default tool timeout: {settings.default_tool_timeout}s"))
        limits.add(divider())
        limits.add(faint(
            "Remediation always requires your explicit approval. The AI can only "
            "select from registered tools — it can never run arbitrary commands."
        ))
        root.addWidget(limits)

        # Environment
        env = Card(spacing=8)
        env.add(heading("Environment"))
        env.add(muted(f"Platform: {platform.system()} {platform.release()}"))
        env.add(muted(f"Diagnostic tools registered: {len(reg.list_tools(read_only=True))}"))
        env.add(muted(f"Remediation tools registered: {len(reg.list_tools(read_only=False))}"))
        env.add(muted(f"History database: {settings.database_path}"))
        if platform.system() != "Windows":
            env.add(divider())
            env.add(faint(
                "Windows-specific diagnostics and fixes are unavailable on this "
                "platform and will be reported as 'not available' rather than failing."
            ))
        root.addWidget(env)

        root.addStretch(1)
