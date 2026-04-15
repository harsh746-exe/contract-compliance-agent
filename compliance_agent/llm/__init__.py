"""Provider-aware LLM helpers for both async MCP agents and legacy sync workers."""

from __future__ import annotations

import logging
from typing import Optional

from .. import config
from .deepinfra import DeepInfraProvider
from .ollama import OllamaProvider
from .openai_compat import OpenAICompatProvider
from .provider import LLMProvider, LLMRequest, LLMResponse

__all__ = [
    "LLMProvider",
    "LLMRequest",
    "LLMResponse",
    "get_provider",
    "reset_provider",
    "provider_model_for_tier",
]

logger = logging.getLogger(__name__)
_cached_provider: Optional[LLMProvider] = None
_cached_provider_name: Optional[str] = None


def get_provider(preferred: Optional[str] = None) -> LLMProvider:
    """Return a cached provider instance with deterministic credential-based fallback."""
    global _cached_provider, _cached_provider_name

    provider_name = (preferred or config.LLM_PROVIDER or "deepinfra").strip().lower()
    if _cached_provider is not None and _cached_provider_name == provider_name:
        return _cached_provider

    ollama_provider = OllamaProvider(
        model=config.OLLAMA_MODEL,
        base_url=config.OLLAMA_BASE_URL,
        timeout=float(config.LLM_TIMEOUT),
    )
    deepinfra_provider = DeepInfraProvider(
        api_key=config.DEEPINFRA_API_KEY,
        base_url=config.DEEPINFRA_BASE_URL,
        timeout=float(config.LLM_TIMEOUT),
    )
    openai_provider = OpenAICompatProvider(
        api_key=config.OPENAI_API_KEY,
        model=config.OPENAI_MODEL,
        base_url=config.OPENAI_BASE_URL,
        timeout=float(config.LLM_TIMEOUT),
    )

    if provider_name == "ollama" and ollama_provider.is_available():
        logger.info("Selected LLM provider=%s model=%s", "ollama", config.LLM_MODEL)
        _cached_provider = ollama_provider
        _cached_provider_name = provider_name
        return _cached_provider
    if provider_name == "deepinfra" and deepinfra_provider.is_available():
        logger.info("Selected LLM provider=%s model=%s", "deepinfra", config.LLM_MODEL)
        _cached_provider = deepinfra_provider
        _cached_provider_name = provider_name
        return _cached_provider
    if provider_name == "openai" and openai_provider.is_available():
        logger.info("Selected LLM provider=%s model=%s", "openai", config.LLM_MODEL)
        _cached_provider = openai_provider
        _cached_provider_name = provider_name
        return _cached_provider
    if ollama_provider.is_available():
        logger.info("Preferred LLM provider '%s' unavailable; falling back to ollama", provider_name)
        _cached_provider = ollama_provider
        _cached_provider_name = provider_name
        return _cached_provider
    if deepinfra_provider.is_available():
        logger.info("Preferred LLM provider '%s' unavailable; falling back to deepinfra", provider_name)
        _cached_provider = deepinfra_provider
        _cached_provider_name = provider_name
        return _cached_provider
    if openai_provider.is_available():
        logger.info("Preferred LLM provider '%s' unavailable; falling back to openai", provider_name)
        _cached_provider = openai_provider
        _cached_provider_name = provider_name
        return _cached_provider

    logger.warning("No configured LLM provider credentials found; returning provider shell for '%s'", provider_name)
    _cached_provider = deepinfra_provider if provider_name == "deepinfra" else openai_provider
    _cached_provider_name = provider_name
    return _cached_provider


def reset_provider() -> None:
    """Reset the cached provider instance, primarily for tests."""
    global _cached_provider, _cached_provider_name
    _cached_provider = None
    _cached_provider_name = None


def provider_model_for_tier(tier: str = "standard") -> str:
    """Resolve the configured model for a skill tier."""
    return config.LLM_TIERS.get(tier, config.LLM_MODEL) or config.LLM_MODEL
