"""Structured logging setup for the agentic system."""

from __future__ import annotations

import logging
from pathlib import Path


def configure_logging(level: int = logging.INFO, log_path: str | Path | None = None) -> None:
    """Configure a consistent logging formatter and optional file sink."""
    root = logging.getLogger()
    root.setLevel(level)

    formatter = logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
    if not root.handlers:
        stream_handler = logging.StreamHandler()
        stream_handler.setFormatter(formatter)
        root.addHandler(stream_handler)

    if log_path is None:
        return

    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    resolved = str(path.resolve())

    for handler in root.handlers:
        if isinstance(handler, logging.FileHandler) and getattr(handler, "baseFilename", None) == resolved:
            return

    file_handler = logging.FileHandler(path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    root.addHandler(file_handler)
