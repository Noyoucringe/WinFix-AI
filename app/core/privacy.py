"""Minimize and sanitize what may be sent to a cloud AI provider.

Local-first: nothing leaves the PC unless cloud analysis is turned on. Even
then only the categories the user allows are included, and every string is
scrubbed of user names, the computer name, profile paths, network addresses,
e-mail addresses and anything that looks like a secret.
"""

from __future__ import annotations

import getpass
import os
import re
import socket
from functools import lru_cache
from typing import Any

from app.core.models import Category, Diagnosis
from app.knowledge import evidence as ev

ITEM_MEASUREMENTS = "Measurements and findings"
ITEM_PROCESS_NAMES = "Process and service names"
ITEM_EVENTS = "Event log excerpts"

_PATTERNS = [
    (re.compile(r"(?i)\b(sk-(?:ant-)?[A-Za-z0-9_\-]{16,})"), "<secret>"),
    (re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._\-]{12,}"), r"\1<secret>"),
    (re.compile(r"(?i)\b(password|passwd|pwd|token|api[_-]?key|secret)\s*[:=]\s*\S+"),
     r"\1=<secret>"),
    (re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"), "<email>"),
    (re.compile(r"(?i)\b(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}\b"), "<mac>"),
    (re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b"), "<ip>"),
    (re.compile(r"(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b"),
     "<id>"),
    (re.compile(r"(?i)([a-z]:\\users\\)[^\\\s\"']+"), r"\1<user>"),
    (re.compile(r"(/home/|/Users/)[^/\s\"']+"), r"\1<user>"),
    (re.compile(r"\b[A-Za-z0-9+/_\-]{40,}={0,2}"), "<redacted>"),
]


@lru_cache(maxsize=1)
def _identifiers() -> tuple[str, ...]:
    values = set()
    for getter in (getpass.getuser, socket.gethostname):
        try:
            values.add(getter())
        except Exception:  # noqa: BLE001
            continue
    for var in ("USERNAME", "USER", "COMPUTERNAME", "USERDOMAIN"):
        if os.environ.get(var):
            values.add(os.environ[var])
    # Ignore very short values that would over-match ordinary words.
    return tuple(v for v in values if v and len(v) >= 3)


def redact(text: str) -> str:
    if not text:
        return ""
    for pattern, replacement in _PATTERNS:
        text = pattern.sub(replacement, text)
    for identifier in _identifiers():
        text = re.sub(re.escape(identifier), "<redacted>", text, flags=re.IGNORECASE)
    return text


def _app_names(results: dict) -> list[str]:
    return [g["display_name"] for g in ev.app_groups(results)[:10]]


def build_payload(
    problem: str,
    category: Category,
    diagnosis: Diagnosis,
    results: dict[str, Any],
    *,
    include_process_names: bool,
    include_event_excerpts: bool,
) -> tuple[dict[str, Any], list[str]]:
    """The minimal, sanitized payload for cloud analysis, and what it contains."""
    items = [ITEM_MEASUREMENTS]
    names = _app_names(results) if not include_process_names else []

    def scrub(text: str) -> str:
        text = redact(text)
        for name in names:  # hide app names unless the user allowed them
            text = text.replace(name, "an app")
        return text

    memory, cpu, disk = ev.memory(results), ev.cpu(results), ev.disk(results)
    net = ev.network(results)
    measurements = {
        "memory_percent": memory and memory["percent"],
        "cpu_percent": cpu and cpu["percent"],
        "disk_percent": disk and disk["percent"],
        "disk_free_gb": disk and disk["free_gb"],
        "router_reachable": net["gateway_reachable"],
        "dns_working": net["dns_working"],
        "internet_reachable": net["internet"],
        "restart_pending": ev.reboot_pending(results),
        "startup_app_count": ev.startup_count(results),
    }
    payload: dict[str, Any] = {
        "problem": scrub(problem)[:500],
        "category": category.value,
        "measurements": {k: v for k, v in measurements.items() if v is not None},
        "findings": [{"cause": scrub(c.cause), "detail": scrub(c.detail),
                      "confidence": round(c.confidence, 2), "severity": c.level.value}
                     for c in diagnosis.possible_causes[:6]],
    }
    if include_process_names:
        items.append(ITEM_PROCESS_NAMES)
        payload["top_apps"] = [{"name": scrub(g["display_name"]),
                                "memory_mb": g["memory_mb"],
                                "cpu_percent": g["cpu_percent"],
                                "not_responding": g.get("not_responding", False)}
                               for g in ev.app_groups(results)[:5]]
        services = {}
        for tool in ("get_important_services", "get_windows_update_status",
                     "get_network_services_status"):
            data = ev.data(results, tool) or {}
            for name, svc in (data.get("services") or {}).items():
                services[name] = svc.get("status_text")
        if services:
            payload["services"] = services
    if include_event_excerpts:
        events = []
        for tool in ("get_recent_system_errors", "get_recent_application_errors"):
            data = ev.data(results, tool) or {}
            events.extend({"source": scrub(e.get("source") or ""),
                           "message": scrub(e.get("message") or "")[:200]}
                          for e in (data.get("events") or [])[:5])
        if events:
            items.append(ITEM_EVENTS)
            payload["event_excerpts"] = events
    return payload, items
