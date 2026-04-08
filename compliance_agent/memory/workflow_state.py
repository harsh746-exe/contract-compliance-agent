"""Global workflow state helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .. import config


class WorkflowStateManager:
    """Persist orchestrator workflow snapshots."""

    def __init__(self, storage_dir: Path | None = None):
        self.storage_dir = Path(storage_dir or config.WORKFLOW_STATE_DIR)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def save(self, run_id: str, state: dict[str, Any]) -> Path:
        path = self.storage_dir / f"{run_id}_agentic_state.json"
        path.write_text(json.dumps(state, indent=2, default=str))
        return path
