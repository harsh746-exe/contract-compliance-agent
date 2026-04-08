"""Historical comparison agent."""

from __future__ import annotations

from pathlib import Path

from ..mcp.protocol import ToolSchema
from .base import BaseAgent


class ComparisonAgent(BaseAgent):
    """Finds useful prior context and summarizes changes."""

    def __init__(self, agent_id: str = "comparison_agent", **kwargs):
        super().__init__(
            agent_id=agent_id,
            role="comparison",
            description="Compares new source material to prior document history.",
            **kwargs,
        )

    def _declare_tools(self) -> list[ToolSchema]:
        return [
            ToolSchema(
                name="compare_documents",
                description="Compare a source document against prior context.",
                input_schema={"source_path": "str", "prior_paths": "list[str]"},
                output_schema={"summary": "str", "documents": "list[dict]"},
            )
        ]

    async def execute_goal(self, goal: dict) -> dict:
        action = goal.get("action", "compare_documents")
        if action not in {"compare_documents", "find_similar_prior"}:
            raise ValueError(f"Unsupported comparison action: {action}")

        source_path = goal["source_path"]
        prior_paths = goal.get("prior_paths", [])
        source_text = Path(source_path).read_text(encoding="utf-8", errors="ignore")
        prior_documents = [
            {"path": path, "text": Path(path).read_text(encoding="utf-8", errors="ignore")}
            for path in prior_paths
        ]
        return await self.use_skill("summarize_changes", source_text=source_text, prior_documents=prior_documents)
