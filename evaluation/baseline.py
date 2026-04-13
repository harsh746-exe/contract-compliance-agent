"""Baseline comparison for compliance system."""

from __future__ import annotations

import re
from typing import Dict, List

from compliance_agent.ingestion.document_parser import DocumentParser


def _extract_requirements(policy_text: str) -> List[str]:
    candidates = []
    for line in policy_text.splitlines():
        clean = line.strip()
        if not clean:
            continue
        if re.search(r"\b(shall|must|required|requirement)\b", clean, re.IGNORECASE):
            candidates.append(clean)
    if not candidates:
        candidates = [s.strip() for s in re.split(r"[\n\.]", policy_text) if s.strip()][:10]
    return candidates[:25]


class BaselineAgent:
    """Single-pass heuristic baseline used for evaluation comparisons."""

    def process(self, policy_path: str, response_path: str) -> List[Dict]:
        """Process documents using a deterministic lexical baseline."""
        parser = DocumentParser()

        policy_chunks = parser.parse(policy_path, doc_type="policy")
        response_chunks = parser.parse(response_path, doc_type="response")

        policy_text = "\n\n".join([chunk.text for chunk in policy_chunks])
        response_text = "\n\n".join([chunk.text for chunk in response_chunks]).lower()

        requirements = _extract_requirements(policy_text)
        results: List[Dict] = []

        for index, requirement in enumerate(requirements, start=1):
            key_terms = [t.lower() for t in re.findall(r"[A-Za-z]{4,}", requirement)[:8]]
            overlap = sum(1 for term in key_terms if term in response_text)
            coverage = overlap / max(1, len(key_terms))

            if coverage >= 0.7:
                label = "compliant"
                confidence = 0.85
            elif coverage >= 0.35:
                label = "partial"
                confidence = 0.6
            elif overlap > 0:
                label = "not_compliant"
                confidence = 0.45
            else:
                label = "not_addressed"
                confidence = 0.25

            results.append(
                {
                    "requirement_id": f"REQ_{index:04d}",
                    "requirement_text": requirement,
                    "label": label,
                    "explanation": "Lexical overlap baseline.",
                    "confidence": confidence,
                }
            )

        return results
