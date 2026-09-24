"""LLM provider interface and implementations.

Design goals:

* One abstraction (:class:`LLMProvider`) — no vendor names leak into the rest
  of the app.
* The ``local`` provider is always available and needs no network/key.
* Cloud providers *degrade gracefully*: any error (missing key, network,
  malformed response) falls back to the deterministic local analysis so the
  product never breaks because the LLM is unavailable.
* The LLM only ever *selects* tool names or *interprets* evidence. It never
  produces code to run — tool selections are validated against the registry.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.core.config import Settings, get_settings
from app.core.logging_setup import get_logger
from app.core.models import Category, Diagnosis
from app.knowledge import categories as knowledge
from app.knowledge import troubleshooting

logger = get_logger(__name__)


@dataclass
class LLMResponse:
    text: str = ""
    tool_calls: list[str] = field(default_factory=list)
    source: str = "local"


class LLMProvider(ABC):
    """Base class for all providers."""

    name = "base"

    @property
    @abstractmethod
    def available(self) -> bool:
        """Whether this provider can currently be used."""

    def classify(self, problem: str) -> Category:
        """Classify a problem into a troubleshooting category.

        Default implementation uses the offline keyword classifier. Cloud
        providers may override for better accuracy.
        """
        return knowledge.classify(problem)

    def suggest_tools(self, problem: str, category: Category,
                      candidate_tools: list[str]) -> list[str]:
        """Return the diagnostic tools relevant to the problem.

        Default: the category's declared diagnostic tools (intersected with
        what is registered). Cloud providers may refine this.
        """
        spec = knowledge.get_category_spec(category)
        if spec:
            return [t for t in spec.diagnostic_tools if t in candidate_tools]
        return candidate_tools[:6]

    @abstractmethod
    def analyze(self, problem: str, category: Category,
                results: dict[str, Any]) -> Diagnosis:
        """Interpret collected diagnostics into a diagnosis."""


class LocalProvider(LLMProvider):
    """Offline provider using deterministic heuristics. Always available."""

    name = "local"

    @property
    def available(self) -> bool:
        return True

    def analyze(self, problem: str, category: Category,
                results: dict[str, Any]) -> Diagnosis:
        return troubleshooting.analyze(category, results)


class _CloudProvider(LLMProvider):
    """Shared logic for HTTP-based cloud providers."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._local = LocalProvider()

    def _chat(self, system: str, user: str) -> str:  # pragma: no cover - network
        raise NotImplementedError

    def analyze(self, problem: str, category: Category,
                results: dict[str, Any]) -> Diagnosis:
        # Always compute the local baseline first — it is our fallback and our
        # evidence source. The LLM refines the *explanation*, not the facts.
        baseline = self._local.analyze(problem, category, results)
        if not self.available:
            return baseline
        try:
            summary = self._llm_summary(problem, category, baseline)
            if summary:
                baseline.summary = summary
                baseline.analysis_source = "llm"
        except Exception as exc:  # noqa: BLE001 - never break on LLM failure
            logger.warning(
                "LLM analysis failed; using local baseline",
                extra={"component": "llm", "event": "fallback", "status": str(exc)},
            )
        return baseline

    def _llm_summary(self, problem: str, category: Category,
                     baseline: Diagnosis) -> str:  # pragma: no cover - network
        evidence_lines = []
        for c in baseline.possible_causes[:4]:
            evidence_lines.append(f"- {c.cause} (confidence {c.confidence:.2f})")
            evidence_lines.extend(f"    * {e}" for e in c.evidence)
        system = (
            "You are a careful Windows troubleshooting assistant. Given a user "
            "problem and evidence gathered by diagnostic tools, write a concise, "
            "plain-language summary (2-3 sentences). Base every claim on the "
            "evidence. Use hedged language ('likely', 'possible'). Do NOT invent "
            "numbers. Do NOT suggest running commands."
        )
        user = (
            f"Problem: {problem}\nCategory: {category.value}\n\n"
            f"Evidence and candidate causes:\n" + "\n".join(evidence_lines)
        )
        return self._chat(system, user).strip()


class OpenAIProvider(_CloudProvider):
    name = "openai"

    @property
    def available(self) -> bool:
        return bool(self.settings.openai_api_key)

    def _chat(self, system: str, user: str) -> str:  # pragma: no cover - network
        import httpx

        model = self.settings.model_name or "gpt-4o-mini"
        resp = httpx.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {self.settings.openai_api_key}"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "temperature": 0.2,
            },
            timeout=self.settings.llm_timeout_seconds,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]


class AnthropicProvider(_CloudProvider):
    name = "anthropic"

    @property
    def available(self) -> bool:
        return bool(self.settings.anthropic_api_key)

    def _chat(self, system: str, user: str) -> str:  # pragma: no cover - network
        import httpx

        model = self.settings.model_name or "claude-sonnet-5"
        resp = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "x-api-key": self.settings.anthropic_api_key or "",
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": model,
                "max_tokens": 512,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
            timeout=self.settings.llm_timeout_seconds,
        )
        resp.raise_for_status()
        blocks = resp.json().get("content", [])
        return "".join(b.get("text", "") for b in blocks if b.get("type") == "text")


def get_provider(settings: Settings | None = None) -> LLMProvider:
    """Return the configured provider, falling back to local on any problem."""
    settings = settings or get_settings()
    provider_name = (settings.llm_provider or "local").lower()
    try:
        if provider_name == "openai":
            provider = OpenAIProvider(settings)
        elif provider_name == "anthropic":
            provider = AnthropicProvider(settings)
        else:
            provider = LocalProvider()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "provider init failed; using local",
            extra={"component": "llm", "event": "init_fallback", "status": str(exc)},
        )
        return LocalProvider()

    if not provider.available:
        logger.info(
            "configured provider unavailable; using local",
            extra={"component": "llm", "event": "unavailable"},
        )
        return LocalProvider()
    return provider
