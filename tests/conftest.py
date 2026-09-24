"""Shared pytest fixtures.

Tests run fully offline and are platform-independent: Windows-only tools return
structured ``unsupported`` results rather than failing, and no test performs a
destructive operation.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolated_db(monkeypatch, tmp_path):
    """Point the app at a throwaway database for every test."""
    db = tmp_path / "winfix_test.db"
    monkeypatch.setenv("DATABASE_PATH", str(db))
    # Clear the settings cache so the new env var takes effect.
    from app.core.config import get_settings

    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def registry():
    from app.core.tool_registry import get_registry

    return get_registry()


@pytest.fixture
def history(tmp_path):
    from app.core.history import HistoryStore

    return HistoryStore(tmp_path / "hist.db")


@pytest.fixture
def scenario(monkeypatch):
    """Serve recorded evidence from the real registry (see tests/scenarios.py)."""
    from app.core.tool_registry import get_registry
    from tests.scenarios import ScenarioRegistry

    return ScenarioRegistry(monkeypatch, get_registry())


@pytest.fixture(autouse=True)
def _isolated_settings(tmp_path, monkeypatch):
    """Each test gets its own settings file and no stored API keys."""
    from app.core import credentials, user_settings

    user_settings.set_store(user_settings.SettingsStore(tmp_path / "settings.json"))
    monkeypatch.setattr(credentials, "_keyring", lambda: None)
    credentials._session_only.clear()
    for var in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "LLM_PROVIDER"):
        monkeypatch.delenv(var, raising=False)
    yield
    user_settings.set_store(None)
