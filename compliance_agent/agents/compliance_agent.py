"""Autonomous compliance reasoning agent."""

from __future__ import annotations

from copy import deepcopy

from .. import config
from ..mcp.protocol import ToolSchema
from .base import BaseAgent


class ComplianceAgent(BaseAgent):
    """Assesses compliance and supports low-confidence reanalysis."""

    def __init__(self, agent_id: str = "compliance_agent", config_overrides: dict | None = None, **kwargs):
        self.config_overrides = config_overrides or {}
        super().__init__(
            agent_id=agent_id,
            role="compliance",
            description="Assesses requirement compliance using retrieved evidence.",
            **kwargs,
        )

    def _declare_tools(self) -> list[ToolSchema]:
        return [
            ToolSchema(
                name="assess_compliance",
                description="Assess compliance over a requirement/evidence set.",
                input_schema={"requirements": "list[dict]", "evidence_map": "dict"},
                output_schema={"decisions": "list[dict]", "review_queue": "list[str]"},
            ),
            ToolSchema(
                name="reanalyze",
                description="Reanalyze a low-confidence subset with agent-specific overrides.",
                input_schema={"items": "list[dict]", "context": "dict"},
                output_schema={"decisions": "list[dict]", "review_queue": "list[str]"},
            ),
        ]

    async def execute_goal(self, goal: dict) -> dict:
        action = goal.get("action", "assess_compliance")
        if action == "assess_compliance":
            requirements = goal.get("requirements", [])
            evidence_map = goal.get("evidence_map", {})
            return await self._assess(requirements, evidence_map)
        if action == "reanalyze":
            items = goal.get("items", [])
            context = deepcopy(goal.get("context", {}))
            evidence_map = context.get("evidence_map", {})
            requirements = []
            for item in items:
                if "requirement_text" in item:
                    requirements.append(item)
                elif item.get("requirement_id") and context.get("requirements_by_id", {}).get(item["requirement_id"]):
                    requirements.append(context["requirements_by_id"][item["requirement_id"]])
            return await self._assess(requirements, evidence_map)
        raise ValueError(f"Unsupported compliance action: {action}")

    async def _assess(self, requirements: list[dict], evidence_map: dict) -> dict:
        decisions = []
        for requirement in requirements:
            evidence = evidence_map.get(requirement["req_id"], [])
            primary_evidence = evidence[: min(3, len(evidence))]
            decision = await self.use_skill("assess_compliance", requirement=requirement, evidence=primary_evidence)
            decision["requirement_id"] = requirement["req_id"]
            decision = await self.use_skill("score_confidence", decision=decision, evidence=primary_evidence)

            if decision.get("confidence", 0.0) < config.CONFIDENCE_THRESHOLD and len(evidence) > len(primary_evidence):
                self.report_status(
                    f"Compliance agent self-correcting for {requirement['req_id']} by reviewing more evidence before human escalation"
                )
                reconsidered = await self.use_skill(
                    "assess_compliance",
                    requirement=requirement,
                    evidence=evidence,
                )
                reconsidered["requirement_id"] = requirement["req_id"]
                reconsidered["self_correcting"] = True
                reconsidered["self_correcting_note"] = "Expanded evidence review triggered before escalation."
                reconsidered = await self.use_skill("score_confidence", decision=reconsidered, evidence=evidence)
                if reconsidered.get("confidence", 0.0) >= decision.get("confidence", 0.0):
                    decision = reconsidered

            decisions.append(decision)

        review = await self.use_skill("flag_low_confidence", decisions=decisions)
        return {
            "decisions": decisions,
            "review_queue": review["review_queue"],
        }
