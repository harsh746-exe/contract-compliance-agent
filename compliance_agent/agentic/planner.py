"""Planner for bounded agentic workflow decisions."""

from __future__ import annotations

from typing import Dict, List, Optional

from .. import config
from ..runtime import require_langchain_llm_runtime
from .models import PlannerDecision, WorkflowGoal


ALLOWED_ACTIONS = [
    "route_documents",
    "prepare_context",
    "run_compliance_pipeline",
    "reanalyze_low_confidence",
    "compare_with_prior_context",
    "draft_response_outline",
    "evaluate_draft",
    "rewrite_draft",
    "request_human_approval",
    "finalize_outputs",
    "stop_with_error",
]


class WorkflowPlanner:
    """Chooses the next bounded workflow action."""

    def __init__(self, llm=None):
        self.llm = llm

    def decide(self, state: Dict, goal: WorkflowGoal) -> PlannerDecision:
        """Choose the next action, preferring LLM planning with a bounded fallback."""
        if self.llm is not None:
            llm_decision = self._llm_decide(state, goal)
            if llm_decision:
                return llm_decision
        return self._heuristic_decide(state, goal)

    def _llm_decide(self, state: Dict, goal: WorkflowGoal) -> Optional[PlannerDecision]:
        """Use an LLM to select the next bounded action."""
        require_langchain_llm_runtime()
        from langchain.prompts import ChatPromptTemplate

        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are the control planner for a bounded agentic workflow.
You must choose exactly one next action from this list:
{allowed_actions}

Return JSON with:
- next_action
- reason
- required_inputs
- requires_approval
- success_condition

Never invent an action outside the allowed list."""),
            ("human", """Goal:
{goal}

State summary:
{state_summary}"""),
        ])

        try:
            state_summary = {
                "status": state.get("status"),
                "current_phase": state.get("current_phase"),
                "next_action_hint": state.get("next_action_hint"),
                "manifest_ready": bool(state.get("document_manifest")),
                "review_queue": state.get("review_queue", []),
                "unresolved_risks": state.get("unresolved_risks", []),
                "has_compliance_result": bool(state.get("worker_results")),
                "has_comparison_summary": bool(state.get("comparison_summary")),
                "has_draft": bool(state.get("draft_bundle")),
                "draft_evaluation": state.get("draft_evaluation"),
                "pending_approval": state.get("pending_approval_request"),
            }
            response = self.llm.invoke(prompt.format_messages(
                allowed_actions=", ".join(ALLOWED_ACTIONS),
                goal=goal.description,
                state_summary=str(state_summary),
            ))
            content = response.content.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()

            import json

            payload = json.loads(content)
            if payload.get("next_action") not in ALLOWED_ACTIONS:
                return None
            return PlannerDecision(
                next_action=payload["next_action"],
                reason=payload.get("reason", "LLM planner decision"),
                required_inputs=payload.get("required_inputs", []),
                requires_approval=bool(payload.get("requires_approval", False)),
                success_condition=payload.get("success_condition", ""),
            )
        except Exception:
            return None

    def _heuristic_decide(self, state: Dict, goal: WorkflowGoal) -> PlannerDecision:
        """Deterministic fallback planner for tests and offline runs."""
        hint = state.get("next_action_hint")
        if hint in ALLOWED_ACTIONS:
            return PlannerDecision(
                next_action=hint,
                reason=f"Control-layer hint requested {hint}.",
                success_condition=f"Execute {hint} and clear the outstanding control-layer hint.",
            )

        manifest = state.get("document_manifest")
        if not manifest:
            return PlannerDecision(
                next_action="route_documents",
                reason="Documents have not been routed into workflow roles yet.",
                success_condition="Primary source, primary response, and optional context roles are assigned.",
            )

        if state.get("pending_approval_request"):
            return PlannerDecision(
                next_action="request_human_approval",
                reason="A pending approval request must be resolved before further work can continue.",
                requires_approval=True,
                success_condition="Human approval is granted or denied.",
            )

        if not state.get("context_prepared"):
            return PlannerDecision(
                next_action="prepare_context",
                reason="The workflow has not prepared context and retrieval scope yet.",
                success_condition="Context pools and support documents are summarized.",
            )

        if manifest.prior_context and not state.get("comparison_summary"):
            return PlannerDecision(
                next_action="compare_with_prior_context",
                reason="Prior-context documents exist and should be compared before the main compliance pass.",
                success_condition="Historical comparison summary is available.",
            )

        if not state.get("worker_results"):
            return PlannerDecision(
                next_action="run_compliance_pipeline",
                reason="No compliance analysis has been run for the primary source/response pair.",
                success_condition="Compliance decisions and review queue are available.",
            )

        if state.get("review_queue") and state["action_attempts"].get("reanalyze_low_confidence", 0) < config.AGENTIC_MAX_ACTION_RETRIES:
            return PlannerDecision(
                next_action="reanalyze_low_confidence",
                reason="Low-confidence requirements remain and bounded reanalysis is still allowed.",
                required_inputs=list(state.get("review_queue", [])),
                success_condition="Review queue shrinks or bounded retries are exhausted.",
            )

        if goal.draft_requested and not state.get("draft_bundle"):
            return PlannerDecision(
                next_action="draft_response_outline",
                reason="The workflow goal requests drafting support and no outline has been created yet.",
                success_condition="Initial outline and draft sections are available.",
            )

        if goal.draft_requested and state.get("draft_bundle") and not state.get("draft_evaluation"):
            return PlannerDecision(
                next_action="evaluate_draft",
                reason="The generated draft should be evaluated before handoff.",
                success_condition="Draft evaluation result is recorded.",
            )

        if goal.draft_requested and state.get("draft_evaluation", {}).get("issues") and state["action_attempts"].get("rewrite_draft", 0) < config.AGENTIC_MAX_ACTION_RETRIES:
            return PlannerDecision(
                next_action="rewrite_draft",
                reason="The evaluated draft has issues that can be fixed with a bounded rewrite pass.",
                success_condition="Draft issues are reduced or bounded rewrite attempts are exhausted.",
            )

        if state.get("needs_final_approval"):
            return PlannerDecision(
                next_action="request_human_approval",
                reason="The workflow has reached a final review or risk boundary that requires approval.",
                requires_approval=True,
                success_condition="Human approval decision is recorded.",
            )

        return PlannerDecision(
            next_action="finalize_outputs",
            reason="All required workflow stages are complete or no further automated progress is possible.",
            success_condition="Final artifacts and workflow summary are written.",
        )
