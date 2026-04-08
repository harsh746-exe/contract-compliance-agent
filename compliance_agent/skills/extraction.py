"""Requirement extraction skills."""

from __future__ import annotations

import json
import re

from .. import config
from ..llm import LLMRequest, get_provider, provider_model_for_tier
from ..utils.retry import with_retry
from .registry import Skill


def _source_citation(chunk: dict) -> str:
    section = chunk.get("section_title") or "Unknown Section"
    page = chunk.get("page_range") or "N/A"
    return f"{section} {page}".strip()


def _provenance(chunk: dict) -> dict:
    return {
        "source_document": chunk.get("metadata", {}).get("file"),
        "section_title": chunk.get("section_title"),
        "page_range": chunk.get("page_range"),
        "chunk_id": chunk.get("chunk_id"),
    }


def _annotate_requirement(
    item: dict,
    extraction_method: str,
    confidence: float,
    strategy_reason: str | None = None,
    execution_mode: str = "fallback_rules",
) -> dict:
    return {
        **item,
        "extraction_method": extraction_method,
        "extraction_confidence": confidence,
        "strategy_reason": strategy_reason,
        "execution_mode": execution_mode,
    }


async def lexical_extract(
    chunks: list[dict],
    keywords: list[str] | None = None,
    strategy_reason: str | None = None,
) -> dict:
    keywords = keywords or list(config.REQUIREMENT_KEYWORDS)
    requirements = []

    for chunk in chunks:
        sentences = re.split(r"(?<=[.!?])\s+", chunk.get("text", ""))
        for sentence in sentences:
            cleaned = sentence.strip()
            if not cleaned:
                continue
            if any(keyword in cleaned.lower() for keyword in keywords):
                conditions = None
                if re.search(r"\b(if|unless|when|within|after|before)\b", cleaned, re.IGNORECASE):
                    conditions = cleaned
                requirements.append({
                    "requirement_text": cleaned,
                    "source_citation": _source_citation(chunk),
                    "conditions": conditions,
                    "provenance": _provenance(chunk),
                })

    return {
        "requirements": [
            _annotate_requirement(
                item,
                extraction_method="lexical",
                confidence=0.72,
                strategy_reason=strategy_reason,
                execution_mode="fallback_rules",
            )
            for item in requirements
        ],
        "execution_mode": "fallback_rules",
    }


async def split_compound(requirement_text: str) -> dict:
    parts = re.split(r"\s+(?:and|;)\s+", requirement_text.strip())
    atomic = [part.strip() for part in parts if part.strip()]
    return {"requirements": atomic if len(atomic) > 1 else [requirement_text.strip()]}


async def llm_extract(
    chunks: list[dict],
    model: str | None = None,
    strategy_reason: str | None = None,
) -> dict:
    provider = get_provider()
    if not provider.is_available():
        return await lexical_extract(chunks, strategy_reason=strategy_reason)

    joined = "\n\n".join(chunk.get("text", "") for chunk in chunks)[:6000]
    request = LLMRequest(
        model=model or provider_model_for_tier("standard"),
        messages=[
            {
                "role": "system",
                "content": (
                    "Extract atomic contract or policy requirements. "
                    "Return JSON with a top-level key 'requirements'. "
                    "Each item must include requirement_text, source_citation, and conditions."
                ),
            },
            {"role": "user", "content": joined},
        ],
        temperature=0.1,
        max_tokens=1500,
        response_format={"type": "json_object"},
    )

    try:
        response = await with_retry(lambda: provider.complete(request))
        payload = json.loads(response.content)
        requirements = payload.get("requirements", [])
        if not requirements:
            return await lexical_extract(chunks, strategy_reason=strategy_reason)
        normalized = []
        fallback_citation = _source_citation(chunks[0]) if chunks else "Unknown Section"
        for item in requirements:
            normalized.append({
                "requirement_text": item.get("requirement_text", "").strip(),
                "source_citation": item.get("source_citation", fallback_citation),
                "conditions": item.get("conditions"),
                "provenance": _provenance(chunks[0]) if chunks else {},
            })
        return {
            "requirements": [
                _annotate_requirement(
                    item,
                    extraction_method="llm",
                    confidence=0.86,
                    strategy_reason=strategy_reason,
                    execution_mode="llm",
                )
                for item in normalized
                if item["requirement_text"]
            ],
            "execution_mode": "llm",
        }
    except Exception:
        return await lexical_extract(chunks, strategy_reason=strategy_reason)


async def extract_requirements(chunks: list[dict], strategy: str = "hybrid", strategy_reason: str | None = None) -> dict:
    lexical = await lexical_extract(chunks, strategy_reason=strategy_reason)
    refined = await llm_extract(chunks, strategy_reason=strategy_reason)
    merged = refined.get("requirements") or lexical.get("requirements", [])

    deduped = []
    seen = set()
    for item in merged:
        key = re.sub(r"\s+", " ", item["requirement_text"].lower()).strip()
        if key and key not in seen:
            seen.add(key)
            deduped.append(item)

    for index, item in enumerate(deduped, start=1):
        item["req_id"] = f"REQ_{index:04d}"
        item.setdefault("extraction_method", strategy)
        item.setdefault("extraction_confidence", 0.8 if item["extraction_method"] == "llm" else 0.72)
        item.setdefault("strategy_reason", strategy_reason)
        item.setdefault("execution_mode", refined.get("execution_mode", "fallback_rules"))

    return {
        "requirements": deduped,
        "execution_mode": refined.get("execution_mode", lexical.get("execution_mode", "fallback_rules")),
    }


def register_skills(registry):
    registry.register(Skill(
        name="lexical_extract",
        description="Extract candidate requirements from text using lexical cues.",
        handler=lexical_extract,
        input_schema={"chunks": "list[dict]", "keywords": "list[str]", "strategy_reason": "str|null"},
        output_schema={"requirements": "list[dict]"},
        tags=["extraction", "requirements"],
        llm_tier="none",
    ))
    registry.register(Skill(
        name="llm_extract",
        description="Refine and atomize requirements with the configured LLM provider.",
        handler=llm_extract,
        input_schema={"chunks": "list[dict]", "model": "str", "strategy_reason": "str|null"},
        output_schema={"requirements": "list[dict]"},
        tags=["extraction", "requirements", "llm"],
        llm_tier="standard",
    ))
    registry.register(Skill(
        name="split_compound",
        description="Split a compound requirement into atomic units.",
        handler=split_compound,
        input_schema={"requirement_text": "str"},
        output_schema={"requirements": "list[str]"},
        tags=["extraction", "cleanup"],
        llm_tier="none",
    ))
    registry.register(Skill(
        name="extract_requirements",
        description="Run the hybrid extraction pass and return deduplicated requirements.",
        handler=extract_requirements,
        input_schema={"chunks": "list[dict]", "strategy": "str", "strategy_reason": "str|null"},
        output_schema={"requirements": "list[dict]"},
        tags=["extraction", "requirements", "hybrid"],
        llm_tier="standard",
    ))
