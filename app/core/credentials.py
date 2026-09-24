"""API keys, stored in Windows Credential Manager.

Keys are never written to settings files, logs, history or the executable.
``keyring`` uses Windows Credential Manager on Windows. If no credential store
is available, a key is kept in memory for the current run only and the user is
told so.
"""

from __future__ import annotations

import os
import sys

from app.core.logging_setup import get_logger

logger = get_logger(__name__)

SERVICE = "WinFix AI"
_ENV_KEYS = {"openai": "OPENAI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}
_session_only: dict[str, str] = {}


def _user(provider_type: str) -> str:
    return f"{provider_type}-api-key"


def store_name() -> str:
    return "Windows Credential Manager" if sys.platform == "win32" else "the system keyring"


def _keyring():
    try:
        import keyring

        return keyring
    except (KeyboardInterrupt, SystemExit):
        raise
    except BaseException:  # noqa: BLE001 - a broken backend must not crash the app
        return None


class _BackendFailure(Exception):
    pass


def _safe(call, *args):
    """Run a keyring call; any backend failure (including native panics that
    derive from BaseException) means 'store unavailable', never a crash."""
    try:
        return call(*args)
    except (KeyboardInterrupt, SystemExit, GeneratorExit):
        raise
    except BaseException as exc:  # noqa: BLE001 - backend bugs must not crash the app
        raise _BackendFailure(type(exc).__name__) from None


def get_api_key(provider_type: str) -> str | None:
    kr = _keyring()
    if kr is not None:
        try:
            key = _safe(kr.get_password, SERVICE, _user(provider_type))
            if key:
                return key
        except _BackendFailure as exc:
            logger.debug("credential store unavailable",
                         extra={"component": "credentials", "status": str(exc)})
    if provider_type in _session_only:
        return _session_only[provider_type]
    # Developer fallback: a key in the environment / .env. Never written anywhere.
    return os.environ.get(_ENV_KEYS.get(provider_type, "")) or None


def set_api_key(provider_type: str, key: str) -> tuple[bool, str]:
    """Save a key. Returns (persisted, message for the user)."""
    key = (key or "").strip()
    if not key:
        return False, "Enter an API key."
    kr = _keyring()
    if kr is not None:
        try:
            _safe(kr.set_password, SERVICE, _user(provider_type), key)
            _session_only.pop(provider_type, None)
            logger.info("api key saved", extra={"component": "credentials",
                                                "event": "saved"})
            return True, f"Stored in {store_name()}."
        except _BackendFailure as exc:
            logger.warning("credential store write failed",
                           extra={"component": "credentials", "status": str(exc)})
    _session_only[provider_type] = key
    return False, ("Couldn't save the key to the credential store. It will be used until "
                   "you close WinFix AI.")


def delete_api_key(provider_type: str) -> None:
    _session_only.pop(provider_type, None)
    kr = _keyring()
    if kr is not None:
        try:
            _safe(kr.delete_password, SERVICE, _user(provider_type))
        except _BackendFailure:  # nothing stored, or no store
            pass


def describe(provider_type: str) -> str:
    """'Saved key ending in 7F2A. Stored in Windows Credential Manager.'"""
    key = get_api_key(provider_type)
    if not key:
        return "No key saved."
    where = ("Used for this session only." if provider_type in _session_only
             else f"Stored in {store_name()}.")
    return f"Saved key ending in {key[-4:].upper()}. {where}"


def masked(provider_type: str) -> str:
    return "•" * 24 if get_api_key(provider_type) else ""
