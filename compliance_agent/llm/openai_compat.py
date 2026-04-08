"""OpenAI-compatible fallback provider."""

from __future__ import annotations

import time

import httpx

from .provider import LLMProvider, LLMRequest, LLMResponse


class OpenAICompatProvider(LLMProvider):
    """Generic OpenAI-compatible HTTP provider."""
    provider_name = "openai_compat"

    def __init__(self, api_key: str, model: str, base_url: str = "https://api.openai.com/v1", timeout: float = 60.0):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )

    async def complete(self, request: LLMRequest) -> LLMResponse:
        request_id, started = self._log_request_start(request)
        start = time.monotonic()
        payload = {
            "model": request.model or self.model,
            "messages": request.messages,
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }
        if request.response_format:
            payload["response_format"] = request.response_format

        try:
            response = await self.client.post("/chat/completions", json=payload)
            response.raise_for_status()
            data = response.json()

            llm_response = LLMResponse(
                content=data["choices"][0]["message"]["content"],
                model=data.get("model", request.model or self.model),
                usage=data.get("usage", {}),
                provider=self.provider_name,
                latency_ms=(time.monotonic() - start) * 1000,
            )
            self._log_request_success(request_id, started, llm_response, request)
            return llm_response
        except Exception as exc:
            self._log_request_error(request_id, started, request, exc)
            raise

    def is_available(self) -> bool:
        return bool(self.api_key)
