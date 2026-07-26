"""Base model provider interface and provider detection/routing."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from criticai.config import Config


class ModelProvider(ABC):
    """Abstract base for all Bedrock model providers."""

    @abstractmethod
    def invoke(self, model_id: str, system_prompt: str, user_content: str) -> str:
        """Send a prompt to the model and return the response text.

        Raises on any failure (network, auth, empty response, etc.)
        so the caller can decide whether to fall back.
        """
        ...


def detect_provider(model_id: str) -> str:
    """Derive the provider name from a model ID or inference profile ID.

    Scans all dot-separated segments for known provider names, handling
    both bare model IDs ('anthropic.claude-...') and region-prefixed
    inference profiles ('us.anthropic.claude-haiku-4-5-...').
    """
    segments = model_id.split(".")
    for known in ("anthropic", "amazon", "openai"):
        if known in segments:
            return known
    return segments[0]


def get_provider(model_id: str, config: "Config") -> ModelProvider:
    """Factory: return the appropriate provider instance for a model ID."""
    from criticai.providers.anthropic import AnthropicProvider
    from criticai.providers.openai import OpenAIProvider
    from criticai.providers.amazon import AmazonProvider

    provider_name = detect_provider(model_id)

    if provider_name == "anthropic":
        return AnthropicProvider(config)
    elif provider_name == "openai":
        return OpenAIProvider(config)
    elif provider_name == "amazon":
        return AmazonProvider(config)
    else:
        raise ValueError(
            f"Unknown provider {provider_name!r} for model {model_id!r}. "
            f"Supported: anthropic, openai, amazon."
        )
