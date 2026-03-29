"""Demo script for the Compliance Agent system."""

import argparse
from pathlib import Path
from typing import Optional

import config
from compliance_agent import AgenticWorkflowEngine, ComplianceAgent
from compliance_agent.agentic import ApprovalDecision, DocumentInput, WorkflowGoal
from compliance_agent.scenarios import (
    extract_linear_inputs,
    find_results_json,
    load_scenario,
    materialize_agentic_artifacts,
    scenario_ground_truth_path,
    scenario_output_dir,
)
from evaluation import evaluate_scenario_run
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

console = Console()


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI parser for linear and agentic runs."""
    parser = argparse.ArgumentParser(description="Contract/Policy Compliance Agent Demo")
    parser.add_argument("--mode", choices=["linear", "agentic"], help="Workflow mode to run")
    parser.add_argument("--goal", choices=["compliance_review", "draft_proposal", "full_review"], help="High-level workflow goal for agentic mode")
    parser.add_argument("--policy", help="Path to policy/contract/source document")
    parser.add_argument("--response", help="Path to response/proposal document")
    parser.add_argument("--glossary", help="Optional path to glossary/definitions document")
    parser.add_argument("--context", action="append", default=[], help="Optional prior-context document path (repeatable)")
    parser.add_argument("--output-dir", help="Output directory")
    parser.add_argument("--run-id", help="Optional run ID for tracking")
    parser.add_argument("--resume-run-id", help="Resume a paused agentic workflow by run ID")
    parser.add_argument("--scenario-dir", help="Path to a committed demo scenario directory")
    parser.add_argument("--evaluate-only", action="store_true", help="Evaluate an existing scenario run without re-running the workflow")
    return parser


def _validate_path(path_str: str, label: str) -> Path:
    path = Path(path_str)
    if not path.exists():
        raise FileNotFoundError(f"{label} file not found: {path}")
    return path


def _build_goal(goal_name: str) -> WorkflowGoal:
    goal_name = goal_name or "compliance_review"
    if goal_name == "draft_proposal":
        return WorkflowGoal(
            goal_type=goal_name,
            description="Run compliance review, historical comparison, and bounded drafting support.",
            draft_requested=True,
            compare_requested=True,
        )
    if goal_name == "full_review":
        return WorkflowGoal(
            goal_type=goal_name,
            description="Run the full bounded workflow including compliance review, comparison, and final handoff checks.",
            draft_requested=True,
            compare_requested=True,
        )
    return WorkflowGoal(
        goal_type=goal_name,
        description="Run compliance review over the primary source and response documents.",
        draft_requested=False,
        compare_requested=True,
    )


def _interactive_approval_handler(request) -> ApprovalDecision:
    console.print(f"\n[bold yellow]Approval required:[/bold yellow] {request.reason}")
    unresolved = request.context.get("unresolved_items", [])
    if unresolved:
        for item in unresolved[:8]:
            console.print(f"  - {item}")
    answer = console.input("Approve workflow to continue? [y/N]: ").strip().lower()
    approved = answer in {"y", "yes"}
    rationale = "Approved from CLI prompt." if approved else "Denied from CLI prompt."
    return ApprovalDecision(
        request_id=request.request_id,
        approved=approved,
        rationale=rationale,
        reviewer="cli_user",
    )


def resolve_demo_args(args):
    """Apply scenario defaults and normalize CLI arguments."""
    scenario = None
    scenario_dir = None

    if args.scenario_dir:
        scenario_dir = Path(args.scenario_dir)
        scenario = load_scenario(scenario_dir)
        linear_inputs = extract_linear_inputs(scenario.documents)

        args.mode = args.mode or scenario.mode
        args.goal = args.goal or scenario.goal
        args.run_id = args.run_id or scenario.effective_output_subdir
        args.output_dir = str(scenario_output_dir(scenario, args.output_dir))
        args.policy = args.policy or linear_inputs["policy"]
        args.response = args.response or linear_inputs["response"]
        args.glossary = args.glossary or linear_inputs["glossary"]
        if not args.context:
            args.context = linear_inputs["context"]
    else:
        args.mode = args.mode or "linear"
        args.goal = args.goal or "compliance_review"
        if args.mode == "linear":
            args.output_dir = args.output_dir or "output/results"

    args._scenario = scenario
    args._scenario_dir = scenario_dir
    return args


def run_linear_mode(args, console: Console, agent: Optional[ComplianceAgent] = None) -> dict:
    """Execute the existing linear compliance flow."""
    if not args.policy or not args.response:
        raise ValueError("--policy and --response are required in linear mode.")

    policy_path = _validate_path(args.policy, "Policy")
    response_path = _validate_path(args.response, "Response")
    glossary_path = _validate_path(args.glossary, "Glossary") if args.glossary else None
    context_paths = [str(_validate_path(path, "Context")) for path in args.context]

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    console.print("[bold blue]Initializing Compliance Agent...[/bold blue]")
    agent = agent or ComplianceAgent()

    console.print("[bold blue]Processing documents...[/bold blue]")
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        task = progress.add_task("Analyzing compliance...", total=None)
        results = agent.process(
            policy_path=str(policy_path),
            response_path=str(response_path),
            glossary_path=str(glossary_path) if glossary_path else None,
            context_paths=context_paths,
            run_id=args.run_id,
        )
        progress.update(task, completed=True)

    run_id = results["run_id"]
    csv_path = output_dir / f"{run_id}_matrix.csv"
    json_path = output_dir / f"{run_id}_results.json"
    report_path = output_dir / f"{run_id}_report.md"

    agent.export_matrix(str(csv_path))
    agent.export_json(str(json_path))
    agent.export_report(str(report_path))

    results["artifacts"] = {
        "matrix": str(csv_path),
        "results_json": str(json_path),
        "report": str(report_path),
    }
    return results


def run_agentic_mode(
    args,
    console: Console,
    engine: Optional[AgenticWorkflowEngine] = None,
    approval_handler=None,
):
    """Execute or resume the bounded agentic workflow."""
    engine = engine or AgenticWorkflowEngine()
    goal = _build_goal(args.goal)
    approval_handler = approval_handler or _interactive_approval_handler

    if args.resume_run_id:
        result = engine.run(
            goal=goal,
            documents=[],
            approval_handler=approval_handler,
            run_id=args.resume_run_id,
            resume=True,
        )
        if args.output_dir:
            result.artifacts = materialize_agentic_artifacts(result.artifacts, Path(args.output_dir))
        return result

    if getattr(args, "_scenario", None):
        documents = args._scenario.documents
    else:
        if not args.policy or not args.response:
            raise ValueError("--policy and --response are required for a new agentic workflow run.")

        policy_path = _validate_path(args.policy, "Policy")
        response_path = _validate_path(args.response, "Response")
        documents = [
            DocumentInput(path=str(policy_path), role="solicitation_or_requirement_source"),
            DocumentInput(path=str(response_path), role="response_or_proposal"),
        ]

        if args.glossary:
            documents.append(DocumentInput(
                path=str(_validate_path(args.glossary, "Glossary")),
                role="glossary",
            ))

        for context_path in args.context:
            documents.append(DocumentInput(
                path=str(_validate_path(context_path, "Context")),
                role="prior_contract",
            ))

    console.print("[bold blue]Initializing Agentic Workflow Engine...[/bold blue]")
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        task = progress.add_task("Running bounded agentic workflow...", total=None)
        result = engine.run(
            goal=goal,
            documents=documents,
            approval_handler=approval_handler,
            run_id=args.run_id,
        )
        progress.update(task, completed=True)
    if args.output_dir:
        result.artifacts = materialize_agentic_artifacts(result.artifacts, Path(args.output_dir))
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


def render_linear_summary(results: dict, console: Console) -> None:
    """Render the linear workflow summary."""
    console.print("\n[bold green]Processing Complete![/bold green]\n")
    summary_table = Table(title="Compliance Summary")
    summary_table.add_column("Metric", style="cyan")
    summary_table.add_column("Value", style="magenta")

    requirements = results["requirements"]
    decisions = results["decisions"]
    total_reqs = len(requirements)
    compliant = sum(1 for d in decisions if d.label == "compliant")
    partial = sum(1 for d in decisions if d.label == "partial")
    not_compliant = sum(1 for d in decisions if d.label == "not_compliant")
    not_addressed = sum(1 for d in decisions if d.label == "not_addressed")
    avg_confidence = sum(d.confidence for d in decisions) / len(decisions) if decisions else 0.0

    summary_table.add_row("Total Requirements", str(total_reqs))
    summary_table.add_row("Compliant", f"{compliant} ({compliant/total_reqs*100:.1f}%)" if total_reqs > 0 else "0")
    summary_table.add_row("Partial Compliance", f"{partial} ({partial/total_reqs*100:.1f}%)" if total_reqs > 0 else "0")
    summary_table.add_row("Not Compliant", f"{not_compliant} ({not_compliant/total_reqs*100:.1f}%)" if total_reqs > 0 else "0")
    summary_table.add_row("Not Addressed", f"{not_addressed} ({not_addressed/total_reqs*100:.1f}%)" if total_reqs > 0 else "0")
    summary_table.add_row("Average Confidence", f"{avg_confidence:.2f}")
    summary_table.add_row("Items for Review", str(len(results["review_queue"])))
    console.print(summary_table)

    console.print("\n[bold blue]Artifacts[/bold blue]")
    for label, path in results.get("artifacts", {}).items():
        console.print(f"  - {label}: {path}")


def render_agentic_summary(result, console: Console) -> None:
    """Render the agentic workflow summary."""
    console.print("\n[bold green]Agentic Workflow Result[/bold green]\n")
    summary_table = Table(title="Agentic Workflow Summary")
    summary_table.add_column("Metric", style="cyan")
    summary_table.add_column("Value", style="magenta")
    summary_table.add_row("Run ID", result.run_id)
    summary_table.add_row("Status", result.status)
    summary_table.add_row("Goal", result.goal.goal_type)
    summary_table.add_row("Tasks Executed", str(len(result.tasks)))
    summary_table.add_row("Review Queue", str(len(result.review_queue)))
    summary_table.add_row("Approvals Raised", str(len(result.approvals)))
    console.print(summary_table)

    if result.document_manifest:
        manifest = result.document_manifest
        console.print("[bold blue]Document Manifest[/bold blue]")
        console.print(f"  - source: {manifest.primary_source.path if manifest.primary_source else 'missing'}")
        console.print(f"  - response: {manifest.primary_response.path if manifest.primary_response else 'missing'}")
        console.print(f"  - glossary: {manifest.glossary.path if manifest.glossary else 'none'}")
        console.print(f"  - prior context count: {len(manifest.prior_context)}")

    if result.review_queue:
        console.print("[bold yellow]Items requiring review[/bold yellow]")
        for item in result.review_queue[:8]:
            console.print(f"  - {item}")

    console.print("\n[bold blue]Artifacts[/bold blue]")
    for label, path in result.artifacts.items():
        console.print(f"  - {label}: {path}")


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

    if args.mode == "linear":
        results = run_linear_mode(args, console)
        render_linear_summary(results, console)
        evaluation_result = maybe_run_post_scenario_evaluation(args, console)
        if evaluation_result:
            render_evaluation_summary(evaluation_result, console)
        return

    result = run_agentic_mode(args, console)
    render_agentic_summary(result, console)
    evaluation_result = maybe_run_post_scenario_evaluation(args, console)
    if evaluation_result:
        render_evaluation_summary(evaluation_result, console)


if __name__ == "__main__":
    main()
