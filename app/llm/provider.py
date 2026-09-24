"""LLM providers.

* ``LocalProvider`` — always available, no network: offline classifier,
  rule-based follow-up checks and the deterministic analyzer.
* ``OpenAICompatibleProvider`` / ``AnthropicProvider`` — optional cloud
  analysis, configured in Settings > AI provider.

Everything an LLM returns is untrusted. It may only (a) name read-only tools,
which the agent validates against the registry before running, or (b) rephrase
the diagnosis summary, which is length- and content-checked. It never sees raw
diagnostics — only the sanitized payload from ``app.core.privacy``. Any
failure falls back to local analysis and the user is told so.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import Any
from urllib.parse import urlparse

from app.core.logging_setup import get_logger
from app.core.models import Category, CloudTransmission, Diagnosis, now_utc
from app.core.platform_utils import IS_WINDOWS
from app.knowledge import categories as knowledge
from app.knowledge import evidence as ev
from app.knowledge import troubleshooting

logger = get_logger(__name__)

AI_UNAVAILABLE = "AI analysis is unavailable, but local diagnostics are still available."
MAX_FOLLOW_UPS = 3
MAX_REQUESTS = 10
_UNSAFE_TEXT = re.compile(r"(?i)(```|powershell|cmd\.exe|reg\s+(add|delete)|rm\s+-rf|"
                          r"invoke-|iex\b|http[s]?://|<script)")

# Tools that only return data on Windows; never worth a step elsewhere.
_WINDOWS_ONLY = {"get_search_indexer_status", "get_unresponsive_apps",
                 "get_network_services_status", "get_pending_reboot", "get_startup_apps",
                 "get_important_services", "get_problem_devices", "get_bluetooth_devices"}


class LLMError(Exception):
    pass


class LLMProvider(ABC):
    name = "base"
    label = "Base"
    last_transmission: CloudTransmission | None = None

    @property
    @abstractmethod
    def available(self) -> bool:
        ...

    def classify(self, problem: str) -> Category:
        return knowledge.classify(problem)

    def suggest_tools(self, problem: str, category: Category,
                      candidate_tools: list[str]) -> list[str]:
        spec = knowledge.get_category_spec(category)
        if spec:
            return [t for t in spec.diagnostic_tools if t in candidate_tools]
        return []  # the planner falls back to a broad general sweep

    def follow_up_tools(self, session, candidates: list[str]) -> list[str]:
        return local_follow_ups(session, candidates)

    @abstractmethod
    def analyze(self, problem: str, category: Category,
                results: dict[str, Any]) -> Diagnosis:
        ...


def local_follow_ups(session, candidates: list[str]) -> list[str]:
    """Evidence-driven extra checks: look closer where the numbers point."""
    results = session.diagnostics
    category = session.plan.category if session.plan else Category.UNKNOWN
    wanted: list[str] = []
    memory = ev.memory(results)
    if memory and memory["percent"] >= troubleshooting.MEMORY_HIGH:
        wanted += ["get_search_indexer_status", "get_unresponsive_apps", "get_memory_details"]
    cpu = ev.cpu(results)
    if cpu and cpu["percent"] >= troubleshooting.CPU_ELEVATED:
        wanted += ["get_top_cpu_processes", "get_search_indexer_status"]
    disk = ev.disk(results)
    if disk and disk["low"]:
        wanted += ["get_reclaimable_space"]
    net = ev.network(results)
    if net["gateway_reachable"] is False:
        wanted += ["get_ip_configuration", "get_network_profile"]
    if net["dns_working"] is False:
        wanted += ["get_network_services_status"]
    if category == Category.WINDOWS_UPDATE:
        wanted += ["test_internet"]
    if not IS_WINDOWS:
        wanted = [t for t in wanted if t not in _WINDOWS_ONLY]
    return [t for t in dict.fromkeys(wanted) if t in candidates][:MAX_FOLLOW_UPS]


class LocalProvider(LLMProvider):
    """On-device analysis. Nothing leaves the PC."""

    name = "local"
    label = "Local"

    @property
    def available(self) -> bool:
        return True

    def analyze(self, problem: str, category: Category,
                results: dict[str, Any]) -> Diagnosis:
        diagnosis = troubleshooting.analyze(category, results)
        diagnosis.ai_status = "local"
        return diagnosis


class CloudProvider(LLMProvider):
    """Shared logic for HTTP providers. Subclasses implement ``_chat``."""

    def __init__(self, *, endpoint: str, model: str, api_key: str | None,
                 send_process_names: bool = True, send_event_excerpts: bool = False,
                 timeout: float = 30.0) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self._api_key = api_key
        self.send_process_names = send_process_names
        self.send_event_excerpts = send_event_excerpts
        self.timeout = timeout
        self._local = LocalProvider()
        self.last_transmission = None

    @property
    def available(self) -> bool:
        return bool(self._api_key and self.endpoint and self.model)

    def __repr__(self) -> str:  # never leak the key through repr/logging
        return f"{type(self).__name__}(endpoint={self.endpoint!r}, model={self.model!r})"

    @abstractmethod
    def _chat(self, system: str, user: str) -> str:
        ...

    def _record(self, items: list[str]) -> None:
        host = urlparse(self.endpoint).hostname
        previous = self.last_transmission
        merged = sorted(set(items) | set(previous.items if previous else []))
        self.last_transmission = CloudTransmission(sent=True, provider=self.label,
                                                   endpoint_host=host, items=merged,
                                                   at=now_utc())

    def test_connection(self) -> tuple[bool, str]:
        """Send a tiny fixed prompt (no diagnostic data) to check the settings."""
        if not self._api_key:
            return False, "Add an API key first."
        try:
            reply = self._chat("Reply with the single word OK.", "Connection test")
        except Exception as exc:  # noqa: BLE001 - reported to the user, key never included
            return False, connection_error_message(exc)
        if not (reply or "").strip():
            return False, "The provider answered, but the reply was empty. Check the model name."
        return True, f"Connected to {urlparse(self.endpoint).hostname} using {self.model}."

    # --- analysis -----------------------------------------------------------
    def analyze(self, problem: str, category: Category,
                results: dict[str, Any]) -> Diagnosis:
        diagnosis = self._local.analyze(problem, category, results)
        if not self.available:
            diagnosis.ai_status, diagnosis.ai_message = "unavailable", AI_UNAVAILABLE
            return diagnosis
        from app.core.privacy import build_payload

        payload, items = build_payload(
            problem, category, diagnosis, results,
            include_process_names=self.send_process_names,
            include_event_excerpts=self.send_event_excerpts)
        system = (
            "You explain Windows troubleshooting results to a non-technical user. "
            "You receive measurements and findings from read-only diagnostics. Write a "
            "2-3 sentence plain-text summary of what is most likely wrong. Base every "
            "claim on the findings; use hedged words (likely, possible). Do not invent "
            "numbers. Do not give commands, code, links or registry edits.")
        try:
            self._record(items)
            text = self._chat(system, json.dumps(payload))
            diagnosis.summary = self._validate_summary(text)
            diagnosis.analysis_source = diagnosis.ai_status = "cloud"
        except Exception as exc:  # noqa: BLE001 - AI must never break diagnosis
            logger.warning("cloud analysis failed; using local result",
                           extra={"component": "llm", "event": "fallback",
                                  "status": type(exc).__name__})
            diagnosis.ai_status, diagnosis.ai_message = "unavailable", AI_UNAVAILABLE
        return diagnosis

    @staticmethod
    def _validate_summary(text: str) -> str:
        text = (text or "").strip()
        if not text or len(text) > 700 or _UNSAFE_TEXT.search(text):
            raise LLMError("Summary rejected by output validation")
        return text

    # --- tool calling -------------------------------------------------------
    def follow_up_tools(self, session, candidates: list[str]) -> list[str]:
        """Let the model choose extra read-only checks from registered schemas."""
        if not self.available or not candidates:
            return local_follow_ups(session, candidates)
        from app.core.privacy import build_payload
        from app.core.tool_registry import get_registry

        registry = get_registry()
        schemas = [registry.get_tool(t).json_schema() for t in candidates
                   if registry.has(t) and registry.get_tool(t).read_only]
        interim = troubleshooting.analyze(session.plan.category, session.diagnostics)
        payload, items = build_payload(
            session.problem, session.plan.category, interim, session.diagnostics,
            include_process_names=self.send_process_names,
            include_event_excerpts=self.send_event_excerpts)
        system = (
            "You are choosing extra read-only diagnostic checks for a Windows PC. Reply "
            'with JSON only: {"tools": ["tool_name", ...]} using at most 3 names from '
            "the provided list, or an empty list if no more checks are useful.")
        user = json.dumps({"evidence": payload, "available_tools": schemas})
        try:
            self._record(items)
            # Return everything (bounded) so the agent validates and logs each
            # request; the agent enforces how many may actually run.
            return parse_tool_selection(self._chat(system, user))[:MAX_REQUESTS]
        except Exception as exc:  # noqa: BLE001
            logger.warning("cloud tool selection failed; using local rules",
                           extra={"component": "llm", "event": "fallback",
                                  "status": type(exc).__name__})
            return local_follow_ups(session, candidates)


def connection_error_message(exc: Exception) -> str:
    """A user-facing explanation that never echoes request headers or keys."""
    status = getattr(getattr(exc, "response", None), "status_code", None)
    if status in (401, 403):
        return "The provider rejected the API key."
    if status == 404:
        return "The endpoint or model wasn't found. Check the address and model name."
    if status == 429:
        return "The provider is rate limiting requests. Try again in a minute."
    if status:
        return f"The provider returned an error (HTTP {status})."
    name = type(exc).__name__
    if "Timeout" in name:
        return "The provider didn't answer in time."
    if "Connect" in name or isinstance(exc, OSError):
        return "Couldn't reach the endpoint. Check the address and your internet connection."
    return "The connection test failed."


def parse_tool_selection(text: str) -> list[str]:
    """Parse ``{"tools": [...]}`` from model output. Anything else is rejected.

    Names are returned as-is: the agent's safety validator decides whether
    each one may run.
    """
    match = re.search(r"\{.*\}", text or "", re.DOTALL)
    if not match:
        raise LLMError("No JSON object in model output")
    data = json.loads(match.group(0))
    tools = data.get("tools") if isinstance(data, dict) else None
    if not isinstance(tools, list) or not all(isinstance(t, str) for t in tools):
        raise LLMError("Model output did not contain a list of tool names")
    return [t.strip()[:80] for t in tools]


class OpenAICompatibleProvider(CloudProvider):
    name = "openai"
    label = "OpenAI-compatible"

    def _chat(self, system: str, user: str) -> str:  # pragma: no cover - network
        import httpx

        response = httpx.post(
            f"{self.endpoint}/chat/completions",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={"model": self.model, "temperature": 0.2, "max_tokens": 400,
                  "messages": [{"role": "system", "content": system},
                               {"role": "user", "content": user}]},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]


class AnthropicProvider(CloudProvider):
    name = "anthropic"
    label = "Anthropic-compatible"

    def _chat(self, system: str, user: str) -> str:  # pragma: no cover - network
        import httpx

        base = self.endpoint[:-3] if self.endpoint.endswith("/v1") else self.endpoint
        response = httpx.post(
            f"{base}/v1/messages",
            headers={"x-api-key": self._api_key or "", "anthropic-version": "2023-06-01"},
            json={"model": self.model, "max_tokens": 400, "system": system,
                  "messages": [{"role": "user", "content": user}]},
            timeout=self.timeout,
        )
        response.raise_for_status()
        return "".join(b.get("text", "") for b in response.json().get("content", [])
                       if b.get("type") == "text")


def get_provider(settings=None) -> LLMProvider:
    """The provider selected in Settings (or via environment for development)."""
    from app.core import credentials
    from app.core.config import get_settings
    from app.core.user_settings import get_store

    user = settings or get_store().load()
    env = get_settings()
    analysis, provider_type = user.analysis, user.provider_type
    if analysis == "local" and env.llm_provider.lower() in ("openai", "anthropic"):
        analysis, provider_type = "cloud", env.llm_provider.lower()
    if analysis != "cloud":
        return LocalProvider()
    cls = AnthropicProvider if provider_type == "anthropic" else OpenAICompatibleProvider
    model = user.model if user.provider_type == provider_type and user.model else \
        (env.model_name or {"openai": "gpt-4o-mini", "anthropic": "claude-sonnet-5"}[provider_type])
    endpoint = user.endpoint if user.provider_type == provider_type and user.endpoint else \
        {"openai": "https://api.openai.com/v1",
         "anthropic": "https://api.anthropic.com"}[provider_type]
    return cls(endpoint=endpoint, model=model,
               api_key=credentials.get_api_key(provider_type),
               send_process_names=user.send_process_names,
               send_event_excerpts=user.send_event_excerpts,
               timeout=env.llm_timeout_seconds)
