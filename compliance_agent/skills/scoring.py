"""Confidence scoring skills."""

from __future__ import annotations

import logging

from .. import config
from .registry import Skill

logger = logging.getLogger(__name__)
SCORING_CONFIDENCE_FLOOR = 0.20
SCORING_CONFIDENCE_CAP = 0.85


async def score_confidence(decision: dict, evidence: list[dict]) -> dict:
    requirement_id = decision.get("requirement_id") or decision.get("req_id") or "unknown"
    input_confidence = float(decision.get("confidence", 0.5))
    retrieval_scores = [item.get("hybrid_score", item.get("retrieval_score", 0.0)) for item in evidence]
    max_score = max(retrieval_scores, default=0.0)
    avg_score = sum(retrieval_scores) / len(retrieval_scores) if retrieval_scores else 0.0
    contradiction = any(
        any(marker in item.get("text", "").lower() for marker in ("not ", "cannot", "unable", "does not"))
        for item in evidence
    )

    adjusted = (
        (0.5 * input_confidence) + (0.25 * avg_score) + (0.15 * max_score)
        if retrieval_scores
        else input_confidence - 0.15
    )
    if contradiction:
        adjusted -= 0.10
    if len(evidence) >= 3:
        adjusted += 0.05
    adjusted = max(SCORING_CONFIDENCE_FLOOR, min(SCORING_CONFIDENCE_CAP, adjusted))

    output = dict(decision)
    output["confidence"] = adjusted
    output["review_required"] = adjusted < config.CONFIDENCE_THRESHOLD
    output["execution_mode"] = decision.get("execution_mode", "fallback_rules")
    logger.debug(
        "SCORING DIAGNOSTIC req=%s input_confidence=%s output_confidence=%s retrieval_score=%s evidence_count=%d",
        requirement_id,
        input_confidence,
        adjusted,
        max_score,
        len(evidence),
    )
    return output


async def flag_low_confidence(decisions: list[dict], threshold: float = config.CONFIDENCE_THRESHOLD) -> dict:
    review_queue = [decision["requirement_id"] for decision in decisions if decision.get("confidence", 0.0) < threshold]
    return {"review_queue": review_queue, "execution_mode": "fallback_rules"}


def register_skills(registry):
    registry.register(Skill(
        name="score_confidence",
        description="Adjust decision confidence using evidence quality signals.",
        handler=score_confidence,
        input_schema={"decision": "dict", "evidence": "list[dict]"},
        output_schema={"decision": "dict"},
        tags=["scoring", "confidence"],
        llm_tier="none",
    ))
    registry.register(Skill(
        name="flag_low_confidence",
        description="Build a review queue from low-confidence decisions.",
        handler=flag_low_confidence,
        input_schema={"decisions": "list[dict]", "threshold": "float"},
        output_schema={"review_queue": "list[str]"},
        tags=["scoring", "review"],
        llm_tier="none",
    ))
