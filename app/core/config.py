"""Application configuration.

Configuration is loaded from environment variables (and an optional ``.env``
file). Secrets such as API keys are never hard-coded and never logged.
"""

from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root (…/winfix_ai). Used when running from source.
PROJECT_ROOT = Path(__file__).resolve().parents[2]

IS_FROZEN = bool(getattr(sys, "frozen", False))


def app_dir() -> Path:
    """Directory containing the running application.

    For a PyInstaller build this is the folder holding ``WinFix.exe`` — not the
    temporary extraction directory — so a ``.env`` placed next to the
    executable is found.
    """
    if IS_FROZEN:
        return Path(sys.executable).resolve().parent
    return PROJECT_ROOT


def user_data_dir() -> Path:
    """Writable location for the database, logs, and reports.

    A frozen app must never write inside its own bundle: PyInstaller extracts
    one-file builds to a temp directory that is deleted on exit, which would
    silently discard history and logs. Use the per-user app-data folder there.
    """
    if not IS_FROZEN:
        return PROJECT_ROOT
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME")
    root = Path(base) if base else Path.home() / ".local" / "share"
    return root / "WinFixAI"


_DATA_DIR = user_data_dir()


class Settings(BaseSettings):
    """Runtime configuration for WinFix AI.

    Every field has a safe default so the application runs with no ``.env``
    present. Only LLM features require additional configuration.
    """

    model_config = SettingsConfigDict(
        # Look for a .env in the working directory and next to the executable,
        # so a packaged build can be configured without editing the bundle.
        env_file=(".env", str(app_dir() / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- LLM configuration -------------------------------------------------
    # Provider is one of: "local" (default, offline heuristic), "openai",
    # "anthropic". Cloud providers require the matching API key.
    llm_provider: str = Field(default="local")
    openai_api_key: str | None = Field(default=None)
    anthropic_api_key: str | None = Field(default=None)
    model_name: str | None = Field(default=None)
    llm_timeout_seconds: float = Field(default=30.0)

    # --- Backend -----------------------------------------------------------
    backend_url: str = Field(default="http://127.0.0.1:8000")
    api_host: str = Field(default="127.0.0.1")
    api_port: int = Field(default=8000)

    # --- Behaviour limits (safety) ----------------------------------------
    max_agent_steps: int = Field(default=10)
    max_remediation_attempts: int = Field(default=3)
    default_tool_timeout: float = Field(default=15.0)

    # --- Logging -----------------------------------------------------------
    log_level: str = Field(default="INFO")

    # --- Paths -------------------------------------------------------------
    reports_dir: Path = Field(default=_DATA_DIR / "reports")
    logs_dir: Path = Field(default=_DATA_DIR / "logs")
    database_path: Path = Field(default=_DATA_DIR / "winfix.db")

    def ensure_dirs(self) -> None:
        """Create writable directories the app relies on."""
        self.reports_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def llm_enabled(self) -> bool:
        """Whether a cloud LLM is configured. Local provider is always on."""
        provider = self.llm_provider.lower()
        if provider == "openai":
            return bool(self.openai_api_key)
        if provider == "anthropic":
            return bool(self.anthropic_api_key)
        return provider == "local"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    settings = Settings()
    settings.ensure_dirs()
    return settings
