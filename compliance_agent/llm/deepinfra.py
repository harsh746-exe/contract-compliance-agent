"""DeepInfra OpenAI-compatible provider implementation."""

from __future__ import annotations

from .provider import LLMRequest, LLMResponse
from .openai_compat import OpenAICompatProvider


class DeepInfraProvider(OpenAICompatProvider):
    """Async DeepInfra client using the OpenAI-compatible endpoint."""
    provider_name = "deepinfra"

    def __init__(self, api_key: str, base_url: str = "https://api.deepinfra.com/v1/openai", timeout: float = 60.0):
        super().__init__(api_key=api_key, model="", base_url=base_url, timeout=timeout)

    async def complete(self, request: LLMRequest) -> LLMResponse:
        return await super().complete(request)

    def is_available(self) -> bool:
        return bool(self.api_key)
