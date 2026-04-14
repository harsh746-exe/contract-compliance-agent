"""Top-level autonomous workflow orchestrator."""

from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any

from .. import config
from ..llm.orchestrator_llm import plan_next_action
from ..mcp.protocol import MCPMessage, MessageType, ToolSchema
from .base import BaseAgent
from .orchestrator_prompts import PLANNER_SYSTEM_PROMPT, STATE_SUMMARY_TEMPLATE

logger = logging.getLogger(__name__)

MAX_PLANNING_STEPS = 15
MAX_ACTION_RETRIES = 2
PLANNER_LOW_CONFIDENCE_THRESHOLD = 0.85


class Orchestrator(BaseAgent):
    """Coordinates the agentic back-office workflow."""

    def __init__(self, bus, skill_registry):
        super().__init__(
            agent_id="orchestrator",
            role="coordinator",
            description="Top-level workflow coordinator that delegates goals to autonomous agents.",
            bus=bus,
            skill_registry=skill_registry,
        )
        self.logger = logger
        self.workflow_state = {
            "goal": None,
            "phase": "idle",
            "completed_steps": [],
            "active_sub_agents": {},
            "outputs": {},
            "errors": [],
            "retry_counts": {},
            "approval_pending": [],
        }
        self._workflow_state: dict[str, Any] = {}
        self._stage_callback = None

    def _declare_tools(self) -> list[ToolSchema]:
        return [
            ToolSchema(
                name="get_workflow_state",
                description="Return the current orchestrator workflow state.",
                input_schema={},
                output_schema={"state": "dict"},
            )
        ]

    async def execute_goal(self, goal: dict) -> dict:
        """Execute the requested workflow goal and return final outputs."""
        self.workflow_state["goal"] = goal
        self.workflow_state["run_id"] = goal.get("run_id")
        workflow_type = await self._determine_workflow(goal)
        if workflow_type == "proposal_drafting":
            return await self._run_drafting_workflow(goal)
        if workflow_type == "comparison":
            return await self._run_comparison_workflow(goal)
        if workflow_type == "general":
            return await self._run_general_workflow(goal)
        return await self._run_compliance_workflow(goal)

    def set_stage_callback(self, callback) -> None:
        """Register a callback for planning-stage progress updates."""
        self._stage_callback = callback

    async def _determine_workflow(self, goal: dict) -> str:
        task = (goal.get("task") or goal.get("goal_type") or "compliance_review").lower()
        if "draft" in task:
            return "proposal_drafting"
        if "comparison" in task:
            return "comparison"
        if "general" in task:
            return "general"
        return "compliance_review"

    async def _run_compliance_workflow(self, goal: dict) -> dict:
        self.report_status("Orchestrator started compliance workflow")
        self._initialize_planner_state(goal)
        return await self._run_planning_loop(goal)

    def _initialize_planner_state(self, goal: dict) -> None:
        workflow_goal = goal.get("goal") or goal.get("task") or goal.get("goal_type") or "compliance_review"
        workflow_type = goal.get("workflow_type") or goal.get("task") or goal.get("goal_type") or "compliance_review"
        self._workflow_state = {
            "completed_steps": [],
            "requirements": [],
            "requirements_by_id": {},
            "evidence": {},
            "decisions": {},
            "comparison_done": False,
            "qa_done": False,
            "drafting_done": False,
            "reanalysis_done": False,
            "action_history": [],
            "issues": [],
            "workflow_goal": workflow_goal,
            "workflow_type": workflow_type,
            "documents": goal.get("documents", []),
            "parsed_documents": [],
            "all_chunks": [],
            "document_manifest": {},
            "retrieval_plans": {},
            "comparison_summary": None,
            "review_queue": [],
            "qa_report": {},
            "draft": None,
            "draft_review": None,
            "draft_iterations": [],
            "action_attempt_counts": {},
        }

    async def _run_planning_loop(self, goal_payload: dict) -> dict:
        for step_num in range(1, MAX_PLANNING_STEPS + 1):
            state_summary = self._build_state_summary()

            planner_mode = "llm"
            try:
                raw_plan = await plan_next_action(PLANNER_SYSTEM_PROMPT, state_summary)
                plan = self._parse_plan(raw_plan)
                if plan.get("_fallback"):
                    planner_mode = "fallback"
            except Exception as exc:
                logger.warning("Planner LLM failed (%s), using fallback logic", exc)
                plan = self._deterministic_fallback()
                planner_mode = "fallback"

            action = str(plan.get("action", "finalize") or "finalize")
            reasoning = str(plan.get("reasoning", "") or "")
            target_reqs = plan.get("target_requirements") or []
            if not isinstance(target_reqs, list):
                target_reqs = []
            parameters = plan.get("parameters") or {}
            if not isinstance(parameters, dict):
                parameters = {}
            original_action = action

            action, reasoning, target_reqs, parameters, planner_mode = self._apply_action_retry_cap(
                action=action,
                reasoning=reasoning,
                target_reqs=target_reqs,
                parameters=parameters,
                planner_mode=planner_mode,
            )

            logger.info("Step %d: Planner chose '%s' - %s", step_num, action, reasoning)
            self._emit_stage_update(step_num, action, "running")

            self.bus.record_event(
                MessageType.STATUS,
                sender=self.agent_id,
                recipient="orchestrator",
                payload={
                    "event": "planning_decision",
                    "step": step_num,
                    "action": action,
                    "original_action": original_action,
                    "reasoning": reasoning,
                    "target_requirements": target_reqs,
                    "parameters": parameters,
                    "planner_mode": planner_mode,
                },
            )

            if action == "finalize":
                result = await self._execute_finalize(goal_payload)
                self._workflow_state["action_history"].append(
                    {
                        "step": step_num,
                        "action": action,
                        "reasoning": reasoning,
                        "target_requirements": target_reqs,
                        "planner_mode": planner_mode,
                        "confidence_after": self._confidence_snapshot(),
                    }
                )
                self._emit_stage_update(step_num, action, "completed")
                result["planning_trace"] = self._workflow_state.get("action_history", [])
                return result
            if action == "dispatch_intake":
                outcome = await self._execute_intake(goal_payload)
            elif action == "dispatch_extraction":
                outcome = await self._execute_extraction(goal_payload)
            elif action == "dispatch_retrieval":
                outcome = await self._execute_retrieval(goal_payload, target_reqs, parameters)
            elif action == "dispatch_compliance":
                outcome = await self._execute_compliance(goal_payload, target_reqs)
            elif action == "dispatch_comparison":
                outcome = await self._execute_comparison(goal_payload)
            elif action == "dispatch_qa":
                outcome = await self._execute_qa(goal_payload)
            elif action == "dispatch_drafting":
                outcome = await self._execute_drafting(goal_payload)
            elif action == "request_reanalysis":
                outcome = await self._execute_reanalysis(goal_payload, target_reqs)
            else:
                logger.warning("Unknown action '%s', skipping", action)
                self._workflow_state["issues"].append(f"Unknown action: {action}")
                outcome = None

            if isinstance(outcome, dict) and outcome.get("status") in {"retry", "failed"}:
                if outcome["status"] == "retry":
                    continue
                return outcome

            self._update_state_after_action(action, target_reqs)
            self._workflow_state["action_history"].append(
                {
                    "step": step_num,
                    "action": action,
                    "reasoning": reasoning,
                    "target_requirements": target_reqs,
                    "planner_mode": planner_mode,
                    "confidence_after": self._confidence_snapshot(),
                }
            )
            self._emit_stage_update(step_num, action, "completed")

        logger.warning("Hit MAX_PLANNING_STEPS (%d), forcing finalize", MAX_PLANNING_STEPS)
        self._workflow_state["issues"].append(f"Planner hit safety cap ({MAX_PLANNING_STEPS})")
        return await self._execute_finalize(goal_payload)

    def _stage_label(self, action: str) -> str:
        cleaned = action.replace("dispatch_", "").replace("request_", "").replace("_", " ").strip()
        return cleaned.title() or "Working"

    def _emit_stage_update(self, step_num: int, action: str, status: str) -> None:
        callback = self._stage_callback
        if not callback:
            return
        try:
            callback(
                {
                    "step": step_num,
                    "action": action,
                    "status": status,
                    "label": f"Step {step_num}: {self._stage_label(action)}",
                    "stages_completed": [entry.get("action", "") for entry in self._workflow_state.get("action_history", [])],
                    "requirements_count": len(self._workflow_state.get("requirements", [])),
                    "decisions_count": len(self._workflow_state.get("decisions", {})),
                }
            )
        except Exception:
            logger.exception("Stage callback failed for action=%s step=%s", action, step_num)

    def _build_state_summary(self) -> str:
        ws = self._workflow_state

        if ws["decisions"]:
            confidences = [
                float(decision.get("confidence", 0.0))
                for decision in ws["decisions"].values()
                if isinstance(decision, dict)
            ]
            low_conf = self._low_confidence_requirement_ids()
            if confidences:
                conf_summary = (
                    f"Range: {min(confidences):.2f} - {max(confidences):.2f}\n"
                    f"Low confidence (<{PLANNER_LOW_CONFIDENCE_THRESHOLD:.2f}): {low_conf if low_conf else 'None'}"
                )
            else:
                conf_summary = "No decisions yet."
        else:
            conf_summary = "No decisions yet."

        issues_text = "\n".join(f"- {issue}" for issue in ws["issues"]) if ws["issues"] else "None"

        recent = ws["action_history"][-5:]
        actions_text = (
            "\n".join(f"- Step {item['step']}: {item['action']} - {item['reasoning']}" for item in recent)
            if recent
            else "None yet"
        )
        action_attempt_counts = ws.get("action_attempt_counts", {})
        counts_text = (
            "\n".join(
                f"- {action}: {count} attempt(s)"
                for action, count in sorted(action_attempt_counts.items())
            )
            if action_attempt_counts
            else "No actions attempted yet."
        )

        if ws["documents"]:
            roles = [
                str(document.get("role", "unknown"))
                for document in ws["documents"]
                if isinstance(document, dict)
            ]
            doc_roles = ", ".join(roles) if roles else "unknown"
        else:
            doc_roles = "None"

        evidence_count = 0
        for value in ws["evidence"].values():
            if isinstance(value, list):
                evidence_count += len(value)
            else:
                evidence_count += 1

        return STATE_SUMMARY_TEMPLATE.format(
            workflow_goal=ws["workflow_goal"],
            workflow_type=ws["workflow_type"],
            document_count=len(ws["documents"]),
            document_roles=doc_roles,
            completed_steps=", ".join(ws["completed_steps"]) or "None",
            requirements_count=len(ws["requirements"]),
            evidence_count=evidence_count,
            decisions_count=len(ws["decisions"]),
            comparison_done=ws["comparison_done"],
            qa_done=ws["qa_done"],
            drafting_done=ws["drafting_done"],
            confidence_summary=conf_summary,
            action_attempt_counts=counts_text,
            issues=issues_text,
            recent_actions=actions_text,
        )

    def _apply_action_retry_cap(
        self,
        action: str,
        reasoning: str,
        target_reqs: list[str],
        parameters: dict,
        planner_mode: str,
    ) -> tuple[str, str, list[str], dict, str]:
        counts = self._workflow_state.setdefault("action_attempt_counts", {})

        if counts.get(action, 0) >= MAX_ACTION_RETRIES and action not in ("finalize", "dispatch_qa"):
            self.logger.warning(
                "Planner chose '%s' but it has been attempted %d times (max %d). Overriding to next logical step.",
                action,
                counts[action],
                MAX_ACTION_RETRIES,
            )
            fallback = self._deterministic_fallback()
            override_action = str(fallback.get("action", "dispatch_qa"))
            override_reasoning = str(fallback.get("reasoning", "Fallback override"))
            override_targets = fallback.get("target_requirements") or []
            override_parameters = fallback.get("parameters") or {}

            if counts.get(override_action, 0) >= MAX_ACTION_RETRIES and override_action not in ("finalize", "dispatch_qa"):
                if not self._workflow_state.get("qa_done"):
                    override_action = "dispatch_qa"
                    override_reasoning = "Fallback override: retries exhausted, proceeding to QA"
                else:
                    override_action = "finalize"
                    override_reasoning = "Fallback override: retries exhausted, finalizing workflow"
                override_targets = []
                override_parameters = {}

            action = override_action
            reasoning = f"Override: {override_reasoning} (previous action hit retry cap)"
            target_reqs = [req for req in override_targets if isinstance(req, str)]
            parameters = override_parameters if isinstance(override_parameters, dict) else {}
            planner_mode = "fallback"

        counts[action] = counts.get(action, 0) + 1
        return action, reasoning, target_reqs, parameters, planner_mode

    def _parse_plan(self, raw: str) -> dict:
        cleaned = (raw or "").strip()
        if cleaned.startswith("```"):
            cleaned = re.sub(r"^```(?:json)?", "", cleaned).strip()
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3].strip()

        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        match = re.search(r"\{[\s\S]*\}", cleaned)
        if match:
            try:
                parsed = json.loads(match.group(0))
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                pass

        logger.warning("Could not parse planner output: %s", (raw or "")[:200])
        return self._deterministic_fallback()

    def _deterministic_fallback(self) -> dict:
        """Pick next logical step based on current state."""
        ws = self._workflow_state

        if "intake" not in ws["completed_steps"]:
            return {
                "action": "dispatch_intake",
                "reasoning": "Fallback: documents not yet parsed",
                "_fallback": True,
            }

        if "extraction" not in ws["completed_steps"]:
            return {
                "action": "dispatch_extraction",
                "reasoning": "Fallback: requirements not extracted",
                "_fallback": True,
            }

        has_prior_docs = any(
            isinstance(document, dict)
            and document.get("role") in ("prior_contract", "amendment", "past_performance")
            for document in ws.get("documents", [])
        )
        if has_prior_docs and not ws["comparison_done"]:
            return {
                "action": "dispatch_comparison",
                "reasoning": "Fallback: prior docs exist, comparison not done",
                "_fallback": True,
            }

        if "retrieval" not in ws["completed_steps"]:
            return {
                "action": "dispatch_retrieval",
                "reasoning": "Fallback: evidence not retrieved",
                "_fallback": True,
            }

        if "compliance" not in ws["completed_steps"]:
            return {
                "action": "dispatch_compliance",
                "reasoning": "Fallback: compliance not assessed",
                "_fallback": True,
            }

        if not ws["qa_done"]:
            return {
                "action": "dispatch_qa",
                "reasoning": "Fallback: QA not done",
                "_fallback": True,
            }

        goal = ws.get("workflow_goal", "")
        if "draft" in str(goal).lower() and not ws["drafting_done"]:
            return {
                "action": "dispatch_drafting",
                "reasoning": "Fallback: drafting requested but not done",
                "_fallback": True,
            }

        return {
            "action": "finalize",
            "reasoning": "Fallback: all steps complete",
            "_fallback": True,
        }

    def _needs_drafting(self) -> bool:
        goal = str(self._workflow_state.get("workflow_goal") or "").lower()
        workflow_type = str(self._workflow_state.get("workflow_type") or "").lower()
        return "draft" in goal or "draft" in workflow_type

    def _low_confidence_requirement_ids(self) -> list[str]:
        low_conf: list[str] = []
        for req_id, decision in self._workflow_state.get("decisions", {}).items():
            if not isinstance(decision, dict):
                continue
            confidence = float(decision.get("confidence", 0.0) or 0.0)
            if confidence < PLANNER_LOW_CONFIDENCE_THRESHOLD:
                low_conf.append(req_id)
        return sorted(set(low_conf))

    def _normalize_decision_requirement_id(self, decision: dict) -> str | None:
        requirement_id = decision.get("requirement_id") or decision.get("req_id")
        if not requirement_id:
            return None
        decision["requirement_id"] = str(requirement_id)
        return decision["requirement_id"]

    def _refresh_low_confidence_issues(self) -> None:
        static_issues = [
            issue
            for issue in self._workflow_state.get("issues", [])
            if not str(issue).startswith("Low confidence (")
        ]
        dynamic_issues = []
        for req_id, decision in self._workflow_state.get("decisions", {}).items():
            if not isinstance(decision, dict):
                continue
            confidence = float(decision.get("confidence", 0.0) or 0.0)
            if confidence < PLANNER_LOW_CONFIDENCE_THRESHOLD:
                dynamic_issues.append(f"Low confidence ({confidence:.2f}) for {req_id}")
        self._workflow_state["issues"] = static_issues + dynamic_issues

    def _confidence_snapshot(self) -> dict[str, float | int | None]:
        decisions = self._workflow_state.get("decisions", {})
        confidences = [
            float(decision.get("confidence", 0.0) or 0.0)
            for decision in decisions.values()
            if isinstance(decision, dict)
        ]
        if not confidences:
            return {}
        return {
            "min": round(min(confidences), 3),
            "max": round(max(confidences), 3),
            "mean": round(sum(confidences) / len(confidences), 3),
            "low_count": sum(1 for confidence in confidences if confidence < PLANNER_LOW_CONFIDENCE_THRESHOLD),
        }

    def _update_state_after_action(self, action: str, target_reqs: list[str]) -> None:
        action_to_step = {
            "dispatch_intake": "intake",
            "dispatch_extraction": "extraction",
            "dispatch_retrieval": "retrieval",
            "dispatch_compliance": "compliance",
            "dispatch_comparison": "comparison",
            "dispatch_qa": "qa",
            "dispatch_drafting": "drafting",
            "request_reanalysis": "reanalysis",
        }
        step_name = action_to_step.get(action)
        if step_name and step_name not in self._workflow_state["completed_steps"]:
            self._workflow_state["completed_steps"].append(step_name)

        if action == "dispatch_comparison":
            self._workflow_state["comparison_done"] = True
        elif action == "dispatch_qa":
            self._workflow_state["qa_done"] = True
        elif action == "dispatch_drafting":
            self._workflow_state["drafting_done"] = True
        elif action == "request_reanalysis":
            self._workflow_state["reanalysis_done"] = True

    async def _execute_intake(self, goal_payload: dict) -> dict | None:
        self.workflow_state["phase"] = "intake"
        result = await self.ask_agent(
            "intake_agent",
            {
                "action": "process_documents",
                "documents": goal_payload.get("documents", []),
            },
        )
        if result is None or result.type == MessageType.ERROR:
            return self._handle_error("intake", result)

        payload = result.payload or {}
        self._workflow_state["parsed_documents"] = payload.get("parsed_documents", [])
        self._workflow_state["all_chunks"] = payload.get("all_chunks", [])
        self._workflow_state["document_manifest"] = payload.get("document_manifest", {})
        parsed_documents = payload.get("parsed_documents", [])
        if parsed_documents:
            self._workflow_state["documents"] = [
                {
                    "path": document.get("path"),
                    "role": document.get("role", "unknown"),
                }
                for document in parsed_documents
            ]
        return None

    async def _execute_extraction(self, goal_payload: dict) -> dict | None:
        del goal_payload
        self.workflow_state["phase"] = "extraction"

        parsed_documents = self._workflow_state.get("parsed_documents", [])
        if not parsed_documents:
            self._workflow_state["issues"].append("Extraction requested before intake produced parsed documents")
            return None

        result = await self.ask_agent(
            "extraction_agent",
            {
                "action": "extract_and_classify",
                "parsed_documents": parsed_documents,
            },
        )
        if result is None or result.type == MessageType.ERROR:
            return self._handle_error("extraction", result)

        requirements = (result.payload or {}).get("requirements", [])
        self._workflow_state["requirements"] = requirements
        self._workflow_state["requirements_by_id"] = {
            requirement.get("req_id"): requirement
            for requirement in requirements
            if isinstance(requirement, dict) and requirement.get("req_id")
        }
        return None

    async def _execute_retrieval(
        self,
        goal_payload: dict,
        target_reqs: list[str] | None = None,
        parameters: dict | None = None,
    ) -> dict | None:
        del goal_payload
        self.workflow_state["phase"] = "retrieval"

        target_reqs = target_reqs or []
        requirements = self._workflow_state.get("requirements", [])
        if target_reqs:
            target_set = {req_id for req_id in target_reqs if isinstance(req_id, str)}
            requirements = [
                requirement
                for requirement in requirements
                if isinstance(requirement, dict) and requirement.get("req_id") in target_set
            ]

        if not requirements:
            self._workflow_state["issues"].append("Retrieval requested but no requirements are available")
            return None

        corpus_chunks = [
            chunk
            for chunk in self._workflow_state.get("all_chunks", [])
            if isinstance(chunk, dict) and chunk.get("role") != "solicitation_or_requirement_source"
        ]

        payload = {
            "action": "build_index_and_retrieve",
            "requirements": requirements,
            "corpus_chunks": corpus_chunks,
        }
        if parameters:
            payload["parameters"] = parameters

        result = await self.ask_agent("retrieval_agent", payload)
        if result is None or result.type == MessageType.ERROR:
            return self._handle_error("retrieval", result)

        retrieval_payload = dict(result.payload or {})
        retrieval_plans = retrieval_payload.pop("retrieval_plans", {})
        raw_evidence_map = retrieval_payload.get("evidence_map", retrieval_payload)
        if isinstance(raw_evidence_map, dict):
            for requirement_id, evidence_items in raw_evidence_map.items():
                if isinstance(requirement_id, str) and isinstance(evidence_items, list):
                    self._workflow_state["evidence"][requirement_id] = evidence_items
        if isinstance(retrieval_plans, dict):
            self._workflow_state["retrieval_plans"].update(retrieval_plans)
        return None

    async def _execute_compliance(self, goal_payload: dict, target_reqs: list[str] | None = None) -> dict | None:
        del goal_payload
        self.workflow_state["phase"] = "compliance_reasoning"

        requirements = self._workflow_state.get("requirements", [])
        evidence_map = self._workflow_state.get("evidence", {})
        target_reqs = target_reqs or []

        if target_reqs:
            target_set = {req_id for req_id in target_reqs if isinstance(req_id, str)}
            requirements = [
                requirement
                for requirement in requirements
                if isinstance(requirement, dict) and requirement.get("req_id") in target_set
            ]
            evidence_map = {
                req_id: evidence_map.get(req_id, [])
                for req_id in target_set
            }

        if not requirements:
            self._workflow_state["issues"].append("Compliance requested but no requirements are available")
            return None

        result = await self.ask_agent(
            "compliance_agent",
            {
                "action": "assess_compliance",
                "requirements": requirements,
                "evidence_map": evidence_map,
            },
        )
        if result is None or result.type == MessageType.ERROR:
            return self._handle_error("compliance", result)

        payload = result.payload or {}
        updated_requirement_ids: set[str] = set()
        for decision in payload.get("decisions", []):
            if not isinstance(decision, dict):
                continue
            req_id = self._normalize_decision_requirement_id(decision)
            if not req_id:
                continue
            self._workflow_state["decisions"][req_id] = decision
            updated_requirement_ids.add(req_id)

        review_queue = payload.get("review_queue", [])
        if isinstance(review_queue, list):
            combined = set(self._workflow_state.get("review_queue", []))
            combined.update(str(item) for item in review_queue)
            self._workflow_state["review_queue"] = sorted(combined)

        self._refresh_low_confidence_issues()
        self.logger.info(
            "POST-COMPLIANCE updated=%d state decisions count=%d, sample confidence=%s",
            len(updated_requirement_ids),
            len(self._workflow_state["decisions"]),
            {
                k: v.get("confidence")
                for k, v in list(self._workflow_state["decisions"].items())[:3]
            }
            if self._workflow_state["decisions"]
            else "empty",
        )
        return None

    async def _execute_comparison(self, goal_payload: dict) -> dict | None:
        del goal_payload
        self.workflow_state["phase"] = "comparison"
        manifest = self._workflow_state.get("document_manifest", {})
        source_path = manifest.get("primary_source")
        prior_paths = manifest.get("prior_context", [])

        if not source_path or not prior_paths:
            self._workflow_state["issues"].append("Comparison requested without source/prior context")
            self._workflow_state["comparison_done"] = True
            return None

        result = await self.ask_agent(
            "comparison_agent",
            {
                "action": "compare_documents",
                "source_path": source_path,
                "prior_paths": prior_paths,
            },
        )
        if result is None or result.type == MessageType.ERROR:
            return self._handle_error("comparison", result)

        self._workflow_state["comparison_summary"] = result.payload
        self._workflow_state["comparison_done"] = True
        return None

    async def _execute_qa(self, goal_payload: dict) -> dict | None:
        del goal_payload
        self.workflow_state["phase"] = "qa"

        result = await self.ask_agent(
            "qa_agent",
            {
                "action": "final_qa_check",
                "decisions": list(self._workflow_state.get("decisions", {}).values()),
                "requirements": self._workflow_state.get("requirements", []),
            },
        )
        if result is None or result.type == MessageType.ERROR:
            return self._handle_error("qa", result)

        qa_payload = result.payload or {}
        self._workflow_state["qa_report"] = qa_payload
        self._workflow_state["qa_done"] = True
        if qa_payload.get("requires_approval"):
            self.workflow_state["phase"] = "approval_pending"
            logger.info("Approval gate reached; auto-approving in demo mode.")
        return None

    async def _execute_drafting(self, goal_payload: dict) -> dict | None:
        del goal_payload
        self.workflow_state["phase"] = "drafting"

        result = await self.ask_agent(
            "drafting_agent",
            {
                "action": "draft_proposal",
                "requirements": self._workflow_state.get("requirements", []),
                "decisions": list(self._workflow_state.get("decisions", {}).values()),
                "comparison_summary": self._workflow_state.get("comparison_summary"),
                "evidence_map": self._workflow_state.get("evidence", {}),
            },
        )
        if result is None or result.type == MessageType.ERROR:
            return self._handle_error("drafting", result)

        draft_bundle = (result.payload or {}).get("draft")
        self._workflow_state["draft"] = draft_bundle
        self._workflow_state["drafting_done"] = True
        return None

    async def _execute_reanalysis(self, goal_payload: dict, target_reqs: list[str]) -> dict | None:
        del goal_payload
        self.workflow_state["phase"] = "reanalysis"

        targets = [req_id for req_id in (target_reqs or []) if isinstance(req_id, str)]
        if not targets:
            targets = self._low_confidence_requirement_ids()
        if not targets:
            self._workflow_state["issues"].append("Reanalysis requested without target requirements")
            return None

        requirements_by_id = self._workflow_state.get("requirements_by_id", {})
        items = [requirements_by_id[req_id] for req_id in targets if req_id in requirements_by_id]
        if not items:
            self._workflow_state["issues"].append("Reanalysis targets did not match known requirements")
            return None

        # Force a retrieval variant during reanalysis so retries are not identical to the initial pass.
        await self._execute_retrieval(
            goal_payload={},
            target_reqs=targets,
            parameters={
                "retrieval_strategy": "bm25_heavy",
                "expand_queries": True,
                "semantic_top_k": config.RETRIEVAL_MAX_TOP_K,
                "lexical_top_k": config.RETRIEVAL_MAX_TOP_K,
                "top_k": config.RETRIEVAL_MAX_TOP_K,
            },
        )

        result = await self._spawn_reanalysis_subagent(
            items,
            {
                "evidence_map": self._workflow_state.get("evidence", {}),
                "requirements_by_id": requirements_by_id,
            },
        )

        updated_requirement_ids: set[str] = set()
        for decision in result.get("decisions", []):
            if not isinstance(decision, dict):
                continue
            req_id = self._normalize_decision_requirement_id(decision)
            if req_id:
                self._workflow_state["decisions"][req_id] = decision
                updated_requirement_ids.add(req_id)

        review_queue = result.get("review_queue", [])
        if isinstance(review_queue, list):
            combined = set(self._workflow_state.get("review_queue", []))
            combined.update(str(item) for item in review_queue)
            self._workflow_state["review_queue"] = sorted(combined)

        self._refresh_low_confidence_issues()
        self.logger.info(
            "POST-REANALYSIS updated=%d state decisions count=%d, sample confidence=%s",
            len(updated_requirement_ids),
            len(self._workflow_state["decisions"]),
            {
                k: v.get("confidence")
                for k, v in list(self._workflow_state["decisions"].items())[:3]
            }
            if self._workflow_state["decisions"]
            else "empty",
        )
        self._workflow_state["reanalysis_done"] = True
        return None

    async def _execute_finalize(self, goal_payload: dict) -> dict:
        self.workflow_state["phase"] = "finalize"

        decisions = [
            self._workflow_state["decisions"][req_id]
            for req_id in sorted(self._workflow_state.get("decisions", {}).keys())
        ]
        outputs = {
            "requirements": self._workflow_state.get("requirements", []),
            "evidence_map": self._workflow_state.get("evidence", {}),
            "retrieval_plans": self._workflow_state.get("retrieval_plans", {}),
            "decisions": decisions,
            "review_queue": self._workflow_state.get("review_queue", []),
            "comparison_summary": self._workflow_state.get("comparison_summary"),
            "document_manifest": self._workflow_state.get("document_manifest", {}),
        }

        step_pairs = [(step_name, "completed") for step_name in self._workflow_state.get("completed_steps", [])]
        qa_report = self._workflow_state.get("qa_report", {})
        if qa_report.get("requires_approval"):
            step_pairs.append(("approval", "auto_approved_demo_mode"))

        self.workflow_state["completed_steps"] = step_pairs
        self.workflow_state["outputs"] = outputs

        return {
            "workflow": "compliance_review",
            "run_id": goal_payload.get("run_id"),
            "steps": step_pairs,
            "outputs": outputs,
            "qa_report": qa_report,
            "planning_trace": self._workflow_state.get("action_history", []),
            "audit_log": self.bus.get_audit_log(),
        }

    async def _spawn_reanalysis_subagent(self, items: list, retrieval_context: dict) -> dict:
        from .compliance_agent import ComplianceAgent as AutonomousComplianceAgent

        sub_id = f"reanalysis_sub_{uuid.uuid4().hex[:6]}"
        logger.info("Spawning sub-agent %s for %s low-confidence items", sub_id, len(items))

        AutonomousComplianceAgent(
            agent_id=sub_id,
            bus=self.bus,
            skill_registry=self.skills,
            config_overrides={"top_k": 10, "temperature": 0.1},
        )
        self.workflow_state["active_sub_agents"][sub_id] = "running"
        self.report_status(
            f"Orchestrator spawned compliance reanalysis sub-agent {sub_id} for {len(items)} low-confidence requirements"
        )

        result = await self.ask_agent(
            sub_id,
            {
                "action": "reanalyze",
                "items": items,
                "context": retrieval_context,
            },
        )

        self.bus.unregister_agent(sub_id, reason="reanalysis_complete")
        self.workflow_state["active_sub_agents"][sub_id] = "terminated"
        self.report_status(f"Orchestrator terminated reanalysis sub-agent {sub_id}")

        if result is None or result.type == MessageType.ERROR:
            return {"decisions": [], "review_queue": [item["req_id"] for item in items]}
        return result.payload

    async def _run_drafting_workflow(self, goal: dict) -> dict:
        compliance_result = await self._run_compliance_workflow({**goal, "task": "compliance_review"})
        outputs = compliance_result.get("outputs", {})
        draft_result = await self.ask_agent(
            "drafting_agent",
            {
                "action": "draft_proposal",
                "requirements": outputs.get("requirements", []),
                "decisions": outputs.get("decisions", []),
                "comparison_summary": outputs.get("comparison_summary"),
                "evidence_map": outputs.get("evidence_map", {}),
            },
        )
        draft_iterations = []
        if draft_result and draft_result.type != MessageType.ERROR:
            draft_bundle = draft_result.payload["draft"]
            draft_iterations.append(
                {
                    "iteration": 1,
                    "action": "draft_proposal",
                    "draft": draft_bundle,
                }
            )
            self.report_status("Orchestrator sent first draft to QA for critique")

            draft_review = await self.ask_agent(
                "qa_agent",
                {
                    "action": "review_draft",
                    "draft": draft_bundle,
                    "requirements": outputs.get("requirements", []),
                    "decisions": outputs.get("decisions", []),
                },
            )
            if draft_review and draft_review.type != MessageType.ERROR:
                draft_iterations.append(
                    {
                        "iteration": 1,
                        "action": "review_draft",
                        "review": draft_review.payload,
                    }
                )

                iteration = 0
                while draft_review.payload.get("requires_rewrite") and iteration < config.MAX_REWRITE_ITERATIONS:
                    iteration += 1
                    self.report_status(
                        f"Orchestrator running drafting self-critique loop iteration {iteration}"
                    )
                    rewrite = await self.ask_agent(
                        "drafting_agent",
                        {
                            "action": "rewrite_sections",
                            "draft_bundle": draft_bundle,
                            "issues": draft_review.payload.get("issues", []),
                        },
                    )
                    if rewrite is None or rewrite.type == MessageType.ERROR:
                        break
                    draft_bundle = rewrite.payload["draft"]
                    draft_iterations.append(
                        {
                            "iteration": iteration,
                            "action": "rewrite_sections",
                            "draft": draft_bundle,
                        }
                    )
                    draft_review = await self.ask_agent(
                        "qa_agent",
                        {
                            "action": "review_draft",
                            "draft": draft_bundle,
                            "requirements": outputs.get("requirements", []),
                            "decisions": outputs.get("decisions", []),
                        },
                    )
                    if draft_review is None or draft_review.type == MessageType.ERROR:
                        break
                    draft_iterations.append(
                        {
                            "iteration": iteration + 1,
                            "action": "review_draft",
                            "review": draft_review.payload,
                        }
                    )

                compliance_result["draft_review"] = draft_review.payload
            compliance_result["draft"] = draft_bundle
            compliance_result["draft_iterations"] = draft_iterations
        compliance_result["workflow"] = "proposal_drafting"
        compliance_result.setdefault("steps", []).append(("drafting", "completed"))
        compliance_result["audit_log"] = self.bus.get_audit_log()
        return compliance_result

    async def _run_comparison_workflow(self, goal: dict) -> dict:
        intake_result = await self.ask_agent(
            "intake_agent",
            {
                "action": "process_documents",
                "documents": goal.get("documents", []),
            },
        )
        if intake_result is None or intake_result.type == MessageType.ERROR:
            return self._handle_error("intake", intake_result)

        manifest = intake_result.payload["document_manifest"]
        comparison_result = await self.ask_agent(
            "comparison_agent",
            {
                "action": "compare_documents",
                "source_path": manifest["primary_source"],
                "prior_paths": manifest.get("prior_context", []),
            },
        )
        if comparison_result is None or comparison_result.type == MessageType.ERROR:
            return self._handle_error("comparison", comparison_result)

        return {
            "workflow": "comparison",
            "run_id": goal.get("run_id"),
            "steps": [("intake", "completed"), ("comparison", "completed")],
            "outputs": comparison_result.payload,
            "audit_log": self.bus.get_audit_log(),
        }

    async def _run_general_workflow(self, goal: dict) -> dict:
        return await self._run_compliance_workflow(goal)

    def _handle_error(self, step_name: str, error_msg: MCPMessage | None) -> dict:
        payload = {
            "error": "Unknown error",
            "goal": {},
        }
        if error_msg is not None:
            payload = error_msg.payload or payload

        self.workflow_state["errors"].append({"step": step_name, "error": payload})
        count = self.workflow_state["retry_counts"].get(step_name, 0)
        if count < config.MAX_RETRIES:
            self.workflow_state["retry_counts"][step_name] = count + 1
            return {"status": "retry", "step": step_name, "attempt": count + 1}
        return {"status": "failed", "step": step_name, "errors": self.workflow_state["errors"]}
