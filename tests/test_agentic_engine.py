import io
import json
from pathlib import Path
from types import SimpleNamespace

import config
from compliance_agent.agentic.engine import AgenticWorkflowEngine
from compliance_agent.agentic.models import (
    ApprovalDecision,
    DocumentInput,
    DocumentManifest,
    WorkflowGoal,
    WorkflowRunResult,
)
from compliance_agent.agentic.store import WorkflowStateStore
from demo import run_agentic_mode
from rich.console import Console


class FakeComplianceAgent:
    def __init__(self, review_sequences=None):
        self.review_sequences = review_sequences or [[]]
        self.calls = 0
        self.exported = []

    def process(self, policy_path, response_path, glossary_path=None, context_paths=None, run_id=None):
        review_queue = self.review_sequences[min(self.calls, len(self.review_sequences) - 1)]
        self.calls += 1
        requirement = SimpleNamespace(req_id="REQ_0001", category="reporting", requirement_text="Provide monthly status reports.")
        decision = SimpleNamespace(requirement_id="REQ_0001", label="partial" if review_queue else "compliant", confidence=0.6 if review_queue else 0.9)
        return {
            "requirements": [requirement],
            "decisions": [decision],
            "review_queue": list(review_queue),
            "summary": {"worker_calls": self.calls},
            "run_id": run_id or f"worker_{self.calls}",
        }

    def export_matrix(self, output_path):
        Path(output_path).write_text("matrix")
        self.exported.append(("matrix", output_path))

    def export_json(self, output_path):
        Path(output_path).write_text("{}")
        self.exported.append(("json", output_path))

    def export_report(self, output_path):
        Path(output_path).write_text("# report")
        self.exported.append(("report", output_path))


def _build_engine(tmp_path, fake_agent):
    return AgenticWorkflowEngine(
        compliance_agent=fake_agent,
        state_store=WorkflowStateStore(tmp_path / "workflow_state"),
    )


def test_agentic_engine_completes_primary_pair_with_optional_context(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "AGENTIC_RESULTS_DIR", tmp_path / "agentic_results")
    fake_agent = FakeComplianceAgent(review_sequences=[[]])
    engine = _build_engine(tmp_path, fake_agent)

    source = tmp_path / "client_rfp_policy.txt"
    response = tmp_path / "team_response_proposal.txt"
    prior = tmp_path / "prior_contract.txt"
    source.write_text("The vendor shall provide monthly status reports.")
    response.write_text("We provide monthly status reports.")
    prior.write_text("Prior contract covered reporting requirements.")

    result = engine.run(
        goal=WorkflowGoal(),
        documents=[
            DocumentInput(path=str(source), role="solicitation_or_requirement_source"),
            DocumentInput(path=str(response), role="response_or_proposal"),
            DocumentInput(path=str(prior), role="prior_contract"),
        ],
        run_id="agentic_complete",
    )

    assert result.status == "completed"
    assert "matrix" in result.artifacts
    assert "comparison_summary" in result.artifacts
    assert "handoff_summary" in result.artifacts
    handoff_summary = json.loads(Path(result.artifacts["handoff_summary"]).read_text())
    assert handoff_summary["safe_for_demo_handoff"] is True
    assert len(result.tasks) >= 4


def test_agentic_engine_pauses_and_resumes_for_approval(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "AGENTIC_RESULTS_DIR", tmp_path / "agentic_results")
    fake_agent = FakeComplianceAgent(review_sequences=[["REQ_0001"], ["REQ_0001"], ["REQ_0001"], []])
    state_store = WorkflowStateStore(tmp_path / "workflow_state")
    engine = AgenticWorkflowEngine(compliance_agent=fake_agent, state_store=state_store)

    source = tmp_path / "source.txt"
    response = tmp_path / "response.txt"
    source.write_text("The vendor shall provide monthly status reports.")
    response.write_text("We provide regular updates.")

    initial = engine.run(
        goal=WorkflowGoal(),
        documents=[
            DocumentInput(path=str(source), role="solicitation_or_requirement_source"),
            DocumentInput(path=str(response), role="response_or_proposal"),
        ],
        run_id="agentic_pause_resume",
    )
    assert initial.status == "awaiting_approval"
    assert initial.approvals
    assert "handoff_summary" in initial.artifacts
    paused_handoff = json.loads(Path(initial.artifacts["handoff_summary"]).read_text())
    assert paused_handoff["safe_for_demo_handoff"] is False
    assert paused_handoff["status"] == "awaiting_approval"

    resumed = engine.run(
        goal=WorkflowGoal(),
        documents=[],
        run_id="agentic_pause_resume",
        resume=True,
        approval_handler=lambda request: ApprovalDecision(
            request_id=request.request_id,
            approved=True,
            rationale="Reviewed and approved for bounded continuation.",
            reviewer="test",
        ),
    )
    assert resumed.status == "completed"


def test_agentic_demo_helper_matches_engine_result(monkeypatch, tmp_path):
    result = WorkflowRunResult(
        run_id="demo_run",
        status="completed",
        goal=WorkflowGoal(),
        document_manifest=DocumentManifest(
            primary_source=DocumentInput(path="source.txt", role="solicitation_or_requirement_source"),
            primary_response=DocumentInput(path="response.txt", role="response_or_proposal"),
            glossary=None,
            prior_context=[],
        ),
        tasks=[],
        approvals=[],
        artifacts={
            "workflow_summary": str(tmp_path / "summary.md"),
            "handoff_summary": str(tmp_path / "handoff.json"),
        },
        review_queue=[],
        summary={"planner_actions": []},
    )

    class FakeEngine:
        def run(self, **kwargs):
            self.kwargs = kwargs
            return result

    source = tmp_path / "source.txt"
    response = tmp_path / "response.txt"
    source.write_text("source")
    response.write_text("response")

    args = SimpleNamespace(
        goal="compliance_review",
        policy=str(source),
        response=str(response),
        glossary=None,
        context=[],
        run_id="demo_run",
        resume_run_id=None,
        output_dir=None,
        _scenario=None,
    )
    fake_engine = FakeEngine()
    demo_result = run_agentic_mode(
        args,
        console=Console(file=io.StringIO(), force_terminal=False),
        engine=fake_engine,
    )

    assert demo_result.run_id == result.run_id
    assert fake_engine.kwargs["goal"].goal_type == "compliance_review"
    assert len(fake_engine.kwargs["documents"]) == 2
