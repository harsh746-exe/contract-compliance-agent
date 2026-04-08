"""Confidence and Escalation Agent - assigns confidence scores and flags for review."""

from typing import Dict, List

from .. import config
from ..llm import build_default_chat_llm
from ..memory.persistent_store import ComplianceDecision, Evidence


def _build_default_llm():
    return build_default_chat_llm(temperature=0.1)


class ConfidenceScorerAgent:
    """Assigns confidence scores and flags decisions for human review."""

    def __init__(self, llm=None):
        self.llm = llm or _build_default_llm()

    def score(
        self,
        decision: ComplianceDecision,
        evidence_list: List[Evidence],
        working_memory=None,
    ) -> ComplianceDecision:
        """Score confidence and determine if escalation is needed."""
        signals = self._calculate_signals(decision, evidence_list)
        original_confidence = decision.confidence
        adjusted_confidence = self._adjust_confidence(decision.confidence, signals)
        decision.confidence = adjusted_confidence

        escalation_status = self._determine_escalation(adjusted_confidence, signals)

        if working_memory:
            working_memory.log_agent_action(
                agent_name="confidence_scorer",
                action="score_confidence",
                input_data={
                    "requirement_id": decision.requirement_id,
                    "original_confidence": original_confidence,
                    "signals": signals,
                },
                output_data={
                    "adjusted_confidence": adjusted_confidence,
                    "escalation_status": escalation_status,
                },
            )

        if escalation_status != "accept":
            decision.explanation += f"\n[ESCALATION: {escalation_status.upper()}]"

        return decision

    def _calculate_signals(
        self,
        decision: ComplianceDecision,
        evidence_list: List[Evidence],
    ) -> Dict[str, float]:
        """Calculate confidence signals."""
        signals: Dict[str, float] = {}

        if evidence_list:
            retrieval_scores = [ev.retrieval_score for ev in evidence_list]
            signals["avg_retrieval_score"] = sum(retrieval_scores) / len(retrieval_scores)
            signals["max_retrieval_score"] = max(retrieval_scores)
            signals["retrieval_score_variance"] = self._variance(retrieval_scores)
        else:
            signals["avg_retrieval_score"] = 0.0
            signals["max_retrieval_score"] = 0.0
            signals["retrieval_score_variance"] = 1.0

        signals["evidence_count"] = len(evidence_list)

        label_confidence_map = {
            "compliant": 0.9,
            "partial": 0.6,
            "not_compliant": 0.8,
            "not_addressed": 0.7,
        }
        signals["label_baseline"] = label_confidence_map.get(decision.label, 0.5)
        signals["explanation_length"] = min(1.0, len(decision.explanation) / 500.0)
        signals["contradiction_score"] = self._check_contradictions(evidence_list)

        return signals

    def _adjust_confidence(self, base_confidence: float, signals: Dict[str, float]) -> float:
        """Adjust confidence based on signals."""
        adjusted = base_confidence

        if signals["max_retrieval_score"] > 0.8:
            adjusted += 0.1
        elif signals["max_retrieval_score"] < 0.3:
            adjusted -= 0.2

        if signals["evidence_count"] >= 3:
            adjusted += 0.05
        elif signals["evidence_count"] == 0:
            adjusted -= 0.3

        adjusted = (adjusted + signals["label_baseline"]) / 2
        adjusted -= signals["contradiction_score"] * 0.2

        return max(0.0, min(1.0, adjusted))

    def _determine_escalation(self, confidence: float, signals: Dict[str, float]) -> str:
        """Determine if escalation is needed."""
        if confidence >= config.CONFIDENCE_HIGH:
            return "accept"
        if confidence >= config.CONFIDENCE_MEDIUM:
            return "review"
        return "flag"

    def _variance(self, values: List[float]) -> float:
        """Calculate variance."""
        if not values:
            return 0.0
        mean = sum(values) / len(values)
        return sum((x - mean) ** 2 for x in values) / len(values)

    def _check_contradictions(self, evidence_list: List[Evidence]) -> float:
        """Check for contradictions between evidence chunks."""
        if len(evidence_list) < 2:
            return 0.0

        negation_words = ["not", "no", "never", "cannot", "unable", "lacks", "missing"]

        negation_count = 0
        for ev in evidence_list:
            ev_lower = ev.evidence_text.lower()
            if any(neg in ev_lower for neg in negation_words):
                negation_count += 1

        if 0 < negation_count < len(evidence_list):
            return 0.5

        return 0.0

    def get_review_queue(self, decisions: List[ComplianceDecision]) -> List[str]:
        """Get list of requirement IDs that need human review."""
        return [
            decision.requirement_id
            for decision in decisions
            if decision.confidence < config.CONFIDENCE_HIGH
        ]
