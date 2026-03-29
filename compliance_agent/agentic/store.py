"""Persistent workflow state store for agentic runs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from pydantic import BaseModel

from .. import config
from .models import (
    ApprovalRequest,
    DocumentInput,
    DocumentManifest,
    EvaluatorDecision,
    PlannerDecision,
    WorkflowGoal,
    WorkflowRunResult,
    WorkflowTask,
)


def _to_jsonable(value: Any) -> Any:
    """Recursively convert workflow models and paths to JSON-safe values."""
    if isinstance(value, BaseModel):
        return _to_jsonable(value.model_dump(mode="json"))
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "__dict__") and not isinstance(value, type):
        return _to_jsonable(vars(value))
    if isinstance(value, dict):
        return {key: _to_jsonable(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    return value


class WorkflowStateStore:
    """Stores agentic workflow snapshots separately from worker artifacts."""

    def __init__(self, storage_dir: Path = None):
        self.storage_dir = Path(storage_dir or config.WORKFLOW_STATE_DIR)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    def state_path(self, run_id: str) -> Path:
        return self.storage_dir / f"{run_id}_workflow_state.json"

    def summary_path(self, run_id: str) -> Path:
        return self.storage_dir / f"{run_id}_workflow_summary.json"

    def save_state(self, run_id: str, state: Dict[str, Any]) -> Path:
        """Persist the mutable workflow state."""
        path = self.state_path(run_id)
        path.write_text(json.dumps(_to_jsonable(state), indent=2))
        return path

    def load_state(self, run_id: str) -> Dict[str, Any]:
        """Load a saved workflow state snapshot."""
        path = self.state_path(run_id)
        if not path.exists():
            raise FileNotFoundError(f"Workflow state not found for run_id={run_id}")
        return json.loads(path.read_text())

    def save_result_summary(self, result: WorkflowRunResult) -> Path:
        """Persist a stable summary payload for the final/paused result."""
        path = self.summary_path(result.run_id)
        path.write_text(json.dumps(_to_jsonable(result), indent=2))
        return path


def document_from_dict(data: Dict[str, Any]) -> DocumentInput:
    """Hydrate a DocumentInput from JSON-loaded state."""
    return DocumentInput.model_validate(data)


def manifest_from_dict(data: Dict[str, Any]) -> DocumentManifest:
    """Hydrate a DocumentManifest from JSON-loaded state."""
    return DocumentManifest.model_validate(data)


def goal_from_dict(data: Dict[str, Any]) -> WorkflowGoal:
    """Hydrate a WorkflowGoal from JSON-loaded state."""
    return WorkflowGoal.model_validate(data)


def planner_decision_from_dict(data: Dict[str, Any]) -> PlannerDecision:
    """Hydrate a PlannerDecision from JSON-loaded state."""
    return PlannerDecision.model_validate(data)


def evaluator_decision_from_dict(data: Dict[str, Any]) -> EvaluatorDecision:
    """Hydrate an EvaluatorDecision from JSON-loaded state."""
    return EvaluatorDecision.model_validate(data)


def task_from_dict(data: Dict[str, Any]) -> WorkflowTask:
    """Hydrate a WorkflowTask from JSON-loaded state."""
    return WorkflowTask.model_validate(data)


def approval_request_from_dict(data: Dict[str, Any]) -> ApprovalRequest:
    """Hydrate an ApprovalRequest from JSON-loaded state."""
    return ApprovalRequest.model_validate(data)
