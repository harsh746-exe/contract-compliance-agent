"""Requirement extraction and structuring agent."""

from __future__ import annotations

import re

from ..mcp.protocol import ToolSchema
from .base import BaseAgent


class ExtractionAgent(BaseAgent):
    """Autonomously extracts and classifies requirements."""

    def __init__(self, agent_id: str = "extraction_agent", **kwargs):
        super().__init__(
            agent_id=agent_id,
            role="extraction",
            description="Extracts atomic requirements and classifies them.",
            **kwargs,
        )

    def _declare_tools(self) -> list[ToolSchema]:
        return [
            ToolSchema(
                name="extract_requirements",
                description="Extract and classify requirements from parsed source documents.",
                input_schema={"parsed_documents": "list[dict]"},
                output_schema={"requirements": "list[dict]"},
            )
        ]

    async def execute_goal(self, goal: dict) -> dict:
        action = goal.get("action", "extract_and_classify")
        if action not in {"extract_and_classify", "extract_requirements"}:
            raise ValueError(f"Unsupported extraction action: {action}")

        parsed_documents = goal.get("parsed_documents", [])
        source_documents = [
            document
            for document in parsed_documents
            if document.get("role") == "solicitation_or_requirement_source"
        ]
        if not source_documents:
            raise ValueError("No source document available for extraction.")

        strategy = self._choose_strategy(source_documents[0]["chunks"])
        reason = strategy["reason"]
        self.report_status(
            f"Extraction agent chose strategy {strategy['name']} because {reason}"
        )

        if strategy["name"] == "lexical":
            extracted = await self.use_skill(
                "lexical_extract",
                chunks=source_documents[0]["chunks"],
                strategy_reason=reason,
            )
        elif strategy["name"] == "llm":
            extracted = await self.use_skill(
                "llm_extract",
                chunks=source_documents[0]["chunks"],
                strategy_reason=reason,
            )
        else:
            extracted = await self.use_skill(
                "extract_requirements",
                chunks=source_documents[0]["chunks"],
                strategy=strategy["name"],
                strategy_reason=reason,
            )

        for requirement in extracted.get("requirements", []):
            requirement.setdefault("extraction_method", strategy["name"])
            requirement.setdefault("strategy_reason", reason)
        extracted["requirements"] = self._normalize_requirements(extracted.get("requirements", []))

        classified = await self.use_skill("classify_requirements", requirements=extracted["requirements"])
        return classified

    def _choose_strategy(self, chunks: list[dict]) -> dict:
        keyword_hits = 0
        section_titles = 0
        dense_chunks = 0
        messy_markers = 0

        for chunk in chunks:
            text = chunk.get("text", "")
            lowered = text.lower()
            keyword_hits += sum(1 for keyword in ("shall", "must", "required", "provide") if keyword in lowered)
            if chunk.get("section_title") and chunk.get("section_title") != "Unknown Section":
                section_titles += 1
            if len(text.split()) > 90:
                dense_chunks += 1
            if any(marker in lowered for marker in ("...", "table", "appendix", "attachment", "note:")):
                messy_markers += 1

        total_chunks = max(1, len(chunks))
        if section_titles / total_chunks >= 0.6 and keyword_hits >= total_chunks:
            return {
                "name": "lexical",
                "reason": "the source looks structured and lexical requirement cues are strong",
            }
        if dense_chunks or messy_markers:
            return {
                "name": "hybrid",
                "reason": "the source is dense or messy enough that lexical cues should be refined with LLM help",
            }
        return {
            "name": "llm",
            "reason": "the document is lightly structured and benefits from semantic extraction support",
        }

    def _normalize_requirements(self, requirements: list[dict]) -> list[dict]:
        deduped = []
        seen = set()
        for requirement in requirements:
            text = re.sub(r"\s+", " ", requirement.get("requirement_text", "").strip().lower())
            if not text or text in seen:
                continue
            seen.add(text)
            deduped.append(requirement)

        for index, requirement in enumerate(deduped, start=1):
            requirement["req_id"] = f"REQ_{index:04d}"
        return deduped
