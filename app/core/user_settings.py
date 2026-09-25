"""User-editable settings, persisted as JSON in the per-user data folder.

Contains no secrets: API keys live in Windows Credential Manager (see
``credentials``). A corrupt settings file is backed up and replaced with
defaults instead of stopping the app from starting.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Literal
from urllib.parse import urlparse

from pydantic import BaseModel, Field, ValidationError, field_validator

from app.core.config import user_data_dir
from app.core.logging_setup import get_logger

logger = get_logger(__name__)

ProviderType = Literal["openai", "anthropic"]

DEFAULT_ENDPOINTS = {
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com",
}
DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-opus-5",
}
PROVIDER_LABELS = {
    "anthropic": "Anthropic (Claude)",
    "openai": "OpenAI-compatible",
}
# Local AI server on this PC (Ollama's OpenAI-compatible endpoint by default;
# LM Studio uses http://localhost:1234/v1).
DEFAULT_LOCAL_ENDPOINT = "http://localhost:11434/v1"
DEFAULT_LOCAL_MODEL = "llama3.1"
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


class EndpointError(ValueError):
    pass


def validate_endpoint(url: str) -> str:
    """HTTPS only — plain HTTP is allowed just for an AI server on this PC."""
    url = (url or "").strip().rstrip("/")
    if not url:
        return ""
    parsed = urlparse(url)
    if parsed.scheme not in ("https", "http") or not parsed.hostname:
        raise EndpointError("Enter a full address, for example https://api.example.com/v1")
    if parsed.scheme == "http" and parsed.hostname not in _LOCAL_HOSTS:
        raise EndpointError("Use an https:// address. Plain http is only allowed for "
                            "an AI server running on this PC.")
    if parsed.username or parsed.password:
        raise EndpointError("Don't put credentials in the address. Use the API key field.")
    return url


class UserSettings(BaseModel):
    theme: Literal["system", "light", "dark"] = "system"
    analysis: Literal["local", "local_ai", "cloud"] = "local"
    provider_type: ProviderType = "openai"
    endpoint: str = ""
    model: str = ""
    local_endpoint: str = ""
    local_model: str = ""
    send_process_names: bool = True
    send_event_excerpts: bool = False
    diagnostic_depth: Literal["quick", "standard", "thorough"] = "standard"
    notifications: bool = True
    start_with_windows: bool = False
    window: dict = Field(default_factory=dict)

    @field_validator("endpoint", "local_endpoint")
    @classmethod
    def _endpoint(cls, value: str) -> str:
        return validate_endpoint(value)

    @property
    def effective_endpoint(self) -> str:
        return self.endpoint or DEFAULT_ENDPOINTS[self.provider_type]

    @property
    def effective_model(self) -> str:
        return self.model or DEFAULT_MODELS[self.provider_type]


class SettingsStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (user_data_dir() / "settings.json")
        self._lock = threading.Lock()

    def load(self) -> UserSettings:
        with self._lock:
            if not self.path.exists():
                return UserSettings()
            try:
                return UserSettings.model_validate(
                    json.loads(self.path.read_text(encoding="utf-8")))
            except (OSError, json.JSONDecodeError, ValidationError) as exc:
                backup = self.path.with_suffix(".corrupt.json")
                try:
                    self.path.replace(backup)
                except OSError:
                    pass
                logger.error("settings file unreadable; using defaults",
                             extra={"component": "settings", "event": "corrupt",
                                    "status": type(exc).__name__})
                return UserSettings()

    def save(self, settings: UserSettings) -> None:
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(settings.model_dump_json(indent=2), encoding="utf-8")
            tmp.replace(self.path)

    def update(self, **changes) -> UserSettings:
        current = self.load()
        updated = UserSettings.model_validate({**current.model_dump(), **changes})
        self.save(updated)
        return updated


_store: SettingsStore | None = None


def get_store() -> SettingsStore:
    global _store
    if _store is None:
        _store = SettingsStore()
    return _store


def set_store(store: SettingsStore | None) -> None:
    """Swap the process-wide store (tests, demo mode)."""
    global _store
    _store = store
