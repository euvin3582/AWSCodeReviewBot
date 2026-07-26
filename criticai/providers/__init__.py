"""Bedrock model providers — one module per provider family."""

from criticai.providers.base import ModelProvider, detect_provider, get_provider
from criticai.providers.anthropic import AnthropicProvider
from criticai.providers.openai import OpenAIProvider
from criticai.providers.amazon import AmazonProvider

__all__ = [
    "ModelProvider",
    "detect_provider",
    "get_provider",
    "AnthropicProvider",
    "OpenAIProvider",
    "AmazonProvider",
]
