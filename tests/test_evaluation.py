import json

from evaluation import BaselineAgent, ComplianceEvaluator, evaluate_scenario_run, evaluate_system


def test_evaluation_imports_are_available():
    assert callable(evaluate_system)
    assert BaselineAgent.__name__ == "BaselineAgent"


def test_evaluate_system_handles_flat_output(tmp_path):
    ground_truth_path = tmp_path / "ground_truth.json"
    system_output_path = tmp_path / "results.json"

    ground_truth_path.write_text(json.dumps({
        "REQ_0001": "compliant",
        "REQ_0002": "partial",
    }))
    system_output_path.write_text(json.dumps({
        "REQ_0001": "compliant",
        "REQ_0002": "not_addressed",
    }))

    metrics = evaluate_system(str(ground_truth_path), str(system_output_path))

    assert metrics["accuracy"] == 0.5
    assert metrics["confusion_matrix"]["partial"]["not_addressed"] == 1
    assert metrics["calibration"]["available"] is False


def test_evaluator_handles_structured_output_and_report(tmp_path, requirement_dicts, evidence_dicts, decision_dicts):
    ground_truth_path = tmp_path / "ground_truth.json"
    system_output_path = tmp_path / "results.json"
    metrics_path = tmp_path / "metrics.json"
    report_path = tmp_path / "evaluation.md"

    ground_truth_path.write_text(json.dumps({
        "REQ_0001": "compliant",
        "REQ_0002": "partial",
    }))
    system_output_path.write_text(json.dumps({
        "metadata": {"total_requirements": 2},
        "requirements": [
            {
                "requirement": requirement_dicts[0],
                "decision": decision_dicts[0],
                "evidence": [evidence_dicts[0]],
            },
            {
                "requirement": requirement_dicts[1],
                "decision": decision_dicts[1],
                "evidence": [evidence_dicts[1]],
            },
        ],
    }))

    evaluator = ComplianceEvaluator(str(ground_truth_path))
    metrics = evaluator.evaluate(str(system_output_path), str(metrics_path))
    evaluator.generate_evaluation_report(metrics, str(report_path))

    assert metrics["accuracy"] == 1.0
    assert metrics["calibration"]["available"] is True
    assert metrics_path.exists()
    assert "## Overall Metrics" in report_path.read_text()


def test_evaluate_scenario_run_writes_expected_artifacts(tmp_path, requirement_dicts, evidence_dicts, decision_dicts):
    ground_truth_path = tmp_path / "ground_truth.json"
    system_output_path = tmp_path / "results.json"
    output_dir = tmp_path / "scenario_eval"

    ground_truth_path.write_text(json.dumps({
        "REQ_0001": "compliant",
        "REQ_0002": "partial",
    }))
    system_output_path.write_text(json.dumps({
        "metadata": {"total_requirements": 2},
        "requirements": [
            {
                "requirement": requirement_dicts[0],
                "decision": decision_dicts[0],
                "evidence": [evidence_dicts[0]],
            },
            {
                "requirement": requirement_dicts[1],
                "decision": decision_dicts[1],
                "evidence": [evidence_dicts[1]],
            },
        ],
    }))

    evaluation_result = evaluate_scenario_run(
        str(ground_truth_path),
        str(system_output_path),
        str(output_dir),
    )

    assert output_dir.joinpath("evaluation_metrics.json").exists()
    assert output_dir.joinpath("evaluation_report.md").exists()
    assert evaluation_result["metrics"]["accuracy"] == 1.0
