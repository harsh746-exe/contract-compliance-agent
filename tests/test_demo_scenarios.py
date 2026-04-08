import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from rich.console import Console

from compliance_agent.agentic import DocumentInput, DocumentManifest, WorkflowGoal, WorkflowRunResult
from compliance_agent.scenarios import find_results_json, load_scenario, scenario_output_dir
from demo import resolve_demo_args, run_agentic_mode, run_linear_mode, run_scenario_evaluation


class FakeLinearAgent:
    def __init__(self):
        self.process_calls = []
        self.export_calls = []

    def process(self, policy_path, response_path, glossary_path=None, context_paths=None, run_id=None):
        self.process_calls.append({
            "policy_path": policy_path,
            "response_path": response_path,
            "glossary_path": glossary_path,
            "context_paths": context_paths,
            "run_id": run_id,
        })
        return {
            "requirements": [SimpleNamespace(req_id="REQ_0001")],
            "decisions": [SimpleNamespace(label="compliant", confidence=0.9)],
            "review_queue": [],
            "run_id": run_id or "scenario_linear_run",
        }

    def export_matrix(self, output_path):
        Path(output_path).write_text("matrix")
        self.export_calls.append(("matrix", output_path))

    def export_json(self, output_path):
        Path(output_path).write_text(json.dumps({
            "REQ_0001": "compliant",
        }))
        self.export_calls.append(("json", output_path))

    def export_report(self, output_path):
        Path(output_path).write_text("# report")
        self.export_calls.append(("report", output_path))


def _write_scenario(tmp_path, goal="compliance_review", evaluate_after_run=True):
    scenario_dir = tmp_path / "scenario"
    scenario_dir.mkdir()
    (scenario_dir / "source.txt").write_text(
        "1. REQUIREMENTS\nThe contractor shall provide monthly status reports.\n"
    )
    (scenario_dir / "response.txt").write_text(
        "1. RESPONSE\nWe will provide monthly status reports.\n"
    )
    (scenario_dir / "prior_contract.txt").write_text(
        "1. PRIOR CONTEXT\nPrevious contract required monthly reporting.\n"
    )
    (scenario_dir / "ground_truth.json").write_text(json.dumps({
        "REQ_0001": "compliant",
        "REQ_0002": "partial",
    }))
    (scenario_dir / "scenario.json").write_text(json.dumps({
        "name": "scenario_case",
        "mode": "agentic",
        "goal": goal,
        "output_subdir": "scenario_case",
        "evaluate_after_run": evaluate_after_run,
        "ground_truth_path": "ground_truth.json",
        "documents": [
            {"path": "source.txt", "role": "solicitation_or_requirement_source"},
            {"path": "response.txt", "role": "response_or_proposal"},
            {"path": "prior_contract.txt", "role": "prior_contract"},
        ],
    }))
    return scenario_dir


def test_load_scenario_validates_and_resolves_paths(tmp_path):
    scenario_dir = _write_scenario(tmp_path)

    scenario = load_scenario(scenario_dir)

    assert scenario.name == "scenario_case"
    assert scenario.documents[0].path.endswith("source.txt")
    assert scenario.documents[1].role == "response_or_proposal"


def test_resolve_demo_args_applies_scenario_defaults(tmp_path):
    scenario_dir = _write_scenario(tmp_path)
    args = SimpleNamespace(
        mode=None,
        goal=None,
        policy=None,
        response=None,
        glossary=None,
        context=[],
        output_dir=None,
        run_id=None,
        resume_run_id=None,
        scenario_dir=str(scenario_dir),
        evaluate_only=False,
    )

    resolved = resolve_demo_args(args)

    assert resolved.mode == "mcp"
    assert resolved.goal == "compliance_review"
    assert resolved.run_id == "scenario_case"
    assert resolved.policy.endswith("source.txt")
    assert resolved.output_dir.endswith("output/demo_cases/scenario_case")


def test_run_linear_mode_uses_scenario_output_dir(tmp_path):
    scenario_dir = _write_scenario(tmp_path)
    args = resolve_demo_args(SimpleNamespace(
        mode="linear",
        goal=None,
        policy=None,
        response=None,
        glossary=None,
        context=[],
        output_dir=None,
        run_id=None,
        resume_run_id=None,
        scenario_dir=str(scenario_dir),
        evaluate_only=False,
    ))

    fake_agent = FakeLinearAgent()
    results = run_linear_mode(args, Console(file=io.StringIO(), force_terminal=False), agent=fake_agent)

    output_dir = scenario_output_dir(args._scenario)
    assert results["artifacts"]["results_json"].startswith(str(output_dir))
    assert Path(results["artifacts"]["results_json"]).exists()


def test_run_agentic_mode_materializes_scenario_artifacts(tmp_path):
    scenario_dir = _write_scenario(tmp_path, goal="draft_proposal", evaluate_after_run=False)
    args = resolve_demo_args(SimpleNamespace(
        mode=None,
        goal=None,
        policy=None,
        response=None,
        glossary=None,
        context=[],
        output_dir=None,
        run_id=None,
        resume_run_id=None,
        scenario_dir=str(scenario_dir),
        evaluate_only=False,
    ))

    source_artifact_dir = tmp_path / "agentic_source"
    source_artifact_dir.mkdir()
    workflow_summary = source_artifact_dir / "workflow_summary.md"
    draft_outline = source_artifact_dir / "draft_outline.json"
    handoff_summary = source_artifact_dir / "handoff_summary.json"
    workflow_summary.write_text("# workflow")
    draft_outline.write_text(json.dumps({"sections": []}))
    handoff_summary.write_text(json.dumps({"status": "completed"}))

    result = WorkflowRunResult(
        run_id="scenario_case",
        status="completed",
        goal=WorkflowGoal(goal_type="draft_proposal", draft_requested=True),
        document_manifest=DocumentManifest(
            primary_source=DocumentInput(path="source.txt", role="solicitation_or_requirement_source"),
            primary_response=DocumentInput(path="response.txt", role="response_or_proposal"),
        ),
        tasks=[],
        approvals=[],
        artifacts={
            "workflow_summary": str(workflow_summary),
            "draft_outline": str(draft_outline),
            "handoff_summary": str(handoff_summary),
        },
        review_queue=[],
        summary={"planner_actions": []},
    )

    class FakeEngine:
        def run(self, **kwargs):
            self.kwargs = kwargs
            return result

    demo_result = run_agentic_mode(
        args,
        console=Console(file=io.StringIO(), force_terminal=False),
        engine=FakeEngine(),
        approval_handler=lambda request: None,
    )

    output_dir = Path(args.output_dir)
    assert output_dir.joinpath("workflow_summary.md").exists()
    assert output_dir.joinpath("draft_outline.json").exists()
    assert output_dir.joinpath("handoff_summary.json").exists()
    assert demo_result.artifacts["draft_outline"].startswith(str(output_dir))


def test_run_scenario_evaluation_writes_metrics_and_report(tmp_path):
    scenario_dir = _write_scenario(tmp_path)
    args = resolve_demo_args(SimpleNamespace(
        mode=None,
        goal=None,
        policy=None,
        response=None,
        glossary=None,
        context=[],
        output_dir=None,
        run_id=None,
        resume_run_id=None,
        scenario_dir=str(scenario_dir),
        evaluate_only=True,
    ))

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    results_path = output_dir / "scenario_case_results.json"
    results_path.write_text(json.dumps({
        "metadata": {"total_requirements": 2},
        "requirements": [
            {
                "requirement": {"req_id": "REQ_0001", "requirement_text": "Provide reports."},
                "decision": {"requirement_id": "REQ_0001", "label": "compliant", "confidence": 0.9},
                "evidence": [],
            },
            {
                "requirement": {"req_id": "REQ_0002", "requirement_text": "Provide onsite support."},
                "decision": {"requirement_id": "REQ_0002", "label": "partial", "confidence": 0.7},
                "evidence": [],
            }
        ],
    }))

    evaluation_result = run_scenario_evaluation(args, Console(file=io.StringIO(), force_terminal=False))

    assert find_results_json(output_dir, "scenario_case") == results_path
    assert output_dir.joinpath("evaluation_metrics.json").exists()
    assert output_dir.joinpath("evaluation_report.md").exists()
    assert evaluation_result["metrics"]["accuracy"] == 1.0


def test_load_scenario_requires_primary_pair(tmp_path):
    scenario_dir = tmp_path / "scenario_bad"
    scenario_dir.mkdir()
    (scenario_dir / "source.txt").write_text("requirements")
    (scenario_dir / "scenario.json").write_text(json.dumps({
        "name": "bad_case",
        "mode": "agentic",
        "goal": "compliance_review",
        "documents": [
            {"path": "source.txt", "role": "solicitation_or_requirement_source"},
        ],
    }))

    with pytest.raises(ValueError, match="primary response"):
        load_scenario(scenario_dir)
