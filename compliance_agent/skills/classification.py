"""Requirement classification skills."""

from __future__ import annotations

import json

from ..llm import LLMRequest, get_provider, provider_model_for_tier
from ..utils.retry import with_retry
from .registry import Skill


KEYWORD_MAPPING = {
    "obligations": ["shall", "must", "responsible", "ensure", "maintain", "provide"],
    "deliverables": ["deliver", "deliverable", "artifact", "work product"],
    "reporting": ["report", "status", "notify", "update", "governance"],
    "documentation": ["documentation", "manual", "record", "guide"],
    "timelines": ["within", "days", "weeks", "months", "deadline", "milestone"],
    "compliance": ["comply", "compliance", "regulatory", "law", "standard"],
}


async def keyword_classify(requirement_text: str) -> dict:
    text = requirement_text.lower()
    for category, keywords in KEYWORD_MAPPING.items():
        if any(keyword in text for keyword in keywords):
            return {"category": category, "subcategory": None, "confidence": 0.7}
    return {"category": "obligations", "subcategory": None, "confidence": 0.4}


async def llm_classify(requirement_text: str, model: str | None = None) -> dict:
    provider = get_provider()
    if not provider.is_available():
        return await keyword_classify(requirement_text)

    request = LLMRequest(
        model=model or provider_model_for_tier("fast"),
        messages=[
            {
                "role": "system",
                "content": (
                    "Classify this requirement into one of these categories: "
                    "obligations, deliverables, reporting, documentation, timelines, compliance. "
                    "Return JSON with category, subcategory, confidence."
                ),
            },
            {"role": "user", "content": requirement_text},
        ],
        temperature=0.1,
        max_tokens=300,
        response_format={"type": "json_object"},
    )
    try:
        response = await with_retry(lambda: provider.complete(request))
        payload = json.loads(response.content)
        return {
            "category": payload.get("category", "obligations"),
            "subcategory": payload.get("subcategory"),
            "confidence": float(payload.get("confidence", 0.5)),
        }
    except Exception:
        return await keyword_classify(requirement_text)


async def classify_requirements(requirements: list[dict]) -> dict:
    output = []
    for requirement in requirements:
        category = await keyword_classify(requirement["requirement_text"])
        if category["confidence"] < 0.6:
            category = await llm_classify(requirement["requirement_text"])
        output.append({**requirement, **category})
    return {"requirements": output}


def register_skills(registry):
    registry.register(Skill(
        name="keyword_classify",
        description="Classify a requirement with deterministic keyword rules.",
        handler=keyword_classify,
        input_schema={"requirement_text": "str"},
        output_schema={"category": "str", "subcategory": "str|null", "confidence": "float"},
        tags=["classification", "requirements"],
        llm_tier="none",
    ))
    registry.register(Skill(
        name="llm_classify",
        description="Classify a requirement with the configured LLM provider.",
        handler=llm_classify,
        input_schema={"requirement_text": "str", "model": "str"},
        output_schema={"category": "str", "subcategory": "str|null", "confidence": "float"},
        tags=["classification", "requirements", "llm"],
        llm_tier="fast",
    ))
    registry.register(Skill(
        name="classify_requirements",
        description="Classify a list of extracted requirements.",
        handler=classify_requirements,
        input_schema={"requirements": "list[dict]"},
        output_schema={"requirements": "list[dict]"},
        tags=["classification", "requirements", "batch"],
        llm_tier="fast",
    ))
