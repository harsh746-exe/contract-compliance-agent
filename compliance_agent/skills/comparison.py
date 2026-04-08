"""Historical comparison skills."""

from __future__ import annotations

import re
from pathlib import Path

from .registry import Skill


def _terms(text: str) -> set[str]:
    return set(re.findall(r"\b[a-z]{5,}\b", text.lower()))


async def match_prior_docs(source_text: str, prior_documents: list[dict]) -> dict:
    source_terms = _terms(source_text)
    matches = []
    for document in prior_documents:
        prior_text = document.get("text", "")
        prior_terms = _terms(prior_text)
        overlap = sorted(source_terms & prior_terms)
        similarity = len(overlap) / max(1, len(source_terms))
        matches.append({
            "path": document.get("path") or document.get("metadata", {}).get("file"),
            "similarity": round(similarity, 3),
            "overlap_terms": overlap[:12],
        })
    matches.sort(key=lambda item: item["similarity"], reverse=True)
    return {"matches": matches}


async def compute_delta(source_text: str, prior_text: str) -> dict:
    source_terms = _terms(source_text)
    prior_terms = _terms(prior_text)
    return {
        "new_terms": sorted(source_terms - prior_terms)[:20],
        "reused_terms": sorted(source_terms & prior_terms)[:20],
    }


async def summarize_changes(source_text: str, prior_documents: list[dict]) -> dict:
    matches = await match_prior_docs(source_text, prior_documents)
    top = matches["matches"][0] if matches["matches"] else None
    if not top:
        return {"summary": "No prior documents were available for comparison.", "documents": []}
    return {
        "summary": (
            f"Closest historical match: {Path(top['path']).name if top.get('path') else 'unknown'} "
            f"with similarity {top['similarity']:.2f}. "
            f"Likely reusable terms: {', '.join(top['overlap_terms'][:5]) or 'none'}."
        ),
        "documents": matches["matches"],
    }


def register_skills(registry):
    registry.register(Skill(
        name="match_prior_docs",
        description="Rank prior documents by likely relevance to a new source document.",
        handler=match_prior_docs,
        input_schema={"source_text": "str", "prior_documents": "list[dict]"},
        output_schema={"matches": "list[dict]"},
        tags=["comparison", "historical"],
        llm_tier="none",
    ))
    registry.register(Skill(
        name="compute_delta",
        description="Compute reused versus new terms between a source and prior document.",
        handler=compute_delta,
        input_schema={"source_text": "str", "prior_text": "str"},
        output_schema={"new_terms": "list[str]", "reused_terms": "list[str]"},
        tags=["comparison", "delta"],
        llm_tier="none",
    ))
    registry.register(Skill(
        name="summarize_changes",
        description="Summarize likely reuse and delta areas across prior documents.",
        handler=summarize_changes,
        input_schema={"source_text": "str", "prior_documents": "list[dict]"},
        output_schema={"summary": "str", "documents": "list[dict]"},
        tags=["comparison", "summary"],
        llm_tier="none",
    ))
