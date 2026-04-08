"""QA skills."""

from __future__ import annotations

import re

from .registry import Skill


async def check_acronyms(text: str) -> dict:
    acronyms = re.findall(r"\b[A-Z]{2,}\b", text)
    return {"acronyms": sorted(set(acronyms))}


async def detect_placeholders(text: str) -> dict:
    placeholders = [token for token in ("TBD", "TODO", "[INSERT", "lorem ipsum") if token.lower() in text.lower()]
    return {"placeholders": placeholders}


async def format_check(text: str) -> dict:
    return {
        "has_double_blank_lines": "\n\n\n" in text,
        "line_count": len(text.splitlines()),
    }


async def coverage_check(requirements: list[dict], decisions: list[dict]) -> dict:
    decision_ids = {decision["requirement_id"] for decision in decisions}
    missing = [requirement["req_id"] for requirement in requirements if requirement["req_id"] not in decision_ids]
    return {"missing_requirement_ids": missing}


async def review_draft(draft: dict, requirements: list[dict], decisions: list[dict] | None = None) -> dict:
    decisions = decisions or []
    issues = []
    section_feedback = []
    covered_requirements = set()

    for section in draft.get("sections", []):
        content = section.get("content", "")
        section_issues = []
        if section.get("draft_quality") != "revised":
            section_issues.append("has not yet gone through the critique-and-rewrite pass")
        placeholders = (await detect_placeholders(content))["placeholders"]
        if placeholders:
            section_issues.append(f"contains placeholders: {', '.join(placeholders)}")
        if len(content.strip()) < 60:
            section_issues.append("needs more grounded detail")
        if "Evidence-backed coverage exists for none" in content:
            section_issues.append("does not cite evidence-backed coverage")

        covered_requirements.update(section.get("requirement_ids", []))
        if section_issues:
            issues.append(f"{section.get('heading', 'Untitled Section')}: " + "; ".join(section_issues))
        section_feedback.append({
            "heading": section.get("heading", "Untitled Section"),
            "issues": section_issues,
        })

    missing_requirement_ids = [
        requirement["req_id"]
        for requirement in requirements
        if requirement["req_id"] not in covered_requirements
    ]
    if missing_requirement_ids:
        issues.append(
            "Draft does not cover requirements: " + ", ".join(missing_requirement_ids)
        )

    return {
        "overall_pass": not issues,
        "issues": issues,
        "missing_requirement_ids": missing_requirement_ids,
        "section_feedback": section_feedback,
        "requires_rewrite": bool(issues),
    }


async def final_qa_check(decisions: list[dict], requirements: list[dict]) -> dict:
    review_required = [decision["requirement_id"] for decision in decisions if decision.get("review_required")]
    missing = (await coverage_check(requirements, decisions))["missing_requirement_ids"]
    overall_pass = not review_required and not missing
    return {
        "overall_pass": overall_pass,
        "requires_approval": bool(review_required),
        "review_required": review_required,
        "missing_requirement_ids": missing,
    }


def register_skills(registry):
    registry.register(Skill(
        name="check_acronyms",
        description="Find acronym-like tokens in text.",
        handler=check_acronyms,
        input_schema={"text": "str"},
        output_schema={"acronyms": "list[str]"},
        tags=["qa", "text"],
        llm_tier="none",
    ))
    registry.register(Skill(
        name="detect_placeholders",
        description="Detect placeholder text in draft content.",
        handler=detect_placeholders,
        input_schema={"text": "str"},
        output_schema={"placeholders": "list[str]"},
        tags=["qa", "draft"],
        llm_tier="none",
    ))
    registry.register(Skill(
        name="format_check",
        description="Perform lightweight formatting checks.",
        handler=format_check,
        input_schema={"text": "str"},
        output_schema={"has_double_blank_lines": "bool", "line_count": "int"},
        tags=["qa", "format"],
        llm_tier="none",
    ))
    registry.register(Skill(
        name="coverage_check",
        description="Check whether every requirement has a decision.",
        handler=coverage_check,
        input_schema={"requirements": "list[dict]", "decisions": "list[dict]"},
        output_schema={"missing_requirement_ids": "list[str]"},
        tags=["qa", "coverage"],
        llm_tier="none",
    ))
    registry.register(Skill(
        name="review_draft",
        description="Evaluate draft quality and recommend whether a rewrite pass is needed.",
        handler=review_draft,
        input_schema={"draft": "dict", "requirements": "list[dict]", "decisions": "list[dict]|null"},
        output_schema={"overall_pass": "bool", "issues": "list[str]", "requires_rewrite": "bool"},
        tags=["qa", "draft", "review"],
        llm_tier="none",
    ))
    registry.register(Skill(
        name="final_qa_check",
        description="Run the final QA gate on decisions and requirements.",
        handler=final_qa_check,
        input_schema={"decisions": "list[dict]", "requirements": "list[dict]"},
        output_schema={"overall_pass": "bool", "requires_approval": "bool"},
        tags=["qa", "gate"],
        llm_tier="none",
    ))
