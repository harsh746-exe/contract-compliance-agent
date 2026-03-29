import os

import pytest

from compliance_agent.agents.compliance_reasoner import ComplianceReasonerAgent
from compliance_agent.agents.confidence_scorer import ConfidenceScorerAgent
from compliance_agent.agents.requirement_classifier import RequirementClassifierAgent
from compliance_agent.agents.requirement_extractor import RequirementExtractorAgent
from compliance_agent.memory.persistent_store import Evidence


@pytest.mark.live
def test_live_llm_smoke_path():
    if os.getenv("RUN_LIVE_LLM_TESTS") != "1":
        pytest.skip("Set RUN_LIVE_LLM_TESTS=1 to run live smoke tests.")
    if not os.getenv("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY is required for live smoke tests.")

    extractor = RequirementExtractorAgent()
    classifier = RequirementClassifierAgent()
    reasoner = ComplianceReasonerAgent()
    scorer = ConfidenceScorerAgent()

    requirements = extractor.extract([{
        "chunk_id": "policy_chunk_1",
        "doc_type": "policy",
        "section_title": "Section 1",
        "page_range": "1-1",
        "text": "The vendor shall provide monthly status reports.",
        "metadata": {},
    }])

    assert requirements

    classified = classifier.classify(requirements)
    evidence = [Evidence(
        evidence_chunk_id="response_chunk_1",
        evidence_text="We provide monthly status reports to the client.",
        evidence_citation="Section 1 1-1",
        retrieval_score=0.95,
        requirement_id=classified[0].req_id,
    )]

    decision = reasoner.reason(classified[0], evidence)
    scored = scorer.score(decision, evidence)

    assert scored.label in {"compliant", "partial", "not_compliant", "not_addressed"}
    assert 0.0 <= scored.confidence <= 1.0
