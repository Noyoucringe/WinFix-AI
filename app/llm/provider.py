"""LLM providers.

* ``LocalProvider`` — always available, no network: offline classifier,
  rule-based follow-up checks and the deterministic analyzer.
* ``AnthropicProvider`` (official ``anthropic`` SDK) and
  ``OpenAICompatibleProvider`` (any OpenAI-style endpoint, including Ollama and
  LM Studio running on this PC) — optional AI, configured in Settings > AI
  provider.

With AI configured the agent is AI-led: the model reads the user's own words
to pick the problem category and the first read-only checks, then decides
round by round which further read-only checks to run until it has enough
evidence (bounded by the safety validator's step limit), and writes the
explanation. Choices are constrained by JSON schemas with enums of the
allowed categories and tool names.

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
from dataclasses import dataclass, field
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


@dataclass
class Understanding:
    """What the AI took from the user's description (validated)."""

    category: Category
    restated: str = ""
    checks: list[str] = field(default_factory=list)
    reasoning: str = ""


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

    def understand(self, problem: str, candidate_tools: list[str]) -> Understanding | None:
        """AI reading of the problem; None means use the offline classifier."""
        return None

    last_reasoning: str = ""

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
    """Shared logic for AI providers. Subclasses implement ``_chat``."""

    def __init__(self, *, endpoint: str, model: str, api_key: str | None,
                 send_process_names: bool = True, send_event_excerpts: bool = False,
                 timeout: float = 45.0) -> None:
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self._api_key = api_key
        self.send_process_names = send_process_names
        self.send_event_excerpts = send_event_excerpts
        self.timeout = timeout
        self._local = LocalProvider()
        self.last_transmission = None
        self.last_reasoning = ""

    @property
    def on_this_pc(self) -> bool:
        """An AI server running on this PC (Ollama, LM Studio): nothing leaves it."""
        return (urlparse(self.endpoint).hostname or "") in ("localhost", "127.0.0.1", "::1")

    @property
    def available(self) -> bool:
        return bool(self.endpoint and self.model and (self._api_key or self.on_this_pc))

    def __repr__(self) -> str:  # never leak the key through repr/logging
        return f"{type(self).__name__}(endpoint={self.endpoint!r}, model={self.model!r})"

    @abstractmethod
    def _chat(self, system: str, user: str, schema: dict | None = None,
              max_tokens: int = 1024) -> str:
        """Return the model's text. With ``schema``, the text is a JSON object."""

    def _json(self, system: str, user: str, schema: dict, max_tokens: int = 2048) -> dict:
        text = self._chat(system, user, schema=schema, max_tokens=max_tokens)
        match = re.search(r"\{.*\}", text or "", re.DOTALL)
        if not match:
            raise LLMError("No JSON object in model output")
        data = json.loads(match.group(0))
        if not isinstance(data, dict):
            raise LLMError("Model output is not a JSON object")
        return data

    def _record(self, items: list[str]) -> None:
        if self.on_this_pc:
            return  # nothing leaves the PC; not a cloud transmission
        host = urlparse(self.endpoint).hostname
        previous = self.last_transmission
        merged = sorted(set(items) | set(previous.items if previous else []))
        self.last_transmission = CloudTransmission(sent=True, provider=self.label,
                                                   endpoint_host=host, items=merged,
                                                   at=now_utc())

    def test_connection(self) -> tuple[bool, str]:
        """Send a tiny fixed prompt (no diagnostic data) to check the settings."""
        if not self._api_key and not self.on_this_pc:
            return False, "Add an API key first."
        try:
            reply = self._chat("Reply with the single word OK.", "Connection test",
                               max_tokens=256)
        except Exception as exc:  # noqa: BLE001 - reported to the user, key never included
            return False, connection_error_message(exc)
        if not (reply or "").strip():
            return False, "The provider answered, but the reply was empty. Check the model name."
        where = "this PC" if self.on_this_pc else urlparse(self.endpoint).hostname
        return True, f"Connected to {where} using {self.model}."

    # --- understanding the problem ---------------------------------------------------
    def understand(self, problem: str, candidate_tools: list[str]) -> Understanding | None:
        if not self.available:
            return None
        from app.core.privacy import ITEM_PROBLEM, redact
        from app.core.tool_registry import get_registry

        registry = get_registry()
        tools = [t for t in candidate_tools
                 if registry.has(t) and registry.get_tool(t).read_only]
        categories = {c.value: spec.title for c, spec in knowledge.CATEGORIES.items()}
        schema = {
            "type": "object",
            "properties": {
                "category": {"type": "string", "enum": [*categories, "unknown"]},
                "restated_problem": {"type": "string"},
                "checks": {"type": "array", "items": {"type": "string", "enum": tools}},
                "reasoning": {"type": "string"},
            },
            "required": ["category", "restated_problem", "checks", "reasoning"],
            "additionalProperties": False,
        }
        system = (
            "You are the planning step of a Windows troubleshooting assistant. Read the "
            "user's description of their PC problem, pick the single best category, and "
            "choose 3-7 read-only checks that would give evidence about the likely causes. "
            "Prefer checks that measure the specific component the user mentions (for "
            "example GPU checks for graphics lag, network checks for Wi-Fi). "
            "restated_problem: one short sentence in plain English. reasoning: one or two "
            "sentences explaining which checks you picked and why. Only use category and "
            "check names from the schema.")
        user = json.dumps({
            "problem": redact(problem)[:500],
            "categories": categories,
            "available_checks": {t: registry.get_tool(t).description for t in tools},
        })
        try:
            self._record([ITEM_PROBLEM])
            data = self._json(system, user, schema)
        except Exception as exc:  # noqa: BLE001 - AI must never break planning
            logger.warning("AI understanding failed; using offline classifier",
                           extra={"component": "llm", "event": "fallback",
                                  "status": type(exc).__name__})
            return None
        try:
            category = Category(str(data.get("category")))
        except ValueError:
            category = Category.UNKNOWN
        if category == Category.UNKNOWN:
            category = knowledge.classify(problem)
        # Names are validated again by the planner's safety check.
        checks = [str(t)[:80] for t in data.get("checks") or [] if isinstance(t, str)]
        return Understanding(category=category,
                             restated=self._safe_text(data.get("restated_problem"), 200),
                             checks=checks[:MAX_REQUESTS],
                             reasoning=self._safe_text(data.get("reasoning"), 400))

    @staticmethod
    def _safe_text(value: Any, limit: int) -> str:
        text = str(value or "").strip()
        if not text or _UNSAFE_TEXT.search(text):
            return ""
        return text[:limit]

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
            "You receive the user's problem and measurements and findings from read-only "
            "diagnostics. Write a 2-3 sentence plain-text summary of what is most likely "
            "wrong and how it relates to what the user described. Base every claim on the "
            "findings; use hedged words (likely, possible). Do not invent numbers. Do not "
            "give commands, code, links or registry edits.")
        try:
            self._record(items)
            text = self._chat(system, json.dumps(payload), max_tokens=2048)
            diagnosis.summary = self._validate_summary(text)
            diagnosis.analysis_source = diagnosis.ai_status = "cloud"
        except Exception as exc:  # noqa: BLE001 - AI must never break diagnosis
            logger.warning("AI analysis failed; using local result",
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

    # --- autonomous investigation -------------------------------------------------
    def follow_up_tools(self, session, candidates: list[str]) -> list[str]:
        """Let the model decide whether more read-only checks are needed, and which."""
        self.last_reasoning = ""
        if not self.available or not candidates:
            return local_follow_ups(session, candidates)
        from app.core.privacy import build_payload
        from app.core.tool_registry import get_registry

        registry = get_registry()
        tools = [t for t in candidates if registry.has(t) and registry.get_tool(t).read_only]
        if not tools:
            return []
        interim = troubleshooting.analyze(session.plan.category, session.diagnostics)
        payload, items = build_payload(
            session.problem, session.plan.category, interim, session.diagnostics,
            include_process_names=self.send_process_names,
            include_event_excerpts=self.send_event_excerpts)
        payload["checks_already_run"] = sorted(session.diagnostics)
        schema = {
            "type": "object",
            "properties": {
                "enough_evidence": {"type": "boolean"},
                "next_checks": {"type": "array", "items": {"type": "string", "enum": tools}},
                "reasoning": {"type": "string"},
            },
            "required": ["enough_evidence", "next_checks", "reasoning"],
            "additionalProperties": False,
        }
        system = (
            "You are investigating a Windows PC problem using read-only checks. Given the "
            "user's problem and the evidence so far, decide whether the likely cause is "
            "already clear (enough_evidence=true, next_checks empty) or which 1-3 further "
            "checks from available_checks would best confirm or rule out a cause. "
            "reasoning: one sentence a user can read, e.g. 'GPU usage is normal, so checking "
            "for display driver crashes next.'")
        user = json.dumps({"evidence": payload,
                           "available_checks": {t: registry.get_tool(t).description
                                                for t in tools}})
        try:
            self._record(items)
            data = self._json(system, user, schema)
        except Exception as exc:  # noqa: BLE001
            logger.warning("AI tool selection failed; using local rules",
                           extra={"component": "llm", "event": "fallback",
                                  "status": type(exc).__name__})
            return local_follow_ups(session, candidates)
        self.last_reasoning = self._safe_text(data.get("reasoning"), 300)
        if data.get("enough_evidence") is True:
            return []
        names = data.get("next_checks")
        if not isinstance(names, list):
            return []
        # Everything (bounded) goes back so the agent validates and logs each request.
        return [str(t).strip()[:80] for t in names if isinstance(t, str)][:MAX_REQUESTS]


def connection_error_message(exc: Exception) -> str:
    """A user-facing explanation that never echoes request headers or keys."""
    status = getattr(exc, "status_code", None) or \
        getattr(getattr(exc, "response", None), "status_code", None)
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
        return ("Couldn't reach the endpoint. Check the address and your internet "
                "connection (for a local AI model, check that Ollama or LM Studio is "
                "running).")
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
    """OpenAI-style chat completions: OpenAI, compatible services, and local AI
    servers such as Ollama and LM Studio (no key needed on this PC)."""

    name = "openai"
    label = "OpenAI-compatible"

    def _chat(self, system: str, user: str, schema: dict | None = None,
              max_tokens: int = 1024) -> str:  # pragma: no cover - network
        import httpx

        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        body: dict[str, Any] = {
            "model": self.model, "temperature": 0.2, "max_tokens": max_tokens,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}]}
        if schema:
            body["response_format"] = {"type": "json_schema", "json_schema": {
                "name": "answer", "schema": schema, "strict": True}}
        response = httpx.post(f"{self.endpoint}/chat/completions", headers=headers,
                              json=body, timeout=self.timeout)
        if schema and response.status_code == 400:
            # Older servers without structured outputs: the prompt still asks for JSON.
            body.pop("response_format")
            body["messages"][0]["content"] += (
                " Reply with only a JSON object matching this schema: " + json.dumps(schema))
            response = httpx.post(f"{self.endpoint}/chat/completions", headers=headers,
                                  json=body, timeout=self.timeout)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"] or ""


# Models that accept output_config.effort, and the ones that support the
# server-side refusal fallback (routes a declined request to another model).
_EFFORT_MODELS = ("claude-opus-5", "claude-opus-4-8", "claude-opus-4-7", "claude-opus-4-6",
                  "claude-sonnet-5", "claude-sonnet-4-6", "claude-fable-5")
_FALLBACK_MODELS = ("claude-opus-5", "claude-fable-5-1")
_ANTHROPIC_HOST = "api.anthropic.com"


class AnthropicProvider(CloudProvider):
    """Claude via the official ``anthropic`` Python SDK."""

    name = "anthropic"
    label = "Anthropic (Claude)"

    def _client(self):
        import anthropic

        kwargs: dict[str, Any] = {"api_key": self._api_key, "timeout": self.timeout,
                                  "max_retries": 1}
        base = self.endpoint[:-3] if self.endpoint.endswith("/v1") else self.endpoint
        if urlparse(base).hostname != _ANTHROPIC_HOST:
            kwargs["base_url"] = base  # an Anthropic-compatible gateway
        return anthropic.Anthropic(**kwargs)

    def _chat(self, system: str, user: str, schema: dict | None = None,
              max_tokens: int = 1024) -> str:  # pragma: no cover - network
        import anthropic

        client = self._client()
        params: dict[str, Any] = {
            "model": self.model, "max_tokens": max(max_tokens, 1024), "system": system,
            "messages": [{"role": "user", "content": user}]}
        output_config: dict[str, Any] = {}
        if self.model.startswith(_EFFORT_MODELS):
            output_config["effort"] = "low"  # small, well-specified decisions
        if schema:
            output_config["format"] = {"type": "json_schema", "schema": schema}
        if output_config:
            params["output_config"] = output_config
        official = urlparse(self.endpoint).hostname == _ANTHROPIC_HOST
        try:
            if official and self.model in _FALLBACK_MODELS:
                response = client.beta.messages.create(
                    **params, betas=["server-side-fallback-2026-07-01"], fallbacks="default")
            else:
                response = client.messages.create(**params)
        except anthropic.BadRequestError:
            if not output_config:
                raise
            # An older model or gateway without these options: ask plainly once.
            params.pop("output_config")
            if schema:
                params["system"] += (" Reply with only a JSON object matching this schema: "
                                     + json.dumps(schema))
            response = client.messages.create(**params)
        if response.stop_reason == "refusal":
            raise LLMError("The model declined the request")
        return "".join(b.text for b in response.content if b.type == "text")


def get_provider(settings=None) -> LLMProvider:
    """The provider selected in Settings (or via environment for development)."""
    from app.core import credentials
    from app.core.config import get_settings
    from app.core.user_settings import (
        DEFAULT_ENDPOINTS,
        DEFAULT_LOCAL_ENDPOINT,
        DEFAULT_LOCAL_MODEL,
        DEFAULT_MODELS,
        get_store,
    )

    user = settings or get_store().load()
    env = get_settings()
    analysis, provider_type = user.analysis, user.provider_type
    if analysis == "local" and env.llm_provider.lower() in ("openai", "anthropic"):
        analysis, provider_type = "cloud", env.llm_provider.lower()
    if analysis == "local_ai":
        return OpenAICompatibleProvider(
            endpoint=user.local_endpoint or DEFAULT_LOCAL_ENDPOINT,
            model=user.local_model or DEFAULT_LOCAL_MODEL, api_key=None,
            send_process_names=user.send_process_names,
            send_event_excerpts=user.send_event_excerpts,
            timeout=max(env.llm_timeout_seconds, 90.0))  # local models can be slow
    if analysis != "cloud":
        return LocalProvider()
    cls = AnthropicProvider if provider_type == "anthropic" else OpenAICompatibleProvider
    same = user.provider_type == provider_type
    model = user.model if same and user.model else \
        (env.model_name or DEFAULT_MODELS[provider_type])
    endpoint = user.endpoint if same and user.endpoint else DEFAULT_ENDPOINTS[provider_type]
    return cls(endpoint=endpoint, model=model,
               api_key=credentials.get_api_key(provider_type),
               send_process_names=user.send_process_names,
               send_event_excerpts=user.send_event_excerpts,
               timeout=max(env.llm_timeout_seconds, 45.0))
