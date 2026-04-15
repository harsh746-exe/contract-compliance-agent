"""Ollama local LLM provider (OpenAI-compatible endpoint)."""

from __future__ import annotations

import httpx

from .openai_compat import OpenAICompatProvider


class OllamaProvider(OpenAICompatProvider):
    """Local Ollama provider — no API key required."""

    provider_name = "ollama"

    def __init__(
        self,
        model: str = "",
        base_url: str = "http://localhost:11434/v1",
        timeout: float = 120.0,
    ):
        super().__init__(
            api_key="ollama",
            model=model,
            base_url=base_url,
            timeout=timeout,
        )

    def is_available(self) -> bool:
        """Check whether the Ollama server is reachable."""
        try:
            resp = httpx.get(f"{self.base_url}/models", timeout=5.0)
            return resp.status_code == 200
        except Exception:
            return False
