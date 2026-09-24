"""Structured logging for WinFix AI.

Logs are emitted as single-line JSON records so they can be parsed by tools
and are safe to ship. Secrets are never logged: callers must not pass API
keys or credentials into log ``extra`` fields.
"""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import datetime, timezone
from typing import Any

from app.core.config import get_settings

_CONFIGURED = False

# Keys that carry structured context beyond the standard LogRecord attributes.
_CONTEXT_KEYS = ("component", "event", "tool", "duration_ms", "status")

# Defense in depth: even if a secret reaches a log call by mistake, it is
# masked before anything is written.
_SECRETS = [
    (re.compile(r"(?i)\bsk-(?:ant-)?[A-Za-z0-9_\-]{12,}"), "<secret>"),
    (re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._\-]{12,}"), r"\1<secret>"),
    (re.compile(r"(?i)(x-api-key|api[_-]?key|authorization|password|passwd|token|secret)"
                r"([\"']?\s*[:=]\s*[\"']?)[^\s\"',}]+"), r"\1\2<secret>"),
]


def redact_secrets(text: str) -> str:
    for pattern, replacement in _SECRETS:
        text = pattern.sub(replacement, text)
    return text


class JsonFormatter(logging.Formatter):
    """Format log records as compact JSON lines."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": redact_secrets(record.getMessage()),
        }
        for key in _CONTEXT_KEYS:
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = redact_secrets(value) if isinstance(value, str) else value
        if record.exc_info:
            payload["exception"] = redact_secrets(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging() -> None:
    """Configure the root logger once. Idempotent."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    settings = get_settings()
    settings.ensure_dirs()

    root = logging.getLogger()
    root.setLevel(settings.log_level.upper())

    formatter = JsonFormatter()

    stream = logging.StreamHandler(sys.stderr)
    stream.setFormatter(formatter)
    root.addHandler(stream)

    log_file = settings.logs_dir / "winfix.log"
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)

    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a configured logger for ``name``."""
    setup_logging()
    return logging.getLogger(name)
