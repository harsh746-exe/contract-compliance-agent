"""Structured JSON-first state models for the agentic workflow engine."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> str:
    """Return a simple ISO timestamp for persisted workflow state."""
    return datetime.utcnow().isoformat()


PLANNER_ACTIONS = (
    "route_documents",
    "prepare_context",
    "run_compliance_pipeline",
    "reanalyze_low_confidence",
    "compare_with_prior_context",
    "draft_response_outline",
    "evaluate_draft",
    "rewrite_draft",
    "request_human_approval",
    "finalize_outputs",
    "stop_with_error",
)

DOCUMENT_ROLES = (
    "solicitation_or_requirement_source",
    "response_or_proposal",
    "glossary",
    "prior_proposal",
    "prior_contract",
    "amendment",
    "past_performance",
    "unknown",
)

TASK_STATUSES = ("pending", "in_progress", "completed", "failed", "blocked")
WORKFLOW_STATUSES = ("running", "awaiting_approval", "completed", "blocked")
APPROVAL_STATUSES = ("pending", "approved", "denied")
EVALUATOR_OUTCOMES = (
    "accept",
    "retry_subset",
    "branch_to_other_action",
    "request_approval",
    "terminate_blocked",
)
WORKFLOW_GOAL_TYPES = (
    "compliance_review",
    "draft_proposal",
    "comparison_review",
    "document_workflow",
)

PlannerAction = Literal[
    "route_documents",
    "prepare_context",
    "run_compliance_pipeline",
    "reanalyze_low_confidence",
    "compare_with_prior_context",
    "draft_response_outline",
    "evaluate_draft",
    "rewrite_draft",
    "request_human_approval",
    "finalize_outputs",
    "stop_with_error",
]

DocumentRole = Literal[
    "solicitation_or_requirement_source",
    "response_or_proposal",
    "glossary",
    "prior_proposal",
    "prior_contract",
    "amendment",
    "past_performance",
    "unknown",
]

TaskStatus = Literal["pending", "in_progress", "completed", "failed", "blocked"]
WorkflowStatus = Literal["running", "awaiting_approval", "completed", "blocked"]
ApprovalStatus = Literal["pending", "approved", "denied"]
EvaluatorOutcome = Literal[
    "accept",
    "retry_subset",
    "branch_to_other_action",
    "request_approval",
    "terminate_blocked",
]
WorkflowGoalType = Literal[
    "compliance_review",
    "draft_proposal",
    "comparison_review",
    "document_workflow",
]


class WorkflowModel(BaseModel):
    """Common base model for agentic workflow schemas."""

    model_config = ConfigDict(
        extra="forbid",
        from_attributes=True,
        validate_assignment=True,
        populate_by_name=True,
    )


class WorkflowGoal(WorkflowModel):
    """Top-level user goal for the agentic workflow."""

    goal_type: WorkflowGoalType = "compliance_review"
    description: str = "Run compliance review over the provided source and response documents."
    draft_requested: bool = False
    compare_requested: bool = True


class DocumentInput(WorkflowModel):
    """A user-supplied document and its interpreted workflow role."""

    path: str
    role: DocumentRole = "unknown"
    label: Optional[str] = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DocumentManifest(WorkflowModel):
    """Resolved document-role manifest for a workflow run."""

    primary_source: Optional[DocumentInput] = None
    primary_response: Optional[DocumentInput] = None
    glossary: Optional[DocumentInput] = None
    prior_context: List[DocumentInput] = Field(default_factory=list)
    unknown: List[DocumentInput] = Field(default_factory=list)
    route_notes: List[str] = Field(default_factory=list)
    ambiguous_documents: List[str] = Field(default_factory=list)


class WorkflowTask(WorkflowModel):
    """One bounded workflow action selected by the planner."""

    task_id: str
    action: PlannerAction
    status: TaskStatus
    reason: str
    required_inputs: List[str] = Field(default_factory=list)
    success_condition: str = ""
    attempt: int = Field(default=0, ge=0)
    output_summary: str = ""
    created_at: str = Field(default_factory=utc_now)


class PlannerDecision(WorkflowModel):
    """Planner-selected next step."""

    next_action: PlannerAction
    reason: str
    required_inputs: List[str] = Field(default_factory=list)
    requires_approval: bool = False
    success_condition: str = ""


class EvaluatorDecision(WorkflowModel):
    """Control-layer assessment of the last action's output."""

    outcome: EvaluatorOutcome
    reason: str
    retry_action: Optional[PlannerAction] = None
    next_action: Optional[PlannerAction] = None
    requires_approval: bool = False
    unresolved_items: List[str] = Field(default_factory=list)


class ApprovalRequest(WorkflowModel):
    """Structured human-approval checkpoint."""

    request_id: str
    reason: str
    suggested_action: PlannerAction
    context: Dict[str, Any] = Field(default_factory=dict)
    status: ApprovalStatus = "pending"
    created_at: str = Field(default_factory=utc_now)


class ApprovalDecision(WorkflowModel):
    """Human decision for a pending approval request."""

    request_id: str
    approved: bool
    rationale: str = ""
    reviewer: str = "human"
    timestamp: str = Field(default_factory=utc_now)


class WorkflowRunResult(WorkflowModel):
    """Final or paused result returned by the agentic workflow engine."""

    run_id: str
    status: WorkflowStatus
    goal: WorkflowGoal
    document_manifest: DocumentManifest
    tasks: List[WorkflowTask] = Field(default_factory=list)
    approvals: List[ApprovalRequest] = Field(default_factory=list)
    artifacts: Dict[str, str] = Field(default_factory=dict)
    review_queue: List[str] = Field(default_factory=list)
    summary: Dict[str, Any] = Field(default_factory=dict)


def workflow_model_schemas() -> Dict[str, Dict[str, Any]]:
    """Return JSON Schemas for the public control-plane models."""

    models = {
        "WorkflowGoal": WorkflowGoal,
        "DocumentInput": DocumentInput,
        "DocumentManifest": DocumentManifest,
        "WorkflowTask": WorkflowTask,
        "PlannerDecision": PlannerDecision,
        "EvaluatorDecision": EvaluatorDecision,
        "ApprovalRequest": ApprovalRequest,
        "ApprovalDecision": ApprovalDecision,
        "WorkflowRunResult": WorkflowRunResult,
    }
    return {name: model.model_json_schema() for name, model in models.items()}
