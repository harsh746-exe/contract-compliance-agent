"""Proposal drafting agent."""

from __future__ import annotations

from ..mcp.protocol import ToolSchema
from .base import BaseAgent


class DraftingAgent(BaseAgent):
    """Produces outlines and section rewrites."""

    def __init__(self, agent_id: str = "drafting_agent", **kwargs):
        super().__init__(
            agent_id=agent_id,
            role="drafting",
            description="Generates proposal outlines and bounded rewrites.",
            **kwargs,
        )

    def _declare_tools(self) -> list[ToolSchema]:
        return [
            ToolSchema(
                name="draft_proposal",
                description="Create an outline and drafted sections.",
                input_schema={"requirements": "list[dict]", "decisions": "list[dict]", "comparison_summary": "dict|null", "evidence_map": "dict|null"},
                output_schema={"draft": "dict"},
            ),
            ToolSchema(
                name="rewrite_sections",
                description="Rewrite weak sections from a draft bundle.",
                input_schema={"draft_bundle": "dict", "issues": "list[str]"},
                output_schema={"draft": "dict"},
            ),
        ]

    async def execute_goal(self, goal: dict) -> dict:
        action = goal.get("action", "draft_proposal")
        if action == "draft_proposal":
            outline = await self.use_skill(
                "generate_outline",
                requirements=goal.get("requirements", []),
                decisions=goal.get("decisions", []),
                comparison_summary=goal.get("comparison_summary"),
            )
            sections = []
            for section in outline["sections"]:
                sections.append(await self.use_skill("write_section", section=section, evidence_map=goal.get("evidence_map", {})))
            outline["sections"] = sections
            return {"draft": outline}
        if action == "rewrite_sections":
            draft_bundle = goal.get("draft_bundle", {})
            issues = goal.get("issues", [])
            rewritten = []
            for section in draft_bundle.get("sections", []):
                rewritten.append(await self.use_skill("rewrite_section", section=section, issues=issues))
            draft_bundle["sections"] = rewritten
            return {"draft": draft_bundle}
        raise ValueError(f"Unsupported drafting action: {action}")
