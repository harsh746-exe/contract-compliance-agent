"""Demo script for the MCP compliance agent system."""

import argparse
import asyncio
from pathlib import Path
from typing import Optional

import config
from compliance_agent.scenarios import (
    extract_linear_inputs,
    find_results_json,
    load_scenario,
    scenario_ground_truth_path,
    scenario_output_dir,
)
from evaluation import evaluate_scenario_run
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

console = Console()


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for MCP runs."""
    parser = argparse.ArgumentParser(description="Contract/Policy Compliance Agent Demo")
    parser.add_argument(
        "--goal",
        choices=["compliance_review", "draft_proposal", "full_review"],
        help="High-level workflow goal.",
    )
    parser.add_argument("--policy", help="Path to policy/contract/source document")
    parser.add_argument("--response", help="Path to response/proposal document")
    parser.add_argument("--glossary", help="Optional path to glossary/definitions document")
    parser.add_argument("--context", action="append", default=[], help="Optional prior-context document path (repeatable)")
    parser.add_argument("--output-dir", help="Output directory")
    parser.add_argument("--run-id", help="Optional run ID for tracking")
    # Backward-compatible flag used by existing demo scripts; current CLI always runs MCP mode.
    parser.add_argument("--mode", default="mcp", help=argparse.SUPPRESS)
    parser.add_argument("--scenario-dir", help="Path to a committed demo scenario directory")
    parser.add_argument("--evaluate-only", action="store_true", help="Evaluate an existing scenario run without re-running the workflow")
    return parser


def _validate_path(path_str: str, label: str) -> Path:
    path = Path(path_str)
    if not path.exists():
        raise FileNotFoundError(f"{label} file not found: {path}")
    return path


def resolve_demo_args(args):
    """Apply scenario defaults and normalize CLI arguments."""
    scenario = None
    scenario_dir = None

    if args.scenario_dir:
        scenario_dir = Path(args.scenario_dir)
        scenario = load_scenario(scenario_dir)
        linear_inputs = extract_linear_inputs(scenario.documents)

        args.goal = args.goal or scenario.goal
        args.run_id = args.run_id or scenario.effective_output_subdir
        args.output_dir = str(scenario_output_dir(scenario, args.output_dir))
        args.policy = args.policy or linear_inputs["policy"]
        args.response = args.response or linear_inputs["response"]
        args.glossary = args.glossary or linear_inputs["glossary"]
        if not args.context:
            args.context = linear_inputs["context"]
    else:
        args.goal = args.goal or "compliance_review"
        args.output_dir = args.output_dir or str(config.DEMO_CASES_DIR)

    args._scenario = scenario
    args._scenario_dir = scenario_dir
    return args


def _mcp_documents_from_args(args) -> list[dict]:
    if getattr(args, "_scenario", None):
        return [
            {
                "path": str(_validate_path(document.path, document.role)),
                "role": document.role,
                "label": document.label,
                "confidence": document.confidence,
                "metadata": document.metadata,
            }
            for document in args._scenario.documents
        ]

    if not args.policy or not args.response:
        raise ValueError("--policy and --response are required.")

    policy_path = _validate_path(args.policy, "Policy")
    response_path = _validate_path(args.response, "Response")
    documents = [
        {
            "path": str(policy_path),
            "role": "solicitation_or_requirement_source",
            "label": "Source document",
        },
        {
            "path": str(response_path),
            "role": "response_or_proposal",
            "label": "Response document",
        },
    ]

    if args.glossary:
        glossary_path = _validate_path(args.glossary, "Glossary")
        documents.append(
            {
                "path": str(glossary_path),
                "role": "glossary",
                "label": "Glossary",
            }
        )

    for index, context_path in enumerate(args.context, start=1):
        validated = _validate_path(context_path, "Context")
        documents.append(
            {
                "path": str(validated),
                "role": "prior_contract",
                "label": f"Prior context {index}",
            }
        )

    return documents


def _resolve_mcp_output_root(output_dir: Path, run_id: Optional[str]) -> Path:
    if run_id and output_dir.name == run_id:
        return output_dir.parent
    return output_dir


def run_mcp_mode(args, console: Console) -> dict:
    """Execute the MCP multi-agent compliance workflow."""
    from compliance_agent.main import run as mcp_run

    documents = _mcp_documents_from_args(args)
    output_dir = Path(args.output_dir or config.DEMO_CASES_DIR)
    output_root = _resolve_mcp_output_root(output_dir, args.run_id)
    output_root.mkdir(parents=True, exist_ok=True)

    goal = {
        "task": args.goal or "compliance_review",
        "documents": documents,
        "output_dir": str(output_root),
    }
    if args.run_id:
        goal["run_id"] = args.run_id

    console.print("[bold blue]Running MCP compliance workflow...[/bold blue]")
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        task = progress.add_task("Executing MCP multi-agent pipeline...", total=None)
        result = asyncio.run(mcp_run(goal))
        progress.update(task, completed=True)
    return result


def run_scenario_evaluation(args, console: Console):
    """Evaluate a scenario's existing results and write stable metrics artifacts."""
    scenario = getattr(args, "_scenario", None)
    scenario_dir = getattr(args, "_scenario_dir", None)

    if scenario is None or scenario_dir is None:
        raise ValueError("--evaluate-only requires --scenario-dir.")

    ground_truth_path = scenario_ground_truth_path(scenario, scenario_dir)
    if ground_truth_path is None:
        raise ValueError("Scenario does not define a ground_truth_path for evaluation.")

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    results_json = find_results_json(output_dir, args.run_id or scenario.effective_output_subdir)

    console.print("[bold blue]Running scenario evaluation...[/bold blue]")
    return evaluate_scenario_run(
        str(ground_truth_path),
        str(results_json),
        str(output_dir),
    )


def maybe_run_post_scenario_evaluation(args, console: Console):
    """Run scenario evaluation after a workflow finishes when configured."""
    scenario = getattr(args, "_scenario", None)
    if not scenario or not scenario.evaluate_after_run:
        return None

    try:
        return run_scenario_evaluation(args, console)
    except FileNotFoundError as exc:
        console.print(f"[yellow]Scenario evaluation skipped:[/yellow] {exc}")
        return None


def render_mcp_summary(result: dict, console: Console) -> None:
    """Render a concise MCP run completion summary."""
    outputs = result.get("outputs", {})
    requirements = outputs.get("requirements", []) or []
    decisions = outputs.get("decisions", []) or []
    confidence_scores = [
        float(item.get("confidence"))
        for item in decisions
        if isinstance(item, dict) and item.get("confidence") is not None
    ]
    confidence_range = (
        f"{min(confidence_scores):.2f} - {max(confidence_scores):.2f}"
        if confidence_scores
        else "n/a"
    )
    artifact_names = sorted({
        Path(path).name
        for path in (result.get("artifacts", {}) or {}).values()
        if path
    })

    console.print("\n=== MCP Compliance Run Complete ===")
    console.print(f"Run ID:           {result.get('run_id', 'unknown')}")
    console.print(f"Requirements:     {len(requirements)}")
    console.print(f"Decisions:        {len(decisions)}")
    console.print(f"Confidence range: {confidence_range}")
    console.print(f"Output folder:    {result.get('run_dir', 'unknown')}")
    console.print(
        "Artifacts:        "
        + (", ".join(artifact_names) if artifact_names else "(none)")
    )


def render_evaluation_summary(evaluation_result: dict, console: Console) -> None:
    """Render scenario evaluation summary."""
    metrics = evaluation_result["metrics"]
    calibration = metrics.get("calibration", {})

    console.print("\n[bold green]Scenario Evaluation Complete[/bold green]\n")
    summary_table = Table(title="Evaluation Summary")
    summary_table.add_column("Metric", style="cyan")
    summary_table.add_column("Value", style="magenta")
    summary_table.add_row("Accuracy", f"{metrics['accuracy']:.3f}")
    summary_table.add_row("Cohen's Kappa", f"{metrics['cohen_kappa']:.3f}")
    summary_table.add_row(
        "Calibration",
        (
            f"ECE={calibration['expected_calibration_error']:.3f}"
            if calibration.get("available")
            else "Not available"
        ),
    )
    console.print(summary_table)
    console.print("\n[bold blue]Evaluation Artifacts[/bold blue]")
    console.print(f"  - metrics: {evaluation_result['metrics_path']}")
    console.print(f"  - report: {evaluation_result['report_path']}")


def main():
    parser = build_parser()
    args = resolve_demo_args(parser.parse_args())

    if args.evaluate_only:
        evaluation_result = run_scenario_evaluation(args, console)
        render_evaluation_summary(evaluation_result, console)
        return

    result = run_mcp_mode(args, console)
    render_mcp_summary(result, console)
    evaluation_result = maybe_run_post_scenario_evaluation(args, console)
    if evaluation_result:
        render_evaluation_summary(evaluation_result, console)


if __name__ == "__main__":
    main()
