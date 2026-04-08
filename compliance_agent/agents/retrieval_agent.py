"""Evidence retrieval and context assembly agent."""

from __future__ import annotations

import re

from .. import config
from ..mcp.protocol import ToolSchema
from .base import BaseAgent


class RetrievalAgent(BaseAgent):
    """Retrieves evidence for each extracted requirement."""

    def __init__(self, agent_id: str = "retrieval_agent", **kwargs):
        super().__init__(
            agent_id=agent_id,
            role="retrieval",
            description="Builds hybrid retrieval context for requirements.",
            **kwargs,
        )

    def _declare_tools(self) -> list[ToolSchema]:
        return [
            ToolSchema(
                name="build_index",
                description="Build hybrid retrieval context and evidence maps.",
                input_schema={"requirements": "list[dict]", "corpus_chunks": "list[dict]"},
                output_schema={"evidence_map": "dict"},
            )
        ]

    async def execute_goal(self, goal: dict) -> dict:
        action = goal.get("action", "build_index_and_retrieve")
        if action not in {"build_index_and_retrieve", "build_index", "retrieve_evidence"}:
            raise ValueError(f"Unsupported retrieval action: {action}")

        requirements = goal.get("requirements", [])
        corpus_chunks = goal.get("corpus_chunks", [])
        parameters = goal.get("parameters", {}) or {}
        retrieval_plans = {}
        for requirement in requirements:
            plan = self._choose_strategy(requirement, parameters=parameters)
            retrieval_plans[requirement["req_id"]] = plan
            self.report_status(
                f"Retrieval agent chose strategy {plan['strategy']} for {requirement['req_id']} because {plan['reason']}"
            )

        evidence_map = await self.use_skill(
            "assemble_context",
            requirements=requirements,
            corpus_chunks=corpus_chunks,
            retrieval_plans=retrieval_plans,
        )
        evidence_map["retrieval_plans"] = retrieval_plans
        return evidence_map

    def _choose_strategy(self, requirement: dict, parameters: dict | None = None) -> dict:
        parameters = parameters or {}
        text = requirement.get("requirement_text", "")
        lowered = text.lower()

        if re.search(r"\b(?:far|dfars|cfr)\s+\d", lowered) or re.search(r"\b\d{2}\.\d{3,}-\d+\b", lowered):
            plan = {
                "strategy": "lexical",
                "reason": "it references a clause or regulation identifier that needs exact matching",
                "weights": {"semantic": 0.2, "lexical": 0.8},
                "top_k": config.RETRIEVAL_MAX_TOP_K,
                "semantic_top_k": config.TOP_K_RETRIEVAL,
                "lexical_top_k": config.RETRIEVAL_MAX_TOP_K,
            }
        elif any(term in lowered for term in ("security", "resilience", "architecture", "capability", "controls", "approach")):
            plan = {
                "strategy": "semantic",
                "reason": "the requirement is conceptual and benefits from semantic similarity over exact keyword overlap",
                "weights": {"semantic": 0.75, "lexical": 0.25},
                "top_k": config.RETRIEVAL_MAX_TOP_K,
                "semantic_top_k": config.RETRIEVAL_MAX_TOP_K,
                "lexical_top_k": config.BM25_TOP_K,
            }
        else:
            plan = {
                "strategy": "hybrid",
                "reason": "the requirement mixes concrete wording with contextual meaning, so balanced hybrid retrieval is safest",
                "weights": {"semantic": 0.5, "lexical": 0.5},
                "top_k": config.RETRIEVAL_MAX_TOP_K,
                "semantic_top_k": config.TOP_K_RETRIEVAL,
                "lexical_top_k": config.BM25_TOP_K,
            }

        override = str(parameters.get("retrieval_strategy", "")).strip().lower()
        if override == "bm25_heavy":
            plan["strategy"] = "bm25_heavy"
            plan["reason"] = "reanalysis requested lexical-heavy retrieval to surface strict term matches"
            plan["weights"] = {"semantic": 0.3, "lexical": 0.7}
            plan["lexical_top_k"] = max(plan["lexical_top_k"], config.RETRIEVAL_MAX_TOP_K)
            plan["semantic_top_k"] = max(plan["semantic_top_k"], config.TOP_K_RETRIEVAL)
        elif override == "semantic_heavy":
            plan["strategy"] = "semantic_heavy"
            plan["reason"] = "reanalysis requested semantic-heavy retrieval to widen contextual matches"
            plan["weights"] = {"semantic": 0.7, "lexical": 0.3}

        if "top_k" in parameters:
            plan["top_k"] = int(parameters["top_k"])
        if "semantic_top_k" in parameters:
            plan["semantic_top_k"] = int(parameters["semantic_top_k"])
        if "lexical_top_k" in parameters:
            plan["lexical_top_k"] = int(parameters["lexical_top_k"])
        if parameters.get("expand_queries"):
            plan["expand_queries"] = True

        return plan
