"""Dedicated LLM client for orchestrator planning decisions."""

from __future__ import annotations

import logging

from compliance_agent.config import (
    ORCHESTRATOR_API_KEY,
    ORCHESTRATOR_BASE_URL,
    ORCHESTRATOR_LLM_PROVIDER,
    ORCHESTRATOR_MAX_TOKENS,
    ORCHESTRATOR_MODEL,
    ORCHESTRATOR_TEMPERATURE,
)
from compliance_agent.llm.ollama import OllamaProvider
from compliance_agent.llm.openai_compat import OpenAICompatProvider
from compliance_agent.llm.provider import LLMProvider, LLMRequest

logger = logging.getLogger(__name__)

_cached_provider: LLMProvider | None = None


def get_orchestrator_provider() -> LLMProvider:
    """Build and cache the dedicated orchestrator provider."""
    global _cached_provider
    if _cached_provider is None:
        if ORCHESTRATOR_LLM_PROVIDER == "ollama":
            _cached_provider = OllamaProvider(
                model=ORCHESTRATOR_MODEL,
                base_url=ORCHESTRATOR_BASE_URL,
            )
        else:
            _cached_provider = OpenAICompatProvider(
                api_key=ORCHESTRATOR_API_KEY,
                model=ORCHESTRATOR_MODEL,
                base_url=ORCHESTRATOR_BASE_URL,
            )
    return _cached_provider


async def plan_next_action(system_prompt: str, state_summary: str) -> str:
    """Ask the orchestrator LLM what to do next. Returns raw LLM text."""
    provider = get_orchestrator_provider()
    if not provider.is_available():
        raise RuntimeError(
            "Orchestrator planner LLM is not configured. "
            "Set ORCHESTRATOR_API_KEY, DEEPINFRA_API_KEY, or use LLM_PROVIDER=ollama."
        )

    request = LLMRequest(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": state_summary},
        ],
        model=ORCHESTRATOR_MODEL,
        temperature=ORCHESTRATOR_TEMPERATURE,
        max_tokens=ORCHESTRATOR_MAX_TOKENS,
    )

    response = await provider.complete(request)
    logger.info("Orchestrator LLM plan response: %s", (response.content or "")[:200])
    return response.content
