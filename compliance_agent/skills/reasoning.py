"""Compliance reasoning skills."""

from __future__ import annotations

import json
import logging
import re

from ..constants import (
    LABEL_COMPLIANT,
    LABEL_NOT_ADDRESSED,
    LABEL_NOT_COMPLIANT,
    LABEL_PARTIAL,
)
from ..llm import LLMRequest, get_provider, provider_model_for_tier
from ..utils.retry import with_retry
from .registry import Skill

logger = logging.getLogger(__name__)

FALLBACK_CONFIDENCE_FLOOR = 0.30
FALLBACK_CONFIDENCE_CAP = 0.85
CONTRADICTION_MARKERS = (" not ", "cannot", "unable", "does not", "without")


def _evidence_citation(item: dict) -> str:
    section = item.get("section_title") or item.get("metadata", {}).get("section_title") or ""
    page = item.get("page_range") or item.get("metadata", {}).get("page_range") or ""
    citation = f"{section} {page}".strip()
    return citation or item.get("chunk_id", "")


def _fallback_compliance_assessment(requirement_text: str, evidence_texts: list[str]) -> dict:
    """Run deterministic fallback reasoning for one requirement/evidence set."""
    if not evidence_texts:
        return {
            "label": LABEL_NOT_ADDRESSED,
            "confidence": 0.55,
            "explanation": "No evidence found addressing this requirement.",
            "execution_mode": "fallback_rules",
        }

    combined_evidence = " ".join(evidence_texts).lower()
    req_lower = requirement_text.lower()

    req_numbers = set(re.findall(r"\d+[\.\d]*", req_lower))
    req_acronyms = set(re.findall(r"\b[A-Z]{2,}\b", requirement_text))

    number_matches = sum(1 for number in req_numbers if number in combined_evidence)
    acronym_matches = sum(1 for acronym in req_acronyms if acronym.lower() in combined_evidence)
    total_key_terms = len(req_numbers) + len(req_acronyms)
    key_term_matches = number_matches + acronym_matches
    key_term_ratio = key_term_matches / max(total_key_terms, 1)

    req_words = {
        word
        for word in re.findall(r"\b[a-z0-9]{3,}\b", req_lower)
        if word not in {
            "the", "a", "an", "is", "are", "must", "shall", "will", "be", "to",
            "of", "and", "or", "in", "for", "with", "all", "that", "this", "from",
        }
    }
    evidence_words = set(re.findall(r"\b[a-z0-9]{3,}\b", combined_evidence))
    overlap = len(req_words & evidence_words)
    overlap_ratio = overlap / max(len(req_words), 1)

    if overlap_ratio > 0.5 and key_term_ratio > 0.5:
        label = LABEL_COMPLIANT
        confidence = 0.65 + (overlap_ratio * 0.15) + (key_term_ratio * 0.10)
    elif overlap_ratio > 0.3 or key_term_ratio > 0.3:
        label = LABEL_PARTIAL
        confidence = 0.50 + (overlap_ratio * 0.15)
    elif overlap_ratio > 0.15:
        label = LABEL_PARTIAL
        confidence = 0.40 + (overlap_ratio * 0.10)
    else:
        label = LABEL_NOT_ADDRESSED
        confidence = 0.50 + (1 - overlap_ratio) * 0.10

    confidence = min(max(confidence, FALLBACK_CONFIDENCE_FLOOR), FALLBACK_CONFIDENCE_CAP)
    return {
        "label": label,
        "confidence": round(confidence, 4),
        "explanation": (
            f"Fallback assessment: word overlap {overlap_ratio:.0%}, key term match "
            f"{key_term_ratio:.0%} ({key_term_matches}/{max(total_key_terms, 1)} key terms found in evidence)."
        ),
        "execution_mode": "fallback_rules",
    }


def _signal_profile(requirement_text: str, evidence_texts: list[str]) -> dict:
    combined = " ".join(evidence_texts).lower()
    req_lower = requirement_text.lower()
    req_numbers = set(re.findall(r"\d+[\.\d]*", req_lower))
    req_acronyms = set(re.findall(r"\b[A-Z]{2,}\b", requirement_text))
    key_terms = {token.lower() for token in req_numbers | req_acronyms}
    key_term_matches = sum(1 for token in key_terms if token in combined)
    key_term_ratio = key_term_matches / max(len(key_terms), 1)
    req_words = {
        word
        for word in re.findall(r"\b[a-z0-9]{3,}\b", req_lower)
        if word not in {
            "the", "a", "an", "is", "are", "must", "shall", "will", "be", "to",
            "of", "and", "or", "in", "for", "with", "all", "that", "this", "from",
            "each", "per", "least", "more", "than", "including",
        }
    }
    evidence_words = set(re.findall(r"\b[a-z0-9]{3,}\b", combined))
    overlap_ratio = len(req_words & evidence_words) / max(len(req_words), 1)
    return {
        "has_quantitative_terms": bool(key_terms),
        "key_term_ratio": key_term_ratio,
        "overlap_ratio": overlap_ratio,
        "has_contradiction": any(marker in combined for marker in CONTRADICTION_MARKERS),
    }


def _calibrate_llm_decision(requirement_text: str, evidence: list[dict], decision: dict) -> dict:
    if decision.get("execution_mode") != "llm":
        return decision
    if not evidence:
        return decision

    label = decision.get("label")
    if label not in {LABEL_NOT_COMPLIANT, LABEL_NOT_ADDRESSED}:
        return decision

    signals = _signal_profile(requirement_text, [item.get("text", "") for item in evidence])

    if label == LABEL_NOT_COMPLIANT and signals["has_contradiction"]:
        return decision

    calibrated = dict(decision)
    if signals["has_quantitative_terms"] and signals["key_term_ratio"] < 0.34:
        calibrated["label"] = LABEL_NOT_ADDRESSED
        calibrated["confidence"] = max(float(decision.get("confidence", 0.6)), 0.65)
    elif signals["overlap_ratio"] >= 0.65 and signals["key_term_ratio"] >= 0.5:
        calibrated["label"] = LABEL_COMPLIANT
        calibrated["confidence"] = max(float(decision.get("confidence", 0.7)), 0.75)
    elif signals["overlap_ratio"] >= 0.35 or signals["key_term_ratio"] >= 0.34:
        calibrated["label"] = LABEL_PARTIAL
        calibrated["confidence"] = max(float(decision.get("confidence", 0.65)), 0.65)
    else:
        calibrated["label"] = LABEL_NOT_ADDRESSED
        calibrated["confidence"] = max(float(decision.get("confidence", 0.6)), 0.60)

    calibrated["explanation"] = (
        f"{calibrated.get('explanation', '').rstrip()} "
        f"Calibration adjusted label via overlap/key-term checks (overlap={signals['overlap_ratio']:.2f}, "
        f"key_terms={signals['key_term_ratio']:.2f})."
    ).strip()
    return calibrated


async def rules_fallback(requirement: dict, evidence: list[dict]) -> dict:
    requirement_id = requirement.get("req_id") or requirement.get("requirement_id") or "unknown"
    if not evidence:
        decision = _fallback_compliance_assessment(requirement["requirement_text"], [])
        decision.update({
            "evidence_chunk_ids": [],
            "suggested_edits": [f"Add explicit language covering: {requirement['requirement_text']}"],
        })
        validated = await validate_citations(decision, evidence)
        logger.debug(
            "REASONING DIAGNOSTIC req=%s label=%s confidence=%s execution_mode=%s evidence_count=%d",
            requirement_id,
            validated.get("label"),
            validated.get("confidence"),
            validated.get("execution_mode"),
            len(evidence),
        )
        return validated

    assessment = _fallback_compliance_assessment(
        requirement["requirement_text"],
        [item.get("text", "") for item in evidence],
    )
    chunk_ids = [
        item.get("chunk_id")
        for item in evidence
        if item.get("chunk_id")
    ][:3]
    decision = {
        "label": assessment["label"],
        "confidence": max(float(assessment["confidence"]), FALLBACK_CONFIDENCE_FLOOR),
        "explanation": assessment["explanation"],
        "evidence_chunk_ids": chunk_ids,
        "suggested_edits": (
            []
            if assessment["label"] == LABEL_COMPLIANT
            else ["Add clearer, evidence-backed coverage."]
        ),
        "execution_mode": "fallback_rules",
    }
    validated = await validate_citations(decision, evidence)
    logger.debug(
        "REASONING DIAGNOSTIC req=%s label=%s confidence=%s execution_mode=%s evidence_count=%d",
        requirement_id,
        validated.get("label"),
        validated.get("confidence"),
        validated.get("execution_mode"),
        len(evidence),
    )
    return validated


async def assess_compliance(requirement: dict, evidence: list[dict], model: str | None = None) -> dict:
    requirement_id = requirement.get("req_id") or requirement.get("requirement_id") or "unknown"
    if not evidence:
        return await rules_fallback(requirement, evidence)

    provider = get_provider()
    if not provider.is_available():
        return await rules_fallback(requirement, evidence)

    evidence_text = "\n\n".join(
        f"[{item['chunk_id']}] {item.get('text', '')[:500]}"
        for item in evidence[:5]
    )
    request = LLMRequest(
        model=model or provider_model_for_tier("standard"),
        messages=[
            {
                "role": "system",
                "content": (
                    "Assess requirement compliance. "
                    "Use one of: compliant, partial, not_compliant, not_addressed. "
                    "Return JSON with label, confidence, explanation, evidence_chunk_ids, suggested_edits. "
                    "Only cite chunk IDs from the provided evidence."
                ),
            },
            {
                "role": "user",
                "content": (
                    f"Requirement: {requirement['requirement_text']}\n"
                    f"Conditions: {requirement.get('conditions') or 'None'}\n"
                    f"Evidence:\n{evidence_text}"
                ),
            },
        ],
        temperature=0.1,
        max_tokens=900,
        response_format={"type": "json_object"},
    )

    try:
        response = await with_retry(lambda: provider.complete(request))
        payload = json.loads(response.content)
        result = {
            "label": payload.get("label", LABEL_NOT_ADDRESSED),
            "confidence": float(payload.get("confidence", 0.5)),
            "explanation": payload.get("explanation", ""),
            "evidence_chunk_ids": payload.get("evidence_chunk_ids", []),
            "suggested_edits": payload.get("suggested_edits", []),
            "execution_mode": "llm",
        }
        calibrated = _calibrate_llm_decision(requirement["requirement_text"], evidence, result)
        validated = await validate_citations(calibrated, evidence)
        logger.debug(
            "REASONING DIAGNOSTIC req=%s label=%s confidence=%s execution_mode=%s evidence_count=%d",
            requirement_id,
            validated.get("label"),
            validated.get("confidence"),
            validated.get("execution_mode"),
            len(evidence),
        )
        return validated
    except Exception:
        return await rules_fallback(requirement, evidence)


async def validate_citations(decision: dict, evidence: list[dict]) -> dict:
    valid_chunk_ids = {item["chunk_id"] for item in evidence}
    raw_cited = list(dict.fromkeys(decision.get("evidence_chunk_ids", [])))
    cited = [chunk_id for chunk_id in raw_cited if chunk_id in valid_chunk_ids]
    invalid = [chunk_id for chunk_id in raw_cited if chunk_id not in valid_chunk_ids]
    total_citations = len(raw_cited)
    coverage_denominator = total_citations if total_citations else (1 if evidence else 0)
    coverage = len(cited) / coverage_denominator if coverage_denominator else 1.0
    penalty = 0.0
    if invalid:
        penalty += min(0.35, 0.15 * len(invalid))
    if evidence and not cited and decision.get("label") != LABEL_NOT_ADDRESSED:
        penalty += 0.1

    decision["evidence_chunk_ids"] = cited
    decision["citation_coverage"] = round(coverage, 3)
    decision["invalid_citation_ids"] = invalid
    decision["citation_penalty"] = round(penalty, 3)
    decision["citation_validation_status"] = "valid" if not invalid else "invalid"
    decision["supporting_citations"] = [
        _evidence_citation(item)
        for item in evidence
        if item.get("chunk_id") in cited
    ][:3]
    decision["confidence"] = max(0.0, min(1.0, float(decision.get("confidence", 0.5)) - penalty))

    if cited and not any(chunk_id in decision.get("explanation", "") for chunk_id in cited):
        decision["explanation"] = (
            f"{decision.get('explanation', '').rstrip()} "
            f"Evidence chunks considered: {', '.join(cited)}."
        ).strip()
    if invalid:
        decision["explanation"] = (
            f"{decision.get('explanation', '').rstrip()} "
            f"Invalid citations removed: {', '.join(invalid)}."
        ).strip()
    return decision


def register_skills(registry):
    registry.register(Skill(
        name="rules_fallback",
        description="Fallback compliance reasoning when the LLM is unavailable.",
        handler=rules_fallback,
        input_schema={"requirement": "dict", "evidence": "list[dict]"},
        output_schema={"label": "str", "confidence": "float", "explanation": "str", "evidence_chunk_ids": "list[str]", "citation_coverage": "float"},
        tags=["reasoning", "fallback"],
        llm_tier="none",
    ))
    registry.register(Skill(
        name="assess_compliance",
        description="Assess whether evidence satisfies a requirement.",
        handler=assess_compliance,
        input_schema={"requirement": "dict", "evidence": "list[dict]", "model": "str"},
        output_schema={"label": "str", "confidence": "float", "explanation": "str", "evidence_chunk_ids": "list[str]", "citation_coverage": "float"},
        tags=["reasoning", "compliance", "llm"],
        llm_tier="standard",
    ))
    registry.register(Skill(
        name="validate_citations",
        description="Ensure a compliance decision only cites valid evidence chunk IDs.",
        handler=validate_citations,
        input_schema={"decision": "dict", "evidence": "list[dict]"},
        output_schema={"label": "str", "confidence": "float", "explanation": "str", "evidence_chunk_ids": "list[str]", "citation_coverage": "float"},
        tags=["reasoning", "validation"],
        llm_tier="none",
    ))
