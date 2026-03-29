"""Evaluation components."""

from pathlib import Path
from typing import Any

from .metrics import ComplianceEvaluator


def evaluate_system(
    ground_truth_path: str,
    system_output_path: str,
    output_metrics_path: str = None
):
    """Convenience helper for one-shot evaluation runs."""
    evaluator = ComplianceEvaluator(ground_truth_path)
    return evaluator.evaluate(system_output_path, output_metrics_path)


def evaluate_scenario_run(
    ground_truth_path: str,
    system_output_path: str,
    output_dir: str,
):
    """Run evaluation and write stable scenario metrics/report artifacts."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    evaluator = ComplianceEvaluator(ground_truth_path)
    metrics_path = output_path / "evaluation_metrics.json"
    report_path = output_path / "evaluation_report.md"

    metrics = evaluator.evaluate(system_output_path, str(metrics_path))
    evaluator.generate_evaluation_report(metrics, str(report_path))

    return {
        "metrics": metrics,
        "metrics_path": str(metrics_path),
        "report_path": str(report_path),
    }


def __getattr__(name: str) -> Any:
    """Lazily import optional evaluation components."""
    if name == "BaselineAgent":
        from .baseline import BaselineAgent
        return BaselineAgent
    raise AttributeError(f"module 'evaluation' has no attribute {name!r}")


__all__ = ["ComplianceEvaluator", "BaselineAgent", "evaluate_system", "evaluate_scenario_run"]
