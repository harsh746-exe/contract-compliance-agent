"""Async retry helpers for provider-backed calls."""

from __future__ import annotations

import asyncio
import socket
from typing import Awaitable, Callable, TypeVar

from .. import config

T = TypeVar("T")

try:
    import httpx
except ImportError:  # pragma: no cover - httpx is present in normal runs
    httpx = None


def _is_non_retriable(exc: Exception) -> bool:
    if isinstance(exc, socket.gaierror):
        return True
    if httpx is not None and isinstance(exc, httpx.ConnectError):
        return True
    return "nodename nor servname provided" in str(exc).lower()


async def with_retry(operation: Callable[[], Awaitable[T]]) -> T:
    """Run an async operation with exponential backoff."""
    attempt = 0
    while True:
        try:
            return await operation()
        except Exception as exc:
            attempt += 1
            if _is_non_retriable(exc) or attempt >= config.LLM_MAX_RETRIES:
                raise
            delay = config.LLM_BACKOFF_BASE ** (attempt - 1)
            await asyncio.sleep(delay)
