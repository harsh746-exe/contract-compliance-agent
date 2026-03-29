from compliance_agent.agentic.models import DocumentInput, DocumentManifest, WorkflowGoal
from compliance_agent.agentic.planner import ALLOWED_ACTIONS, WorkflowPlanner


def test_planner_emits_allowed_action():
    planner = WorkflowPlanner()
    state = {
        "status": "running",
        "document_manifest": None,
        "review_queue": [],
        "unresolved_risks": [],
        "worker_results": None,
        "comparison_summary": None,
        "draft_bundle": None,
        "draft_evaluation": None,
        "pending_approval_request": None,
        "action_attempts": {},
    }

    decision = planner.decide(state, WorkflowGoal())

    assert decision.next_action in ALLOWED_ACTIONS
    assert decision.next_action == "route_documents"


def test_planner_chooses_reanalysis_for_low_confidence_items():
    planner = WorkflowPlanner()
    state = {
        "status": "running",
        "document_manifest": DocumentManifest(
            primary_source=DocumentInput(path="policy.pdf", role="solicitation_or_requirement_source"),
            primary_response=DocumentInput(path="response.docx", role="response_or_proposal"),
        ),
        "context_prepared": True,
        "comparison_summary": None,
        "worker_results": {"run_id": "worker"},
        "review_queue": ["REQ_0001"],
        "unresolved_risks": ["REQ_0001"],
        "draft_bundle": None,
        "draft_evaluation": None,
        "pending_approval_request": None,
        "action_attempts": {"reanalyze_low_confidence": 0},
    }

    decision = planner.decide(state, WorkflowGoal())

    assert decision.next_action == "reanalyze_low_confidence"
    assert decision.required_inputs == ["REQ_0001"]
