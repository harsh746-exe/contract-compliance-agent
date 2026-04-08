"""Run-scoped persistent store for the new agentic architecture."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .. import config


class RunStore:
    """Persist run artifacts in run-scoped JSON files."""

    def __init__(self, run_id: str, storage_dir: Path | None = None):
        self.run_id = run_id
        self.storage_dir = Path(storage_dir or config.RUN_STORE_DIR) / run_id
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def write_json(self, name: str, payload: Any) -> Path:
        path = self.storage_dir / f"{name}.json"
        path.write_text(json.dumps(payload, indent=2, default=str))
        return path
