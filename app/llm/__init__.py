"""LLM provider abstraction.

The application talks to LLMs only through :class:`LLMProvider`. Providers are
selected via configuration; the ``local`` provider requires no network and no
API key so the product always works offline.
"""

from app.llm.provider import (
    LLMProvider,
    LLMResponse,
    get_provider,
)

__all__ = ["LLMProvider", "LLMResponse", "get_provider"]
