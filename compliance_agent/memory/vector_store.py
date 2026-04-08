"""Shared vector-store helpers for the new agentic architecture."""

from __future__ import annotations

from pathlib import Path

from .. import config


class VectorStoreConfig:
    """Simple wrapper around the configured vector store path."""

    def __init__(self, path: Path | None = None):
        self.path = Path(path or config.VECTOR_STORE_PATH)
        self.path.mkdir(parents=True, exist_ok=True)
