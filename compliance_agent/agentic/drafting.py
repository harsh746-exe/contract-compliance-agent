"""Proposal drafting and bounded rewrite helpers for agentic workflows."""

from __future__ import annotations

from collections import defaultdict
from typing import Dict, List, Optional

from ..memory.persistent_store import ComplianceDecision, Requirement
from ..runtime import require_langchain_llm_runtime


class ProposalDrafter:
    """Generates a bounded response outline and section-level draft."""

    def __init__(self, llm=None):
        self.llm = llm

    def draft_outline(
        self,
        requirements: List[Requirement],
        decisions: List[ComplianceDecision],
        comparison_summary: Optional[Dict] = None,
    ) -> Dict:
        """Build a first-pass response outline with traceability."""
        grouped: Dict[str, List[Requirement]] = defaultdict(list)
        decision_map = {decision.requirement_id: decision for decision in decisions}
        for requirement in requirements:
            grouped[requirement.category or "general"].append(requirement)

        sections = []
        for category, reqs in grouped.items():
            section_title = category.replace("_", " ").title()
            requirement_ids = [req.req_id for req in reqs]
            status_summary = ", ".join(
                f"{req.req_id}: {decision_map.get(req.req_id).label if decision_map.get(req.req_id) else 'unknown'}"
                for req in reqs
            )
            content = (
                f"This section addresses {section_title.lower()} requirements. "
                f"Key items include {', '.join(req.requirement_text for req in reqs[:2])}. "
                f"Current compliance traceability: {status_summary}."
            )
            sections.append({
                "heading": section_title,
                "content": content,
                "requirement_ids": requirement_ids,
            })

        if comparison_summary and comparison_summary.get("summary"):
            sections.insert(0, {
                "heading": "Historical Context",
                "content": comparison_summary["summary"],
                "requirement_ids": [],
            })

        outline = [section["heading"] for section in sections]
        draft = {
            "title": "Agentic Proposal Response Outline",
            "outline": outline,
            "sections": sections,
            "traceability": {section["heading"]: section["requirement_ids"] for section in sections},
        }

        if self.llm is not None:
            enriched = self._llm_draft(requirements, sections, comparison_summary)
            if enriched:
                draft = enriched

        return draft

    def _llm_draft(self, requirements, sections, comparison_summary) -> Optional[Dict]:
        require_langchain_llm_runtime()
        from langchain.prompts import ChatPromptTemplate

        prompt = ChatPromptTemplate.from_messages([
            ("system", """Create a concise proposal outline with JSON fields:
- title
- outline
- sections (array of heading, content, requirement_ids)
- traceability

Keep the response bounded and grounded in the supplied requirement IDs."""),
            ("human", "Requirements: {requirements}\n\nSeed sections: {sections}\n\nComparison: {comparison}"),
        ])
        try:
            response = self.llm.invoke(prompt.format_messages(
                requirements=str([(req.req_id, req.requirement_text) for req in requirements]),
                sections=str(sections),
                comparison=str(comparison_summary or {}),
            ))
            content = response.content.strip()
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            import json
            return json.loads(content)
        except Exception:
            return None


class DraftEvaluator:
    """Evaluates whether a bounded draft is complete enough for handoff."""

    def evaluate(self, draft_bundle: Dict, requirement_ids: List[str]) -> Dict:
        traceability = draft_bundle.get("traceability", {})
        covered = set()
        for ids in traceability.values():
            covered.update(ids)

        issues = []
        for requirement_id in requirement_ids:
            if requirement_id not in covered:
                issues.append(f"Missing traceability for {requirement_id}")

        for section in draft_bundle.get("sections", []):
            if "TBD" in section.get("content", "") or len(section.get("content", "").strip()) < 20:
                issues.append(f"Weak section content in {section.get('heading', 'unknown')}")

        return {
            "issues": issues,
            "status": "needs_revision" if issues else "ready",
        }


class DraftRewriter:
    """Performs bounded draft rewrites based on evaluator findings."""

    def rewrite(self, draft_bundle: Dict, evaluation: Dict) -> Dict:
        updated = dict(draft_bundle)
        updated_sections = []

        for section in draft_bundle.get("sections", []):
            content = section.get("content", "")
            if "TBD" in content or len(content.strip()) < 20:
                content = (
                    f"{section.get('heading', 'Section')} expands the draft with a clearer response. "
                    f"It explicitly ties the section to requirements {', '.join(section.get('requirement_ids', [])) or 'context-only material'}."
                )
            updated_sections.append({
                **section,
                "content": content,
            })

        updated["sections"] = updated_sections
        updated["traceability"] = {
            section["heading"]: section.get("requirement_ids", [])
            for section in updated_sections
        }
        updated["rewrite_notes"] = evaluation.get("issues", [])
        return updated
