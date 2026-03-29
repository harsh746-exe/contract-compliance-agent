"""Agentic control-plane engine for bounded workflow execution."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union
from uuid import uuid4

from pydantic import BaseModel

from .. import config
from .comparison import HistoricalComparisonWorker
from .drafting import DraftEvaluator, DraftRewriter, ProposalDrafter
from .evaluator import WorkflowEvaluator
from .models import (
    ApprovalDecision,
    ApprovalRequest,
    DocumentInput,
    PlannerDecision,
    WorkflowGoal,
    WorkflowRunResult,
    WorkflowTask,
)
from .planner import WorkflowPlanner
from .router import DocumentRouter
from .store import (
    WorkflowStateStore,
    approval_request_from_dict,
    document_from_dict,
    goal_from_dict,
    manifest_from_dict,
    planner_decision_from_dict,
    task_from_dict,
)


ApprovalHandler = Callable[[ApprovalRequest], ApprovalDecision]


def _to_jsonable(value: Any) -> Any:
    """Convert workflow values into JSON-safe data."""
    if isinstance(value, BaseModel):
        return _to_jsonable(value.model_dump(mode="json"))
    if isinstance(value, Path):
        return str(value)
    if hasattr(value, "__dict__") and not isinstance(value, type):
        return _to_jsonable(vars(value))
    if isinstance(value, dict):
        return {key: _to_jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(item) for item in value]
    return value


class AgenticWorkflowEngine:
    """Planner-driven bounded workflow engine built on top of the compliance backbone."""

    def __init__(
        self,
        planner: Optional[WorkflowPlanner] = None,
        router: Optional[DocumentRouter] = None,
        evaluator: Optional[WorkflowEvaluator] = None,
        comparison_worker: Optional[HistoricalComparisonWorker] = None,
        proposal_drafter: Optional[ProposalDrafter] = None,
        draft_evaluator: Optional[DraftEvaluator] = None,
        draft_rewriter: Optional[DraftRewriter] = None,
        state_store: Optional[WorkflowStateStore] = None,
        compliance_agent_factory=None,
        compliance_agent=None,
        llm=None,
    ):
        self.planner = planner or WorkflowPlanner(llm=llm)
        self.router = router or DocumentRouter(llm=llm)
        self.evaluator = evaluator or WorkflowEvaluator()
        self.comparison_worker = comparison_worker or HistoricalComparisonWorker(llm=llm)
        self.proposal_drafter = proposal_drafter or ProposalDrafter(llm=llm)
        self.draft_evaluator = draft_evaluator or DraftEvaluator()
        self.draft_rewriter = draft_rewriter or DraftRewriter()
        self.state_store = state_store or WorkflowStateStore()
        self.compliance_agent_factory = compliance_agent_factory
        self.compliance_agent = compliance_agent
        self.llm = llm

    def run(
        self,
        goal: Union[WorkflowGoal, str, Dict[str, Any]],
        documents: Optional[List[Union[DocumentInput, Dict[str, Any]]]] = None,
        approval_handler: Optional[ApprovalHandler] = None,
        run_id: Optional[str] = None,
        resume: bool = False,
    ) -> WorkflowRunResult:
        """Run or resume the bounded agentic workflow."""
        if resume:
            if not run_id:
                raise ValueError("run_id is required to resume an agentic workflow.")
            state = self._hydrate_state(self.state_store.load_state(run_id))
            if state["status"] == "awaiting_approval" and approval_handler is not None:
                state["status"] = "running"
        else:
            state = self._initialize_state(goal, documents or [], run_id)

        while state["status"] == "running":
            if len(state["tasks"]) >= config.AGENTIC_MAX_STEPS:
                state["status"] = "blocked"
                state["errors"].append("Workflow exceeded the maximum number of bounded control steps.")
                break

            if state.get("pending_approval_request"):
                approval_result = self._execute_request_human_approval(state, approval_handler)
                self._record_evaluator_decision(
                    state,
                    self.evaluator.evaluate(state, "request_human_approval", approval_result),
                )
                if state["status"] != "running":
                    break
                continue

            decision = self.planner.decide(state, state["goal"])
            task = self._create_task(state, decision)
            result = self._execute_action(decision, state, approval_handler)
            evaluator_decision = self.evaluator.evaluate(state, decision.next_action, result)
            self._complete_task(task, result)
            self._record_evaluator_decision(state, evaluator_decision)
            self._apply_evaluator_decision(state, evaluator_decision)
            self.state_store.save_state(state["run_id"], state)

        handoff_summary_path = self._write_handoff_summary(state)
        state["artifacts"]["handoff_summary"] = handoff_summary_path
        final_result = self._build_result(state)
        final_result.artifacts["handoff_summary"] = handoff_summary_path
        self.state_store.save_result_summary(final_result)
        self.state_store.save_state(state["run_id"], state)
        return final_result

    def _initialize_state(self, goal, documents, run_id: Optional[str]) -> Dict[str, Any]:
        workflow_goal = self._coerce_goal(goal)
        workflow_documents = self._coerce_documents(documents)
        run_id = run_id or f"agentic_{uuid4().hex[:10]}"

        state = {
            "run_id": run_id,
            "status": "running",
            "goal": workflow_goal,
            "documents": workflow_documents,
            "document_manifest": None,
            "tasks": [],
            "planner_history": [],
            "evaluator_history": [],
            "approval_requests": [],
            "approval_decisions": [],
            "pending_approval_request": None,
            "artifacts": {},
            "current_phase": "intake",
            "context_prepared": False,
            "context_summary": {},
            "comparison_summary": None,
            "draft_bundle": None,
            "draft_evaluation": None,
            "worker_results": None,
            "review_queue": [],
            "unresolved_risks": [],
            "next_action_hint": None,
            "needs_final_approval": False,
            "action_attempts": {},
            "errors": [],
            "worker_run_id": None,
        }
        self.state_store.save_state(run_id, state)
        return state

    def _coerce_goal(self, goal: Union[WorkflowGoal, str, Dict[str, Any]]) -> WorkflowGoal:
        if isinstance(goal, WorkflowGoal):
            return goal
        if isinstance(goal, dict):
            return WorkflowGoal(**goal)
        if isinstance(goal, str):
            goal_type = "draft_proposal" if "draft" in goal.lower() else "compliance_review"
            return WorkflowGoal(
                goal_type=goal_type,
                description=goal,
                draft_requested="draft" in goal.lower(),
                compare_requested=True,
            )
        raise TypeError("goal must be a WorkflowGoal, dict, or string")

    def _coerce_documents(self, documents: List[Union[DocumentInput, Dict[str, Any]]]) -> List[DocumentInput]:
        normalized = []
        for document in documents:
            if isinstance(document, DocumentInput):
                normalized.append(document)
            else:
                normalized.append(DocumentInput(**document))
        return normalized

    def _hydrate_state(self, raw_state: Dict[str, Any]) -> Dict[str, Any]:
        raw_state["goal"] = goal_from_dict(raw_state["goal"])
        raw_state["documents"] = [document_from_dict(doc) for doc in raw_state.get("documents", [])]
        raw_state["document_manifest"] = (
            manifest_from_dict(raw_state["document_manifest"])
            if raw_state.get("document_manifest")
            else None
        )
        raw_state["tasks"] = [task_from_dict(task) for task in raw_state.get("tasks", [])]
        raw_state["planner_history"] = [
            planner_decision_from_dict(item) if isinstance(item, dict) else item
            for item in raw_state.get("planner_history", [])
        ]
        raw_state["approval_requests"] = [
            approval_request_from_dict(item) if isinstance(item, dict) else item
            for item in raw_state.get("approval_requests", [])
        ]
        raw_state["pending_approval_request"] = (
            approval_request_from_dict(raw_state["pending_approval_request"])
            if raw_state.get("pending_approval_request")
            else None
        )
        return raw_state

    def _create_task(self, state: Dict[str, Any], decision: PlannerDecision) -> WorkflowTask:
        attempts = state["action_attempts"].get(decision.next_action, 0) + 1
        state["action_attempts"][decision.next_action] = attempts
        task = WorkflowTask(
            task_id=f"TASK_{len(state['tasks']) + 1:04d}",
            action=decision.next_action,
            status="in_progress",
            reason=decision.reason,
            required_inputs=decision.required_inputs,
            success_condition=decision.success_condition,
            attempt=attempts,
        )
        state["tasks"].append(task)
        state["planner_history"].append(decision)
        return task

    def _complete_task(self, task: WorkflowTask, result: Dict[str, Any]) -> None:
        task.status = "completed"
        task.output_summary = result.get("summary", "")

    def _record_evaluator_decision(self, state: Dict[str, Any], evaluator_decision) -> None:
        state["evaluator_history"].append(evaluator_decision.model_dump(mode="json"))

    def _apply_evaluator_decision(self, state: Dict[str, Any], evaluator_decision) -> None:
        if evaluator_decision.outcome == "accept":
            state["next_action_hint"] = evaluator_decision.next_action
            if state["tasks"] and state["tasks"][-1].action == "finalize_outputs":
                state["status"] = "completed"
        elif evaluator_decision.outcome == "retry_subset":
            state["next_action_hint"] = evaluator_decision.retry_action
            state["unresolved_risks"] = evaluator_decision.unresolved_items
            state["review_queue"] = evaluator_decision.unresolved_items
        elif evaluator_decision.outcome == "branch_to_other_action":
            state["next_action_hint"] = evaluator_decision.next_action
            state["unresolved_risks"] = evaluator_decision.unresolved_items
        elif evaluator_decision.outcome == "request_approval":
            state["unresolved_risks"] = evaluator_decision.unresolved_items
            state["needs_final_approval"] = True
            request = ApprovalRequest(
                request_id=f"APR_{len(state['approval_requests']) + 1:04d}",
                reason=evaluator_decision.reason,
                suggested_action=evaluator_decision.next_action or state.get("current_phase") or "finalize_outputs",
                context={"unresolved_items": evaluator_decision.unresolved_items},
            )
            state["approval_requests"].append(request)
            state["pending_approval_request"] = request
            state["next_action_hint"] = None
        elif evaluator_decision.outcome == "terminate_blocked":
            state["status"] = "blocked"
            state["errors"].append(evaluator_decision.reason)

    def _execute_action(
        self,
        decision: PlannerDecision,
        state: Dict[str, Any],
        approval_handler: Optional[ApprovalHandler],
    ) -> Dict[str, Any]:
        action = decision.next_action
        state["current_phase"] = action

        if action == "route_documents":
            manifest = self.router.route(state["documents"])
            state["document_manifest"] = manifest
            return {
                **manifest.model_dump(mode="json"),
                "summary": f"Routed {len(state['documents'])} documents into workflow roles.",
            }

        if action == "prepare_context":
            manifest = state["document_manifest"]
            state["context_prepared"] = True
            state["context_summary"] = {
                "glossary_path": manifest.glossary.path if manifest.glossary else None,
                "prior_context_paths": [doc.path for doc in manifest.prior_context],
                "comparison_available": bool(manifest.prior_context),
            }
            return {
                "comparison_available": bool(manifest.prior_context),
                "summary": "Prepared retrieval scope and optional context pools.",
            }

        if action == "compare_with_prior_context":
            manifest = state["document_manifest"]
            comparison_summary = self.comparison_worker.compare(
                manifest.primary_source.path,
                [doc.path for doc in manifest.prior_context],
            )
            state["comparison_summary"] = comparison_summary
            return {
                **comparison_summary,
                "summary": comparison_summary["summary"],
            }

        if action in {"run_compliance_pipeline", "reanalyze_low_confidence"}:
            manifest = state["document_manifest"]
            worker_run_id = f"{state['run_id']}_{action}_{state['action_attempts'][action]}"
            state["worker_run_id"] = worker_run_id
            compliance_agent = self._get_compliance_agent(state["run_id"])
            results = compliance_agent.process(
                policy_path=manifest.primary_source.path,
                response_path=manifest.primary_response.path,
                glossary_path=manifest.glossary.path if manifest.glossary else None,
                context_paths=[doc.path for doc in manifest.prior_context],
                run_id=worker_run_id,
            )
            state["worker_results"] = results
            state["review_queue"] = results.get("review_queue", [])
            return {
                **results,
                "summary": f"Completed compliance analysis with {len(results.get('requirements', []))} requirements.",
            }

        if action == "draft_response_outline":
            if not state.get("worker_results"):
                state["errors"].append("Drafting requested before compliance results were available.")
                return {"summary": "Drafting could not start because compliance results are missing."}
            requirements = state["worker_results"]["requirements"]
            decisions = state["worker_results"]["decisions"]
            draft_bundle = self.proposal_drafter.draft_outline(
                requirements,
                decisions,
                state.get("comparison_summary"),
            )
            state["draft_bundle"] = draft_bundle
            return {
                **draft_bundle,
                "summary": f"Generated a draft outline with {len(draft_bundle.get('sections', []))} sections.",
            }

        if action == "evaluate_draft":
            requirement_ids = [req.req_id for req in state["worker_results"]["requirements"]]
            evaluation = self.draft_evaluator.evaluate(state["draft_bundle"], requirement_ids)
            state["draft_evaluation"] = evaluation
            return {
                **evaluation,
                "summary": f"Draft evaluation status: {evaluation['status']}.",
            }

        if action == "rewrite_draft":
            rewritten = self.draft_rewriter.rewrite(state["draft_bundle"], state["draft_evaluation"] or {})
            state["draft_bundle"] = rewritten
            return {
                **rewritten,
                "summary": "Rewrote the bounded draft based on evaluator findings.",
            }

        if action == "request_human_approval":
            return self._execute_request_human_approval(state, approval_handler)

        if action == "finalize_outputs":
            artifacts = self._finalize_outputs(state)
            state["artifacts"].update(artifacts)
            return {
                "artifacts": artifacts,
                "summary": f"Wrote {len(artifacts)} workflow artifacts.",
            }

        state["status"] = "blocked"
        state["errors"].append(f"Unsupported planner action: {action}")
        return {"summary": f"Unsupported planner action: {action}"}

    def _execute_request_human_approval(
        self,
        state: Dict[str, Any],
        approval_handler: Optional[ApprovalHandler],
    ) -> Dict[str, Any]:
        request = state.get("pending_approval_request")
        if request is None:
            return {"approved": True, "summary": "No approval was pending."}

        if approval_handler is None:
            state["status"] = "awaiting_approval"
            return {
                "approved": False,
                "paused": True,
                "unresolved_items": request.context.get("unresolved_items", []),
                "summary": "Workflow paused awaiting human approval.",
            }

        decision = approval_handler(request)
        state["approval_decisions"].append(decision.model_dump(mode="json"))
        request.status = "approved" if decision.approved else "denied"
        state["pending_approval_request"] = None
        if decision.approved:
            state["status"] = "running"
            state["needs_final_approval"] = False
            state["next_action_hint"] = request.suggested_action
        else:
            state["status"] = "blocked"

        return {
            "approved": decision.approved,
            "unresolved_items": request.context.get("unresolved_items", []),
            "summary": f"Human approval {'granted' if decision.approved else 'denied'}.",
        }

    def _get_compliance_agent(self, run_id: str):
        if self.compliance_agent is not None:
            return self.compliance_agent
        if self.compliance_agent_factory is not None:
            return self.compliance_agent_factory(run_id)

        from ..orchestration.pipeline import ComplianceAgent

        storage_path = config.WORKFLOW_COMPLIANCE_STORE_DIR / run_id
        return ComplianceAgent(storage_path=storage_path, llm=self.llm)

    def _finalize_outputs(self, state: Dict[str, Any]) -> Dict[str, str]:
        output_dir = config.AGENTIC_RESULTS_DIR / state["run_id"]
        output_dir.mkdir(parents=True, exist_ok=True)
        artifacts: Dict[str, str] = {}

        if state.get("worker_results"):
            compliance_agent = self._get_compliance_agent(state["run_id"])
            matrix_path = output_dir / f"{state['run_id']}_matrix.csv"
            json_path = output_dir / f"{state['run_id']}_results.json"
            report_path = output_dir / f"{state['run_id']}_report.md"
            compliance_agent.export_matrix(str(matrix_path))
            compliance_agent.export_json(str(json_path))
            compliance_agent.export_report(str(report_path))
            artifacts.update({
                "matrix": str(matrix_path),
                "results_json": str(json_path),
                "report": str(report_path),
            })

        if state.get("comparison_summary"):
            comparison_path = output_dir / f"{state['run_id']}_comparison_summary.json"
            comparison_path.write_text(__import__("json").dumps(state["comparison_summary"], indent=2))
            artifacts["comparison_summary"] = str(comparison_path)

        if state.get("draft_bundle"):
            draft_path = output_dir / f"{state['run_id']}_draft_outline.json"
            draft_path.write_text(__import__("json").dumps(state["draft_bundle"], indent=2))
            artifacts["draft_outline"] = str(draft_path)

        workflow_md_path = output_dir / f"{state['run_id']}_workflow_summary.md"
        workflow_md_path.write_text(self._build_workflow_markdown(state))
        artifacts["workflow_summary"] = str(workflow_md_path)
        artifacts["handoff_summary"] = self._write_handoff_summary(state, artifacts)
        return artifacts

    def _write_handoff_summary(
        self,
        state: Dict[str, Any],
        artifacts: Optional[Dict[str, str]] = None,
    ) -> str:
        """Write a machine-readable handoff summary for completed or paused runs."""
        output_dir = config.AGENTIC_RESULTS_DIR / state["run_id"]
        output_dir.mkdir(parents=True, exist_ok=True)
        handoff_path = output_dir / f"{state['run_id']}_handoff_summary.json"

        artifact_inventory = dict(state.get("artifacts", {}))
        if artifacts:
            artifact_inventory.update(artifacts)
        artifact_inventory["handoff_summary"] = str(handoff_path)

        payload = {
            "run_id": state["run_id"],
            "status": state["status"],
            "goal": _to_jsonable(state.get("goal")),
            "executed_actions": [task.action for task in state.get("tasks", [])],
            "approval_requests": _to_jsonable(state.get("approval_requests", [])),
            "approval_decisions": _to_jsonable(state.get("approval_decisions", [])),
            "unresolved_review_queue": list(state.get("review_queue", [])),
            "errors": list(state.get("errors", [])),
            "artifact_inventory": artifact_inventory,
            "safe_for_demo_handoff": (
                state["status"] == "completed"
                and not state.get("review_queue")
                and not state.get("pending_approval_request")
                and not state.get("errors")
            ),
        }

        handoff_path.write_text(json.dumps(payload, indent=2))
        return str(handoff_path)

    def _build_workflow_markdown(self, state: Dict[str, Any]) -> str:
        manifest = state.get("document_manifest")
        lines = [
            "# Agentic Workflow Summary",
            "",
            f"- Run ID: {state['run_id']}",
            f"- Status: {state['status']}",
            f"- Goal: {state['goal'].description}",
            f"- Current Phase: {state['current_phase']}",
            f"- Review Queue Size: {len(state.get('review_queue', []))}",
            "",
            "## Tasks",
            "",
        ]
        for task in state.get("tasks", []):
            lines.append(f"- {task.task_id}: `{task.action}` [{task.status}] - {task.reason}")
        lines.extend(["", "## Manifest", ""])
        if manifest:
            lines.append(f"- Primary Source: {manifest.primary_source.path if manifest.primary_source else 'missing'}")
            lines.append(f"- Primary Response: {manifest.primary_response.path if manifest.primary_response else 'missing'}")
            lines.append(f"- Glossary: {manifest.glossary.path if manifest.glossary else 'none'}")
            lines.append(f"- Prior Context Count: {len(manifest.prior_context)}")
            if manifest.ambiguous_documents:
                lines.append(f"- Ambiguous: {', '.join(manifest.ambiguous_documents)}")
        if state.get("comparison_summary"):
            lines.extend(["", "## Historical Comparison", "", state["comparison_summary"].get("summary", "")])
        if state.get("draft_evaluation"):
            lines.extend(["", "## Draft Evaluation", "", f"- Status: {state['draft_evaluation'].get('status', 'unknown')}"])
            for issue in state["draft_evaluation"].get("issues", []):
                lines.append(f"- Issue: {issue}")
        if state.get("approval_requests"):
            lines.extend(["", "## Approval Requests", ""])
            for request in state["approval_requests"]:
                lines.append(f"- {request.request_id}: {request.reason} [{request.status}]")
        return "\n".join(lines) + "\n"

    def _build_result(self, state: Dict[str, Any]) -> WorkflowRunResult:
        manifest = state["document_manifest"] or self.router.route(state["documents"])
        summary = {
            "current_phase": state["current_phase"],
            "completed_tasks": len([task for task in state["tasks"] if task.status == "completed"]),
            "planner_actions": [task.action for task in state["tasks"]],
            "errors": state.get("errors", []),
            "approval_decisions": state.get("approval_decisions", []),
        }
        return WorkflowRunResult(
            run_id=state["run_id"],
            status=state["status"],
            goal=state["goal"],
            document_manifest=manifest,
            tasks=state["tasks"],
            approvals=state["approval_requests"],
            artifacts=state.get("artifacts", {}),
            review_queue=state.get("review_queue", []),
            summary=summary,
        )
