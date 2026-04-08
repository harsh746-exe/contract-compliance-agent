"""Drafting skills."""

from __future__ import annotations

from collections import defaultdict

from .registry import Skill


async def generate_outline(requirements: list[dict], decisions: list[dict], comparison_summary: dict | None = None) -> dict:
    decision_map = {decision["requirement_id"]: decision for decision in decisions}
    grouped = defaultdict(list)
    for requirement in requirements:
        grouped[requirement.get("category", "general")].append(requirement)

    sections = []
    for category, items in grouped.items():
        sections.append({
            "heading": category.replace("_", " ").title(),
            "requirement_ids": [item["req_id"] for item in items],
            "content": " ".join(
                f"{item['req_id']}: {decision_map.get(item['req_id'], {}).get('label', 'unknown')}"
                for item in items
            ),
        })

    if comparison_summary and comparison_summary.get("summary"):
        sections.insert(0, {
            "heading": "Historical Context",
            "requirement_ids": [],
            "content": comparison_summary["summary"],
        })

    return {
        "title": "Generated Proposal Outline",
        "outline": [section["heading"] for section in sections],
        "sections": sections,
    }


async def write_section(section: dict, evidence_map: dict | None = None) -> dict:
    evidence_map = evidence_map or {}
    coverage = []
    for requirement_id in section.get("requirement_ids", []):
        if requirement_id in evidence_map and evidence_map[requirement_id]:
            coverage.append(requirement_id)
    content = (
        f"{section['heading']} addresses requirements {', '.join(section.get('requirement_ids', [])) or 'context only'}. "
        f"Evidence-backed coverage exists for {', '.join(coverage) or 'none'}."
    )
    return {**section, "content": content, "draft_quality": "initial"}


async def rewrite_section(section: dict, issues: list[str] | None = None) -> dict:
    issues = issues or []
    content = section.get("content", "")
    if not content or "TBD" in content or len(content) < 40:
        content = (
            f"{section['heading']} is rewritten to remove placeholders and provide a clearer, "
            f"handoff-ready summary tied to {', '.join(section.get('requirement_ids', [])) or 'supporting context'}."
        )
    else:
        content = (
            f"{content} This revised section grounds the narrative in the available evidence and clarifies any residual gaps "
            f"for requirements {', '.join(section.get('requirement_ids', [])) or 'supporting context'}."
        )
    return {
        **section,
        "content": content,
        "rewrite_issues": issues,
        "draft_quality": "revised",
    }


def register_skills(registry):
    registry.register(Skill(
        name="generate_outline",
        description="Generate a traceable proposal outline from requirements and decisions.",
        handler=generate_outline,
        input_schema={"requirements": "list[dict]", "decisions": "list[dict]", "comparison_summary": "dict|null"},
        output_schema={"title": "str", "outline": "list[str]", "sections": "list[dict]"},
        tags=["drafting", "outline"],
        llm_tier="none",
    ))
    registry.register(Skill(
        name="write_section",
        description="Draft one section with requirement traceability.",
        handler=write_section,
        input_schema={"section": "dict", "evidence_map": "dict|null"},
        output_schema={"section": "dict"},
        tags=["drafting", "write"],
        llm_tier="none",
    ))
    registry.register(Skill(
        name="rewrite_section",
        description="Rewrite a weak section to remove placeholders and improve quality.",
        handler=rewrite_section,
        input_schema={"section": "dict", "issues": "list[str]|null"},
        output_schema={"section": "dict"},
        tags=["drafting", "rewrite"],
        llm_tier="none",
    ))
