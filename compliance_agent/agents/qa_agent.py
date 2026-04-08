"""QA and approval gate agent."""

from __future__ import annotations

from ..mcp.protocol import ToolSchema
from .base import BaseAgent


class QAAgent(BaseAgent):
    """Runs final quality and approval checks."""

    def __init__(self, agent_id: str = "qa_agent", **kwargs):
        super().__init__(
            agent_id=agent_id,
            role="qa",
            description="Applies QA checks and recommends approval or review.",
            **kwargs,
        )

    def _declare_tools(self) -> list[ToolSchema]:
        return [
            ToolSchema(
                name="qa_check",
                description="Run the final QA gate on workflow outputs.",
                input_schema={"decisions": "list[dict]", "requirements": "list[dict]"},
                output_schema={"overall_pass": "bool", "requires_approval": "bool"},
            ),
            ToolSchema(
                name="review_draft",
                description="Review a draft bundle and return rewrite feedback.",
                input_schema={"draft": "dict", "requirements": "list[dict]", "decisions": "list[dict]|null"},
                output_schema={"overall_pass": "bool", "issues": "list[str]", "requires_rewrite": "bool"},
            )
        ]

    async def execute_goal(self, goal: dict) -> dict:
        action = goal.get("action", "final_qa_check")
        if action == "review_draft":
            return await self.use_skill(
                "review_draft",
                draft=goal.get("draft", {}),
                requirements=goal.get("requirements", []),
                decisions=goal.get("decisions", []),
            )
        if action not in {"final_qa_check", "qa_check", "approve_or_flag"}:
            raise ValueError(f"Unsupported QA action: {action}")
        return await self.use_skill(
            "final_qa_check",
            decisions=goal.get("decisions", []),
            requirements=goal.get("requirements", []),
        )
