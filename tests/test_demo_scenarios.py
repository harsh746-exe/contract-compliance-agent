import io
import json
from pathlib import Path
from types import SimpleNamespace

from rich.console import Console

from compliance_agent.scenarios import find_results_json, load_scenario, scenario_output_dir
from demo import resolve_demo_args, run_mcp_mode, run_scenario_evaluation


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
        "mode": "mcp",
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
        goal=None,
        policy=None,
        response=None,
        glossary=None,
        context=[],
        output_dir=None,
        run_id=None,
        scenario_dir=str(scenario_dir),
        evaluate_only=False,
    )

    resolved = resolve_demo_args(args)

    assert resolved.goal == "compliance_review"
    assert resolved.run_id == "scenario_case"
    assert resolved.policy.endswith("source.txt")
    assert resolved.output_dir.endswith("output/demo_cases/scenario_case")


def test_run_mcp_mode_uses_scenario_output_dir(monkeypatch, tmp_path):
    scenario_dir = _write_scenario(tmp_path)
    args = resolve_demo_args(SimpleNamespace(
        goal=None,
        policy=None,
        response=None,
        glossary=None,
        context=[],
        output_dir=None,
        run_id=None,
        scenario_dir=str(scenario_dir),
        evaluate_only=False,
    ))

    captured_goal = {}

    async def fake_run(goal):
        captured_goal.update(goal)
        out_dir = Path(goal["output_dir"]) / goal["run_id"]
        out_dir.mkdir(parents=True, exist_ok=True)
        return {
            "run_id": goal["run_id"],
            "run_dir": str(out_dir),
            "outputs": {"requirements": [], "decisions": []},
            "artifacts": {"results_json": str(out_dir / "compliance_results.json")},
        }

    monkeypatch.setattr("compliance_agent.main.run", fake_run)

    run_mcp_mode(args, Console(file=io.StringIO(), force_terminal=False))

    output_dir = scenario_output_dir(args._scenario)
    assert captured_goal["run_id"] == "scenario_case"
    assert captured_goal["output_dir"] == str(output_dir.parent)


def test_run_scenario_evaluation_writes_metrics_and_report(tmp_path):
    scenario_dir = _write_scenario(tmp_path)
    args = resolve_demo_args(SimpleNamespace(
        goal=None,
        policy=None,
        response=None,
        glossary=None,
        context=[],
        output_dir=None,
        run_id=None,
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
