import json

import pytest
from pydantic import ValidationError

from compliance_agent.agentic import workflow_model_schemas
from compliance_agent.agentic.models import (
    ApprovalRequest,
    DocumentInput,
    DocumentManifest,
    PlannerDecision,
    WorkflowGoal,
    WorkflowTask,
)
from compliance_agent.agentic.store import WorkflowStateStore, goal_from_dict, manifest_from_dict, task_from_dict


def test_workflow_model_schemas_expose_bounded_action_and_role_vocabularies():
    schemas = workflow_model_schemas()

    assert "WorkflowGoal" in schemas
    assert "PlannerDecision" in schemas
    assert "DocumentInput" in schemas

    serialized = json.dumps(schemas, sort_keys=True)
    assert "route_documents" in serialized
    assert "rewrite_draft" in serialized
    assert "solicitation_or_requirement_source" in serialized
    assert "past_performance" in serialized


def test_document_input_rejects_invalid_confidence():
    with pytest.raises(ValidationError):
        DocumentInput(path="sample.pdf", confidence=1.5)


def test_planner_decision_rejects_unknown_action():
    with pytest.raises(ValidationError):
        PlannerDecision(next_action="invent_new_tool", reason="not allowed")


def test_state_store_serializes_and_hydrates_json_models(tmp_path):
    store = WorkflowStateStore(tmp_path)

    goal = WorkflowGoal()
    source = DocumentInput(path="source.docx", role="solicitation_or_requirement_source", confidence=0.9)
    response = DocumentInput(path="response.docx", role="response_or_proposal", confidence=0.92)
    manifest = DocumentManifest(primary_source=source, primary_response=response)
    task = WorkflowTask(
        task_id="TASK_0001",
        action="route_documents",
        status="completed",
        reason="Documents were routed.",
    )
    approval = ApprovalRequest(
        request_id="APR_0001",
        reason="Routing ambiguity detected.",
        suggested_action="request_human_approval",
    )

    state = {
        "goal": goal,
        "documents": [source, response],
        "document_manifest": manifest,
        "tasks": [task],
        "approval_requests": [approval],
    }

    store.save_state("run_001", state)
    loaded = store.load_state("run_001")

    assert loaded["goal"]["goal_type"] == "compliance_review"
    assert loaded["document_manifest"]["primary_source"]["path"] == "source.docx"
    assert loaded["tasks"][0]["action"] == "route_documents"

    assert goal_from_dict(loaded["goal"]).goal_type == goal.goal_type
    assert manifest_from_dict(loaded["document_manifest"]).primary_response.path == "response.docx"
    assert task_from_dict(loaded["tasks"][0]).task_id == "TASK_0001"
