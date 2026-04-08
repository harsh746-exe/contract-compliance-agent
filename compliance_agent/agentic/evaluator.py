"""Workflow-level evaluator for the agentic engine."""

from __future__ import annotations

from typing import Dict

from .. import config
from .models import EvaluatorDecision


class WorkflowEvaluator:
    """Determines whether the last workflow action should be accepted, retried, or escalated."""

    def evaluate(self, state: Dict, action: str, result: Dict) -> EvaluatorDecision:
        """Evaluate one completed action and decide the next control outcome."""
        if action == "route_documents":
            ambiguous = result.get("ambiguous_documents", [])
            manifest_ready = bool(result.get("primary_source")) and bool(result.get("primary_response"))
            if not manifest_ready or ambiguous:
                return EvaluatorDecision(
                    outcome="request_approval",
                    reason="Document routing is incomplete or ambiguous.",
                    requires_approval=True,
                    unresolved_items=ambiguous or ["missing_primary_roles"],
                )
            return EvaluatorDecision(outcome="accept", reason="Documents routed successfully.")

        if action == "prepare_context":
            if result.get("comparison_available"):
                return EvaluatorDecision(
                    outcome="branch_to_other_action",
                    reason="Prior context is available for comparison before the main compliance run.",
                    next_action="compare_with_prior_context",
                )
            return EvaluatorDecision(outcome="accept", reason="Context prepared successfully.")

        if action == "compare_with_prior_context":
            return EvaluatorDecision(outcome="accept", reason="Historical comparison summary is available.")

        if action in {"run_compliance_pipeline", "reanalyze_low_confidence"}:
            review_queue = result.get("review_queue", [])
            if review_queue:
                retries = state["action_attempts"].get("reanalyze_low_confidence", 0)
                if retries < config.AGENTIC_MAX_ACTION_RETRIES:
                    return EvaluatorDecision(
                        outcome="retry_subset",
                        reason="Low-confidence items remain after the compliance run.",
                        retry_action="reanalyze_low_confidence",
                        unresolved_items=list(review_queue),
                    )
                return EvaluatorDecision(
                    outcome="request_approval",
                    reason="Low-confidence items remain after bounded reanalysis.",
                    requires_approval=True,
                    unresolved_items=list(review_queue),
                )

            if getattr(state.get("goal"), "draft_requested", False):
                return EvaluatorDecision(
                    outcome="branch_to_other_action",
                    reason="Compliance analysis is complete and the workflow goal also requests drafting.",
                    next_action="draft_response_outline",
                )
            return EvaluatorDecision(outcome="accept", reason="Compliance analysis is complete.")

        if action == "draft_response_outline":
            return EvaluatorDecision(
                outcome="branch_to_other_action",
                reason="Draft created; evaluate it before final handoff.",
                next_action="evaluate_draft",
            )

        if action == "evaluate_draft":
            issues = result.get("issues", [])
            rewrites = state["action_attempts"].get("rewrite_draft", 0)
            if issues and rewrites < config.AGENTIC_MAX_ACTION_RETRIES:
                return EvaluatorDecision(
                    outcome="branch_to_other_action",
                    reason="Draft issues were detected and a bounded rewrite is still allowed.",
                    next_action="rewrite_draft",
                    unresolved_items=list(issues),
                )
            if issues:
                return EvaluatorDecision(
                    outcome="request_approval",
                    reason="Draft issues remain after bounded rewrite attempts.",
                    requires_approval=True,
                    unresolved_items=list(issues),
                )
            return EvaluatorDecision(outcome="accept", reason="Draft evaluation passed.")

        if action == "rewrite_draft":
            issues = state.get("draft_evaluation", {}).get("issues", [])
            if issues:
                return EvaluatorDecision(
                    outcome="branch_to_other_action",
                    reason="Rewrite completed; re-evaluate the updated draft.",
                    next_action="evaluate_draft",
                )
            return EvaluatorDecision(outcome="accept", reason="Draft rewrite completed.")

        if action == "request_human_approval":
            if result.get("approved"):
                return EvaluatorDecision(outcome="accept", reason="Approval granted.")
            return EvaluatorDecision(
                outcome="terminate_blocked",
                reason="Required approval was denied or not available.",
                unresolved_items=result.get("unresolved_items", []),
            )

        if action == "finalize_outputs":
            if result.get("artifacts"):
                return EvaluatorDecision(outcome="accept", reason="Final artifacts were generated.")
            return EvaluatorDecision(
                outcome="terminate_blocked",
                reason="Finalization completed without writing artifacts.",
            )

        return EvaluatorDecision(outcome="accept", reason=f"Action {action} completed.")
