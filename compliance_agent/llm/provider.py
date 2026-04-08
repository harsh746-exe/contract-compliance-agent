"""Provider-agnostic LLM interface."""

from __future__ import annotations

import logging
import time
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional


logger = logging.getLogger(__name__)


@dataclass
class LLMRequest:
    """Normalized chat-completion request payload."""

    messages: list[dict]
    model: str
    temperature: float = 0.2
    max_tokens: int = 2000
    response_format: Optional[dict] = None


@dataclass
class LLMResponse:
    """Provider response payload."""

    content: str
    model: str
    usage: dict = field(default_factory=dict)
    provider: str = ""
    latency_ms: float = 0.0


class LLMProvider(ABC):
    """Abstract provider interface."""

    provider_name: str = "unknown"

    @abstractmethod
    async def complete(self, request: LLMRequest) -> LLMResponse:
        """Execute a chat completion request."""

    @abstractmethod
    def is_available(self) -> bool:
        """Return whether the provider appears configured and reachable."""

    def _log_request_start(self, request: LLMRequest) -> tuple[str, float]:
        request_id = uuid.uuid4().hex[:10]
        started = time.monotonic()
        logger.info(
            "LLM call started request_id=%s provider=%s model=%s messages=%s max_tokens=%s temperature=%s response_format=%s",
            request_id,
            self.provider_name,
            request.model,
            len(request.messages),
            request.max_tokens,
            request.temperature,
            bool(request.response_format),
        )
        return request_id, started

    def _log_request_success(
        self,
        request_id: str,
        started: float,
        response: LLMResponse,
        request: LLMRequest,
    ) -> None:
        logger.info(
            "LLM call completed request_id=%s provider=%s model=%s latency_ms=%.1f usage=%s completion_chars=%s",
            request_id,
            response.provider or self.provider_name,
            response.model or request.model,
            response.latency_ms or ((time.monotonic() - started) * 1000),
            response.usage,
            len(response.content or ""),
        )

    def _log_request_error(self, request_id: str, started: float, request: LLMRequest, exc: Exception) -> None:
        logger.exception(
            "LLM call failed request_id=%s provider=%s model=%s latency_ms=%.1f error=%s",
            request_id,
            self.provider_name,
            request.model,
            (time.monotonic() - started) * 1000,
            exc,
        )
